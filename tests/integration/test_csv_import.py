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
2026-09-14,core,Ada Okafor,Wrote the retry tests.,Waiting on staging creds.,Ship the retry logic.
2026-09-15,core,Ada Okafor,Shipped the retry logic.,Waiting on staging creds.,Finish the migration.
2026-09-15,core,Bruno Silva,Fixed the flaky test.,,Review the database changes.
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
        "not-a-date,core,Ada Okafor,x,,\n"
        "2026-09-15,nope,Ada Okafor,x,,\n"
        "2026-09-15,core,Nobody,x,,\n"
        "2026-09-15,core,Chen Wei,,,\n"
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
    report = import_updates(session, "date,member\n2026-09-15,Ada Okafor\n", source_name="x.csv")
    assert report.imported == 0
    assert report.errors == ["missing column(s): team, progress, blockers, plan"]


def test_importing_the_same_file_twice_changes_nothing(session, team_with_members):
    import_updates(session, GOOD, source_name="sample.csv")
    session.commit()
    again = import_updates(session, GOOD, source_name="sample.csv")
    session.commit()
    assert (again.imported, again.skipped) == (0, 3)
    assert len(session.execute(select(Update)).scalars().all()) == 3
