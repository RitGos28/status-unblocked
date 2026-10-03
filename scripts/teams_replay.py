"""Send a Teams activity fixture to the bot, as Teams would.

Run: python -m scripts.teams_replay personal_command --text "standup"
     python -m scripts.teams_replay personal_card_submit
     python -m scripts.teams_replay channel_unaddressed
Fixtures are tests/fixtures/teams/<name>.json. Their serviceUrl is pointed at
the fake connector, so the bot's replies land there instead of at Microsoft.
"""

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "teams"


def prepare(name: str, connector_url: str, text: str | None = None) -> dict[str, Any]:
    """Load a fixture, aim its replies at the connector, give it a fresh id."""
    activity: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text())
    activity["serviceUrl"] = connector_url.rstrip("/") + "/"
    activity["id"] = str(uuid.uuid4())
    if text is not None:
        activity["text"] = text
    return activity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fixture", help="fixture name, e.g. personal_command")
    parser.add_argument("--text", help="replace the message text")
    parser.add_argument("--app", default="http://127.0.0.1:8000", help="the bot's base URL")
    parser.add_argument("--connector", default="http://127.0.0.1:8092", help="fake connector")
    args = parser.parse_args()
    activity = prepare(args.fixture, args.connector, args.text)
    response = httpx.post(f"{args.app.rstrip('/')}/api/messages", json=activity, timeout=30)
    print(f"{args.fixture}: HTTP {response.status_code}")
    return 0 if response.status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
