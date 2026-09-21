"""The Manage surface: create, edit and delete habits.

Reached from the dashboard with ``n`` / ``e`` / ``d``. ManageScreen lists every
habit and owns the three actions; the actual field entry and the delete
confirmation are small modal screens. All persistence goes through
``app.repo``
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
)

from .models import Habit, periodicity_from_label

_CADENCES = [("Daily", "daily"), ("Weekly", "weekly")]


class HabitFormScreen(ModalScreen):
    """Collect a habit's name, description and cadence.

    Dismisses with a ``dict`` of the field values, or ``None`` if cancelled.
    Pre-fills from ``habit`` when editing.
    """

    CSS = """
    HabitFormScreen { align: center middle; }
    #form {
        width: 60; height: auto; padding: 1 2;
        border: thick $accent; background: $surface;
    }
    #form Input, #form Select { margin-bottom: 1; }
    #title { text-style: bold; margin-bottom: 1; }
    #buttons { height: auto; align-horizontal: right; }
    #buttons Button { margin-left: 2; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, habit: Habit | None = None) -> None:
        super().__init__()
        self._habit = habit

    def compose(self) -> ComposeResult:
        editing = self._habit is not None
        with Vertical(id="form"):
            yield Label("Edit habit" if editing else "New habit", id="title")
            yield Input(
                value=self._habit.name if editing else "",
                placeholder="Name",
                id="name",
            )
            yield Input(
                value=self._habit.description if editing else "",
                placeholder="Description (optional)",
                id="description",
            )
            yield Select(
                _CADENCES,
                value=self._habit.periodicity.label if editing else "daily",
                allow_blank=False,
                id="cadence",
            )
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", variant="primary", id="save")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._submit()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter from either text field saves the form.
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        if not name:
            self.notify("Name is required.", severity="error")
            self.query_one("#name", Input).focus()
            return
        self.dismiss(
            {
                "name": name,
                "description": self.query_one("#description", Input).value.strip(),
                "periodicity": self.query_one("#cadence", Select).value,
            }
        )


class ConfirmScreen(ModalScreen):
    """A yes/no dialog. Dismisses with ``True`` only if confirmed."""

    CSS = """
    ConfirmScreen { align: center middle; }
    #dialog {
        width: 60; height: auto; padding: 1 2;
        border: thick $error; background: $surface;
    }
    #buttons { height: auto; align-horizontal: right; margin-top: 1; }
    #buttons Button { margin-left: 2; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._question)
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Delete", variant="error", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


class ManageScreen(Screen):
    """List every habit and create / edit / delete them."""

    CSS = "DataTable { height: 1fr; }"

    BINDINGS = [
        ("n", "new", "New"),
        ("e", "edit", "Edit"),
        ("d", "delete", "Delete"),
        ("escape", "back", "Back"),
    ]

    def __init__(
        self, open_mode: str | None = None, habit_id: int | None = None
    ) -> None:
        super().__init__()
        self._open_mode = open_mode
        self._habit_id = habit_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="manage", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#manage", DataTable)
        table.add_columns("Habit", "Cadence", "Description")
        self.sub_title = "Manage"
        self.refresh_table()
        # Honour the action the dashboard opened us for.
        if self._open_mode == "new":
            self.action_new()
        elif self._open_mode == "edit":
            self._select_row(self._habit_id)
            self.action_edit()
        elif self._open_mode == "delete":
            self._select_row(self._habit_id)
            self.action_delete()

    # --- table -----------------------------------------------------------

    def refresh_table(self) -> None:
        table = self.query_one("#manage", DataTable)
        table.clear()
        for habit in self.app.repo.list_all():
            table.add_row(
                habit.name,
                habit.periodicity.label,
                habit.description or "—",
                key=str(habit.id),
            )

    def _select_row(self, habit_id: int | None) -> None:
        if habit_id is None:
            return
        table = self.query_one("#manage", DataTable)
        try:
            table.move_cursor(row=table.get_row_index(str(habit_id)))
        except Exception:
            pass

    def _selected_id(self) -> int | None:
        table = self.query_one("#manage", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return int(row_key.value)

    # --- actions ---------------------------------------------------------

    def action_new(self) -> None:
        self.app.push_screen(HabitFormScreen(), self._create)

    def _create(self, data: dict | None) -> None:
        if not data:
            return
        habit = Habit(
            name=data["name"],
            description=data["description"],
            periodicity=periodicity_from_label(data["periodicity"]),
        )
        self.app.repo.add(habit)
        self.notify(f"Created “{habit.name}”.")
        self.refresh_table()

    def action_edit(self) -> None:
        habit_id = self._selected_id()
        if habit_id is None:
            self.notify("No habit selected.", severity="warning")
            return
        habit = self.app.repo.get(habit_id)
        self.app.push_screen(
            HabitFormScreen(habit), lambda data: self._save(habit_id, data)
        )

    def _save(self, habit_id: int, data: dict | None) -> None:
        if not data:
            return
        self.app.repo.update(
            habit_id,
            name=data["name"],
            description=data["description"],
            periodicity=periodicity_from_label(data["periodicity"]),
        )
        self.notify("Saved.")
        self.refresh_table()

    def action_delete(self) -> None:
        habit_id = self._selected_id()
        if habit_id is None:
            self.notify("No habit selected.", severity="warning")
            return
        habit = self.app.repo.get(habit_id)
        self.app.push_screen(
            ConfirmScreen(f"Delete “{habit.name}” and its history?"),
            lambda ok: self._delete(habit_id, habit.name, ok),
        )

    def _delete(self, habit_id: int, name: str, ok: bool) -> None:
        if not ok:
            return
        self.app.repo.delete(habit_id)
        self.notify(f"Deleted “{name}”.")
        self.refresh_table()

    def action_back(self) -> None:
        self.dismiss()
