"""The manager portal's JSON API (``/api/manager/*``), for the React app.

One manager, signed in with the username and password pair from settings
(``auth/manager.py``). What it can do, and the line it must not cross, is
invariant 7 in CLAUDE.md: it adds members, reads a team's digests and evidence,
builds digests, and gets a period summary built from the validated digest
claims. It sees nothing about a person that their teammates cannot see: no
per-person metrics, no "who has not submitted", no stored text outside the
audited evidence view. Every read of someone's words here is recorded under
``actor_kind="manager"`` and shows on that person's My data page.
"""

from collections import OrderedDict
from datetime import date, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, BackgroundTasks, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from standup.api.api_router import cycle_rows, digest_payload, evidence_payload
from standup.api.digests import drain_tracker_outbox
from standup.auth.manager import (
    MANAGER_SESSION_KEY,
    MANAGER_SIGN_IN_FAILED,
    check_manager_credentials,
)
from standup.auth.team_code import format_team_code, normalise_name
from standup.db.models import Digest, Member, StandupCycle, Team, TrackerLink, Update, UpdateItem
from standup.deps import (
    AppClock,
    AppSettings,
    AppSummarizer,
    CurrentManager,
    DbSession,
    OptionalManager,
)
from standup.domain.enums import BLOCKER_KINDS, AuditAction, ClaimKind
from standup.domain.errors import (
    BadRequestError,
    ConflictError,
    ManagerUnauthorizedError,
    NotFoundError,
)
from standup.domain.timezones import local_cycle_date
from standup.domain.urls import public_base_url
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit
from standup.summarize.render import SECTION_TITLES, explain_rule
from standup.summarize.service import build_digest, latest_digest

router = APIRouter(prefix="/api/manager", tags=["manager"])
log = get_logger(__name__)

# The summary window: a week by default, never more than a quarter.
SUMMARY_DEFAULT_DAYS = 7
SUMMARY_MAX_DAYS = 90


class ManagerLoginPayload(BaseModel):
    username: str = Field(default="")
    password: str = Field(default="")


class NewMemberPayload(BaseModel):
    display_name: str = Field(default="")
    tz: str = Field(default="UTC")


def _format_team(team: Team) -> dict[str, Any]:
    return {
        "id": team.id,
        "slug": team.slug,
        "name": team.name,
        "tz_default": team.tz_default,
        "cutoff_local_time": team.cutoff_local_time,
        "retention_days": team.retention_days,
        "github_repo": team.github_repo,
        # The manager needs the code to onboard the member they just added.
        "join_code": format_team_code(team.join_code),
        "member_count": sum(1 for m in team.members if m.active),
    }


def _format_member(member: Member) -> dict[str, Any]:
    return {
        "id": member.id,
        "display_name": member.display_name,
        "tz": member.tz,
        "active": member.active,
        "teams_linked": member.teams_aad_id is not None,
    }


def _team_or_404(session: DbSession, team_id: str) -> Team:
    team = session.get(Team, team_id)
    if team is None:
        raise NotFoundError("That team does not exist.")
    return team


# --- sign-in -----------------------------------------------------------------


@router.get("/me")
def manager_me(manager: OptionalManager, settings: AppSettings) -> dict[str, Any]:
    """Whether the portal is on, and whether this session is signed in to it."""
    return {
        "enabled": settings.manager_enabled,
        "authenticated": manager is not None,
        "username": manager,
    }


@router.post("/login")
def manager_login(
    payload: ManagerLoginPayload, request: Request, settings: AppSettings
) -> dict[str, Any]:
    """Sign in with the portal's username and password; keeps any member sign-in."""
    if not settings.manager_enabled:
        raise NotFoundError(
            "The manager portal is not switched on: set STANDUP_MANAGER_USERNAME "
            "and STANDUP_MANAGER_PASSWORD."
        )
    assert settings.manager_password is not None  # manager_enabled checked it
    ok = check_manager_credentials(
        settings.manager_username,
        settings.manager_password.get_secret_value(),
        payload.username,
        payload.password,
    )
    if not ok:
        # Neither field is logged: one of them may be a near miss of the real one.
        log.info("manager.login_rejected")
        raise ManagerUnauthorizedError(MANAGER_SIGN_IN_FAILED)
    request.session[MANAGER_SESSION_KEY] = settings.manager_username.strip()
    log.info("manager.login")
    return {"success": True, "username": settings.manager_username.strip()}


@router.post("/logout")
def manager_logout(request: Request) -> dict[str, Any]:
    """Sign the manager out; a member signed in on the same browser stays signed in."""
    request.session.pop(MANAGER_SESSION_KEY, None)
    return {"success": True}


# --- teams and members -------------------------------------------------------


