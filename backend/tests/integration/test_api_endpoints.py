"""Tests for REST API endpoints consumed by the React frontend."""

from sqlalchemy import select

from standup.db.models import Member, Team, UpdateItem
from tests.helpers import login_as


def test_api_me_unauthenticated(client):
    response = client.get("/api/me")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is False
    assert data["member"] is None


def test_api_me_authenticated(client, team_with_members):
    member = team_with_members[1][0]
    login_as(client, member.id)
    response = client.get("/api/me")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["member"]["id"] == member.id
    assert data["member"]["display_name"] == member.display_name


def test_api_submit_and_digests(client, session, team_with_members):
    member = team_with_members[1][0]
    login_as(client, member.id)

    submit_res = client.post(
        "/api/submit",
        json={
            "progress": "Built the new React frontend migration.",
            "blockers": "Need staging database credentials.",
            "plan": "Connect the REST endpoints.",
        },
    )
    assert submit_res.status_code == 200
    submit_data = submit_res.json()
    assert submit_data["success"] is True
    assert "update_id" in submit_data
    assert "cycle_id" in submit_data

    # List digests
    digests_res = client.get("/api/digests")
    assert digests_res.status_code == 200
    digests_data = digests_res.json()
    assert len(digests_data["rows"]) >= 1
    assert digests_data["rows"][0]["update_count"] >= 1

    # Build digest
    cycle_id = submit_data["cycle_id"]
    build_res = client.post(f"/api/digests/build/{cycle_id}")
    assert build_res.status_code == 200
    digest_id = build_res.json()["digest_id"]

    # View digest
    view_res = client.get(f"/api/digest/{digest_id}")
    assert view_res.status_code == 200
    digest_detail = view_res.json()
    assert digest_detail["digest"]["id"] == digest_id
    assert len(digest_detail["sections"]) > 0
    assert all(section["hint"] for section in digest_detail["sections"])

    # Evidence view
    item = session.execute(select(UpdateItem)).scalars().first()
    assert item is not None
    evidence_res = client.get(f"/api/evidence/{item.id}")
    assert evidence_res.status_code == 200
    evidence_data = evidence_res.json()
    assert evidence_data["expired"] is False
    assert evidence_data["quote"] == item.text


def test_api_teams_link(client, team_with_members):
    member = team_with_members[1][0]
    login_as(client, member.id)
    response = client.get("/api/me/teams")
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert "minutes" in data


def _built_digest(client, member_id: str) -> str:
    login_as(client, member_id)
    cycle_id = client.post(
        "/api/submit",
        json={"progress": "Shipped the export.", "blockers": "Waiting on review from infra."},
    ).json()["cycle_id"]
    return client.post(f"/api/digests/build/{cycle_id}").json()["digest_id"]


def test_api_digest_downloads_match_the_server_pages(client, team_with_members):
    digest_id = _built_digest(client, team_with_members[1][0].id)

    md = client.get(f"/api/digest/{digest_id}.md")
    assert md.status_code == 200
    assert md.text == client.get(f"/digest/{digest_id}.md").text
    assert "Waiting on review from infra." in md.text

    csv = client.get(f"/api/digest/{digest_id}.csv")
    assert csv.status_code == 200
    assert csv.content == client.get(f"/digest/{digest_id}.csv").content
    assert "attachment" in csv.headers["content-disposition"]


def test_api_digest_downloads_are_team_scoped(client, session, team_with_members):
    digest_id = _built_digest(client, team_with_members[1][0].id)
    other = Team(slug="mobile", name="Mobile")
    session.add(other)
    session.flush()
    dana = Member(team_id=other.id, display_name="Vikram Malhotra", tz="UTC")
    session.add(dana)
    session.commit()

    login_as(client, dana.id)
    for suffix in (".md", ".csv", ""):
        assert client.get(f"/api/digest/{digest_id}{suffix}").status_code == 404


def test_api_my_data_shows_who_opened_my_update(client, session, team_with_members):
    ada, bruno = team_with_members[1][0], team_with_members[1][1]
    login_as(client, ada.id)
    client.post("/api/submit", json={"progress": "Wrote the migration."})
    item = session.execute(select(UpdateItem)).scalars().first()

    login_as(client, bruno.id)
    assert client.get(f"/api/evidence/{item.id}").status_code == 200

    login_as(client, ada.id)
    data = client.get("/api/me/data").json()
    assert data["updates"][0]["raw_text"]
    views = [e for e in data["events"] if e["action"] == "evidence.viewed"]
    assert [e["by"] for e in views] == ["Rohan Verma"]


def test_api_my_export_is_a_json_file_and_is_audited(client, team_with_members):
    ada = team_with_members[1][0]
    login_as(client, ada.id)
    response = client.get("/api/me/export")
    assert response.status_code == 200
    assert response.json()["member"]["display_name"] == "Aarav Sharma"
    assert "attachment" in response.headers["content-disposition"]
    events = client.get("/api/me/data").json()["events"]
    assert any(e["action"] == "data.exported" for e in events)


def test_api_my_data_needs_sign_in(client):
    assert client.get("/api/me/data").status_code == 401
    assert client.get("/api/me/export").status_code == 401


