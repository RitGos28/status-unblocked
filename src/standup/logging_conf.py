"""Structured logging with secret scrubbing.

Every log line is an event with a stable name (``update.ingested``,
``digest.built``, ``claim.rejected``) rather than f-string prose, so logs stay
greppable and aggregatable.

The scrubbing processor is not decoration: ``tests/unit/test_logging.py``
asserts a known secret value never reaches the output stream.
"""

import logging
import re
import sys
from typing import Any

import structlog

# Keys whose values are redacted wholesale, whatever they contain.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "client_secret",
        "clientsecret",
        "api_key",
        "apikey",
        "authorization",
        "github_token",
    }
)

# Value-shaped secrets that can turn up embedded in free text.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),  # GitHub tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key IDs
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),  # JWTs
)

_REDACTED = "[REDACTED]"


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub(_REDACTED, value)
        return value
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_scrub_value(v) for v in value)
    return value


def scrub_secrets(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Redact sensitive keys and secret-shaped values before anything is emitted."""
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = _REDACTED
        else:
            event_dict[key] = _scrub_value(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            scrub_secrets,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
