"""Shared fixtures.

Time is injected, never faked with freezegun, and nothing sleeps. Each test
gets its own SQLite file so runs are isolated and parallelisable.
"""

import os
from datetime import UTC, datetime

# The suite sets what it needs; .env.example's demo values must not fill gaps.
os.environ["STANDUP_ENV_EXAMPLE_FALLBACK"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from standup.config import get_database_settings, get_settings
from standup.db import session as db_session
from standup.db.models import Member, Team
from standup.deps import set_clock
from standup.domain.models import FakeClock, SystemClock
from tests.helpers import TEST_SECRET_KEY


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(current=datetime(2026, 9, 15, 9, 30, tzinfo=UTC))


@pytest.fixture
def app_env(tmp_path, monkeypatch, clock):
    """Point the app at a throwaway database and a frozen clock.

    SQLite in a temp file by default. CI sets STANDUP_TEST_DATABASE_URL to a
    Postgres instance, and each test then gets freshly created tables.
    """
    shared_url = os.environ.get("STANDUP_TEST_DATABASE_URL")
    db_url = shared_url or f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("STANDUP_DATABASE_URL", db_url)
    monkeypatch.setenv("STANDUP_BASE_URL", "http://testserver")
    monkeypatch.setenv("STANDUP_ENV", "test")
    monkeypatch.setenv("STANDUP_SECRET_KEY", TEST_SECRET_KEY)
    # Pin what a developer's backend/.env could otherwise change under the
    # suite: a fake-GitHub URL there would escape the respx mocks. Tests that
    # want GitHub or Teams set these themselves.
    monkeypatch.setenv("STANDUP_TRACKER", "noop")
    monkeypatch.setenv("STANDUP_GITHUB_API_URL", "https://api.github.com")
    monkeypatch.setenv("STANDUP_TEAMS_ENABLED", "false")
    monkeypatch.setenv("STANDUP_SCHEDULER", "false")

    get_settings.cache_clear()
    get_database_settings.cache_clear()
    db_session.reset_engine()
    db_session.create_all()
    set_clock(clock)

    yield

    set_clock(SystemClock())
    if shared_url:
        db_session.drop_all()
    db_session.reset_engine()
    get_settings.cache_clear()
    get_database_settings.cache_clear()


@pytest.fixture
def session(app_env) -> Session:
    s = db_session.get_session_factory()()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(app_env) -> TestClient:
    from standup.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def team_with_members(session) -> tuple[Team, list[Member]]:
    team = Team(slug="core", name="Core Platform")
    session.add(team)
    session.flush()

    members = [
        Member(team_id=team.id, display_name="Ritwik Gossain", tz="Europe/London"),
        Member(team_id=team.id, display_name="Madhav Kumar", tz="America/Sao_Paulo"),
        Member(team_id=team.id, display_name="Shresth Tiwari", tz="Asia/Singapore"),
    ]
    session.add_all(members)
    session.commit()
    return team, members
