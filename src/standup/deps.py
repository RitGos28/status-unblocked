"""Dependency injection wiring.

Time and the summarizer are injected rather than imported directly, so tests
can swap a ``FakeClock`` or a deliberately hallucinating summarizer without
patching module internals.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from standup.config import Settings, get_settings
from standup.db.session import get_session_factory
from standup.domain.models import Clock, SystemClock
from standup.summarize.base import Summarizer
from standup.summarize.render import explain_rule
from standup.summarize.rules import RulesSummarizer

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["explain_rule"] = explain_rule

_clock: Clock = SystemClock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    """Tests use this to freeze or advance time."""
    global _clock
    _clock = clock


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_summarizer(settings: Annotated[Settings, Depends(get_settings)]) -> Summarizer:
    """Select the summarizer implementation.

    The LLM implementation lands in week 4 behind this same call, and clears the
    same validator.
    """
    if settings.summarizer == "rules":
        return RulesSummarizer()
    raise ValueError(
        f"unknown summarizer {settings.summarizer!r} (available: 'rules')"
    )


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
AppClock = Annotated[Clock, Depends(get_clock)]
AppSummarizer = Annotated[Summarizer, Depends(get_summarizer)]
