"""What the scheduler should do right now. Pure: no I/O, no project imports.

Given the time and a snapshot of recent cycles, return the jobs that are due.
Pure function plus injected clock means "simulate three days" is a loop in a
test, with nothing to mock and nothing that sleeps.

The rules:
- once a cycle's cutoff has passed and it has updates, build its digest;
- if updates arrived after the latest digest (a late submission), rebuild it;
- notify the team only on a cycle's first build, never on rebuilds;
- drain the tracker outbox every tick, so retries run without a build.
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


@dataclass(frozen=True)
class BuildDigest:
    cycle_id: str
    notify: bool


@dataclass(frozen=True)
class DrainOutbox:
    pass


Job = BuildDigest | DrainOutbox


def tick(now: datetime, cycles: list[CycleView]) -> list[Job]:
    jobs: list[Job] = []
    for cycle in cycles:
        if cycle.cutoff_at is None or now < cycle.cutoff_at or not cycle.has_updates:
            continue
        if cycle.last_digest_at is None:
            jobs.append(BuildDigest(cycle.cycle_id, notify=True))
        elif cycle.last_update_at is not None and cycle.last_update_at > cycle.last_digest_at:
            jobs.append(BuildDigest(cycle.cycle_id, notify=False))
    jobs.append(DrainOutbox())
    return jobs
