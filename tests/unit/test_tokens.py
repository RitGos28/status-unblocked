"""Personal login links: only an unexpired link signed with our key works."""

from standup.auth.tokens import issue_login_token, login_url, read_login_token

KEY = "k" * 40


def test_round_trip_returns_the_member():
    token = issue_login_token(KEY, "member-1")
    assert read_login_token(KEY, token, max_age_seconds=60) == "member-1"


def test_link_signed_with_another_key_is_rejected():
    token = issue_login_token("x" * 40, "member-1")
    assert read_login_token(KEY, token, max_age_seconds=60) is None


def test_tampered_link_is_rejected():
    token = issue_login_token(KEY, "member-1")
    assert read_login_token(KEY, token[:-2] + "xx", max_age_seconds=60) is None


def test_expired_link_is_rejected():
    token = issue_login_token(KEY, "member-1")
    assert read_login_token(KEY, token, max_age_seconds=-1) is None


def test_login_url_joins_cleanly():
    assert login_url("http://host/", "abc") == "http://host/login/abc"
