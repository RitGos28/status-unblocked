"""Team-local calendar arithmetic. Pure: stdlib only, no I/O.

A standup "day" is the team's local date, not the UTC date. Without this, a
Singapore member submitting at 08:00 local (00:00 UTC) and a Sao Paulo member
submitting at 18:00 local the previous evening could land in different cycles
for what the team experiences as one working day, or the same cycle for two.
"""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


def as_utc(value: datetime) -> datetime:
    """An aware UTC datetime. Naive values are UTC already: SQLite returns
    stored timestamps without their zone, and every stored timestamp is UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def local_cycle_date(now: datetime, tz_name: str) -> date:
    """The team-local calendar date that ``now`` falls on."""
    return now.astimezone(ZoneInfo(tz_name)).date()


def cutoff_utc(local_date: date, cutoff_local_time: str, tz_name: str) -> datetime:
    """The cutoff instant for one local date, as an aware UTC datetime.

    ``cutoff_local_time`` is ``"HH:MM"`` in the team's zone. ZoneInfo resolves
    DST, so an 11:00 cutoff stays 11:00 local across a clock change.
    """
    hours, minutes = (int(part) for part in cutoff_local_time.split(":"))
    local = datetime.combine(local_date, time(hours, minutes), tzinfo=ZoneInfo(tz_name))
    return local.astimezone(UTC)