@router.get("/teams")
def manager_teams(session: DbSession, _manager: CurrentManager) -> dict[str, Any]:
    """Every team, to pick one. The dashboard shows one team at a time."""
    teams = session.execute(select(Team).order_by(Team.name)).scalars().all()
    return {"teams": [_format_team(team) for team in teams]}


@router.get("/teams/{team_id}")
def manager_team(session: DbSession, _manager: CurrentManager, team_id: str) -> dict[str, Any]:
    """One team: its members, its code, and its standup days with their digests."""
    team = _team_or_404(session, team_id)
    members = sorted(
        (m for m in team.members if m.active), key=lambda m: normalise_name(m.display_name)
    )
    return {
        "team": _format_team(team),
        "members": [_format_member(m) for m in members],
        "days": cycle_rows(session, team.id),
    }


@router.post("/teams/{team_id}/members")
def manager_add_member(
    session: DbSession,
    manager: CurrentManager,
    team_id: str,
    payload: NewMemberPayload,
) -> dict[str, Any]:
    """Add a member to the team. They sign in with the team's code and this name."""
    team = _team_or_404(session, team_id)
    display_name = " ".join(payload.display_name.split())
    if not display_name:
        raise BadRequestError("A member needs a name.")
    if len(display_name) > 200:
        raise BadRequestError("That name is too long (200 characters at most).")
    tz = payload.tz.strip() or "UTC"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise BadRequestError(
            f"{tz!r} is not a time zone name; use one like Europe/London or Asia/Kolkata."
        ) from exc
    # Sign-in resolves the code plus a name to one member, so names are unique
    # per team, compared the way sign-in compares them.
    wanted = normalise_name(display_name)
    for existing in team.members:
        if existing.active and normalise_name(existing.display_name) == wanted:
            raise ConflictError(f"{existing.display_name} is already on {team.name}.")

    member = Member(
        team_id=team.id,
        display_name=display_name,
        tz=tz,
        source_keys={"webform": display_name.lower().replace(" ", ".")},
    )
    session.add(member)
    session.flush()
    record_audit(
        session,
        actor_kind="manager",
        actor_id=manager,
        action=AuditAction.MEMBER_ADDED,
        subject_member_id=member.id,
        object_ids={"team_id": team.id, "member_id": member.id},
        purpose="the manager added a team member",
    )
    log.info("manager.member_added", team_id=team.id, member_id=member.id)
    return {
        "success": True,
        "member": _format_member(member),
        "join_code": format_team_code(team.join_code),
    }


# --- digests and evidence ------------------------------------------------------


@router.post("/digests/build/{cycle_id}")
def manager_build_digest(
    cycle_id: str,
    request: Request,
    session: DbSession,
    manager: CurrentManager,
    summarizer: AppSummarizer,
    settings: AppSettings,
    background: BackgroundTasks,
    clock: AppClock,
) -> dict[str, Any]:
    """Build (or rebuild) one day's digest, exactly as a member's Build does."""
    cycle = session.get(StandupCycle, cycle_id)
    if cycle is None:
        raise NotFoundError("That standup day does not exist.")
    digest = build_digest(
        session,
        cycle_id=cycle_id,
        summarizer=summarizer,
        base_url=public_base_url(settings.base_url, str(request.base_url)),
        now=clock.now(),
        actor_id=f"manager:{manager}",
    )
    # Commit before the background drain, as api/digests.py explains.
    session.commit()
    background.add_task(drain_tracker_outbox)
    return {"success": True, "digest_id": digest.id, "cycle_id": cycle.id}


@router.get("/digest/{digest_id}")
def manager_digest(
    digest_id: str, session: DbSession, _manager: CurrentManager, clock: AppClock
) -> dict[str, Any]:
    """A digest, in the same shape the member's page gets."""
    digest = session.get(Digest, digest_id)
    cycle = session.get(StandupCycle, digest.cycle_id) if digest else None
    if digest is None or cycle is None:
        raise NotFoundError("That digest does not exist.")
    return digest_payload(session, digest, cycle, clock.now())


@router.get("/evidence/{item_id}")
def manager_evidence(item_id: str, session: DbSession, manager: CurrentManager) -> dict[str, Any]:
    """The cited words in their stored update. Audited as the manager, so the
    member sees "<username> (manager) opened your update" on My data."""
    item = session.get(UpdateItem, item_id)
    update = session.get(Update, item.update_id) if item else None
    if item is None or update is None:
        raise NotFoundError("That evidence does not exist.")
    record_audit(
        session,
        actor_kind="manager",
        actor_id=manager,
        action=AuditAction.EVIDENCE_VIEWED,
        subject_member_id=update.member_id,
        object_ids={"update_item_id": item_id, "update_id": update.id},
        purpose="citation verification (manager portal)",
    )
    return evidence_payload(item, update)


# --- the period summary --------------------------------------------------------


