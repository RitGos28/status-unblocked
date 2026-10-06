"""Shared test helpers (plain functions, not fixtures)."""

from standup.auth.team_code import format_team_code
from standup.db.models import Member
from standup.db.session import get_session_factory

TEST_SECRET_KEY = "test-secret-key-that-is-at-least-32-characters-long"


def login_as(client, member_id: str) -> None:
    """Sign the test client in as one member, through the real login route:
    their team's code and their name, as a person would type them."""
    with get_session_factory()() as session:
        member = session.get(Member, member_id)
        assert member is not None, member_id
        data = {"team_code": format_team_code(member.team.join_code), "name": member.display_name}
    response = client.post("/login", data=data, follow_redirects=False)
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
