"""Digest building and reading."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select

from standup.db.models import Digest, StandupCycle, Team, Update
from standup.deps import (
    AppSettings,
    AppSummarizer,
    CurrentMember,
    DbSession,
    ensure_same_team,
    templates,
)
from standup.domain.errors import NotFoundError
from standup.summarize.service import build_digest

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
                .where(Update.superseded_by.is_(None))
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
        actor_id=member.id,
    )
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
    digest_id: str, request: Request, session: DbSession, member: CurrentMember
) -> HTMLResponse:
    digest, cycle = _visible_digest(session, member, digest_id)
    team = session.get(Team, cycle.team_id)

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
        },
    )
