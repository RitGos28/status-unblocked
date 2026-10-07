"""REST API endpoints for the modern React frontend.

These endpoints return structured JSON for all client-side operations:
authentication, updates submission, digest browsing, and verifiable evidence lookup.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from standup.api.digests import drain_tracker_outbox, view_digest_csv, view_digest_markdown
from standup.api.me import _events_about, _my_updates, my_export
from standup.auth.signin import SIGN_IN_FAILED, sign_in, team_summary
from standup.auth.team_code import (
    format_team_code,
    generate_team_code,
    normalise_name,
    normalise_team_code,
)
from standup.auth.teams_link import TEAMS_LINK_MAX_AGE_SECONDS, issue_teams_link_code
from standup.db.models import (
    Digest,
    Member,
    StandupCycle,
    Team,
    TeamTask,
    TrackerLink,
    Update,
    UpdateItem,
)
from standup.deps import (
    AppClock,
    AppSettings,
    AppSummarizer,
    CurrentMember,
    DbSession,
    OptionalMember,
    ensure_same_team,
)
from standup.domain.enums import AuditAction
from standup.domain.errors import BadRequestError, NotFoundError, UnauthorizedError
from standup.ingestion.permalink import describe_missing_permalink
from standup.ingestion.service import ingest
from standup.ingestion.web_adapter import WebFormAdapter
from standup.privacy.audit import record_audit
from standup.privacy.retention import day_was_purged
from standup.summarize.render import SECTION_HINTS, SECTION_ORDER, SECTION_TITLES, explain_rule
from standup.summarize.service import build_digest, latest_digest

router = APIRouter(prefix="/api", tags=["frontend-api"])


class LoginPayload(BaseModel):
    team_code: str = Field(default="")
    name: str = Field(default="")


class JoinPayload(BaseModel):
    team_code: str = Field(default="")
    name: str = Field(default="")
    tz: str = Field(default="UTC")


class SubmitPayload(BaseModel):
    progress: str = Field(default="")
    blockers: str = Field(default="")
    plan: str = Field(default="")


class TaskCreatePayload(BaseModel):
    title: str
    description: str = Field(default="")
    assigned_to_id: str | None = Field(default=None)
    priority: str = Field(default="medium")
    due_date: str | None = Field(default=None)


class TaskUpdatePayload(BaseModel):
    title: str | None = Field(default=None)
    description: str | None = Field(default=None)
    assigned_to_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    priority: str | None = Field(default=None)
    due_date: str | None = Field(default=None)


class AddMemberPayload(BaseModel):
    name: str
    tz: str = Field(default="UTC")


class UpdateTeamCodePayload(BaseModel):
    custom_code: str | None = Field(default=None)


class ManagerAuthPayload(BaseModel):
    username: str = Field(default="")
    password: str = Field(default="")


class MemberTaskUpdatePayload(BaseModel):
    status: str


def _format_member(member: Member) -> dict[str, Any]:
    return {
        "id": member.id,
        "display_name": member.display_name,
        "team_id": member.team_id,
        "team_name": member.team.name if member.team else "Team",
        "tz": member.tz,
        "teams_aad_id": member.teams_aad_id,
    }


def _age_days(now: datetime, created_at: datetime) -> int:
    if created_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    return max((now - created_at).days, 0)


@router.get("/me")
def get_current_user(viewer: OptionalMember) -> dict[str, Any]:
    """Get the signed-in member status."""
    if viewer is None:
        return {"authenticated": False, "member": None}
    return {
        "authenticated": True,
        "member": _format_member(viewer),
    }


@router.post("/auth/login")
def api_login(payload: LoginPayload, request: Request, session: DbSession) -> dict[str, Any]:
    """Sign in with a team code and a name; sets the session cookie."""
    member = sign_in(session, payload.team_code, payload.name)
    if member is None:
        raise UnauthorizedError(SIGN_IN_FAILED)

    request.session.clear()
    request.session["member_id"] = member.id
    return {
        "success": True,
        "member": _format_member(member),
    }


@router.post("/auth/join")
def api_join_team(
    payload: JoinPayload, request: Request, session: DbSession
) -> dict[str, Any]:
    """Join a team using its team code and your name. Creates the member if new."""
    code = normalise_team_code(payload.team_code)
    name = payload.name.strip()
    if not code or not name:
        raise BadRequestError("Team code and name are both required.")

    team = session.execute(select(Team).where(Team.join_code == code)).scalar_one_or_none()
    if team is None:
        raise UnauthorizedError(
            "That team code was not found. Please verify the code or check with your team manager."
        )

    wanted = normalise_name(name)
    members = session.execute(
        select(Member).where(Member.team_id == team.id)
    ).scalars().all()

    target_member = None
    for m in members:
        if normalise_name(m.display_name) == wanted:
            if not m.active:
                m.active = True
            target_member = m
            break

    if target_member is None:
        target_member = Member(
            team_id=team.id,
            display_name=name,
            tz=payload.tz.strip() or team.tz_default or "UTC",
            source_keys={"webform": name.lower().replace(" ", ".")},
        )
        session.add(target_member)
        session.flush()

    session.commit()
    request.session.clear()
    request.session["member_id"] = target_member.id

    return {
        "success": True,
        "member": _format_member(target_member),
    }


@router.post("/auth/logout")
def api_logout(request: Request) -> dict[str, Any]:
    """Sign out the current member."""
    request.session.clear()
    return {"success": True}


@router.get("/digests")
def api_list_digests(session: DbSession, member: CurrentMember) -> dict[str, Any]:
    """List standup cycles and digests for the viewer's team."""
    cycles = (
        session.execute(
            select(StandupCycle)
            .where(StandupCycle.team_id == member.team_id)
            .order_by(StandupCycle.local_date.desc())
        )
        .scalars()
        .all()
    )

    rows = []
    for cycle in cycles:
        digest = latest_digest(session, cycle.id)
        update_count = len(
            session.execute(
                select(Update)
                .where(Update.cycle_id == cycle.id)
                .where(Update.is_live())
            )
            .scalars()
            .all()
        )
        team = session.get(Team, cycle.team_id)
        rows.append(
            {
                "cycle": {
                    "id": cycle.id,
                    "local_date": str(cycle.local_date),
                    "state": cycle.state,
                },
                "digest": {
                    "id": digest.id,
                    "generated_at": digest.generated_at.isoformat() if digest else None,
                }
                if digest
                else None,
                "update_count": update_count,
                # Retention removed the day's stored text: nothing to rebuild from.
                "final": day_was_purged(session, cycle.id),
                "team_name": team.name if team else "Team",
            }
        )

    return {
        "viewer": _format_member(member),
        "rows": rows,
    }


