"""Digest building and reading."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
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
from standup.domain.errors import NotFoundError
from standup.summarize.service import build_digest
from standup.tracker.outbox import drain

router = APIRouter(tags=["digest"])


@router.get("/digests", response_class=HTMLResponse)
def list_digests(request: Request, session: DbSession, member: CurrentMember) -> HTMLResponse:
    """The viewer's own team only. Other teams' cycles are not listed."""
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
        raise NotFoundError(f"cycle {cycle_id} not found")
    ensure_same_team(member, cycle.team_id, f"cycle {cycle_id}")

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


@router.get("/digest/{digest_id}.md", response_class=PlainTextResponse)
def view_digest_markdown(digest_id: str, session: DbSession, member: CurrentMember) -> str:
    """Registered before the HTML route: Starlette matches in declaration
    order, and ``{digest_id}`` would otherwise swallow the ``.md`` suffix."""
    digest, _cycle = _visible_digest(session, member, digest_id)
    return digest.body_md


def _visible_digest(
    session: DbSession, member: CurrentMember, digest_id: str
) -> tuple[Digest, StandupCycle]:
    """A digest the viewer's team owns, or 404 for anything else."""
    digest = session.get(Digest, digest_id)
    cycle = session.get(StandupCycle, digest.cycle_id) if digest else None
    if digest is None or cycle is None:
        raise NotFoundError(f"digest {digest_id} not found")
    ensure_same_team(member, cycle.team_id, f"digest {digest_id}")
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
    from standup.summarize.render import SECTION_ORDER, SECTION_TITLES

    sections: list[dict[str, Any]] = []
    for kind in SECTION_ORDER:
        claims = [c for c in digest.claims if c.kind == kind.value]
        if claims:
            sections.append(
                {"title": SECTION_TITLES[kind], "claims": sorted(claims, key=lambda c: c.order)}
            )

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


def _age_days(now: datetime, created_at: datetime) -> int:
    # SQLite returns naive datetimes; both sides are UTC.
    if created_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    return max((now - created_at).days, 0)


def drain_tracker_outbox() -> None:
    """Deliver queued blocker writes. Called as a background task after a build."""
    with session_scope() as session:
        drain(session, tracker_from_settings(get_settings()), get_clock().now())
