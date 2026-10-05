"""Blocker write-back to GitHub Issues, end to end against a mocked API.

Building a digest queues one outbox row per blocker; the background drain that
runs after the build turns each into exactly one issue. A rebuild adds
nothing, a later day adds one comment, a lost link is recovered from the
issue's marker, and GitHub failures never touch the digest.
"""

import json
import re
from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from standup.config import get_settings
from standup.db.models import (
    AuditLog,
    Digest,
    StandupCycle,
    Team,
    TrackerLink,
    TrackerOutbox,
)
from standup.domain.enums import AuditAction
from standup.ingestion.normalizer import normalized_key
from standup.tracker.github import API
from standup.tracker.idempotency import fingerprint, marker
from tests.helpers import submit

REPO = "acme/platform"
BLOCKER = "Waiting on staging credentials from infra."
ISSUES = f"{API}/repos/{REPO}/issues"


@pytest.fixture
def github_on(monkeypatch, session, team_with_members):
    """Switch the tracker to GitHub for this test and give the team a repo."""
    monkeypatch.setenv("STANDUP_TRACKER", "github")
    monkeypatch.setenv("STANDUP_GITHUB_TOKEN", "test-token")
    get_settings.cache_clear()
    team = session.get(Team, team_with_members[0].id)
    team.github_repo = REPO
    session.commit()
    return team_with_members


