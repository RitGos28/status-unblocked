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


def build_latest(client, session, team_id: str | None = None):
    """Press Build on the latest day (of ``team_id``'s, if given) as the signed-in
    member, and return exactly the digest the build redirected to."""
    from sqlalchemy import select

    from standup.db.models import Digest, StandupCycle

    query = select(StandupCycle).order_by(StandupCycle.local_date.desc())
    if team_id is not None:
        query = query.where(StandupCycle.team_id == team_id)
    cycle = session.execute(query).scalars().first()
    response = client.post(f"/digests/build/{cycle.id}", follow_redirects=False)
    assert response.status_code == 303, response.text
    session.expire_all()
    return session.get(Digest, response.headers["location"].rsplit("/", 1)[-1])
