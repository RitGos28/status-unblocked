"""Claims that the digest and evidence store make about themselves, checked
against a real database: classifications stay explainable after the build,
stored text is tamper-evident, and cycles follow the team's local date.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from standup.db.models import DigestClaim, StandupCycle, Team, Update
from standup.privacy.audit import verify_chain, verify_evidence


def submit(client, member_id: str, **fields: str):
    return client.post(
        "/submit",
        data={"member_id": member_id, **fields},
        follow_redirects=False,
    )


def build(client, session) -> str:
    cycle = session.execute(select(StandupCycle)).scalars().one()
    response = client.post(f"/digests/build/{cycle.id}", follow_redirects=False)
    assert response.status_code == 303
    return response.headers["location"]


def test_promotion_reason_is_persisted_and_shown(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, progress="Still stuck waiting on the security review.")

    digest_url = build(client, session)

    claim = session.execute(select(DigestClaim)).scalars().one()
    assert claim.kind == "blocker"
    assert claim.matched_rule.startswith("promoted:marker:")
    assert "Moved to Blockers" in client.get(digest_url).text


def test_editing_stored_text_is_detected(client, session, team_with_members):
    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    session.expire_all()

    assert verify_chain(session) == (True, None)
    assert verify_evidence(session) == []

    update = session.execute(select(Update)).scalars().one()
    update.raw_text = update.raw_text.replace("staging", "prod")
    session.commit()

    assert verify_evidence(session) == [update.id]


def test_cycle_uses_the_team_local_date(client, session, clock, team_with_members):
    team, (ada, bruno, _chen) = team_with_members
    team = session.get(Team, team.id)
    team.tz_default = "Asia/Singapore"
    session.commit()

    # 23:30 UTC on the 14th is 07:30 on the 15th in Singapore, and so is 01:00
    # UTC on the 15th: one local working day, so one cycle.
    clock.current = datetime(2026, 9, 14, 23, 30, tzinfo=UTC)
    submit(client, ada.id, progress="Shipped the retry logic.")
    clock.current = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    submit(client, bruno.id, progress="Reviewed #214.")

    cycles = session.execute(select(StandupCycle)).scalars().all()
    assert len(cycles) == 1
    assert str(cycles[0].local_date) == "2026-09-15"
    assert cycles[0].cutoff_at_utc is not None


def test_browser_errors_render_html_and_api_errors_stay_json(client, app_env):
    browser = client.get("/digest/does-not-exist", headers={"accept": "text/html"})
    assert browser.status_code == 404
    assert browser.headers["content-type"].startswith("text/html")

    api = client.get("/digest/does-not-exist")
    assert api.status_code == 404
    assert api.headers["content-type"] == "application/problem+json"


def test_evidence_links_use_the_request_address_when_unconfigured(
    client, session, monkeypatch, team_with_members
):
    from standup.config import get_settings

    monkeypatch.setenv("STANDUP_BASE_URL", "")
    get_settings.cache_clear()

    _team, (ada, *_rest) = team_with_members
    submit(client, ada.id, blockers="Waiting on staging credentials.")
    digest_url = build(client, session)

    markdown = client.get(f"{digest_url}.md").text
    assert "(http://testserver/evidence/" in markdown
