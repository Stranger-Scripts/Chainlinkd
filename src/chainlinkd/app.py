"""Textual UI for Chainlinkd.

This is the presentation layer: it renders screens and turns key presses into
repository/domain calls. It is deliberately thin — the full Dashboard / Manage
/ Analysis surface described in the concept is a later milestone. For now it
reads habits through the repository and toggles today's completion in place.
"""

from __future__ import annotations

from datetime import date, timedelta

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header

from . import analytics
from .repository import ClockWentBackwardError, HabitRepository, connect


def _chain(habit, today: date, width: int = 7) -> str:
    """Render the last ``width`` periods as filled/empty links: ○○●●●●●"""
    periodicity = habit.periodicity
    done = set(habit.completed_periods())
    cells = []
    cursor = periodicity.period_start(today)
    for _ in range(width):
        cells.append("●" if cursor in done else "○")
        cursor = periodicity.period_start(cursor - timedelta(days=1))
    return "".join(reversed(cells))


class ChainlinkdApp(App):
    """A minimal habit tracker backed by the SQLite repository."""

    TITLE = "Chainlinkd"
    SUB_TITLE = "Don't break the chain"

    CSS = "DataTable { height: 1fr; }"

    BINDINGS = [
        ("space", "toggle_today", "Toggle today"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, repo: HabitRepository | None = None) -> None:
        super().__init__()
        self.repo = repo or HabitRepository(connect())
        self.repo.seed_if_empty()

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="habits", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#habits", DataTable)
        table.add_columns("Habit", "Cadence", "Chain", "Streak", "Rate")
        self._warn_if_clock_backward()
        self.refresh_table()

    def _warn_if_clock_backward(self) -> None:
        check = self.repo.clock_check()
        if not check.ok:
            self.notify(
                f"System clock is behind by {check.backward_by}. Streaks use "
                "your clock — new completions for 'now' are blocked until it "
                "catches up.",
                title="Clock warning",
                severity="warning",
                timeout=10,
            )
        self.repo.mark_seen(check.now)

    def refresh_table(self) -> None:
        table = self.query_one("#habits", DataTable)
        table.clear()
        today = self.repo.today()
        for habit in self.repo.list_all():
            table.add_row(
                habit.name,
                habit.periodicity.label,
                _chain(habit, today),
                str(analytics.current_streak(habit, today)),
                f"{analytics.completion_rate(habit, today):.0%}",
                key=str(habit.id),
            )

    def _selected_habit(self):
        table = self.query_one("#habits", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return self.repo.get(int(row_key.value))

    def action_toggle_today(self) -> None:
        habit = self._selected_habit()
        if habit is None:
            return
        today = self.repo.today()
        if habit.is_due(today):
            try:
                self.repo.log(habit.id)
            except ClockWentBackwardError as exc:
                self.notify(str(exc), title="Clock warning", severity="error")
                return
        else:
            self.repo.unlog(habit.id, habit.periodicity.period_start(today))
        self.refresh_table()
