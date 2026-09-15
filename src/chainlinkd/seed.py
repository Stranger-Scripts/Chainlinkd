"""Predefined habits and four weeks of example tracking data.

The examples are deliberately *not* uniformly complete — complete data
exercises no edge cases. Anchored to a ``today`` (the 28-day window ends
there), the shapes are:

* an unbroken 28-day daily chain,
* a daily habit with a gap that splits it into two runs,
* a daily run still open at the window's end,
* two weekly habits done in some weeks and missed in others.

The fixture therefore doubles as the expected-value table for the streak
tests, which is why ``seed_habits`` accepts an explicit ``today``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from .models import DAILY, WEEKLY, Habit

WINDOW_DAYS = 28


def _at(today: date, days_ago: int) -> datetime:
    """A timestamp at noon UTC, ``days_ago`` days before ``today``."""
    return datetime.combine(today - timedelta(days=days_ago), time(12), timezone.utc)


def seed_habits(today: date | None = None) -> list[Habit]:
    """Build the predefined habits with their example logs.

    Returned habits are unsaved (``id is None``); the repository persists them.
    """
    today = today or date.today()
    created = datetime.combine(
        today - timedelta(days=WINDOW_DAYS - 1), time(0), timezone.utc
    )

    def new(name: str, description: str, periodicity) -> Habit:
        return Habit(
            name=name,
            description=description,
            periodicity=periodicity,
            created_at=created,
        )

    # 1. Unbroken 28-day daily chain: done every day in the window.
    meditate = new("Meditate", "Ten minutes of stillness", DAILY)
    for days_ago in range(WINDOW_DAYS):
        meditate.complete(_at(today, days_ago))

    # 2. Daily habit with a gap → two runs, nothing recent.
    #    days 27..20 done (8), gap 19..17, days 16..8 done (9), then nothing.
    exercise = new("Exercise", "A brisk workout", DAILY)
    for days_ago in [*range(27, 19, -1), *range(16, 7, -1)]:
        exercise.complete(_at(today, days_ago))

    # 3. Daily run still open at the window's end: last 10 days incl. today.
    read = new("Read", "Read a few pages", DAILY)
    for days_ago in range(10):
        read.complete(_at(today, days_ago))

    # 4. Weekly habit done in some weeks, missed the week before last.
    finances = new("Review finances", "Check the budget", WEEKLY)
    for days_ago in (0, 7, 21):
        finances.complete(_at(today, days_ago))

    # 5. Weekly habit with a different partial pattern (missed last week).
    family = new("Call family", "Catch up with family", WEEKLY)
    for days_ago in (3, 17, 24):
        family.complete(_at(today, days_ago))

    return [meditate, exercise, read, finances, family]
