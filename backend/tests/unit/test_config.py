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


# Found by the round-2 review (B): "   " and "localhost:8020" were accepted,
# and ended up as "   /digest/…" and "localhost:8020/digest/…" in GitHub
# issues and Teams notices.


def test_a_blank_base_url_means_unset():
    assert Settings(_env_file=None, secret_key=KEY, base_url="   ").base_url == ""


@pytest.mark.parametrize("url", ["localhost:8020", "127.0.0.1:8000", "ftp://x.example", "http://"])
def test_a_base_url_must_be_an_absolute_http_url(url):
    with pytest.raises(ValidationError, match="STANDUP_BASE_URL"):
        Settings(_env_file=None, secret_key=KEY, base_url=url)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8000", "https://standup.example.com/", " https://x.example/app "]
)
def test_absolute_http_base_urls_are_accepted_and_trimmed(url):
    assert Settings(_env_file=None, secret_key=KEY, base_url=url).base_url == url.strip()


# --- .env.example as the demo fallback ---------------------------------------

from pathlib import Path  # noqa: E402

from standup.config import (  # noqa: E402
    DEMO_SECRET_KEY,
    ENV_EXAMPLE_PATH,
    apply_env_example_fallback,
    parse_env_file,
)


def test_env_example_is_a_working_local_demo_config(monkeypatch):
    """Applied as the fallback, .env.example alone starts the app."""
    values = parse_env_file(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert values["STANDUP_ENV"] == "local"
    assert values["STANDUP_SECRET_KEY"] == DEMO_SECRET_KEY
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None)
    assert settings.tracker == "github"
    assert settings.github_api_url.startswith("http://127.0.0.1")
    assert settings.teams_enabled is True


def test_fallback_fills_only_unset_keys(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("STANDUP_ENV=local\nSTANDUP_TRACKER=github\nSTANDUP_BLANK=\n# x=y\n")
    environ = {"STANDUP_TRACKER": "noop"}
    applied = apply_env_example_fallback(environ, example, dotenv_dirs=(tmp_path,))
    assert applied == ["STANDUP_ENV"]
    assert environ == {"STANDUP_TRACKER": "noop", "STANDUP_ENV": "local"}


def test_fallback_steps_aside_for_a_real_dotenv(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("STANDUP_TRACKER=github\n")
    (tmp_path / ".env").write_text("STANDUP_TRACKER=noop\n")
    environ: dict[str, str] = {}
    assert apply_env_example_fallback(environ, example, dotenv_dirs=(tmp_path,)) == []
    assert environ == {}


@pytest.mark.parametrize(
    "environ",
    [{"STANDUP_ENV": "production"}, {"STANDUP_ENV_EXAMPLE_FALLBACK": "false"}],
)
def test_fallback_is_off_outside_local_or_when_switched_off(tmp_path: Path, environ):
    example = tmp_path / ".env.example"
    example.write_text(f"STANDUP_SECRET_KEY={DEMO_SECRET_KEY}\n")
    before = dict(environ)
    assert apply_env_example_fallback(environ, example, dotenv_dirs=(tmp_path,)) == []
    assert environ == before


def test_fallback_ignores_an_example_that_is_not_local(tmp_path: Path):
    example = tmp_path / ".env.example"
    example.write_text("STANDUP_ENV=production\nSTANDUP_TRACKER=github\n")
    environ: dict[str, str] = {}
    assert apply_env_example_fallback(environ, example, dotenv_dirs=(tmp_path,)) == []


def test_demo_secret_key_works_locally():
    assert Settings(_env_file=None, secret_key=DEMO_SECRET_KEY, env="local").env == "local"


def test_demo_secret_key_is_refused_outside_local():
    with pytest.raises(ValidationError, match="demo key published in .env.example"):
        Settings(_env_file=None, secret_key=DEMO_SECRET_KEY, env="production")
