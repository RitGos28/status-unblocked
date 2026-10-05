"""Words a viewer reads about a digest are accurate.

Found by the Tier 2 browser pass:
- the Teams notice said "Today's ... digest" for yesterday's digest, and its
  blocker count left out carried-over blockers ("1 blocker" beside a page
  showing two);
- a carried-over line had two identical "source" buttons;
- the digest list said "digested", evidence said "via webform", the digest
  subtitle showed "rules 0.1.0", and the 404 page linked to the start page.
"""

import re
from datetime import UTC, datetime

from sqlalchemy import select

from standup.db.models import UpdateItem
from standup.scheduling.jobs import _notice
from tests.helpers import build_latest, login_as, submit

BLOCKER = "Waiting on staging credentials from infra."


def two_days(client, session, clock, team_with_members):
    _team, (ada, bruno, _chen) = team_with_members
    clock.current = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
    submit(client, ada.id, blockers=BLOCKER)
    first = build_latest(client, session)
    clock.current = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
    submit(client, ada.id, blockers=BLOCKER)
    submit(client, bruno.id, blockers="Waiting on the design review.")
    second = build_latest(client, session)
    return first, second


def test_the_notice_names_its_digests_date_and_counts_every_blocker(
    client, session, clock, team_with_members
):
    first, second = two_days(client, session, clock, team_with_members)
    old_text, _ = _notice(session, first.cycle_id, "https://standup.example")
    new_text, _ = _notice(session, second.cycle_id, "https://standup.example")

    assert "Today's" not in old_text and "Today's" not in new_text
    assert "for 2026-09-14" in old_text and "for 2026-09-15" in new_text
    assert "2 blockers" in new_text and "1 still open from an earlier day" in new_text
    assert re.search(r"\b1 blocker\b(?!s)", old_text)


def test_a_carried_over_line_labels_its_earlier_source(client, session, clock, team_with_members):
    _first, second = two_days(client, session, clock, team_with_members)
    login_as(client, team_with_members[1][0].id)
    page = client.get(f"/digest/{second.id}").text
    assert ">earlier report<" in page
    assert "earlier report" in second.body_md


def test_digest_list_evidence_and_subtitle_use_plain_words(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers=BLOCKER)
    digest = build_latest(client, session)
    login_as(client, ada.id)

    listing = client.get("/digests").text
    assert "digested" not in listing and "Digest built" in listing
    page = client.get(f"/digest/{digest.id}").text
    assert "rules 0.1.0" not in page and "2026-09-15" in page
    item = session.execute(select(UpdateItem)).scalar_one()
    assert "via the web form" in client.get(f"/evidence/{item.id}").text


def test_the_not_found_page_leads_a_signed_in_reader_back_to_digests(client, team_with_members):
    login_as(client, team_with_members[1][0].id)
    page = client.get("/digest/nope", headers={"accept": "text/html"}).text
    assert 'href="/digests"' in page.split("</header>")[-1]
