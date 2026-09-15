"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from standup.api import digests, evidence, health, web_forms
from standup.config import get_settings
from standup.db.session import create_all
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
    async def handle_standup_error(_request: Request, exc: StandupError) -> JSONResponse:
        """RFC-9457 problem+json, so clients get a machine-readable shape."""
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

    app.include_router(health.router)
    app.include_router(web_forms.router)
    app.include_router(digests.router)
    app.include_router(evidence.router)
    return app


app = create_app()
