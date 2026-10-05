"""Personal login links.

Each member gets a signed, expiring link that carries only their member id.
Opening it sets a session cookie. There are no passwords and no roles: the
link identifies a person, and what they can see follows from their team
(invariant 7: no manager role).

Rotating ``STANDUP_SECRET_KEY`` invalidates every link and every session.
"""

from itsdangerous import BadSignature, URLSafeTimedSerializer

_SALT = "standup-login"


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=_SALT)


def issue_login_token(secret_key: str, member_id: str) -> str:
    return _serializer(secret_key).dumps(member_id)


def read_login_token(secret_key: str, token: str, *, max_age_seconds: int) -> str | None:
    """The member id the token was issued for, or None if forged or expired."""
    try:
        member_id = _serializer(secret_key).loads(token, max_age=max_age_seconds)
    except BadSignature:  # SignatureExpired is a subclass
        return None
    return member_id if isinstance(member_id, str) else None


def login_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/login/{token}"


# --- Teams account linking ------------------------------------------------
# A signed-in web member gets a short-lived code and sends "link <code>" to the
# bot. The bot learns which Teams account belongs to which member without the
# app ever asking Microsoft Graph who anyone is.

_TEAMS_LINK_SALT = "standup-teams-link"
TEAMS_LINK_MAX_AGE_SECONDS = 15 * 60


def issue_teams_link_code(secret_key: str, member_id: str) -> str:
    return URLSafeTimedSerializer(secret_key, salt=_TEAMS_LINK_SALT).dumps(member_id)


def read_teams_link_code(secret_key: str, code: str) -> str | None:
    try:
        member_id = URLSafeTimedSerializer(secret_key, salt=_TEAMS_LINK_SALT).loads(
            code, max_age=TEAMS_LINK_MAX_AGE_SECONDS
        )
    except BadSignature:
        return None
    return member_id if isinstance(member_id, str) else None
