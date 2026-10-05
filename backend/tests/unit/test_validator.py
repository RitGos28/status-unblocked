"""Faithfulness validator tests.

The most convincing tests in the project live here. Two ideas:

1. A deliberately hallucinating summarizer must be rejected 100% of the time.
2. Any single mutation of a *valid* result must be caught — flip a digit, swap
   a source id, shift an offset by one, paraphrase a quote, reassign the
   author. If a mutation slips through, the validator has a hole.

The suite is parametrized over summarizer implementations, so when the LLM
lands in week 4 it clears this same bar rather than a softer one.
"""

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from standup.domain.enums import ClaimKind, ItemKind
from standup.summarize.base import (
    Citation,
    Claim,
    SourceDoc,
    SummaryRequest,
    SummaryResult,
)
from standup.summarize.rules import RulesSummarizer
from standup.summarize.validator import FaithfulnessValidator

NOW = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)


def source(
    id_: str = "s1",
    member_id: str = "m1",
    text: str = "Waiting on staging credentials from infra.",
    kind: ItemKind = ItemKind.BLOCKER,
) -> SourceDoc:
    return SourceDoc(
        id=id_,
        member_id=member_id,
        member_name="Ada Okafor",
        kind=kind,
        text=text,
        captured_at=NOW,
        evidence_url=f"http://testserver/evidence/{id_}",
    )


def request_with(*sources: SourceDoc) -> SummaryRequest:
    return SummaryRequest(
        cycle_date=NOW.date(),
        team_name="Core Platform",
        sources=sources,
    )


def valid_claim(src: SourceDoc) -> Claim:
    return Claim(
        kind=ClaimKind.BLOCKER,
        member_id=src.member_id,
        member_name=src.member_name,
        text=src.text,
        citations=(Citation(source_id=src.id, quote=src.text, start=0, end=len(src.text)),),
        extractive=True,
    )


def result_with(*claims: Claim) -> SummaryResult:
    return SummaryResult(claims=claims, summarizer_name="test", summarizer_version="0")


# --------------------------------------------------------------------------
# A summarizer that writes plausible, fluent, completely unsourced prose.
# This is the failure mode the whole project is designed around.
# --------------------------------------------------------------------------
class HallucinatingSummarizer:
    name = "hallucinating"
    version = "0.0.1"

    def summarize(self, req: SummaryRequest) -> SummaryResult:
        claims = [
            Claim(
                kind=ClaimKind.BLOCKER,
                member_id="m1",
                member_name="Ada Okafor",
                text="The team is blocked on 3 separate infrastructure issues, see #999.",
                citations=(
                    Citation(source_id="does-not-exist", quote="fabricated", start=0, end=11),
                ),
                extractive=False,
            ),
            Claim(
                kind=ClaimKind.PROGRESS,
                member_id="m1",
                member_name="Ada Okafor",
                text="Everything is on track and morale is high.",
                citations=(),
                extractive=False,
            ),
        ]
        return SummaryResult(tuple(claims), self.name, self.version)


def test_valid_claim_passes():
    src = source()
    kept, report = FaithfulnessValidator().validate(
        result_with(valid_claim(src)), request_with(src)
    )
    assert len(kept) == 1
    assert report.ok
    assert report.withheld == 0


def test_hallucinating_summarizer_is_rejected_entirely():
    """Every claim must be dropped. Not most of them - all of them."""
    src = source()
    req = request_with(src)
    result = HallucinatingSummarizer().summarize(req)

    kept, report = FaithfulnessValidator().validate(result, req)

    assert kept == (), "a fabricated claim reached the digest"
    assert report.withheld == report.checked == 2
    rules = {v.rule for v in report.violations}
    assert "V1" in rules  # the uncited claim
    assert "V2" in rules  # the invented source id


def test_v1_claim_without_citation_is_dropped():
    src = source()
    claim = Claim(ClaimKind.BLOCKER, src.member_id, src.member_name, src.text, citations=())
    kept, report = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()
    assert [v.rule for v in report.violations] == ["V1"]


def test_v2_unknown_source_id_is_dropped():
    src = source()
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        src.text,
        citations=(Citation("ghost", src.text, 0, len(src.text)),),
    )
    kept, report = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()
    assert "V2" in {v.rule for v in report.violations}


def test_v3_paraphrase_presented_as_quote_is_dropped():
    """The rule that stops 'summarised' text being passed off as verbatim."""
    src = source()
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        "Ada is waiting for infra credentials",
        citations=(
            Citation(src.id, "Ada is waiting for infra credentials", 0, len(src.text)),
        ),
    )
    kept, report = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()
    assert "V3" in {v.rule for v in report.violations}


