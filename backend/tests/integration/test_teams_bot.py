"""The Teams bot, end to end below the HTTP layer.

``StandupAgent.on_turn`` runs against a real database with a fake turn
context that records replies, so these tests need no tenant and no network.
The HTTP route itself is covered at the bottom, in anonymous Playground mode.
"""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from standup.api.teams_router import StandupAgent
from standup.auth.tokens import issue_teams_link_code
from standup.db.models import IngestRejection, Member, Update
from standup.domain.enums import SourceKind
from standup.privacy.audit import verify_evidence
from tests.helpers import TEST_SECRET_KEY, login_as
from tests.teams_fixtures import activity, raw_activity


class FakeTurnContext:
    """Records what the bot sends instead of calling the Bot Framework."""

    def __init__(self, act):
        self.activity = act
        self.sent: list[Any] = []

    async def send_activity(self, activity_or_text):
        self.sent.append(activity_or_text)


def run_turn(session, clock, act) -> FakeTurnContext:
    context = FakeTurnContext(act)
    agent = StandupAgent(
        session=session, clock=clock, secret_key=TEST_SECRET_KEY, base_url="http://testserver"
    )
    asyncio.run(agent.on_turn(context))
    session.commit()
    return context


def link(session, clock, member: Member) -> None:
    code = issue_teams_link_code(TEST_SECRET_KEY, member.id, member.teams_aad_id)
    run_turn(session, clock, activity("personal_command", text=f"link {code}"))


def test_standup_command_replies_with_the_card(session, clock, team_with_members):
    context = run_turn(session, clock, activity("personal_command"))
    (reply,) = context.sent
    (attachment,) = reply.attachments
    assert attachment.content_type == "application/vnd.microsoft.card.adaptive"


def test_unknown_command_gets_help(session, clock, team_with_members):
    context = run_turn(session, clock, activity("personal_command", text="hello"))
    assert "standup" in context.sent[0]


def test_unlinked_account_cannot_submit(session, clock, team_with_members):
    context = run_turn(session, clock, activity("personal_card_submit"))
    assert "isn't linked" in context.sent[0]
    assert session.execute(select(Update)).first() is None


def test_link_then_submit_ingests_through_the_shared_path(session, clock, team_with_members):
    _team, (ada, *_rest) = team_with_members
    link(session, clock, ada)
    session.refresh(ada)
    assert ada.teams_aad_id == "aad-ada"

    context = run_turn(session, clock, activity("personal_card_submit"))
    assert "Recorded" in context.sent[0]

    update = session.execute(select(Update)).scalar_one()
    assert update.member_id == ada.id
    assert update.source_kind == SourceKind.TEAMS
    # A 1:1 chat cannot produce a message deep link, and the row says so.
    assert update.permalink is None
    assert "a:-form" in update.permalink_reason
    assert "Waiting on staging credentials" in update.raw_text
    # Same invariants as the web form: the content hash is pinned in the chain.
    assert verify_evidence(session) == []


def test_bad_link_code_is_refused(session, clock, team_with_members):
    context = run_turn(session, clock, activity("personal_command", text="link not-a-code"))
    assert "invalid or has expired" in context.sent[0]


def test_one_teams_account_cannot_speak_for_two_members(session, clock, team_with_members):
    _team, (ada, bruno, _chen) = team_with_members
    link(session, clock, ada)
    code = issue_teams_link_code(TEST_SECRET_KEY, bruno.id, bruno.teams_aad_id)
    context = run_turn(session, clock, activity("personal_command", text=f"link {code}"))
    assert "already linked to another member" in context.sent[0]
    session.refresh(bruno)
    assert bruno.teams_aad_id is None


