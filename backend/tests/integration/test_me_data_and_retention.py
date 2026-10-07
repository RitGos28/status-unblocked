"""What a member can see about themselves, and how long their words are kept.

/me/data turns the audit log from something only operators could read into
something its subject reads: their updates, and who opened them. /me/export
gives the same as JSON. Retention removes stored submissions older than the
team's retention period, while digests stay readable and verifiable.
"""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from standup.db.models import AuditLog, Digest, StandupCycle, Team, Update, UpdateItem
from standup.domain.enums import AuditAction
from standup.privacy.audit import verify_chain, verify_evidence
from standup.privacy.retention import purge_expired
from tests.helpers import login_as, submit

NOW = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)


def test_my_data_shows_my_updates_and_who_opened_them(client, session, team_with_members):
    _team, (ada, bruno, _chen) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    submit(client, bruno.id, progress="Reviewed #214.")
    ada_item = session.execute(
        select(UpdateItem).join(Update).where(Update.member_id == ada.id)
    ).scalar_one()

    login_as(client, bruno.id)
    client.get(f"/evidence/{ada_item.id}")

    login_as(client, ada.id)
    page = client.get("/me/data").text
    assert "Waiting on staging credentials." in page
    assert "Reviewed #214." not in page  # only my own updates
    viewers = page.split("Who has opened your updates")[1]
    assert "Rohan Verma" in viewers


def test_my_export_is_json_and_is_itself_audited(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    login_as(client, ada.id)

    response = client.get("/me/export")
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers["content-disposition"]
    data = json.loads(response.text)
    assert data["member"]["display_name"] == "Aarav Sharma"
    assert "Waiting on staging credentials." in data["updates"][0]["raw_text"]
    assert any(e["action"] == "update.ingested" for e in data["audit"])
    session.expire_all()
    exported = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.DATA_EXPORTED.value)
    ).scalar_one()
    assert exported.actor_id == ada.id and exported.subject_member_id == ada.id


def test_retention_removes_old_submissions_and_digests_stay_readable(
    client, session, clock, team_with_members
):
    team, (ada, *_rest) = team_with_members
    clock.current = NOW
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    cycle = session.execute(select(StandupCycle)).scalar_one()
    client.post(f"/digests/build/{cycle.id}", follow_redirects=False)
    clock.current = NOW + timedelta(days=10)
    submit(client, ada.id, progress="A recent update.")

    session.get(Team, team.id).retention_days = 7
    session.commit()
    purged = purge_expired(session, NOW + timedelta(days=10, hours=1))
    session.commit()

    assert purged == 1
    session.expire_all()
    old, recent = session.execute(select(Update).order_by(Update.captured_at)).scalars().all()
    assert old.raw_text is None and old.raw_payload_json is None and old.purged_at is not None
    assert recent.raw_text is not None
    # The digest still renders, its evidence says it expired, and nothing
    # looks tampered with.
    login_as(client, ada.id)
    digest = session.execute(select(Digest)).scalar_one()
    assert "Waiting on staging credentials." in client.get(f"/digest/{digest.id}").text
    item = session.execute(select(UpdateItem).where(UpdateItem.update_id == old.id)).scalar_one()
    assert "expired" in client.get(f"/evidence/{item.id}").text
    assert verify_chain(session) == (True, None)
    assert verify_evidence(session) == []
    mine = client.get("/me/data").text  # renders a purged update's quoted lines
    assert "removed by retention" in mine and "Waiting on staging credentials." in mine
    deleted = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.DATA_DELETED.value)
    ).scalar_one()
    assert (deleted.actor_id, deleted.subject_member_id) == ("retention", ada.id)


def test_purging_twice_purges_nothing_more(client, session, clock, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    later = NOW + timedelta(days=40)
    assert purge_expired(session, later) == 1
    assert purge_expired(session, later) == 0
