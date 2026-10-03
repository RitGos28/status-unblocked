"""A local stand-in for the Teams service the bot replies to, for demos.

Run: python -m scripts.fake_teams_connector [--port 8092]
Replay activities with scripts/teams_replay.py, which points their serviceUrl
here. Every message the bot sends (replies, cards, the scheduler's "digest
ready" notices) is recorded: see http://127.0.0.1:8092/ or /messages (JSON).
Needs no tenant and no credentials: the app must run with
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED=True.
"""

import argparse
import html
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse


def create_fake_connector() -> FastAPI:
    app = FastAPI(title="fake Teams connector")
    messages: list[dict[str, Any]] = []

    async def record(conversation_id: str, request: Request) -> dict[str, str]:
        body = await request.json()
        messages.append(
            {
                "conversation_id": conversation_id,
                "text": body.get("text"),
                "attachments": [a.get("contentType") for a in body.get("attachments") or []],
                "authenticated": bool(request.headers.get("authorization")),
            }
        )
        return {"id": f"fake-{len(messages)}"}

    @app.post("/v3/conversations/{conversation_id}/activities")
    async def send(conversation_id: str, request: Request) -> dict[str, str]:
        return await record(conversation_id, request)

    @app.post("/v3/conversations/{conversation_id}/activities/{reply_to}")
    async def reply(conversation_id: str, reply_to: str, request: Request) -> dict[str, str]:
        return await record(conversation_id, request)

    @app.get("/messages")
    def all_messages() -> list[dict[str, Any]]:
        return messages

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        rows = "".join(
            f"<li><code>{html.escape(m['conversation_id'])}</code>: "
            f"{html.escape(m['text'] or ', '.join(m['attachments']) or '(empty)')}</li>"
            for m in messages
        )
        return (
            "<!doctype html><meta charset='utf-8'><title>Bot messages</title>"
            "<body style='font:15px/1.5 system-ui;max-width:760px;margin:24px auto'>"
            "<p style='color:#a4442c'>fake Teams connector for demos: not Microsoft Teams</p>"
            f"<h1>What the bot sent</h1><ol>{rows or '<li>nothing yet</li>'}</ol></body>"
        )

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()
    uvicorn.run(create_fake_connector(), port=args.port)


if __name__ == "__main__":
    main()
