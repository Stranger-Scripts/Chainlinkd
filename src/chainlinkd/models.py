"""Domain model for Chainlinkd.

This layer holds the habit objects, the periodicity logic and nothing else:
it imports neither Textual nor ``sqlite3`` so it can be tested in isolation.
The design follows the Strategy pattern (Gamma et al., 1994) — cadence-specific
behaviour lives in a :class:`Periodicity` hierarchy that :class:`Habit`
composes, rather than in ``Habit`` subclasses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Clock:
    """Maps instants to the user's local calendar day.

    Completions are stored in UTC, but "which day did this count for" is a
    question about the *user's* calendar, so period boundaries are derived
    from a configured timezone rather than from UTC or the raw system date.
    Injected into habits by the repository; defaults to UTC so the domain and
    its tests need no configuration.
    """

    tz: ZoneInfo = UTC

    def now(self) -> datetime:
        """The current instant as an aware UTC datetime."""
        return datetime.now(timezone.utc)

    def today(self) -> date:
        """The current date in the configured zone."""
        return self.local_date(self.now())

    def local_date(self, moment: datetime) -> date:
        """The calendar date ``moment`` falls on in the configured zone.

        Naive datetimes are assumed to be UTC (that is how they are stored).
        """
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(self.tz).date()


# --- periodicity ---------------------------------------------------------


class Periodicity(ABC):
    """A cadence: it knows where the period containing a date begins and
    where the next one starts. Consumers call this polymorphic interface and
    never branch on the concrete cadence.
    """

    #: stable identifier persisted alongside each habit
    label: str

    @abstractmethod
    def period_start(self, day: date) -> date:
        """Return the first day of the period that contains ``day``."""

    @abstractmethod
    def next_period(self, day: date) -> date:
        """Return the ``period_start`` of the period following ``day``'s."""

    def periods_between(self, earlier: date, later: date) -> int:
        """Count period boundaries crossed from ``earlier`` to ``later``.

        Zero means both dates fall in the same period; one means ``later``
        sits in the period immediately following ``earlier``'s, and so on.
        Implemented once here in terms of the two abstract methods, so every
        cadence — daily, weekly and a later monthly one — reuses it.
        """
        start = self.period_start(earlier)
        goal = self.period_start(later)
        count = 0
        while start < goal:
            start = self.next_period(start)
            count += 1
        return count


class DailyPeriodicity(Periodicity):
    """A habit expected once per calendar day."""

    label = "daily"

    def period_start(self, day: date) -> date:
        return day

    def next_period(self, day: date) -> date:
        return day + timedelta(days=1)


class WeeklyPeriodicity(Periodicity):
    """A habit expected once per ISO week (weeks begin on Monday)."""

    label = "weekly"

    def period_start(self, day: date) -> date:
        return day - timedelta(days=day.weekday())

    def next_period(self, day: date) -> date:
        return self.period_start(day) + timedelta(days=7)


#: single shared instances — periodicities are stateless flyweights
DAILY = DailyPeriodicity()
WEEKLY = WeeklyPeriodicity()

_BY_LABEL: dict[str, Periodicity] = {DAILY.label: DAILY, WEEKLY.label: WEEKLY}


def periodicity_from_label(label: str) -> Periodicity:
    """Reconstruct a :class:`Periodicity` from its persisted ``label``."""
    try:
        return _BY_LABEL[label]
    except KeyError:
        raise ValueError(f"unknown periodicity label: {label!r}") from None


# --- records -------------------------------------------------------------


@dataclass
class HabitLog:
    """A completion recorded against a habit.

    Stores the full ``completed_at`` timestamp alongside ``period_start`` —
    the start of the period the completion falls in, computed by the habit's
    :class:`Periodicity` at write time. That derived value lets the database
    enforce "at most one completion per period" with a unique constraint.
    """

    completed_at: datetime
    period_start: date
    habit_id: int | None = None
    id: int | None = None

    def as_row(self) -> tuple[int | None, str, str]:
        """Return the persistable ``(habit_id, completed_at, period_start)``."""
        return (
            self.habit_id,
            self.completed_at.isoformat(),
            self.period_start.isoformat(),
        )


@dataclass
class Habit:
    """A tracked habit: its identity, its cadence and its completion history.

    ``id`` is ``None`` until the repository has persisted the habit and
    assigned the SQLite rowid.
    """

    name: str
    description: str = ""
    periodicity: Periodicity = DAILY
    created_at: datetime = field(default_factory=_utcnow)
    logs: list[HabitLog] = field(default_factory=list)
    clock: Clock = field(default_factory=Clock)
    id: int | None = None

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("habit name cannot be blank")

    def complete(self, at: datetime | None = None) -> HabitLog:
        """Build a :class:`HabitLog` for completion at ``at`` (default: now).

        ``period_start`` is derived from the *local* day ``at`` falls on (per
        this habit's clock) and this habit's periodicity. The returned log is
        appended to ``logs`` but not persisted — that is the repository's job.
        """
        at = at or self.clock.now()
        log = HabitLog(
            completed_at=at,
            period_start=self.periodicity.period_start(self.clock.local_date(at)),
            habit_id=self.id,
        )
        self.logs.append(log)
        return log

    def is_due(self, on: date | None = None) -> bool:
        """Return True if the period containing ``on`` has no completion yet.

        ``on`` defaults to today in this habit's configured zone.
        """
        on = on or self.clock.today()
        target = self.periodicity.period_start(on)
        return target not in self.completed_periods()

    def completed_periods(self) -> list[date]:
        """Return the sorted, de-duplicated period starts that are done."""
        return sorted({log.period_start for log in self.logs})