@pytest.fixture
def github():
    """A mocked GitHub: no labelled issues yet, creating returns #42."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(ISSUES).mock(return_value=httpx.Response(200, json=[]))
        mock.post(ISSUES).mock(
            return_value=httpx.Response(201, json={"number": 42, "html_url": "https://gh/42"})
        )
        mock.post(f"{ISSUES}/42/comments").mock(return_value=httpx.Response(201, json={}))
        yield mock


def build_today(client, session) -> Digest:
    cycle = session.execute(
        select(StandupCycle).order_by(StandupCycle.local_date.desc())
    ).scalars().first()
    response = client.post(f"/digests/build/{cycle.id}", follow_redirects=False)
    assert response.status_code == 303
    session.expire_all()
    return session.execute(
        select(Digest).where(Digest.cycle_id == cycle.id).order_by(Digest.generated_at.desc())
    ).scalars().first()


def calls(mock, method: str, url: str) -> list[httpx.Request]:
    return [
        c.request
        for c in mock.calls
        if c.request.method == method and str(c.request.url).split("?")[0] == url
    ]


def test_a_blocker_becomes_exactly_one_issue(client, session, github_on, github):
    _team, (ada, bruno, _chen) = github_on
    submit(client, ada.id, progress="Shipped the retry logic.", blockers=BLOCKER)
    submit(client, bruno.id, progress="Reviewed #214.", blockers="No blockers today.")

    digest = build_today(client, session)

    (created,) = calls(github, "POST", ISSUES)
    payload = json.loads(created.read())
    assert payload["title"] == f"Blocker: {BLOCKER}"
    assert payload["labels"] == ["standup-blocker", "team:core"]
    assert f"> {BLOCKER}" in payload["body"]
    assert "/evidence/" in payload["body"] and f"/digest/{digest.id}" in payload["body"]

    link = session.execute(select(TrackerLink)).scalar_one()
    assert (link.issue_number, link.repo, link.member_id) == (42, REPO, ada.id)
    assert marker(link.fingerprint) in payload["body"]
    assert session.execute(select(TrackerOutbox.status)).scalar_one() == "done"

    # The digest links the blocker to its issue, and the write is audited.
    assert 'href="https://gh/42"' in client.get(f"/digest/{digest.id}").text
    write = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.TRACKER_WRITE.value)
    ).scalar_one()
    assert write.object_ids_json["write"] == "created"
    assert write.subject_member_id == ada.id


def test_rebuilding_the_same_day_writes_nothing_more(client, session, github_on, github):
    _team, (ada, *_rest) = github_on
    submit(client, ada.id, blockers=BLOCKER)
    build_today(client, session)
    build_today(client, session)

    assert len(calls(github, "POST", ISSUES)) == 1
    assert calls(github, "POST", f"{ISSUES}/42/comments") == []
    assert len(session.execute(select(TrackerOutbox)).scalars().all()) == 1


def test_the_same_blocker_next_day_comments_instead_of_reopening(
    client, session, clock, github_on, github
):
    _team, (ada, *_rest) = github_on
    submit(client, ada.id, blockers=BLOCKER)
    build_today(client, session)

    clock.advance(days=1)
    submit(client, ada.id, blockers=BLOCKER)
    build_today(client, session)

    assert len(calls(github, "POST", ISSUES)) == 1
    (comment,) = calls(github, "POST", f"{ISSUES}/42/comments")
    assert "Still blocked on 2026-09-16" in json.loads(comment.read())["body"]


def test_a_lost_link_is_recovered_from_the_issue_marker(client, session, github_on, github):
    team, (ada, *_rest) = github_on
    fp = fingerprint(team.id, ada.id, normalized_key(BLOCKER))
    github.get(ISSUES).mock(
        return_value=httpx.Response(
            200, json=[{"number": 9, "html_url": "https://gh/9", "body": f"old\n{marker(fp)}"}]
        )
    )
    submit(client, ada.id, blockers=BLOCKER)
    build_today(client, session)

    assert calls(github, "POST", ISSUES) == []
    link = session.execute(select(TrackerLink)).scalar_one()
    assert link.issue_number == 9


def test_rate_limiting_schedules_a_retry_and_leaves_the_digest_alone(
    client, session, github_on, github
):
    _team, (ada, *_rest) = github_on
    github.post(ISSUES).mock(
        return_value=httpx.Response(
            403, headers={"x-ratelimit-remaining": "0", "retry-after": "600"}
        )
    )
    submit(client, ada.id, blockers=BLOCKER)
    digest = build_today(client, session)

    row = session.execute(select(TrackerOutbox)).scalar_one()
    assert (row.status, row.attempts) == ("pending", 1)
    created = row.created_at.replace(tzinfo=None)
    assert row.next_attempt_at.replace(tzinfo=None) >= created + timedelta(seconds=599)
    assert client.get(f"/digest/{digest.id}").status_code == 200
    assert session.execute(select(TrackerLink)).first() is None


def test_a_bad_token_fails_the_row_without_retrying(client, session, github_on, github):
    _team, (ada, *_rest) = github_on
    github.post(ISSUES).mock(return_value=httpx.Response(401))
    submit(client, ada.id, blockers=BLOCKER)
    build_today(client, session)

    row = session.execute(select(TrackerOutbox)).scalar_one()
    assert row.status == "failed"
    assert "401" in row.last_error


def test_without_a_tracker_rows_are_skipped_and_nothing_is_sent(
    client, session, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    with respx.mock(assert_all_called=False) as mock:
        submit(client, ada.id, blockers=BLOCKER)
        build_today(client, session)
        assert mock.calls.call_count == 0

    row = session.execute(select(TrackerOutbox)).scalar_one()
    assert row.status == "skipped"
    assert "STANDUP_TRACKER=noop" in row.last_error


def test_a_team_without_a_repo_is_skipped(client, session, monkeypatch, team_with_members):
    monkeypatch.setenv("STANDUP_TRACKER", "github")
    monkeypatch.setenv("STANDUP_GITHUB_TOKEN", "test-token")
    get_settings.cache_clear()
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers=BLOCKER)
    build_today(client, session)

    row = session.execute(select(TrackerOutbox)).scalar_one()
    assert (row.status, row.last_error) == ("skipped", "team has no github_repo configured")


# --- structured output: the issue is machine-readable, not just prose -------

_JSON_BLOCK = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def json_block(body: str) -> dict:
    match = _JSON_BLOCK.search(body)
    assert match, f"no ```json block in:\n{body}"
    return json.loads(match.group(1))


def test_the_issue_carries_a_json_record_and_a_team_label(client, session, github_on, github):
    team, (ada, *_rest) = github_on
    submit(client, ada.id, blockers=BLOCKER)
    digest = build_today(client, session)

    (created,) = calls(github, "POST", ISSUES)
    payload = json.loads(created.read())
    assert payload["labels"] == ["standup-blocker", "team:core"]
    record = json_block(payload["body"])["standup_blocker"]
    link = session.execute(select(TrackerLink)).scalar_one()
    assert record == {
        "fingerprint": link.fingerprint,
        "team": "core",
        "reported_by": "Ada Okafor",
        "quote": BLOCKER,
        "first_reported": "2026-09-15",
        "days_reported": 1,
        "evidence_url": record["evidence_url"],
        "digest_url": f"http://testserver/digest/{digest.id}",
    }
    assert "/evidence/" in record["evidence_url"]


def test_each_later_day_adds_a_comment_with_the_running_count(
    client, session, clock, github_on, github
):
    _team, (ada, *_rest) = github_on
    for _day in range(3):
        submit(client, ada.id, blockers=BLOCKER)
        build_today(client, session)
        clock.advance(days=1)

    posted = calls(github, "POST", f"{ISSUES}/42/comments")
    comments = [json.loads(c.read())["body"] for c in posted]
    assert [json_block(c)["standup_blocker_update"]["days_reported"] for c in comments] == [2, 3]
    assert json_block(comments[-1])["standup_blocker_update"]["date"] == "2026-09-17"
    assert session.execute(select(TrackerLink.days_reported)).scalar_one() == 3


def test_blockers_skipped_before_a_repo_was_set_are_filed_once_it_is(
    client, session, clock, monkeypatch, team_with_members, github
):
    """Found by the round-2 review (B): rows skipped for 'no github_repo' were
    final, so connecting the repo afterwards never filed that day's blockers."""
    from standup.deps import tracker_from_settings
    from standup.tracker.outbox import drain, requeue_skipped

    monkeypatch.setenv("STANDUP_TRACKER", "github")
    monkeypatch.setenv("STANDUP_GITHUB_TOKEN", "test-token")
    get_settings.cache_clear()
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers=BLOCKER)
    build_today(client, session)  # no repo yet: the background drain skips it
    row = session.execute(select(TrackerOutbox)).scalar_one()
    assert row.status == "skipped"

    team = session.get(Team, team_with_members[0].id)
    team.github_repo = REPO
    assert requeue_skipped(session, team.id, clock.now()) == 1
    session.commit()
    report = drain(session, tracker_from_settings(get_settings()), clock.now())
    assert report.done == 1
    assert len(calls(github, "POST", ISSUES)) == 1
    session.expire_all()
    assert session.execute(select(TrackerOutbox)).scalar_one().status == "done"


def test_requeue_leaves_old_skipped_rows_alone(
    client, session, clock, monkeypatch, team_with_members
):
    from standup.tracker.outbox import requeue_skipped

    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers=BLOCKER)
    build_today(client, session)
    assert requeue_skipped(session, team_with_members[0].id, clock.now() + timedelta(days=30)) == 0
