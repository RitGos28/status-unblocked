"""Retention: stored submissions are kept only for the team's retention period.

After ``team.retention_days`` an update's full submission (``raw_text`` and
``raw_payload_json``) is removed, and so is every line of it that no digest
quoted (``UpdateItem.text`` becomes None); ``purged_at`` is set. What stays:
the lines a digest quoted, because the digest is the team's record and must
stay readable and verifiable. The evidence page then says the source expired,
or, for a removed line, that it was removed. A purged day cannot be rebuilt.

Each purge is audited under the member it concerns (actor "retention"), so it
appears on that member's /me/data page. The scheduler runs this on every pass.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.db.models import Digest, DigestClaim, StandupCycle, Team, Update
from standup.domain.enums import AuditAction
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit

log = get_logger(__name__)


def purge_expired(session: Session, now: datetime) -> int:
    """Purge every update older than its team's retention period. Returns how many."""
    purged = 0
    for team in session.execute(select(Team)).scalars():
        cutoff = now - timedelta(days=team.retention_days)
        quoted = _quoted_item_ids(session, team.id)
        expired = session.execute(
            select(Update)
            .join(StandupCycle, Update.cycle_id == StandupCycle.id)
            .where(StandupCycle.team_id == team.id)
            .where(Update.purged_at.is_(None))
            .where(Update.captured_at < cutoff)
        ).scalars().all()
        for update in expired:
            update.raw_text = None
            update.raw_payload_json = None
            for item in update.items:
                if item.id not in quoted:
                    item.text = None
            update.purged_at = now
            record_audit(
                session,
                actor_kind="system",
                actor_id="retention",
                action=AuditAction.DATA_DELETED,
                subject_member_id=update.member_id,
                object_ids={"update_id": update.id, "retention_days": team.retention_days},
                purpose="retention: stored submission removed after the team's retention period",
            )
            purged += 1
    if purged:
        session.flush()
        log.info("retention.purged", updates=purged)
    return purged


def _quoted_item_ids(session: Session, team_id: str) -> set[str]:
    """Every line any of the team's digests cites, carry-over citations included."""
    citations = session.execute(
        select(DigestClaim.citations_json)
        .join(Digest, DigestClaim.digest_id == Digest.id)
        .join(StandupCycle, Digest.cycle_id == StandupCycle.id)
        .where(StandupCycle.team_id == team_id)
    ).scalars()
    return {c["source_id"] for claim in citations for c in (claim or [])}


def day_was_purged(session: Session, cycle_id: str) -> bool:
    """True when retention removed this day's updates and none is left to rebuild from."""
    updates = session.execute(
        select(Update.purged_at).where(Update.cycle_id == cycle_id)
    ).scalars().all()
    return bool(updates) and all(purged is not None for purged in updates)
