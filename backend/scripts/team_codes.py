"""Print each team's sign-in code, or issue a new one.

Run: python -m scripts.team_codes [--team SLUG] [--rotate]

Share a team's code with its members; each signs in with the code and their
name. Every member can also read the code on their Team page in the app.
--rotate (with --team) replaces that team's code: later sign-ins need the new
one, and nobody already signed in is affected.
"""

import argparse

from sqlalchemy import select

from standup.auth.team_code import format_team_code, generate_team_code
from standup.db.models import Team
from standup.db.session import session_scope


def print_codes(team_slug: str | None = None) -> None:
    with session_scope() as session:
        query = select(Team).order_by(Team.name)
        if team_slug:
            query = query.where(Team.slug == team_slug)
        teams = session.execute(query).scalars().all()
        if not teams:
            print(f"No team with slug {team_slug!r}." if team_slug else "No teams yet.")
            return
        for team in teams:
            names = sorted(m.display_name for m in team.members if m.active)
            print(f"{team.name} ({team.slug}): {format_team_code(team.join_code)}")
            print(f"  members: {', '.join(names) if names else 'none yet'}")


def rotate(team_slug: str) -> int:
    with session_scope() as session:
        team = session.execute(select(Team).where(Team.slug == team_slug)).scalar_one_or_none()
        if team is None:
            print(f"No team with slug {team_slug!r}.")
            return 1
        team.join_code = generate_team_code(team.slug)
        print(f"{team.name} ({team.slug}): new code {format_team_code(team.join_code)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--team", help="team slug")
    parser.add_argument("--rotate", action="store_true", help="issue the team a new code")
    args = parser.parse_args()
    if args.rotate:
        if not args.team:
            parser.error("--rotate needs --team SLUG")
        return rotate(args.team)
    print_codes(args.team)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
