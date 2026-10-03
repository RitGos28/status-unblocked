"""The demo's fake GitHub speaks the same API the real client uses.

The demo must exercise the real GitHubTracker, so these tests drive it against
scripts/fake_github.py instead of mocking the client.
"""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from scripts.fake_github import create_fake_github
from sqlalchemy import select

from standup.db.models import StandupCycle, Team
from standup.summarize.rules import RulesSummarizer
from standup.summarize.service import build_digest
from standup.tracker.base import TrackerError
from standup.tracker.github import GitHubTracker
from standup.tracker.idempotency import LABEL, marker
from standup.tracker.outbox import drain
from tests.helpers import submit

REPO = "demo/core"


@pytest.fixture
def fake():
    return TestClient(create_fake_github("http://fake-github"))


def tracker(fake) -> GitHubTracker:
    return GitHubTracker("any-token", client=fake)


def test_create_find_and_comment_round_trip(fake):
    gh = tracker(fake)
    body = f"body\n{marker('a' * 64)}"
    ref = gh.create_issue(REPO, title="Blocker: x", body=body, labels=[LABEL])
    assert (ref.number, ref.url) == (1, "http://fake-github/demo/core/issues/1")
    assert gh.find_issue_by_marker(REPO, marker("a" * 64)) == ref
    assert gh.find_issue_by_marker(REPO, marker("b" * 64)) is None
    gh.add_comment(REPO, 1, "Still blocked")
    assert "Still blocked" in fake.get("/demo/core/issues/1").text


def test_requests_without_a_token_are_refused_like_github(fake):
    assert fake.get(f"/repos/{REPO}/issues").status_code == 401
    with pytest.raises(TrackerError) as excinfo:
        GitHubTracker("", client=fake).add_comment(REPO, 99, "x")
    assert excinfo.value.retryable is False


def test_a_two_day_backfill_opens_the_issue_on_the_first_day(
    client, session, clock, fake, team_with_members
):
    """One pass that builds two days must open the issue for day 1 and comment for day 2."""
    team, (ada, *_rest) = team_with_members
    session.get(Team, team.id).github_repo = REPO
    session.commit()
    for day in (14, 15):
        clock.current = datetime(2026, 9, day, 9, 0, tzinfo=UTC)
        submit(client, ada.id, blockers="Waiting on staging credentials from infra.")

    # Both days built in one pass, at one moment: their outbox rows tie on created_at.
    now = datetime(2026, 9, 15, 11, 5, tzinfo=UTC)
    for cycle in session.execute(
        select(StandupCycle).order_by(StandupCycle.local_date.desc())
    ).scalars():
        build_digest(
            session, cycle_id=cycle.id, summarizer=RulesSummarizer(),
            base_url="https://standup.example", now=now,
        )
    session.commit()
    drain(session, tracker(fake), now)

    issues = fake.get(f"/repos/{REPO}/issues", headers={"authorization": "Bearer x"}).json()
    assert len(issues) == 1 and issues[0]["comments"] == 1
    assert "on 2026-09-14" in issues[0]["body"]
    assert "Still blocked on 2026-09-15" in fake.get("/demo/core/issues/1").text
    json.dumps(issues)  # the listing is plain JSON