def test_api_digests_lists_the_last_build_and_whether_the_day_is_final(
    client, session, team_with_members
):
    first = _built_digest(client, team_with_members[1][0].id)
    client.post("/api/submit", json={"progress": "And one more thing."})
    rows = client.get("/api/digests").json()["rows"]
    second = client.post(f"/api/digests/build/{rows[0]['cycle']['id']}").json()["digest_id"]
    assert second != first

    row = client.get("/api/digests").json()["rows"][0]
    assert row["digest"]["id"] == second
    assert row["final"] is False


def test_api_manager_tasks_and_members_and_summary(client, team_with_members):
    member = team_with_members[1][0]
    login_as(client, member.id)

    # 1. Unauthenticated manager request is rejected
    unauth_res = client.get("/api/manager/tasks")
    assert unauth_res.status_code == 401

    # 2. Invalid credentials rejected
    bad_auth = client.post(
        "/api/manager/auth",
        json={"username": "wrong_user", "password": "wrong_password"},
    )
    assert bad_auth.status_code == 401

    # 3. Successful manager authentication
    auth_res = client.post(
        "/api/manager/auth",
        json={"username": "manager", "password": "status2026"},
    )
    assert auth_res.status_code == 200
    assert auth_res.json()["is_manager"] is True

    status_res = client.get("/api/manager/status")
    assert status_res.status_code == 200
    assert status_res.json()["is_manager"] is True

    # 4. Add member
    add_res = client.post(
        "/api/manager/members",
        json={"name": "Kavita Rao", "tz": "Asia/Kolkata"},
    )
    assert add_res.status_code == 200
    kavita = add_res.json()["member"]
    assert kavita["display_name"] == "Kavita Rao"

    # Member immediately visible on team endpoint
    team_res = client.get("/api/me/team")
    assert team_res.status_code == 200
    assert "Kavita Rao" in team_res.json()["team"]["members"]

    # 5. Create task assigned to Kavita
    task_res = client.post(
        "/api/manager/tasks",
        json={
            "title": "Migrate database indexes",
            "description": "Optimize query latencies on digests",
            "assigned_to_id": kavita["id"],
            "priority": "high",
            "due_date": "2026-10-15",
        },
    )
    assert task_res.status_code == 200
    task_id = task_res.json()["task"]["id"]
    assert task_res.json()["task"]["title"] == "Migrate database indexes"
    assert task_res.json()["task"]["assigned_to_name"] == "Kavita Rao"

    # 6. List tasks as manager
    list_res = client.get("/api/manager/tasks")
    assert list_res.status_code == 200
    assert len(list_res.json()["tasks"]) >= 1

    # 7. Member view of assigned tasks: sign in as Kavita
    login_as(client, kavita["id"])
    my_tasks_res = client.get("/api/me/tasks")
    assert my_tasks_res.status_code == 200
    my_tasks = my_tasks_res.json()["tasks"]
    assert len(my_tasks) == 1
    assert my_tasks[0]["id"] == task_id
    assert my_tasks[0]["title"] == "Migrate database indexes"

    # Kavita updates task status to in_progress
    update_my_res = client.patch(
        f"/api/me/tasks/{task_id}",
        json={"status": "in_progress"},
    )
    assert update_my_res.status_code == 200
    assert update_my_res.json()["task"]["status"] == "in_progress"

    # Kavita cannot access manager dashboard routes
    assert client.get("/api/manager/tasks").status_code == 401

    # 8. Re-authenticate as manager and mark completed
    auth_res2 = client.post(
        "/api/manager/auth",
        json={"username": "manager", "password": "status2026"},
    )
    assert auth_res2.status_code == 200

    update_res = client.patch(
        f"/api/manager/tasks/{task_id}",
        json={"status": "completed"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["task"]["status"] == "completed"
    assert update_res.json()["task"]["completed_at"] is not None

    # 9. Get manager summary
    summary_res = client.get("/api/manager/summary?scope=daily")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["stats"]["completed"] >= 1
    assert "Migrate database indexes" in [t["title"] for t in summary["completed_tasks"]]

    # 10. Team code update / custom code
    code_res = client.post("/api/manager/team-code", json={"custom_code": "TEST-SYNC9"})
    assert code_res.status_code == 200
    assert "TEST-SYNC9" in code_res.json()["join_code"]

    # 11. Lock manager session
    lock_res = client.post("/api/manager/lock")
    assert lock_res.status_code == 200
    assert lock_res.json()["is_manager"] is False
    assert client.get("/api/manager/tasks").status_code == 401

    # 12. Delete task (re-auth as manager)
    client.post(
        "/api/manager/auth",
        json={"username": "manager", "password": "status2026"},
    )
    del_res = client.delete(f"/api/manager/tasks/{task_id}")
    assert del_res.status_code == 200


def test_api_join_team(client, team_with_members):
    team = team_with_members[0]
    join_res = client.post(
        "/api/auth/join",
        json={
            "team_code": team.join_code,
            "name": "Devansh Nair",
            "tz": "Asia/Kolkata",
        },
    )
    assert join_res.status_code == 200
    member = join_res.json()["member"]
    assert member["display_name"] == "Devansh Nair"

    # Verified signed in
    me_res = client.get("/api/me")
    assert me_res.status_code == 200
    assert me_res.json()["member"]["display_name"] == "Devansh Nair"
