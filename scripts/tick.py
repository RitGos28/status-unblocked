"""Run one scheduler pass: build due digests, notify, drain the tracker outbox.

Run: python -m scripts.tick [--at 2026-10-01T11:05:00Z]
For cron, or instead of STANDUP_SCHEDULER=true. Needs STANDUP_BASE_URL so the
digest links it sends are absolute.

--at runs the pass as if it were that moment, so the daily build can be shown
at any hour (the demo uses it; production cron never should).
"""

import argparse
import asyncio
from datetime import UTC, datetime

from standup.config import get_settings
from standup.deps import set_clock
from standup.domain.models import FakeClock
from standup.scheduling.jobs import DigestNotifier, run_once


def _parse_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--at", type=_parse_at, help="run as if it were this ISO-8601 time")
    args = parser.parse_args()
    if args.at is not None:
        set_clock(FakeClock(current=args.at))

    settings = get_settings()
    notifier: DigestNotifier | None = None
    if settings.teams_enabled:
        from standup.api.teams_router import build_teams_notifier

        notifier = build_teams_notifier()
    report = asyncio.run(run_once(notifier))
    print(
        f"built {len(report.built)} digest(s), notified {report.notified}, "
        f"notify failures {report.notify_failures}, tracker writes {report.drained}, "
        f"purged {report.purged}"
    )


if __name__ == "__main__":
    main()
