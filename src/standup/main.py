"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from standup.api import auth, digests, evidence, health, me, web_forms
from standup.config import get_settings
from standup.db.models import Member
from standup.db.session import create_all, session_scope
from standup.deps import templates
from standup.domain.errors import StandupError
from standup.logging_conf import configure_logging, get_logger
from standup.scheduling.jobs import run_once

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    # Convenience for local SQLite runs and tests. Real deployments run
    # "alembic upgrade head" so the schema carries a migration history.
    if settings.is_sqlite:
        create_all()

    log.info("app.started", env=settings.env, summarizer=settings.summarizer)
    scheduler = None
    if settings.scheduler:
        scheduler = asyncio.create_task(_scheduler_loop(_app, settings.scheduler_interval_seconds))
    yield
    if scheduler is not None:
        scheduler.cancel()
    log.info("app.stopped")


_FRAMEWORK_ERRORS = {
    404: ("Not found", "There is no page at this address."),
    405: ("Not allowed", "This address does not accept that kind of request."),
}


def _error_response(
    request: Request, status: int, title: str, detail: str, kind: str
) -> Response:
    """RFC-9457 problem+json, so clients get a machine-readable shape.

    A browser asking for HTML gets the same status as a readable page, with
    the signed-in header kept. problem+json stays the default for API clients.
    """
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"title": title, "detail": detail, "viewer": _viewer(request)},
            status_code=status,
        )
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": f"about:blank#{kind}", "title": title, "status": status, "detail": detail},
    )


def _viewer(request: Request) -> Member | None:
    """The signed-in member, for the header on error pages. Never raises."""
    member_id = request.session.get("member_id") if "session" in request.scope else None
    if not member_id:
        return None
    try:
        with session_scope() as session:
            member = session.get(Member, member_id)
            if member is None or not member.active:
                return None
            _ = member.team.name  # load it before the session closes
            return member
    except Exception:  # noqa: BLE001 - an error page must render even if the DB is down
        return None


async def _scheduler_loop(app: FastAPI, interval_seconds: int) -> None:
    """Run a scheduler pass every interval. A failing pass is logged, never fatal."""
    while True:
        try:
            await run_once(getattr(app.state, "teams_notifier", None))
        except Exception:  # noqa: BLE001 - the next pass retries
            log.exception("scheduler.tick_failed")
        await asyncio.sleep(interval_seconds)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Status Unblocked",
        description="Async standup digests with verifiable citations",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(StandupError)
    async def handle_standup_error(request: Request, exc: StandupError) -> Response:
        return _error_response(
            request, exc.status_code, exc.title, str(exc), type(exc).__name__
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> Response:
        """The framework's own errors (unknown URL, wrong method) get the same
        treatment as ours, instead of raw {"detail": "Not Found"} JSON."""
        title, detail = _FRAMEWORK_ERRORS.get(
            exc.status_code, ("Error", str(exc.detail))
        )
        return _error_response(request, exc.status_code, title, detail, f"HTTP{exc.status_code}")

    settings = get_settings()
    # Signed cookie holding only the member id. Lax, so a login link opened
    # from chat or email still lands signed in.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="standup_session",
        same_site="lax",
        https_only=settings.cookie_secure,
        max_age=settings.login_link_days * 86400,
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(web_forms.router)
    app.include_router(digests.router)
    app.include_router(evidence.router)
    app.include_router(me.router)
    if settings.teams_enabled:
        # Imported only when switched on, so the SDK is not loaded otherwise.
        from standup.api.teams_router import mount_teams

        mount_teams(app)
    return app


app = create_app()
