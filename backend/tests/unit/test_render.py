"""Digest rendering: gaps are never silent, and moves are always explained."""

from datetime import UTC, datetime

from standup.domain.enums import ClaimKind
from standup.summarize.base import Citation, Claim
from standup.summarize.render import (
    SECTION_HINTS,
    SECTION_TITLES,
    explain_rule,
    group_sections,
    render_markdown,
)

NOW = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)


def claim(text: str = "Shipped it.") -> Claim:
    return Claim(
        kind=ClaimKind.PROGRESS,
        member_id="m1",
        member_name="Aarav Sharma",
        text=text,
        citations=(Citation("s1", text, 0, len(text)),),
    )


def test_promotion_is_explained_with_its_marker():
    assert explain_rule("promoted:marker:stuck") == (
        'Moved to Blockers: the author filed it elsewhere, but it says "stuck".'
    )


def test_field_classification_needs_no_explanation():
    assert explain_rule("field:progress") == ""
    assert explain_rule("") == ""


def test_truncated_lines_are_reported_separately_from_withheld():
    body = render_markdown(
        team_name="Core Platform",
        cycle_date="2026-09-15",
        claims=(claim(),),
        evidence_urls={"s1": "http://testserver/evidence/s1"},
        withheld_count=1,
        truncated_count=3,
    )
    assert "1 item(s) withheld" in body
    assert "3 more item(s) not shown" in body


def test_no_truncation_notice_when_nothing_was_cut():
    body = render_markdown(
        team_name="Core Platform",
        cycle_date="2026-09-15",
        claims=(claim(),),
        evidence_urls={},
    )
    assert "not shown" not in body


def _promoted(text: str = "Stuck on the deploy pipeline.") -> Claim:
    return Claim(
        kind=ClaimKind.BLOCKER,
        member_id="m1",
        member_name="Ananya Patel",
        text=text,
        citations=(Citation("s1", text, 0, len(text)),),
        matched_rule="promoted:marker:stuck",
    )


def _markdown(*claims: Claim) -> str:
    return render_markdown(
        team_name="Core Platform",
        cycle_date="2026-09-15",
        claims=claims,
        evidence_urls={"s1": "http://testserver/evidence/s1"},
    )


def test_markdown_links_are_ordinary_links():
    """Found by the browser pass: '[[source]](url)' rendered with doubled brackets."""
    body = _markdown(claim())
    assert "[source](http://testserver/evidence/s1)" in body
    assert "[[source]]" not in body


def test_markdown_explains_a_promoted_blocker_like_the_page_does():
    assert "Moved to Blockers" in _markdown(_promoted())


def test_markdown_carries_the_verbatim_footer_like_the_page_does():
    assert "verbatim quote" in _markdown(claim())


def test_every_section_has_a_plain_language_hint():
    """Each heading a reader can meet has one line explaining it, for people
    who do not know standup vocabulary; the hint never leaks into Markdown."""
    assert set(SECTION_HINTS) == set(SECTION_TITLES) == set(ClaimKind)
    assert all(hint.strip() for hint in SECTION_HINTS.values())
    (section,) = group_sections([claim()])
    assert section.title == "Progress"
    assert section.hint == SECTION_HINTS[ClaimKind.PROGRESS]
    md = render_markdown(
        team_name="Core", cycle_date="2026-09-15", claims=(claim(),), evidence_urls={}
    )
    assert section.hint not in md
