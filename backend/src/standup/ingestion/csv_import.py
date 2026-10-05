"""Load made-up (or exported) standup updates from a CSV file.

Columns: date, team, member, progress, blockers, plan, and optionally time
(HH:MM, default 09:00). ``date`` is a UTC date, ``team`` a team slug, ``member``
a member's display name. Each row goes through the same ingest() path as the
web form and Teams, filed at that date and time.

All or nothing: every row is validated first, and one bad row means nothing is
imported, and so does a row dated in the future. A row identical to the
member's current update for that day is skipped, so re-importing a file
changes nothing. A row never replaces a later update the member already has
for that day (``kept_later``). Days that already had a digest are listed in
``stale_digests``: the digest predates the import and needs a rebuild.
Imports are audited as actor "import", not as the member.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.db.models import Digest, Member, StandupCycle, Team, Update
from standup.domain.enums import SourceKind
from standup.domain.timezones import as_utc, local_cycle_date
from standup.ingestion.base import FORM_FIELDS, RawSubmission, text_fields_from
from standup.ingestion.normalizer import normalize
from standup.ingestion.service import ingest

REQUIRED = ("date", "team", "member", *FORM_FIELDS)
DEFAULT_TIME = time(9, 0)


@dataclass
class ImportReport:
    imported: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    # Rows not imported because the member already has a later update that day.
    kept_later: list[str] = field(default_factory=list)
    # "team-slug YYYY-MM-DD" for each day whose existing digest predates the import.
    stale_digests: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Row:
    line: int
    when: datetime
    member: Member
    submission: RawSubmission


def import_updates(
    session: Session, text: str, *, source_name: str, now: datetime | None = None
) -> ImportReport:
    report = ImportReport()
    now = now or datetime.now(UTC)
    # Excel's "CSV UTF-8" starts with a byte-order mark, which would otherwise
    # become part of the first column's name.
    reader = csv.DictReader(io.StringIO(text.removeprefix("\ufeff")))
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        report.errors.append(f"missing column(s): {', '.join(missing)}")
        return report

    rows: list[_Row] = []
    for line, record in enumerate(reader, start=2):  # line 1 is the header
        row = _validate(session, line, record, source_name, now, report.errors)
        if row is not None:
            rows.append(row)
    if report.errors:
        return report  # all or nothing

    for row in rows:
        if _unchanged(session, row):
            report.skipped += 1
            continue
        local_date = local_cycle_date(row.when, row.member.team.tz_default)
        if _has_later_update(session, row, local_date):
            report.kept_later.append(
                f"line {row.line}: {row.member.display_name} already has a later update "
                f"for {local_date}"
            )
            continue
        ingest(
            session,
            row.submission,
            row.member,
            row.when,
            permalink_reason="csv import: no platform message to link to",
            actor_kind="import",
            actor_id=f"csv:{source_name}",
        )
        report.imported += 1
        day = f"{row.member.team.slug} {local_date}"
        if day not in report.stale_digests and _has_digest(session, row, local_date):
            report.stale_digests.append(day)
    return report


def _validate(
    session: Session,
    line: int,
    record: dict[str, str],
    source_name: str,
    now: datetime,
    errors: list[str],
) -> _Row | None:
    def value(column: str) -> str:
        return (record.get(column) or "").strip()

    try:
        day = date.fromisoformat(value("date"))
    except ValueError:
        errors.append(f"line {line}: date {value('date')!r} is not YYYY-MM-DD")
        return None
    try:
        at = time.fromisoformat(value("time")) if value("time") else DEFAULT_TIME
    except ValueError:
        errors.append(f"line {line}: time {value('time')!r} is not HH:MM")
        return None

    team = session.execute(select(Team).where(Team.slug == value("team"))).scalar_one_or_none()
    if team is None:
        errors.append(f"line {line}: no team with slug {value('team')!r}")
        return None
    member = session.execute(
        select(Member)
        .where(Member.team_id == team.id)
        .where(Member.display_name == value("member"))
        .where(Member.active.is_(True))
    ).scalar_one_or_none()
    if member is None:
        errors.append(f"line {line}: no active member {value('member')!r} in team {team.slug!r}")
        return None

    fields = text_fields_from({name: value(name) for name in FORM_FIELDS})
    if not any(fields.values()):
        errors.append(f"line {line}: progress, blockers and plan are all empty")
        return None

    when = datetime.combine(day, at, tzinfo=UTC)
    if when > now:
        errors.append(f"line {line}: {day} {at:%H:%M} UTC is in the future")
        return None
    submission = RawSubmission(
        source_kind=SourceKind.CSV,
        external_user_key=member.id,
        text_fields=fields,
        captured_at=when,
        source_ids={"adapter": "csv", "file": source_name, "line": line},
        raw_payload=dict(record),
    )
    return _Row(line=line, when=when, member=member, submission=submission)


def _unchanged(session: Session, row: _Row) -> bool:
    """True when the member's current update that day has exactly this text."""
    local_date = local_cycle_date(row.when, row.member.team.tz_default)
    current = (
        session.execute(
            select(Update.content_sha256)
            .join(StandupCycle, Update.cycle_id == StandupCycle.id)
            .where(StandupCycle.team_id == row.member.team_id)
            .where(StandupCycle.local_date == local_date)
            .where(Update.member_id == row.member.id)
            .where(Update.is_live())
        )
        .scalars()
        .all()
    )
    return normalize(row.submission).content_sha256 in current


def _has_later_update(session: Session, row: _Row, local_date: date) -> bool:
    captured = session.execute(
        select(Update.captured_at)
        .join(StandupCycle, Update.cycle_id == StandupCycle.id)
        .where(StandupCycle.team_id == row.member.team_id)
        .where(StandupCycle.local_date == local_date)
        .where(Update.member_id == row.member.id)
        .where(Update.is_live())
    ).scalars()
    return any(as_utc(at) > row.when for at in captured)


def _has_digest(session: Session, row: _Row, local_date: date) -> bool:
    return (
        session.execute(
            select(Digest.id)
            .join(StandupCycle, Digest.cycle_id == StandupCycle.id)
            .where(StandupCycle.team_id == row.member.team_id)
            .where(StandupCycle.local_date == local_date)
            .limit(1)
        ).first()
        is not None
    )
