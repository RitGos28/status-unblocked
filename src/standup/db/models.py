"""SQLAlchemy schema.

Two things here are load-bearing for the whole project and must not be
"tidied up":

1. ``Update.raw_text`` / ``raw_payload_json`` are **immutable**. They are
   written once at ingestion and never updated. Retention nulls them; nothing
   else touches them. Every citation's verifiability rests on this.

2. ``DigestClaim.citations_json`` deliberately duplicates the quote and its
   offsets. That redundancy is what lets a digest stay verifiable *after*
   retention has purged the raw text, at which point the evidence view renders
   "evidence expired" rather than a broken link.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from standup.domain.enums import CycleState, ItemKind, SourceKind


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[dict[str, Any]]: JSON}


class Team(Base):
    __tablename__ = "team"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    tz_default: Mapped[str] = mapped_column(String(64), default="UTC")
    prompt_local_time: Mapped[str] = mapped_column(String(5), default="09:00")
    cutoff_local_time: Mapped[str] = mapped_column(String(5), default="11:00")
    workdays: Mapped[str] = mapped_column(String(20), default="1,2,3,4,5")
    github_repo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=30)

    members: Mapped[list["Member"]] = relationship(back_populates="team")


class Member(Base):
    __tablename__ = "member"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("team.id"))
    display_name: Mapped[str] = mapped_column(String(200))
    tz: Mapped[str] = mapped_column(String(64), default="UTC")
    # Maps an external identity (Teams aadObjectId, web form handle) to this row.
    source_keys: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    team: Mapped[Team] = relationship(back_populates="members")


class StandupCycle(Base):
    """One standup day for one team."""

    __tablename__ = "standup_cycle"
    __table_args__ = (UniqueConstraint("team_id", "local_date", name="uq_cycle_team_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("team.id"))
    local_date: Mapped[date] = mapped_column(Date)
    opens_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    cutoff_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(16), default=CycleState.OPEN)


class Update(Base):
    """One member's submission for one cycle. Append-only.

    ``raw_text`` is the canonical source every citation resolves against.
    """

    __tablename__ = "update"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("standup_cycle.id"))
    member_id: Mapped[str] = mapped_column(ForeignKey("member.id"))

    # --- immutable evidence ------------------------------------------------
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    # -----------------------------------------------------------------------

    source_kind: Mapped[str] = mapped_column(String(16), default=SourceKind.WEBFORM)
    # Every identifier the source handed us, stored verbatim so a permalink can
    # be backfilled later if the platform ever makes one constructible.
    source_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    permalink: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Why there is no permalink. For Teams 1:1 chats this records that the
    # payload carried an "a:" conversation id, which cannot form a deep link.
    permalink_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    redacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["UpdateItem"]] = relationship(
        back_populates="update", cascade="all, delete-orphan"
    )
    member: Mapped[Member] = relationship()

    @property
    def is_purged(self) -> bool:
        return self.purged_at is not None


class UpdateItem(Base):
    """One progress/blocker/plan sentence, with its exact span in ``raw_text``.

    Invariant, asserted in tests: ``update.raw_text[span_start:span_end] == text``.
    """

    __tablename__ = "update_item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    update_id: Mapped[str] = mapped_column(ForeignKey("update.id"))
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    span_start: Mapped[int] = mapped_column(Integer)
    span_end: Mapped[int] = mapped_column(Integer)
    # Lowercased, stopword-stripped key used to match a blocker across days.
    normalized_key: Mapped[str] = mapped_column(String(500), default="")
    entity_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    order: Mapped[int] = mapped_column(Integer, default=0)

    update: Mapped[Update] = relationship(back_populates="items")

    @property
    def item_kind(self) -> ItemKind:
        return ItemKind(self.kind)


class Digest(Base):
    __tablename__ = "digest"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("standup_cycle.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    summarizer_name: Mapped[str] = mapped_column(String(64))
    summarizer_version: Mapped[str] = mapped_column(String(32))
    validator_report_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    body_md: Mapped[str] = mapped_column(Text, default="")
    # Claims dropped for failing faithfulness validation, or removed by their
    # author. Surfaced in the digest so a gap is never silent.
    withheld_count: Mapped[int] = mapped_column(Integer, default=0)

    claims: Mapped[list["DigestClaim"]] = relationship(
        back_populates="digest", cascade="all, delete-orphan"
    )


class DigestClaim(Base):
    __tablename__ = "digest_claim"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    digest_id: Mapped[str] = mapped_column(ForeignKey("digest.id"))
    kind: Mapped[str] = mapped_column(String(16))
    member_id: Mapped[str] = mapped_column(ForeignKey("member.id"))
    member_name: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    # [{source_id, quote, start, end}, ...] - duplicated on purpose, see module docstring.
    citations_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    extractive: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)

    digest: Mapped[Digest] = relationship(back_populates="claims")


class AuditLog(Base):
    """Hash-chained record of every read of someone's raw update text.

    ``row_hash = sha256(prev_hash || canonical_row)``. Cheap tamper-evidence,
    and it powers the "who looked at your updates" section of /me/data.
    """

    __tablename__ = "audit_log"

    # seq is the primary key because the chain is strictly ordered; a uuid
    # would not give us a deterministic "previous row".
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actor_kind: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    subject_member_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    object_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    purpose: Mapped[str] = mapped_column(String(200), default="")
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    row_hash: Mapped[str] = mapped_column(String(64), default="")
