"""Enumerations shared across layers. Pure: imports nothing from this project."""

from enum import StrEnum


class SourceKind(StrEnum):
    """Where an update came in from. One value per ingestion adapter."""

    WEBFORM = "webform"
    TEAMS = "teams"
    CLI = "cli"


class ItemKind(StrEnum):
    """The three things a standup update is made of."""

    PROGRESS = "progress"
    BLOCKER = "blocker"
    PLAN = "plan"


class ClaimKind(StrEnum):
    """What a digest line asserts.

    CARRYOVER is a blocker that was already open in an earlier cycle; it cites
    both the original and the current source.
    """

    PROGRESS = "progress"
    BLOCKER = "blocker"
    PLAN = "plan"
    CARRYOVER = "carryover"


class CycleState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    DIGESTED = "digested"


class AuditAction(StrEnum):
    """Every action that reads or derives from someone's raw update text."""

    UPDATE_INGESTED = "update.ingested"
    EVIDENCE_VIEWED = "evidence.viewed"
    DIGEST_BUILT = "digest.built"
    DIGEST_VIEWED = "digest.viewed"
    DATA_EXPORTED = "data.exported"
    DATA_DELETED = "data.deleted"
    TRACKER_WRITE = "tracker.write"