@router.post("/digests/build/{cycle_id}")
def api_build_digest(
    cycle_id: str,
    request: Request,
    session: DbSession,
    member: CurrentMember,
    summarizer: AppSummarizer,
    settings: AppSettings,
    background: BackgroundTasks,
    clock: AppClock,
) -> dict[str, Any]:
    """Trigger a digest build for a specific standup cycle."""
    cycle = session.get(StandupCycle, cycle_id)
    if cycle is None:
        raise NotFoundError("That standup day does not exist, or it belongs to another team.")
    ensure_same_team(member, cycle.team_id, "standup day")

    digest = build_digest(
        session,
        cycle_id=cycle_id,
        summarizer=summarizer,
        base_url=settings.base_url or str(request.base_url),
        now=clock.now(),
        actor_id=member.id,
    )
    session.commit()
    background.add_task(drain_tracker_outbox)
    return {
        "success": True,
        "digest_id": digest.id,
        "cycle_id": cycle.id,
    }


# The downloads, under /api so the React app's proxy reaches them. Registered
# before /digest/{digest_id}, which would otherwise swallow the suffix.
@router.api_route("/digest/{digest_id}.md", methods=["GET", "HEAD"])
def api_digest_markdown(digest_id: str, session: DbSession, member: CurrentMember) -> Response:
    """The digest as Markdown, the same text as /digest/{id}.md."""
    body = view_digest_markdown(digest_id, session, member)
    return Response(content=body, media_type="text/plain; charset=utf-8")


@router.api_route("/digest/{digest_id}.csv", methods=["GET", "HEAD"])
def api_digest_csv(digest_id: str, session: DbSession, member: CurrentMember) -> Response:
    """The digest as a spreadsheet, the same file as /digest/{id}.csv."""
    return view_digest_csv(digest_id, session, member)


