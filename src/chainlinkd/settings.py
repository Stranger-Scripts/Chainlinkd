"""The Settings surface: currently just the timezone.

Which calendar day a completion counts for is derived from this zone (see
``models.Clock`` and ``repository``), so changing it here changes how "today"
and every period boundary are computed from now on. Existing logs keep the
``period_start`` they were written with — a change of zone is not applied
retroactively.
"""

from __future__ import annotations

from zoneinfo import available_timezones

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select


class SettingsScreen(ModalScreen):
    """Edit application settings. Dismisses True if anything changed."""

    CSS = """
    SettingsScreen { align: center middle; }
    #settings {
        width: 60; height: auto; padding: 1 2;
        border: thick $accent; background: $surface;
    }
    #title { text-style: bold; margin-bottom: 1; }
    #settings Select { margin-bottom: 1; }
    #buttons { height: auto; align-horizontal: right; }
    #buttons Button { margin-left: 2; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        current = self.app.repo.get_timezone()
        zones = sorted(available_timezones())
        if current not in zones:  # keep an unusual stored value selectable
            zones.insert(0, current)
        with Vertical(id="settings"):
            yield Label("Settings", id="title")
            yield Label("Timezone")
            yield Select(
                [(zone, zone) for zone in zones],
                value=current,
                allow_blank=False,
                id="tz",
            )
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", variant="primary", id="save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._submit()
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def _submit(self) -> None:
        chosen = self.query_one("#tz", Select).value
        if chosen == self.app.repo.get_timezone():
            self.dismiss(False)
            return
        try:
            self.app.repo.set_timezone(chosen)
        except ValueError:
            self.notify("Invalid timezone.", severity="error")
            return
        self.notify(f"Timezone set to {chosen}.")
        self.dismiss(True)
