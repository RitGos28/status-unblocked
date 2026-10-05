"""Run what tick() decides: build due digests, notify, drain the outbox.

This is the I/O half of the scheduler. It loads a snapshot of recent cycles,
asks the pure ``tick()`` what is due, and does it. Called every minute by the
in-app loop (``STANDUP_SCHEDULER=true``) or by ``python -m scripts.tick``.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from standup.db.lease import acquire_lease, release_lease
from standup.db.models import Digest, Member, StandupCycle, Team, Update
from standup.domain.enums import ClaimKind
from standup.domain.errors import ConfigurationError
from standup.logging_conf import get_logger
from standup.privacy.retention import purge_expired
from standup.scheduling.tick import (
    BuildDigest,
    CycleView,
    DrainOutbox,
    NotifyDigest,
    PurgeExpired,
    tick,
)
from standup.summarize.base import Summarizer
from standup.summarize.service import build_digest
from standup.tracker.base import TrackerAdapter
from standup.tracker.outbox import drain

log = get_logger(__name__)

# Cycles older than this are left alone: the scheduler is for today's work,
# not for rewriting last month's history.
LOOKBACK = timedelta(days=7)


class DigestNotifier(Protocol):
    """Tells a member a digest is ready. Teams is the one implementation."""

    async def notify(self, conversation_ref: dict[str, Any], text: str) -> None: ...


@dataclass
class TickReport:
    busy: bool = False
    built: list[str] = field(default_factory=list)
    notified: int = 0
    notify_failures: int = 0
    drained: int = 0
    purged: int = 0


def _aware(value: datetime | None) -> datetime | None:
    # SQLite hands back naive datetimes; every stored value is UTC.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def load_cycle_views(session: Session, now: datetime) -> list[CycleView]:
    since = (now - LOOKBACK).date()
    cycles = session.execute(
        select(StandupCycle).where(StandupCycle.local_date >= since)
    ).scalars()
    views: list[CycleView] = []
    for cycle in cycles:
        update_count, last_update = session.execute(
            select(func.count(Update.id), func.max(Update.captured_at))
            .where(Update.cycle_id == cycle.id)
            .where(Update.is_live())
        ).one()
        last_digest = session.execute(
            select(func.max(Digest.generated_at)).where(Digest.cycle_id == cycle.id)
        ).scalar()
        views.append(
            CycleView(
                cycle_id=cycle.id,
                cutoff_at=_aware(cycle.cutoff_at_utc),
                has_updates=update_count > 0,
                last_update_at=_aware(last_update),
                last_digest_at=_aware(last_digest),
                notified=cycle.notified_at is not None,
            )
        )
    return views


SCHEDULER_LEASE = "scheduler"
SCHEDULER_LEASE_TTL = timedelta(minutes=10)


async def run_tick(
    session: Session,
    *,
    now: datetime,
    summarizer: Summarizer,
    tracker: TrackerAdapter,
    base_url: str,
    notifier: DigestNotifier | None = None,
) -> TickReport:
    """One pass: build due digests, send due notices, drain the outbox.

    Single-runner: it must hold the scheduler lease, so several workers, or
    cron plus the in-app loop, never build or announce the same digest twice.
    Every database and HTTP step runs in a worker thread, off the event loop,
    so a slow pass never stalls the web app. The session is used by one thread
    at a time, in sequence.
    """
    if not base_url:
        raise ConfigurationError(
            "STANDUP_BASE_URL is required for scheduled digests: their links go into "
            "GitHub issues and Teams notices, where a relative link is useless"
        )
    holder = str(uuid.uuid4())
    acquired = await asyncio.to_thread(
        acquire_lease, session, SCHEDULER_LEASE, holder, now, SCHEDULER_LEASE_TTL
    )
    if not acquired:
        log.info("scheduler.busy")
        return TickReport(busy=True)
    try:
        return await _run_jobs(session, now, summarizer, tracker, base_url, notifier)
    finally:
        await asyncio.to_thread(_finish, session, holder)


def _finish(session: Session, holder: str) -> None:
    session.rollback()
    release_lease(session, SCHEDULER_LEASE, holder)


async def _run_jobs(
    session: Session,
    now: datetime,
    summarizer: Summarizer,
    tracker: TrackerAdapter,
    base_url: str,
    notifier: DigestNotifier | None,
) -> TickReport:
    report = TickReport()
    jobs = await asyncio.to_thread(lambda: tick(now, load_cycle_views(session, now)))
    for job in jobs:
        if isinstance(job, BuildDigest):
            digest_id = await asyncio.to_thread(
                _build, session, job.cycle_id, summarizer, base_url, now
            )
            report.built.append(digest_id)
            if job.notify:
                await _announce(session, notifier, job.cycle_id, base_url, now, report)
        elif isinstance(job, NotifyDigest):
            await _announce(session, notifier, job.cycle_id, base_url, now, report)
        elif isinstance(job, PurgeExpired):
            report.purged = await asyncio.to_thread(_purge, session, now)
        elif isinstance(job, DrainOutbox):
            drained = await asyncio.to_thread(drain, session, tracker, now)
            report.drained = drained.done
    return report


def _purge(session: Session, now: datetime) -> int:
    purged = purge_expired(session, now)
    session.commit()
    return purged


def _build(
    session: Session, cycle_id: str, summarizer: Summarizer, base_url: str, now: datetime
) -> str:
    digest = build_digest(
        session,
        cycle_id=cycle_id,
        summarizer=summarizer,
        base_url=base_url,
        now=now,
        actor_id="scheduler",
    )
    session.commit()
    return digest.id


async def _announce(
    session: Session,
    notifier: DigestNotifier | None,
    cycle_id: str,
    base_url: str,
    now: datetime,
    report: TickReport,
) -> None:
    """Tell the team their digest is ready, once per cycle.

    The notice carries a link and a count, never anyone's words: the digest
    itself stays behind sign-in. The cycle is marked notified even when no one
    can be reached (Teams off, or no linked members), so it is not retried.
    """
    text, references = await asyncio.to_thread(_notice, session, cycle_id, base_url)
    if notifier is not None:
        for member_id, reference in references:
            try:
                await notifier.notify(reference, text)
                report.notified += 1
            except Exception as exc:  # noqa: BLE001 - one unreachable member must not stop the rest
                report.notify_failures += 1
                log.warning("digest.notify_failed", member_id=member_id, error=type(exc).__name__)
    await asyncio.to_thread(_mark_notified, session, cycle_id, now)


def _notice(
    session: Session, cycle_id: str, base_url: str
) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    cycle = session.get(StandupCycle, cycle_id)
    team = session.get(Team, cycle.team_id) if cycle else None
    digest = session.execute(
        select(Digest).where(Digest.cycle_id == cycle_id).order_by(Digest.generated_at.desc())
    ).scalars().first()
    if cycle is None or team is None or digest is None:
        return "", []
    # Carried-over blockers are blockers too: the page shows them first.
    blocker_kinds = {ClaimKind.BLOCKER.value, ClaimKind.CARRYOVER.value}
    blockers = sum(1 for c in digest.claims if c.kind in blocker_kinds)
    carried = sum(1 for c in digest.claims if c.kind == ClaimKind.CARRYOVER.value)
    counts = f"{blockers} blocker{'' if blockers == 1 else 's'}"
    if carried:
        counts += f", {carried} still open from an earlier day"
    # Name the digest's own date: a pass can announce yesterday's digest too.
    text = (
        f"The {team.name} digest for {cycle.local_date} is ready ({counts}): "
        f"{base_url.rstrip('/')}/digest/{digest.id}"
    )
    members = session.execute(
        select(Member)
        .where(Member.team_id == team.id)
        .where(Member.active.is_(True))
        .where(Member.teams_conversation_ref.is_not(None))
    ).scalars()
    return text, [(m.id, m.teams_conversation_ref or {}) for m in members]


def _mark_notified(session: Session, cycle_id: str, now: datetime) -> None:
    cycle = session.get(StandupCycle, cycle_id)
    if cycle is not None:
        cycle.notified_at = now
    session.commit()


async def run_once(notifier: DigestNotifier | None = None) -> TickReport:
    """One scheduler pass with the app's own settings, clock and session."""
    from standup.config import get_settings
    from standup.db.session import session_scope
    from standup.deps import get_clock, get_summarizer, tracker_from_settings

    settings = get_settings()
    with session_scope() as session:
        report = await run_tick(
            session,
            now=get_clock().now(),
            summarizer=get_summarizer(settings),
            tracker=tracker_from_settings(settings),
            base_url=settings.base_url,
            notifier=notifier,
        )
    if report.built or report.drained or report.notify_failures:
        log.info(
            "scheduler.tick",
            built=len(report.built),
            notified=report.notified,
            notify_failures=report.notify_failures,
            drained=report.drained,
        )
    return report
