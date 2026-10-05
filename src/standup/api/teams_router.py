"""The Teams bot.

``POST /api/messages`` receives Bot Framework activities through the
Microsoft 365 Agents SDK. This file and ``ingestion/teams_adapter.py`` are the
only two allowed to import that SDK (invariant 9), so a breaking SDK release
touches two files. import-linter enforces it.

What the bot does, and nothing more:
- in a 1:1 chat, ``standup`` sends the update card; submitting it goes through
  the same ``ingest()`` as the web form
- ``link <code>`` ties this Teams account to a member, using a short-lived code
  the member gets from ``/me/teams`` while signed in to the web app
- a channel message that @mentions the bot gets a pointer to the 1:1 chat;
  channel text is never ingested
- anything else is refused and counted as a content-free ``IngestRejection``

The bot asks Microsoft Graph for nothing (the manifest requests no
permissions): who someone is comes from the link code, never from a lookup.

The route exists only when ``STANDUP_TEAMS_ENABLED=true``; otherwise it 404s.
"""

import os
from typing import Any, Protocol

from fastapi import APIRouter, FastAPI, Request, Response
from microsoft_agents.activity import Activity, ConversationReference, load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.core import CardFactory, MessageFactory
from microsoft_agents.hosting.core.authorization import ClaimsIdentity
from microsoft_agents.hosting.fastapi import CloudAdapter, jwt_authorization_decorator
from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.auth.tokens import read_teams_link_code, teams_link_state
from standup.config import TEAMS_APP_ID_ENV, teams_anonymous_allowed
from standup.db.models import IngestRejection, Member
from standup.deps import AppClock, AppSettings, DbSession
from standup.domain.errors import EmptySubmissionError
from standup.domain.models import Clock
from standup.ingestion.permalink import teams_permalink
from standup.ingestion.service import ingest
from standup.ingestion.teams_adapter import (
    ScopeDecision,
    TeamsAdapter,
    classify_scope,
    standup_card,
    teams_user_key,
)
from standup.logging_conf import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["teams"])

HELP_TEXT = (
    "Type **standup** to file today's update. "
    "To connect this Teams account, sign in to the web app, open /me/teams, "
    "and send me **link** followed by the code it shows."
)
MENTION_REPLY = (
    "I don't read channel conversations. Message me in a 1:1 chat and type "
    "**standup** to file your update."
)


class ReplyContext(Protocol):
    """The slice of TurnContext the bot uses, so tests can pass a fake."""

    @property
    def activity(self) -> Activity: ...

    async def send_activity(self, activity_or_text: Any) -> Any: ...


class StandupAgent:
    """Handles one turn. Built per request, with that request's DB session."""

    def __init__(self, *, session: Session, clock: Clock, secret_key: str, base_url: str):
        self._session = session
        self._clock = clock
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")

    async def on_turn(self, context: ReplyContext) -> None:
        activity = context.activity
        decision = classify_scope(activity)

        if decision.kind == "ignored":
            return
        if decision.kind == "rejected":
            self._record_rejection(decision)
            return
        if decision.kind == "mention":
            await context.send_activity(MENTION_REPLY)
            return
        self._remember_conversation(activity)
        if decision.kind == "card_submit":
            await self._handle_submit(context, activity)
            return
        await self._handle_command(context, activity, decision.text)

    # -- handlers ---------------------------------------------------------

    async def _handle_command(self, context: ReplyContext, activity: Activity, text: str) -> None:
        command, _, argument = text.partition(" ")
        command = command.lower()
        if command in {"standup", "update"}:
            card = CardFactory.adaptive_card(standup_card())
            await context.send_activity(MessageFactory.attachment(card))
        elif command == "link":
            await context.send_activity(self._link(activity, argument.strip()))
            self._remember_conversation(activity)
        else:
            await context.send_activity(HELP_TEXT)

    async def _handle_submit(self, context: ReplyContext, activity: Activity) -> None:
        member = self._member_for(activity)
        if member is None:
            await context.send_activity(
                "This Teams account isn't linked to a member yet. Sign in to the web app, "
                f"open {self._base_url}/me/teams, and send me **link** with the code it shows."
            )
            return

        now = self._clock.now()
        submission = TeamsAdapter().to_raw_submission(activity, captured_at=now)
        conversation_id = activity.conversation.id if activity.conversation else ""
        permalink, reason = teams_permalink(conversation_id, activity.id or "")
        try:
            ingest(
                self._session,
                submission,
                member,
                now,
                permalink=permalink,
                permalink_reason=reason,
            )
        except EmptySubmissionError:
            await context.send_activity("The card was empty, so nothing was recorded.")
            return

        await context.send_activity(
            f"Recorded for {member.team.name}. Submitting again today replaces it. "
            f"Digests: {self._base_url}/digests"
        )

    def _link(self, activity: Activity, code: str) -> str:
        invalid = "That code is invalid or has expired. Get a fresh one from /me/teams."
        user_key = teams_user_key(activity)
        signed = read_teams_link_code(self._secret_key, code) if code else None
        member = self._session.get(Member, signed[0]) if signed else None
        if not user_key or signed is None or member is None or not member.active:
            return invalid
        if member.teams_aad_id == user_key:
            return f"You're already linked as {member.display_name}."
        # Single use: the code signed the link state at issue. Once used, or
        # once the member links again some other way, it no longer matches.
        if signed[1] != teams_link_state(member.teams_aad_id):
            log.info("teams.link_code_reused", member_id=member.id)
            return invalid

        holder = self._session.execute(
            select(Member).where(Member.teams_aad_id == user_key)
        ).scalar_one_or_none()
        if holder is not None and holder.id != member.id:
            return "This Teams account is already linked to another member."

        member.teams_aad_id = user_key
        self._session.flush()
        log.info("teams.linked", member_id=member.id)
        return (
            f"Linked. You're {member.display_name} on {member.team.name}. "
            "Type **standup** to begin."
        )

    # -- helpers ----------------------------------------------------------

    def _member_for(self, activity: Activity) -> Member | None:
        user_key = teams_user_key(activity)
        if not user_key:
            return None
        return self._session.execute(
            select(Member).where(Member.teams_aad_id == user_key).where(Member.active.is_(True))
        ).scalar_one_or_none()

    def _remember_conversation(self, activity: Activity) -> None:
        """Keep the latest 1:1 conversation reference for a linked member, so
        the scheduler can tell them their digest is ready."""
        member = self._member_for(activity)
        if member is None:
            return
        reference = activity.get_conversation_reference()
        member.teams_conversation_ref = reference.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )

    def _record_rejection(self, decision: ScopeDecision) -> None:
        self._session.add(
            IngestRejection(
                at=self._clock.now(),
                source="teams",
                reason=decision.reason,
                conversation_type=decision.conversation_type,
            )
        )
        log.info(
            "ingest.scope_violation",
            source="teams",
            reason=decision.reason,
            conversation_type=decision.conversation_type,
        )


