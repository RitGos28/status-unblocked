"""The scheduler is safe to run from several places at once.

Found by the robustness and duplication reviews, each reproduced first:
- With an empty STANDUP_BASE_URL a tick wrote relative links into GitHub
  issue bodies and Teams notices.
- Two runners (several workers, or cron plus the in-app loop) each built the
  digest and each sent the Teams notice.
- A manual build before the cutoff meant the scheduled notice never went out.
- The tick's synchronous database work ran on the event loop's thread.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from standup.db import session as db_session
from standup.db.models import Digest, Member, StandupCycle
from standup.scheduling.jobs import run_tick
from standup.summarize.rules import RulesSummarizer
from standup.tracker.noop import NoopTracker
from tests.helpers import login_as, submit

BEFORE_CUTOFF = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)
AFTER_CUTOFF = datetime(2026, 9, 15, 11, 5, tzinfo=UTC)
BASE = "https://standup.example"


class RecordingNotifier:
    def __init__(self):
        self.sent: list[str] = []
        self._lock = threading.Lock()

    async def notify(self, conversation_ref, text):
        with self._lock:
            self.sent.append(text)


def _tick(session, now, notifier=None, base_url=BASE, summarizer=None):
    return asyncio.run(
        run_tick(
            session,
            now=now,
            summarizer=summarizer or RulesSummarizer(),
            tracker=NoopTracker(),
            base_url=base_url,
            notifier=notifier,
        )
    )


def _with_teams_user(session, member_id: str) -> None:
    session.get(Member, member_id).teams_conversation_ref = {"user": {"id": member_id}}
    session.commit()


def test_a_tick_without_a_base_url_refuses_and_writes_nothing(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    with pytest.raises(Exception, match="STANDUP_BASE_URL"):
        _tick(session, AFTER_CUTOFF, base_url="")
    session.rollback()
    assert session.execute(select(Digest)).first() is None


def test_two_runners_at_once_build_once_and_notify_once(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    _with_teams_user(session, ada.id)
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    notifier = RecordingNotifier()

    def runner(_):
        own = db_session.get_session_factory()()
        try:
            _tick(own, AFTER_CUTOFF, notifier)
            own.commit()
            return "ok"
        except Exception as exc:  # noqa: BLE001
            own.rollback()
            return type(exc).__name__
        finally:
            own.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(runner, range(2)))

    assert results == ["ok", "ok"]
    session.expire_all()
    assert len(session.execute(select(Digest)).scalars().all()) == 1
    assert len(notifier.sent) == 1


def test_a_manual_build_before_the_cutoff_still_gets_the_scheduled_notice(
    client, session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    _with_teams_user(session, ada.id)
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    login_as(client, ada.id)
    cycle_id = session.execute(select(StandupCycle.id)).scalar_one()
    clock.current = BEFORE_CUTOFF
    assert client.post(f"/digests/build/{cycle_id}", follow_redirects=False).status_code == 303

    notifier = RecordingNotifier()
    _tick(session, AFTER_CUTOFF, notifier)
    _tick(session, AFTER_CUTOFF, notifier)

    assert len(notifier.sent) == 1


def test_the_ticks_database_work_runs_off_the_event_loop_thread(
    client, session, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    threads: dict[str, int] = {}

    class RecordingSummarizer(RulesSummarizer):
        def summarize(self, req):
            threads["summarize"] = threading.get_ident()
            return super().summarize(req)

    async def run():
        threads["loop"] = threading.get_ident()
        await run_tick(
            session, now=AFTER_CUTOFF, summarizer=RecordingSummarizer(),
            tracker=NoopTracker(), base_url=BASE,
        )

    asyncio.run(run())
    assert threads["summarize"] != threads["loop"]
