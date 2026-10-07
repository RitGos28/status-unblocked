"""What people read on screen is plain language, not internals.

Each case was found by the Tier 1 browser pass, a person-style click-through of
docs/DEMO.md in Chrome.
"""

import re

import pytest
from sqlalchemy import select

from standup.db.models import Member, StandupCycle, Team, UpdateItem
from tests.helpers import login_as, submit

HTML = {"accept": "text/html"}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def other_member(session) -> Member:
    team = Team(slug="mobile", name="Mobile")
    session.add(team)
    session.flush()
    member = Member(team_id=team.id, display_name="Vikram Malhotra", tz="UTC")
    session.add(member)
    session.commit()
    return member


def test_the_sign_in_page_does_not_tell_people_to_run_commands(client, team_with_members):
    page = client.get("/digests", headers=HTML).text
    assert "python" not in page
    assert "team code" in page


def test_the_submit_form_placeholders_are_not_the_demo_answers(client, team_with_members):
    login_as(client, team_with_members[1][0].id)
    page = client.get("/submit").text
    for seeded in ("staging credentials", "retry logic", "the migration"):
        assert seeded not in page


def test_the_evidence_page_explains_a_missing_permalink_in_words(
    client, session, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    item = session.execute(select(UpdateItem)).scalar_one()
    page = client.get(f"/evidence/{item.id}").text
    assert "webform:" not in page
    assert "web form" in page
    assert 'href="/digests"' in page


def test_not_found_pages_show_no_raw_ids_and_keep_the_signed_in_header(
    client, session, team_with_members, other_member
):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    cycle = session.execute(select(StandupCycle)).scalar_one()
    client.post(f"/digests/build/{cycle.id}", follow_redirects=False)
    digest_url = client.get("/digests").text.split('href="/digest/')[1].split('"')[0]

    login_as(client, other_member.id)
    page = client.get(f"/digest/{digest_url}", headers=HTML)
    assert page.status_code == 404
    assert not UUID.search(page.text.split("<header>")[0] + page.text.split("</header>")[-1])
    assert "Vikram Malhotra" in page.text  # the signed-in header is still there
    api = client.get(f"/digest/{digest_url}")
    assert not UUID.search(api.json()["detail"])


def test_signing_out_says_so(client, team_with_members):
    login_as(client, team_with_members[1][0].id)
    response = client.post("/logout")
    assert "signed out" in response.text.lower()
