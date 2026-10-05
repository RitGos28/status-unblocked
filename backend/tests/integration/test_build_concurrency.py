"""One day, one digest per distinct set of inputs, and "latest" means last built.

Found by the round-2 reviews (B, F), reproduced before this change:
- six simultaneous Build clicks made six identical digests;
- after a scheduler pass on a demo clock (11:06), a hand rebuild at 09:22
  real time was hidden: the list picked the latest by generated_at.
Runs on SQLite locally and on Postgres in CI.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from standup.db import session as db_session
from standup.db.models import Digest, StandupCycle
from standup.summarize.rules import RulesSummarizer
from standup.summarize.service import build_digest, latest_digest
from tests.helpers import login_as, submit

NOW = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)


def _build(cycle_id: str) -> str:
    session = db_session.get_session_factory()()
    try:
        digest = build_digest(
            session,
            cycle_id=cycle_id,
            summarizer=RulesSummarizer(),
            base_url="http://testserver",
            now=NOW,
        )
        session.commit()
        return digest.id
    except Exception as exc:  # noqa: BLE001 - the test reports what failed
        session.rollback()
        return type(exc).__name__
    finally:
        session.close()


def test_simultaneous_builds_of_one_day_make_one_digest(client, session, clock, team_with_members):
    _team, (ada, *_rest) = team_with_members
    clock.current = NOW
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    cycle_id = session.execute(select(StandupCycle.id)).scalar_one()
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(_build, [cycle_id] * 6))
    assert len(set(results)) == 1, results
    session.expire_all()
    assert session.scalar(select(func.count(Digest.id))) == 1


def test_a_rebuild_with_nothing_new_returns_the_same_digest(
    client, session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    clock.current = NOW
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    cycle_id = session.execute(select(StandupCycle.id)).scalar_one()
    login_as(client, ada.id)
    first = client.post(f"/digests/build/{cycle_id}", follow_redirects=False).headers["location"]
    again = client.post(f"/digests/build/{cycle_id}", follow_redirects=False).headers["location"]
    assert first == again
    submit(client, ada.id, blockers="Now blocked on review.")
    login_as(client, ada.id)
    changed = client.post(f"/digests/build/{cycle_id}", follow_redirects=False).headers["location"]
    assert changed != first


def test_the_last_build_is_the_one_listed_whatever_its_clock_says(
    client, session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    clock.current = NOW + timedelta(hours=2)  # the scheduler on a demo clock
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    cycle_id = session.execute(select(StandupCycle.id)).scalar_one()
    login_as(client, ada.id)
    client.post(f"/digests/build/{cycle_id}", follow_redirects=False)
    clock.current = NOW  # back to real time, earlier than that build
    submit(client, ada.id, blockers="Now blocked on review.")
    login_as(client, ada.id)
    rebuilt = client.post(f"/digests/build/{cycle_id}", follow_redirects=False).headers["location"]
    assert rebuilt in client.get("/digests").text
    session.expire_all()
    assert f"/digest/{latest_digest(session, cycle_id).id}" == rebuilt
