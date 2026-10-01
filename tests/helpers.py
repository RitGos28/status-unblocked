"""Shared test helpers (plain functions, not fixtures)."""

from standup.auth.tokens import issue_login_token

TEST_SECRET_KEY = "test-secret-key-that-is-at-least-32-characters-long"


def login_as(client, member_id: str) -> None:
    """Sign the test client in as one member, through the real login route."""
    token = issue_login_token(TEST_SECRET_KEY, member_id)
    response = client.get(f"/login/{token}", follow_redirects=False)
    assert response.status_code == 303, response.text


def submit(client, member_id: str, **fields: str):
    """Sign in as ``member_id`` and file one update as them."""
    login_as(client, member_id)
    return client.post("/submit", data=fields, follow_redirects=False)
