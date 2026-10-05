"""Blocker write-back through an outbox.

``enqueue_blocker_issues`` runs inside the digest build and only writes rows to
our own database. ``drain`` runs afterwards (a background task after a build,
or the scheduler) and performs the tracker calls. So a tracker outage, a bad
token or a rate limit can delay an issue but never block or lose a digest
(invariant 8).

Each blocker becomes one issue. The same blocker reported on a later day adds
one comment to that issue. The bot never closes issues; people do.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.db.lease import acquire_lease, release_lease
from standup.db.models import (
    Digest,
    StandupCycle,
    Team,
    TrackerLink,
    TrackerOutbox,
    UpdateItem,
)
from standup.domain.enums import AuditAction, ClaimKind
from standup.domain.urls import digest_url
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit
from standup.tracker.base import TrackerAdapter, TrackerError
from standup.tracker.idempotency import LABEL, fingerprint, marker

log = get_logger(__name__)

MAX_ATTEMPTS = 8
_BLOCKER_KINDS = {ClaimKind.BLOCKER.value, ClaimKind.CARRYOVER.value}


@dataclass
class DrainReport:
    busy: bool = False
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
                    "digest_url": digest_url(base, digest.id),
                },
            )
        )
        queued += 1

    session.flush()
    return queued


# How far back requeue_skipped reaches: the same week carry-over looks back,
# so connecting a repo files this week's blockers, not every blocker ever.
REQUEUE_WINDOW = timedelta(days=7)


def requeue_skipped(session: Session, team_id: str, now: datetime) -> int:
    """Queue again the team's recent rows skipped for lack of a tracker or repo.

    Call it after configuring one, so blockers reported before that are filed
    too. Returns how many rows were requeued; the next drain delivers them.
    """
    rows = session.execute(
        select(TrackerOutbox)
        .where(TrackerOutbox.team_id == team_id)
        .where(TrackerOutbox.status == "skipped")
        .where(TrackerOutbox.created_at >= now - REQUEUE_WINDOW)
    ).scalars().all()
    for row in rows:
        row.status = "pending"
        row.next_attempt_at = now
        row.last_error = ""
    session.flush()
    return len(rows)


DRAIN_LEASE = "outbox-drain"
DRAIN_LEASE_TTL = timedelta(minutes=5)


def drain(
    session: Session, tracker: TrackerAdapter, now: datetime, *, limit: int = 50
) -> DrainReport:
    """Deliver due outbox rows. Commits after each row, so one bad row cannot
    roll back the issues already created for the others.

    Single-runner: a drain must hold the outbox-drain lease, otherwise it
    returns at once (``busy``). Two drains at the same moment would both see
    "no issue yet" for a blocker and both create one, even for two different
    rows of the same blocker, so per-row claims are not enough.
    """
    holder = str(uuid.uuid4())
    if not acquire_lease(session, DRAIN_LEASE, holder, now, DRAIN_LEASE_TTL):
        log.info("tracker.drain_busy")
        return DrainReport(busy=True)
    try:
        return _drain_rows(session, tracker, now, limit)
    finally:
        session.rollback()
        release_lease(session, DRAIN_LEASE, holder)


def _drain_rows(
    session: Session, tracker: TrackerAdapter, now: datetime, limit: int
) -> DrainReport:
    report = DrainReport()
    rows = (
        session.execute(
            select(TrackerOutbox)
            .join(StandupCycle, TrackerOutbox.cycle_id == StandupCycle.id)
            .where(TrackerOutbox.status == "pending")
            .where(TrackerOutbox.next_attempt_at <= now)
            # Oldest standup day first: one pass may queue several days (a
            # backfill), and the first day must open the issue that later days
            # comment on, not the other way round.
            .order_by(StandupCycle.local_date, TrackerOutbox.created_at)
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
                body=_issue_body(payload, team, row.fingerprint),
                labels=[LABEL, f"team:{team.slug}"],
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
        days = link.days_reported + 1
        tracker.add_comment(repo, link.issue_number, _comment_body(payload, row.fingerprint, days))
        link.last_cycle_id = row.cycle_id
        link.days_reported = days
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


def _json_block(record: dict[str, Any]) -> str:
    """A fenced JSON block: the structured part of an issue or comment, for
    anything that reads the tracker (dashboards, scripts, other bots)."""
    return "```json\n" + json.dumps(record, indent=2, sort_keys=True) + "\n```"


def _issue_body(payload: dict[str, Any], team: Team, fp: str) -> str:
    record = {
        "standup_blocker": {
            "fingerprint": fp,
            "team": team.slug,
            "reported_by": payload["author"],
            "quote": payload["quote"],
            "first_reported": payload["date"],
            "days_reported": 1,
            "evidence_url": payload["evidence_url"],
            "digest_url": payload["digest_url"],
        }
    }
    return (
        f"**{payload['author']}** reported this blocker in the {team.name} standup "
        f"on {payload['date']}:\n\n"
        f"{_quote_block(payload['quote'])}\n\n"
        f"- Source, verbatim with the cited span highlighted (team sign-in required): "
        f"{payload['evidence_url']}\n"
        f"- Digest: {payload['digest_url']}\n\n"
        "Filed by Status Unblocked. Each later day the same blocker is reported adds a "
        "comment here. The bot never closes issues.\n\n"
        f"{_json_block(record)}\n\n"
        f"{marker(fp)}"
    )


def _comment_body(payload: dict[str, Any], fp: str, days_reported: int) -> str:
    record = {
        "standup_blocker_update": {
            "fingerprint": fp,
            "date": payload["date"],
            "days_reported": days_reported,
            "evidence_url": payload["evidence_url"],
            "digest_url": payload["digest_url"],
        }
    }
    return (
        f"Still blocked on {payload['date']} (reported on {days_reported} days):\n\n"
        f"{_quote_block(payload['quote'])}\n\n"
        f"Source: {payload['evidence_url']} · Digest: {payload['digest_url']}\n\n"
        f"{_json_block(record)}"
    )
