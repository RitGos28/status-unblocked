"""Web-form ingestion.

The adapter that has no external dependencies, so the pipeline is always
demoable. It shares every line downstream of ``RawSubmission`` with the Teams
adapter that arrives in week 2.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from standup.db.models import Member, StandupCycle, Team, Update, UpdateItem
from standup.deps import AppClock, DbSession, templates
from standup.domain.enums import AuditAction, CycleState, SourceKind
from standup.domain.errors import EmptySubmissionError, NotFoundError
from standup.ingestion.normalizer import normalize
from standup.ingestion.web_adapter import WebFormAdapter
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit

router = APIRouter(tags=["ingestion"])
log = get_logger(__name__)


def get_or_create_open_cycle(session: DbSession, team_id: str, now: datetime) -> StandupCycle:
    """One cycle per team per local date."""
    local_date = now.date()
    cycle = session.execute(
        select(StandupCycle)
        .where(StandupCycle.team_id == team_id)
        .where(StandupCycle.local_date == local_date)
    ).scalar_one_or_none()

    if cycle is None:
        cycle = StandupCycle(
            team_id=team_id,
            local_date=local_date,
            opens_at_utc=now,
            state=CycleState.OPEN,
        )
        session.add(cycle)
        session.flush()
    return cycle


@router.get("/submit", response_class=HTMLResponse)
def submit_form(request: Request, session: DbSession) -> HTMLResponse:
    members = session.execute(select(Member).where(Member.active.is_(True))).scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="submit.html",
        context={"members": members},
    )


@router.post("/submit")
def submit(
    session: DbSession,
    clock: AppClock,
    member_id: str = Form(...),
    progress: str = Form(""),
    blockers: str = Form(""),
    plan: str = Form(""),
) -> RedirectResponse:
    now = clock.now()

    member = session.get(Member, member_id)
    if member is None:
        raise NotFoundError(f"member {member_id} not found")

    submission = WebFormAdapter().to_raw_submission(
        {
            "member_id": member_id,
            "progress": progress,
            "blockers": blockers,
            "plan": plan,
            "captured_at": now,
        }
    )
    if submission.is_empty():
        raise EmptySubmissionError("submission contained no text")

    normalized = normalize(submission)
    cycle = get_or_create_open_cycle(session, member.team_id, now)

    update = Update(
        cycle_id=cycle.id,
        member_id=member.id,
        raw_text=normalized.raw_text,
        raw_payload_json=submission.raw_payload
        | {"captured_at": now.isoformat()},
        content_sha256=normalized.content_sha256,
        source_kind=SourceKind.WEBFORM,
        source_ids_json=submission.source_ids,
        permalink=None,
        # Recorded rather than left silently null: a web submission has no
        # platform message, so the evidence view is the citation target.
        permalink_reason="webform: no platform message to link to",
        captured_at=now,
    )
    session.add(update)
    session.flush()

    for item in normalized.items:
        session.add(
            UpdateItem(
                update_id=update.id,
                kind=item.kind.value,
                text=item.text,
                span_start=item.span_start,
                span_end=item.span_end,
                normalized_key=item.normalized_key,
                entity_refs=item.entity_refs,
                order=item.order,
            )
        )

    record_audit(
        session,
        actor_kind="member",
        actor_id=member.id,
        action=AuditAction.UPDATE_INGESTED,
        subject_member_id=member.id,
        object_ids={"update_id": update.id, "cycle_id": cycle.id},
        purpose="standup submission",
    )

    log.info(
        "update.ingested",
        update_id=update.id,
        member_id=member.id,
        cycle_id=cycle.id,
        items=len(normalized.items),
        source=SourceKind.WEBFORM.value,
    )

    return RedirectResponse(url=f"/digests?submitted={update.id}", status_code=303)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: DbSession) -> HTMLResponse:
    teams = session.execute(select(Team)).scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"teams": teams, "now": datetime.now(UTC)},
    )
