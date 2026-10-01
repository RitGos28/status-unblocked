"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from standup.api import auth, digests, evidence, health, web_forms
from standup.config import get_settings
from standup.db.session import create_all
from standup.deps import templates
from standup.domain.errors import StandupError
from standup.logging_conf import configure_logging, get_logger

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
    yield
    log.info("app.stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Status Unblocked",
        description="Async standup digests with verifiable citations",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(StandupError)
    async def handle_standup_error(request: Request, exc: StandupError) -> Response:
        """RFC-9457 problem+json, so clients get a machine-readable shape.

        A browser asking for HTML gets the same status as a readable page
        instead of raw JSON. problem+json stays the default for API clients.
        """
        if "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"title": exc.title, "detail": str(exc)},
                status_code=exc.status_code,
            )
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": f"about:blank#{type(exc).__name__}",
                "title": exc.title,
                "status": exc.status_code,
                "detail": str(exc),
            },
        )

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
    return app


app = create_app()
