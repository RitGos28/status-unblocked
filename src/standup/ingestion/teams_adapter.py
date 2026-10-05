"""Teams ingestion adapter.

Produces the identical ``RawSubmission`` the web form produces, from a
Microsoft 365 Agents SDK ``Activity`` instead of posted form fields. Everything
downstream of ``RawSubmission`` (normalizer, summarizer, validator, digest) is
unaware this update ever touched Teams.

This is the only other file, alongside ``api/teams_router.py``, permitted to
import the Agents SDK -- see CLAUDE.md's Teams invariant on keeping the blast
radius of a breaking SDK change to two files.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from microsoft_agents.activity import Activity

from standup.domain.enums import SourceKind
from standup.ingestion.base import FORM_FIELDS, RawSubmission, text_fields_from


def teams_user_key(activity: Activity) -> str:
    """The sender's stable Teams identity: aadObjectId, else the channel id."""
    from_property = activity.from_property
    return str(
        (from_property.aad_object_id if from_property else None)
        or (from_property.id if from_property else None)
        or ""
    ).strip()


class TeamsAdapter:
    """Turns a Teams ``Action.Submit`` activity into a canonical submission."""

    source_kind = SourceKind.TEAMS

    def to_raw_submission(self, activity: Activity, *, captured_at: datetime) -> RawSubmission:
        # ``captured_at`` is the server clock (AppClock), not activity.timestamp
        # (when Teams says the message was sent) -- cycle-bucketing must use the
        # same clock every adapter uses, exactly like WebFormAdapter's caller
        # passes ``now`` rather than trusting a client-supplied timestamp.
        external_user_key = teams_user_key(activity)

        value: dict[str, Any] = activity.value if isinstance(activity.value, dict) else {}

        return RawSubmission(
            source_kind=self.source_kind,
            external_user_key=external_user_key,
            text_fields=text_fields_from(value),
            captured_at=captured_at,
            # A 1:1 Teams chat's conversation id is in ``a:`` form -- no
            # permalink is constructible from it. Every identifier Teams gives
            # us is recorded verbatim anyway, so the evidence view is the
            # citation target and the reason a permalink is absent is never a
            # silent null (see Update.permalink_reason).
            source_ids={
                "adapter": "teams",
                "conversation_id": activity.conversation.id if activity.conversation else "",
                "channel_id": str(activity.channel_id) if activity.channel_id else "",
                "service_url": activity.service_url or "",
                "activity_id": activity.id or "",
            },
            raw_payload=activity.model_dump(mode="json"),
        )


# --- Scope gate -----------------------------------------------------------
# The bot reads only what is addressed to it: a card submission or a typed
# command in a 1:1 chat, or a channel message that explicitly @mentions it.
# Anything else is refused before it reaches ingest() and counted, with no
# content recorded (see db.models.IngestRejection).

STANDUP_FIELDS = frozenset(FORM_FIELDS)


ScopeKind = Literal["card_submit", "command", "mention", "ignored", "rejected"]


@dataclass(frozen=True)
class ScopeDecision:
    """What the bot may do with one activity.

    ``kind`` is one of:
      - "card_submit": a standup card submitted in a 1:1 chat. Ingest it.
      - "command": text typed in a 1:1 chat ("standup", "link <code>", ...).
      - "mention": a channel or group message that @mentions the bot. Reply
        only; channel text is never ingested.
      - "ignored": not a message (install, typing, ...). Neither handled nor
        counted.
      - "rejected": a message outside scope. Count it, read nothing.
    """

    kind: ScopeKind
    conversation_type: str
    reason: str = ""
    text: str = ""


def classify_scope(activity: Activity) -> ScopeDecision:
    conversation = activity.conversation
    conversation_type = (
        (conversation.conversation_type if conversation else None) or "personal"
    )

    if activity.type != "message":
        return ScopeDecision("ignored", conversation_type)

    value = activity.value if isinstance(activity.value, dict) else None
    is_card_submit = value is not None and bool(STANDUP_FIELDS & value.keys())

    if conversation_type == "personal":
        if is_card_submit:
            return ScopeDecision("card_submit", conversation_type)
        return ScopeDecision(
            "command", conversation_type, text=(activity.text or "").strip()
        )

    if is_card_submit:
        # We only ever post the standup card into 1:1 chats, so a submission
        # from a channel or group is not one of ours.
        return ScopeDecision("rejected", conversation_type, reason="card_submit_outside_personal")
    if activity.is_recipient_mentioned():
        return ScopeDecision("mention", conversation_type)
    return ScopeDecision("rejected", conversation_type, reason="unaddressed_group_message")


_CARD_LABELS = {"progress": "Progress", "blockers": "Blockers", "plan": "Today"}


def standup_card() -> dict[str, Any]:
    """The Adaptive Card that collects one update.

    Structured fields are what keep the rules summarizer faithful: whether a
    line is a blocker is the author's statement, not an inference.
    """
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [
            {"type": "TextBlock", "text": "Today's update", "weight": "Bolder", "size": "Medium"},
            {
                "type": "TextBlock",
                "text": "Only what you type here is stored. Your team sees it equally.",
                "isSubtle": True,
                "wrap": True,
            },
            *(
                {"type": "Input.Text", "id": name, "label": _CARD_LABELS[name], "isMultiline": True}
                for name in FORM_FIELDS
            ),
        ],
        "actions": [{"type": "Action.Submit", "title": "Submit update"}],
    }
