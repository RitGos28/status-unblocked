"""Sign-in and team boundaries.

Each member sees exactly their own team's digests and evidence. Another
team's resources answer 404 rather than 403, so their existence is not
disclosed. Nobody can file an update as someone else.
"""

import pytest
from sqlalchemy import select

from standup.auth.team_code import format_team_code
from standup.db.models import AuditLog, Member, Team, Update, UpdateItem
from standup.domain.enums import AuditAction
from tests.helpers import build_latest as build_digest_for
from tests.helpers import login_as, submit


@pytest.fixture
def other_team(session) -> tuple[Team, Member]:
    team = Team(slug="mobile", name="Mobile")
    session.add(team)
    session.flush()
    member = Member(team_id=team.id, display_name="Dana Park", tz="UTC")
    session.add(member)
    session.commit()
    return team, member


def test_pages_require_sign_in(client, team_with_members):
    for path in ("/submit", "/digests"):
        response = client.get(path, headers={"accept": "text/html"})
        assert response.status_code == 401
        assert "team code" in response.text


@pytest.mark.parametrize(
    "team_code, name",
    [
        ("CORE-NOPE1", "Ada Okafor"),  # a code no team has
        ("{code}", "Nobody Here"),  # the right code, a name not on the team
        ("{code}", ""),
        ("", "Ada Okafor"),
    ],
)
def test_a_wrong_code_or_name_does_not_sign_in(client, team_with_members, team_code, name):
    team, _members = team_with_members
    data = {"team_code": team_code.format(code=format_team_code(team.join_code)), "name": name}
    response = client.post("/login", data=data, follow_redirects=False)
    assert response.status_code == 401
    assert "do not match" in response.text
    assert client.get("/digests").status_code == 401


def test_code_and_name_forgive_case_and_spacing(client, team_with_members):
    team, (ada, *_rest) = team_with_members
    code = team.join_code.lower()
    data = {"team_code": f"  {code[:4]} - {code[4:]} ", "name": "  ada   OKAFOR "}
    response = client.post("/login", data=data, follow_redirects=False)
    assert response.status_code == 303
    assert "Ada Okafor" in client.get("/digests").text


def test_a_team_code_signs_in_only_that_teams_members(client, team_with_members, other_team):
    core, _members = team_with_members
    _mobile, dana = other_team
    data = {"team_code": format_team_code(core.join_code), "name": dana.display_name}
    assert client.post("/login", data=data, follow_redirects=False).status_code == 401


def test_an_inactive_member_cannot_sign_in(client, session, team_with_members):
    team, (ada, *_rest) = team_with_members
    ada.active = False
    session.commit()
    data = {"team_code": format_team_code(team.join_code), "name": ada.display_name}
    assert client.post("/login", data=data, follow_redirects=False).status_code == 401


def test_every_member_sees_the_team_code_on_the_team_page(client, team_with_members):
    team, (ada, bruno, _chen) = team_with_members
    for member in (ada, bruno):
        login_as(client, member.id)
        page = client.get("/me/team").text
        assert format_team_code(team.join_code) in page
        assert "Chen Wei" in page
    api = client.get("/api/me/team").json()
    assert api["team"]["join_code"] == format_team_code(team.join_code)
    assert api["team"]["members"] == ["Ada Okafor", "Bruno Silva", "Chen Wei"]


def test_the_json_api_signs_in_with_the_same_code_and_name(client, team_with_members):
    team, (ada, *_rest) = team_with_members
    bad = client.post("/api/auth/login", json={"team_code": "CORE-NOPE1", "name": "Ada Okafor"})
    assert bad.status_code == 401
    good = client.post(
        "/api/auth/login",
        json={"team_code": format_team_code(team.join_code), "name": "ada okafor"},
    )
    assert good.status_code == 200
    assert good.json()["member"]["display_name"] == "Ada Okafor"
    assert client.get("/api/me").json()["authenticated"] is True


def test_sign_out_ends_the_session(client, team_with_members):
    login_as(client, team_with_members[1][0].id)
    assert client.get("/digests").status_code == 200
    client.post("/logout", follow_redirects=False)
    assert client.get("/digests").status_code == 401


def test_cannot_submit_as_someone_else(client, session, team_with_members):
    _team, (ada, bruno, _chen) = team_with_members
    login_as(client, ada.id)
    # A forged member_id field is ignored: the session decides who submits.
    client.post(
        "/submit",
        data={"member_id": bruno.id, "progress": "Pretending to be Bruno."},
        follow_redirects=False,
    )
    update = session.execute(select(Update)).scalar_one()
    assert update.member_id == ada.id


def test_other_teams_digest_and_evidence_are_not_found(
    client, session, team_with_members, other_team
):
    core, (ada, *_rest) = team_with_members
    _mobile, dana = other_team

    submit(client, ada.id, blockers="Waiting on staging credentials.")
    digest = build_digest_for(client, session, core.id)
    item = session.execute(select(UpdateItem)).scalar_one()
    cycle_id = digest.cycle_id

    login_as(client, dana.id)
    assert client.get(f"/digest/{digest.id}").status_code == 404
    assert client.get(f"/digest/{digest.id}.md").status_code == 404
    assert client.get(f"/evidence/{item.id}").status_code == 404
    assert client.post(f"/digests/build/{cycle_id}").status_code == 404
    assert "Core Platform" not in client.get("/digests").text

    # A refused read is not a read: no audit row names Dana.
    views = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.EVIDENCE_VIEWED.value)
    ).scalars().all()
    assert all(v.actor_id != dana.id for v in views)


def test_evidence_views_are_audited_by_member(client, session, team_with_members):
    _team, (ada, bruno, _chen) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    item = session.execute(select(UpdateItem)).scalar_one()

    login_as(client, bruno.id)
    assert client.get(f"/evidence/{item.id}").status_code == 200

    view = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.EVIDENCE_VIEWED.value)
    ).scalar_one()
    assert view.actor_kind == "member"
    assert view.actor_id == bruno.id
    assert view.subject_member_id == ada.id


def test_resubmitting_supersedes_the_earlier_update(client, session, clock, team_with_members):
    core, (ada, *_rest) = team_with_members
    submit(client, ada.id, progress="First draft of my update.")
    clock.advance(minutes=5)
    submit(client, ada.id, progress="Corrected update.")

    session.expire_all()
    first, second = session.execute(select(Update).order_by(Update.captured_at)).scalars().all()
    assert first.superseded_by == second.id
    assert second.superseded_by is None
    # The earlier text is untouched (invariant 2), just no longer used.
    assert "First draft" in first.raw_text

    digest = build_digest_for(client, session, core.id)
    texts = [c.text for c in digest.claims]
    assert texts == ["Corrected update."]
