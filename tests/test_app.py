"""Integration tests that drive the Textual UI with the pilot.

These exercise the Manage flow, day-navigation/backfill and Settings end to end
— key press → screen → repository — against an in-memory database, which is the
only screen coverage the concept asks for.
"""

import asyncio
from datetime import timedelta

from textual.widgets import DataTable, Input, Label, Select

from chainlinkd.app import ChainlinkdApp, DashboardScreen
from chainlinkd.models import Habit
from chainlinkd.repository import HabitRepository, connect


def _repo(seeded: bool = True) -> HabitRepository:
    repo = HabitRepository(connect(":memory:"))
    repo.set_timezone("UTC")
    if not seeded:
        repo._set_meta("seeded", "1")  # skip the example habits
    return repo


def _app(repo: HabitRepository | None = None) -> ChainlinkdApp:
    return ChainlinkdApp(repo=repo or _repo())


def _run(scenario) -> None:
    asyncio.run(scenario())


def test_create_habit_through_manage():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            await pilot.pause()
            before = {h.name for h in app.repo.list_all()}
            await pilot.press("n")            # dashboard -> Manage(new) -> form
            await pilot.pause()
            await pilot.press(*"floss")        # type into the focused name field
            await pilot.press("enter")         # submit the form
            await pilot.pause()
            names = {h.name for h in app.repo.list_all()}
        assert names - before == {"floss"}

    _run(scenario)


def test_edit_habit_through_manage():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            await pilot.pause()
            target = app.repo.list_all()[0]  # cursor starts on the first row
            await pilot.press("e")            # Manage(edit) opens the pre-filled form
            await pilot.pause()
            name_field = app.screen.query_one("#name", Input)  # the modal on top
            assert name_field.value == target.name
            name_field.value = ""
            await pilot.press(*"renamed")
            await pilot.press("enter")
            await pilot.pause()
            reloaded = app.repo.get(target.id)
        assert reloaded.name == "renamed"

    _run(scenario)


def test_delete_habit_through_manage():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            await pilot.pause()
            target = app.repo.list_all()[0]
            await pilot.press("d")            # Manage(delete) -> confirm dialog
            await pilot.pause()
            await pilot.click("#confirm")      # confirm the deletion
            await pilot.pause()
            gone = app.repo.get(target.id)
        assert gone is None

    _run(scenario)


def test_backfill_past_day_from_dashboard():
    async def scenario():
        repo = _repo(seeded=False)
        habit = repo.add(Habit(name="Read"))  # no history yet
        app = _app(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("left")          # move the viewing day back one
            await pilot.press("space")         # toggle -> backfills yesterday
            await pilot.pause()
            periods = repo.get(habit.id).completed_periods()
        assert periods == [repo.today() - timedelta(days=1)]

    _run(scenario)


def test_backfill_toggle_off_removes_the_log():
    async def scenario():
        repo = _repo(seeded=False)
        habit = repo.add(Habit(name="Read"))
        app = _app(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("left")
            await pilot.press("space")         # on
            await pilot.press("space")         # off again
            await pilot.pause()
            periods = repo.get(habit.id).completed_periods()
        assert periods == []

    _run(scenario)


def test_cannot_navigate_past_today():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            await pilot.pause()
            dashboard = app.screen
            start = dashboard._viewing_day
            await pilot.press("right")         # already on today -> no-op
            await pilot.pause()
            assert dashboard._viewing_day == start == app.repo.today()

    _run(scenario)


def test_analysis_screen_lists_metrics():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            await pilot.pause()
            expected = len(app.repo.list_all())  # five seeded habits
            await pilot.press("a")             # open Analysis
            await pilot.pause()
            table = app.screen.query_one("#analysis", DataTable)
            columns = [str(c.label) for c in table.columns.values()]
            rows = table.row_count
            summary = str(app.screen.query_one("#summary", Label).render())
            await pilot.press("escape")        # a/esc returns to dashboard
            await pilot.pause()
            returned = isinstance(app.screen, DashboardScreen)
        assert rows == expected
        assert columns == ["Habit", "Cadence", "Current", "Longest", "Rate", "Total"]
        assert "Longest streak across all habits:" in summary
        assert returned  # dashboard is active again

    _run(scenario)


def test_change_timezone_in_settings():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")             # open Settings
            await pilot.pause()
            app.screen.query_one("#tz", Select).value = "Asia/Tokyo"
            await pilot.click("#save")
            await pilot.pause()
            tz = app.repo.get_timezone()
        assert tz == "Asia/Tokyo"

    _run(scenario)
