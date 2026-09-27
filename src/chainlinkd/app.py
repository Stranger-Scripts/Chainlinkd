"""Textual UI for Chainlinkd.

This is the presentation layer: it renders screens and turns key presses into
repository/domain calls. The dashboard is the home surface — today's habits,
their chains and streaks. Arrow keys move the cursor and the *displayed day* so
past periods can be filled in; ``n`` / ``e`` / ``d`` open Manage; ``s`` opens
Settings. Analysis (``a``) is a later milestone.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from . import analytics
from .analysis import AnalysisScreen
from .manage import ManageScreen
from .models import Habit
from .repository import ClockWentBackwardError, HabitRepository, connect
from .settings import SettingsScreen

def _chain(habit: Habit, last_day: date) -> str:
    """Render the ``width`` periods ending at ``last_day`` as links: ○○●●●●●"""
    periodicity = habit.periodicity
    done = set(habit.completed_periods())

    periods: list[date] = []
    cursor = periodicity.period_start(last_day)
    for _ in range(periodicity.chain_length):
        periods.append(cursor)
        cursor = periodicity.period_start(cursor - timedelta(days=1))
    periods.reverse()  # oldest → newest

    labels = [periodicity.tick_label(p) for p in periods]
    cells = [
        f"{label}{'●' if period in done else '○'}" if label
        else ("●" if period in done else "○")
        for period, label in zip(periods, labels)
    ]
    return " ".join(cells) if any(labels) else "".join(cells)


class DashboardScreen(Screen):
    """Home surface: habits, streak chains, and a movable viewing day."""

    CSS = "DataTable { height: 1fr; }"

    BINDINGS = [
        ("space", "toggle", "Toggle"),
        Binding("left", "prev_day", "Prev day", priority=True),
        Binding("right", "next_day", "Next day", priority=True),
        ("t", "today", "Today"),
        ("n", "manage_new", "New"),
        ("e", "manage_edit", "Edit"),
        ("d", "manage_delete", "Delete"),
        ("a", "analysis", "Analysis"),
        ("s", "settings", "Settings"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._viewing_day: date = date.today()

    @property
    def repo(self) -> HabitRepository:
        return self.app.repo

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="habits", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#habits", DataTable)
        table.add_columns("Habit", "Cadence", "Chain", "Streak", "Rate")
        table.focus()
        self._viewing_day = self.repo.today()
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

    # --- rendering -------------------------------------------------------

    def refresh_table(self) -> None:
        table = self.query_one("#habits", DataTable)
        prior_row = table.cursor_row
        table.clear()
        view, today = self._viewing_day, self.repo.today()
        for habit in self.repo.list_all():
            table.add_row(
                habit.name,
                habit.periodicity.label,
                _chain(habit, view),
                str(analytics.current_streak(habit, today)),
                f"{analytics.completion_rate(habit, today):.0%}",
                key=str(habit.id),
            )
        if table.row_count:
            table.move_cursor(row=min(prior_row, table.row_count - 1))

        label = view.strftime("%a %d %b %Y")
        self.app.sub_title = f"{label} · today" if view == today else f"{label} · viewing past"

    def _selected_habit(self) -> Habit | None:
        table = self.query_one("#habits", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return self.repo.get(int(row_key.value))

    # --- day navigation --------------------------------------------------

    def action_prev_day(self) -> None:
        self._viewing_day -= timedelta(days=1)
        self.refresh_table()

    def action_next_day(self) -> None:
        # Never advance past today — the future can't be logged.
        if self._viewing_day < self.repo.today():
            self._viewing_day += timedelta(days=1)
            self.refresh_table()

    def action_today(self) -> None:
        self._viewing_day = self.repo.today()
        self.refresh_table()

    # --- toggling --------------------------------------------------------

    def action_toggle(self) -> None:
        habit = self._selected_habit()
        if habit is None:
            return
        day = self._viewing_day
        period_start = habit.periodicity.period_start(day)
        if period_start in habit.completed_periods():
            self.repo.unlog(habit.id, period_start)
        else:
            try:
                if day >= self.repo.today():
                    self.repo.log(habit.id)  # 'now' — clock-guarded
                else:
                    self.repo.log(habit.id, at=self._noon(day))  # past backfill
            except ClockWentBackwardError as exc:
                self.notify(str(exc), title="Clock warning", severity="error")
                return
        self.refresh_table()

    def _noon(self, day: date) -> datetime:
        """Midday on ``day`` in the configured zone, so it lands on that day."""
        return datetime.combine(day, time(12), tzinfo=self.repo.clock().tz)

    # --- other screens ---------------------------------------------------

    def _open_manage(self, mode: str) -> None:
        habit = self._selected_habit()
        habit_id = habit.id if habit else None
        self.app.push_screen(
            ManageScreen(mode, habit_id), lambda _result: self.refresh_table()
        )

    def action_manage_new(self) -> None:
        self._open_manage("new")

    def action_manage_edit(self) -> None:
        self._open_manage("edit")

    def action_manage_delete(self) -> None:
        self._open_manage("delete")

    def action_analysis(self) -> None:
        self.app.push_screen(AnalysisScreen(), lambda _result: self.refresh_table())

    def action_settings(self) -> None:
        self.app.push_screen(SettingsScreen(), self._after_settings)

    def _after_settings(self, changed: bool | None) -> None:
        if changed:
            # A new zone may have moved "today"; keep the viewing day in range.
            self._viewing_day = min(self._viewing_day, self.repo.today())
        self.refresh_table()


class ChainlinkdApp(App):
    """The application shell: owns the repository and hosts the screens."""

    TITLE = "Chainlinkd"
    SUB_TITLE = "Don't break the chain"

    def __init__(self, repo: HabitRepository | None = None) -> None:
        super().__init__()
        self.repo = repo or HabitRepository(connect())
        self.repo.seed_if_empty()

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())
