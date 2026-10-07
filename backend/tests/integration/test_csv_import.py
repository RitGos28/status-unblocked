"""Made-up updates load from a spreadsheet (the brief's "web form + spreadsheet").

Rows go through the same ingest() path as the web form and Teams, filed on the
row's own date. A file with any bad row imports nothing. Re-importing the same
file changes nothing. Imports are audited as imports, not as the member.
"""

from sqlalchemy import select

from standup.db.models import AuditLog, StandupCycle, Update
from standup.domain.enums import AuditAction, SourceKind
from standup.ingestion.csv_import import import_updates

GOOD = """date,team,member,progress,blockers,plan
2026-09-14,core,Aarav Sharma,Wrote the retry tests.,Waiting on staging creds.,Ship the retry logic.
2026-09-15,core,Aarav Sharma,Shipped retry logic.,Waiting on staging creds.,Finish migration.
2026-09-15,core,Rohan Verma,Fixed the flaky test.,,Review the database changes.
"""


def test_rows_are_filed_on_their_own_dates_through_ingest(session, team_with_members):
    report = import_updates(session, GOOD, source_name="sample.csv")
    session.commit()

    assert (report.imported, report.skipped, report.errors) == (3, 0, [])
    dates = sorted(str(c.local_date) for c in session.execute(select(StandupCycle)).scalars())
    assert dates == ["2026-09-14", "2026-09-15"]
    updates = session.execute(select(Update)).scalars().all()
    assert {u.source_kind for u in updates} == {SourceKind.CSV}
    assert all(u.captured_at.hour == 9 for u in updates)
    ingested = session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.UPDATE_INGESTED.value)
    ).scalars().all()
    assert {(a.actor_kind, a.actor_id) for a in ingested} == {("import", "csv:sample.csv")}


def test_a_file_with_any_bad_row_imports_nothing_and_names_each_problem(
    session, team_with_members
):
    bad = GOOD + (
        "not-a-date,core,Aarav Sharma,x,,\n"
        "2026-09-15,nope,Aarav Sharma,x,,\n"
        "2026-09-15,core,Nobody,x,,\n"
        "2026-09-15,core,Ananya Patel,,,\n"
    )
    report = import_updates(session, bad, source_name="bad.csv")
    session.commit()

    assert report.imported == 0
    assert report.errors == [
        "line 5: date 'not-a-date' is not YYYY-MM-DD",
        "line 6: no team with slug 'nope'",
        "line 7: no active member 'Nobody' in team 'core'",
        "line 8: progress, blockers and plan are all empty",
    ]
    assert session.execute(select(Update)).first() is None


def test_missing_columns_are_reported(session, team_with_members):
    report = import_updates(session, "date,member\n2026-09-15,Aarav Sharma\n", source_name="x.csv")
    assert report.imported == 0
    assert report.errors == ["missing column(s): team, progress, blockers, plan"]


def test_importing_the_same_file_twice_changes_nothing(session, team_with_members):
    import_updates(session, GOOD, source_name="sample.csv")
    session.commit()
    again = import_updates(session, GOOD, source_name="sample.csv")
    session.commit()
    assert (again.imported, again.skipped) == (0, 3)
    assert len(session.execute(select(Update)).scalars().all()) == 3


# --- round-2 review (B) edge cases ------------------------------------------


def test_excels_utf8_byte_order_mark_is_ignored(session, team_with_members):
    report = import_updates(session, "﻿" + GOOD, source_name="excel.csv")
    assert (report.imported, report.errors) == (3, [])


def test_a_row_dated_in_the_future_is_refused(session, team_with_members):
    from datetime import UTC, datetime

    future = GOOD + "2031-01-01,core,Ananya Patel,Time travel.,,\n"
    report = import_updates(
        session, future, source_name="x.csv", now=datetime(2026, 10, 5, 12, tzinfo=UTC)
    )
    assert report.imported == 0
    assert report.errors == ["line 5: 2031-01-01 09:00 UTC is in the future"]


def test_an_import_never_replaces_a_later_update_for_that_day(
    client, session, clock, team_with_members
):
    from datetime import UTC, datetime

    from tests.helpers import submit

    _team, (ada, *_rest) = team_with_members
    clock.current = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)  # after the row's 09:00
    submit(client, ada.id, progress="Typed into the web form at 10:00.")
    report = import_updates(session, GOOD, source_name="sample.csv")
    session.commit()
    assert report.imported == 2  # Ada's 09-14 row and Bruno's 09-15 row
    assert report.kept_later == ["line 3: Aarav Sharma already has a later update for 2026-09-15"]
    live = session.execute(
        select(Update.raw_text).where(Update.member_id == ada.id).where(Update.is_live())
    ).scalars().all()
    assert any("10:00" in (t or "") for t in live)


def test_days_whose_digest_is_now_out_of_date_are_named(
    client, session, clock, team_with_members
):
    from datetime import UTC, datetime

    from tests.helpers import login_as, submit

    _team, (ada, _bruno, chen) = team_with_members
    clock.current = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
    submit(client, chen.id, progress="Early update.")
    cycle = session.execute(select(StandupCycle)).scalar_one()
    login_as(client, chen.id)
    client.post(f"/digests/build/{cycle.id}", follow_redirects=False)
    report = import_updates(session, GOOD, source_name="sample.csv")
    assert report.stale_digests == ["core 2026-09-15"]


def test_the_script_reports_a_bad_file_in_one_line(tmp_path, monkeypatch, capsys, app_env):
    import scripts.import_updates_csv as script

    latin = tmp_path / "latin.csv"
    latin.write_bytes(GOOD.replace("Aarav", "Aaráv").encode("latin-1"))
    for path, expected in (
        (latin, "is not UTF-8"),
        (tmp_path / "missing.csv", "no such file"),
    ):
        monkeypatch.setattr("sys.argv", ["import_updates_csv", str(path)])
        assert script.main() == 1
        out = capsys.readouterr()
        assert expected in out.out + out.err and "Traceback" not in out.err
