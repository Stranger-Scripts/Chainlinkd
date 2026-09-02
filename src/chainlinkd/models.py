"""Pydantic data models for Chainlinkd."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Frequency(str, Enum):
    """How often a habit is expected to be performed."""

    DAILY = "daily"
    WEEKLY = "weekly"


class HabitEntry(BaseModel):
    """A single record that a habit was completed on a given day."""

    on: date
    note: str = ""

    @field_validator("on")
    @classmethod
    def not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("cannot log a habit entry in the future")
        return value


class Habit(BaseModel):
    """A habit the user is tracking, plus its completion history."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(min_length=1, max_length=100)
    frequency: Frequency = Frequency.DAILY
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    entries: list[HabitEntry] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("habit name cannot be blank")
        return stripped

    # --- behaviour -------------------------------------------------------

    def is_done_on(self, day: date) -> bool:
        """Return True if this habit has an entry for ``day``."""
        return any(entry.on == day for entry in self.entries)

    def mark_done(self, day: date | None = None, note: str = "") -> bool:
        """Log completion for ``day`` (defaults to today).

        Returns True if a new entry was added, False if it already existed.
        """
        day = day or date.today()
        if self.is_done_on(day):
            return False
        self.entries.append(HabitEntry(on=day, note=note))
        self.entries.sort(key=lambda e: e.on)
        return True

    def unmark(self, day: date | None = None) -> bool:
        """Remove the entry for ``day``. Returns True if one was removed."""
        day = day or date.today()
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.on != day]
        return len(self.entries) < before

    def current_streak(self, today: date | None = None) -> int:
        """Count consecutive completed days ending today (daily habits)."""
        today = today or date.today()
        done = {e.on for e in self.entries}
        streak = 0
        cursor = today
        while cursor in done:
            streak += 1
            cursor = date.fromordinal(cursor.toordinal() - 1)
        return streak


class HabitDB(BaseModel):
    """Top-level container persisted to disk."""

    habits: list[Habit] = Field(default_factory=list)
