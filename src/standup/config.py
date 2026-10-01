"""Application settings.

Fails fast at startup and names every missing key at once, rather than dying on
the first attribute access somewhere deep in a request.
"""

import functools
import os

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The Microsoft 365 Agents SDK reads its credentials from these hierarchical
# variables itself, so they carry no STANDUP_ prefix.
TEAMS_REQUIRED_ENV = (
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID",
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET",
    "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID",
)


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

    # Signs login links and the session cookie. Required: there is no safe
    # default. Rotating it signs everyone out and invalidates every link.
    secret_key: SecretStr = Field(min_length=32)
    # How long a personal login link stays valid.
    login_link_days: int = Field(default=30, ge=1)
    # Send the session cookie over HTTPS only. Turn on behind TLS.
    cookie_secure: bool = False

    # Which Summarizer implementation to use. "rules" is the extractive engine;
    # "llm" lands in week 4 behind the same protocol and the same validator.
    summarizer: str = "rules"

    # When true, a claim that fails faithfulness validation raises instead of
    # being silently dropped. CI runs strict; production drops and reports.
    validator_strict: bool = False

    retention_days: int = Field(default=30, ge=1)

    # Optional integrations. Each one's credentials become required only when
    # it is switched on, and the error names every missing key at once.
    teams_enabled: bool = False
    tracker: str = "noop"
    github_token: SecretStr | None = None

    @model_validator(mode="after")
    def _integration_credentials_present(self) -> "Settings":
        missing: list[str] = []
        if self.teams_enabled:
            missing += [key for key in TEAMS_REQUIRED_ENV if not os.environ.get(key)]
        if self.tracker == "github" and not self.github_token:
            missing.append("STANDUP_GITHUB_TOKEN")
        if missing:
            raise ValueError("missing required settings: " + ", ".join(missing))
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # secret_key comes from the environment


@functools.lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
