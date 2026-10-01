"""Web-form ingestion.

The adapter that has no external dependencies, so the pipeline is always
demoable. Who is submitting comes from the signed-in session, never from the
form, so nobody can file an update as someone else.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from standup.deps import AppClock, CurrentMember, DbSession, OptionalMember, templates
from standup.ingestion.service import ingest
from standup.ingestion.web_adapter import WebFormAdapter

router = APIRouter(tags=["ingestion"])


@router.get("/submit", response_class=HTMLResponse)
def submit_form(request: Request, member: CurrentMember) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="submit.html",
        context={"viewer": member},
    )


@router.post("/submit")
def submit(
    session: DbSession,
    clock: AppClock,
    member: CurrentMember,
    progress: str = Form(""),
    blockers: str = Form(""),
    plan: str = Form(""),
) -> RedirectResponse:
    now = clock.now()
    submission = WebFormAdapter().to_raw_submission(
        {
            "member_id": member.id,
            "progress": progress,
            "blockers": blockers,
            "plan": plan,
            "captured_at": now,
        }
    )
    update = ingest(
        session,
        submission,
        member,
        now,
        # A web submission has no platform message, so the evidence view is
        # the citation target; say so rather than leave a silent null.
        permalink_reason="webform: no platform message to link to",
    )
    return RedirectResponse(url=f"/digests?submitted={update.id}", status_code=303)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, viewer: OptionalMember) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"viewer": viewer},
    )
