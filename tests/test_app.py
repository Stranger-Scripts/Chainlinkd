"""Integration tests that drive the Textual UI with the pilot.

These exercise the Manage flow end to end — key press → modal → repository —
against an in-memory database, which is the only screen coverage the concept
asks for (the rest of the layering makes snapshot tests unnecessary).
"""

import asyncio

from textual.widgets import Input

from chainlinkd.app import ChainlinkdApp
from chainlinkd.repository import HabitRepository, connect


def _app() -> ChainlinkdApp:
    repo = HabitRepository(connect(":memory:"))
    repo.set_timezone("UTC")
    return ChainlinkdApp(repo=repo)


def _run(scenario) -> None:
    asyncio.run(scenario())


def test_create_habit_through_manage():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            before = {h.name for h in app.repo.list_all()}
            await pilot.press("n")            # dashboard -> Manage(new) -> form
            await pilot.pause()
            await pilot.press(*"floss")        # type into the focused name field
            await pilot.press("enter")         # submit the form
            await pilot.pause()
            names = {h.name for h in app.repo.list_all()}
        assert "floss" in names
        assert names - before == {"floss"}

    _run(scenario)


def test_edit_habit_through_manage():
    async def scenario():
        app = _app()
        async with app.run_test() as pilot:
            target = app.repo.list_all()[0]  # cursor starts on the first row
            await pilot.press("e")            # Manage(edit) opens the pre-filled form
            await pilot.pause()
            name_field = app.screen.query_one("#name", Input)  # the modal on top
            assert name_field.value == target.name  # pre-filled from the habit
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
            target = app.repo.list_all()[0]
            await pilot.press("d")            # Manage(delete) -> confirm dialog
            await pilot.pause()
            await pilot.click("#confirm")      # confirm the deletion
            await pilot.pause()
            gone = app.repo.get(target.id)
        assert gone is None

    _run(scenario)
