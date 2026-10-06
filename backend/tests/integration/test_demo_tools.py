"""The demo tooling works: seed data and the scheduler's demo clock.

docs/DEMO.md and scripts/demo_check.sh depend on these; if they break, the
demo breaks, so they are tested like features.
"""

from datetime import UTC, datetime

import pytest
from scripts.seed_demo import seed
from scripts.tick import _parse_at
from sqlalchemy import select

from standup.db.models import Member, StandupCycle, Team, Update

NOW = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)


def test_seed_creates_both_teams_and_is_safe_to_rerun(session, app_env):
    seed(now=NOW)
    seed(now=NOW)
    teams = {t.slug: t for t in session.execute(select(Team)).scalars()}
    assert set(teams) == {"core", "mobile"}
    assert len(session.execute(select(Member)).scalars().all()) == 4


def test_seed_days_files_one_cycle_per_day_with_a_misfiled_blocker(session, app_env):
    seed(days=2, now=NOW)
    seed(days=2, now=NOW)  # re-running adds nothing

    by_team = {
        (c.team_id, str(c.local_date)) for c in session.execute(select(StandupCycle)).scalars()
    }
    teams = {t.slug: t.id for t in session.execute(select(Team)).scalars()}
    assert by_team == {
        (teams["core"], "2026-09-14"),
        (teams["core"], "2026-09-15"),
        (teams["mobile"], "2026-09-15"),
    }
    updates = session.execute(select(Update)).scalars().all()
    assert len(updates) == 7
    today = [u.raw_text for u in updates if u.captured_at.replace(tzinfo=UTC) == NOW]
    assert any("Stuck on the deploy pipeline." in text for text in today)
    # The earlier day is filed before the 11:00 cutoff, so the scheduler builds it.
    earlier = [u for u in updates if u.captured_at.replace(tzinfo=UTC) != NOW]
    assert all(u.captured_at.hour == 9 for u in earlier)


def test_with_updates_means_today_only(session, app_env):
    seed(with_updates=True, now=NOW)
    dates = {str(c.local_date) for c in session.execute(select(StandupCycle)).scalars()}
    assert dates == {"2026-09-15"}  # one day, for each team


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-01T11:06:00Z", datetime(2026, 10, 1, 11, 6, tzinfo=UTC)),
        ("2026-10-01T11:06:00", datetime(2026, 10, 1, 11, 6, tzinfo=UTC)),
        ("2026-10-01T16:36:00+05:30", datetime(2026, 10, 1, 11, 6, tzinfo=UTC)),
    ],
)
def test_tick_at_parses_iso_times_as_utc(value, expected):
    parsed = _parse_at(value)
    assert parsed == expected
    assert parsed.utcoffset() == expected.utcoffset()


def test_the_seed_tells_you_to_serve_on_the_configured_port(monkeypatch, app_env):
    from scripts.seed_demo import serve_command

    from standup.config import get_settings

    monkeypatch.setenv("STANDUP_BASE_URL", "http://127.0.0.1:8025")
    get_settings.cache_clear()
    assert serve_command() == "uvicorn standup.main:app --port 8025"
