"""Normalizer tests.

The first test here is the one the whole citation contract depends on: a span
must round-trip exactly. If it ever fails, every "source" link in every digest
is potentially lying.
"""

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from standup.domain.enums import ItemKind, SourceKind
from standup.ingestion.base import RawSubmission
from standup.ingestion.normalizer import (
    extract_entities,
    normalize,
    normalized_key,
)


def make_submission(progress: str = "", blockers: str = "", plan: str = "") -> RawSubmission:
    return RawSubmission(
        source_kind=SourceKind.WEBFORM,
        external_user_key="ada",
        text_fields={
            ItemKind.PROGRESS: progress,
            ItemKind.BLOCKER: blockers,
            ItemKind.PLAN: plan,
        },
        captured_at=datetime(2026, 9, 15, 9, 30, tzinfo=UTC),
    )


def test_spans_round_trip_exactly():
    """raw_text[start:end] == item.text, for every item. The core invariant."""
    result = normalize(
        make_submission(
            progress="Shipped the retry logic. Reviewed #214.",
            blockers="Waiting on staging credentials from infra.",
            plan="Finish the migration.",
        )
    )

    assert result.items, "expected items"
    for item in result.items:
        assert result.raw_text[item.span_start : item.span_end] == item.text


@given(
    progress=st.text(min_size=1, max_size=200),
    blockers=st.text(min_size=1, max_size=200),
)
def test_spans_round_trip_for_arbitrary_text(progress: str, blockers: str):
    """Property version: no input shape may produce a drifting offset."""
    result = normalize(make_submission(progress=progress, blockers=blockers))
    for item in result.items:
        assert result.raw_text[item.span_start : item.span_end] == item.text


def test_kind_comes_from_the_field_not_inference():
    """Structured input is what keeps the summarizer faithful: the person
    told us which bucket their text belongs in."""
    result = normalize(
        make_submission(progress="Shipped it.", blockers="Stuck on review.", plan="Ship more.")
    )
    kinds = {item.kind for item in result.items}
    assert kinds == {ItemKind.PROGRESS, ItemKind.BLOCKER, ItemKind.PLAN}


def test_sentences_become_separate_items():
    """Granular items mean a citation points at one sentence, not a whole blob."""
    result = normalize(make_submission(progress="Did A. Did B. Did C."))
    progress = [i for i in result.items if i.kind is ItemKind.PROGRESS]
    assert len(progress) == 3
    assert [i.text for i in progress] == ["Did A.", "Did B.", "Did C."]


def test_bullets_become_separate_items():
    result = normalize(make_submission(blockers="- waiting on infra\n- no staging access"))
    blockers = [i for i in result.items if i.kind is ItemKind.BLOCKER]
    assert len(blockers) == 2
    assert blockers[0].text == "waiting on infra"


def test_empty_fields_are_skipped():
    result = normalize(make_submission(progress="Only this."))
    assert {i.kind for i in result.items} == {ItemKind.PROGRESS}
    assert "Blockers:" not in result.raw_text


def test_content_hash_is_stable_and_changes_with_content():
    a = normalize(make_submission(progress="Same text."))
    b = normalize(make_submission(progress="Same text."))
    c = normalize(make_submission(progress="Different text."))
    assert a.content_sha256 == b.content_sha256
    assert a.content_sha256 != c.content_sha256


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Blocked on #214", {"#214"}),
        ("See https://example.com/x", {"https://example.com/x"}),
        ("Waiting on PROJ-42", {"PROJ-42"}),
        ("Need @ada to review", {"@ada"}),
    ],
)
def test_extract_entities(text: str, expected: set[str]):
    found = {e["value"] for e in extract_entities(text)}
    assert expected <= found


def test_normalized_key_ignores_wording_noise():
    """Carry-over matching should survive small rewordings of the same blocker."""
    a = normalized_key("I am still waiting on the staging credentials")
    b = normalized_key("Waiting on staging credentials")
    assert set(b.split()) <= set(a.split())


def test_normalized_key_separates_different_blockers():
    a = normalized_key("waiting on staging credentials")
    b = normalized_key("flaky test in the payment module")
    assert not set(a.split()) & set(b.split())


@pytest.mark.parametrize(
    "progress",
    [
        "Did a thing.\nBlockers:\nnot really",
        "Blockers:\nToday:\nProgress:\nall headings, typed by hand",
    ],
)
def test_typed_headings_cannot_shift_the_real_spans(progress: str):
    """A user typing a section heading into another box must not move offsets.

    Found by an adversarial review: the heading was located with str.index,
    which matched the user's text first, and the span check failed with a 500.
    """
    submission = make_submission(
        progress=progress, blockers="Waiting on infra.", plan="Finish the migration."
    )
    normalized = normalize(submission)
    for item in normalized.items:
        assert normalized.raw_text[item.span_start : item.span_end] == item.text
    blockers = [i.text for i in normalized.items if i.kind is ItemKind.BLOCKER]
    assert blockers == ["Waiting on infra."]


_HEADING_SOUP = st.lists(
    st.sampled_from(["Progress:", "Blockers:", "Today:", "Plan:", "\n", "\n\n", "x", " ", ". "]),
    max_size=12,
).map("".join)


@given(progress=_HEADING_SOUP, blockers=_HEADING_SOUP, plan=_HEADING_SOUP)
def test_spans_round_trip_whatever_headings_users_type(progress, blockers, plan):
    """Any field may contain any heading text; every span must still round-trip."""
    normalized = normalize(make_submission(progress=progress, blockers=blockers, plan=plan))
    for item in normalized.items:
        assert normalized.raw_text[item.span_start : item.span_end] == item.text