@router.get("/teams/{team_id}/summary")
def manager_summary(
    session: DbSession,
    _manager: CurrentManager,
    clock: AppClock,
    team_id: str,
    days: Annotated[int, Query(ge=1, le=SUMMARY_MAX_DAYS)] = SUMMARY_DEFAULT_DAYS,
) -> dict[str, Any]:
    """The last ``days`` standup days of one team, read from its digests.

    Nothing here is summarised afresh: every line is a validated digest claim,
    so the manager's summary is exactly as faithful as the digests it is made
    of. A day without a digest shows how many updates are waiting for one.
    Blockers are grouped by their tracker fingerprint across days; one is
    "open" when the most recent digest in the window still reports it.
    """
    team = _team_or_404(session, team_id)
    today = local_cycle_date(clock.now(), team.tz_default)
    start = today - timedelta(days=days - 1)
    cycles = (
        session.execute(
            select(StandupCycle)
            .where(StandupCycle.team_id == team.id)
            .where(StandupCycle.local_date >= start)
            .where(StandupCycle.local_date <= today)
            .order_by(StandupCycle.local_date)
        )
        .scalars()
        .all()
    )

    by_day: list[dict[str, Any]] = []
    blockers: OrderedDict[str, dict[str, Any]] = OrderedDict()
    by_member: dict[str, dict[str, Any]] = {}
    latest_digested: date | None = None
    digests_built = 0
    updates_total = 0

    for cycle in cycles:
        digest = latest_digest(session, cycle.id)
        update_count = len(
            session.execute(
                select(Update.id).where(Update.cycle_id == cycle.id).where(Update.is_live())
            ).all()
        )
        updates_total += update_count
        counts = {kind.value: 0 for kind in ClaimKind}
        if digest is not None:
            digests_built += 1
            latest_digested = cycle.local_date
            for claim in sorted(digest.claims, key=lambda c: c.order):
                counts[claim.kind] += 1
                line = {
                    "day": str(cycle.local_date),
                    "kind": claim.kind,
                    "section": SECTION_TITLES[ClaimKind(claim.kind)],
                    "text": claim.text,
                    "rule_explanation": explain_rule(claim.matched_rule),
                    "claim_id": claim.id,
                    "digest_id": digest.id,
                    "citations": claim.citations_json,
                }
                person = by_member.setdefault(
                    claim.member_id,
                    {"member_id": claim.member_id, "display_name": claim.member_name, "lines": []},
                )
                person["lines"].append(line)
                if claim.kind in BLOCKER_KINDS:
                    key = claim.tracker_fingerprint or f"{claim.member_id}:{claim.text.casefold()}"
                    entry = blockers.get(key)
                    if entry is None:
                        entry = blockers[key] = {
                            "member_id": claim.member_id,
                            "member_name": claim.member_name,
                            "first_day": str(cycle.local_date),
                            "days_reported": 0,
                            "tracker_fingerprint": claim.tracker_fingerprint,
                        }
                    # The latest day's wording and citations are the ones shown.
                    entry.update(
                        {
                            "text": claim.text,
                            "last_day": str(cycle.local_date),
                            "days_reported": entry["days_reported"] + 1,
                            "claim_id": claim.id,
                            "digest_id": digest.id,
                            "citations": claim.citations_json,
                        }
                    )
        by_day.append(
            {
                "local_date": str(cycle.local_date),
                "cycle_id": cycle.id,
                "state": cycle.state,
                "digest_id": digest.id if digest else None,
                "update_count": update_count,
                "blockers": counts[ClaimKind.BLOCKER.value] + counts[ClaimKind.CARRYOVER.value],
                "progress": counts[ClaimKind.PROGRESS.value],
                "plan": counts[ClaimKind.PLAN.value],
                "withheld": digest.withheld_count if digest else 0,
            }
        )

    fingerprints = [b["tracker_fingerprint"] for b in blockers.values() if b["tracker_fingerprint"]]
    issues = {
        link.fingerprint: {"number": link.issue_number, "url": link.issue_url}
        for link in session.execute(
            select(TrackerLink).where(TrackerLink.fingerprint.in_(fingerprints))
        ).scalars()
    }
    for entry in blockers.values():
        entry["issue"] = issues.get(entry["tracker_fingerprint"])
        entry["open"] = latest_digested is not None and entry["last_day"] == str(latest_digested)

    return {
        "team": _format_team(team),
        "period": {"from": str(start), "to": str(today), "days": days},
        "totals": {
            "days_with_updates": len(cycles),
            "digests_built": digests_built,
            "updates": updates_total,
            "open_blockers": sum(1 for b in blockers.values() if b["open"]),
        },
        "by_day": by_day,
        "blockers": {
            "open": [b for b in blockers.values() if b["open"]],
            "earlier": [b for b in blockers.values() if not b["open"]],
        },
        "by_member": sorted(by_member.values(), key=lambda p: normalise_name(p["display_name"])),
    }
