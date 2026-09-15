from datetime import date, datetime, timezone

import pytest

from chainlinkd import analytics
from chainlinkd.models import DAILY, WEEKLY, Habit
from chainlinkd.repository import HabitRepository, connect


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    return HabitRepository(connect(":memory:"))


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


def test_seed_shapes_match_concept():
    repo = HabitRepository(connect(":memory:"))
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
