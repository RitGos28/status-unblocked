"""Show the faithfulness validator at work on a real day's updates.

Run: python -m scripts.faithfulness_demo [--team core]

Takes the team's latest day, builds the same SummaryRequest a digest would,
and validates two sets of claims against it: the rules summarizer's output
(every line passes) and a set of plausible-looking bad claims an unfaithful
summarizer could write (each is dropped, naming the rule). Read-only: nothing
is written, no digest is built, nothing is audited.
"""

import argparse
import sys
from dataclasses import replace

from sqlalchemy import select

from standup.config import get_settings
from standup.db.models import StandupCycle, Team
from standup.db.session import session_scope
from standup.domain.enums import ClaimKind
from standup.summarize.base import Citation, Claim, SourceDoc, SummaryRequest
from standup.summarize.rules import RulesSummarizer
from standup.summarize.service import build_request
from standup.summarize.validator import FaithfulnessValidator


def bad_claims(request: SummaryRequest, good: tuple[Claim, ...]) -> list[tuple[str, Claim]]:
    """Each one is a way a fluent summarizer goes wrong, built from real claims."""
    blocker = next(c for c in good if c.kind in (ClaimKind.BLOCKER, ClaimKind.CARRYOVER))
    progress = next(c for c in good if c.kind is ClaimKind.PROGRESS)
    other = next(s for s in request.sources if s.member_id != blocker.member_id)
    first = blocker.citations[0]
    return [
        ("invents a source", replace(blocker, citations=(replace(first, source_id="made-up"),))),
        ("misquotes its source", replace(blocker, citations=(replace(first, quote="All done."),))),
        ("says the blocker is solved", replace(blocker, text="Fully unblocked; release on track.")),
        ("hides a blocker under Progress", replace(blocker, kind=ClaimKind.PROGRESS)),
        ("turns progress into a blocker", replace(progress, kind=ClaimKind.BLOCKER)),
        (
            "adds a number",
            replace(blocker, text=blocker.text + " 3 days left.", extractive=False),
        ),
        (
            "credits the wrong person",
            replace(
                blocker,
                citations=(Citation(other.id, other.text.strip(), 0, len(other.text.strip())),),
                text=other.text.strip(),
            ),
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--team", default="core", help="team slug (default: core)")
    args = parser.parse_args()
    validator = FaithfulnessValidator()

    with session_scope() as session:
        team = session.execute(select(Team).where(Team.slug == args.team)).scalar_one_or_none()
        if team is None:
            print(f"faithfulness_demo: no team {args.team!r}", file=sys.stderr)
            return 2
        cycle = (
            session.execute(
                select(StandupCycle)
                .where(StandupCycle.team_id == team.id)
                .order_by(StandupCycle.local_date.desc())
            )
            .scalars()
            .first()
        )
        if cycle is None:
            print(f"faithfulness_demo: {team.name} has no updates yet", file=sys.stderr)
            return 2
        request = build_request(session, cycle.id, get_settings().base_url)

    result = RulesSummarizer().summarize(request)
    good = result.claims
    _kept, report = validator.validate(result, request)
    print(f"{team.name}, {cycle.local_date}: the rules summarizer's {report.checked} lines")
    print(f"  passed {report.passed}, withheld {report.withheld}")

    try:
        cases = bad_claims(request, good)
    except StopIteration:
        print("  (needs a blocker, a progress line and two members to show bad claims)")
        return 0
    print("Claims an unfaithful summarizer could write:")
    caught = 0
    for label, claim in cases:
        rules = sorted(
            {v.rule for v in validator.validate_claim(claim, _sources(request))},
            key=lambda rule: int(rule[1:]),
        )
        caught += bool(rules)
        print(f"  {'withheld' if rules else 'PASSED  '}  {', '.join(rules):<8} {label}")
    print(f"withheld {caught} of {len(cases)}")
    return 0 if caught == len(cases) and report.withheld == 0 else 1


def _sources(request: SummaryRequest) -> dict[str, SourceDoc]:
    sources = {s.id: s for s in request.sources}
    for prior in request.prior_open_blockers:
        sources.setdefault(prior.id, prior)
    return sources


if __name__ == "__main__":
    sys.exit(main())
