"""Secret scrubbing tests.

`logging_conf.py` and CLAUDE.md both claim a known secret value never reaches
the output stream. This is the test that makes that a fact rather than a
promise. Logs get shipped to aggregators; a leaked token there is a real
incident.
"""

import io
import json

import pytest
import structlog

from standup.logging_conf import configure_logging, scrub_secrets

KNOWN_SECRET = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"


@pytest.fixture
def captured() -> io.StringIO:
    """Configure structlog to write JSON into a buffer we can inspect."""
    stream = io.StringIO()
    configure_logging("INFO", json_output=True)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            scrub_secrets,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.WriteLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )
    return stream


def test_sensitive_key_is_redacted(captured):
    structlog.get_logger("t").info("tracker.auth", github_token=KNOWN_SECRET)
    output = captured.getvalue()
    assert KNOWN_SECRET not in output
    assert "[REDACTED]" in output


@pytest.mark.parametrize(
    "key", ["password", "token", "secret", "client_secret", "api_key", "authorization"]
)
def test_every_sensitive_key_name_is_redacted(captured, key):
    structlog.get_logger("t").info("event", **{key: KNOWN_SECRET})
    assert KNOWN_SECRET not in captured.getvalue()


def test_secret_shaped_value_in_free_text_is_redacted(captured):
    """The dangerous case: a token pasted into an ordinary message field,
    under a key name that looks harmless."""
    structlog.get_logger("t").info("update.ingested", detail=f"user pasted {KNOWN_SECRET} here")
    output = captured.getvalue()
    assert KNOWN_SECRET not in output
    assert "[REDACTED]" in output


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "AKIAIOSFODNN7EXAMPLE",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    ],
)
def test_secret_patterns_are_caught(captured, secret):
    structlog.get_logger("t").info("event", note=f"value={secret}")
    assert secret not in captured.getvalue()


def test_nested_structures_are_scrubbed(captured):
    """Payloads are stored as JSON blobs, so nesting is the normal case."""
    structlog.get_logger("t").info(
        "teams.activity",
        payload={"headers": {"authorization": KNOWN_SECRET}, "items": [KNOWN_SECRET]},
    )
    assert KNOWN_SECRET not in captured.getvalue()


def test_ordinary_values_survive(captured):
    """Scrubbing must not eat the fields that make logs useful."""
    structlog.get_logger("t").info(
        "digest.built", digest_id="abc-123", claims=7, summarizer="rules"
    )
    record = json.loads(captured.getvalue().strip().splitlines()[-1])
    assert record["digest_id"] == "abc-123"
    assert record["claims"] == 7
    assert record["summarizer"] == "rules"


def test_scrub_is_idempotent():
    once = scrub_secrets(None, "info", {"note": f"x {KNOWN_SECRET}"})
    twice = scrub_secrets(None, "info", dict(once))
    assert once == twice


def test_login_tokens_are_redacted_from_the_access_log():
    """Login links carry the token in the path; uvicorn's access log prints
    paths. Anyone with the logs could otherwise sign in as anyone."""
    import logging

    configure_logging("INFO")
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    access = logging.getLogger("uvicorn.access")
    previous_level = access.level
    access.setLevel(logging.INFO)  # as uvicorn sets it when it serves
    access.addHandler(handler)
    try:
        # Exactly how uvicorn's access logger formats a request line.
        access.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:5000", "GET", "/login/eyJsecret.token-value_123", "1.1", 303,
        )
    finally:
        access.removeHandler(handler)
        access.setLevel(previous_level)
    line = buffer.getvalue()
    assert "eyJsecret.token-value_123" not in line
    assert "/login/[redacted]" in line
