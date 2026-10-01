"""The GitHub client: the right calls, and the right retry classification."""

import httpx
import pytest
import respx

from standup.tracker.base import TrackerError
from standup.tracker.github import API, GitHubTracker
from standup.tracker.idempotency import marker

REPO = "acme/platform"


@respx.mock
def test_create_issue_sends_title_body_label_and_token():
    route = respx.post(f"{API}/repos/{REPO}/issues").mock(
        return_value=httpx.Response(201, json={"number": 7, "html_url": "https://gh/7"})
    )
    ref = GitHubTracker("tok").create_issue(REPO, title="T", body="B", labels=["standup-blocker"])

    assert (ref.number, ref.url) == (7, "https://gh/7")
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer tok"
    assert request.read() == b'{"title":"T","body":"B","labels":["standup-blocker"]}'


@respx.mock
def test_find_by_marker_scans_labelled_issues_across_pages():
    fp = "a" * 64
    page1 = [{"number": n, "html_url": f"u{n}", "body": "no marker"} for n in range(100)]
    page2 = [{"number": 500, "html_url": "u500", "body": f"x\n{marker(fp)}"}]
    respx.get(f"{API}/repos/{REPO}/issues", params={"page": "1"}).mock(
        return_value=httpx.Response(200, json=page1)
    )
    respx.get(f"{API}/repos/{REPO}/issues", params={"page": "2"}).mock(
        return_value=httpx.Response(200, json=page2)
    )
    ref = GitHubTracker("tok").find_issue_by_marker(REPO, marker(fp))
    assert ref is not None and ref.number == 500


@respx.mock
def test_find_by_marker_returns_none_when_absent():
    respx.get(f"{API}/repos/{REPO}/issues").mock(return_value=httpx.Response(200, json=[]))
    assert GitHubTracker("tok").find_issue_by_marker(REPO, marker("b" * 64)) is None


@pytest.mark.parametrize(
    ("status", "headers", "retryable", "retry_after"),
    [
        (403, {"x-ratelimit-remaining": "0"}, True, None),
        (403, {"retry-after": "120"}, True, 120),
        (429, {"retry-after": "30"}, True, 30),
        (502, {}, True, None),
        (401, {}, False, None),
        (404, {}, False, None),
        (403, {}, False, None),
    ],
)
@respx.mock
def test_errors_are_classified_for_the_outbox(status, headers, retryable, retry_after):
    respx.post(f"{API}/repos/{REPO}/issues/3/comments").mock(
        return_value=httpx.Response(status, headers=headers)
    )
    with pytest.raises(TrackerError) as excinfo:
        GitHubTracker("tok").add_comment(REPO, 3, "body")
    assert excinfo.value.retryable is retryable
    assert excinfo.value.retry_after_seconds == retry_after


@respx.mock
def test_network_errors_are_retryable_and_never_include_the_token():
    respx.post(f"{API}/repos/{REPO}/issues/3/comments").mock(
        side_effect=httpx.ConnectError("boom")
    )
    with pytest.raises(TrackerError) as excinfo:
        GitHubTracker("secret-token").add_comment(REPO, 3, "body")
    assert excinfo.value.retryable is True
    assert "secret-token" not in str(excinfo.value)
