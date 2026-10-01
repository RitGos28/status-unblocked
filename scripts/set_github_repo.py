"""Point a team's blocker issues at a GitHub repository.

Run: python -m scripts.set_github_repo --team core --repo owner/name
Pass --repo "" to stop writing that team's blockers anywhere.
Also needs STANDUP_TRACKER=github and STANDUP_GITHUB_TOKEN (a fine-grained
token with Issues: read and write on that repository only).
"""

import argparse
import re
import sys

from sqlalchemy import select

from standup.db.models import Team
from standup.db.session import session_scope

_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--team", required=True, help="team slug")
    parser.add_argument("--repo", required=True, help='owner/name, or "" to clear')
    args = parser.parse_args()

    if args.repo and not _REPO.match(args.repo):
        print(f"not an owner/name repository: {args.repo!r}")
        return 1
    with session_scope() as session:
        team = session.execute(select(Team).where(Team.slug == args.team)).scalar_one_or_none()
        if team is None:
            print(f"no team with slug {args.team!r}")
            return 1
        team.github_repo = args.repo or None
        print(f"{team.name}: blockers go to {args.repo or 'nowhere'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
