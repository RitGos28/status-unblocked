"""A tiny stand-in for the GitHub Issues API, for demos without an account.

Run: python -m scripts.fake_github [--port 8091]
Then: STANDUP_TRACKER=github STANDUP_GITHUB_TOKEN=anything
      STANDUP_GITHUB_API_URL=http://127.0.0.1:8091

It implements only the three endpoints the app calls (list issues by label,
create an issue, add a comment), so the demo runs the real GitHubTracker code.
Open http://127.0.0.1:8091/ to see the issues it received. State lives in
memory and is gone when it stops.
"""

import argparse
import html
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse


@dataclass
class FakeIssue:
    number: int
    title: str
    body: str
    labels: list[str]
    comments: list[str] = field(default_factory=list)


def create_fake_github(public_url: str) -> FastAPI:
    app = FastAPI(title="fake GitHub")
    repos: dict[str, list[FakeIssue]] = {}
    base = public_url.rstrip("/")

    def require_token(request: Request) -> None:
        # Like GitHub: no bearer token, no access.
        if not request.headers.get("authorization", "").startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Requires authentication")

    def as_json(repo: str, issue: FakeIssue) -> dict[str, Any]:
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "labels": [{"name": name} for name in issue.labels],
            "comments": len(issue.comments),
            "html_url": f"{base}/{repo}/issues/{issue.number}",
        }

    def find(repo: str, number: int) -> FakeIssue:
        for issue in repos.get(repo, []):
            if issue.number == number:
                return issue
        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/repos/{owner}/{name}/issues")
    def list_issues(
        owner: str, name: str, request: Request, labels: str = "", page: int = 1, per_page: int = 30
    ) -> list[dict[str, Any]]:
        require_token(request)
        repo = f"{owner}/{name}"
        wanted = {label for label in labels.split(",") if label}
        matching = [i for i in repos.get(repo, []) if wanted <= set(i.labels)]
        start = (page - 1) * per_page
        return [as_json(repo, i) for i in matching[start : start + per_page]]

    @app.post("/repos/{owner}/{name}/issues", status_code=201)
    async def create_issue(owner: str, name: str, request: Request) -> dict[str, Any]:
        require_token(request)
        payload = await request.json()
        repo = f"{owner}/{name}"
        issues = repos.setdefault(repo, [])
        issue = FakeIssue(
            number=len(issues) + 1,
            title=payload["title"],
            body=payload.get("body", ""),
            labels=list(payload.get("labels", [])),
        )
        issues.append(issue)
        return as_json(repo, issue)

    @app.post("/repos/{owner}/{name}/issues/{number}/comments", status_code=201)
    async def add_comment(owner: str, name: str, number: int, request: Request) -> dict[str, Any]:
        require_token(request)
        payload = await request.json()
        issue = find(f"{owner}/{name}", number)
        issue.comments.append(payload["body"])
        return {"id": len(issue.comments), "body": payload["body"]}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        rows = "".join(
            f'<li><a href="/{repo}/issues/{i.number}">{html.escape(repo)} #{i.number}</a> '
            f"{html.escape(i.title)} ({len(i.comments)} comment(s))</li>"
            for repo, issues in repos.items()
            for i in issues
        )
        return _page("Issues received", f"<ul>{rows or '<li>none yet</li>'}</ul>")

    @app.get("/{owner}/{name}/issues/{number}", response_class=HTMLResponse)
    def show_issue(owner: str, name: str, number: int) -> str:
        issue = find(f"{owner}/{name}", number)
        comments = "".join(f"<pre>{html.escape(c)}</pre>" for c in issue.comments)
        return _page(
            f"{owner}/{name} #{issue.number}: {issue.title}",
            f"<p>Labels: {html.escape(', '.join(issue.labels))}</p>"
            f"<pre>{html.escape(issue.body)}</pre>"
            f"<h2>Comments ({len(issue.comments)})</h2>{comments or '<p>none</p>'}",
        )

    return app


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<body style='font:15px/1.5 system-ui;max-width:760px;margin:24px auto'>"
        "<p style='color:#a4442c'>fake GitHub for demos: not github.com</p>"
        f"<h1>{html.escape(title)}</h1>{body}</body>"
    )


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    uvicorn.run(create_fake_github(f"http://127.0.0.1:{args.port}"), port=args.port)


if __name__ == "__main__":
    main()
