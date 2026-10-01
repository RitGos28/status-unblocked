"""Seed a demo team so the app is usable immediately after checkout.

Run: python -m scripts.seed_demo [--with-updates]
"""

import argparse
from datetime import UTC, datetime

from sqlalchemy import select

from scripts.issue_links import print_links
from standup.db.models import Member, Team, Update
from standup.db.session import create_all, session_scope
from standup.ingestion.service import get_or_create_open_cycle, ingest
from standup.ingestion.web_adapter import WebFormAdapter

DEMO_TEAM_SLUG = "core"

DEMO_MEMBERS = [
    ("Ada Okafor", "Europe/London"),
    ("Bruno Silva", "America/Sao_Paulo"),
    ("Chen Wei", "Asia/Singapore"),
]


DEMO_UPDATES = {
    "Ada Okafor": {
        "progress": "Shipped the retry logic and reviewed the deployment plan.",
        "blockers": "Waiting on staging credentials from infra.",
        "plan": "Finish the migration and verify the rollout.",
    },
    "Bruno Silva": {
        "progress": "Fixed the flaky integration test.",
        "blockers": "No blockers today.",
        "plan": "Review the database changes.",
    },
    "Chen Wei": {
        "progress": "Drafted the schema update.",
        "blockers": "",
        "plan": "Pair with Ada on the migration.",
    },
}


def seed(*, with_updates: bool = False) -> None:
    create_all()

    with session_scope() as session:
        existing = session.execute(
            select(Team).where(Team.slug == DEMO_TEAM_SLUG)
        ).scalar_one_or_none()

        if existing is not None:
            team = existing
            print(f"Team {DEMO_TEAM_SLUG!r} already seeded.")
        else:
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
            session.flush()
            print(f"Seeded team {team.name!r} with {len(DEMO_MEMBERS)} members.")

        if with_updates:
            now = datetime.now(UTC)
            cycle = get_or_create_open_cycle(session, team, now)
            existing_member_ids = set(
                session.execute(
                    select(Update.member_id).where(Update.cycle_id == cycle.id)
                ).scalars()
            )
            members = session.execute(
                select(Member).where(Member.team_id == team.id, Member.active.is_(True))
            ).scalars()
            adapter = WebFormAdapter()
            added = 0
            for member in members:
                if member.id in existing_member_ids:
                    continue
                fields = DEMO_UPDATES.get(member.display_name)
                if fields is None:
                    continue
                submission = adapter.to_raw_submission(
                    {"member_id": member.id, **fields, "captured_at": now}
                )
                ingest(
                    session,
                    submission,
                    member,
                    now,
                    permalink_reason="webform: no platform message to link to",
                )
                added += 1
            print(f"Added {added} demo updates for {cycle.local_date}.")

    print("\nPersonal login links (each signs in as that person):")
    print_links(DEMO_TEAM_SLUG)
    print("\nNow run: uvicorn standup.main:app --reload")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--with-updates", action="store_true", help="add today's sample updates")
    seed(with_updates=parser.parse_args().with_updates)
