"""The tracker used when none is configured: writes nothing anywhere."""

from standup.tracker.base import IssueRef


class NoopTracker:
    name = "noop"

    def find_issue_by_marker(self, repo: str, marker: str) -> IssueRef | None:
        return None

    def create_issue(self, repo: str, *, title: str, body: str, labels: list[str]) -> IssueRef:
        raise NotImplementedError("NoopTracker never writes; the outbox skips its rows")

    def add_comment(self, repo: str, number: int, body: str) -> None:
        raise NotImplementedError("NoopTracker never writes; the outbox skips its rows")
