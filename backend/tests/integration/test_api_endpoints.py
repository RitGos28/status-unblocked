"""Tests for REST API endpoints consumed by the React frontend."""

from sqlalchemy import select

from standup.db.models import UpdateItem
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
