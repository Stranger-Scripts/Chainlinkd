# Chainlinkd

A terminal habit tracker built with [Textual](https://textual.textualize.io/).
Every completion is a *link*, and the unbroken sequence a habit accumulates is
its *chain*.

*Don't break the chain.*

## Install

```bash
uv sync            # or: pip install -e ".[dev]"
```

Requires Python 3.13+. 

## Run

```bash
uv run chainlinkd  # or: python -m chainlinkd
```

On first run the database is created and seeded with example habits.

### Keys

| Key     | Action              |
| ------- | ------------------- |
| `space` | Toggle today's mark |
| `q`     | Quit                |

## Architecture

Three layers with a strictly one-directional dependency
(presentation → domain → persistence):

```
src/chainlinkd/
  app.py         # presentation — Textual UI
  models.py      # domain — Habit, HabitLog, Periodicity (Daily/Weekly)
  analytics.py   # domain — pure streak/rate functions
  repository.py  # persistence — HabitRepository + SQLite connection
  schema.sql     # persistence — table definitions (shipped in the package)
  seed.py        # predefined habits + four weeks of example data
  __main__.py    # `chainlinkd` entry point
tests/
  test_models.py       # domain + analytics
  test_repository.py    # round-trip, cascade, unique constraint, seeding
```

The domain layer imports neither Textual nor `sqlite3`, so it can be tested in
isolation.

## Data

All state lives in one SQLite file, `chainlinkd.db`, in the platform user-data directory (resolved by [platformdirs](https://pypi.org/project/platformdirs/) — e.g. `~/.local/share/chainlinkd/chainlinkd.db` on Linux). The connection enables `foreign_keys` and WAL journalling; all SQL is confined to `HabitRepository`.

Two tables hold the data — `habits` and `habit_logs`, joined by a foreign key with `ON DELETE CASCADE` — plus a `meta` table for the schema version, the one-shot seeded flag, the configured timezone and the clock high-water mark. A completion is stored as a full timestamp alongside a derived `period_start`; a `UNIQUE(habit_id, period_start)` constraint enforces "at most one completion per period", so toggling is an idempotent upsert. Streaks are derived from the logs on read, never cached.

Editing a habit's cadence (`HabitRepository.update`) recomputes `period_start` for every existing log under the new periodicity and drops any collisions the coarser cadence creates, keeping the unique constraint intact. 

### Time and integrity

Which calendar day a completion counts for is a question about *your* day, not UTC, so period boundaries are derived from a configured IANA timezone stored in `meta` (defaulting to the system zone on first run, changeable via `set_timezone`). Completions are still stored in UTC.

A lightweight guard records the highest wall-clock value seen (`last_seen_at`) and refuses to log a completion for *now* if the system clock has been turned back behind that mark, meant as a cheap check against accidental clock skew and casual backdating. It is deliberately not tamper-proof, it never blocks legitimate backfilling of a *past* period, and it requires no network: the concept keeps Chainlinkd offline-first. 

## Test

```bash
uv run pytest      # or: pytest
```
