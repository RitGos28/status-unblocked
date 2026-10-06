"""Pages about the signed-in member's own account and data."""

import json
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from standup.auth.signin import team_summary
from standup.auth.teams_link import TEAMS_LINK_MAX_AGE_SECONDS, issue_teams_link_code
from standup.db.models import AuditLog, Member, StandupCycle, Update
from standup.deps import AppSettings, CurrentMember, DbSession, templates
from standup.domain.enums import AuditAction
from standup.domain.timezones import as_utc
from standup.privacy.audit import record_audit

router = APIRouter(tags=["me"])

# What each audit action means, in the words /me/data shows.
_ACTIONS = {
    AuditAction.UPDATE_INGESTED.value: "stored your update",
    AuditAction.EVIDENCE_VIEWED.value: "opened your update",
    AuditAction.DIGEST_BUILT.value: "built a digest",
    AuditAction.DIGEST_VIEWED.value: "viewed a digest",
    AuditAction.DATA_EXPORTED.value: "exported your data",
    AuditAction.DATA_DELETED.value: "removed your stored submission",
    AuditAction.TRACKER_WRITE.value: "wrote your blocker to the tracker",
}


@router.get("/me/team", response_class=HTMLResponse)
def my_team(request: Request, member: CurrentMember) -> HTMLResponse:
    """The member's team: the code to share with a teammate, and who is on it.

    Every member sees the same page. Sharing the code is not a privilege, so
    there is no role behind it (invariant 7).
    """
    return templates.TemplateResponse(
        request=request,
        name="team.html",
        context={"viewer": member, "team": team_summary(member.team)},
    )


@router.get("/me/teams", response_class=HTMLResponse)
def teams_link(request: Request, member: CurrentMember, settings: AppSettings) -> HTMLResponse:
    """A short-lived code that links this member's Teams account to the bot."""
    code = issue_teams_link_code(
        settings.secret_key.get_secret_value(), member.id, member.teams_aad_id
    )
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


@router.get("/me/data", response_class=HTMLResponse)
def my_data(request: Request, session: DbSession, member: CurrentMember) -> HTMLResponse:
    """Everything stored about me, and every recorded access to it.

    The audit log is only worth having if the person it is about can read it:
    this is where "who opened my updates" is answered.
    """
    return templates.TemplateResponse(
        request=request,
        name="me_data.html",
        context={
            "viewer": member,
            "updates": _my_updates(session, member),
            "events": _events_about(session, member),
        },
    )


@router.get("/me/export")
def my_export(session: DbSession, member: CurrentMember) -> Response:
    """The same data as /me/data, as a JSON file. The export is itself audited."""
    data = {
        "member": {
            "id": member.id,
            "display_name": member.display_name,
            "team": member.team.name,
            "teams_account_linked": member.teams_aad_id is not None,
        },
        "updates": _my_updates(session, member),
        "audit": _events_about(session, member),
    }
    record_audit(
        session,
        actor_kind="member",
        actor_id=member.id,
        action=AuditAction.DATA_EXPORTED,
        subject_member_id=member.id,
        object_ids={"updates": len(data["updates"])},
        purpose="the member exported their own data",
    )
    return Response(
        content=json.dumps(data, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="my-standup-data.json"'},
    )


def _my_updates(session: DbSession, member: Member) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Update, StandupCycle.local_date)
        .join(StandupCycle, Update.cycle_id == StandupCycle.id)
        .where(Update.member_id == member.id)
        .order_by(Update.captured_at.desc())
    ).all()
    return [
        {
            "id": update.id,
            "day": str(day),
            "captured_at": as_utc(update.captured_at).isoformat(),
            "source": update.source_kind,
            "raw_text": update.raw_text,
            "replaced_by_a_later_update": update.superseded_by is not None,
            "removed_by_retention_at": as_utc(update.purged_at).isoformat()
            if update.purged_at
            else None,
            # Not "items": in a template, u.items would be the dict method.
            "lines": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "text": item.text,
                    "removed_by_retention": item.text is None,
                }
                for item in sorted(update.items, key=lambda i: i.order)
            ],
        }
        for update, day in rows
    ]


def _events_about(session: DbSession, member: Member) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(AuditLog)
            .where(AuditLog.subject_member_id == member.id)
            .order_by(AuditLog.seq.desc())
        )
        .scalars()
        .all()
    )
    names = {
        m.id: m.display_name
        for m in session.execute(
            select(Member).where(Member.id.in_({r.actor_id for r in rows if r.actor_id}))
        ).scalars()
    }
    return [
        {
            "when": as_utc(row.ts).isoformat(),
            "action": row.action,
            "what": _ACTIONS.get(row.action, row.action),
            "by": names.get(row.actor_id or "", row.actor_id or row.actor_kind),
            "by_kind": row.actor_kind,
        }
        for row in rows
    ]
