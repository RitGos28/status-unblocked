"""What the scheduler should do right now. Pure: no I/O, no project imports.

Given the time and a snapshot of recent cycles, return the jobs that are due.
Pure function plus injected clock means "simulate three days" is a loop in a
test, with nothing to mock and nothing that sleeps.

The rules, once a cycle's cutoff has passed and it has updates:
- build its digest if there is none, or rebuild it if updates arrived after
  the latest one (a late submission);
- notify the team exactly once per cycle, whenever it has not been notified
  yet: with the first scheduled build, or on its own when someone already
  built the digest by hand before the cutoff;
- and on every tick, drain the tracker outbox so retries run without a build.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CycleView:
    """What tick() needs to know about one cycle. All datetimes are aware UTC."""

    cycle_id: str
    cutoff_at: datetime | None
    has_updates: bool
    last_update_at: datetime | None
    last_digest_at: datetime | None
    notified: bool = False


@dataclass(frozen=True)
class BuildDigest:
    cycle_id: str
    notify: bool


@dataclass(frozen=True)
class NotifyDigest:
    """The digest is current but the team has not been told yet."""

    cycle_id: str


@dataclass(frozen=True)
class DrainOutbox:
    pass


Job = BuildDigest | NotifyDigest | DrainOutbox


def tick(now: datetime, cycles: list[CycleView]) -> list[Job]:
    jobs: list[Job] = []
    for cycle in cycles:
        if cycle.cutoff_at is None or now < cycle.cutoff_at or not cycle.has_updates:
            continue
        stale = cycle.last_digest_at is None or (
            cycle.last_update_at is not None and cycle.last_update_at > cycle.last_digest_at
        )
        if stale:
            jobs.append(BuildDigest(cycle.cycle_id, notify=not cycle.notified))
        elif not cycle.notified:
            jobs.append(NotifyDigest(cycle.cycle_id))
    jobs.append(DrainOutbox())
    return jobs