def test_v3_tolerates_whitespace_and_unicode_normalisation():
    """A non-breaking space must not invalidate an otherwise honest quote."""
    src = source(text="Waiting on staging credentials.")
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        "Waiting on staging credentials.",
        citations=(Citation(src.id, "Waiting on staging credentials.", 0, len(src.text)),),
    )
    kept, _ = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert len(kept) == 1


def test_v4_invented_number_is_dropped():
    src = source(text="Waiting on credentials.")
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        "Waiting on credentials for 3 days.",
        citations=(Citation(src.id, "Waiting on credentials.", 0, len(src.text)),),
        extractive=False,
    )
    kept, report = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()
    assert "V4" in {v.rule for v in report.violations}


def test_v5_invented_issue_reference_is_dropped():
    src = source(text="Blocked on the deploy.")
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        "Blocked on the deploy, see #4212.",
        citations=(Citation(src.id, "Blocked on the deploy.", 0, len(src.text)),),
        extractive=False,
    )
    kept, report = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()
    assert "V5" in {v.rule for v in report.violations}


def test_v6_cross_attribution_is_dropped():
    """Attributing one person's blocker to another is the most damaging
    failure this tool could have. It must never survive."""
    src = source(id_="s1", member_id="m1")
    claim = Claim(
        ClaimKind.BLOCKER,
        "m2",  # someone else entirely
        "Bruno Silva",
        src.text,
        citations=(Citation(src.id, src.text, 0, len(src.text)),),
    )
    kept, report = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()
    assert "V6" in {v.rule for v in report.violations}


def test_v8_abstractive_claim_may_not_balloon_beyond_evidence():
    src = source(text="Blocked.")
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        "Blocked, and the team is considering a full architectural rewrite.",
        citations=(Citation(src.id, "Blocked.", 0, 8),),
        extractive=False,
    )
    kept, report = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()
    assert "V8" in {v.rule for v in report.violations}


def test_extractive_claims_are_exempt_from_the_length_guard():
    src = source()
    kept, _ = FaithfulnessValidator().validate(
        result_with(valid_claim(src)), request_with(src)
    )
    assert len(kept) == 1


def test_good_claims_survive_alongside_bad_ones():
    """A bad claim is dropped; it must not take the honest ones with it."""
    good_src = source(id_="s1", member_id="m1")
    bad = Claim(ClaimKind.BLOCKER, "m1", "Ada Okafor", "invented", citations=())

    kept, report = FaithfulnessValidator().validate(
        result_with(valid_claim(good_src), bad), request_with(good_src)
    )
    assert len(kept) == 1
    assert report.withheld == 1


# --------------------------------------------------------------------------
# Mutation properties: perturb a valid result, assert rejection.
# --------------------------------------------------------------------------


@given(offset=st.integers(min_value=1, max_value=10))
def test_shifted_offset_is_rejected(offset: int):
    src = source(text="Waiting on staging credentials from infra.")
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        src.text,
        citations=(Citation(src.id, src.text, offset, len(src.text)),),
    )
    kept, _ = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == (), f"offset shifted by {offset} was accepted"


@given(bogus_id=st.text(alphabet="abcdef0123456789-", min_size=1, max_size=20))
def test_swapped_source_id_is_rejected(bogus_id: str):
    src = source(id_="s1")
    if bogus_id == src.id:
        return
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        src.text,
        citations=(Citation(bogus_id, src.text, 0, len(src.text)),),
    )
    kept, _ = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()


@given(digit=st.integers(min_value=0, max_value=9))
def test_injected_digit_is_rejected(digit: int):
    src = source(text="Blocked on the deploy.")
    claim = Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        f"Blocked on the deploy for {digit} days.",
        citations=(Citation(src.id, "Blocked on the deploy.", 0, len(src.text)),),
        extractive=False,
    )
    kept, _ = FaithfulnessValidator().validate(result_with(claim), request_with(src))
    assert kept == ()


# --------------------------------------------------------------------------
# Every implementation clears the same bar. Add new summarizers to this list.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("summarizer", [RulesSummarizer()], ids=lambda s: s.name)
def test_shipped_summarizers_produce_fully_valid_output(summarizer):
    sources = (
        source(id_="s1", member_id="m1", text="Waiting on staging credentials."),
        source(id_="s2", member_id="m1", text="Shipped the retry logic.", kind=ItemKind.PROGRESS),
        source(id_="s3", member_id="m2", text="Reviewed #214.", kind=ItemKind.PROGRESS),
    )
    req = request_with(*sources)
    result = summarizer.summarize(req)

    kept, report = FaithfulnessValidator().validate(result, req)

    assert report.ok, f"{summarizer.name} emitted violations: {report.violations}"
    assert len(kept) == len(result.claims)


