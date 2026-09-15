"""Application settings.

Fails fast at startup and names every missing key at once, rather than dying on
the first attribute access somewhere deep in a request.
"""

import functools

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STANDUP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    database_url: str = "sqlite:///./standup.db"
    base_url: str = "http://localhost:8000"

    log_level: str = "INFO"
    log_json: bool = False

    # Which Summarizer implementation to use. "rules" is the extractive engine;
    # "llm" lands in week 4 behind the same protocol and the same validator.
    summarizer: str = "rules"

    # When true, a claim that fails faithfulness validation raises instead of
    # being silently dropped. CI runs strict; production drops and reports.
    validator_strict: bool = False

    retention_days: int = Field(default=30, ge=1)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
