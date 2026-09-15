"""Hash-chained audit log.

Every read of, or derivation from, someone's raw update text appends a row.
Each row hashes the previous one, so a deletion or edit anywhere in the chain
is detectable by recomputing it.

This is roughly thirty lines of code and it is the most persuasive
"enterprise-grade" artifact in the project: it turns "we don't spy on you" from
a claim into something a member can check for themselves via /me/data, which
lands in week 4.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.domain.enums import AuditAction

GENESIS_HASH = "0" * 64


def timestamp_key(value: datetime) -> str:
    """Canonical timestamp string for hashing.

    SQLite stores DateTime(timezone=True) as a naive value, so a row read back
    is tz-naive while the row we just wrote is tz-aware. Hashing the raw
    isoformat would therefore break the chain on the first verification. We
    normalise to UTC and drop the offset so both sides agree.
    """
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.replace(tzinfo=None).isoformat(timespec="microseconds")


def _canonical_row(
    *,
    ts: str,
    actor_kind: str,
    actor_id: str | None,
    action: str,
    subject_member_id: str | None,
    object_ids: dict[str, Any],
    purpose: str,
) -> str:
    """Deterministic serialisation. Key order is fixed, so the hash is stable."""
    return json.dumps(
        {
            "ts": ts,
            "actor_kind": actor_kind,
            "actor_id": actor_id,
            "action": action,
            "subject_member_id": subject_member_id,
            "object_ids": object_ids,
            "purpose": purpose,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_row_hash(prev_hash: str, canonical: str) -> str:
    return hashlib.sha256(f"{prev_hash}{canonical}".encode()).hexdigest()


def record_audit(
    session: Session,
    *,
    actor_kind: str,
    action: AuditAction,
    actor_id: str | None = None,
    subject_member_id: str | None = None,
    object_ids: dict[str, Any] | None = None,
    purpose: str = "",
):
    """Append one row to the chain. Flushes so ``seq`` is assigned immediately."""
    from standup.db.models import AuditLog

    last = session.execute(
        select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)
    ).scalar_one_or_none()
    prev_hash = last.row_hash if last else GENESIS_HASH

    row = AuditLog(
        actor_kind=actor_kind,
        actor_id=actor_id,
        action=action.value,
        subject_member_id=subject_member_id,
        object_ids_json=object_ids or {},
        purpose=purpose,
        prev_hash=prev_hash,
    )
    session.add(row)
    session.flush()

    row.row_hash = compute_row_hash(
        prev_hash,
        _canonical_row(
            ts=timestamp_key(row.ts),
            actor_kind=actor_kind,
            actor_id=actor_id,
            action=action.value,
            subject_member_id=subject_member_id,
            object_ids=object_ids or {},
            purpose=purpose,
        ),
    )
    session.flush()
    return row


def verify_chain(session: Session) -> tuple[bool, int | None]:
    """Recompute the chain. Returns (intact, first_bad_seq)."""
    from standup.db.models import AuditLog

    rows = session.execute(select(AuditLog).order_by(AuditLog.seq)).scalars().all()

    prev_hash = GENESIS_HASH
    for row in rows:
        if row.prev_hash != prev_hash:
            return False, row.seq

        expected = compute_row_hash(
            prev_hash,
            _canonical_row(
                ts=timestamp_key(row.ts),
                actor_kind=row.actor_kind,
                actor_id=row.actor_id,
                action=row.action,
                subject_member_id=row.subject_member_id,
                object_ids=row.object_ids_json or {},
                purpose=row.purpose,
            ),
        )
        if expected != row.row_hash:
            return False, row.seq
        prev_hash = row.row_hash

    return True, None
