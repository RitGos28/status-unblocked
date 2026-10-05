"""Personal login links.

Each member gets a signed, expiring link that carries only their member id.
Opening it sets a session cookie. There are no passwords and no roles: the
link identifies a person, and what they can see follows from their team
(invariant 7: no manager role).

Rotating ``STANDUP_SECRET_KEY`` invalidates every link and every session.
"""

from itsdangerous import BadSignature, URLSafeTimedSerializer

from standup.domain.urls import login_url  # re-exported for callers

# Distinct salts: a login token can never be replayed as a Teams link code, or
# the other way round, even though both sign a member id with the same key.
_LOGIN_SALT = "standup-login"
_TEAMS_LINK_SALT = "standup-teams-link"
TEAMS_LINK_MAX_AGE_SECONDS = 15 * 60


def _issue(secret_key: str, salt: str, member_id: str) -> str:
    return URLSafeTimedSerializer(secret_key, salt=salt).dumps(member_id)


def _read(secret_key: str, salt: str, token: str, max_age_seconds: int) -> str | None:
    """The member id a token was signed for, or None if forged or expired."""
    try:
        member_id = URLSafeTimedSerializer(secret_key, salt=salt).loads(
            token, max_age=max_age_seconds
        )
    except BadSignature:  # SignatureExpired is a subclass
        return None
    return member_id if isinstance(member_id, str) else None


def issue_login_token(secret_key: str, member_id: str) -> str:
    return _issue(secret_key, _LOGIN_SALT, member_id)


def read_login_token(secret_key: str, token: str, *, max_age_seconds: int) -> str | None:
    return _read(secret_key, _LOGIN_SALT, token, max_age_seconds)


# --- Teams account linking ------------------------------------------------
# A signed-in web member gets a short-lived code and sends "link <code>" to the
# bot. The bot learns which Teams account belongs to which member without the
# app ever asking Microsoft Graph who anyone is.


def issue_teams_link_code(secret_key: str, member_id: str) -> str:
    return _issue(secret_key, _TEAMS_LINK_SALT, member_id)


def read_teams_link_code(secret_key: str, code: str) -> str | None:
    return _read(secret_key, _TEAMS_LINK_SALT, code, TEAMS_LINK_MAX_AGE_SECONDS)


__all__ = [
    "TEAMS_LINK_MAX_AGE_SECONDS",
    "issue_login_token",
    "issue_teams_link_code",
    "login_url",
    "read_login_token",
    "read_teams_link_code",
]
