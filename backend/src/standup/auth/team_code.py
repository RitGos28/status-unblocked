"""Team codes: one short code per team, shared by the team, typed at sign-in.

A team code does not prove who someone is. It proves they were given it by
someone on the team; the person then says who they are by name. That keeps
sign-in to two fields, with no email, no password and no per-person secret,
which suits a small team whose members already know each other. It also keeps
roles out of member sign-in: every member sees the code on their Team page and
can share it. The manager portal (``auth/manager.py``) is the one separate
login, and it holds no code a member does not have (invariant 7).

Pure: no I/O. Codes are stored compact (``CORE7K3MQ``) and shown with a
hyphen (``CORE-7K3MQ``); what people type is normalised before comparison, so
case, spaces and the hyphen never matter.
"""

import re
import secrets

# No 0/O or 1/I, so a code read out loud or off a screen is never ambiguous.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SUFFIX_LENGTH = 5
_PREFIX_LENGTH = 4
_NOT_CODE = re.compile(r"[^A-Z0-9]")


def generate_team_code(slug: str) -> str:
    """A fresh code for a team: a prefix from its slug, then random characters."""
    prefix = _NOT_CODE.sub("", slug.upper())[:_PREFIX_LENGTH] or "TEAM"
    suffix = "".join(secrets.choice(CODE_ALPHABET) for _ in range(SUFFIX_LENGTH))
    return f"{prefix}{suffix}"


def normalise_team_code(typed: str) -> str:
    """What someone typed, as the code is stored: upper-case letters and digits only."""
    return _NOT_CODE.sub("", typed.upper())


def format_team_code(code: str) -> str:
    """The stored code as people see it: ``CORE-7K3MQ``."""
    if len(code) <= SUFFIX_LENGTH:
        return code
    return f"{code[:-SUFFIX_LENGTH]}-{code[-SUFFIX_LENGTH:]}"


def normalise_name(typed: str) -> str:
    """A display name for comparison: case and repeated spaces ignored."""
    return " ".join(typed.split()).casefold()
