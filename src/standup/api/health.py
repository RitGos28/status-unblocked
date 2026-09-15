"""Liveness, readiness, and build info.

/healthz never touches a dependency so a wedged database cannot make the
platform kill a container that is otherwise fine. /readyz does check, because
that is the signal for "send this instance traffic".
"""

from fastapi import APIRouter
from sqlalchemy import text

from standup.config import get_settings
from standup.db.session import get_engine

router = APIRouter(tags=["ops"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
        return {"status": "degraded", "database": type(exc).__name__}
    return {"status": "ok", "database": "ok"}


@router.get("/version")
def version() -> dict[str, str]:
    settings = get_settings()
    return {
        "version": "0.1.0",
        "env": settings.env,
        "summarizer": settings.summarizer,
    }
