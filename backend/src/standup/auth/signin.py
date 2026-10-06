"""Sign-in: a team code plus a name, resolved to exactly one member."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from standup.auth.team_code import format_team_code, normalise_name, normalise_team_code
from standup.db.models import Member, Team

SIGN_IN_FAILED = (
    "That team code and name do not match anyone. Check the code with your team, "
    "and use the name your team lists you under."
)


def sign_in(session: Session, team_code: str, name: str) -> Member | None:
    """The active member of the team with ``team_code`` called ``name``, or None.

    Code and name are compared normalised (case, spacing and the hyphen in the
    code are ignored). A wrong code and a wrong name get the same answer, so a
    code cannot be probed to learn whether a team exists.
    """
    code = normalise_team_code(team_code)
    wanted = normalise_name(name)
    if not code or not wanted:
        return None
    team = session.execute(select(Team).where(Team.join_code == code)).scalar_one_or_none()
    if team is None:
        return None
    members = session.execute(
        select(Member).where(Member.team_id == team.id, Member.active.is_(True))
    ).scalars()
    for member in members:
        if normalise_name(member.display_name) == wanted:
            return member
    return None


def team_summary(team: Team) -> dict[str, Any]:
    """What the Team page shows every member: the code to share, and who is on the team."""
    return {
        "name": team.name,
        "slug": team.slug,
        "join_code": format_team_code(team.join_code),
        "members": sorted(m.display_name for m in team.members if m.active),
    }
