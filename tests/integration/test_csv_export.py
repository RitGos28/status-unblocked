"""A digest downloads as a spreadsheet (the brief's "web form + spreadsheet").

Same team scoping as the page. User-written text is neutralised against
spreadsheet formula injection: a cell beginning with = + - @ or a tab/CR
would otherwise run as a formula when the file is opened.
"""

import csv
import io

import pytest

from standup.db.models import Member, Team
from tests.helpers import build_latest as build
from tests.helpers import login_as, submit

HEADER = [
    "section", "member", "text", "evidence_url", "earlier_report_url", "issue_url",
]


def rows(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.text)))


def test_a_digest_downloads_as_csv_with_one_row_per_line(client, session, team_with_members):
    _team, (ada, bruno, _chen) = team_with_members
    submit(client, ada.id, progress="Shipped the retry logic.", blockers="Waiting on infra.")
    submit(client, bruno.id, progress="Reviewed #214.")
    digest = build(client, session)

    response = client.get(f"/digest/{digest.id}.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="core-2026-09-15.csv"' in response.headers["content-disposition"]
    table = rows(response)
    assert table[0] == HEADER
    body = {(r[0], r[1], r[2]) for r in table[1:]}
    assert ("Blockers", "Bruno Silva", "Reviewed #214.") not in body
    assert ("Blockers", "Ada Okafor", "Waiting on infra.") in body
    assert ("Progress", "Bruno Silva", "Reviewed #214.") in body
    assert all(r[3].startswith("http://testserver/evidence/") for r in table[1:])
    assert client.head(f"/digest/{digest.id}.csv").status_code == 200


@pytest.mark.parametrize("payload", ['=HYPERLINK("http://evil.example","x")', "+1+2", "@SUM(A1)"])
def test_formulas_in_user_text_are_neutralised(client, session, team_with_members, payload):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, progress=payload)
    digest = build(client, session)
    (row,) = rows(client.get(f"/digest/{digest.id}.csv"))[1:]
    assert row[2] == "'" + payload


def test_another_team_cannot_download_it(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on infra.")
    digest = build(client, session)
    mobile = Team(slug="mobile", name="Mobile")
    session.add(mobile)
    session.flush()
    dana = Member(team_id=mobile.id, display_name="Dana Park", tz="UTC")
    session.add(dana)
    session.commit()
    login_as(client, dana.id)
    assert client.get(f"/digest/{digest.id}.csv").status_code == 404
