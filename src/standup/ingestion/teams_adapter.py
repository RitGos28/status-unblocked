"""Teams ingestion adapter.

Produces the identical ``RawSubmission`` the web form produces, from a
Microsoft 365 Agents SDK ``Activity`` instead of posted form fields. Everything
downstream of ``RawSubmission`` (normalizer, summarizer, validator, digest) is
unaware this update ever touched Teams.

This is the only other file, alongside ``api/teams_router.py``, permitted to
import the Agents SDK -- see CLAUDE.md's Teams invariant on keeping the blast
radius of a breaking SDK change to two files.
"""

from datetime import datetime
from typing import Any

from microsoft_agents.activity import Activity

from standup.domain.enums import ItemKind, SourceKind
from standup.ingestion.base import RawSubmission


class TeamsAdapter:
    """Turns a Teams ``Action.Submit`` activity into a canonical submission."""

    source_kind = SourceKind.TEAMS

    def to_raw_submission(self, activity: Activity, *, captured_at: datetime) -> RawSubmission:
        # ``captured_at`` is the server clock (AppClock), not activity.timestamp
        # (when Teams says the message was sent) -- cycle-bucketing must use the
        # same clock every adapter uses, exactly like WebFormAdapter's caller
        # passes ``now`` rather than trusting a client-supplied timestamp.
        from_property = activity.from_property
        external_user_key = str(
            (from_property.aad_object_id if from_property else None)
            or (from_property.id if from_property else None)
            or ""
        ).strip()

        value: dict[str, Any] = activity.value if isinstance(activity.value, dict) else {}

        return RawSubmission(
            source_kind=self.source_kind,
            external_user_key=external_user_key,
            text_fields={
                ItemKind.PROGRESS: str(value.get("progress", "") or ""),
                ItemKind.BLOCKER: str(value.get("blockers", "") or ""),
                ItemKind.PLAN: str(value.get("plan", "") or ""),
            },
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
