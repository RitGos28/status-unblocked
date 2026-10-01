"""The scope gate: the bot reads only what is addressed to it."""

import pytest

from standup.ingestion.teams_adapter import classify_scope, standup_card
from tests.teams_fixtures import activity


@pytest.mark.parametrize(
    ("fixture", "kind", "reason"),
    [
        ("personal_command", "command", ""),
        ("personal_card_submit", "card_submit", ""),
        ("channel_mention", "mention", ""),
        ("channel_unaddressed", "rejected", "unaddressed_group_message"),
        ("channel_card_submit", "rejected", "card_submit_outside_personal"),
        ("conversation_update", "ignored", ""),
    ],
)
def test_each_activity_shape_gets_the_right_decision(fixture, kind, reason):
    decision = classify_scope(activity(fixture))
    assert decision.kind == kind
    assert decision.reason == reason


def test_command_text_is_passed_through_trimmed():
    decision = classify_scope(activity("personal_command", text="  link abc123 "))
    assert decision.text == "link abc123"


def test_group_chat_without_mention_is_rejected():
    act = activity(
        "channel_unaddressed",
        conversation={"id": "19:group@thread.v2", "conversationType": "groupChat"},
    )
    decision = classify_scope(act)
    assert decision.kind == "rejected"
    assert decision.conversation_type == "groupChat"


def test_card_collects_exactly_the_three_standup_fields():
    inputs = [el["id"] for el in standup_card()["body"] if el["type"] == "Input.Text"]
    assert inputs == ["progress", "blockers", "plan"]
