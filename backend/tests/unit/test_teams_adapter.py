"""Teams adapter tests.

TeamsAdapter must produce the exact same RawSubmission shape WebFormAdapter
does, from a real Microsoft Agents SDK Activity instead of posted form
fields. If this drifts, the Teams path silently stops being a first-class
citizen of the citation pipeline.
"""

from datetime import UTC, datetime

from microsoft_agents.activity import Activity

from standup.domain.enums import ItemKind, SourceKind
from standup.ingestion.teams_adapter import TeamsAdapter

CAPTURED_AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def make_activity(
    progress: str = "",
    blockers: str = "",
    plan: str = "",
    aad_object_id: str | None = "aad-123",
    member_id: str = "29:abc",
) -> Activity:
    from_property: dict[str, str] = {"id": member_id, "name": "Ada"}
    if aad_object_id is not None:
        from_property["aadObjectId"] = aad_object_id

    return Activity.model_validate(
        {
            "type": "message",
            "id": "act-1",
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "channelId": "msteams",
            "from": from_property,
            "conversation": {"id": "a:conv-1"},
            "value": {"progress": progress, "blockers": blockers, "plan": plan},
        }
    )


def test_card_submit_produces_expected_raw_submission():
    activity = make_activity(
        progress="Finished the ingestion normalizer.",
        blockers="Blocked on staging credentials.",
        plan="Wire up the digest render step.",
    )

    submission = TeamsAdapter().to_raw_submission(activity, captured_at=CAPTURED_AT)

    assert submission.source_kind == SourceKind.TEAMS
    assert submission.external_user_key == "aad-123"
    assert submission.text_fields[ItemKind.PROGRESS] == "Finished the ingestion normalizer."
    assert submission.text_fields[ItemKind.BLOCKER] == "Blocked on staging credentials."
    assert submission.text_fields[ItemKind.PLAN] == "Wire up the digest render step."
    assert submission.captured_at == CAPTURED_AT
    assert submission.source_ids == {
        "adapter": "teams",
        "conversation_id": "a:conv-1",
        "channel_id": "msteams",
        "service_url": "https://smba.trafficmanager.net/teams/",
        "activity_id": "act-1",
    }
    # The whole activity is stored verbatim -- this is what makes the evidence
    # view a faithful citation target for a Teams-sourced claim.
    assert submission.raw_payload["value"]["blockers"] == "Blocked on staging credentials."


def test_falls_back_to_member_id_when_no_aad_object_id():
    """Some channels/emulators omit aadObjectId; the Teams member id still identifies a person."""
    activity = make_activity(progress="Shipped X", aad_object_id=None, member_id="29:xyz")

    submission = TeamsAdapter().to_raw_submission(activity, captured_at=CAPTURED_AT)

    assert submission.external_user_key == "29:xyz"


def test_partial_fields_map_correctly_and_is_not_empty():
    activity = make_activity(progress="Shipped X", blockers="", plan="")

    submission = TeamsAdapter().to_raw_submission(activity, captured_at=CAPTURED_AT)

    assert submission.text_fields[ItemKind.PROGRESS] == "Shipped X"
    assert submission.text_fields[ItemKind.BLOCKER] == ""
    assert submission.text_fields[ItemKind.PLAN] == ""
    assert submission.is_empty() is False


def test_all_blank_fields_is_empty():
    activity = make_activity(progress="", blockers="", plan="")

    submission = TeamsAdapter().to_raw_submission(activity, captured_at=CAPTURED_AT)

    assert submission.is_empty() is True
