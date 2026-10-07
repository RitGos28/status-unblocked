"""REST API endpoints for the modern React frontend.

These endpoints return structured JSON for all client-side operations:
authentication, updates submission, digest browsing, and verifiable evidence lookup.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from standup.api.digests import drain_tracker_outbox, view_digest_csv, view_digest_markdown
from standup.api.me import _events_about, _my_updates, my_export
from standup.auth.signin import SIGN_IN_FAILED, sign_in, team_summary
from standup.auth.teams_link import TEAMS_LINK_MAX_AGE_SECONDS, issue_teams_link_code
from standup.db.models import Digest, Member, StandupCycle, Team, TrackerLink, Update, UpdateItem
from standup.deps import (
    AppClock,
    AppSettings,
    AppSummarizer,
    CurrentMember,
    DbSession,
    OptionalMember,
    ensure_same_team,
)
from standup.domain.enums import AuditAction
from standup.domain.errors import NotFoundError, UnauthorizedError
from standup.ingestion.permalink import describe_missing_permalink
from standup.ingestion.service import ingest
from standup.ingestion.web_adapter import WebFormAdapter
from standup.privacy.audit import record_audit
from standup.privacy.retention import day_was_purged
from standup.summarize.render import SECTION_HINTS, SECTION_ORDER, SECTION_TITLES, explain_rule
from standup.summarize.service import build_digest, latest_digest

router = APIRouter(prefix="/api", tags=["frontend-api"])


class LoginPayload(BaseModel):
    team_code: str = Field(default="")
    name: str = Field(default="")


class SubmitPayload(BaseModel):
    progress: str = Field(default="")
    blockers: str = Field(default="")
    plan: str = Field(default="")


def _format_member(member: Member) -> dict[str, Any]:
    return {
        "id": member.id,
        "display_name": member.display_name,
        "team_id": member.team_id,
        "team_name": member.team.name if member.team else "Team",
        "tz": member.tz,
        "teams_aad_id": member.teams_aad_id,
    }


def _age_days(now: datetime, created_at: datetime) -> int:
    if created_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    return max((now - created_at).days, 0)


@router.get("/me")
def get_current_user(viewer: OptionalMember) -> dict[str, Any]:
    """Get the signed-in member status."""
    if viewer is None:
        return {"authenticated": False, "member": None}
    return {
        "authenticated": True,
        "member": _format_member(viewer),
    }


@router.post("/auth/login")
def api_login(payload: LoginPayload, request: Request, session: DbSession) -> dict[str, Any]:
    """Sign in with a team code and a name; sets the session cookie."""
    member = sign_in(session, payload.team_code, payload.name)
    if member is None:
        raise UnauthorizedError(SIGN_IN_FAILED)

    request.session.clear()
    request.session["member_id"] = member.id
    return {
        "success": True,
        "member": _format_member(member),
    }


@router.post("/auth/logout")
def api_logout(request: Request) -> dict[str, Any]:
    """Sign out the current member."""
    request.session.clear()
    return {"success": True}


def cycle_rows(session: DbSession, team_id: str) -> list[dict[str, Any]]:
    """One team's standup days, newest first, each with its latest digest.

    Shared by the member's list and the manager portal, so both show the same
    days and link the same build (invariant 14: by build order, not clock).
    """
    cycles = (
        session.execute(
            select(StandupCycle)
            .where(StandupCycle.team_id == team_id)
            .order_by(StandupCycle.local_date.desc())
        )
        .scalars()
        .all()
    )
    team = session.get(Team, team_id)
    rows = []
    for cycle in cycles:
        digest = latest_digest(session, cycle.id)
        update_count = len(
            session.execute(
                select(Update)
                .where(Update.cycle_id == cycle.id)
                .where(Update.is_live())
            )
            .scalars()
            .all()
        )
        rows.append(
            {
                "cycle": {
                    "id": cycle.id,
                    "local_date": str(cycle.local_date),
                    "state": cycle.state,
                },
                "digest": {
                    "id": digest.id,
                    "generated_at": digest.generated_at.isoformat() if digest else None,
                }
                if digest
                else None,
                "update_count": update_count,
                # Retention removed the day's stored text: nothing to rebuild from.
                "final": day_was_purged(session, cycle.id),
                "team_name": team.name if team else "Team",
            }
        )
    return rows


@router.get("/digests")
def api_list_digests(session: DbSession, member: CurrentMember) -> dict[str, Any]:
    """List standup cycles and digests for the viewer's team."""
    return {
        "viewer": _format_member(member),
        "rows": cycle_rows(session, member.team_id),
    }


