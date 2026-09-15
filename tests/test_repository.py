from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from chainlinkd import analytics
from chainlinkd.models import DAILY, WEEKLY, Habit
from chainlinkd.repository import (
    ClockWentBackwardError,
    HabitRepository,
    connect,
)


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    # Pin to UTC so date assertions are independent of the sandbox's zone.
    r = HabitRepository(connect(":memory:"))
    r.set_timezone("UTC")
    return r


def test_add_assigns_id_and_roundtrips(repo):
    h = Habit(name="Meditate", description="Stillness", periodicity=WEEKLY)
    h.complete(_dt(2026, 9, 15))
    repo.add(h)

    assert h.id is not None
    loaded = repo.get(h.id)
    assert loaded.name == "Meditate"
    assert loaded.description == "Stillness"
    assert loaded.periodicity is WEEKLY
    assert loaded.completed_periods() == [date(2026, 9, 14)]


def test_list_all_orders_by_creation(repo):
    repo.add(Habit(name="First", created_at=_dt(2026, 9, 1)))
    repo.add(Habit(name="Second", created_at=_dt(2026, 9, 2)))
    assert analytics.list_habits(repo.list_all()) == ["First", "Second"]


def test_delete_cascades_to_logs(repo):
    h = Habit(name="Run")
    h.complete(_dt(2026, 9, 15))
    repo.add(h)

    repo.delete(h.id)
    assert repo.get(h.id) is None
    orphans = repo.conn.execute(
        "SELECT COUNT(*) AS n FROM habit_logs WHERE habit_id = ?", (h.id,)
    ).fetchone()["n"]
    assert orphans == 0


def test_log_is_idempotent_per_period(repo):
    h = repo.add(Habit(name="Read", periodicity=DAILY))
    repo.log(h.id, _dt(2026, 9, 15))
    repo.log(h.id, _dt(2026, 9, 15))  # same period again

    count = repo.conn.execute(
        "SELECT COUNT(*) AS n FROM habit_logs WHERE habit_id = ?", (h.id,)
    ).fetchone()["n"]
    assert count == 1


def test_unlog_toggles_off(repo):
    h = repo.add(Habit(name="Read"))
    repo.log(h.id, _dt(2026, 9, 15))
    repo.unlog(h.id, date(2026, 9, 15))
    assert repo.get(h.id).completed_periods() == []


def test_seed_if_empty_runs_once(repo):
    assert repo.seed_if_empty() is True
    seeded = repo.list_all()
    assert len(seeded) == 5
    # second call is a no-op guarded by the meta flag
    assert repo.seed_if_empty() is False
    assert len(repo.list_all()) == 5


# --- timezone --------------------------------------------------------------


def test_timezone_default_is_set_on_first_run():
    fresh = HabitRepository(connect(":memory:"))
    assert fresh.get_timezone()  # non-empty, a valid IANA key
    ZoneInfo(fresh.get_timezone())  # would raise if invalid


def test_set_timezone_validates_and_flows_to_habits(repo):
    with pytest.raises(ValueError):
        repo.set_timezone("Mars/Phobos")
    repo.set_timezone("Europe/Berlin")
    assert repo.get_timezone() == "Europe/Berlin"

    h = repo.add(Habit(name="Read"))
    assert repo.get(h.id).clock.tz == ZoneInfo("Europe/Berlin")


# --- backward-clock guard --------------------------------------------------


def test_backward_clock_blocks_logging_now(repo):
    h = repo.add(Habit(name="Run"))
    repo.mark_seen(datetime.now(timezone.utc) + timedelta(days=1))  # future mark

    with pytest.raises(ClockWentBackwardError):
        repo.log(h.id)  # claiming a completion 'now' under a rewound clock
    assert repo.get(h.id).completed_periods() == []

    repo.log(h.id, allow_backward=True)  # explicit override still works
    assert repo.get(h.id).completed_periods()


def test_backward_clock_allows_past_backfill(repo):
    h = repo.add(Habit(name="Run"))
    repo.mark_seen(datetime.now(timezone.utc) + timedelta(days=1))
    # An explicit past timestamp is a legitimate backfill, not a 'now' claim.
    repo.log(h.id, at=_dt(2026, 9, 1))
    assert repo.get(h.id).completed_periods() == [date(2026, 9, 1)]


def test_mark_seen_ratchets_forward_only(repo):
    late = _dt(2026, 9, 2)
    repo.mark_seen(late)
    repo.mark_seen(_dt(2026, 9, 1))  # earlier: must not lower the mark
    assert repo.last_seen() == late


# --- update ----------------------------------------------------------------


def test_update_edits_fields_without_touching_logs(repo):
    h = repo.add(Habit(name="Old", description="a", periodicity=DAILY))
    repo.log(h.id, at=_dt(2026, 9, 15))

    updated = repo.update(h.id, name="New", description="b")
    assert (updated.name, updated.description) == ("New", "b")
    assert updated.periodicity is DAILY
    assert updated.completed_periods() == [date(2026, 9, 15)]


def test_update_rejects_blank_name(repo):
    h = repo.add(Habit(name="Keep"))
    with pytest.raises(ValueError):
        repo.update(h.id, name="   ")


def test_update_cadence_recomputes_and_dedupes(repo):
    # Mon/Tue/Wed of the same ISO week (2026-09-14 is a Monday).
    h = repo.add(Habit(name="Move", periodicity=DAILY))
    for day in (14, 15, 16):
        repo.log(h.id, at=_dt(2026, 9, day))

    updated = repo.update(h.id, periodicity=WEEKLY)
    assert updated.periodicity is WEEKLY
    # Three daily completions collapse onto the one week start...
    assert updated.completed_periods() == [date(2026, 9, 14)]
    # ...and exactly one row survives, so UNIQUE(habit_id, period_start) holds.
    surviving = repo.conn.execute(
        "SELECT COUNT(*) AS n FROM habit_logs WHERE habit_id = ?", (h.id,)
    ).fetchone()["n"]
    assert surviving == 1


def test_seed_shapes_match_concept():
    repo = HabitRepository(connect(":memory:"))
    repo.set_timezone("UTC")
    today = date(2026, 9, 15)
    from chainlinkd.seed import seed_habits

    for h in seed_habits(today):
        repo.add(h)
    by_name = {h.name: h for h in repo.list_all()}

    # unbroken 28-day daily chain
    assert analytics.current_streak(by_name["Meditate"], today) == 28
    assert analytics.longest_streak(by_name["Meditate"]) == 28
    # gap splits into two runs; nothing recent
    assert analytics.longest_streak(by_name["Exercise"]) == 9
    assert analytics.current_streak(by_name["Exercise"], today) == 0
    # run still open at the window's end
    assert analytics.current_streak(by_name["Read"], today) == 10
