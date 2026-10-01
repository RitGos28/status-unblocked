"""One definition of a "live" update: not superseded, and not purged.

Found by the duplication review: four places filtered superseded updates but
only the digest builder also excluded purged ones, so a cycle whose updates had
all been purged by retention still looked like it had updates. The scheduler
would build an empty digest for it, and /digests would show a non-zero count.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from standup.db.models import Update
from standup.scheduling.jobs import load_cycle_views
from tests.helpers import login_as, submit

NOW = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)


def purge_all(session) -> None:
    for update in session.execute(select(Update)).scalars():
        update.purged_at = NOW
        update.raw_text = None
    session.commit()


def test_a_purged_only_cycle_has_no_updates_for_the_scheduler(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    purge_all(session)

    (view,) = load_cycle_views(session, NOW + timedelta(hours=3))
    assert view.has_updates is False


def test_a_purged_only_cycle_shows_zero_updates_on_the_list(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    purge_all(session)

    login_as(client, ada.id)
    page = client.get("/digests").text
    assert "<td>0</td>" in page


def test_is_live_is_the_single_definition(session, team_with_members, client):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, progress="one")
    submit(client, ada.id, progress="two")
    session.expire_all()
    live = session.execute(select(Update).where(Update.is_live())).scalars().all()
    assert [u.raw_text.split("\n")[1] for u in live] == ["two"]
