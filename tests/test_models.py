from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from chainlinkd.models import Frequency, Habit


def test_name_is_stripped_and_required():
    assert Habit(name="  Read  ").name == "Read"
    with pytest.raises(ValidationError):
        Habit(name="   ")


def test_mark_done_is_idempotent():
    h = Habit(name="Meditate")
    assert h.mark_done() is True
    assert h.mark_done() is False
    assert h.is_done_on(date.today())


def test_no_future_entries():
    h = Habit(name="Run")
    with pytest.raises(ValidationError):
        h.mark_done(date.today() + timedelta(days=1))


def test_current_streak_counts_consecutive_days():
    h = Habit(name="Journal", frequency=Frequency.DAILY)
    today = date.today()
    for offset in (0, 1, 2):
        h.mark_done(today - timedelta(days=offset))
    assert h.current_streak(today) == 3

    h.unmark(today - timedelta(days=1))
    assert h.current_streak(today) == 1
