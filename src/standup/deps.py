"""Dependency injection wiring.

Time and the summarizer are injected rather than imported directly, so tests
can swap a ``FakeClock`` or a deliberately hallucinating summarizer without
patching module internals.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from standup.config import Settings, get_settings
from standup.db.models import Member
from standup.db.session import get_session_factory
from standup.domain.errors import NotFoundError, UnauthorizedError
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


def get_optional_member(request: Request, session: DbSession) -> Member | None:
    """The signed-in member, or None. Inactive members count as signed out."""
    member_id = request.session.get("member_id")
    if not member_id:
        return None
    member = session.get(Member, member_id)
    if member is None or not member.active:
        return None
    return member


def get_current_member(
    member: Annotated[Member | None, Depends(get_optional_member)],
) -> Member:
    if member is None:
        raise UnauthorizedError(
            "Open the personal link your team gave you to sign in. "
            "Each link is for one person and expires; ask a teammate to run "
            "'python -m scripts.issue_links' if yours has."
        )
    return member


def ensure_same_team(member: Member, team_id: str, what: str) -> None:
    """Team scoping, in one place.

    Another team's resource answers 404, not 403, so its existence is not
    disclosed. There is no override and no admin role (invariant 7).
    """
    if member.team_id != team_id:
        raise NotFoundError(f"{what} not found")
AppSettings = Annotated[Settings, Depends(get_settings)]
AppClock = Annotated[Clock, Depends(get_clock)]
AppSummarizer = Annotated[Summarizer, Depends(get_summarizer)]
CurrentMember = Annotated[Member, Depends(get_current_member)]
OptionalMember = Annotated[Member | None, Depends(get_optional_member)]
