from datetime import date, datetime, timezone

import pytest

from chainlinkd import analytics
from chainlinkd.models import (
    DAILY,
    WEEKLY,
    Habit,
    periodicity_from_label,
)


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


# --- periodicity ---------------------------------------------------------


def test_daily_period_boundaries():
    assert DAILY.period_start(date(2026, 9, 15)) == date(2026, 9, 15)
    assert DAILY.next_period(date(2026, 9, 15)) == date(2026, 9, 16)


def test_weekly_period_starts_on_monday():
    # 2026-09-15 is a Tuesday; its week starts Monday the 14th.
    assert WEEKLY.period_start(date(2026, 9, 15)) == date(2026, 9, 14)
    assert WEEKLY.next_period(date(2026, 9, 15)) == date(2026, 9, 21)


def test_periods_between_counts_boundaries():
    assert DAILY.periods_between(date(2026, 9, 1), date(2026, 9, 1)) == 0
    assert DAILY.periods_between(date(2026, 9, 1), date(2026, 9, 4)) == 3
    assert WEEKLY.periods_between(date(2026, 9, 1), date(2026, 9, 15)) == 2


def test_periodicity_from_label_roundtrip():
    assert periodicity_from_label("daily") is DAILY
    assert periodicity_from_label("weekly") is WEEKLY
    with pytest.raises(ValueError):
        periodicity_from_label("monthly")


# --- habit ---------------------------------------------------------------


def test_name_is_stripped_and_required():
    assert Habit(name="  Read  ").name == "Read"
    with pytest.raises(ValueError):
        Habit(name="   ")


def test_complete_sets_period_start_from_cadence():
    h = Habit(name="Meditate", periodicity=WEEKLY)
    log = h.complete(_dt(2026, 9, 15))  # a Tuesday
    assert log.period_start == date(2026, 9, 14)  # Monday
    assert h.completed_periods() == [date(2026, 9, 14)]


def test_is_due_reflects_completion_of_current_period():
    h = Habit(name="Run")
    assert h.is_due(date(2026, 9, 15)) is True
    h.complete(_dt(2026, 9, 15))
    assert h.is_due(date(2026, 9, 15)) is False


# --- analytics streak folds ----------------------------------------------


def test_longest_streak_daily_with_gap():
    h = Habit(name="Exercise")
    for day in (1, 2, 3, 5, 6):  # gap on the 4th
        h.complete(_dt(2026, 9, day))
    assert analytics.longest_streak(h) == 3


def test_current_streak_ignores_open_current_period():
    h = Habit(name="Read")
    # completed the three days before today, but not today itself
    for day in (12, 13, 14):
        h.complete(_dt(2026, 9, day))
    assert analytics.current_streak(h, on=date(2026, 9, 15)) == 3


def test_current_streak_breaks_on_real_gap():
    h = Habit(name="Read")
    for day in (10, 11, 14, 15):  # gap on 12-13
        h.complete(_dt(2026, 9, day))
    assert analytics.current_streak(h, on=date(2026, 9, 15)) == 2


def test_weekly_streak_counts_weeks():
    h = Habit(name="Review", periodicity=WEEKLY)
    for day in (1, 8, 15):  # three consecutive Mondays-ish
        h.complete(_dt(2026, 9, day))
    assert analytics.longest_streak(h) == 3


def test_completion_rate_full_and_partial():
    h = Habit(name="Meditate", created_at=_dt(2026, 9, 13))
    for day in (13, 14, 15):
        h.complete(_dt(2026, 9, day))
    assert analytics.completion_rate(h, on=date(2026, 9, 15)) == 1.0

    h2 = Habit(name="Skip", created_at=_dt(2026, 9, 13))
    h2.complete(_dt(2026, 9, 13))
    assert analytics.completion_rate(h2, on=date(2026, 9, 15)) == pytest.approx(1 / 3)
