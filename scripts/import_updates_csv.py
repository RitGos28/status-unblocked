"""Import standup updates from a CSV file.

Run: python -m scripts.import_updates_csv docs/sample_updates.csv
Columns: date (UTC, YYYY-MM-DD), team (slug), member (display name), progress,
blockers, plan, and optionally time (HH:MM, default 09:00). One bad row means
nothing is imported; re-importing the same file changes nothing.
"""

import argparse
import sys
from pathlib import Path

from standup.db.session import session_scope
from standup.ingestion.csv_import import import_updates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    with session_scope() as session:
        report = import_updates(session, args.path.read_text(), source_name=args.path.name)
        if report.errors:
            session.rollback()
    for error in report.errors:
        print(error)
    print(
        f"imported {report.imported}, skipped {report.skipped} unchanged, "
        f"errors {len(report.errors)}"
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
