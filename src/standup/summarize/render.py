"""Digest rendering.

Withheld claims are handled here from day one, even though the features that
produce them (validation drops, author deletion in week 4) arrive later. A gap
in a digest must never be silent: if something was removed, the digest says so
and says how many.
"""

from dataclasses import dataclass

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


@dataclass(frozen=True)
class RenderedSection:
    kind: ClaimKind
    title: str
    claims: tuple[Claim, ...]


def explain_rule(matched_rule: str) -> str:
    """Human-readable reason a claim sits in its section, or "" if unremarkable.

    Only promotions need explaining: a line the author filed under Progress or
    Today that the digest shows under Blockers. The text is never changed, so
    the explanation is the only visible trace of the move.
    """
    if not matched_rule.startswith("promoted:"):
        return ""
    _, _, detail = matched_rule.partition(":")
    _, _, marker = detail.partition(":")
    if marker:
        return f'Moved to Blockers: the author filed it elsewhere, but it says "{marker}".'
    return "Moved to Blockers: the author filed it elsewhere."


def group_sections(claims: tuple[Claim, ...]) -> list[RenderedSection]:
    """Blockers first. That ordering is the whole point of the digest."""
    sections: list[RenderedSection] = []
    for kind in SECTION_ORDER:
        matching = tuple(c for c in claims if c.kind is kind)
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
                    f"[[source]]({evidence_urls.get(c.source_id, '#')})"
                    for c in claim.citations
                )
                lines.append(f"- **{claim.member_name}** - {claim.text} {links}")
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

    return "\n".join(lines).strip() + "\n"
