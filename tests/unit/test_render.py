"""Digest rendering: gaps are never silent, and moves are always explained."""

from datetime import UTC, datetime

from standup.domain.enums import ClaimKind
from standup.summarize.base import Citation, Claim
from standup.summarize.render import explain_rule, render_markdown

NOW = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)


def claim(text: str = "Shipped it.") -> Claim:
    return Claim(
        kind=ClaimKind.PROGRESS,
        member_id="m1",
        member_name="Ada Okafor",
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
