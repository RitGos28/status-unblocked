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
