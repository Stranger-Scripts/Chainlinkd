# Chainlinkd

A terminal habit tracker built with [Textual](https://textual.textualize.io/),
with data models validated by [Pydantic](https://docs.pydantic.dev/).

*Don't break the chain.*

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.13+.

## Run

```bash
source venv./bin/activate # on linux or mac 
# or 
.venv\Scripts\Activate.ps1 # on windows

chainlinkd        # or: python -m chainlinkd
```

### Keys

| Key     | Action              |
| ------- | ------------------- |
| `a`     | Focus the add box   |
| `space` | Toggle today's mark |
| `d`     | Delete selected     |
| `q`     | Quit                |

## Layout

```
src/chainlinkd/
  models.py     # Pydantic models: Habit, HabitEntry, HabitDB
  storage.py    # JSON persistence (XDG data dir)
  app.py        # Textual application
  __main__.py   # `chainlinkd` entry point
tests/
  test_models.py
```

Habits are stored as JSON at `$XDG_DATA_HOME/chainlinkd/habits.json`
(falls back to `~/.local/share/chainlinkd/habits.json`).

## Test

```bash
pytest
```