def test_unaddressed_channel_message_is_refused_counted_and_not_read(
    session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    link(session, clock, ada)
    context = run_turn(session, clock, activity("channel_unaddressed"))

    assert context.sent == []
    assert session.execute(select(Update)).first() is None
    rejection = session.execute(select(IngestRejection)).scalar_one()
    assert rejection.reason == "unaddressed_group_message"
    assert rejection.conversation_type == "channel"
    # Content-free: the row has nowhere to keep the text or the sender.
    assert {c.name for c in IngestRejection.__table__.columns} == {
        "id", "at", "source", "reason", "conversation_type"
    }


def test_channel_mention_gets_a_pointer_not_an_ingest(session, clock, team_with_members):
    context = run_turn(session, clock, activity("channel_mention"))
    assert "1:1 chat" in context.sent[0]
    assert session.execute(select(Update)).first() is None
    assert session.execute(select(IngestRejection)).first() is None


def test_install_events_are_ignored_silently(session, clock, team_with_members):
    context = run_turn(session, clock, activity("conversation_update"))
    assert context.sent == []
    assert session.execute(select(IngestRejection)).first() is None


# --- HTTP route --------------------------------------------------------------


def test_route_does_not_exist_when_teams_is_off(client, app_env):
    assert client.post("/api/messages", json=raw_activity("conversation_update")).status_code == 404


@pytest.fixture
def teams_client(app_env, monkeypatch):
    """The app with Teams on, in the anonymous mode Agents Playground uses."""
    from standup.config import get_settings
    from standup.main import create_app

    monkeypatch.setenv("STANDUP_TEAMS_ENABLED", "true")
    monkeypatch.setenv("CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED", "True")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c


def test_route_accepts_activities_and_counts_out_of_scope_ones(teams_client, session, app_env):
    for fixture in ("conversation_update", "channel_unaddressed"):
        response = teams_client.post("/api/messages", json=raw_activity(fixture))
        assert response.status_code == 202

    scope = teams_client.get("/scope").json()
    assert scope == {"scope_violations": 1, "by_reason": {"unaddressed_group_message": 1}}


def test_link_page_shows_a_code_for_the_signed_in_member(teams_client, team_with_members):
    login_as(teams_client, team_with_members[1][0].id)
    page = teams_client.get("/me/teams")
    assert page.status_code == 200
    assert "link " in page.text


def test_a_linked_member_turn_saves_the_conversation_for_notices(
    session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    link(session, clock, ada)
    session.refresh(ada)
    assert ada.teams_conversation_ref["conversation"]["id"] == "a:1on1-ada"
    assert ada.teams_conversation_ref["serviceUrl"].startswith("https://smba")


def test_channel_turns_never_save_a_conversation(session, clock, team_with_members):
    _team, (ada, *_rest) = team_with_members
    link(session, clock, ada)
    session.refresh(ada)
    before = dict(ada.teams_conversation_ref)
    run_turn(session, clock, activity("channel_mention"))
    session.refresh(ada)
    assert ada.teams_conversation_ref == before


def test_notifier_continues_the_saved_conversation():
    from standup.api.teams_router import TeamsNotifier

    class FakeAdapter:
        def __init__(self):
            self.calls = []

        async def continue_conversation(self, app_id, continuation, callback):
            context = FakeTurnContext(continuation)
            await callback(context)
            self.calls.append((app_id, continuation, context.sent))

    adapter = FakeAdapter()
    reference = {
        "user": {"id": "29:user-ada"},
        "agent": {"id": "28:bot-id"},
        "conversation": {"id": "a:1on1-ada"},
        "serviceUrl": "https://smba.trafficmanager.net/teams/",
        "channelId": "msteams",
    }
    asyncio.run(TeamsNotifier(adapter, "app-id").notify(reference, "Digest ready"))

    ((app_id, continuation, sent),) = adapter.calls
    assert app_id == "app-id"
    assert continuation.conversation.id == "a:1on1-ada"
    assert continuation.service_url == "https://smba.trafficmanager.net/teams/"
    assert sent == ["Digest ready"]


def _from(account: str) -> dict[str, Any]:
    return {"from": {"id": f"29:{account}", "aadObjectId": account, "name": account}}


def test_a_link_code_works_once(session, clock, team_with_members):
    """Found by the round-2 review (B): the same code, sent from a second
    Teams account, re-linked Ada to it and she was not told."""
    _team, (ada, *_rest) = team_with_members
    code = issue_teams_link_code(TEST_SECRET_KEY, ada.id, ada.teams_aad_id)
    first = run_turn(session, clock, activity("personal_command", text=f"link {code}"))
    assert "Linked" in first.sent[0]
    again = run_turn(
        session, clock, activity("personal_command", text=f"link {code}", **_from("aad-mallory"))
    )
    assert "invalid or has expired" in again.sent[0]
    session.refresh(ada)
    assert ada.teams_aad_id == "aad-ada"


def test_a_fresh_code_still_moves_the_link_to_a_new_account(session, clock, team_with_members):
    _team, (ada, *_rest) = team_with_members
    link(session, clock, ada)
    session.refresh(ada)
    code = issue_teams_link_code(TEST_SECRET_KEY, ada.id, ada.teams_aad_id)
    moved = run_turn(
        session, clock, activity("personal_command", text=f"link {code}", **_from("aad-ada-new"))
    )
    assert "Linked" in moved.sent[0]
    session.refresh(ada)
    assert ada.teams_aad_id == "aad-ada-new"


def test_resending_a_used_code_from_the_linked_account_is_harmless(
    session, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    code = issue_teams_link_code(TEST_SECRET_KEY, ada.id, None)
    run_turn(session, clock, activity("personal_command", text=f"link {code}"))
    again = run_turn(session, clock, activity("personal_command", text=f"link {code}"))
    assert "already linked" in again.sent[0].lower() and "Ada" in again.sent[0]