@router.get("/digest/{digest_id}")
def api_view_digest(
    digest_id: str, session: DbSession, member: CurrentMember, clock: AppClock
) -> dict[str, Any]:
    """Retrieve full structured digest content for the viewer's team."""
    digest = session.get(Digest, digest_id)
    cycle = session.get(StandupCycle, digest.cycle_id) if digest else None
    if digest is None or cycle is None:
        raise NotFoundError("That digest does not exist, or it belongs to another team.")
    ensure_same_team(member, cycle.team_id, "digest")

    team = session.get(Team, cycle.team_id)
    fingerprints = [c.tracker_fingerprint for c in digest.claims if c.tracker_fingerprint]
    links = {
        link.fingerprint: link
        for link in session.execute(
            select(TrackerLink).where(TrackerLink.fingerprint.in_(fingerprints))
        ).scalars()
    }
    now = clock.now()
    issues = {
        fp: {
            "number": link.issue_number,
            "url": link.issue_url,
            "age_days": _age_days(now, link.created_at),
        }
        for fp, link in links.items()
    }

    sections: list[dict[str, Any]] = []
    for kind in SECTION_ORDER:
        claims = [c for c in digest.claims if c.kind == kind.value]
        if claims:
            claims_data = []
            for claim in sorted(claims, key=lambda c: c.order):
                issue = issues.get(claim.tracker_fingerprint) if claim.tracker_fingerprint else None
                claims_data.append(
                    {
                        "id": claim.id,
                        "member_name": claim.member_name,
                        "text": claim.text,
                        "matched_rule": claim.matched_rule,
                        "rule_explanation": explain_rule(claim.matched_rule),
                        "tracker_fingerprint": claim.tracker_fingerprint,
                        "issue": issue,
                        "citations": claim.citations_json,
                    }
                )
            sections.append(
                {
                    "kind": kind.value,
                    "title": SECTION_TITLES[kind],
                    "hint": SECTION_HINTS[kind],
                    "claims": claims_data,
                }
            )

    return {
        "digest": {
            "id": digest.id,
            "cycle_id": digest.cycle_id,
            "generated_at": digest.generated_at.isoformat(),
            "summarizer_name": digest.summarizer_name,
            "summarizer_version": digest.summarizer_version,
            "withheld_count": digest.withheld_count,
            "truncated_count": digest.truncated_count,
            "body_md": digest.body_md,
        },
        "cycle": {
            "id": cycle.id,
            "local_date": str(cycle.local_date),
            "state": cycle.state,
        },
        "team_name": team.name if team else "Team",
        "sections": sections,
        "viewer": _format_member(member),
    }


@router.post("/submit")
def api_submit(
    session: DbSession,
    clock: AppClock,
    member: CurrentMember,
    payload: SubmitPayload,
) -> dict[str, Any]:
    """Submit today's standup update via JSON payload."""
    now = clock.now()
    submission = WebFormAdapter().to_raw_submission(
        {
            "member_id": member.id,
            "progress": payload.progress,
            "blockers": payload.blockers,
            "plan": payload.plan,
            "captured_at": now,
        }
    )
    update = ingest(
        session,
        submission,
        member,
        now,
        permalink_reason="webform: no platform message to link to",
    )
    return {
        "success": True,
        "update_id": update.id,
        "cycle_id": update.cycle_id,
    }


