"""Load the Teams activity fixtures (see tests/fixtures/teams/README.md)."""

import json
from pathlib import Path
from typing import Any

from microsoft_agents.activity import Activity

FIXTURES = Path(__file__).parent / "fixtures" / "teams"


def raw_activity(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def activity(name: str, **overrides: Any) -> Activity:
    return Activity.model_validate(raw_activity(name) | overrides)
