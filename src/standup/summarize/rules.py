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
    SourceDoc,
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


# What people type into the Blockers box to mean "nothing". Compared after
# lowercasing and dropping punctuation other than "/" and "-".
_EMPTY_ANSWERS = frozenset(
    {
        "none", "n/a", "na", "nothing", "-", "--", "nope", "nil", "no",
        "none today", "nothing today", "nothing yet", "none so far", "nothing so far",
    }
)

# Clause boundaries. A negation cancels only the markers in its own clause:
# "no blockers on the API, but stuck on the migration" still has a blocker.
_CLAUSE_SPLIT = re.compile(r"[,;]|\b(?:but|however|although|though)\b")


# A line that is only a section heading ("Blockers:", "Today") carries no
# content. People type them when pasting notes into one box; they must not
# become claims, and above all must not be promoted to blockers.
_BARE_HEADING = re.compile(r"^\s*(?:progress|blockers?|today|plan)\s*:?\s*$", re.IGNORECASE)


def is_bare_heading(text: str) -> bool:
    return bool(_BARE_HEADING.match(text))


def is_empty_answer(text: str) -> bool:
    """True for answers like "None", "N/A" or "-" that mean "no blocker"."""
    cleaned = re.sub(r"[^\w/\-\s]", "", text.lower())
    return " ".join(cleaned.split()) in _EMPTY_ANSWERS


def looks_like_blocker(text: str) -> tuple[bool, str]:
    """Return (is_blocker, matched_rule).

    Evaluated clause by clause, and within a clause negations win over markers.
    When nothing marks a blocker, the rule names the first negation seen, if
    any, so a Blockers field that says "not blocked" can be dropped.
    """
    negation_rule = ""
    for clause in _CLAUSE_SPLIT.split(text.lower()):
        negation = next((n for n in _NEGATIONS if n in clause), None)
        if negation is not None:
            negation_rule = negation_rule or f"negation:{negation}"
            continue
        for marker in _BLOCKER_MARKERS:
            if re.search(rf"\b{re.escape(marker)}", clause):
                return True, f"marker:{marker}"
    return False, negation_rule


def _earliest_same_blocker(
    source: SourceDoc, prior: tuple[SourceDoc, ...]
) -> SourceDoc | None:
    """The earliest earlier blocker by the same member with the same key."""
    if not source.normalized_key:
        return None
    matches = [
        p
        for p in prior
        if p.member_id == source.member_id and p.normalized_key == source.normalized_key
    ]
    return min(matches, key=lambda p: p.captured_at) if matches else None


def classify(kind: ItemKind, text: str) -> tuple[ClaimKind | None, str]:
    """Which digest section a line belongs in, and why; None if it is not reported.

    The one classification policy. RulesSummarizer applies it, and the
    validator (V10) holds every summarizer to it, so a section can never
    depend on which implementation built the digest.
    """
    text = text.strip()
    if not text or is_bare_heading(text):
        return None, "empty"
    if kind is not ItemKind.BLOCKER:
        # Secondary path: a line filed under progress/plan that plainly
        # announces a blocker is promoted, with the reason recorded.
        is_blocker, rule = looks_like_blocker(text)
        if is_blocker:
            return ClaimKind.BLOCKER, f"promoted:{rule}"
        return _KIND_TO_CLAIM[kind], f"field:{kind.value}"
    # A blocker field saying "None", or "no blockers", is not a blocker. One
    # that also names a real blocker in another clause ("no blockers on X, but
    # stuck on Y") is.
    if is_empty_answer(text):
        return None, "empty-answer"
    is_blocker, rule = looks_like_blocker(text)
    if not is_blocker and rule.startswith("negation:"):
        return None, rule
    return ClaimKind.BLOCKER, f"field:{kind.value}"


class RulesSummarizer:
    """Deterministic extractive summarizer. No network, no model, no cost."""

    name = "rules"
    version = "0.1.0"

    def summarize(self, req: SummaryRequest) -> SummaryResult:
        claims: list[Claim] = []

        for source in req.sources:
            classified, matched_rule = classify(source.kind, source.text)
            if classified is None:
                continue
            claim_kind: ClaimKind = classified
            text = source.text.strip()

            # The claim IS the span. start/end index into source.text, so
            # quote == source.text[start:end] holds trivially.
            start = source.text.index(text)
            end = start + len(text)
            citations = [Citation(source_id=source.id, quote=text, start=start, end=end)]

            # Carry-over: the same person reported the same blocker on an
            # earlier day. The claim keeps today's words verbatim (invariant 4)
            # and also cites the earliest earlier report, so both days resolve.
            if claim_kind is ClaimKind.BLOCKER:
                earlier = _earliest_same_blocker(source, req.prior_open_blockers)
                if earlier is not None:
                    quote = earlier.text.strip()
                    offset = earlier.text.index(quote)
                    citations.append(
                        Citation(
                            source_id=earlier.id, quote=quote, start=offset, end=offset + len(quote)
                        )
                    )
                    claim_kind = ClaimKind.CARRYOVER
                    matched_rule = (
                        f"{matched_rule};carryover:{earlier.captured_at.date().isoformat()}"
                    )

            claims.append(
                Claim(
                    kind=claim_kind,
                    member_id=source.member_id,
                    member_name=source.member_name,
                    text=text,
                    citations=tuple(citations),
                    extractive=True,
                    matched_rule=matched_rule,
                )
            )

        claims, truncated = self._order(claims, req.max_claims_per_section)

        return SummaryResult(
            claims=tuple(claims),
            summarizer_name=self.name,
            summarizer_version=self.version,
            notes={"sources": str(len(req.sources)), "claims": str(len(claims))},
            truncated=truncated,
        )

    @staticmethod
    def _order(claims: list[Claim], cap: int) -> tuple[list[Claim], int]:
        """Blockers first — they are the reason anyone reads a digest.

        Within a section, group by member so a reader can find their own name.
        Returns the kept claims and how many the per-section cap cut, so the
        digest can say so instead of dropping them silently.
        """
        section_rank = {
            ClaimKind.CARRYOVER: 0,
            ClaimKind.BLOCKER: 1,
            ClaimKind.PROGRESS: 2,
            ClaimKind.PLAN: 3,
        }
        ordered = sorted(claims, key=lambda c: (section_rank[c.kind], c.member_name))

        capped: list[Claim] = []
        truncated = 0
        seen: dict[ClaimKind, int] = {}
        for claim in ordered:
            count = seen.get(claim.kind, 0)
            if count >= cap:
                truncated += 1
                continue
            seen[claim.kind] = count + 1
            capped.append(claim)
        return capped, truncated
