"""Submissions stay consistent when they arrive at the same moment.

Two bugs found by a robustness review, both reproduced before this change:
- Several people submitting the first update of the day raced to create the
  day's cycle; all but one got an IntegrityError (a 500).
- A double-click (concurrent resubmits by one member) left several "live"
  updates, and every later submit from that member failed with
  MultipleResultsFound, locking them out for the day.
Runs on SQLite locally and on Postgres in CI.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import func, select

from standup.db import session as db_session
from standup.db.models import Member, StandupCycle, Update
from standup.domain.enums import ItemKind, SourceKind
from standup.ingestion.base import RawSubmission
from standup.ingestion.service import ingest

NOW = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)


def _submit(member_id: str, text: str) -> str:
    session = db_session.get_session_factory()()
    try:
        member = session.get(Member, member_id)
        submission = RawSubmission(
            source_kind=SourceKind.WEBFORM,
            external_user_key=member_id,
            text_fields={ItemKind.PROGRESS: text},
            captured_at=NOW,
            source_ids={},
            raw_payload={},
        )
        ingest(session, submission, member, NOW)
        session.commit()
        return "ok"
    except Exception as exc:  # noqa: BLE001 - the test reports what failed
        session.rollback()
        return type(exc).__name__
    finally:
        session.close()


def _live(session, member_id: str) -> int:
    session.expire_all()
    return session.scalar(
        select(func.count(Update.id))
        .where(Update.member_id == member_id)
        .where(Update.superseded_by.is_(None))
    )


def test_concurrent_first_submissions_of_the_day_all_succeed(session, team_with_members):
    _team, members = team_with_members
    # Several submissions per member, so the cycle race is hit hard.
    jobs = [m.id for m in members] * 3
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(lambda mid: _submit(mid, f"first from {mid}"), jobs))

    assert results == ["ok"] * len(jobs)
    assert session.scalar(select(func.count(StandupCycle.id))) == 1
    assert all(_live(session, m.id) == 1 for m in members)


def test_a_double_click_leaves_one_live_update_and_never_locks_out(session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    assert _submit(ada.id, "before the double click") == "ok"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: _submit(ada.id, f"click {i}"), range(8)))

    assert results == ["ok"] * 8
    assert _live(session, ada.id) == 1
    assert _submit(ada.id, "after") == "ok"
    assert _live(session, ada.id) == 1


def test_data_already_broken_by_the_old_bug_recovers_on_the_next_submit(
    session, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    assert _submit(ada.id, "one") == "ok"
    assert _submit(ada.id, "two") == "ok"
    # Recreate the old bug's damage: two live updates for one member.
    session.expire_all()
    for update in session.execute(select(Update).where(Update.member_id == ada.id)).scalars():
        update.superseded_by = None
    session.commit()
    assert _live(session, ada.id) == 2

    assert _submit(ada.id, "three") == "ok"
    assert _live(session, ada.id) == 1
