"""SQLite persistence for Chainlinkd (the Repository pattern, Fowler 2003).

All SQL lives here: the rest of the code sees :class:`Habit` objects and never
a cursor, which also lets the test suite run against an in-memory database.
The domain layer never imports this module — dependency points downward only.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from importlib import resources
from pathlib import Path

from platformdirs import user_data_path

from .models import Habit, HabitLog, periodicity_from_label
from .seed import seed_habits

APP_NAME = "chainlinkd"
DB_FILENAME = "chainlinkd.db"


def default_db_path() -> Path:
    """Location of the SQLite file in the platform's user-data directory."""
    return user_data_path(APP_NAME, appauthor=False) / DB_FILENAME


def _load_schema() -> str:
    """Read the packaged ``schema.sql``."""
    return resources.files(__package__).joinpath("schema.sql").read_text("utf-8")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with the schema applied and pragmas set.

    ``foreign_keys`` is enabled so ``ON DELETE CASCADE`` fires, and WAL
    journalling is set for durability under the single-writer workload.
    Pass ``":memory:"`` for an ephemeral database (used by the tests).
    """
    if path is None:
        path = default_db_path()
    if path != ":memory:":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = str(path)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(_load_schema())
    conn.commit()
    return conn


class HabitRepository:
    """Load and store :class:`Habit` objects, mapping them to/from SQL rows."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- writes ----------------------------------------------------------

    def add(self, habit: Habit) -> Habit:
        """Insert a habit (and any logs it carries) and assign its id."""
        cur = self.conn.execute(
            "INSERT INTO habits (name, description, periodicity, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                habit.name,
                habit.description,
                habit.periodicity.label,
                habit.created_at.isoformat(),
            ),
        )
        habit.id = int(cur.lastrowid)
        for log in habit.logs:
            log.habit_id = habit.id
            self._insert_log(log)
        self.conn.commit()
        return habit

    def delete(self, habit_id: int) -> None:
        """Delete a habit; its logs go too via ON DELETE CASCADE."""
        self.conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
        self.conn.commit()

    def log(self, habit_id: int, at: datetime | None = None) -> None:
        """Record a completion for ``habit_id`` at ``at`` (default: now).

        Idempotent: a second completion in the same period is silently
        ignored thanks to the UNIQUE(habit_id, period_start) constraint.
        """
        habit = self.get(habit_id)
        if habit is None:
            raise KeyError(habit_id)
        log = habit.complete(at)
        self._insert_log(log)
        self.conn.commit()

    def unlog(self, habit_id: int, period_start) -> None:
        """Remove the completion for ``habit_id`` in a given period (toggle off)."""
        self.conn.execute(
            "DELETE FROM habit_logs WHERE habit_id = ? AND period_start = ?",
            (habit_id, period_start.isoformat()),
        )
        self.conn.commit()

    def _insert_log(self, log: HabitLog) -> None:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO habit_logs "
            "(habit_id, completed_at, period_start) VALUES (?, ?, ?)",
            log.as_row(),
        )
        if cur.lastrowid:
            log.id = int(cur.lastrowid)

    # --- reads -----------------------------------------------------------

    def get(self, habit_id: int) -> Habit | None:
        """Return a fully-populated habit by id, or None if absent."""
        row = self.conn.execute(
            "SELECT * FROM habits WHERE id = ?", (habit_id,)
        ).fetchone()
        if row is None:
            return None
        habit = self._habit_from_row(row)
        self._attach_logs(habit)
        return habit

    def list_all(self) -> list[Habit]:
        """Return every habit with its logs, ordered by creation."""
        rows = self.conn.execute(
            "SELECT * FROM habits ORDER BY created_at, id"
        ).fetchall()
        habits = [self._habit_from_row(row) for row in rows]
        for habit in habits:
            self._attach_logs(habit)
        return habits

    def _attach_logs(self, habit: Habit) -> None:
        rows = self.conn.execute(
            "SELECT * FROM habit_logs WHERE habit_id = ? ORDER BY period_start",
            (habit.id,),
        ).fetchall()
        habit.logs = [
            HabitLog(
                id=row["id"],
                habit_id=row["habit_id"],
                completed_at=datetime.fromisoformat(row["completed_at"]),
                period_start=datetime.fromisoformat(row["period_start"]).date(),
            )
            for row in rows
        ]

    @staticmethod
    def _habit_from_row(row: sqlite3.Row) -> Habit:
        return Habit(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            periodicity=periodicity_from_label(row["periodicity"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # --- seeding ---------------------------------------------------------

    def seed_if_empty(self) -> bool:
        """Insert the predefined habits on first run only.

        Guarded by the ``seeded`` flag in ``meta`` so re-running is a no-op.
        Returns True if seeding happened, False if it was already done.
        """
        flag = self.conn.execute(
            "SELECT value FROM meta WHERE key = 'seeded'"
        ).fetchone()
        if flag is not None and flag["value"] == "1":
            return False

        for habit in seed_habits():
            self.add(habit)
        self.conn.execute("UPDATE meta SET value = '1' WHERE key = 'seeded'")
        self.conn.commit()
        return True
