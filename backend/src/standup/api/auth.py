"""Sign in with a personal link; sign out."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from standup.auth.tokens import read_login_token
from standup.db.models import Member
from standup.deps import AppSettings, DbSession
from standup.domain.errors import UnauthorizedError
from standup.logging_conf import get_logger

router = APIRouter(tags=["auth"])
log = get_logger(__name__)


@router.get("/login/{token}")
def login(
    token: str, request: Request, session: DbSession, settings: AppSettings
) -> RedirectResponse:
    member_id = read_login_token(
        settings.secret_key.get_secret_value(),
        token,
        max_age_seconds=settings.login_link_days * 86400,
    )
    member = session.get(Member, member_id) if member_id else None
    if member is None or not member.active:
        log.info("auth.login_rejected")
        raise UnauthorizedError(
            "That link is invalid or has expired. Ask a teammate for a fresh one."
        )

    request.session.clear()
    request.session["member_id"] = member.id
    log.info("auth.login", member_id=member.id)
    return RedirectResponse(url="/digests", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/?signed_out=1", status_code=303)
