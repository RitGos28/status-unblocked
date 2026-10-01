"""Blocker write-back through an outbox.

``enqueue_blocker_issues`` runs inside the digest build and only writes rows to
our own database. ``drain`` runs afterwards (a background task after a build,
or the scheduler) and performs the tracker calls. So a tracker outage, a bad
token or a rate limit can delay an issue but never block or lose a digest
(invariant 8).

Each blocker becomes one issue. The same blocker reported on a later day adds
one comment to that issue. The bot never closes issues; people do.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.db.models import (
    Digest,
    StandupCycle,
    Team,
    TrackerLink,
    TrackerOutbox,
    UpdateItem,
)
from standup.domain.enums import AuditAction, ClaimKind
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit
from standup.tracker.base import TrackerAdapter, TrackerError
from standup.tracker.idempotency import LABEL, fingerprint, marker

log = get_logger(__name__)

MAX_ATTEMPTS = 8
_BLOCKER_KINDS = {ClaimKind.BLOCKER.value, ClaimKind.CARRYOVER.value}


@dataclass
class DrainReport:
    done: int = 0
    skipped: int = 0
    retrying: int = 0
    failed: int = 0
    actions: list[str] = field(default_factory=list)


def enqueue_blocker_issues(
    session: Session, digest: Digest, cycle: StandupCycle, base_url: str, now: datetime
) -> int:
    """Queue one tracker write per distinct blocker in ``digest``.

    Also stamps each blocker claim with its fingerprint so the digest page can
    show the issue link once it exists. Rebuilding a digest for the same cycle
    queues nothing new: ``(fingerprint, cycle_id)`` is unique.
    """
    base = base_url.rstrip("/")
    queued = 0
    seen: set[str] = set()

    for claim in digest.claims:
        if claim.kind not in _BLOCKER_KINDS or not claim.citations_json:
            continue
        citation = claim.citations_json[0]
        item = session.get(UpdateItem, citation["source_id"])
        key = (item.normalized_key if item else "") or claim.text.lower()
        fp = fingerprint(cycle.team_id, claim.member_id, key)
        claim.tracker_fingerprint = fp

        if fp in seen:
            continue
        seen.add(fp)
        already = session.execute(
            select(TrackerOutbox.id)
            .where(TrackerOutbox.fingerprint == fp)
            .where(TrackerOutbox.cycle_id == cycle.id)
        ).first()
        if already:
            continue

        session.add(
            TrackerOutbox(
                created_at=now,
                next_attempt_at=now,
                fingerprint=fp,
                team_id=cycle.team_id,
                member_id=claim.member_id,
                cycle_id=cycle.id,
                digest_id=digest.id,
                payload_json={
                    "quote": claim.text,
                    "author": claim.member_name,
                    "date": cycle.local_date.isoformat(),
                    "evidence_url": citation.get("evidence_url", ""),
                    "digest_url": f"{base}/digest/{digest.id}",
                },
            )
        )
        queued += 1

    session.flush()
    return queued


def drain(
    session: Session, tracker: TrackerAdapter, now: datetime, *, limit: int = 50
) -> DrainReport:
    """Deliver due outbox rows. Commits after each row, so one bad row cannot
    roll back the issues already created for the others."""
    report = DrainReport()
    rows = (
        session.execute(
            select(TrackerOutbox)
            .where(TrackerOutbox.status == "pending")
            .where(TrackerOutbox.next_attempt_at <= now)
            .order_by(TrackerOutbox.created_at)
            .limit(limit)
        )
        .scalars()
        .all()
    )

    for row in rows:
        team = session.get(Team, row.team_id)
        if tracker.name == "noop":
            _finish(row, "skipped", "no tracker configured (STANDUP_TRACKER=noop)")
            report.skipped += 1
        elif team is None or not team.github_repo:
            _finish(row, "skipped", "team has no github_repo configured")
            report.skipped += 1
        else:
            try:
                action = _deliver(session, tracker, row, team, now)
            except TrackerError as exc:
                row.attempts += 1
                row.last_error = str(exc)[:300]
                if exc.retryable and row.attempts < MAX_ATTEMPTS:
                    delay = exc.retry_after_seconds or min(60 * 2**row.attempts, 86_400)
                    row.next_attempt_at = now + timedelta(seconds=delay)
                    report.retrying += 1
                    log.warning("tracker.retry", outbox_id=row.id, attempts=row.attempts)
                else:
                    row.status = "failed"
                    report.failed += 1
                    log.error("tracker.failed", outbox_id=row.id, error=row.last_error)
            else:
                _finish(row, "done", "")
                report.done += 1
                report.actions.append(action)
        session.commit()

    return report


def _deliver(
    session: Session, tracker: TrackerAdapter, row: TrackerOutbox, team: Team, now: datetime
) -> str:
    repo = team.github_repo or ""
    payload = row.payload_json
    link = session.execute(
        select(TrackerLink).where(TrackerLink.fingerprint == row.fingerprint)
    ).scalar_one_or_none()

    if link is None:
        # Layer 2: the issue may exist although our link row does not (a crash
        # after creating it). Find it by its marker before creating another.
        ref = tracker.find_issue_by_marker(repo, marker(row.fingerprint))
        action = "recovered"
        if ref is None:
            ref = tracker.create_issue(
                repo,
                title=_title(payload["quote"]),
                body=_issue_body(payload, team.name, row.fingerprint),
                labels=[LABEL],
            )
            action = "created"
        link = TrackerLink(
            fingerprint=row.fingerprint,
            team_id=row.team_id,
            member_id=row.member_id,
            provider=tracker.name,
            repo=repo,
            issue_number=ref.number,
            issue_url=ref.url,
            created_at=now,
            last_cycle_id=row.cycle_id,
        )
        session.add(link)
    elif link.last_cycle_id != row.cycle_id:
        tracker.add_comment(repo, link.issue_number, _comment_body(payload))
        link.last_cycle_id = row.cycle_id
        action = "commented"
    else:
        return "unchanged"

    session.flush()
    record_audit(
        session,
        actor_kind="system",
        actor_id="tracker",
        action=AuditAction.TRACKER_WRITE,
        subject_member_id=row.member_id,
        object_ids={
            "outbox_id": row.id,
            "fingerprint": row.fingerprint,
            "issue_number": link.issue_number,
            "write": action,
        },
        purpose="blocker write-back to the team's task tracker",
    )
    log.info("tracker.write", action=action, issue_number=link.issue_number, outbox_id=row.id)
    return action


def _finish(row: TrackerOutbox, status: str, reason: str) -> None:
    row.status = status
    row.last_error = reason


def _title(quote: str) -> str:
    text = " ".join(quote.split())
    return f"Blocker: {text}" if len(text) <= 90 else f"Blocker: {text[:89]}…"


def _quote_block(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines() or [""])


def _issue_body(payload: dict[str, Any], team_name: str, fp: str) -> str:
    return (
        f"**{payload['author']}** reported this blocker in the {team_name} standup "
        f"on {payload['date']}:\n\n"
        f"{_quote_block(payload['quote'])}\n\n"
        f"- Source, verbatim with the cited span highlighted (team sign-in required): "
        f"{payload['evidence_url']}\n"
        f"- Digest: {payload['digest_url']}\n\n"
        "Filed by Status Unblocked. Each later day the same blocker is reported adds a "
        "comment here. The bot never closes issues.\n\n"
        f"{marker(fp)}"
    )


def _comment_body(payload: dict[str, Any]) -> str:
    return (
        f"Still blocked on {payload['date']}:\n\n"
        f"{_quote_block(payload['quote'])}\n\n"
        f"Source: {payload['evidence_url']} · Digest: {payload['digest_url']}"
    )
