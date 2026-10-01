"""Seed demo teams so the app is usable, and demoable, immediately after checkout.

Run: python -m scripts.seed_demo [--with-updates] [--days N]

- Always: team "Core Platform" (3 members) and team "Mobile" (1 member), so
  the cross-team 404 can be shown. Safe to re-run.
- --with-updates: today's made-up updates for Core Platform.
- --days N: N days of made-up updates, ending today (implies --with-updates).
  Earlier days are filed at 09:00 UTC, before the 11:00 cutoff, through the
  same ingest() path the web form uses. Ada's blocker repeats every day, and
  Chen files a blocker under Progress, so recurrence and promotion can be shown.
"""

import argparse
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.issue_links import print_links
from standup.db.models import Member, Team, Update
from standup.db.session import create_all, session_scope
from standup.ingestion.service import get_or_create_open_cycle, ingest
from standup.ingestion.web_adapter import WebFormAdapter

DEMO_TEAM_SLUG = "core"
OTHER_TEAM_SLUG = "mobile"

DEMO_MEMBERS = [
    ("Ada Okafor", "Europe/London"),
    ("Bruno Silva", "America/Sao_Paulo"),
    ("Chen Wei", "Asia/Singapore"),
]
OTHER_MEMBERS = [("Dana Park", "UTC")]


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
        # The second sentence is a blocker filed under Progress: the digest
        # moves it to Blockers and says why.
        "progress": "Drafted the schema update. Stuck on the deploy pipeline.",
        "blockers": "",
        "plan": "Pair with Ada on the migration.",
    },
}

# Earlier days. Ada's blocker is word-for-word the same as today's, so it is
# recognised as the same blocker across days.
EARLIER_UPDATES = {
    "Ada Okafor": {
        "progress": "Wrote the retry logic tests.",
        "blockers": "Waiting on staging credentials from infra.",
        "plan": "Ship the retry logic.",
    },
    "Bruno Silva": {
        "progress": "Reproduced the flaky integration test.",
        "blockers": "Not blocked.",
        "plan": "Fix the flaky test.",
    },
    "Chen Wei": {
        "progress": "Read the schema migration notes.",
        "blockers": "",
        "plan": "Draft the schema update.",
    },
}

EARLIER_DAY_TIME = time(9, 0)


def _ensure_team(
    session: Session, slug: str, name: str, members: list[tuple[str, str]]
) -> Team:
    team = session.execute(select(Team).where(Team.slug == slug)).scalar_one_or_none()
    if team is not None:
        print(f"Team {slug!r} already seeded.")
        return team
    team = Team(
        slug=slug,
        name=name,
        tz_default="UTC",
        prompt_local_time="09:00",
        cutoff_local_time="11:00",
    )
    session.add(team)
    session.flush()
    for display_name, tz in members:
        session.add(
            Member(
                team_id=team.id,
                display_name=display_name,
                tz=tz,
                source_keys={"webform": display_name.lower().replace(" ", ".")},
            )
        )
    session.flush()
    print(f"Seeded team {name!r} with {len(members)} member(s).")
    return team


def _file_day(
    session: Session, team: Team, when: datetime, updates: dict[str, dict[str, str]]
) -> int:
    """File one day's updates for ``team`` at ``when``, skipping anyone who
    already has an update that day. Returns how many were added."""
    cycle = get_or_create_open_cycle(session, team, when)
    already = set(
        session.execute(select(Update.member_id).where(Update.cycle_id == cycle.id)).scalars()
    )
    members = session.execute(
        select(Member).where(Member.team_id == team.id, Member.active.is_(True))
    ).scalars()
    adapter = WebFormAdapter()
    added = 0
    for member in members:
        fields = updates.get(member.display_name)
        if member.id in already or fields is None:
            continue
        submission = adapter.to_raw_submission(
            {"member_id": member.id, **fields, "captured_at": when}
        )
        ingest(
            session,
            submission,
            member,
            when,
            permalink_reason="webform: no platform message to link to",
        )
        added += 1
    print(f"Added {added} demo update(s) for {cycle.local_date}.")
    return added


def seed(*, with_updates: bool = False, days: int = 0, now: datetime | None = None) -> None:
    create_all()
    now = now or datetime.now(UTC)
    if with_updates and days < 1:
        days = 1

    with session_scope() as session:
        team = _ensure_team(session, DEMO_TEAM_SLUG, "Core Platform", DEMO_MEMBERS)
        _ensure_team(session, OTHER_TEAM_SLUG, "Mobile", OTHER_MEMBERS)

        for offset in range(days - 1, -1, -1):
            if offset == 0:
                _file_day(session, team, now, DEMO_UPDATES)
            else:
                day = (now - timedelta(days=offset)).date()
                when = datetime.combine(day, EARLIER_DAY_TIME, tzinfo=UTC)
                _file_day(session, team, when, EARLIER_UPDATES)

    print("\nPersonal login links (each signs in as that person):")
    print_links()
    print("\nNow run: uvicorn standup.main:app --reload")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--with-updates", action="store_true", help="add today's sample updates")
    parser.add_argument(
        "--days", type=int, default=0, help="add N days of sample updates, ending today"
    )
    args = parser.parse_args()
    seed(with_updates=args.with_updates, days=args.days)
