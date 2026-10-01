"""Named, expiring leases: "only one of us does this at a time".

A lease is taken with a conditional UPDATE (succeeds only if the current lease
has expired) and committed at once, so no database lock is held while the
holder works. If the holder dies, the lease simply expires. Used to make the
tracker drain, and the scheduler, single-runner across threads and processes.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from standup.db.models import Lease
from standup.db.upsert import insert_ignoring_conflict

_NEVER = datetime(1970, 1, 1, tzinfo=UTC)


def acquire_lease(
    session: Session, name: str, holder: str, now: datetime, ttl: timedelta
) -> bool:
    """Take the lease if it is free or expired. Commits either way."""
    insert_ignoring_conflict(
        session, Lease, {"name": name, "holder": "", "expires_at": _NEVER}, ["name"]
    )
    taken = session.execute(
        update(Lease)
        .where(Lease.name == name)
        .where(Lease.expires_at <= now)
        .values(holder=holder, expires_at=now + ttl)
    ).rowcount
    session.commit()
    return taken == 1


def release_lease(session: Session, name: str, holder: str) -> None:
    """Give the lease back early, if we still hold it. Commits."""
    session.execute(
        update(Lease)
        .where(Lease.name == name)
        .where(Lease.holder == holder)
        .values(expires_at=_NEVER)
    )
    session.commit()
