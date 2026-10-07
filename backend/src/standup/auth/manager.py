"""The manager portal's sign-in: one username and password pair from settings.

Pure: no I/O. The pair comes from ``STANDUP_MANAGER_USERNAME`` and
``STANDUP_MANAGER_PASSWORD``; there are no manager accounts in the database.
Comparison is constant-time on both fields, and a wrong username gets the same
answer as a wrong password, so neither can be probed on its own.
"""

import secrets

MANAGER_SIGN_IN_FAILED = "That username and password do not match."

# What the session stores for a signed-in manager, next to a member's id.
MANAGER_SESSION_KEY = "manager"


def check_manager_credentials(
    expected_username: str, expected_password: str, username: str, password: str
) -> bool:
    """True only when both fields match; the username ignores surrounding space."""
    username_ok = secrets.compare_digest(
        expected_username.strip().encode(), username.strip().encode()
    )
    password_ok = secrets.compare_digest(expected_password.encode(), password.encode())
    return username_ok and password_ok and bool(expected_username.strip()) and bool(password)
