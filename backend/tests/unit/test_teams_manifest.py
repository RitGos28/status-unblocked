"""The Teams app requests no Microsoft Graph or resource-specific permissions.

This is the test behind the README's claim that an admin can verify, from the
manifest alone, that the bot cannot read anything it is not sent.
"""

import zipfile

from scripts.make_teams_zip import build, render_manifest

BOT_ID = "00000000-0000-0000-0000-000000000000"


def manifest() -> dict:
    return render_manifest(BOT_ID, "https://standup.example")


def test_requests_no_graph_or_resource_specific_permissions():
    m = manifest()
    # webApplicationInfo is how an app asks for Entra/Graph SSO consent;
    # authorization.permissions is how it asks for resource-specific consent.
    assert "webApplicationInfo" not in m
    assert "authorization" not in m
    assert "permissions" not in m
    assert m["validDomains"] == []


def test_bot_is_personal_and_team_scoped_only():
    (bot,) = manifest()["bots"]
    assert bot["botId"] == BOT_ID
    assert sorted(bot["scopes"]) == ["personal", "team"]
    assert bot["supportsFiles"] is False


def test_package_contains_manifest_and_icons(tmp_path, monkeypatch):
    import scripts.make_teams_zip as mtz

    monkeypatch.setattr(mtz, "OUT_DIR", tmp_path)
    out = build(BOT_ID, "https://standup.example")
    names = set(zipfile.ZipFile(out).namelist())
    assert names == {"manifest.json", "color.png", "outline.png"}
