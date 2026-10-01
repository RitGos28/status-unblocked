"""Run one scheduler pass: build due digests, notify, drain the tracker outbox.

Run: python -m scripts.tick
For cron, or instead of STANDUP_SCHEDULER=true. Needs STANDUP_BASE_URL so the
digest links it sends are absolute.
"""

import asyncio

from standup.config import get_settings
from standup.scheduling.jobs import DigestNotifier, run_once


def main() -> None:
    settings = get_settings()
    notifier: DigestNotifier | None = None
    if settings.teams_enabled:
        from standup.api.teams_router import build_teams_notifier

        notifier = build_teams_notifier()
    report = asyncio.run(run_once(notifier))
    print(
        f"built {len(report.built)} digest(s), notified {report.notified}, "
        f"notify failures {report.notify_failures}, tracker writes {report.drained}"
    )


if __name__ == "__main__":
    main()
