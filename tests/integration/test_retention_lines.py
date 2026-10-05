"""Retention removes every line no digest quoted, and a purged day is final.

Found by the round-2 reviews (B, E): retention nulled only the full submission,
so every line outlived the window and stayed visible in /me/data and the
export; and Rebuild after a purge replaced the day's digest with an empty one.
"""

import json
from datetime import timedelta

from sqlalchemy import select

from standup.db.models import Digest, StandupCycle, UpdateItem
from standup.privacy.audit import verify_chain, verify_evidence
from standup.privacy.retention import purge_expired
from tests.helpers import login_as, submit
from tests.integration.test_me_data_and_retention import NOW

LATER = NOW + timedelta(days=40)


def _setup(client, session, clock, ada):
    clock.current = NOW
    # Quoted in the digest: the blocker and the progress line. The first
    # submission is replaced before the build, so its lines are never quoted.
    submit(client, ada.id, blockers="Waiting on DBA.")
    submit(client, ada.id, progress="Shipped search.", blockers="Waiting on staging creds.")
    cycle = session.execute(select(StandupCycle)).scalar_one()
    login_as(client, ada.id)
    assert client.post(f"/digests/build/{cycle.id}", follow_redirects=False).status_code == 303
    assert purge_expired(session, LATER) == 2
    session.commit()
    session.expire_all()
    return cycle


def test_lines_no_digest_quoted_are_removed_and_quoted_ones_stay(
    client, session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    _setup(client, session, clock, ada)
    texts = sorted(t for (t,) in session.execute(select(UpdateItem.text)) if t is not None)
    assert texts == ["Shipped search.", "Waiting on staging creds."]
    assert "Waiting on DBA." not in client.get("/me/data").text
    assert "Waiting on DBA." not in client.get("/me/export").text
    assert verify_chain(session) == (True, None)
    assert verify_evidence(session) == []


def test_evidence_of_a_removed_line_says_so_and_claims_nothing(
    client, session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    _setup(client, session, clock, ada)
    removed = session.execute(select(UpdateItem).where(UpdateItem.text.is_(None))).scalars().first()
    page = client.get(f"/evidence/{removed.id}").text
    assert "removed" in page and "what the digest cited" not in page


def test_export_marks_removed_lines(client, session, clock, team_with_members):
    _team, (ada, *_rest) = team_with_members
    _setup(client, session, clock, ada)
    data = json.loads(client.get("/me/export").text)
    lines = [line for u in data["updates"] for line in u["lines"]]
    removed = [line for line in lines if line["removed_by_retention"]]
    assert len(removed) == 1 and removed[0]["text"] is None
    assert all(line["text"] for line in lines if not line["removed_by_retention"])


def test_a_purged_day_cannot_be_rebuilt_and_its_digest_stays(
    client, session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    cycle = _setup(client, session, clock, ada)
    clock.current = LATER
    listing = client.get("/digests").text
    assert "Rebuild" not in listing
    response = client.post(f"/digests/build/{cycle.id}", follow_redirects=False)
    assert response.status_code == 409
    digests = session.execute(select(Digest)).scalars().all()
    assert len(digests) == 1 and "Waiting on staging creds." in (digests[0].body_md or "")