def _abstractive(src: SourceDoc, text: str) -> Claim:
    return Claim(
        ClaimKind.BLOCKER,
        src.member_id,
        src.member_name,
        text,
        citations=(Citation(src.id, src.text, 0, len(src.text)),),
        extractive=False,
    )


@pytest.mark.parametrize(
    ("evidence", "claim_text", "rule"),
    [
        ("Waiting 10 days on credentials.", "Waiting 1 day on credentials.", "V4"),
        ("Deploy failed 25 times today.", "Deploy failed 5 times today.", "V4"),
        ("Blocked on #12 for the deploy.", "Blocked on #1 for the deploy.", "V5"),
        ("Waiting on @anabel for review.", "Waiting on @ana for review.", "V5"),
        ("Blocked by ABC-12 in the tracker.", "Blocked by ABC-1 in the tracker.", "V5"),
        ("See https://x.io/abcdef for logs.", "See https://x.io/abc for logs.", "V5"),
    ],
)
def test_numbers_and_references_must_match_whole_not_as_a_substring(evidence, claim_text, rule):
    """Found by the robustness review: '1' passed against '10' because V4 (and
    V5) checked substrings of the evidence instead of whole tokens."""
    src = source(text=evidence)
    kept, report = FaithfulnessValidator().validate(
        result_with(_abstractive(src, claim_text)), request_with(src)
    )
    assert kept == ()
    assert rule in {v.rule for v in report.violations}


@pytest.mark.parametrize(
    ("evidence", "claim_text"),
    [
        ("Waiting 10 days on credentials.", "Waiting 10 days on credentials, still."),
        ("Blocked on #12 by @anabel.", "Blocked on #12 by @anabel, still."),
    ],
)
def test_exact_numbers_and_references_still_pass(evidence, claim_text):
    src = source(text=evidence)
    kept, _ = FaithfulnessValidator().validate(
        result_with(_abstractive(src, claim_text)), request_with(src)
    )
    assert len(kept) == 1


# --------------------------------------------------------------------------
# V9: an extractive claim says exactly what it cites. V10: a claim's section
# follows the classification policy, whichever summarizer produced it.


def _rules(claim: Claim, *sources: SourceDoc) -> list[str]:
    _kept, report = FaithfulnessValidator().validate(result_with(claim), request_with(*sources))
    return [v.rule for v in report.violations]


def test_v9_extractive_claim_with_text_other_than_its_quote_is_dropped():
    src = source(text="Waiting on staging credentials from infra.")
    claim = Claim(
        kind=ClaimKind.PROGRESS,
        member_id=src.member_id,
        member_name=src.member_name,
        text="Ada is fully unblocked and the release is on track.",
        citations=(Citation(source_id=src.id, quote=src.text, start=0, end=len(src.text)),),
        extractive=True,
    )
    assert "V9" in _rules(claim, src)


def test_v9_allows_whitespace_and_nfkc_differences():
    src = source(text="Waiting  on staging.")
    claim = valid_claim(src)
    claim = Claim(**{**claim.__dict__, "text": "Waiting on staging."})
    assert _rules(claim, src) == []


def test_v10_progress_line_reported_as_a_blocker_is_dropped():
    src = source(text="Shipped the retry logic.", kind=ItemKind.PROGRESS)
    assert "V10" in _rules(valid_claim(src), src)  # valid_claim is a BLOCKER claim


def test_v10_a_blocker_hidden_under_progress_is_dropped():
    src = source(text="Waiting on staging credentials from infra.")
    claim = Claim(**{**valid_claim(src).__dict__, "kind": ClaimKind.PROGRESS})
    assert "V10" in _rules(claim, src)


def test_v10_an_empty_blocker_answer_is_not_a_blocker():
    src = source(text="None.")
    assert "V10" in _rules(valid_claim(src), src)


def test_v10_a_promoted_blocker_is_allowed():
    src = source(text="Stuck on the deploy pipeline.", kind=ItemKind.PROGRESS)
    assert _rules(valid_claim(src), src) == []


def test_v10_carryover_needs_an_earlier_report():
    src = source(text="Waiting on staging credentials from infra.")
    claim = Claim(**{**valid_claim(src).__dict__, "kind": ClaimKind.CARRYOVER})
    assert "V10" in _rules(claim, src)


def test_v9_v10_do_not_crash_when_the_first_citation_is_unknown():
    src = source()
    claim = Claim(
        **{
            **valid_claim(src).__dict__,
            "citations": (Citation(source_id="nope", quote="x", start=0, end=1),)
            + valid_claim(src).citations,
        }
    )
    assert _rules(claim, src) == ["V2"]
