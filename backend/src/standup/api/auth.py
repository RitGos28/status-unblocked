"""Sign in with a team code and your name; sign out.

There are no passwords and no roles. A team code is shared by the whole team
(every member sees it on their Team page) and the name says who you are; see
``auth/team_code.py`` for the trade that makes.
"""

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from standup.auth.signin import SIGN_IN_FAILED, sign_in
from standup.deps import DbSession, OptionalMember, templates
from standup.logging_conf import get_logger

router = APIRouter(tags=["auth"])
log = get_logger(__name__)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, viewer: OptionalMember) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"viewer": viewer, "error": None, "team_code": "", "name": ""},
    )


@router.post("/login")
def login(
    request: Request,
    session: DbSession,
    team_code: str = Form(""),
    name: str = Form(""),
) -> Response:
    member = sign_in(session, team_code, name)
    if member is None:
        # Neither the code nor the name is logged: the code is shared, the
        # name may be a typo of a real one.
        log.info("auth.login_rejected")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"viewer": None, "error": SIGN_IN_FAILED, "team_code": team_code, "name": name},
            status_code=401,
        )

    request.session.clear()
    request.session["member_id"] = member.id
    log.info("auth.login", member_id=member.id)
    return RedirectResponse(url="/digests", status_code=303)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/?signed_out=1", status_code=303)
