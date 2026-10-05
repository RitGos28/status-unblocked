"""Pure domain types. No I/O, no ORM, no project imports beyond sibling enums."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Time is injected, never read from the wall clock inside logic.

    Keeps the scheduler and every time-dependent test deterministic — see the
    testing conventions in CLAUDE.md.
    """

    def now(self) -> datetime: ...


class SystemClock:
    """The real clock. Injected in production via ``deps.get_clock``."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass
class FakeClock:
    """Test clock. Advance it explicitly; never sleeps."""

    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)
