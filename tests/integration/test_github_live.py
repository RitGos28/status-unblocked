"""One read-only check against the real GitHub API.

Skipped unless STANDUP_LIVE_GITHUB_TOKEN and STANDUP_LIVE_GITHUB_REPO are set,
so CI never touches the network. It only lists issues; it writes nothing.
"""

import os

import pytest

from standup.tracker.github import GitHubTracker
from standup.tracker.idempotency import marker

TOKEN = os.environ.get("STANDUP_LIVE_GITHUB_TOKEN")
REPO = os.environ.get("STANDUP_LIVE_GITHUB_REPO")


@pytest.mark.live_github
@pytest.mark.skipif(not (TOKEN and REPO), reason="live GitHub credentials not set")
def test_token_can_list_labelled_issues():
    # A marker no issue carries: proves auth and the listing call work end to end.
    assert GitHubTracker(TOKEN or "").find_issue_by_marker(REPO or "", marker("0" * 64)) is None