@router.post("/digests/build/{cycle_id}")
def api_build_digest(
    cycle_id: str,
    request: Request,
    session: DbSession,
    member: CurrentMember,
    summarizer: AppSummarizer,
    settings: AppSettings,
    background: BackgroundTasks,
    clock: AppClock,
) -> dict[str, Any]:
    """Trigger a digest build for a specific standup cycle."""
    cycle = session.get(StandupCycle, cycle_id)
    if cycle is None:
        raise NotFoundError("That standup day does not exist, or it belongs to another team.")
    ensure_same_team(member, cycle.team_id, "standup day")

    digest = build_digest(
        session,
        cycle_id=cycle_id,
        summarizer=summarizer,
        base_url=settings.base_url or str(request.base_url),
        now=clock.now(),
        actor_id=member.id,
    )
    session.commit()
    background.add_task(drain_tracker_outbox)
    return {
        "success": True,
        "digest_id": digest.id,
        "cycle_id": cycle.id,
    }


# The downloads, under /api so the React app's proxy reaches them. Registered
# before /digest/{digest_id}, which would otherwise swallow the suffix.
@router.api_route("/digest/{digest_id}.md", methods=["GET", "HEAD"])
def api_digest_markdown(digest_id: str, session: DbSession, member: CurrentMember) -> Response:
    """The digest as Markdown, the same text as /digest/{id}.md."""
    body = view_digest_markdown(digest_id, session, member)
    return Response(content=body, media_type="text/plain; charset=utf-8")


@router.api_route("/digest/{digest_id}.csv", methods=["GET", "HEAD"])
def api_digest_csv(digest_id: str, session: DbSession, member: CurrentMember) -> Response:
    """The digest as a spreadsheet, the same file as /digest/{id}.csv."""
    return view_digest_csv(digest_id, session, member)


@router.get("/digest/{digest_id}")
def api_view_digest(
    digest_id: str, session: DbSession, member: CurrentMember, clock: AppClock
) -> dict[str, Any]:
    """Retrieve full structured digest content for the viewer's team."""
    digest = session.get(Digest, digest_id)
    cycle = session.get(StandupCycle, digest.cycle_id) if digest else None
    if digest is None or cycle is None:
        raise NotFoundError("That digest does not exist, or it belongs to another team.")
    ensure_same_team(member, cycle.team_id, "digest")
    return digest_payload(session, digest, cycle, clock.now()) | {
        "viewer": _format_member(member)
    }


def digest_payload(
    session: DbSession, digest: Digest, cycle: StandupCycle, now: datetime
) -> dict[str, Any]:
    """A digest as the React app renders it: sections of validated claims,
    each with its citations and tracker issue. Shared with the manager portal."""
    team = session.get(Team, cycle.team_id)
    fingerprints = [c.tracker_fingerprint for c in digest.claims if c.tracker_fingerprint]
    links = {
        link.fingerprint: link
        for link in session.execute(
            select(TrackerLink).where(TrackerLink.fingerprint.in_(fingerprints))
        ).scalars()
    }
    issues = {
        fp: {
            "number": link.issue_number,
            "url": link.issue_url,
            "age_days": _age_days(now, link.created_at),
        }
        for fp, link in links.items()
    }

    sections: list[dict[str, Any]] = []
    for kind in SECTION_ORDER:
        claims = [c for c in digest.claims if c.kind == kind.value]
        if claims:
            claims_data = []
            for claim in sorted(claims, key=lambda c: c.order):
                issue = issues.get(claim.tracker_fingerprint) if claim.tracker_fingerprint else None
                claims_data.append(
                    {
                        "id": claim.id,
                        "member_name": claim.member_name,
                        "text": claim.text,
                        "matched_rule": claim.matched_rule,
                        "rule_explanation": explain_rule(claim.matched_rule),
                        "tracker_fingerprint": claim.tracker_fingerprint,
                        "issue": issue,
                        "citations": claim.citations_json,
                    }
                )
            sections.append(
                {
                    "kind": kind.value,
                    "title": SECTION_TITLES[kind],
                    "hint": SECTION_HINTS[kind],
                    "claims": claims_data,
                }
            )

    return {
        "digest": {
            "id": digest.id,
            "cycle_id": digest.cycle_id,
            "generated_at": digest.generated_at.isoformat(),
            "summarizer_name": digest.summarizer_name,
            "summarizer_version": digest.summarizer_version,
            "withheld_count": digest.withheld_count,
            "truncated_count": digest.truncated_count,
            "body_md": digest.body_md,
        },
        "cycle": {
            "id": cycle.id,
            "local_date": str(cycle.local_date),
            "state": cycle.state,
        },
        "team_name": team.name if team else "Team",
        "sections": sections,
    }


