"""Absolute links the app hands out: in digests, issues, notices and seeds. Pure."""

# Where a local run serves the app when STANDUP_BASE_URL is not set, for
# scripts that print links with no request to take the address from.
LOCAL_BASE_URL = "http://localhost:8000"


def public_base_url(configured: str, request_base: str) -> str:
    """STANDUP_BASE_URL if set, else the address the request arrived on."""
    return configured or request_base


def app_url(base_url: str, path: str) -> str:
    """An absolute link to a page of the app, e.g. app_url(base, "/digests")."""
    return f"{base_url.rstrip('/')}{path}"


def digest_url(base_url: str, digest_id: str) -> str:
    return app_url(base_url, f"/digest/{digest_id}")


def evidence_url(base_url: str, item_id: str) -> str:
    return app_url(base_url, f"/evidence/{item_id}")

