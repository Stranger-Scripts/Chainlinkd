"""The Analysis surface: a read-only table of per-habit metrics.

Opened from the dashboard with ``a``. Every number is derived on demand from
the logs by the pure functions in :mod:`chainlinkd.analytics` -- this screen
only arranges them, holding no state of its own.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

from . import analytics


class AnalysisScreen(Screen):
    """Current streak, longest streak, completion rate and total completions
    per habit, plus the longest streak across all habits.
    """

    CSS = """
    DataTable { height: 1fr; }
    #summary { padding: 1 2; text-style: bold; }
    """

    BINDINGS = [
        ("a", "back", "Back"),
        ("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="analysis", cursor_type="row")
        yield Label("", id="summary")
        yield Footer()

    def on_mount(self) -> None:
        self.app.sub_title = "Analysis"
        table = self.query_one("#analysis", DataTable)
        table.add_columns(
            "Habit", "Cadence", "Current", "Longest", "Rate", "Total"
        )

        today = self.app.repo.today()
        habits = self.app.repo.list_all()
        for habit in habits:
            table.add_row(
                habit.name,
                habit.periodicity.label,
                str(analytics.current_streak(habit, today)),
                str(analytics.longest_streak(habit)),
                f"{analytics.completion_rate(habit, today):.0%}",
                str(analytics.total_completions(habit)),
                key=str(habit.id),
            )

        overall = analytics.longest_streak_overall(habits)
        self.query_one("#summary", Label).update(
            f"Longest streak across all habits: {overall}"
        )

    def action_back(self) -> None:
        self.dismiss()