@router.post("/submit")
def api_submit(
    session: DbSession,
    clock: AppClock,
    member: CurrentMember,
    payload: SubmitPayload,
) -> dict[str, Any]:
    """Submit today's standup update via JSON payload."""
    now = clock.now()
    submission = WebFormAdapter().to_raw_submission(
        {
            "member_id": member.id,
            "progress": payload.progress,
            "blockers": payload.blockers,
            "plan": payload.plan,
            "captured_at": now,
        }
    )
    update = ingest(
        session,
        submission,
        member,
        now,
        permalink_reason="webform: no platform message to link to",
    )
    return {
        "success": True,
        "update_id": update.id,
        "cycle_id": update.cycle_id,
    }


@router.get("/evidence/{item_id}")
def api_view_evidence(
    item_id: str, session: DbSession, member: CurrentMember
) -> dict[str, Any]:
    """Fetch citation evidence and record an audit row."""
    item = session.get(UpdateItem, item_id)
    update = session.get(Update, item.update_id) if item else None
    cycle = session.get(StandupCycle, update.cycle_id) if update else None
    if item is None or update is None or cycle is None:
        raise NotFoundError("That evidence does not exist, or it belongs to another team.")
    ensure_same_team(member, cycle.team_id, "evidence")

    record_audit(
        session,
        actor_kind="member",
        actor_id=member.id,
        action=AuditAction.EVIDENCE_VIEWED,
        subject_member_id=update.member_id,
        object_ids={"update_item_id": item_id, "update_id": update.id},
        purpose="citation verification",
    )
    return evidence_payload(item, update)


def evidence_payload(item: UpdateItem, update: Update) -> dict[str, Any]:
    """The stored text around a cited span. The caller has already recorded
    the audit row, because who is looking differs (a member or the manager)."""
    if update.is_purged or update.raw_text is None:
        return {
            "expired": True,
            "quote": item.text,
            "before": "",
            "after": "",
            "item": {
                "id": item.id,
                "span_start": item.span_start,
                "span_end": item.span_end,
                "kind": item.kind,
            },
            "member_name": update.member.display_name if update.member else "Unknown",
            "purged_at": update.purged_at.isoformat() if update.purged_at else None,
            "captured_at": update.captured_at.isoformat(),
            "source_kind": update.source_kind,
            "permalink": update.permalink,
            "permalink_reason": describe_missing_permalink(update.permalink_reason)
            if update.permalink_reason
            else None,
        }

    raw = update.raw_text
    return {
        "expired": False,
        "quote": raw[item.span_start : item.span_end],
        "before": raw[: item.span_start],
        "after": raw[item.span_end :],
        "item": {
            "id": item.id,
            "span_start": item.span_start,
            "span_end": item.span_end,
            "kind": item.kind,
        },
        "member_name": update.member.display_name if update.member else "Unknown",
        "captured_at": update.captured_at.isoformat(),
        "source_kind": update.source_kind,
        "permalink": update.permalink,
        "permalink_reason": describe_missing_permalink(update.permalink_reason)
        if update.permalink_reason
        else None,
    }


@router.get("/me/team")
def api_my_team(member: CurrentMember) -> dict[str, Any]:
    """The member's team: its sign-in code to share, and who is on it."""
    return {"team": team_summary(member.team), "viewer": _format_member(member)}


@router.get("/me/data")
def api_my_data(session: DbSession, member: CurrentMember) -> dict[str, Any]:
    """Everything stored about the member, and every recorded access to it."""
    return {
        "updates": _my_updates(session, member),
        "events": _events_about(session, member),
        "viewer": _format_member(member),
    }


@router.get("/me/export")
def api_my_export(session: DbSession, member: CurrentMember) -> Response:
    """The same JSON file as /me/export; the export is audited the same way."""
    return my_export(session, member)


@router.get("/me/teams")
def api_teams_link(
    member: CurrentMember, settings: AppSettings
) -> dict[str, Any]:
    """Retrieve personal linking code for Microsoft Teams."""
    code = issue_teams_link_code(
        settings.secret_key.get_secret_value(), member.id, member.teams_aad_id
    )
    return {
        "teams_enabled": settings.teams_enabled,
        "linked": member.teams_aad_id is not None,
        "code": code,
        "minutes": TEAMS_LINK_MAX_AGE_SECONDS // 60,
        "viewer": _format_member(member),
    }
