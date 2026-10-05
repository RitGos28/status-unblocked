"""GitHub Issues as the task tracker, over the REST API with a fine-grained PAT.

Only three endpoints are used: list issues by label (to find a marker), create
an issue, and add a comment. The token needs Issues: read and write on the
target repository and nothing else.
"""

import httpx

from standup.tracker.base import IssueRef, TrackerError
from standup.tracker.idempotency import LABEL, marker_in

API = "https://api.github.com"
_MAX_PAGES = 10  # 1,000 labelled issues; beyond that, the link table is the source of truth


class GitHubTracker:
    name = "github"

    def __init__(self, token: str, *, api_url: str = API, client: httpx.Client | None = None):
        # api_url points at GitHub, or at scripts/fake_github.py for an
        # accountless demo that still exercises this exact client.
        self._client = client or httpx.Client(base_url=api_url, timeout=10.0)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def find_issue_by_marker(self, repo: str, marker: str) -> IssueRef | None:
        wanted = marker_in(marker)
        for page in range(1, _MAX_PAGES + 1):
            response = self._request(
                "GET",
                f"/repos/{repo}/issues",
                params={"labels": LABEL, "state": "all", "per_page": 100, "page": page},
            )
            issues = response.json()
            for issue in issues:
                if marker_in(issue.get("body") or "") == wanted:
                    return IssueRef(number=issue["number"], url=issue["html_url"])
            if len(issues) < 100:
                return None
        return None

    def create_issue(self, repo: str, *, title: str, body: str, labels: list[str]) -> IssueRef:
        response = self._request(
            "POST", f"/repos/{repo}/issues", json={"title": title, "body": body, "labels": labels}
        )
        issue = response.json()
        return IssueRef(number=issue["number"], url=issue["html_url"])

    def add_comment(self, repo: str, number: int, body: str) -> None:
        self._request("POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body})

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            response = self._client.request(method, path, headers=self._headers, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            raise TrackerError(f"github: {type(exc).__name__}", retryable=True) from exc

        if response.status_code < 400:
            return response

        retry_after = response.headers.get("retry-after")
        retry_seconds = int(retry_after) if retry_after and retry_after.isdigit() else None
        rate_limited = response.status_code == 429 or (
            response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0"
        ) or (response.status_code == 403 and retry_after is not None)
        if rate_limited or response.status_code >= 500:
            raise TrackerError(
                f"github: HTTP {response.status_code}",
                retryable=True,
                retry_after_seconds=retry_seconds,
            )
        # 401 bad token, 403 missing permission, 404 no such repo, 422 bad label:
        # configuration problems that retrying cannot fix.
        raise TrackerError(
            f"github: HTTP {response.status_code} on {method} {path}", retryable=False
        )