@router.get("/evidence/{item_id}")
def api_view_evidence(
    item_id: str, session: DbSession, member: CurrentMember
) -> dict[str, Any]:
    """Fetch citation evidence and record an audit row."""
    item = session.get(UpdateItem, item_id)
    update = session.get(Update, item.update_id) if item else None
    cycle = session.get(StandupCycle, update.cycle_id) if update else None
    if item is None or update is None or cycle is None:
        raise NotFoundError("That evidence does not exist, or it belongs to another team.")
    ensure_same_team(member, cycle.team_id, "evidence")

    record_audit(
        session,
        actor_kind="member",
        actor_id=member.id,
        action=AuditAction.EVIDENCE_VIEWED,
        subject_member_id=update.member_id,
        object_ids={"update_item_id": item_id, "update_id": update.id},
        purpose="citation verification",
    )

    if update.is_purged or update.raw_text is None:
        return {
            "expired": True,
            "quote": item.text,
            "before": "",
            "after": "",
            "item": {
                "id": item.id,
                "span_start": item.span_start,
                "span_end": item.span_end,
                "kind": item.kind,
            },
            "member_name": update.member.display_name if update.member else "Unknown",
            "purged_at": update.purged_at.isoformat() if update.purged_at else None,
            "captured_at": update.captured_at.isoformat(),
            "source_kind": update.source_kind,
            "permalink": update.permalink,
            "permalink_reason": describe_missing_permalink(update.permalink_reason)
            if update.permalink_reason
            else None,
        }

    raw = update.raw_text
    return {
        "expired": False,
        "quote": raw[item.span_start : item.span_end],
        "before": raw[: item.span_start],
        "after": raw[item.span_end :],
        "item": {
            "id": item.id,
            "span_start": item.span_start,
            "span_end": item.span_end,
            "kind": item.kind,
        },
        "member_name": update.member.display_name if update.member else "Unknown",
        "captured_at": update.captured_at.isoformat(),
        "source_kind": update.source_kind,
        "permalink": update.permalink,
        "permalink_reason": describe_missing_permalink(update.permalink_reason)
        if update.permalink_reason
        else None,
    }


@router.get("/me/team")
def api_my_team(member: CurrentMember) -> dict[str, Any]:
    """The member's team: its sign-in code to share, and who is on it."""
    return {"team": team_summary(member.team), "viewer": _format_member(member)}


@router.get("/me/data")
def api_my_data(session: DbSession, member: CurrentMember) -> dict[str, Any]:
    """Everything stored about the member, and every recorded access to it."""
    return {
        "updates": _my_updates(session, member),
        "events": _events_about(session, member),
        "viewer": _format_member(member),
    }


@router.get("/me/export")
def api_my_export(session: DbSession, member: CurrentMember) -> Response:
    """The same JSON file as /me/export; the export is audited the same way."""
    return my_export(session, member)


@router.get("/me/teams")
def api_teams_link(
    member: CurrentMember, settings: AppSettings
) -> dict[str, Any]:
    """Retrieve personal linking code for Microsoft Teams."""
    code = issue_teams_link_code(
        settings.secret_key.get_secret_value(), member.id, member.teams_aad_id
    )
    return {
        "teams_enabled": settings.teams_enabled,
        "linked": member.teams_aad_id is not None,
        "code": code,
        "minutes": TEAMS_LINK_MAX_AGE_SECONDS // 60,
        "viewer": _format_member(member),
    }


# =====================================================================
# Manager Dashboard & Team Tasks Endpoints
# =====================================================================


