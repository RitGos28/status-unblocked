"""Web-form ingestion adapter.

Zero external dependencies, so the full pipeline is exercisable and demoable
whatever a Teams tenant's sideloading policy turns out to be. The Teams adapter
in week 2 produces the identical ``RawSubmission``.
"""

from datetime import UTC, datetime
from typing import Any

from standup.domain.enums import ItemKind, SourceKind
from standup.ingestion.base import RawSubmission


class WebFormAdapter:
    """Turns posted form fields into a canonical submission."""

    source_kind = SourceKind.WEBFORM

    def to_raw_submission(self, payload: dict[str, Any]) -> RawSubmission:
        captured_raw = payload.get("captured_at")
        captured_at = (
            captured_raw if isinstance(captured_raw, datetime) else datetime.now(UTC)
        )

        return RawSubmission(
            source_kind=self.source_kind,
            external_user_key=str(payload.get("member_id", "")).strip(),
            text_fields={
                ItemKind.PROGRESS: str(payload.get("progress", "") or ""),
                ItemKind.BLOCKER: str(payload.get("blockers", "") or ""),
                ItemKind.PLAN: str(payload.get("plan", "") or ""),
            },
            captured_at=captured_at,
            # A web submission has no platform message to link to; the evidence
            # view is the citation target. Recorded explicitly rather than left
            # as a silent null.
            source_ids={"adapter": "webform"},
            raw_payload=dict(payload),
        )
