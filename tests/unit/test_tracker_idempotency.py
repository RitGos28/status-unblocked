"""Blocker fingerprints and issue-body markers."""

from standup.tracker.idempotency import fingerprint, marker, marker_in


def test_fingerprint_is_stable_and_scoped_to_team_and_member():
    fp = fingerprint("team", "ada", "waiting staging credentials")
    assert fp == fingerprint("team", "ada", "waiting staging credentials")
    assert fp != fingerprint("team", "bruno", "waiting staging credentials")
    assert fp != fingerprint("other-team", "ada", "waiting staging credentials")
    assert len(fp) == 64


def test_marker_round_trips_through_an_issue_body():
    fp = fingerprint("team", "ada", "key")
    body = f"Some text\n\n{marker(fp)}\n"
    assert marker_in(body) == fp


def test_body_without_a_marker_has_none():
    assert marker_in("an ordinary issue") is None
    assert marker_in("") is None
