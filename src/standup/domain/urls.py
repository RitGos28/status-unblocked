"""Absolute links the app hands out: in digests, issues, notices and seeds. Pure."""


def _join(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def digest_url(base_url: str, digest_id: str) -> str:
    return _join(base_url, f"/digest/{digest_id}")


def evidence_url(base_url: str, item_id: str) -> str:
    return _join(base_url, f"/evidence/{item_id}")


def login_url(base_url: str, token: str) -> str:
    return _join(base_url, f"/login/{token}")
