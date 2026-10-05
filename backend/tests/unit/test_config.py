"""Startup fails fast and names every missing required key at once."""

import pytest
from pydantic import ValidationError

from standup.config import TEAMS_REQUIRED_ENV, Settings

KEY = "k" * 40


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "STANDUP_SECRET_KEY",
        "STANDUP_GITHUB_TOKEN",
        "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED",
        *TEAMS_REQUIRED_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def test_secret_key_is_required():
    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None)


def test_short_secret_key_is_rejected():
    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None, secret_key="too-short")


def test_integrations_off_need_no_credentials():
    settings = Settings(_env_file=None, secret_key=KEY)
    assert settings.teams_enabled is False
    assert settings.tracker == "noop"


def test_every_missing_integration_key_is_named_together():
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, secret_key=KEY, teams_enabled=True, tracker="github")
    message = str(excinfo.value)
    for name in (*TEAMS_REQUIRED_ENV, "STANDUP_GITHUB_TOKEN"):
        assert name in message


def test_github_tracker_with_token_is_accepted():
    settings = Settings(_env_file=None, secret_key=KEY, tracker="github", github_token="ghp_x")
    assert settings.github_token is not None


def test_anonymous_teams_mode_is_refused_outside_local(monkeypatch):
    monkeypatch.setenv("CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED", "True")
    with pytest.raises(ValidationError, match="only allowed when STANDUP_ENV is local or test"):
        Settings(_env_file=None, secret_key=KEY, env="production", teams_enabled=True)


def test_anonymous_teams_mode_needs_no_credentials_locally(monkeypatch):
    monkeypatch.setenv("CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED", "True")
    settings = Settings(_env_file=None, secret_key=KEY, env="local", teams_enabled=True)
    assert settings.teams_enabled is True


def test_scheduler_requires_a_base_url_for_its_links():
    with pytest.raises(ValidationError, match="STANDUP_BASE_URL"):
        Settings(_env_file=None, secret_key=KEY, scheduler=True, base_url="")
    assert Settings(_env_file=None, secret_key=KEY, scheduler=True, base_url="https://x").scheduler
