"""A blocker reported again on a later day is "Still blocked", citing both days."""

from datetime import UTC, datetime

from sqlalchemy import select

from standup.db.models import Digest, StandupCycle
from tests.helpers import login_as, submit

BLOCKER = "Waiting on staging credentials from infra."


def build(client, session, day: int) -> Digest:
    cycle = session.execute(
        select(StandupCycle).order_by(StandupCycle.local_date.desc())
    ).scalars().first()
    assert client.post(f"/digests/build/{cycle.id}", follow_redirects=False).status_code == 303
    session.expire_all()
    return session.execute(
        select(Digest).where(Digest.cycle_id == cycle.id)
    ).scalars().first()


def test_the_second_day_shows_the_blocker_as_still_blocked(
    client, session, clock, team_with_members
):
    _team, (ada, bruno, _chen) = team_with_members
    clock.current = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
    submit(client, ada.id, blockers=BLOCKER)
    submit(client, bruno.id, blockers="Blocked on the flaky test.")
    first = build(client, session, 14)
    assert {c.kind for c in first.claims} == {"blocker"}

    clock.current = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
    submit(client, ada.id, blockers=BLOCKER)
    submit(client, bruno.id, blockers="Waiting on the design review.")  # a new blocker
    second = build(client, session, 15)

    by_member = {c.member_name: c for c in second.claims}
    carried = by_member["Ada Okafor"]
    assert carried.kind == "carryover"
    assert carried.text == BLOCKER
    assert len(carried.citations_json) == 2
    assert by_member["Bruno Silva"].kind == "blocker"

    # Both citations resolve to evidence pages, and the page explains why.
    login_as(client, ada.id)
    for citation in carried.citations_json:
        assert client.get(f"/evidence/{citation['source_id']}").status_code == 200
    page = client.get(f"/digest/{second.id}").text
    assert "Still blocked" in page
    assert "Also reported on 2026-09-14, and still open." in page
    assert "## Still blocked" in second.body_md
