"""Seed a demo team so the app is usable immediately after checkout.

Run: python -m scripts.seed_demo
"""

from sqlalchemy import select

from standup.db.models import Member, Team
from standup.db.session import create_all, session_scope

DEMO_TEAM_SLUG = "core"

DEMO_MEMBERS = [
    ("Ada Okafor", "Europe/London"),
    ("Bruno Silva", "America/Sao_Paulo"),
    ("Chen Wei", "Asia/Singapore"),
]


def seed() -> None:
    create_all()

    with session_scope() as session:
        existing = session.execute(
            select(Team).where(Team.slug == DEMO_TEAM_SLUG)
        ).scalar_one_or_none()

        if existing is not None:
            print(f"Team {DEMO_TEAM_SLUG!r} already seeded; nothing to do.")
            return

        team = Team(
            slug=DEMO_TEAM_SLUG,
            name="Core Platform",
            tz_default="UTC",
            prompt_local_time="09:00",
            cutoff_local_time="11:00",
        )
        session.add(team)
        session.flush()

        for name, tz in DEMO_MEMBERS:
            session.add(
                Member(
                    team_id=team.id,
                    display_name=name,
                    tz=tz,
                    source_keys={"webform": name.lower().replace(" ", ".")},
                )
            )

        print(f"Seeded team {team.name!r} with {len(DEMO_MEMBERS)} members.")
        print("Now run: uvicorn standup.main:app --reload")


if __name__ == "__main__":
    seed()
