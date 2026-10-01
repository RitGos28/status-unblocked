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
    and_,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import ColumnElement

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
    # The member's Teams identity (aadObjectId), set when they link their
    # account with a code from the web app. Unique: one Teams account can
    # speak for exactly one member.
    teams_aad_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True, default=None
    )
    # Where to reach this member proactively in Teams: the conversation
    # reference from their latest 1:1 turn with the bot. Only the scheduler's
    # "digest is ready" notice uses it.
    # none_as_null: store SQL NULL, not JSON 'null', so "IS NOT NULL" means
    # "has a conversation".
    teams_conversation_ref: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True, default=None
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bumped by every submission. Its real job is the row lock that the
    # UPDATE takes, which serialises one member's concurrent submissions.
    submission_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

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
    # When the team was told this cycle's digest is ready. Exactly one notice
    # per cycle, whoever built the digest and whenever.
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


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
    # Set when the same member resubmits in the same cycle. The newer update is
    # the one the digest uses; this row's text is never edited (invariant 2),
    # so old digests that cited it still resolve.
    superseded_by: Mapped[str | None] = mapped_column(
        ForeignKey("update.id"), nullable=True, default=None
    )

    items: Mapped[list["UpdateItem"]] = relationship(
        back_populates="update", cascade="all, delete-orphan"
    )
    member: Mapped[Member] = relationship()

    @property
    def is_purged(self) -> bool:
        return self.purged_at is not None

    @classmethod
    def is_live(cls) -> ColumnElement[bool]:
        """SQL filter for the updates that count: not superseded, not purged.

        The single definition. Anything that asks "does this cycle have
        updates", or "which update is this member's current one", uses it.
        """
        return and_(cls.superseded_by.is_(None), cls.purged_at.is_(None))


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
    # Claims cut by the per-section line limit. Also surfaced, so a long
    # digest never loses lines without saying so.
    truncated_count: Mapped[int] = mapped_column(Integer, default=0)

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
    # Why the claim is in its section, e.g. "field:progress" or
    # "promoted:marker:stuck". Persisted so a classification stays explainable
    # after the build, not just while the summarizer is running.
    matched_rule: Mapped[str] = mapped_column(String(120), default="")
    # For blocker claims: the fingerprint linking this line to its tracker
    # issue (see tracker/idempotency.py). Empty for every other claim.
    tracker_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    order: Mapped[int] = mapped_column(Integer, default=0)

    digest: Mapped[Digest] = relationship(back_populates="claims")


class AuditLog(Base):
    """Hash-chained record of every read of someone's raw update text.

    ``row_hash = sha256(prev_hash || canonical_row)``. Cheap tamper-evidence,
    and it powers the "who looked at your updates" section of /me/data.
    """

    __tablename__ = "audit_log"
    # A second row naming the same predecessor would be a fork. The append
    # path serialises on AuditChainHead so this never fires; if it ever does,
    # the write fails loudly instead of silently forking the chain.
    __table_args__ = (UniqueConstraint("prev_hash", name="uq_audit_log_prev_hash"),)

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


class AuditChainHead(Base):
    """One row (id=1) that every audit append locks before reading the chain.

    Appending reads the last row's hash and inserts the next row. Without a
    lock, two requests can read the same last row and fork the chain. Updating
    this row first makes concurrent appends queue up, on SQLite and Postgres
    alike, without SAVEPOINT (which pysqlite does not support by default).
    """

    __tablename__ = "audit_chain_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)


class IngestRejection(Base):
    """One message the bot refused to ingest because it was out of scope.

    This is the ``scope_violation`` counter. Deliberately content-free: no
    text, no sender, no conversation id. Recording *what* was refused would be
    the very collection the refusal exists to prevent.
    """

    __tablename__ = "ingest_rejection"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    source: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(64))
    conversation_type: Mapped[str] = mapped_column(String(32), default="")


class TrackerLink(Base):
    """One blocker's issue in the task tracker.

    ``fingerprint`` is UNIQUE: the first of the three idempotency layers that
    guarantee a recurring blocker never opens a second issue.
    """

    __tablename__ = "tracker_link"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("team.id"))
    member_id: Mapped[str] = mapped_column(ForeignKey("member.id"))
    provider: Mapped[str] = mapped_column(String(16))
    repo: Mapped[str] = mapped_column(String(200))
    issue_number: Mapped[int] = mapped_column(Integer)
    issue_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # The latest cycle that has been written to the issue, so a recurrence adds
    # one comment per cycle and a rebuild of the same day adds none.
    last_cycle_id: Mapped[str] = mapped_column(String(36))


class TrackerOutbox(Base):
    """A pending write to the task tracker.

    Digest building only enqueues these; a separate drain step performs the
    HTTP calls with backoff, so a tracker outage can never block a digest or
    lose an update (invariant 8). One row per blocker per cycle.
    """

    __tablename__ = "tracker_outbox"
    __table_args__ = (
        UniqueConstraint("fingerprint", "cycle_id", name="uq_outbox_fingerprint_cycle"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    fingerprint: Mapped[str] = mapped_column(String(64))
    team_id: Mapped[str] = mapped_column(ForeignKey("team.id"))
    member_id: Mapped[str] = mapped_column(ForeignKey("member.id"))
    cycle_id: Mapped[str] = mapped_column(ForeignKey("standup_cycle.id"))
    digest_id: Mapped[str] = mapped_column(ForeignKey("digest.id"))
    # What the issue or comment needs: title, quote, author, date, links.
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # pending -> done | skipped | failed
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # A short, secret-free reason for the last failure or skip.
    last_error: Mapped[str] = mapped_column(String(300), default="")


class Lease(Base):
    """A named, expiring "only one runner at a time" lease (see db/lease.py)."""

    __tablename__ = "lease"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    holder: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
