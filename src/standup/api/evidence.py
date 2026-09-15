"""The evidence view — the canonical citation target.

Why this exists rather than a platform permalink: Teams message deep links
require a ``19:``-form chat id, and a 1:1 bot conversation reports its id in
``a:`` form, so a true per-message permalink is not constructible for the
primary collection path. Rather than pretend otherwise, every citation points
here, and a native permalink is offered *additionally* when one can be built.

That turns out to be the better engineering answer anyway: this store is
immutable and survives platform-side retention or deletion, which a permalink
does not.

Every view appends an audit row. Reading someone's words is an event.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from standup.db.models import Update, UpdateItem
from standup.deps import DbSession, templates
from standup.domain.enums import AuditAction
from standup.domain.errors import NotFoundError
from standup.privacy.audit import record_audit

router = APIRouter(tags=["evidence"])


@router.get("/evidence/{item_id}", response_class=HTMLResponse)
def view_evidence(item_id: str, request: Request, session: DbSession) -> HTMLResponse:
    item = session.get(UpdateItem, item_id)
    if item is None:
        raise NotFoundError(f"evidence {item_id} not found")

    update = session.get(Update, item.update_id)
    if update is None:
        raise NotFoundError(f"update {item.update_id} not found")

    record_audit(
        session,
        actor_kind="viewer",
        actor_id=request.client.host if request.client else "unknown",
        action=AuditAction.EVIDENCE_VIEWED,
        subject_member_id=update.member_id,
        object_ids={"update_item_id": item_id, "update_id": update.id},
        purpose="citation verification",
    )

    # After retention purges raw_text the digest stays valid and readable; the
    # evidence page says the source expired rather than 404ing or, worse,
    # silently rendering nothing.
    if update.is_purged or update.raw_text is None:
        return templates.TemplateResponse(
            request=request,
            name="evidence.html",
            context={
                "expired": True,
                "item": item,
                "update": update,
                "before": "",
                "quote": item.text,
                "after": "",
            },
        )

    raw = update.raw_text
    return templates.TemplateResponse(
        request=request,
        name="evidence.html",
        context={
            "expired": False,
            "item": item,
            "update": update,
            "before": raw[: item.span_start],
            "quote": raw[item.span_start : item.span_end],
            "after": raw[item.span_end :],
            "member_name": update.member.display_name,
        },
    )
