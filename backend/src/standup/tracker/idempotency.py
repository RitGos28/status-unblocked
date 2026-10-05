"""Blocker identity across days.

Three layers keep a recurring blocker to exactly one issue:

1. **Fingerprint**: ``sha256(team | member | normalized blocker text)``,
   UNIQUE on ``tracker_link.fingerprint``.
2. **Machine marker** in the issue body (and a ``standup-blocker`` label), so
   the mapping can be rebuilt from GitHub alone if the link row is lost, for
   example after a crash between creating the issue and saving the link.
3. **One write per blocker per cycle**: UNIQUE ``(fingerprint, cycle_id)`` on
   the outbox, so rebuilding a digest never comments twice.
"""

import hashlib
import re

LABEL = "standup-blocker"
_MARKER_PREFIX = "standup-bot:blocker:"
_MARKER_RE = re.compile(r"<!-- standup-bot:blocker:([0-9a-f]{64}) -->")


def fingerprint(team_id: str, member_id: str, normalized_key: str) -> str:
    return hashlib.sha256(f"{team_id}|{member_id}|{normalized_key}".encode()).hexdigest()


def marker(fp: str) -> str:
    return f"<!-- {_MARKER_PREFIX}{fp} -->"


def marker_in(body: str) -> str | None:
    """The fingerprint carried by an issue body, if any."""
    match = _MARKER_RE.search(body or "")
    return match.group(1) if match else None
