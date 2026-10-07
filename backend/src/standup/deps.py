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

from standup.auth.manager import MANAGER_SESSION_KEY
from standup.config import Settings, get_settings
from standup.db.models import Member
from standup.db.session import get_session_factory
from standup.domain.errors import ManagerUnauthorizedError, NotFoundError, UnauthorizedError
from standup.domain.models import Clock, SystemClock
from standup.ingestion.permalink import describe_missing_permalink
from standup.summarize.base import Summarizer
from standup.summarize.render import explain_rule
from standup.summarize.rules import RulesSummarizer
from standup.tracker.base import TrackerAdapter
from standup.tracker.github import GitHubTracker
from standup.tracker.noop import NoopTracker

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["explain_rule"] = explain_rule
templates.env.filters["describe_missing_permalink"] = describe_missing_permalink

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

    "rules" is the only implementation. Any other one plugs in here and must
    clear the same validator, which runs after it in ``summarize/service.py``.
    """
    if settings.summarizer == "rules":
        return RulesSummarizer()
    raise ValueError(f"unknown summarizer {settings.summarizer!r} (available: 'rules')")


def tracker_from_settings(settings: Settings) -> TrackerAdapter:
    """GitHub when configured (config.py guarantees the token), else no-op."""
    if settings.tracker == "github" and settings.github_token is not None:
        return GitHubTracker(
            settings.github_token.get_secret_value(), api_url=settings.github_api_url
        )
    return NoopTracker()


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
            "Sign in with your team's code and your name. Anyone on your team can "
            "read the code off their Team page."
        )
    return member


def ensure_same_team(member: Member, team_id: str, what: str) -> None:
    """Team scoping, in one place.

    Another team's resource answers 404, not 403, so its existence is not
    disclosed. Members have no override: the manager portal reads teams
    through its own routes in ``api/manager.py``, never through these.
    """
    if member.team_id != team_id:
        raise NotFoundError(f"That {what} does not exist, or it belongs to another team.")


def get_optional_manager(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> str | None:
    """The signed-in manager's username, or None. Nothing when the portal is off."""
    if not settings.manager_enabled:
        return None
    username = request.session.get(MANAGER_SESSION_KEY)
    if not username or username != settings.manager_username.strip():
        return None
    return str(username)


def get_current_manager(
    manager: Annotated[str | None, Depends(get_optional_manager)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """A signed-in manager, or 401 (404 when the portal is not configured)."""
    if not settings.manager_enabled:
        raise NotFoundError(
            "The manager portal is not switched on: set STANDUP_MANAGER_USERNAME "
            "and STANDUP_MANAGER_PASSWORD."
        )
    if manager is None:
        raise ManagerUnauthorizedError(
            "Sign in to the manager portal with its username and password."
        )
    return manager


AppSettings = Annotated[Settings, Depends(get_settings)]
AppClock = Annotated[Clock, Depends(get_clock)]
AppSummarizer = Annotated[Summarizer, Depends(get_summarizer)]
CurrentMember = Annotated[Member, Depends(get_current_member)]
OptionalMember = Annotated[Member | None, Depends(get_optional_member)]
CurrentManager = Annotated[str, Depends(get_current_manager)]
OptionalManager = Annotated[str | None, Depends(get_optional_manager)]
