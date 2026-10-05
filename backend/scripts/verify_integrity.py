"""Verify the audit chain and every stored update against it.

Run: python -m scripts.verify_integrity
Exits 1 if anything fails, so it can gate a deploy or a cron alert.
"""

import sys

from standup.db.session import session_scope
from standup.privacy.audit import verify_chain, verify_evidence


def main() -> int:
    with session_scope() as session:
        intact, bad_seq = verify_chain(session)
        if not intact:
            print(f"audit chain broken at seq {bad_seq}")
            return 1
        tampered = verify_evidence(session)
        if tampered:
            print(f"{len(tampered)} update(s) do not match their pinned hash:")
            for update_id in tampered:
                print(f"  {update_id}")
            return 1
    print("audit chain intact; every stored update matches its pinned hash")
    return 0


if __name__ == "__main__":
    sys.exit(main())
