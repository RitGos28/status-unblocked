"""Import standup updates from a CSV file.

Run: python -m scripts.import_updates_csv docs/sample_updates.csv
Columns: date (UTC, YYYY-MM-DD), team (slug), member (display name), progress,
blockers, plan, and optionally time (HH:MM, default 09:00). One bad row (or a
future date) means nothing is imported; re-importing the same file changes
nothing; a row never replaces a later update the member already has that day.
UTF-8, with or without Excel's byte-order mark.
"""

import argparse
import sys
from pathlib import Path

from standup.db.session import session_scope
from standup.deps import get_clock
from standup.ingestion.csv_import import import_updates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        # utf-8-sig also accepts Excel's "CSV UTF-8", which starts with a BOM.
        text = args.path.read_bytes().decode("utf-8-sig")
    except FileNotFoundError:
        print(f"import_updates_csv: no such file: {args.path}", file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print(
            f"import_updates_csv: {args.path} is not UTF-8; "
            'save it as "CSV UTF-8" and try again',
            file=sys.stderr,
        )
        return 1
    with session_scope() as session:
        report = import_updates(session, text, source_name=args.path.name, now=get_clock().now())
        if report.errors:
            session.rollback()
    for message in (*report.errors, *report.kept_later):
        print(message)
    print(
        f"imported {report.imported}, skipped {report.skipped} unchanged, "
        f"kept {len(report.kept_later)} later update(s), errors {len(report.errors)}"
    )
    if report.stale_digests and not report.errors:
        print(
            "these days already had a digest, built before this import; rebuild them "
            "from Digests to include it: " + ", ".join(report.stale_digests)
        )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
