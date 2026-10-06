"""Teams account linking codes.

A signed-in web member gets a short-lived code and sends "link <code>" to the
bot. The bot learns which Teams account belongs to which member without the
app ever asking Microsoft Graph who anyone is.

A code is single-use: it also signs the member's link state when it was
issued (a hash of the Teams account linked then, or of nothing). Using it
changes that state, so every copy of the code stops working, and a code that
leaked after use cannot move the member's link to another account.

Rotating ``STANDUP_SECRET_KEY`` invalidates every outstanding code.
"""

from itsdangerous import BadSignature, URLSafeTimedSerializer

from standup.domain.text import content_sha256

_TEAMS_LINK_SALT = "standup-teams-link"
TEAMS_LINK_MAX_AGE_SECONDS = 15 * 60


def teams_link_state(linked_account: str | None) -> str:
    return content_sha256(linked_account or "")[:16]


def issue_teams_link_code(secret_key: str, member_id: str, linked_account: str | None) -> str:
    serializer = URLSafeTimedSerializer(secret_key, salt=_TEAMS_LINK_SALT)
    return serializer.dumps(f"{member_id}:{teams_link_state(linked_account)}")


def read_teams_link_code(secret_key: str, code: str) -> tuple[str, str] | None:
    """(member id, link state at issue), or None if forged, expired or malformed."""
    try:
        payload = URLSafeTimedSerializer(secret_key, salt=_TEAMS_LINK_SALT).loads(
            code, max_age=TEAMS_LINK_MAX_AGE_SECONDS
        )
    except BadSignature:  # SignatureExpired is a subclass
        return None
    if not isinstance(payload, str):
        return None
    member_id, sep, state = payload.rpartition(":")
    return (member_id, state) if sep and member_id and state else None


__all__ = [
    "TEAMS_LINK_MAX_AGE_SECONDS",
    "issue_teams_link_code",
    "read_teams_link_code",
    "teams_link_state",
]
