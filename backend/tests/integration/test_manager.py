"""The manager portal: one password-protected login, team admin, and a summary.

What it may do and what it must not is invariant 7. These tests pin both:
adding a member, reading digests and evidence, and the period summary work;
the portal is off without credentials; and every manager read of someone's
words is audited and visible to that person.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from standup.auth.team_code import format_team_code
from standup.config import get_settings
from standup.db.models import AuditLog, Member, Team
from standup.domain.enums import AuditAction
from tests.helpers import build_latest, login_as, submit

USERNAME = "manager"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def manager_client(monkeypatch, app_env) -> TestClient:
    """A client against an app with the manager portal switched on."""
    monkeypatch.setenv("STANDUP_MANAGER_USERNAME", USERNAME)
    monkeypatch.setenv("STANDUP_MANAGER_PASSWORD", PASSWORD)
    get_settings.cache_clear()
    from standup.main import create_app

    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def manager_login(client: TestClient) -> None:
    response = client.post("/api/manager/login", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 200, response.text


# --- the portal is off without credentials ---------------------------------


def test_portal_is_off_until_configured(client, team_with_members):
    assert client.get("/api/manager/me").json() == {
        "enabled": False,
        "authenticated": False,
        "username": None,
    }
    login = client.post("/api/manager/login", json={"username": USERNAME, "password": PASSWORD})
    assert login.status_code == 404
    assert "not switched on" in login.json()["detail"]
    assert client.get("/api/manager/teams").status_code == 404


# --- sign-in ------------------------------------------------------------------


@pytest.mark.parametrize(
    "username, password",
    [
        ("manager", "wrong"),
        ("someone-else", PASSWORD),
        ("", PASSWORD),
        ("manager", ""),
    ],
)
def test_wrong_username_or_password_is_refused_the_same_way(
    manager_client, team_with_members, username, password
):
    response = manager_client.post(
        "/api/manager/login", json={"username": username, "password": password}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "That username and password do not match."
    assert manager_client.get("/api/manager/teams").status_code == 401
    assert manager_client.get("/api/manager/me").json()["authenticated"] is False


def test_sign_in_sign_out(manager_client, team_with_members):
    manager_login(manager_client)
    me = manager_client.get("/api/manager/me").json()
    assert me == {"enabled": True, "authenticated": True, "username": USERNAME}
    assert manager_client.get("/api/manager/teams").status_code == 200
    manager_client.post("/api/manager/logout")
    assert manager_client.get("/api/manager/teams").status_code == 401


def test_manager_and_member_sessions_coexist(manager_client, team_with_members):
    """Signing in to the portal does not sign a member out, and the member's
    own routes never gain manager powers."""
    _team, (ada, *_rest) = team_with_members
    login_as(manager_client, ada.id)
    manager_login(manager_client)
    assert manager_client.get("/api/me").json()["member"]["display_name"] == "Ada Okafor"
    assert manager_client.get("/api/manager/me").json()["authenticated"] is True
    manager_client.post("/api/manager/logout")
    assert manager_client.get("/api/me").json()["authenticated"] is True


# --- teams and members ----------------------------------------------------------


def test_lists_every_team_and_one_teams_members(manager_client, session, team_with_members):
    core, _members = team_with_members
    session.add(Team(slug="mobile", name="Mobile"))
    session.commit()
    manager_login(manager_client)
    teams = manager_client.get("/api/manager/teams").json()["teams"]
    assert [t["slug"] for t in teams] == ["core", "mobile"]
    assert teams[0]["member_count"] == 3
    assert teams[0]["join_code"] == format_team_code(core.join_code)

    detail = manager_client.get(f"/api/manager/teams/{core.id}").json()
    assert [m["display_name"] for m in detail["members"]] == [
        "Ada Okafor",
        "Bruno Silva",
        "Chen Wei",
    ]
    assert detail["days"] == []
    assert manager_client.get("/api/manager/teams/nope").status_code == 404


def test_added_member_appears_on_the_team_page_and_can_sign_in(
    manager_client, session, team_with_members
):
    core, (ada, *_rest) = team_with_members
    manager_login(manager_client)
    response = manager_client.post(
        f"/api/manager/teams/{core.id}/members",
        json={"display_name": "  Erin   Novak ", "tz": "Europe/Dublin"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["member"]["display_name"] == "Erin Novak"
    assert body["member"]["tz"] == "Europe/Dublin"
    assert body["join_code"] == format_team_code(core.join_code)

    # A teammate sees Erin on the Team page, in both the page and the JSON API.
    login_as(manager_client, ada.id)
    assert "Erin Novak" in manager_client.get("/me/team").text
    assert "Erin Novak" in manager_client.get("/api/me/team").json()["team"]["members"]

    # Erin signs in with the team's code and her name, like anyone else.
    signin = manager_client.post(
        "/api/auth/login",
        json={"team_code": format_team_code(core.join_code), "name": "erin novak"},
    )
    assert signin.status_code == 200
    assert signin.json()["member"]["team_name"] == "Core Platform"

    # The addition is on the audit chain, under the manager, about Erin.
    erin = session.execute(select(Member).where(Member.display_name == "Erin Novak")).scalar_one()
    row = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.MEMBER_ADDED.value)
    ).scalar_one()
    assert row.actor_kind == "manager"
    assert row.actor_id == USERNAME
    assert row.subject_member_id == erin.id
    # And Erin can see who added her.
    events = manager_client.get("/api/me/data").json()["events"]
    assert events[-1]["by"] == "manager (manager)"
    assert events[-1]["what"] == "added you to the team"


@pytest.mark.parametrize(
    "payload, status, detail",
    [
        ({"display_name": "   "}, 400, "needs a name"),
        ({"display_name": "x" * 201}, 400, "too long"),
        ({"display_name": "Fay Lin", "tz": "Mars/Olympus"}, 400, "not a time zone"),
        ({"display_name": "ada OKAFOR"}, 409, "already on Core Platform"),
    ],
)
def test_bad_member_requests_are_refused(
    manager_client, session, team_with_members, payload, status, detail
):
    core, _members = team_with_members
    manager_login(manager_client)
    response = manager_client.post(f"/api/manager/teams/{core.id}/members", json=payload)
    assert response.status_code == status
    assert detail in response.json()["detail"]
    assert len(session.execute(select(Member)).scalars().all()) == 3


def test_adding_a_member_needs_the_manager(manager_client, team_with_members):
    core, (ada, *_rest) = team_with_members
    login_as(manager_client, ada.id)  # a member, not the manager
    response = manager_client.post(
        f"/api/manager/teams/{core.id}/members", json={"display_name": "Erin Novak"}
    )
    assert response.status_code == 401


# --- digests, evidence, and the summary --------------------------------------------


@pytest.fixture
def a_digested_day(manager_client, session, team_with_members):
    """Ada and Bruno file today; the digest is built."""
    _team, (ada, bruno, _chen) = team_with_members
    submit(
        manager_client,
        ada.id,
        progress="Reviewed the rollout plan.",
        blockers="Waiting on staging credentials from infra.",
    )
    submit(manager_client, bruno.id, progress="Merged the API changes.", blockers="No blockers.")
    return build_latest(manager_client, session)


def test_manager_reads_the_days_digest_and_evidence(
    manager_client, session, team_with_members, a_digested_day
):
    core, (ada, *_rest) = team_with_members
    digest = a_digested_day
    manager_login(manager_client)

    days = manager_client.get(f"/api/manager/teams/{core.id}").json()["days"]
    assert len(days) == 1
    assert days[0]["digest"]["id"] == digest.id
    assert days[0]["update_count"] == 2

    view = manager_client.get(f"/api/manager/digest/{digest.id}").json()
    assert "viewer" not in view
    blockers = [s for s in view["sections"] if s["kind"] == "blocker"][0]
    assert blockers["claims"][0]["text"] == "Waiting on staging credentials from infra."
    source_id = blockers["claims"][0]["citations"][0]["source_id"]

    evidence = manager_client.get(f"/api/manager/evidence/{source_id}").json()
    assert evidence["quote"] == "Waiting on staging credentials from infra."
    assert evidence["member_name"] == "Ada Okafor"
    assert manager_client.get("/api/manager/digest/nope").status_code == 404
    assert manager_client.get("/api/manager/evidence/nope").status_code == 404

    # Ada sees the manager opened her update. (Her sign-in replaces the whole
    # session, manager included, so this comes last.)
    login_as(manager_client, ada.id)
    opened = [
        e
        for e in manager_client.get("/api/me/data").json()["events"]
        if e["action"] == AuditAction.EVIDENCE_VIEWED.value
    ]
    assert opened[0]["by"] == "manager (manager)"
    assert opened[0]["by_kind"] == "manager"


def test_manager_builds_a_digest(manager_client, session, team_with_members):
    core, (ada, *_rest) = team_with_members
    submit(manager_client, ada.id, progress="Drafted the schema update.")
    manager_login(manager_client)
    cycle_id = manager_client.get(f"/api/manager/teams/{core.id}").json()["days"][0]["cycle"]["id"]
    response = manager_client.post(f"/api/manager/digests/build/{cycle_id}")
    assert response.status_code == 200
    digest_id = response.json()["digest_id"]
    assert manager_client.get(f"/api/manager/digest/{digest_id}").json()["sections"]
    built = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.DIGEST_BUILT.value)
    ).scalar_one()
    assert built.actor_id == f"manager:{USERNAME}"
    assert manager_client.post("/api/manager/digests/build/nope").status_code == 404


def test_summary_is_read_from_the_digests(
    manager_client, session, team_with_members, a_digested_day, clock
):
    core, (ada, bruno, _chen) = team_with_members
    manager_login(manager_client)
    summary = manager_client.get(f"/api/manager/teams/{core.id}/summary?days=7").json()

    assert summary["period"]["days"] == 7
    assert summary["period"]["to"] == "2026-09-15"
    assert summary["totals"] == {
        "days_with_updates": 1,
        "digests_built": 1,
        "updates": 2,
        "open_blockers": 1,
    }
    (day,) = summary["by_day"]
    assert day["local_date"] == "2026-09-15"
    assert day["digest_id"] == a_digested_day.id
    assert (day["blockers"], day["progress"], day["update_count"]) == (1, 2, 2)

    (blocker,) = summary["blockers"]["open"]
    assert blocker["text"] == "Waiting on staging credentials from infra."
    assert blocker["member_name"] == "Ada Okafor"
    assert blocker["days_reported"] == 1
    assert blocker["open"] is True
    assert blocker["citations"][0]["quote"] == "Waiting on staging credentials from infra."
    assert summary["blockers"]["earlier"] == []

    # Lines grouped by person: verbatim digest claims, nothing counted or scored.
    people = {p["display_name"]: p for p in summary["by_member"]}
    assert set(people) == {"Ada Okafor", "Bruno Silva"}
    assert [line["text"] for line in people["Bruno Silva"]["lines"]] == ["Merged the API changes."]
    assert not any(key in people["Ada Okafor"] for key in ("count", "streak", "missed", "late"))


def test_summary_window_and_days_without_a_digest(
    manager_client, session, team_with_members, clock
):
    core, (ada, *_rest) = team_with_members
    submit(manager_client, ada.id, progress="An undigested day.")
    manager_login(manager_client)
    summary = manager_client.get(f"/api/manager/teams/{core.id}/summary").json()
    (day,) = summary["by_day"]
    assert day["digest_id"] is None
    assert day["update_count"] == 1
    assert summary["totals"]["digests_built"] == 0
    assert summary["by_member"] == []

    assert manager_client.get(f"/api/manager/teams/{core.id}/summary?days=0").status_code == 422
    assert manager_client.get(f"/api/manager/teams/{core.id}/summary?days=91").status_code == 422
    assert manager_client.get("/api/manager/teams/nope/summary").status_code == 404
