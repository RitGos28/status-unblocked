"""The daily digest builds itself.

run_tick() against a real database and a FakeClock: nothing before the cutoff,
one digest at it, a quiet rebuild after a late update, notices to members with
a Teams conversation, and a failing notice that does not stop the rest.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from standup.db.models import AuditLog, Digest, Member, StandupCycle, Team, TrackerOutbox
from standup.domain.enums import AuditAction
from standup.scheduling.jobs import run_tick
from standup.summarize.rules import RulesSummarizer
from standup.tracker.noop import NoopTracker
from tests.helpers import submit

# The team fixture's default zone is UTC and its cutoff 11:00 local.
BEFORE_CUTOFF = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)
AFTER_CUTOFF = datetime(2026, 9, 15, 11, 5, tzinfo=UTC)


class RecordingNotifier:
    def __init__(self, fail_for: str | None = None):
        self.sent: list[tuple[str, str]] = []
        self.fail_for = fail_for

    async def notify(self, conversation_ref, text):
        if conversation_ref.get("user", {}).get("id") == self.fail_for:
            raise RuntimeError("unreachable")
        self.sent.append((conversation_ref["user"]["id"], text))


def ref(user_id: str) -> dict:
    return {
        "user": {"id": user_id},
        "conversation": {"id": f"a:{user_id}"},
        "serviceUrl": "https://smba.example/",
        "channelId": "msteams",
    }


def tick(session, now, notifier=None):
    return asyncio.run(
        run_tick(
            session,
            now=now,
            summarizer=RulesSummarizer(),
            tracker=NoopTracker(),
            base_url="https://standup.example",
            notifier=notifier,
        )
    )


def digests(session) -> list[Digest]:
    session.expire_all()
    return session.execute(select(Digest).order_by(Digest.generated_at)).scalars().all()


def test_nothing_happens_before_the_cutoff(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    report = tick(session, BEFORE_CUTOFF)
    assert report.built == []
    assert digests(session) == []


def test_the_digest_builds_once_at_the_cutoff(client, session, team_with_members):
    _team, (ada, bruno, _chen) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    submit(client, bruno.id, progress="Reviewed #214.")

    first = tick(session, AFTER_CUTOFF)
    again = tick(session, AFTER_CUTOFF + timedelta(minutes=1))

    assert len(first.built) == 1 and again.built == []
    (digest,) = digests(session)
    assert digest.generated_at.replace(tzinfo=UTC) == AFTER_CUTOFF
    # Built by the scheduler, audited as such, and its blocker queued for the tracker.
    built = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.DIGEST_BUILT.value)
    ).scalar_one()
    assert built.actor_id == "scheduler"
    assert session.execute(select(TrackerOutbox.status)).scalar_one() == "skipped"


def test_a_late_update_is_folded_in_without_a_second_notice(
    client, session, clock, team_with_members
):
    _team, (ada, bruno, _chen) = team_with_members
    session.get(Member, ada.id).teams_conversation_ref = ref("ada")
    session.commit()
    notifier = RecordingNotifier()

    submit(client, ada.id, progress="Shipped the retry logic.")
    tick(session, AFTER_CUTOFF, notifier)

    clock.current = AFTER_CUTOFF + timedelta(minutes=10)
    submit(client, bruno.id, blockers="Blocked on the deploy pipeline.")
    tick(session, AFTER_CUTOFF + timedelta(minutes=15), notifier)

    first, rebuilt = digests(session)
    assert "Blocked on the deploy pipeline." in rebuilt.body_md
    assert "Blocked on the deploy pipeline." not in first.body_md
    assert len(notifier.sent) == 1


def test_members_with_a_teams_conversation_get_a_link_not_content(
    client, session, team_with_members
):
    _team, (ada, bruno, chen) = team_with_members
    session.get(Member, ada.id).teams_conversation_ref = ref("ada")
    session.get(Member, bruno.id).teams_conversation_ref = ref("bruno")
    session.commit()
    notifier = RecordingNotifier(fail_for="ada")

    submit(client, chen.id, blockers="Waiting on staging credentials.")
    report = tick(session, AFTER_CUTOFF, notifier)

    # Ritwik's notice failed; Madhav's still went out. Shresth has no Teams conversation.
    assert (report.notified, report.notify_failures) == (1, 1)
    ((user, text),) = notifier.sent
    assert user == "bruno"
    assert "1 blocker" in text and "https://standup.example/digest/" in text
    assert "staging credentials" not in text


def test_cycles_follow_their_own_team_cutoff(client, session, team_with_members):
    team, (ada, *_rest) = team_with_members
    team = session.get(Team, team.id)
    team.cutoff_local_time = "15:00"
    session.commit()
    submit(client, ada.id, progress="Shipped it.")
    cycle = session.execute(select(StandupCycle)).scalar_one()
    assert cycle.cutoff_at_utc.replace(tzinfo=UTC) == datetime(2026, 9, 15, 15, 0, tzinfo=UTC)
    assert tick(session, AFTER_CUTOFF).built == []


def test_run_once_uses_the_app_settings_clock_and_database(
    client, session, clock, monkeypatch, team_with_members
):
    from standup.config import get_settings
    from standup.scheduling.jobs import run_once

    monkeypatch.setenv("STANDUP_BASE_URL", "https://standup.example")
    get_settings.cache_clear()
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")

    clock.current = AFTER_CUTOFF
    report = asyncio.run(run_once())

    assert len(report.built) == 1
    (digest,) = digests(session)
    assert "https://standup.example/evidence/" in digest.body_md
