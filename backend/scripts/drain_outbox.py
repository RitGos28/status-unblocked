"""Deliver queued blocker writes to the task tracker now.

Run: python -m scripts.drain_outbox
A build drains automatically in the background; this retries rows that were
rate-limited or failed transiently, once their backoff has passed.
"""

from standup.config import get_settings
from standup.db.session import session_scope
from standup.deps import tracker_from_settings
from standup.domain.models import SystemClock
from standup.tracker.outbox import drain


def main() -> None:
    with session_scope() as session:
        report = drain(session, tracker_from_settings(get_settings()), SystemClock().now())
    print(
        f"done {report.done}, skipped {report.skipped}, "
        f"retrying {report.retrying}, failed {report.failed}"
    )


if __name__ == "__main__":
    main()
