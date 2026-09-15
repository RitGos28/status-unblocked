"""Extractive, deterministic summarizer.

Faithfulness here is structural rather than aspirational:

* **Kind** comes from the form field the person filled in, not from inference.
* **Claim text is the verbatim span**, never a paraphrase, so ``extractive`` is
  always true and V3 holds by construction.
* Any "summarisation" comes from *selection and ordering*, not rewriting.

Free-text blocker detection exists only as a secondary path, for updates that
arrive without structure (a plain Teams message rather than a card). Matches
record ``matched_rule`` so a classification is always explainable.
"""

import re

from standup.domain.enums import ClaimKind, ItemKind
from standup.summarize.base import (
    Citation,
    Claim,
    SummaryRequest,
    SummaryResult,
)

_KIND_TO_CLAIM: dict[ItemKind, ClaimKind] = {
    ItemKind.PROGRESS: ClaimKind.PROGRESS,
    ItemKind.BLOCKER: ClaimKind.BLOCKER,
    ItemKind.PLAN: ClaimKind.PLAN,
}

# Markers that suggest a blocker in unstructured text.
_BLOCKER_MARKERS = (
    "blocked",
    "blocker",
    "waiting on",
    "waiting for",
    "stuck",
    "can't",
    "cannot",
    "need help",
    "needs help",
    "depends on",
    "no access",
    "needs review",
    "pending approval",
    "held up",
)

# Phrases that cancel a marker. Without these, "no blockers" reads as a blocker
# — the single most common false positive in this class of tool.
_NEGATIONS = (
    "no blockers",
    "no blocker",
    "not blocked",
    "nothing blocking",
    "no issues",
    "unblocked",
    "not stuck",
    "no longer blocked",
    "nothing is blocking",
)


def looks_like_blocker(text: str) -> tuple[bool, str]:
    """Return (is_blocker, matched_rule). Negations win over markers."""
    lowered = text.lower()

    for negation in _NEGATIONS:
        if negation in lowered:
            return False, f"negation:{negation}"

    for marker in _BLOCKER_MARKERS:
        if re.search(rf"\b{re.escape(marker)}", lowered):
            return True, f"marker:{marker}"

    return False, ""


class RulesSummarizer:
    """Deterministic extractive summarizer. No network, no model, no cost."""

    name = "rules"
    version = "0.1.0"

    def summarize(self, req: SummaryRequest) -> SummaryResult:
        claims: list[Claim] = []

        for source in req.sources:
            text = source.text.strip()
            if not text:
                continue

            claim_kind = _KIND_TO_CLAIM[source.kind]
            matched_rule = f"field:{source.kind.value}"

            # Secondary path: a line filed under progress/plan that plainly
            # announces a blocker is promoted, with the reason recorded.
            if source.kind is not ItemKind.BLOCKER:
                is_blocker, rule = looks_like_blocker(text)
                if is_blocker:
                    claim_kind = ClaimKind.BLOCKER
                    matched_rule = f"promoted:{rule}"
            else:
                # A blocker field saying "no blockers" is not a blocker.
                _, rule = looks_like_blocker(text)
                if rule.startswith("negation:"):
                    continue

            # The claim IS the span. start/end index into source.text, so
            # quote == source.text[start:end] holds trivially.
            start = source.text.index(text)
            end = start + len(text)

            claims.append(
                Claim(
                    kind=claim_kind,
                    member_id=source.member_id,
                    member_name=source.member_name,
                    text=text,
                    citations=(
                        Citation(
                            source_id=source.id,
                            quote=text,
                            start=start,
                            end=end,
                        ),
                    ),
                    extractive=True,
                    matched_rule=matched_rule,
                )
            )

        claims = self._order(claims, req.max_claims_per_section)

        return SummaryResult(
            claims=tuple(claims),
            summarizer_name=self.name,
            summarizer_version=self.version,
            notes={"sources": str(len(req.sources)), "claims": str(len(claims))},
        )

    @staticmethod
    def _order(claims: list[Claim], cap: int) -> list[Claim]:
        """Blockers first — they are the reason anyone reads a digest.

        Within a section, group by member so a reader can find their own name.
        """
        section_rank = {
            ClaimKind.CARRYOVER: 0,
            ClaimKind.BLOCKER: 1,
            ClaimKind.PROGRESS: 2,
            ClaimKind.PLAN: 3,
        }
        ordered = sorted(claims, key=lambda c: (section_rank[c.kind], c.member_name))

        capped: list[Claim] = []
        seen: dict[ClaimKind, int] = {}
        for claim in ordered:
            count = seen.get(claim.kind, 0)
            if count >= cap:
                continue
            seen[claim.kind] = count + 1
            capped.append(claim)
        return capped
