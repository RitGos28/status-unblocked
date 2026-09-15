"""Shared fixtures.

Time is injected, never faked with freezegun, and nothing sleeps. Each test
gets its own SQLite file so runs are isolated and parallelisable.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from standup.config import get_settings
from standup.db import session as db_session
from standup.db.models import Member, Team
from standup.deps import set_clock
from standup.domain.models import FakeClock, SystemClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(current=datetime(2026, 9, 15, 9, 30, tzinfo=UTC))


@pytest.fixture
def app_env(tmp_path, monkeypatch, clock):
    """Point the app at a throwaway database and a frozen clock."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("STANDUP_DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("STANDUP_BASE_URL", "http://testserver")
    monkeypatch.setenv("STANDUP_ENV", "test")

    get_settings.cache_clear()
    db_session.reset_engine()
    db_session.create_all()
    set_clock(clock)

    yield

    set_clock(SystemClock())
    db_session.reset_engine()
    get_settings.cache_clear()


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
        Member(team_id=team.id, display_name="Ada Okafor", tz="Europe/London"),
        Member(team_id=team.id, display_name="Bruno Silva", tz="America/Sao_Paulo"),
        Member(team_id=team.id, display_name="Chen Wei", tz="Asia/Singapore"),
    ]
    session.add_all(members)
    session.commit()
    return team, members
