"""Faithfulness validator.

Runs in ``service.py`` **after** any summarizer, never inside one, so it cannot
be bypassed by the next implementation. The rules engine passes it trivially;
that is the point — the bar is set against output that is correct by
construction, so a future LLM has to meet the same standard rather than a
softer one written for it.

Rules implemented here (week 1-2):

* **V1** every claim carries at least one citation
* **V2** every cited ``source_id`` exists in the request (kills fabricated ids)
* **V3** ``quote == source.text[start:end]`` (kills paraphrase-as-quote)
* **V4** numbers in the claim appear in a cited quote, or are derivable
* **V5** entity refs (#123, URLs, @handles) appear in a cited quote
* **V6** the claim's member matches every cited source (no cross-attribution)
* **V8** length-inflation guard for abstractive claims

V7 (no source outside consented/visible scope) lands in week 4 with the
consent and visibility model.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from standup.summarize.base import Claim, SummaryRequest, SummaryResult

# Derived values a claim may state without them appearing verbatim in a source.
DERIVED_METRICS = frozenset({"days_open", "source_count"})

_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")
def _entity_token(entity: str) -> str:
    """An entity as written, minus sentence punctuation the pattern swallowed:
    "@anabel." at the end of a sentence is the handle "@anabel"."""
    return entity.rstrip(".,;:!?)")


_ENTITY = re.compile(r"(?:\b[\w.-]+/[\w.-]+)?#\d+|https?://\S+|@[\w.-]+|\b[A-Z][A-Z0-9]{1,9}-\d+\b")

# How much longer a claim may be than the evidence supporting it.
LENGTH_INFLATION_FACTOR = 1.3


def _canonical(text: str) -> str:
    """NFKC-normalise and collapse whitespace, so a quote is not rejected for
    a non-breaking space or a smart quote round-trip."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


@dataclass(frozen=True)
class Violation:
    rule: str
    claim_text: str
    detail: str


@dataclass
class ValidationReport:
    checked: int = 0
    passed: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def withheld(self) -> int:
        return self.checked - self.passed

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, object]:
        return {
            "checked": self.checked,
            "passed": self.passed,
            "withheld": self.withheld,
            "violations": [
                {"rule": v.rule, "claim": v.claim_text[:200], "detail": v.detail}
                for v in self.violations
            ],
        }


class FaithfulnessValidator:
    """Checks a ``SummaryResult`` against the sources it was built from."""

    def validate_claim(
        self, claim: Claim, sources_by_id: dict[str, object]
    ) -> list[Violation]:
        from standup.summarize.base import SourceDoc  # local: keeps the seam narrow

        violations: list[Violation] = []
        text = claim.text

        # V1 - every claim is cited.
        if not claim.citations:
            violations.append(Violation("V1", text, "claim has no citations"))
            return violations

        cited_quotes: list[str] = []

        for citation in claim.citations:
            source = sources_by_id.get(citation.source_id)

            # V2 - the cited source actually exists.
            if source is None:
                violations.append(
                    Violation("V2", text, f"unknown source_id {citation.source_id!r}")
                )
                continue

            assert isinstance(source, SourceDoc)

            # V3 - the quote is really a substring at those offsets.
            actual = source.text[citation.start : citation.end]
            if _canonical(actual) != _canonical(citation.quote):
                violations.append(
                    Violation(
                        "V3",
                        text,
                        f"quote does not match source[{citation.start}:{citation.end}]: "
                        f"{citation.quote!r} != {actual!r}",
                    )
                )
                continue

            # V6 - no cross-attribution.
            if source.member_id != claim.member_id:
                violations.append(
                    Violation(
                        "V6",
                        text,
                        f"claim attributed to {claim.member_id} cites "
                        f"{source.member_id}'s source",
                    )
                )

            cited_quotes.append(citation.quote)

        if not cited_quotes:
            return violations

        evidence = " ".join(_canonical(q) for q in cited_quotes)
        canonical_text = _canonical(text)

        # V4 and V5 compare whole tokens, never substrings: "1" must not pass
        # because the evidence says "10", nor "#1" because it says "#12".
        evidence_numbers = set(_NUMBER.findall(evidence))
        evidence_entities = {_entity_token(e) for e in _ENTITY.findall(evidence)}

        # V4 - every number is supported by the evidence.
        for number in _NUMBER.findall(canonical_text):
            if number not in evidence_numbers:
                violations.append(
                    Violation("V4", text, f"number {number!r} appears in no cited source")
                )

        # V5 - every entity reference is supported by the evidence.
        for entity in _ENTITY.findall(canonical_text):
            if _entity_token(entity) not in evidence_entities:
                violations.append(
                    Violation("V5", text, f"entity {entity!r} appears in no cited source")
                )

        # V8 - an abstractive claim may not balloon beyond its evidence.
        if not claim.extractive:
            budget = LENGTH_INFLATION_FACTOR * sum(len(q) for q in cited_quotes)
            if len(text) > budget:
                violations.append(
                    Violation(
                        "V8",
                        text,
                        f"claim length {len(text)} exceeds evidence budget {budget:.0f}",
                    )
                )

        return violations

    def validate(
        self, result: SummaryResult, request: SummaryRequest
    ) -> tuple[tuple[Claim, ...], ValidationReport]:
        """Return the claims that survive, plus a report of what did not."""
        sources_by_id: dict[str, object] = {s.id: s for s in request.sources}
        for prior in request.prior_open_blockers:
            sources_by_id.setdefault(prior.id, prior)

        report = ValidationReport()
        kept: list[Claim] = []

        for claim in result.claims:
            report.checked += 1
            violations = self.validate_claim(claim, sources_by_id)
            if violations:
                report.violations.extend(violations)
            else:
                report.passed += 1
                kept.append(claim)

        return tuple(kept), report
