"""The ingestion seam.

Every source — the web form now, Microsoft Teams in week 2 — normalises to a
single ``RawSubmission``. Everything downstream (normalizer, summarizer,
validator, tracker, digest) sees only canonical records and has no idea which
platform a update arrived from.

This is what makes Teams optional: if a tenant blocks sideloading, the web
adapter still exercises the entire pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from standup.domain.enums import ItemKind, SourceKind


@dataclass(frozen=True)
class RawSubmission:
    """One person's standup answers, exactly as they typed them."""

    source_kind: SourceKind
    # Identity as the source knows it: a Teams aadObjectId, or a web handle.
    external_user_key: str
    # ItemKind -> what they wrote for it. Structured fields are what keep the
    # rules summarizer faithful: we never have to infer "is this a blocker",
    # because the person answered that question by choosing a field.
    text_fields: dict[ItemKind, str]
    captured_at: datetime
    source_ids: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any(v.strip() for v in self.text_fields.values())


class IngestionAdapter(Protocol):
    """Turns a platform-specific payload into a ``RawSubmission``."""

    source_kind: SourceKind

    def to_raw_submission(self, payload: Any) -> RawSubmission: ...
