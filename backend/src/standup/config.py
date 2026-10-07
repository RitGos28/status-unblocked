"""Application settings.

Fails fast at startup and names every missing key at once, rather than dying on
the first attribute access somewhere deep in a request.
"""

import functools
import os
from collections.abc import MutableMapping
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The Microsoft 365 Agents SDK reads its credentials from these hierarchical
# variables itself, so they carry no STANDUP_ prefix.
TEAMS_APP_ID_ENV = "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID"
TEAMS_REQUIRED_ENV = (
    TEAMS_APP_ID_ENV,
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET",
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID",
)
# Lets the bot accept unsigned requests, which is what Agents Playground sends.
# Only ever honoured in a local or test environment.
TEAMS_ANONYMOUS_ENV = "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED"
LOCAL_ENVS = frozenset({"local", "test"})

# backend/.env.example holds working demo values. With no backend/.env, they
# fill in whatever the environment leaves unset, so a fresh checkout runs the
# demo with nothing to configure. Never outside a local environment.
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_EXAMPLE_PATH = BACKEND_DIR / ".env.example"
ENV_FALLBACK_SWITCH = "STANDUP_ENV_EXAMPLE_FALLBACK"
# The signing key published in .env.example. Anyone can read it, so anyone
# could forge a session with it: refused outside local and test.
DEMO_SECRET_KEY = "demo-only-signing-key-published-in-env-example-never-deploy"


def parse_env_file(text: str) -> dict[str, str]:
    """KEY=value lines; blank values, comments and malformed lines are skipped."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value:
            values[key] = value
    return values


def apply_env_example_fallback(
    environ: MutableMapping[str, str] = os.environ,
    example: Path = ENV_EXAMPLE_PATH,
    dotenv_dirs: tuple[Path, ...] = (Path.cwd(), BACKEND_DIR),
) -> list[str]:
    """Fill unset variables from .env.example; return the keys it set.

    Does nothing when a .env exists (that is the real configuration), when
    STANDUP_ENV already names a non-local environment, or when switched off
    with STANDUP_ENV_EXAMPLE_FALLBACK=false (the test suite does this).
    A variable already set always wins.
    """
    if environ.get(ENV_FALLBACK_SWITCH, "true").strip().lower() in {"0", "false", "no"}:
        return []
    if environ.get("STANDUP_ENV", "local") not in LOCAL_ENVS:
        return []
    if any((d / ".env").is_file() for d in dotenv_dirs) or not example.is_file():
        return []
    values = parse_env_file(example.read_text(encoding="utf-8"))
    if values.get("STANDUP_ENV", "local") not in LOCAL_ENVS:
        return []
    applied = [key for key in values if key not in environ]
    for key in applied:
        environ[key] = values[key]
    return applied


def teams_anonymous_allowed() -> bool:
    return os.environ.get(TEAMS_ANONYMOUS_ENV, "").strip().lower() in {"1", "true", "yes"}


class DatabaseSettings(BaseSettings):
    """Just the connection string.

    Alembic uses this rather than ``Settings`` so running migrations does not
    require the application's secrets.
    """

    model_config = SettingsConfigDict(
        env_prefix="STANDUP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./standup.db"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


class Settings(DatabaseSettings):
    env: str = "local"
    # Public URL used in evidence links. Empty means "use the address the
    # request arrived on", which is right for local runs and most proxies.
    base_url: str = ""

    log_level: str = "INFO"
    log_json: bool = False

    # Signs the session cookie and Teams link codes. Required: there is no
    # safe default. Rotating it signs everyone out.
    secret_key: SecretStr = Field(min_length=32)
    # How long a sign-in lasts before the person signs in again.
    session_days: int = Field(default=30, ge=1)
    # Send the session cookie over HTTPS only. Turn on behind TLS.
    cookie_secure: bool = False

    # Which Summarizer implementation to use. "rules", the extractive engine,
    # is the only one; another would sit behind the same protocol and validator.
    summarizer: str = "rules"

    # When true, a claim that fails faithfulness validation raises instead of
    # being silently dropped. CI runs strict; production drops and reports.
    validator_strict: bool = False

    # Manager dashboard credentials (protects manager dashboard from non-managers)
    manager_username: str = "manager"
    manager_password: str = "status2026"


    # Optional integrations. Each one's credentials become required only when
    # it is switched on, and the error names every missing key at once.
    teams_enabled: bool = False
    tracker: str = "noop"
    # Build each team's digest at its cutoff, notify, and drain the tracker
    # outbox, from a loop inside the app. Off by default; scripts/tick does the
    # same once, for cron.
    scheduler: bool = False
    scheduler_interval_seconds: int = Field(default=60, ge=10)
    github_token: SecretStr | None = None
    # The GitHub REST API. Point it at scripts/fake_github.py for a demo.
    github_api_url: str = "https://api.github.com"

    @field_validator("base_url")
    @classmethod
    def _absolute_http_url(cls, value: str) -> str:
        """Blank means unset. Anything else must be an absolute http(s) URL:
        these links go into GitHub issues and Teams notices, where
        "localhost:8000/digest/…" or "   /digest/…" lead nowhere."""
        value = value.strip()
        if not value:
            return ""
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError(
                f"STANDUP_BASE_URL must be an absolute http(s) URL such as "
                f"http://127.0.0.1:8000, not {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _integration_credentials_present(self) -> "Settings":
        missing: list[str] = []
        if self.secret_key.get_secret_value() == DEMO_SECRET_KEY and self.env not in LOCAL_ENVS:
            raise ValueError(
                "STANDUP_SECRET_KEY is the demo key published in .env.example; "
                "generate a real one outside local and test"
            )
        if teams_anonymous_allowed() and self.env not in LOCAL_ENVS:
            raise ValueError(
                f"{TEAMS_ANONYMOUS_ENV} is only allowed when STANDUP_ENV is local or test; "
                "a deployed bot must verify every request's token"
            )
        if self.teams_enabled and not teams_anonymous_allowed():
            missing += [key for key in TEAMS_REQUIRED_ENV if not os.environ.get(key)]
        if self.tracker == "github" and not self.github_token:
            missing.append("STANDUP_GITHUB_TOKEN")
        if self.scheduler and not self.base_url:
            # Scheduled digests and notices carry links, and there is no
            # request to take the address from.
            missing.append("STANDUP_BASE_URL")
        if missing:
            raise ValueError("missing required settings: " + ", ".join(missing))
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    apply_env_example_fallback()
    return Settings()  # type: ignore[call-arg]  # secret_key comes from the environment


@functools.lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    apply_env_example_fallback()
    return DatabaseSettings()
