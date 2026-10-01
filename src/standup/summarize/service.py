"""Digest orchestration: build request, summarize, validate, persist.

This module owns the invariant that makes the whole faithfulness claim hold:
the validator runs **here**, after the summarizer returns, and a summarizer
never gets to call it. Swap in an LLM and the check still happens.

It is also the mapping layer between the ORM and the pure domain types, which
is what keeps ``summarize/`` free of database imports.
"""

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.config import get_settings
from standup.domain.enums import AuditAction, CycleState, ItemKind
from standup.domain.errors import NotFoundError, ValidationFailure
from standup.logging_conf import get_logger
from standup.privacy.audit import record_audit
from standup.summarize.base import (
    SourceDoc,
    Summarizer,
    SummaryRequest,
)
from standup.summarize.render import render_markdown
from standup.summarize.validator import FaithfulnessValidator

if TYPE_CHECKING:
    from standup.db.models import Digest

log = get_logger(__name__)


def evidence_url(base_url: str, item_id: str) -> str:
    return f"{base_url.rstrip('/')}/evidence/{item_id}"


def build_request(session: Session, cycle_id: str, base_url: str) -> SummaryRequest:
    """Map persisted updates into the summarizer's input surface.

    Note what does *not* cross this boundary: ORM objects, the session, member
    identifiers from the source platform, and any purged update's text.
    """
    from standup.db.models import StandupCycle, Team, Update, UpdateItem

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
            .where(Update.purged_at.is_(None))
            .order_by(UpdateItem.order)
        )
        .tuples()
        .all()
    )

    sources: list[SourceDoc] = []
    for item, update in rows:
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
            )
        )

    return SummaryRequest(
        cycle_date=cycle.local_date,
        team_name=team_name,
        sources=tuple(sources),
    )


def build_digest(
    session: Session,
    *,
    cycle_id: str,
    summarizer: Summarizer,
    base_url: str,
    actor_id: str = "system",
) -> "Digest":
    """Produce and persist a digest for one cycle.

    Returns the persisted ``Digest`` row.
    """
    from standup.db.models import Digest, DigestClaim, StandupCycle

    settings = get_settings()
    request = build_request(session, cycle_id, base_url)

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

    evidence_urls = {s.id: s.evidence_url for s in request.sources}
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
        session.add(
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
