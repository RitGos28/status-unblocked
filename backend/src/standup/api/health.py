"""Liveness, readiness, and build info.

/healthz never touches a dependency so a wedged database cannot make the
platform kill a container that is otherwise fine. /readyz does check, because
that is the signal for "send this instance traffic".
"""

from fastapi import APIRouter
from sqlalchemy import func, select, text

from standup.config import get_settings
from standup.db.models import IngestRejection
from standup.db.session import get_engine, session_scope

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


@router.get("/scope")
def scope() -> dict[str, object]:
    """How many messages the bot refused as out of scope, by reason.

    Counts only. Nothing about what was refused, or from whom, is stored, so
    there is nothing more to show.
    """
    with session_scope() as session:
        rows = session.execute(
            select(IngestRejection.reason, func.count()).group_by(IngestRejection.reason)
        ).all()
    by_reason: dict[str, int] = {reason: count for reason, count in rows}  # noqa: C416
    return {"scope_violations": sum(by_reason.values()), "by_reason": by_reason}
