"""Print a personal login link for each active member.

Run: python -m scripts.issue_links [--team SLUG]
Send each person their own link. Anyone holding a link can sign in as that
person until it expires (STANDUP_LOGIN_LINK_DAYS), so treat links like
passwords. Rotating STANDUP_SECRET_KEY revokes all of them.
"""

import argparse

from sqlalchemy import select

from standup.auth.tokens import issue_login_token, login_url
from standup.config import get_settings
from standup.db.models import Member, Team
from standup.db.session import session_scope

DEFAULT_BASE_URL = "http://localhost:8000"


def print_links(team_slug: str | None = None) -> None:
    settings = get_settings()
    secret = settings.secret_key.get_secret_value()
    base_url = settings.base_url or DEFAULT_BASE_URL

    with session_scope() as session:
        query = select(Member, Team).join(Team, Member.team_id == Team.id).where(
            Member.active.is_(True)
        )
        if team_slug:
            query = query.where(Team.slug == team_slug)
        rows = session.execute(query.order_by(Team.name, Member.display_name)).tuples().all()

        if not rows:
            print("No active members found.")
            return
        for member, team in rows:
            link = login_url(base_url, issue_login_token(secret, member.id))
            print(f"{team.name} / {member.display_name}: {link}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--team", help="only this team's slug")
    args = parser.parse_args()
    print_links(args.team)


if __name__ == "__main__":
    main()
