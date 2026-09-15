"""End-to-end smoke test.

This is deliberately both the regression net and the demo script: it walks the
exact path shown in a demo, so if the demo would break, CI says so first.

Three submissions -> digest -> every blocker carries an evidence link ->
the evidence page shows the verbatim source -> the audit trail recorded it.

Target: under ten seconds.
"""

from sqlalchemy import select

from standup.db.models import AuditLog, Digest, DigestClaim, StandupCycle, Update, UpdateItem
from standup.domain.enums import AuditAction, ClaimKind, CycleState
from standup.privacy.audit import verify_chain


def submit(client, member_id: str, progress: str = "", blockers: str = "", plan: str = ""):
    return client.post(
        "/submit",
        data={
            "member_id": member_id,
            "progress": progress,
            "blockers": blockers,
            "plan": plan,
        },
        follow_redirects=False,
    )


def test_full_cycle_submit_digest_and_verify_evidence(client, session, team_with_members):
    _team, members = team_with_members
    ada, bruno, chen = members

    # --- three people file their standup -----------------------------------
    assert submit(
        client,
        ada.id,
        progress="Shipped the retry logic.",
        blockers="Waiting on staging credentials from infra.",
        plan="Finish the migration.",
    ).status_code == 303

    assert submit(
        client,
        bruno.id,
        progress="Reviewed #214.",
        blockers="No blockers today.",
        plan="Pick up the flaky test.",
    ).status_code == 303

    assert submit(
        client,
        chen.id,
        progress="Drafted the schema.",
        plan="Pair with Ada on the migration.",
    ).status_code == 303

    updates = session.execute(select(Update)).scalars().all()
    assert len(updates) == 3

    # Raw text is stored verbatim and hashed.
    assert all(u.raw_text for u in updates)
    assert all(len(u.content_sha256) == 64 for u in updates)

    # A web submission has no platform permalink, and says so rather than
    # leaving a silent null.
    assert all(u.permalink is None for u in updates)
    assert all(u.permalink_reason for u in updates)

    # --- build the digest ---------------------------------------------------
    cycle = session.execute(select(StandupCycle)).scalars().one()
    response = client.post(f"/digests/build/{cycle.id}", follow_redirects=False)
    assert response.status_code == 303

    session.expire_all()
    digest = session.execute(select(Digest)).scalars().one()
    claims = session.execute(
        select(DigestClaim).where(DigestClaim.digest_id == digest.id)
    ).scalars().all()

    assert digest.summarizer_name == "rules"
    assert claims, "digest produced no claims"

    # Nothing was withheld: the rules engine is extractive, so it passes
    # validation by construction.
    assert digest.withheld_count == 0
    assert digest.validator_report_json["violations"] == []

    # --- every claim is cited, and every citation resolves -------------------
    for claim in claims:
        assert claim.citations_json, f"uncited claim reached the digest: {claim.text!r}"
        for citation in claim.citations_json:
            item = session.get(UpdateItem, citation["source_id"])
            assert item is not None, "citation points at a source that does not exist"
            assert citation["quote"] == item.text

    # --- "no blockers" was not mistaken for a blocker ------------------------
    blockers = [c for c in claims if c.kind == ClaimKind.BLOCKER.value]
    assert len(blockers) == 1, [b.text for b in blockers]
    assert blockers[0].member_name == "Ada Okafor"
    assert "staging credentials" in blockers[0].text

    # --- the digest page links each blocker to its source --------------------
    page = client.get(f"/digest/{digest.id}")
    assert page.status_code == 200
    source_id = blockers[0].citations_json[0]["source_id"]
    assert f"/evidence/{source_id}" in page.text

    # --- and the evidence page shows the verbatim words ----------------------
    evidence = client.get(f"/evidence/{source_id}")
    assert evidence.status_code == 200
    assert "Waiting on staging credentials from infra." in evidence.text
    assert "Ada Okafor" in evidence.text

    # --- the cycle is marked digested ---------------------------------------
    session.expire_all()
    cycle = session.get(StandupCycle, cycle.id)
    assert cycle.state == CycleState.DIGESTED

    # --- and every read was audited, in an intact chain ----------------------
    actions = [
        row.action
        for row in session.execute(select(AuditLog).order_by(AuditLog.seq)).scalars().all()
    ]
    assert actions.count(AuditAction.UPDATE_INGESTED.value) == 3
    assert AuditAction.DIGEST_BUILT.value in actions
    assert AuditAction.EVIDENCE_VIEWED.value in actions

    intact, bad_seq = verify_chain(session)
    assert intact, f"audit chain broken at seq {bad_seq}"


def test_markdown_digest_carries_evidence_links(client, session, team_with_members):
    _team, members = team_with_members
    submit(client, members[0].id, blockers="Blocked on the deploy pipeline.")

    cycle = session.execute(select(StandupCycle)).scalars().one()
    client.post(f"/digests/build/{cycle.id}", follow_redirects=False)

    session.expire_all()
    digest = session.execute(select(Digest)).scalars().one()

    markdown = client.get(f"/digest/{digest.id}.md")
    assert markdown.status_code == 200
    assert "Blocked on the deploy pipeline." in markdown.text
    assert "/evidence/" in markdown.text


def test_empty_submission_is_rejected(client, team_with_members):
    _team, members = team_with_members
    response = submit(client, members[0].id)
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")


def test_unknown_member_is_rejected(client, team_with_members):
    response = submit(client, "nope", progress="hello")
    assert response.status_code == 404


def test_evidence_for_unknown_item_is_a_problem_response(client, app_env):
    response = client.get("/evidence/does-not-exist")
    assert response.status_code == 404
    assert response.json()["title"] == "Not found"


def test_health_endpoints(client, app_env):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json()["status"] == "ok"
    assert client.get("/version").json()["summarizer"] == "rules"
