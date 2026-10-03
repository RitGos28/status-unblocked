"""The accountless Teams demo: anonymous notices, the fake connector, replays.

A spike against a local connector showed the SDK's default proactive path
needs a tenant id (it fails with "TENANT_ID is not set"), while
continue_conversation_with_claims with an empty identity uses the anonymous
token provider and needs no credentials. The notifier takes that path only in
anonymous (Playground / local demo) mode.
"""

import asyncio

from fastapi.testclient import TestClient
from scripts.fake_teams_connector import create_fake_connector
from scripts.teams_replay import prepare

from standup.api.teams_router import TeamsNotifier

REFERENCE = {
    "user": {"id": "29:user-ada"},
    "agent": {"id": "28:bot-id"},
    "conversation": {"id": "a:1on1-ada"},
    "serviceUrl": "http://127.0.0.1:8092/",
    "channelId": "msteams",
}


class RecordingAdapter:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    async def continue_conversation(self, app_id, continuation, callback):
        self.calls.append(("default", app_id))

    async def continue_conversation_with_claims(self, identity, continuation, callback):
        self.calls.append(("anonymous", identity))


def test_anonymous_mode_sends_notices_with_an_empty_identity():
    adapter = RecordingAdapter()
    asyncio.run(TeamsNotifier(adapter, "", anonymous=True).notify(REFERENCE, "ready"))
    ((path, identity),) = adapter.calls
    assert path == "anonymous"
    assert identity.claims == {} and identity.allow_anonymous


def test_a_real_tenant_uses_the_app_id_path():
    adapter = RecordingAdapter()
    asyncio.run(TeamsNotifier(adapter, "app-id").notify(REFERENCE, "ready"))
    assert adapter.calls == [("default", "app-id")]


def test_the_fake_connector_records_replies_and_cards():
    client = TestClient(create_fake_connector())
    client.post("/v3/conversations/a:1/activities/42", json={"type": "message", "text": "hi"})
    client.post(
        "/v3/conversations/a:1/activities",
        json={"attachments": [{"contentType": "application/vnd.microsoft.card.adaptive"}]},
    )
    messages = client.get("/messages").json()
    assert [m["text"] for m in messages] == ["hi", None]
    assert messages[1]["attachments"] == ["application/vnd.microsoft.card.adaptive"]
    assert "hi" in client.get("/").text


def test_replay_points_replies_at_the_connector_and_gives_a_fresh_id():
    first = prepare("personal_command", "http://127.0.0.1:8092", text="link abc")
    second = prepare("personal_command", "http://127.0.0.1:8092")
    assert first["serviceUrl"] == "http://127.0.0.1:8092/"
    assert first["text"] == "link abc" and second["text"] == "standup"
    assert first["id"] != second["id"]
