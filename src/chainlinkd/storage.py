"""JSON-backed persistence for the habit database."""

from __future__ import annotations

import os
from pathlib import Path

from .models import HabitDB


def default_data_path() -> Path:
    """Location of the data file, honouring XDG on Linux/macOS."""
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "chainlinkd" / "habits.json"


class Store:
    """Load and save a :class:`HabitDB` as JSON."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_data_path()

    def load(self) -> HabitDB:
        if not self.path.exists():
            return HabitDB()
        return HabitDB.model_validate_json(self.path.read_text("utf-8"))

    def save(self, db: HabitDB) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(db.model_dump_json(indent=2), "utf-8")
