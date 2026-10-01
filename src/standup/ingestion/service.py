"""The single ingestion path.

Every adapter (web form today; Teams, CSV import and the demo seed next) ends
here, so the invariants that make a citation verifiable are enforced once:

- ``raw_text`` and its item offsets come from ``normalize()`` and are written
  once (invariants 2 and 3).
- the content hash is pinned into the audit chain (invariant 10).
- the cycle is the team's local date (invariant 11).
- a resubmission supersedes the member's earlier update in that cycle instead
  of editing it.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.db.models import Member, StandupCycle, Team, Update, UpdateItem
from standup.domain.enums import AuditAction, CycleState
from standup.domain.errors import EmptySubmissionError
from standup.domain.timezones import cutoff_utc, local_cycle_date
from standup.ingestion.base import RawSubmission
from standup.ingestion.normalizer import normalize
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit

log = get_logger(__name__)


def get_or_create_open_cycle(session: Session, team: Team, now: datetime) -> StandupCycle:
    """One cycle per team per local date, in the team's own time zone."""
    local_date = local_cycle_date(now, team.tz_default)
    cycle = session.execute(
        select(StandupCycle)
        .where(StandupCycle.team_id == team.id)
        .where(StandupCycle.local_date == local_date)
    ).scalar_one_or_none()

    if cycle is None:
        cycle = StandupCycle(
            team_id=team.id,
            local_date=local_date,
            opens_at_utc=now,
            cutoff_at_utc=cutoff_utc(local_date, team.cutoff_local_time, team.tz_default),
            state=CycleState.OPEN,
        )
        session.add(cycle)
        session.flush()
    return cycle


def ingest(
    session: Session,
    submission: RawSubmission,
    member: Member,
    now: datetime,
    *,
    permalink: str | None = None,
    permalink_reason: str | None = None,
) -> Update:
    """Store one submission for ``member`` and return the new ``Update``."""
    if submission.is_empty():
        raise EmptySubmissionError("submission contained no text")

    normalized = normalize(submission)
    cycle = get_or_create_open_cycle(session, member.team, now)

    previous = session.execute(
        select(Update)
        .where(Update.cycle_id == cycle.id)
        .where(Update.member_id == member.id)
        .where(Update.superseded_by.is_(None))
    ).scalar_one_or_none()

    update = Update(
        cycle_id=cycle.id,
        member_id=member.id,
        raw_text=normalized.raw_text,
        raw_payload_json=submission.raw_payload | {"captured_at": now.isoformat()},
        content_sha256=normalized.content_sha256,
        source_kind=submission.source_kind,
        source_ids_json=submission.source_ids,
        permalink=permalink,
        # Recorded rather than left silently null when there is no permalink.
        permalink_reason=None if permalink else permalink_reason,
        captured_at=now,
    )
    session.add(update)
    session.flush()

    if previous is not None:
        previous.superseded_by = update.id

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
        # The content hash goes into the hash chain, so editing raw_text later
        # is detectable: privacy.audit.verify_evidence recomputes and compares.
        object_ids={
            "update_id": update.id,
            "cycle_id": cycle.id,
            "content_sha256": normalized.content_sha256,
            **({"supersedes": previous.id} if previous is not None else {}),
        },
        purpose="standup submission",
    )

    log.info(
        "update.ingested",
        update_id=update.id,
        member_id=member.id,
        cycle_id=cycle.id,
        items=len(normalized.items),
        source=submission.source_kind.value,
        superseded=previous.id if previous is not None else None,
    )
    return update
