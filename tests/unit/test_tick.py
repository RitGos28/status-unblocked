"""The scheduler's decision, as a pure function of time and a snapshot."""

from datetime import UTC, datetime, timedelta

from standup.scheduling.tick import BuildDigest, CycleView, DrainOutbox, NotifyDigest, tick

CUTOFF = datetime(2026, 9, 15, 11, 0, tzinfo=UTC)


def cycle(**overrides) -> CycleView:
    fields = {
        "cycle_id": "c1",
        "cutoff_at": CUTOFF,
        "has_updates": True,
        "last_update_at": CUTOFF - timedelta(hours=2),
        "last_digest_at": None,
    }
    return CycleView(**(fields | overrides))


def builds(jobs) -> list[BuildDigest]:
    return [j for j in jobs if isinstance(j, BuildDigest)]


def test_nothing_is_built_before_the_cutoff():
    assert builds(tick(CUTOFF - timedelta(minutes=1), [cycle()])) == []


def test_first_build_after_the_cutoff_notifies():
    assert builds(tick(CUTOFF, [cycle()])) == [BuildDigest("c1", notify=True)]


def test_an_up_to_date_notified_digest_is_left_alone():
    done = cycle(last_digest_at=CUTOFF + timedelta(minutes=1), notified=True)
    assert tick(CUTOFF + timedelta(hours=1), [done]) == [DrainOutbox()]


def test_a_digest_built_by_hand_before_the_cutoff_is_announced_at_the_cutoff():
    manual = cycle(last_digest_at=CUTOFF - timedelta(minutes=30))
    assert tick(CUTOFF - timedelta(minutes=1), [manual]) == [DrainOutbox()]
    assert tick(CUTOFF, [manual]) == [NotifyDigest("c1"), DrainOutbox()]


def test_a_late_update_triggers_a_quiet_rebuild():
    late = cycle(
        last_digest_at=CUTOFF + timedelta(minutes=1),
        last_update_at=CUTOFF + timedelta(minutes=30),
        notified=True,
    )
    assert builds(tick(CUTOFF + timedelta(hours=1), [late])) == [BuildDigest("c1", notify=False)]


def test_a_cycle_without_updates_or_cutoff_is_skipped():
    assert builds(tick(CUTOFF, [cycle(has_updates=False), cycle(cutoff_at=None)])) == []


def test_the_outbox_is_drained_every_tick():
    assert tick(CUTOFF - timedelta(hours=5), []) == [DrainOutbox()]


def test_simulating_three_days_is_a_loop():
    """One build per day at its cutoff, nothing in between."""
    built: list[str] = []
    digested: dict[str, datetime] = {}
    for minutes in range(0, 3 * 24 * 60, 30):
        now = CUTOFF - timedelta(hours=3) + timedelta(minutes=minutes)
        views = [
            cycle(
                cycle_id=f"day{d}",
                cutoff_at=CUTOFF + timedelta(days=d),
                last_update_at=CUTOFF + timedelta(days=d) - timedelta(hours=1),
                last_digest_at=digested.get(f"day{d}"),
                notified=f"day{d}" in digested,
            )
            for d in range(3)
        ]
        for job in builds(tick(now, views)):
            built.append(job.cycle_id)
            digested[job.cycle_id] = now
    assert built == ["day0", "day1", "day2"]
