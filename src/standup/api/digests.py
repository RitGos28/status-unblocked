"""Digest building and reading."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select

from standup.db.models import Digest, StandupCycle, Team, Update
from standup.deps import AppSettings, AppSummarizer, DbSession, templates
from standup.domain.errors import NotFoundError
from standup.summarize.service import build_digest

router = APIRouter(tags=["digest"])


@router.get("/digests", response_class=HTMLResponse)
def list_digests(request: Request, session: DbSession) -> HTMLResponse:
    cycles = (
        session.execute(select(StandupCycle).order_by(StandupCycle.local_date.desc()))
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
            session.execute(select(Update).where(Update.cycle_id == cycle.id)).scalars().all()
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
        context={"rows": rows, "submitted": request.query_params.get("submitted")},
    )


@router.post("/digests/build/{cycle_id}")
def build(
    cycle_id: str,
    session: DbSession,
    summarizer: AppSummarizer,
    settings: AppSettings,
) -> RedirectResponse:
    digest = build_digest(
        session,
        cycle_id=cycle_id,
        summarizer=summarizer,
        base_url=settings.base_url,
    )
    return RedirectResponse(url=f"/digest/{digest.id}", status_code=303)


@router.get("/digest/{digest_id}.md", response_class=PlainTextResponse)
def view_digest_markdown(digest_id: str, session: DbSession) -> str:
    """Registered before the HTML route: Starlette matches in declaration
    order, and ``{digest_id}`` would otherwise swallow the ``.md`` suffix."""
    digest = session.get(Digest, digest_id)
    if digest is None:
        raise NotFoundError(f"digest {digest_id} not found")
    return digest.body_md


@router.get("/digest/{digest_id}", response_class=HTMLResponse)
def view_digest(digest_id: str, request: Request, session: DbSession) -> HTMLResponse:
    digest = session.get(Digest, digest_id)
    if digest is None:
        raise NotFoundError(f"digest {digest_id} not found")

    cycle = session.get(StandupCycle, digest.cycle_id)
    team = session.get(Team, cycle.team_id) if cycle else None

    # Sections in reading order: what is blocking comes before what is done.
    from standup.summarize.render import SECTION_ORDER, SECTION_TITLES

    sections = []
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
        },
    )
