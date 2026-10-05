"""The summarizer seam — and the prompt boundary.

``SummaryRequest`` is the *entire* input surface of any summarizer. No ORM
objects, no database session, no email addresses, no unredacted text, and
nothing belonging to a member who has not opted into external processing.

That matters because when the LLM implementation lands, whatever crosses this
line is what leaves the building. Keeping the boundary narrow is cheaper than
auditing a prompt builder that can reach anywhere.

Why extractive first: verbatim extraction has a near-zero hallucination rate,
while generative summarization fabricates in roughly 15% of outputs even under
strong prompting. For a digest whose value *is* faithfulness, that rate on
blockers is disqualifying. So the rules engine ships first, the validator is
built against it, and any future model must clear the same bar.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from standup.domain.enums import ClaimKind, ItemKind


@dataclass(frozen=True)
class SourceDoc:
    """One citable unit of evidence, as the summarizer sees it."""

    id: str
    member_id: str
    member_name: str
    kind: ItemKind
    text: str
    captured_at: datetime
    evidence_url: str
    permalink: str | None = None
    normalized_key: str = ""
    entity_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class SummaryRequest:
    cycle_date: date
    team_name: str
    sources: tuple[SourceDoc, ...]
    # Blockers still open from earlier cycles, for carry-over detection.
    prior_open_blockers: tuple[SourceDoc, ...] = ()
    max_claims_per_section: int = 50


@dataclass(frozen=True)
class Citation:
    """A pointer into a source's text.

    ``quote`` must equal ``source.text[start:end]``. Validator rule V3 enforces
    it, which is what stops a paraphrase being passed off as a quotation.
    """

    source_id: str
    quote: str
    start: int
    end: int


@dataclass(frozen=True)
class Claim:
    """One line of the digest, plus the evidence for it."""

    kind: ClaimKind
    member_id: str
    member_name: str
    text: str
    citations: tuple[Citation, ...]
    # True when text is a verbatim span. The rules engine only ever emits
    # extractive claims; an LLM may not, and V8 guards length inflation there.
    extractive: bool = True
    matched_rule: str = ""


@dataclass(frozen=True)
class SummaryResult:
    claims: tuple[Claim, ...]
    summarizer_name: str
    summarizer_version: str
    notes: dict[str, str] = field(default_factory=dict)
    # Claims cut by ``max_claims_per_section``. Reported, never silently lost:
    # this is distinct from "withheld" (failed validation or author removal).
    truncated: int = 0


class Summarizer(Protocol):
    """Implemented by RulesSummarizer, the only implementation.

    A summarizer must never call the validator itself — ``service.py`` runs it
    afterwards, so the check cannot be bypassed by the next implementation.
    """

    name: str
    version: str

    def summarize(self, req: SummaryRequest) -> SummaryResult: ...
