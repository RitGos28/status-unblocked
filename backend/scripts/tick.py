"""Run one scheduler pass: build due digests, notify, drain the tracker outbox.

Run: python -m scripts.tick [--at 2026-10-01T11:05:00Z]
For cron, or instead of STANDUP_SCHEDULER=true. Needs STANDUP_BASE_URL so the
digest links it sends are absolute.

--at runs the pass as if it were that moment, so the daily build can be shown
at any hour (the demo uses it; production cron never should).
"""

import argparse
import asyncio
import sys
from datetime import datetime

from pydantic import ValidationError

from standup.config import get_settings
from standup.deps import set_clock
from standup.domain.errors import ConfigurationError
from standup.domain.models import FakeClock
from standup.domain.timezones import as_utc
from standup.scheduling.jobs import DigestNotifier, run_once


def _parse_at(value: str) -> datetime:
    return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--at", type=_parse_at, help="run as if it were this ISO-8601 time")
    args = parser.parse_args()
    if args.at is not None:
        set_clock(FakeClock(current=args.at))

    try:
        settings = get_settings()
    except ValidationError as exc:
        # One line per problem, not a traceback: this is a configuration error.
        for error in exc.errors():
            print(f"tick: {error['msg'].removeprefix('Value error, ')}", file=sys.stderr)
        raise SystemExit(2) from None
    notifier: DigestNotifier | None = None
    if settings.teams_enabled:
        from standup.api.teams_router import build_teams_notifier

        notifier = build_teams_notifier()
    try:
        report = asyncio.run(run_once(notifier))
    except ConfigurationError as exc:
        print(f"tick: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    print(
        f"built {len(report.built)} digest(s), notified {report.notified}, "
        f"notify failures {report.notify_failures}, tracker writes {report.drained}, "
        f"purged {report.purged}"
    )


if __name__ == "__main__":
    main()
