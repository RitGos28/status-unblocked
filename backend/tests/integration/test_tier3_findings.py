"""Rough edges found by the Tier 3 demo pass."""

import json

import pytest

from tests.helpers import login_as, submit

HTML = {"accept": "text/html"}


def test_an_unknown_page_is_an_html_page_in_a_browser(client, team_with_members):
    login_as(client, team_with_members[1][0].id)
    page = client.get("/no-such-page", headers=HTML)
    assert page.status_code == 404
    assert page.headers["content-type"].startswith("text/html")
    assert "Aarav Sharma" in page.text  # signed-in header kept


def test_an_unknown_page_is_problem_json_for_an_api_client(client, app_env):
    api = client.get("/no-such-page")
    assert api.status_code == 404
    assert api.headers["content-type"] == "application/problem+json"
    assert api.json()["status"] == 404


def test_a_wrong_method_is_handled_the_same_way(client, team_with_members):
    login_as(client, team_with_members[1][0].id)
    page = client.get("/digests/build/x", headers=HTML)
    assert page.status_code == 405
    assert page.headers["content-type"].startswith("text/html")


def test_export_timestamps_carry_their_timezone(client, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on infra.")
    login_as(client, ada.id)
    data = json.loads(client.get("/me/export").text)
    stamps = [data["updates"][0]["captured_at"], *(e["when"] for e in data["audit"])]
    assert all(s.endswith("+00:00") for s in stamps), stamps


def test_pages_declare_an_icon_so_browsers_do_not_request_favicon(client, app_env):
    assert 'rel="icon"' in client.get("/").text


def test_tick_without_a_base_url_says_so_without_a_traceback(monkeypatch, capsys, app_env):
    import scripts.tick as tick

    from standup.config import get_settings

    monkeypatch.setenv("STANDUP_BASE_URL", "")
    get_settings.cache_clear()
    monkeypatch.setattr("sys.argv", ["tick"])
    with pytest.raises(SystemExit) as excinfo:
        tick.main()
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "STANDUP_BASE_URL is required" in err and "Traceback" not in err


def test_a_day_past_its_cutoff_without_a_digest_is_waiting_not_collecting(
    client, clock, team_with_members
):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on infra.")
    assert "Collecting updates" in client.get("/digests").text
    clock.advance(hours=3)  # 09:30 -> 12:30 UTC, past the 11:00 cutoff
    listing = client.get("/digests").text
    assert "Waiting for its digest" in listing and "Collecting updates" not in listing
