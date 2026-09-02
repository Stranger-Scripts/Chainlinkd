"""Textual UI for Chainlinkd."""

from __future__ import annotations

from datetime import date

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Header, Input

from .models import Habit
from .storage import Store


class ChainlinkdApp(App):
    """A minimal habit tracker. Extend the widgets/bindings as you grow it."""

    TITLE = "Chainlinkd"
    SUB_TITLE = "Don't break the chain"

    CSS = """
    #new-habit { dock: bottom; margin: 1 2; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        ("a", "focus_input", "Add habit"),
        ("space", "toggle_today", "Toggle today"),
        ("d", "delete_habit", "Delete"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, store: Store | None = None) -> None:
        super().__init__()
        self.store = store or Store()
        self.db = self.store.load()

    # --- layout ----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="habits", cursor_type="row")
        yield Horizontal(
            Input(placeholder="New habit name…", id="new-habit"),
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#habits", DataTable)
        table.add_columns("Habit", "Frequency", "Today", "Streak")
        self.refresh_table()

    # --- rendering -------------------------------------------------------

    def refresh_table(self) -> None:
        table = self.query_one("#habits", DataTable)
        table.clear()
        today = date.today()
        for habit in self.db.habits:
            mark = "✓" if habit.is_done_on(today) else "·"
            table.add_row(
                habit.name,
                habit.frequency.value,
                mark,
                str(habit.current_streak(today)),
                key=habit.id,
            )

    def _selected_habit(self) -> Habit | None:
        table = self.query_one("#habits", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return next((h for h in self.db.habits if h.id == row_key.value), None)

    # --- actions ---------------------------------------------------------

    def action_focus_input(self) -> None:
        self.query_one("#new-habit", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if name:
            self.db.habits.append(Habit(name=name))
            self.store.save(self.db)
            self.refresh_table()
        event.input.value = ""
        self.query_one("#habits", DataTable).focus()

    def action_toggle_today(self) -> None:
        habit = self._selected_habit()
        if habit is None:
            return
        if habit.is_done_on(date.today()):
            habit.unmark()
        else:
            habit.mark_done()
        self.store.save(self.db)
        self.refresh_table()

    def action_delete_habit(self) -> None:
        habit = self._selected_habit()
        if habit is None:
            return
        self.db.habits = [h for h in self.db.habits if h.id != habit.id]
        self.store.save(self.db)
        self.refresh_table()
