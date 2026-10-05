"""The audit chain stays a single chain when many requests append at once.

Found by a robustness review: appending read the last row, then inserted, with
nothing stopping two requests reading the same last row. 40 parallel evidence
views forked the chain, and verify_integrity then reported tampering that never
happened. Runs on SQLite locally and on Postgres in CI.
"""

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from standup.db import session as db_session
from standup.db.models import AuditLog
from standup.domain.enums import AuditAction
from standup.privacy.audit import record_audit, verify_chain

WRITERS = 40


def _append(i: int) -> str:
    session = db_session.get_session_factory()()
    try:
        record_audit(
            session,
            actor_kind="member",
            actor_id=f"member-{i}",
            action=AuditAction.EVIDENCE_VIEWED,
            purpose="concurrency test",
        )
        session.commit()
        return "ok"
    except Exception as exc:  # noqa: BLE001 - the test reports what failed
        session.rollback()
        return type(exc).__name__
    finally:
        session.close()


def test_concurrent_appends_form_one_unbroken_chain(session, app_env):
    with ThreadPoolExecutor(max_workers=WRITERS) as pool:
        results = list(pool.map(_append, range(WRITERS)))

    assert results == ["ok"] * WRITERS
    assert session.scalar(select(func.count(AuditLog.seq))) == WRITERS
    forks = session.execute(
        select(AuditLog.prev_hash).group_by(AuditLog.prev_hash).having(func.count() > 1)
    ).all()
    assert forks == []
    assert verify_chain(session) == (True, None)
