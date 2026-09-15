"""SQLite persistence for Chainlinkd (the Repository pattern, Fowler 2003).

All SQL lives here: the rest of the code sees :class:`Habit` objects and never
a cursor, which also lets the test suite run against an in-memory database.
The domain layer never imports this module — dependency points downward only.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib import resources
from pathlib import Path
from zoneinfo import ZoneInfo

from platformdirs import user_data_path

from .models import Clock, Habit, HabitLog, Periodicity, periodicity_from_label
from .seed import seed_habits

APP_NAME = "chainlinkd"
DB_FILENAME = "chainlinkd.db"


def default_db_path() -> Path:
    """Location of the SQLite file in the platform's user-data directory."""
    return user_data_path(APP_NAME, appauthor=False) / DB_FILENAME


def _is_valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def system_timezone_name() -> str:
    """Best-effort IANA name of the system zone, falling back to ``"UTC"``.

    Used only as the *suggested* default on first run; the user can override
    it, which is the whole point of storing the zone rather than trusting the
    system blindly.
    """
    env = os.environ.get("TZ")
    if env and _is_valid_zone(env):
        return env
    try:
        link = os.readlink("/etc/localtime")
    except OSError:
        link = ""
    marker = "zoneinfo/"
    if marker in link:
        candidate = link.split(marker, 1)[1]
        if _is_valid_zone(candidate):
            return candidate
    return "UTC"


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


class ClockWentBackwardError(RuntimeError):
    """Raised when logging a completion for *now* while the system clock is
    behind the high-water mark seen on a previous run — i.e. the clock has
    been turned back. Legitimate backfilling of a past period is unaffected.
    """


@dataclass(frozen=True)
class ClockCheck:
    """Result of comparing the current clock against its high-water mark."""

    ok: bool
    now: datetime
    last_seen: datetime | None

    @property
    def backward_by(self):
        """How far the clock is behind the mark, or None if it isn't."""
        if self.ok or self.last_seen is None:
            return None
        return self.last_seen - self.now


class HabitRepository:
    """Load and store :class:`Habit` objects, mapping them to/from SQL rows."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._ensure_timezone()

    # --- meta / timezone -------------------------------------------------

    def _get_meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else default

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def _ensure_timezone(self) -> None:
        if not self._get_meta("timezone"):
            self._set_meta("timezone", system_timezone_name())

    def get_timezone(self) -> str:
        """Return the configured IANA zone name."""
        return self._get_meta("timezone") or "UTC"

    def set_timezone(self, name: str) -> None:
        """Change the configured zone. Raises if ``name`` is not a valid key."""
        if not _is_valid_zone(name):
            raise ValueError(f"unknown timezone: {name!r}")
        self._set_meta("timezone", name)

    def clock(self) -> Clock:
        """A :class:`Clock` bound to the configured zone."""
        return Clock(ZoneInfo(self.get_timezone()))

    def today(self) -> date:
        return self.clock().today()

    # --- backward-clock guard --------------------------------------------

    def last_seen(self) -> datetime | None:
        raw = self._get_meta("last_seen_at")
        return datetime.fromisoformat(raw) if raw else None

    def clock_check(self, now: datetime | None = None) -> ClockCheck:
        """Compare ``now`` (default: wall clock) against the high-water mark."""
        now = now or datetime.now(timezone.utc)
        seen = self.last_seen()
        return ClockCheck(ok=seen is None or now >= seen, now=now, last_seen=seen)

    def mark_seen(self, now: datetime | None = None) -> None:
        """Ratchet the high-water mark forward (never backward)."""
        now = now or datetime.now(timezone.utc)
        seen = self.last_seen()
        high = now if seen is None else max(seen, now)
        self._set_meta("last_seen_at", high.isoformat())

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
        habit.clock = self.clock()
        return habit

    def delete(self, habit_id: int) -> None:
        """Delete a habit; its logs go too via ON DELETE CASCADE."""
        self.conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
        self.conn.commit()

    def update(
        self,
        habit_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        periodicity: Periodicity | None = None,
    ) -> Habit:
        """Edit a habit's fields. Only the arguments given are changed.

        Changing the cadence recomputes ``period_start`` for every existing
        log under the new periodicity (using the completion's local date). If
        the coarser cadence collapses several completions into one period, the
        earliest is kept and the rest dropped, so the
        ``UNIQUE(habit_id, period_start)`` constraint still holds. The habit
        row and its logs are rewritten in a single transaction.
        """
        habit = self.get(habit_id)
        if habit is None:
            raise KeyError(habit_id)

        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise ValueError("habit name cannot be blank")
            habit.name = cleaned
        if description is not None:
            habit.description = description

        cadence_changed = (
            periodicity is not None
            and periodicity.label != habit.periodicity.label
        )
        if periodicity is not None:
            habit.periodicity = periodicity

        with self.conn:
            self.conn.execute(
                "UPDATE habits SET name = ?, description = ?, periodicity = ? "
                "WHERE id = ?",
                (habit.name, habit.description, habit.periodicity.label, habit_id),
            )
            if cadence_changed:
                self._rewrite_logs_for_new_cadence(habit)

        return self.get(habit_id)

    def _rewrite_logs_for_new_cadence(self, habit: Habit) -> None:
        """Recompute + de-duplicate ``period_start`` for a habit's logs."""
        kept: dict[date, HabitLog] = {}
        for log in habit.logs:
            period = habit.periodicity.period_start(
                habit.clock.local_date(log.completed_at)
            )
            if period not in kept or log.completed_at < kept[period].completed_at:
                kept[period] = log
        self.conn.execute(
            "DELETE FROM habit_logs WHERE habit_id = ?", (habit.id,)
        )
        self.conn.executemany(
            "INSERT INTO habit_logs (habit_id, completed_at, period_start) "
            "VALUES (?, ?, ?)",
            [
                (habit.id, log.completed_at.isoformat(), period.isoformat())
                for period, log in kept.items()
            ],
        )

    def log(
        self,
        habit_id: int,
        at: datetime | None = None,
        allow_backward: bool = False,
    ) -> None:
        """Record a completion for ``habit_id`` at ``at`` (default: now).

        Idempotent per period thanks to the UNIQUE constraint. When ``at`` is
        omitted (logging *now*), a system clock that has been turned back
        raises :class:`ClockWentBackwardError` unless ``allow_backward`` is
        set. Backfilling an explicit past ``at`` is always allowed.
        """
        habit = self.get(habit_id)
        if habit is None:
            raise KeyError(habit_id)
        now = habit.clock.now()
        if at is None and not allow_backward:
            check = self.clock_check(now)
            if not check.ok:
                raise ClockWentBackwardError(
                    f"system clock is behind by {check.backward_by}; "
                    "refusing to log 'now' (pass allow_backward=True to override)"
                )
        log = habit.complete(at)
        self._insert_log(log)
        self.mark_seen(now)
        self.conn.commit()

    def unlog(self, habit_id: int, period_start: date) -> None:
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

    def _habit_from_row(self, row: sqlite3.Row) -> Habit:
        return Habit(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            periodicity=periodicity_from_label(row["periodicity"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            clock=self.clock(),
        )

    # --- seeding ---------------------------------------------------------

    def seed_if_empty(self) -> bool:
        """Insert the predefined habits on first run only.

        Guarded by the ``seeded`` flag in ``meta`` so re-running is a no-op.
        Returns True if seeding happened, False if it was already done.
        """
        if self._get_meta("seeded") == "1":
            return False

        for habit in seed_habits():
            self.add(habit)
        self._set_meta("seeded", "1")
        return True
