"""Digest rendering.

Withheld claims are counted here: today validation drops are the only source
of them; member-initiated deletion, not built yet, would be another. A gap
in a digest must never be silent: if something was removed, the digest says so
and says how many.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from standup.domain.enums import ClaimKind
from standup.summarize.base import Claim

SECTION_TITLES: dict[ClaimKind, str] = {
    ClaimKind.CARRYOVER: "Still blocked",
    ClaimKind.BLOCKER: "Blockers",
    ClaimKind.PROGRESS: "Progress",
    ClaimKind.PLAN: "Today",
}

SECTION_ORDER: tuple[ClaimKind, ...] = (
    ClaimKind.CARRYOVER,
    ClaimKind.BLOCKER,
    ClaimKind.PROGRESS,
    ClaimKind.PLAN,
)


class _HasKind(Protocol):
    # Any: summarizer Claims carry a ClaimKind, stored DigestClaim rows a
    # SQLAlchemy-mapped str. ClaimKind() accepts both.
    @property
    def kind(self) -> Any: ...


_T = TypeVar("_T", bound=_HasKind)


@dataclass(frozen=True)
class RenderedSection(Generic[_T]):
    kind: ClaimKind
    title: str
    claims: tuple[_T, ...]


def explain_rule(matched_rule: str) -> str:
    """Human-readable reason a claim sits in its section, or "" if unremarkable.

    Two things need explaining, because the text itself never changes:
    - a promotion: a line filed under Progress or Today shown under Blockers;
    - a carry-over: a blocker the same person also reported on an earlier day.
    A rule can carry both, separated by ";".
    """
    reasons: list[str] = []
    for part in matched_rule.split(";"):
        if part.startswith("promoted:"):
            _, _, detail = part.partition(":")
            _, _, marker = detail.partition(":")
            reasons.append(
                f'Moved to Blockers: the author filed it elsewhere, but it says "{marker}".'
                if marker
                else "Moved to Blockers: the author filed it elsewhere."
            )
        elif part.startswith("carryover:"):
            reasons.append(f"Also reported on {part.partition(':')[2]}, and still open.")
    return " ".join(reasons)


def group_sections(claims: Sequence[_T]) -> list[RenderedSection[_T]]:
    """Blockers first. That ordering is the whole point of the digest.

    One grouping for both the Markdown digest (summarizer Claims) and the HTML
    page (stored DigestClaim rows), so the two can never order or title
    sections differently. Claims keep their given order within a section.
    """
    sections: list[RenderedSection[_T]] = []
    for kind in SECTION_ORDER:
        matching = tuple(c for c in claims if ClaimKind(c.kind) is kind)
        if matching:
            sections.append(RenderedSection(kind, SECTION_TITLES[kind], matching))
    return sections


def render_markdown(
    *,
    team_name: str,
    cycle_date: str,
    claims: tuple[Claim, ...],
    evidence_urls: dict[str, str],
    withheld_count: int = 0,
    truncated_count: int = 0,
) -> str:
    """Markdown digest. Every claim carries its evidence link inline."""
    lines: list[str] = [f"# {team_name} - standup {cycle_date}", ""]

    if not claims:
        lines.append("_No updates submitted._")
    else:
        for section in group_sections(claims):
            lines.append(f"## {section.title}")
            lines.append("")
            for claim in section.claims:
                links = " ".join(
                    f"[{'source' if i == 0 else 'earlier report'}]"
                    f"({evidence_urls.get(c.source_id, '#')})"
                    for i, c in enumerate(claim.citations)
                )
                lines.append(f"- **{claim.member_name}** - {claim.text} {links}")
                why = explain_rule(claim.matched_rule)
                if why:
                    lines.append(f"  - _{why}_")
            lines.append("")

    if withheld_count:
        lines.append("")
        lines.append(
            f"_{withheld_count} item(s) withheld: failed source verification "
            f"or removed by their author._"
        )

    if truncated_count:
        lines.append("")
        lines.append(
            f"_{truncated_count} more item(s) not shown: a section reached its line limit._"
        )

    lines.append("")
    lines.append(
        "_Every line above is a verbatim quote, checked against its stored source "
        "before this digest was written._"
    )
    return "\n".join(lines).strip() + "\n"
