"""Concurrent outbox drains never create the same GitHub issue twice.

Found by the robustness review and reproduced first: a background drain after
a build and a scheduler drain could pick up the same row; both created the
issue, and the second crashed inserting its link. Two queued rows for the same
blocker (two different days) had the same problem even with per-row claims, so
draining is single-runner: a drain must hold the "outbox-drain" lease.
"""

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from standup.db import session as db_session
from standup.db.models import Digest, StandupCycle, Team, TrackerLink, TrackerOutbox
from standup.tracker.base import IssueRef
from standup.tracker.outbox import drain
from tests.helpers import submit

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


class RacingTracker:
    """Lets both drains reach the 'no issue yet' check before either creates one."""

    name = "github"

    def __init__(self):
        self.created: list[str] = []
        self.commented: list[int] = []
        self._both_checked = threading.Barrier(2, timeout=1.0)
        self._lock = threading.Lock()

    def find_issue_by_marker(self, repo, marker):
        # Times out when only one drain gets here, which is the fix working.
        with contextlib.suppress(threading.BrokenBarrierError):
            self._both_checked.wait()
        return None

    def create_issue(self, repo, *, title, body, labels):
        with self._lock:
            self.created.append(title)
            return IssueRef(number=len(self.created), url=f"https://gh/{len(self.created)}")

    def add_comment(self, repo, number, body):
        with self._lock:
            self.commented.append(number)


def _drain(tracker) -> str:
    session = db_session.get_session_factory()()
    try:
        drain(session, tracker, NOW)
        return "ok"
    except Exception as exc:  # noqa: BLE001 - the test reports what failed
        session.rollback()
        return type(exc).__name__
    finally:
        session.close()


def _queue_blocker(client, session, member, days_ago: int) -> None:
    """Queue one outbox row for the same blocker on a given day."""
    from standup.deps import get_clock
    from standup.summarize.rules import RulesSummarizer
    from standup.summarize.service import build_digest

    get_clock().current = NOW - timedelta(days=days_ago, hours=3)
    submit(client, member.id, blockers="Waiting on staging credentials from infra.")
    session.expire_all()
    cycle = session.execute(
        select(StandupCycle).order_by(StandupCycle.local_date.desc())
    ).scalars().first()
    build_digest(
        session, cycle_id=cycle.id, summarizer=RulesSummarizer(),
        base_url="https://standup.example", now=get_clock().now(),
    )
    session.commit()


def _github_team(session, team_id: str) -> None:
    team = session.get(Team, team_id)
    team.github_repo = "acme/platform"
    session.commit()


def test_two_drains_on_one_row_create_one_issue(client, session, team_with_members):
    team, (ada, *_rest) = team_with_members
    _github_team(session, team.id)
    _queue_blocker(client, session, ada, days_ago=0)
    tracker = RacingTracker()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _drain(tracker), range(2)))

    assert results == ["ok", "ok"]
    assert len(tracker.created) == 1
    session.expire_all()
    assert len(session.execute(select(TrackerLink)).scalars().all()) == 1
    assert session.execute(select(TrackerOutbox.status)).scalar_one() == "done"


def test_two_drains_on_two_days_of_the_same_blocker_create_one_issue(
    client, session, team_with_members
):
    team, (ada, *_rest) = team_with_members
    _github_team(session, team.id)
    _queue_blocker(client, session, ada, days_ago=1)
    _queue_blocker(client, session, ada, days_ago=0)
    assert len(session.execute(select(Digest)).scalars().all()) == 2
    tracker = RacingTracker()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _drain(tracker), range(2)))
    # Whatever the first pass left, a later pass finishes without duplicating.
    _drain(tracker)

    assert "IntegrityError" not in results
    assert len(tracker.created) == 1
    assert tracker.commented == [1]
    session.expire_all()
    statuses = session.execute(select(TrackerOutbox.status)).scalars().all()
    assert statuses == ["done", "done"]
