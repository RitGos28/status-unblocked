"""Pages about the signed-in member's own account."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from standup.auth.tokens import TEAMS_LINK_MAX_AGE_SECONDS, issue_teams_link_code
from standup.deps import AppSettings, CurrentMember, templates

router = APIRouter(tags=["me"])


@router.get("/me/teams", response_class=HTMLResponse)
def teams_link(request: Request, member: CurrentMember, settings: AppSettings) -> HTMLResponse:
    """A short-lived code that links this member's Teams account to the bot."""
    code = issue_teams_link_code(settings.secret_key.get_secret_value(), member.id)
    return templates.TemplateResponse(
        request=request,
        name="me_teams.html",
        context={
            "viewer": member,
            "code": code,
            "minutes": TEAMS_LINK_MAX_AGE_SECONDS // 60,
            "linked": member.teams_aad_id is not None,
            "teams_enabled": settings.teams_enabled,
        },
    )
