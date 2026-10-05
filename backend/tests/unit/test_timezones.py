"""Team-local cycle dates and cutoffs."""

from datetime import UTC, date, datetime

from standup.domain.timezones import cutoff_utc, local_cycle_date


def test_local_date_differs_from_utc_date_east_of_greenwich():
    # 23:30 UTC on the 14th is already 07:30 on the 15th in Singapore.
    now = datetime(2026, 9, 14, 23, 30, tzinfo=UTC)
    assert now.date() == date(2026, 9, 14)
    assert local_cycle_date(now, "Asia/Singapore") == date(2026, 9, 15)


def test_local_date_differs_from_utc_date_west_of_greenwich():
    # 01:00 UTC on the 15th is still 22:00 on the 14th in Sao Paulo.
    now = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)
    assert local_cycle_date(now, "America/Sao_Paulo") == date(2026, 9, 14)


def test_cutoff_is_local_wall_clock_time_converted_to_utc():
    assert cutoff_utc(date(2026, 9, 15), "11:00", "Asia/Singapore") == datetime(
        2026, 9, 15, 3, 0, tzinfo=UTC
    )


def test_cutoff_follows_daylight_saving():
    # London is UTC+1 in summer and UTC+0 in winter; 11:00 local tracks it.
    summer = cutoff_utc(date(2026, 7, 1), "11:00", "Europe/London")
    winter = cutoff_utc(date(2026, 12, 1), "11:00", "Europe/London")
    assert summer.hour == 10
    assert winter.hour == 11
