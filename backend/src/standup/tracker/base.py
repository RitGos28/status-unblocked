"""The task-tracker seam.

A ``TrackerAdapter`` is the whole surface the outbox needs: open an issue,
comment on one, and find an existing issue by its machine marker. GitHub is the
one real implementation; ``NoopTracker`` is the default when no tracker is
configured.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class IssueRef:
    number: int
    url: str


class TrackerError(Exception):
    """A tracker call failed.

    ``retryable`` separates a transient failure (rate limit, 5xx, network),
    which the outbox retries with backoff, from a configuration error (bad
    token, missing repo), which it marks failed at once.
    """

    def __init__(self, message: str, *, retryable: bool, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class TrackerAdapter(Protocol):
    name: str

    def find_issue_by_marker(self, repo: str, marker: str) -> IssueRef | None: ...

    def create_issue(self, repo: str, *, title: str, body: str, labels: list[str]) -> IssueRef: ...

    def add_comment(self, repo: str, number: int, body: str) -> None: ...
