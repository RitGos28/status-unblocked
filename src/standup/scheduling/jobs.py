"""Run what tick() decides: build due digests, notify, drain the outbox.

This is the I/O half of the scheduler. It loads a snapshot of recent cycles,
asks the pure ``tick()`` what is due, and does it. Called every minute by the
in-app loop (``STANDUP_SCHEDULER=true``) or by ``python -m scripts.tick``.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from standup.db.models import Digest, Member, StandupCycle, Team, Update
from standup.domain.enums import ClaimKind
from standup.logging_conf import get_logger
from standup.scheduling.tick import BuildDigest, CycleView, DrainOutbox, tick
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
    built: list[str] = field(default_factory=list)
    notified: int = 0
    notify_failures: int = 0
    drained: int = 0


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
            .where(Update.superseded_by.is_(None))
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
            )
        )
    return views


async def run_tick(
    session: Session,
    *,
    now: datetime,
    summarizer: Summarizer,
    tracker: TrackerAdapter,
    base_url: str,
    notifier: DigestNotifier | None = None,
) -> TickReport:
    report = TickReport()
    for job in tick(now, load_cycle_views(session, now)):
        if isinstance(job, BuildDigest):
            digest = build_digest(
                session,
                cycle_id=job.cycle_id,
                summarizer=summarizer,
                base_url=base_url,
                now=now,
                actor_id="scheduler",
            )
            session.commit()
            report.built.append(digest.id)
            if job.notify and notifier is not None:
                await _notify_team(session, notifier, digest, base_url, report)
        elif isinstance(job, DrainOutbox):
            report.drained = drain(session, tracker, now).done
    return report


async def _notify_team(
    session: Session,
    notifier: DigestNotifier,
    digest: Digest,
    base_url: str,
    report: TickReport,
) -> None:
    """Post the digest link to every member with a Teams conversation.

    The notice carries a link and a count, never anyone's words: the digest
    itself stays behind sign-in.
    """
    cycle = session.get(StandupCycle, digest.cycle_id)
    team = session.get(Team, cycle.team_id) if cycle else None
    if team is None:
        return
    blockers = sum(1 for c in digest.claims if c.kind == ClaimKind.BLOCKER.value)
    text = (
        f"Today's {team.name} digest is ready ({blockers} blocker"
        f"{'' if blockers == 1 else 's'}): {base_url.rstrip('/')}/digest/{digest.id}"
    )
    members = session.execute(
        select(Member)
        .where(Member.team_id == team.id)
        .where(Member.active.is_(True))
        .where(Member.teams_conversation_ref.is_not(None))
    ).scalars()
    for member in members:
        try:
            await notifier.notify(member.teams_conversation_ref or {}, text)
            report.notified += 1
        except Exception as exc:  # noqa: BLE001 - one unreachable member must not stop the rest
            report.notify_failures += 1
            log.warning("digest.notify_failed", member_id=member.id, error=type(exc).__name__)


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
