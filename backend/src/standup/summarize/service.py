"""Digest orchestration: build request, summarize, validate, persist.

This module owns the invariant that makes the whole faithfulness claim hold:
the validator runs **here**, after the summarizer returns, and a summarizer
never gets to call it. Swap in an LLM and the check still happens.

It is also the mapping layer between the ORM and the pure domain types, which
is what keeps ``summarize/`` free of database imports.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.orm import Session

from standup.config import get_settings
from standup.db.models import Digest, DigestClaim, StandupCycle, Team, Update, UpdateItem
from standup.domain.enums import BLOCKER_KINDS, AuditAction, CycleState, ItemKind
from standup.domain.errors import ConflictError, NotFoundError, ValidationFailure
from standup.domain.text import content_sha256
from standup.domain.urls import evidence_url
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit
from standup.privacy.retention import day_was_purged
from standup.summarize.base import (
    SourceDoc,
    Summarizer,
    SummaryRequest,
)
from standup.summarize.render import render_markdown
from standup.summarize.validator import FaithfulnessValidator
from standup.tracker.outbox import enqueue_blocker_issues

log = get_logger(__name__)

# How far back a blocker counts as "reported before" for carry-over.
CARRYOVER_DAYS = 7


def build_request(session: Session, cycle_id: str, base_url: str) -> SummaryRequest:
    """Map persisted updates into the summarizer's input surface.

    Note what does *not* cross this boundary: ORM objects, the session, member
    identifiers from the source platform, and any purged update's text.
    """
    cycle = session.get(StandupCycle, cycle_id)
    if cycle is None:
        raise NotFoundError(f"cycle {cycle_id} not found")

    team = session.get(Team, cycle.team_id)
    team_name = team.name if team else "Team"

    rows = (
        session.execute(
            select(UpdateItem, Update)
            .join(Update, UpdateItem.update_id == Update.id)
            .where(Update.cycle_id == cycle_id)
            # Not purged, and a resubmission replaces the earlier update.
            .where(Update.is_live())
            .order_by(UpdateItem.order)
        )
        .tuples()
        .all()
    )

    sources: list[SourceDoc] = []
    for item, update in rows:
        if item.text is None:  # removed by retention; live updates never are
            continue
        sources.append(
            SourceDoc(
                id=item.id,
                member_id=update.member_id,
                member_name=update.member.display_name,
                kind=ItemKind(item.kind),
                text=item.text,
                captured_at=update.captured_at,
                evidence_url=evidence_url(base_url, item.id),
                permalink=update.permalink,
                normalized_key=item.normalized_key,
                entity_refs=tuple(e.get("value", "") for e in (item.entity_refs or [])),
                standup_day=cycle.local_date,
            )
        )

    return SummaryRequest(
        cycle_date=cycle.local_date,
        team_name=team_name,
        sources=tuple(sources),
        prior_open_blockers=_prior_blockers(session, cycle, base_url),
    )


def _prior_blockers(
    session: Session, cycle: "StandupCycle", base_url: str
) -> tuple[SourceDoc, ...]:
    """Blockers this team reported in the CARRYOVER_DAYS before ``cycle``.

    Taken from earlier digests' blocker and carry-over claims, so a promoted
    blocker counts too. Each becomes a citable SourceDoc; the summarizer uses
    them to mark a blocker reported again as "Still blocked". Items whose text
    retention has removed are skipped: there is nothing left to cite.
    """
    since = cycle.local_date - timedelta(days=CARRYOVER_DAYS)
    claims = session.execute(
        select(DigestClaim)
        .join(Digest, DigestClaim.digest_id == Digest.id)
        .join(StandupCycle, Digest.cycle_id == StandupCycle.id)
        .where(StandupCycle.team_id == cycle.team_id)
        .where(StandupCycle.local_date < cycle.local_date)
        .where(StandupCycle.local_date >= since)
        .where(DigestClaim.kind.in_(sorted(BLOCKER_KINDS)))
    ).scalars()

    item_ids = {c["source_id"] for claim in claims for c in claim.citations_json}
    prior: list[SourceDoc] = []
    for item_id in sorted(item_ids):
        item = session.get(UpdateItem, item_id)
        update = session.get(Update, item.update_id) if item else None
        if item is None or update is None or not item.text or update.purged_at is not None:
            continue
        earlier_cycle = session.get(StandupCycle, update.cycle_id)
        prior.append(
            SourceDoc(
                id=item.id,
                member_id=update.member_id,
                member_name=update.member.display_name,
                kind=ItemKind(item.kind),
                text=item.text,
                captured_at=update.captured_at,
                evidence_url=evidence_url(base_url, item.id),
                permalink=update.permalink,
                normalized_key=item.normalized_key,
                standup_day=earlier_cycle.local_date if earlier_cycle else None,
            )
        )
    return tuple(prior)


def build_digest(
    session: Session,
    *,
    cycle_id: str,
    summarizer: Summarizer,
    base_url: str,
    now: datetime,
    actor_id: str = "system",
) -> "Digest":
    """Produce and persist a digest for one cycle.

    Returns the persisted ``Digest`` row.
    """
    settings = get_settings()
    if day_was_purged(session, cycle_id):
        raise ConflictError(
            "This day's updates were removed under the team's retention policy, so there is "
            "nothing to rebuild from. Its digest stays as it was."
        )
    # One build of a day at a time: bump the day's counter first, which takes
    # its row lock until commit. A concurrent build waits here, then sees this
    # one's digest (no SAVEPOINT needed, which pysqlite lacks).
    session.execute(
        sql_update(StandupCycle)
        .where(StandupCycle.id == cycle_id)
        .values(build_seq=StandupCycle.build_seq + 1)
    )
    build_seq = session.execute(
        select(StandupCycle.build_seq).where(StandupCycle.id == cycle_id)
    ).scalar_one()
    request = build_request(session, cycle_id, base_url)
    inputs = _inputs_sha256(request, summarizer)
    current = latest_digest(session, cycle_id)
    if current is not None and current.inputs_sha256 == inputs:
        return current  # nothing changed: a second click is not a second digest

    result = summarizer.summarize(request)

    # The check the entire project rests on. Never move this inside a summarizer.
    kept, report = FaithfulnessValidator().validate(result, request)

    if report.violations:
        for violation in report.violations:
            log.warning(
                "claim.rejected",
                rule=violation.rule,
                detail=violation.detail,
                summarizer=result.summarizer_name,
            )
        if settings.validator_strict:
            raise ValidationFailure(
                f"{len(report.violations)} claim(s) failed faithfulness validation"
            )

    evidence_urls = {s.id: s.evidence_url for s in (*request.sources, *request.prior_open_blockers)}
    body_md = render_markdown(
        team_name=request.team_name,
        cycle_date=request.cycle_date.isoformat(),
        claims=kept,
        evidence_urls=evidence_urls,
        withheld_count=report.withheld,
        truncated_count=result.truncated,
    )

    digest = Digest(
        cycle_id=cycle_id,
        generated_at=now,
        build_seq=build_seq,
        inputs_sha256=inputs,
        summarizer_name=result.summarizer_name,
        summarizer_version=result.summarizer_version,
        validator_report_json=report.to_dict(),
        body_md=body_md,
        withheld_count=report.withheld,
        truncated_count=result.truncated,
    )
    session.add(digest)
    session.flush()

    for order, claim in enumerate(kept):
        digest.claims.append(
            DigestClaim(
                digest_id=digest.id,
                kind=claim.kind.value,
                member_id=claim.member_id,
                member_name=claim.member_name,
                text=claim.text,
                # Quote and offsets duplicated deliberately: this is what keeps
                # a digest verifiable after retention purges the raw text.
                citations_json=[
                    {
                        "source_id": c.source_id,
                        "quote": c.quote,
                        "start": c.start,
                        "end": c.end,
                        "evidence_url": evidence_urls.get(c.source_id, ""),
                    }
                    for c in claim.citations
                ],
                extractive=claim.extractive,
                matched_rule=claim.matched_rule,
                order=order,
            )
        )

    cycle = session.get(StandupCycle, cycle_id)
    if cycle is not None:
        cycle.state = CycleState.DIGESTED
        # Blocker write-back is queued here and delivered later by the outbox
        # drain, so the tracker can never slow down or fail a digest.
        enqueue_blocker_issues(session, digest, cycle, base_url, now)

    record_audit(
        session,
        actor_kind="system",
        actor_id=actor_id,
        action=AuditAction.DIGEST_BUILT,
        object_ids={"digest_id": digest.id, "cycle_id": cycle_id},
        purpose="daily digest generation",
    )

    session.flush()
    log.info(
        "digest.built",
        digest_id=digest.id,
        cycle_id=cycle_id,
        claims=len(kept),
        withheld=report.withheld,
        summarizer=result.summarizer_name,
    )
    return digest


def latest_digest(session: Session, cycle_id: str) -> "Digest | None":
    """The day's most recently built digest. By build order, never by clock."""
    return session.execute(
        select(Digest)
        .where(Digest.cycle_id == cycle_id)
        .order_by(Digest.build_seq.desc(), Digest.generated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _inputs_sha256(request: SummaryRequest, summarizer: Summarizer) -> str:
    """A fingerprint of everything a digest is built from."""

    def doc(s: SourceDoc) -> list[str]:
        return [s.id, s.kind.value, s.member_id, s.member_name, s.text, str(s.standup_day)]

    return content_sha256(
        json.dumps(
            {
                "summarizer": [summarizer.name, summarizer.version],
                "day": request.cycle_date.isoformat(),
                "team": request.team_name,
                "sources": [doc(s) for s in request.sources],
                "earlier": [doc(s) for s in request.prior_open_blockers],
            },
            sort_keys=True,
        )
    )
