# Chainlinkd

A terminal habit tracker built with [Textual](https://textual.textualize.io/).
Every completion is a *link*, and the unbroken sequence a habit accumulates is
its *chain*.

*Don't break the chain.*

## Install

```bash
uv sync            # or: pip install -e ".[dev]"
```

Requires Python 3.12+.

Or grab a standalone build for your platform from the
[latest release](https://github.com/Stranger-Scripts/Chainlinkd/releases/latest) —
no Python needed. Verify the download against its `.sha256` sidecar, unpack, and
run the `chainlinkd` binary inside.

## Run

```bash
uv run chainlinkd  # or: python -m chainlinkd
```

On first run the database is created and seeded with example habits.
`chainlinkd --version` prints the version and exits.

### Keys

| Key     | Action                                          |
| ------- | ----------------------------------------------- |
| `↑` `↓` | Move between habits                             |
| `←` `→` | Move the viewing day back / forward             |
| `t`     | Jump back to today                             |
| `space` | Toggle the selected habit for the viewing day   |
| `n`     | New habit (Manage)                             |
| `e`     | Edit selected habit (Manage)                   |
| `d`     | Delete selected habit (Manage)                 |
| `a`     | Analysis (per-habit metrics)                   |
| `s`     | Settings (timezone)                            |
| `q`     | Quit                                           |

The chain column shows the recent periods ending on the **viewing day** (shown
in the header). How many, and how they're drawn, depends on the habit's
cadence: daily and weekly render as bare links (`○○●●●●●`), while monthly and
yearly label each tick so the period is legible, e.g.
`Apr● May● Jun○ Jul● Aug● Sep●`. `←` moves the viewing day into the past so you
can fill in a period you missed — `space` there backfills it; `→` moves forward
but never past today. `t` returns to today.

Habits support four cadences — **daily**, **weekly**, **monthly** and
**yearly** — chosen when you create or edit a habit. Streaks, rates and chains
are all derived generically from the cadence, so the same logic serves each.

`n` / `e` / `d` open the **Manage** screen, which lists every habit and hosts
create / edit / delete via a small form and a delete confirmation. Editing a
habit's cadence recomputes its history (see below). `a` opens **Analysis** -- a
table of current streak, longest streak, completion rate and total completions
per habit, plus the longest streak across all habits. `s` opens **Settings** to
change the timezone. `esc` returns to the dashboard.

## Architecture

Three layers with a strictly one-directional dependency
(presentation → domain → persistence):

```
src/chainlinkd/
  app.py         # presentation — Textual app + dashboard (day-nav, backfill)
  manage.py      # presentation — Manage screen + create/edit/delete modals
  analysis.py    # presentation — Analysis screen (per-habit metrics)
  settings.py    # presentation — Settings screen (timezone)
  models.py      # domain — Habit, HabitLog, Periodicity (Daily/Weekly/Monthly/Yearly), Clock
  analytics.py   # domain — pure streak/rate functions
  repository.py  # persistence — HabitRepository + SQLite connection
  schema.sql     # persistence — table definitions (shipped in the package)
  seed.py        # predefined habits + four weeks of example data
  __main__.py    # `chainlinkd` entry point
tests/
  test_models.py       # domain + analytics
  test_repository.py    # round-trip, cascade, unique constraint, seeding
  test_app.py           # Manage flow driven through the Textual pilot
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

## Build a standalone executable

One PyInstaller spec, [`build/chainlinkd.spec`](build/chainlinkd.spec), drives
both platforms. The bundle includes Python, Textual and the packaged
`schema.sql`, so it runs on a machine with no Python installed. The thin entry
point PyInstaller analyses lives at [`packaging/launcher.py`](packaging/launcher.py).

PyInstaller does **not** cross-compile: each platform must be built on itself.

```bash
uv sync --extra build   # ensure the venv has the runtime + build deps
./build/build-linux.sh
```

```powershell
uv sync --extra build
powershell -ExecutionPolicy Bypass -File build\build-windows.ps1
```

Either produces a onedir bundle at `dist/chainlinkd/`, launched via
`./dist/chainlinkd/chainlinkd` (or `chainlinkd.exe` on Windows).

To build without the wrapper scripts:

```bash
uv run pyinstaller build/chainlinkd.spec --clean --noconfirm
```

## Releasing

[`.github/workflows/release.yml`](.github/workflows/release.yml) builds both
platforms on their own runners, smoke-tests each binary with `--version`,
checks `schema.sql` survived bundling, and attaches the two archives plus
SHA-256 sidecars to a GitHub Release.

Push a version tag to cut a release:

```bash
git tag -a v1.0.0 -m "Chainlinkd 1.0.0"
git push origin v1.0.0
```

Running the workflow manually (`workflow_dispatch`) builds and verifies the
same artifacts without publishing, which is how to rehearse a release before
tagging.

The version has a single source of truth — `__version__` in
[`src/chainlinkd/__init__.py`](src/chainlinkd/__init__.py), which hatchling
reads for the package metadata. Bump it to match the tag.
