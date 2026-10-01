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

from standup.db.models import StandupCycle, Update, UpdateItem
from standup.deps import CurrentMember, DbSession, ensure_same_team, templates
from standup.domain.enums import AuditAction
from standup.domain.errors import NotFoundError
from standup.privacy.audit import record_audit

router = APIRouter(tags=["evidence"])


@router.get("/evidence/{item_id}", response_class=HTMLResponse)
def view_evidence(
    item_id: str, request: Request, session: DbSession, member: CurrentMember
) -> HTMLResponse:
    item = session.get(UpdateItem, item_id)
    update = session.get(Update, item.update_id) if item else None
    cycle = session.get(StandupCycle, update.cycle_id) if update else None
    if item is None or update is None or cycle is None:
        raise NotFoundError(f"evidence {item_id} not found")
    # Checked before the audit row is written: a refused read is not a read.
    ensure_same_team(member, cycle.team_id, f"evidence {item_id}")

    record_audit(
        session,
        actor_kind="member",
        actor_id=member.id,
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
                "viewer": member,
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
            "viewer": member,
        },
    )
