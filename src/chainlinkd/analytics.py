"""Analytics for Chainlinkd, written in the functional paradigm.

Analysis is a read-only transformation of immutable habit data into a number
or a smaller list, so the natural unit is a stateless function rather than a
class. Streaks are derived here on demand, never stored, so no cached counter
can drift out of agreement with the logs.
"""

from __future__ import annotations

from datetime import date
from functools import reduce
from itertools import groupby
from typing import NamedTuple

from .models import Habit


def list_habits(habits: list[Habit]) -> list[str]:
    """Return every tracked habit's name."""
    return [habit.name for habit in habits]


def habits_by_periodicity(habits: list[Habit], label: str) -> list[Habit]:
    """Return the habits whose cadence matches ``label`` (e.g. ``"daily"``)."""
    return [h for h in habits if h.periodicity.label == label]


def group_by_periodicity(habits: list[Habit]) -> dict[str, list[Habit]]:
    """Group habits by cadence label using :func:`itertools.groupby`."""
    ordered = sorted(habits, key=lambda h: h.periodicity.label)
    return {
        label: list(group)
        for label, group in groupby(ordered, key=lambda h: h.periodicity.label)
    }


class _Fold(NamedTuple):
    """Accumulator for the streak fold."""

    current: int
    best: int
    previous: date | None


def longest_streak(habit: Habit) -> int:
    """Length of the longest run of consecutive completed periods.

    Folds the sorted period starts, asking the habit's periodicity at each
    step whether a period immediately follows the previous one. Because that
    test is delegated to the cadence, the identical fold computes daily,
    weekly and later monthly streaks.
    """
    periodicity = habit.periodicity

    def step(acc: _Fold, period: date) -> _Fold:
        consecutive = (
            acc.previous is not None
            and periodicity.next_period(acc.previous) == period
        )
        current = acc.current + 1 if consecutive else 1
        return _Fold(current, max(acc.best, current), period)

    return reduce(step, habit.completed_periods(), _Fold(0, 0, None)).best


def current_streak(habit: Habit, on: date | None = None) -> int:
    """Length of the run of consecutive completed periods ending at ``on``.

    Counts backwards from the period containing ``on``. A period that is not
    yet complete does not break the streak (the current period may still be
    open), but any genuine gap before it does.
    """
    on = on or date.today()
    periodicity = habit.periodicity
    done = set(habit.completed_periods())

    cursor = periodicity.period_start(on)
    if cursor not in done:
        # current period still open — start counting from the previous one
        cursor = _previous_period(periodicity, cursor)

    streak = 0
    while cursor in done:
        streak += 1
        cursor = _previous_period(periodicity, cursor)
    return streak


def longest_streak_overall(habits: list[Habit]) -> int:
    """The longest streak achieved across all habits (0 if none)."""
    return max((longest_streak(h) for h in habits), default=0)


def completion_rate(habit: Habit, on: date | None = None) -> float:
    """Fraction of periods completed since creation, in ``[0.0, 1.0]``.

    The denominator is the number of periods from the habit's creation date
    through the period containing ``on``, inclusive.
    """
    on = on or date.today()
    periodicity = habit.periodicity
    start = periodicity.period_start(habit.created_at.date())
    end = periodicity.period_start(on)
    total = periodicity.periods_between(start, end) + 1
    if total <= 0:
        return 0.0
    return len(habit.completed_periods()) / total


def _previous_period(periodicity, day: date) -> date:
    """Return the ``period_start`` of the period immediately before ``day``'s.

    Derived from ``next_period`` by stepping back one day and normalising, so
    every cadence gets it for free without a dedicated ``prev`` method.
    """
    from datetime import timedelta

    return periodicity.period_start(periodicity.period_start(day) - timedelta(days=1))