@router.post("/api/messages")
@jwt_authorization_decorator  # type: ignore[misc]  # the SDK ships it untyped
async def messages(
    request: Request, session: DbSession, clock: AppClock, settings: AppSettings
) -> Response:
    """Bot Framework endpoint. The decorator verifies the caller's token."""
    agent = StandupAgent(
        session=session,
        clock=clock,
        secret_key=settings.secret_key.get_secret_value(),
        base_url=settings.base_url or str(request.base_url),
    )
    response = await request.app.state.teams_adapter.process(request, agent)
    return response or Response(status_code=202)


class TeamsNotifier:
    """Sends a proactive 1:1 message, for the scheduler's digest notice."""

    def __init__(self, adapter: CloudAdapter, app_id: str, *, anonymous: bool = False):
        self._adapter = adapter
        self._app_id = app_id
        self._anonymous = anonymous

    async def notify(self, conversation_ref: dict[str, Any], text: str) -> None:
        reference = ConversationReference.model_validate(conversation_ref)
        continuation = reference.get_continuation_activity()

        async def send(context: Any) -> None:
            await context.send_activity(text)

        if self._anonymous:
            # Local demo / Agents Playground: an identity with no claims makes
            # the SDK use its anonymous token provider. The default path below
            # adds app-id claims, so MSAL insists on a tenant id and fails.
            await self._adapter.continue_conversation_with_claims(
                ClaimsIdentity(), continuation, send
            )
        else:
            await self._adapter.continue_conversation(self._app_id, continuation, send)


def _build_adapter() -> tuple[CloudAdapter, Any]:
    config = load_configuration_from_env(os.environ)
    connection_manager = MsalConnectionManager(**config)
    return CloudAdapter(connection_manager=connection_manager), connection_manager


def _notifier(adapter: CloudAdapter) -> TeamsNotifier:
    return TeamsNotifier(
        adapter, os.environ.get(TEAMS_APP_ID_ENV, ""), anonymous=teams_anonymous_allowed()
    )


def build_teams_notifier() -> TeamsNotifier:
    """A notifier with its own adapter, for use outside the web app (scripts/tick)."""
    adapter, _ = _build_adapter()
    return _notifier(adapter)


def mount_teams(app: FastAPI) -> None:
    """Wire the SDK from its CONNECTIONS__ environment variables and add the route."""
    adapter, connection_manager = _build_adapter()
    app.state.teams_adapter = adapter
    app.state.teams_notifier = _notifier(adapter)
    # Read by jwt_authorization_decorator to validate inbound tokens.
    app.state.agent_configuration = connection_manager.get_default_connection_configuration()
    app.include_router(router)
