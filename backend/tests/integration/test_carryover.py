"""A blocker reported again on a later day is "Still blocked", citing both days."""

from datetime import UTC, datetime

from tests.helpers import build_latest as build
from tests.helpers import login_as, submit

BLOCKER = "Waiting on staging credentials from infra."


def test_the_second_day_shows_the_blocker_as_still_blocked(
    client, session, clock, team_with_members
):
    _team, (ada, bruno, _chen) = team_with_members
    clock.current = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
    submit(client, ada.id, blockers=BLOCKER)
    submit(client, bruno.id, blockers="Blocked on the flaky test.")
    first = build(client, session)
    assert {c.kind for c in first.claims} == {"blocker"}

    clock.current = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
    submit(client, ada.id, blockers=BLOCKER)
    submit(client, bruno.id, blockers="Waiting on the design review.")  # a new blocker
    second = build(client, session)

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


def test_still_blocked_names_the_teams_own_day_not_the_utc_date(
    client, session, clock, team_with_members
):
    """Found by the round-2 review (B): a team at UTC+14 saw 'Also reported on
    <the UTC date>', one day earlier than the standup day it was filed under."""
    from standup.db.models import Team

    team, (ada, *_rest) = team_with_members
    session.get(Team, team.id).tz_default = "Pacific/Kiritimati"  # UTC+14
    session.commit()
    login_as(client, ada.id)
    # 12:00 UTC is 02:00 the next local day there.
    clock.current = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)  # local 2026-09-15
    submit(client, ada.id, blockers=BLOCKER)
    build(client, session)
    clock.current = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)  # local 2026-09-16
    submit(client, ada.id, blockers=BLOCKER)
    digest = build(client, session)
    page = client.get(f"/digest/{digest.id}").text
    assert "Also reported on 2026-09-15" in page, page[page.find("Also reported") :][:80]
