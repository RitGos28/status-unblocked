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

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.orm import Session

from standup.db.models import Member, StandupCycle, Team, Update, UpdateItem
from standup.db.upsert import insert_ignoring_conflict
from standup.domain.enums import AuditAction, CycleState
from standup.domain.errors import EmptySubmissionError
from standup.domain.timezones import cutoff_utc, local_cycle_date
from standup.ingestion.base import RawSubmission
from standup.ingestion.normalizer import normalize
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit

log = get_logger(__name__)


def get_or_create_open_cycle(session: Session, team: Team, now: datetime) -> StandupCycle:
    """One cycle per team per local date, in the team's own time zone.

    Safe under concurrency: when several people file the day's first update at
    once, each tries the insert, all but one do nothing (UNIQUE team_id,
    local_date), and everyone then reads the same row.
    """
    local_date = local_cycle_date(now, team.tz_default)
    query = (
        select(StandupCycle)
        .where(StandupCycle.team_id == team.id)
        .where(StandupCycle.local_date == local_date)
    )
    cycle = session.execute(query).scalar_one_or_none()
    if cycle is not None:
        return cycle

    insert_ignoring_conflict(
        session,
        StandupCycle,
        {
            "id": str(uuid.uuid4()),
            "team_id": team.id,
            "local_date": local_date,
            "opens_at_utc": now,
            "cutoff_at_utc": cutoff_utc(local_date, team.cutoff_local_time, team.tz_default),
            "state": CycleState.OPEN.value,
        },
        ["team_id", "local_date"],
    )
    return session.execute(query).scalar_one()


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

    # Serialise this member's submissions: bumping their counter takes the row
    # lock (Postgres) or the write lock (SQLite) until commit, so a double
    # click's second request waits, then sees the first one's update.
    session.execute(
        sql_update(Member)
        .where(Member.id == member.id)
        .values(submission_seq=Member.submission_seq + 1)
    )
    cycle = get_or_create_open_cycle(session, member.team, now)

    # Every live update this member has in the cycle: normally zero or one,
    # but data written before the lock existed may hold several, and this
    # supersedes them all so it recovers instead of failing.
    previous = (
        session.execute(
            select(Update)
            .where(Update.cycle_id == cycle.id)
            .where(Update.member_id == member.id)
            .where(Update.is_live())
            .order_by(Update.captured_at)
        )
        .scalars()
        .all()
    )

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

    for earlier in previous:
        earlier.superseded_by = update.id

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
            **({"supersedes": [earlier.id for earlier in previous]} if previous else {}),
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
        superseded=[earlier.id for earlier in previous],
    )
    return update
