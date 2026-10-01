"""The Agents SDK can build the replies the bot sends.

Guards a real failure: on pydantic < 2.11 the SDK's models ignore
``validate_by_name``, so its own snake_case constructors raise and the bot
cannot send anything. The fake turn context in the bot tests never builds a
real reply, so this exercises the SDK's constructors directly.
"""

from microsoft_agents.activity import Activity, ActivityTypes
from microsoft_agents.hosting.core import CardFactory, MessageFactory

from standup.ingestion.teams_adapter import standup_card


def test_card_reply_builds():
    reply = MessageFactory.attachment(CardFactory.adaptive_card(standup_card()))
    assert reply.attachments[0].content_type == "application/vnd.microsoft.card.adaptive"


def test_plain_text_reply_builds_the_way_send_activity_does():
    # TurnContext.send_activity(str) constructs exactly this.
    reply = Activity(type=ActivityTypes.message, text="Recorded.", input_hint="acceptingInput")
    assert reply.text == "Recorded."
    assert MessageFactory.text("Recorded.").text == "Recorded."
