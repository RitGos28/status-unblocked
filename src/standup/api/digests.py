"""Digest building and reading."""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select

from standup.config import get_settings
from standup.db.models import Digest, StandupCycle, Team, TrackerLink, Update
from standup.db.session import session_scope
from standup.deps import (
    AppClock,
    AppSettings,
    AppSummarizer,
    CurrentMember,
    DbSession,
    ensure_same_team,
    get_clock,
    templates,
    tracker_from_settings,
)
from standup.domain.enums import ClaimKind
from standup.domain.errors import NotFoundError
from standup.domain.timezones import as_utc
from standup.privacy.retention import day_was_purged
from standup.summarize.render import SECTION_TITLES, group_sections
from standup.summarize.service import build_digest
from standup.tracker.outbox import drain

router = APIRouter(tags=["digest"])


@router.get("/digests", response_class=HTMLResponse)
def list_digests(
    request: Request, session: DbSession, member: CurrentMember, clock: AppClock
) -> HTMLResponse:
    """The viewer's own team only. Other teams' cycles are not listed."""
    now = clock.now()
    cycles = (
        session.execute(
            select(StandupCycle)
            .where(StandupCycle.team_id == member.team_id)
            .order_by(StandupCycle.local_date.desc())
        )
        .scalars()
        .all()
    )

    rows = []
    for cycle in cycles:
        digest = session.execute(
            select(Digest)
            .where(Digest.cycle_id == cycle.id)
            .order_by(Digest.generated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        update_count = len(
            session.execute(
                select(Update)
                .where(Update.cycle_id == cycle.id)
                .where(Update.is_live())
            )
            .scalars()
            .all()
        )
        team = session.get(Team, cycle.team_id)
        rows.append(
            {
                "cycle": cycle,
                "digest": digest,
                "update_count": update_count,
                "team_name": team.name if team else "Team",
                "status": _status(cycle, now),
                # Retention removed the day's updates: its digest is final.
                "final": day_was_purged(session, cycle.id),
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="digests.html",
        context={
            "rows": rows,
            "submitted": request.query_params.get("submitted"),
            "viewer": member,
        },
    )


@router.post("/digests/build/{cycle_id}")
def build(
    cycle_id: str,
    request: Request,
    session: DbSession,
    member: CurrentMember,
    summarizer: AppSummarizer,
    settings: AppSettings,
    background: BackgroundTasks,
    clock: AppClock,
) -> RedirectResponse:
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
    # Commit now: FastAPI runs background tasks before dependency teardown,
    # which is where get_db would otherwise commit, so the drain would find
    # no outbox rows.
    session.commit()
    # Runs after the response is sent: the page never waits on GitHub.
    background.add_task(drain_tracker_outbox)
    return RedirectResponse(url=f"/digest/{digest.id}", status_code=303)


@router.api_route(
    "/digest/{digest_id}.md", methods=["GET", "HEAD"], response_class=PlainTextResponse
)
def view_digest_markdown(digest_id: str, session: DbSession, member: CurrentMember) -> str:
    """Registered before the HTML route: Starlette matches in declaration
    order, and ``{digest_id}`` would otherwise swallow the ``.md`` suffix."""
    digest, _cycle = _visible_digest(session, member, digest_id)
    return digest.body_md


# Spreadsheet apps run a cell as a formula when it starts with one of these.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: str) -> str:
    """Neutralise user text that a spreadsheet would execute as a formula."""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


@router.api_route("/digest/{digest_id}.csv", methods=["GET", "HEAD"])
def view_digest_csv(digest_id: str, session: DbSession, member: CurrentMember) -> Response:
    """The digest as a spreadsheet: one row per line, with its links.

    Registered before the HTML route, like the Markdown one. Same team
    scoping as the page.
    """
    digest, cycle = _visible_digest(session, member, digest_id)
    team = session.get(Team, cycle.team_id)
    fingerprints = [c.tracker_fingerprint for c in digest.claims if c.tracker_fingerprint]
    issues = {
        link.fingerprint: link.issue_url
        for link in session.execute(
            select(TrackerLink).where(TrackerLink.fingerprint.in_(fingerprints))
        ).scalars()
    }

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["section", "member", "text", "evidence_url", "earlier_report_url", "issue_url"]
    )
    for claim in sorted(digest.claims, key=lambda c: c.order):
        citations = claim.citations_json or []
        writer.writerow(
            [
                SECTION_TITLES[ClaimKind(claim.kind)],
                _cell(claim.member_name),
                _cell(claim.text),
                citations[0].get("evidence_url", "") if citations else "",
                citations[1].get("evidence_url", "") if len(citations) > 1 else "",
                issues.get(claim.tracker_fingerprint, ""),
            ]
        )
    filename = f"{team.slug if team else 'team'}-{cycle.local_date}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _visible_digest(
    session: DbSession, member: CurrentMember, digest_id: str
) -> tuple[Digest, StandupCycle]:
    """A digest the viewer's team owns, or 404 for anything else."""
    digest = session.get(Digest, digest_id)
    cycle = session.get(StandupCycle, digest.cycle_id) if digest else None
    if digest is None or cycle is None:
        raise NotFoundError("That digest does not exist, or it belongs to another team.")
    ensure_same_team(member, cycle.team_id, "digest")
    return digest, cycle


@router.get("/digest/{digest_id}", response_class=HTMLResponse)
def view_digest(
    digest_id: str, request: Request, session: DbSession, member: CurrentMember, clock: AppClock
) -> HTMLResponse:
    digest, cycle = _visible_digest(session, member, digest_id)
    team = session.get(Team, cycle.team_id)
    fingerprints = [c.tracker_fingerprint for c in digest.claims if c.tracker_fingerprint]
    links = {
        link.fingerprint: link
        for link in session.execute(
            select(TrackerLink).where(TrackerLink.fingerprint.in_(fingerprints))
        ).scalars()
    }
    now = clock.now()
    issues = {
        fp: {
            "number": link.issue_number,
            "url": link.issue_url,
            "age_days": _age_days(now, link.created_at),
        }
        for fp, link in links.items()
    }

    # Sections in reading order: what is blocking comes before what is done.
    sections = group_sections(sorted(digest.claims, key=lambda c: c.order))

    return templates.TemplateResponse(
        request=request,
        name="digest.html",
        context={
            "digest": digest,
            "cycle": cycle,
            "team_name": team.name if team else "Team",
            "sections": sections,
            "viewer": member,
            "issues": issues,
        },
    )


def _status(cycle: StandupCycle, now: datetime) -> str:
    """A day's state, in words; an open day past its cutoff is waiting, not collecting."""
    if cycle.state == "digested":
        return "Digest built"
    if cycle.state == "closed":
        return "Closed"
    if cycle.cutoff_at_utc is not None and as_utc(cycle.cutoff_at_utc) <= as_utc(now):
        return "Waiting for its digest"
    return "Collecting updates"


def _age_days(now: datetime, created_at: datetime) -> int:
    return max((as_utc(now) - as_utc(created_at)).days, 0)


def drain_tracker_outbox() -> None:
    """Deliver queued blocker writes. Called as a background task after a build."""
    with session_scope() as session:
        drain(session, tracker_from_settings(get_settings()), get_clock().now())