def _format_task(task: TeamTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "team_id": task.team_id,
        "title": task.title,
        "description": task.description,
        "assigned_to_id": task.assigned_to_id,
        "assigned_to_name": task.assigned_to.display_name if task.assigned_to else None,
        "created_by_id": task.created_by_id,
        "created_by_name": task.created_by.display_name if task.created_by else None,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _ensure_manager(request: Request) -> None:
    """Verify that current session has authenticated as manager."""
    if not request.session.get("is_manager", False):
        raise UnauthorizedError(
            "Manager authorization required. Please authenticate with manager credentials."
        )


# ---------------------------------------------------------------------
# Manager Authentication & Access Control
# ---------------------------------------------------------------------


@router.post("/manager/auth")
def api_manager_auth(
    payload: ManagerAuthPayload,
    request: Request,
    settings: AppSettings,
) -> dict[str, Any]:
    """Authenticate with manager credentials (User ID and Password)."""
    username = payload.username.strip()
    password = payload.password.strip()
    if username == settings.manager_username and password == settings.manager_password:
        request.session["is_manager"] = True
        return {"success": True, "is_manager": True}
    raise UnauthorizedError("Invalid manager credentials.")


@router.get("/manager/status")
def api_manager_status(request: Request) -> dict[str, Any]:
    """Check if the current session has manager access."""
    return {"is_manager": bool(request.session.get("is_manager", False))}


@router.post("/manager/lock")
def api_manager_lock(request: Request) -> dict[str, Any]:
    """Lock manager access for current session."""
    request.session.pop("is_manager", None)
    return {"success": True, "is_manager": False}


# ---------------------------------------------------------------------
# Member Assigned Tasks Endpoints (Visible on Member Dashboard)
# ---------------------------------------------------------------------


@router.get("/me/tasks")
def api_my_tasks(session: DbSession, member: CurrentMember) -> dict[str, Any]:
    """List all tasks assigned to the authenticated team member."""
    tasks = (
        session.execute(
            select(TeamTask)
            .where(
                TeamTask.team_id == member.team_id,
                TeamTask.assigned_to_id == member.id,
            )
            .order_by(TeamTask.created_at.desc())
        )
        .scalars()
        .all()
    )
    return {
        "tasks": [_format_task(t) for t in tasks],
        "member": _format_member(member),
    }


@router.patch("/me/tasks/{task_id}")
def api_update_my_task(
    task_id: str,
    payload: MemberTaskUpdatePayload,
    session: DbSession,
    member: CurrentMember,
    clock: AppClock,
) -> dict[str, Any]:
    """Allow an authenticated team member to update the status of their assigned task."""
    task = session.get(TeamTask, task_id)
    if not task or task.team_id != member.team_id or task.assigned_to_id != member.id:
        raise NotFoundError("Task not found or not assigned to you.")

    valid_statuses = ["pending", "in_progress", "completed", "blocked"]
    if payload.status not in valid_statuses:
        raise BadRequestError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    if payload.status == "completed" and task.status != "completed":
        task.completed_at = clock.now()
    elif payload.status != "completed":
        task.completed_at = None

    task.status = payload.status
    session.commit()
    session.refresh(task)
    return {
        "success": True,
        "task": _format_task(task),
    }


# ---------------------------------------------------------------------
# Manager Operations (Protected)
# ---------------------------------------------------------------------


@router.get("/manager/tasks")
def api_list_tasks(
    session: DbSession, member: CurrentMember, request: Request
) -> dict[str, Any]:
    """List all team tasks for the manager's team."""
    _ensure_manager(request)
    tasks = (
        session.execute(
            select(TeamTask)
            .where(TeamTask.team_id == member.team_id)
            .order_by(TeamTask.created_at.desc())
        )
        .scalars()
        .all()
    )
    return {
        "tasks": [_format_task(t) for t in tasks],
        "viewer": _format_member(member),
    }


@router.post("/manager/tasks")
def api_create_task(
    payload: TaskCreatePayload,
    session: DbSession,
    member: CurrentMember,
    request: Request,
) -> dict[str, Any]:
    """Create a new team task assigned to a team member."""
    _ensure_manager(request)
    title = payload.title.strip()
    if not title:
        raise BadRequestError("Task title cannot be empty.")

    assigned_member = None
    if payload.assigned_to_id:
        assigned_member = session.get(Member, payload.assigned_to_id)
        if not assigned_member or assigned_member.team_id != member.team_id:
            raise BadRequestError("Assigned member must belong to your team.")

    task = TeamTask(
        team_id=member.team_id,
        title=title,
        description=payload.description.strip(),
        assigned_to_id=assigned_member.id if assigned_member else None,
        created_by_id=member.id,
        status="pending",
        priority=(
            payload.priority
            if payload.priority in ["low", "medium", "high", "urgent"]
            else "medium"
        ),
        due_date=payload.due_date.strip() if payload.due_date else None,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return {
        "success": True,
        "task": _format_task(task),
    }


@router.patch("/manager/tasks/{task_id}")
def api_update_task(
    task_id: str,
    payload: TaskUpdatePayload,
    session: DbSession,
    member: CurrentMember,
    clock: AppClock,
    request: Request,
) -> dict[str, Any]:
    """Update task details, assignment, or completion status."""
    _ensure_manager(request)
    task = session.get(TeamTask, task_id)
    if not task or task.team_id != member.team_id:
        raise NotFoundError("Task not found on your team.")

    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise BadRequestError("Task title cannot be empty.")
        task.title = title

    if payload.description is not None:
        task.description = payload.description.strip()

    if payload.assigned_to_id is not None:
        if payload.assigned_to_id == "":
            task.assigned_to_id = None
        else:
            assigned_member = session.get(Member, payload.assigned_to_id)
            if not assigned_member or assigned_member.team_id != member.team_id:
                raise BadRequestError("Assigned member must belong to your team.")
            task.assigned_to_id = assigned_member.id

    if payload.status is not None:
        valid_statuses = ["pending", "in_progress", "completed", "blocked"]
        if payload.status not in valid_statuses:
            raise BadRequestError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        if payload.status == "completed" and task.status != "completed":
            task.completed_at = clock.now()
        elif payload.status != "completed":
            task.completed_at = None
        task.status = payload.status

    if payload.priority is not None:
        valid_priorities = ["low", "medium", "high", "urgent"]
        if payload.priority in valid_priorities:
            task.priority = payload.priority

    if payload.due_date is not None:
        task.due_date = payload.due_date.strip() if payload.due_date.strip() else None

    session.commit()
    session.refresh(task)
    return {
        "success": True,
        "task": _format_task(task),
    }


@router.delete("/manager/tasks/{task_id}")
def api_delete_task(
    task_id: str,
    session: DbSession,
    member: CurrentMember,
    request: Request,
) -> dict[str, Any]:
    """Delete a task from the team."""
    _ensure_manager(request)
    task = session.get(TeamTask, task_id)
    if not task or task.team_id != member.team_id:
        raise NotFoundError("Task not found on your team.")
    session.delete(task)
    session.commit()
    return {"success": True}


@router.post("/manager/members")
def api_add_member(
    payload: AddMemberPayload,
    session: DbSession,
    member: CurrentMember,
    request: Request,
) -> dict[str, Any]:
    """Add a new member to the manager's team. Appears immediately on the team page."""
    _ensure_manager(request)
    name = payload.name.strip()
    if not name:
        raise BadRequestError("Member name cannot be empty.")

    wanted = normalise_name(name)
    existing = (
        session.execute(select(Member).where(Member.team_id == member.team_id))
        .scalars()
        .all()
    )
    for m in existing:
        if normalise_name(m.display_name) == wanted and m.active:
            msg = f"Member '{m.display_name}' is already an active member of this team."
            raise BadRequestError(msg)
        elif normalise_name(m.display_name) == wanted and not m.active:
            m.active = True
            m.tz = payload.tz.strip() or m.tz
            session.commit()
            return {"success": True, "member": _format_member(m)}

    new_member = Member(
        team_id=member.team_id,
        display_name=name,
        tz=payload.tz.strip() or member.team.tz_default or "UTC",
        source_keys={"webform": name.lower().replace(" ", ".")},
    )
    session.add(new_member)
    session.commit()
    session.refresh(new_member)
    return {
        "success": True,
        "member": _format_member(new_member),
    }


@router.get("/manager/summary")
def api_manager_summary(
    session: DbSession,
    member: CurrentMember,
    clock: AppClock,
    request: Request,
    scope: str = "daily",
) -> dict[str, Any]:
    """Generate an end-of-day or project summary of tasks and submitted work."""
    _ensure_manager(request)
    team = member.team
    tasks = (
        session.execute(
            select(TeamTask)
            .where(TeamTask.team_id == member.team_id)
            .order_by(TeamTask.created_at.desc())
        )
        .scalars()
        .all()
    )

    total_tasks = len(tasks)
    completed_tasks = [t for t in tasks if t.status == "completed"]
    in_progress_tasks = [t for t in tasks if t.status == "in_progress"]
    blocked_tasks = [t for t in tasks if t.status == "blocked"]
    pending_tasks = [t for t in tasks if t.status == "pending"]

    cycles: list[StandupCycle]
    if scope == "daily":
        latest_cycle = session.execute(
            select(StandupCycle)
            .where(StandupCycle.team_id == member.team_id)
            .order_by(StandupCycle.local_date.desc())
        ).scalars().first()
        cycles = [latest_cycle] if latest_cycle else []
    else:
        cycles = list(
            session.execute(
                select(StandupCycle)
                .where(StandupCycle.team_id == member.team_id)
                .order_by(StandupCycle.local_date.desc())
                .limit(10)
            )
            .scalars()
            .all()
        )

    cycle_ids = [c.id for c in cycles]
    live_updates: list[Update] = []
    if cycle_ids:
        live_updates = list(session.execute(
            select(Update)
            .where(Update.cycle_id.in_(cycle_ids))
            .where(Update.is_live())
            .order_by(Update.captured_at.desc())
        ).scalars().all())

    team_members = (
        session.execute(
            select(Member).where(Member.team_id == member.team_id, Member.active.is_(True))
        )
        .scalars()
        .all()
    )

    member_breakdowns = []
    standup_blockers = []
    standup_progress = []

    for m in sorted(team_members, key=lambda x: x.display_name):
        m_tasks = [t for t in tasks if t.assigned_to_id == m.id]
        m_completed = [t for t in m_tasks if t.status == "completed"]
        m_in_prog = [t for t in m_tasks if t.status == "in_progress"]
        m_blocked = [t for t in m_tasks if t.status == "blocked"]

        m_update = next((u for u in live_updates if u.member_id == m.id), None)
        progress_text = ""
        blockers_text = ""
        plan_text = ""
        if m_update and m_update.raw_payload_json:
            progress_text = m_update.raw_payload_json.get("progress", "")
            blockers_text = m_update.raw_payload_json.get("blockers", "")
            plan_text = m_update.raw_payload_json.get("plan", "")

        if blockers_text and blockers_text.strip():
            standup_blockers.append(
                {"member_name": m.display_name, "blocker": blockers_text.strip()}
            )
        if progress_text and progress_text.strip():
            standup_progress.append(
                {"member_name": m.display_name, "progress": progress_text.strip()}
            )

        member_breakdowns.append({
            "member_id": m.id,
            "member_name": m.display_name,
            "tasks_total": len(m_tasks),
            "tasks_completed": len(m_completed),
            "tasks_in_progress": len(m_in_prog),
            "tasks_blocked": len(m_blocked),
            "latest_progress": progress_text,
            "latest_blockers": blockers_text,
            "latest_plan": plan_text,
        })

    rate = int(round(len(completed_tasks) / total_tasks * 100)) if total_tasks > 0 else 0
    headline = (
        f"{team.name} {'Daily' if scope == 'daily' else 'Project'} Summary: "
        f"{len(completed_tasks)} tasks completed ({rate}%), "
        f"{len(in_progress_tasks)} in progress, "
        f"{len(blocked_tasks) + len(standup_blockers)} active blockers."
    )

    return {
        "team_name": team.name,
        "scope": scope,
        "headline": headline,
        "generated_at": clock.now().isoformat(),
        "stats": {
            "total_tasks": total_tasks,
            "completed": len(completed_tasks),
            "in_progress": len(in_progress_tasks),
            "blocked": len(blocked_tasks),
            "pending": len(pending_tasks),
            "completion_rate": rate,
            "updates_submitted": len(live_updates),
        },
        "completed_tasks": [_format_task(t) for t in completed_tasks],
        "in_progress_tasks": [_format_task(t) for t in in_progress_tasks],
        "blocked_tasks": [_format_task(t) for t in blocked_tasks],
        "standup_progress": standup_progress,
        "standup_blockers": standup_blockers,
        "member_breakdowns": member_breakdowns,
    }


@router.post("/manager/team-code")
def api_update_team_code(
    payload: UpdateTeamCodePayload,
    session: DbSession,
    member: CurrentMember,
    request: Request,
) -> dict[str, Any]:
    """Set a custom team code (e.g. to sync local and deployed) or regenerate one."""
    _ensure_manager(request)
    team = session.get(Team, member.team_id)
    if team is None:
        raise NotFoundError("Team not found.")

    if payload.custom_code and payload.custom_code.strip():
        new_code = normalise_team_code(payload.custom_code.strip())
        if len(new_code) < 3:
            raise BadRequestError("Team code must be at least 3 characters.")
        existing = session.execute(
            select(Team).where(Team.join_code == new_code, Team.id != team.id)
        ).scalar_one_or_none()
        if existing:
            raise BadRequestError("That team code is already used by another team.")
        team.join_code = new_code
    else:
        team.join_code = generate_team_code(team.slug)

    session.commit()
    session.refresh(team)
    return {
        "success": True,
        "join_code": format_team_code(team.join_code),
        "raw_code": team.join_code,
    }
