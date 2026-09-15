-- Chainlinkd SQLite schema.
--
-- Shipped inside the package and applied on every connect(): each statement
-- is guarded with IF NOT EXISTS so running it against an existing database is
-- a no-op. All access to these tables is confined to HabitRepository.

-- A tracked habit. `periodicity` stores the cadence label ("daily"/"weekly")
-- that the domain layer maps back to a Periodicity object.
CREATE TABLE IF NOT EXISTS habits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    periodicity TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

-- One completion recorded against a habit. `period_start` is derived by the
-- habit's Periodicity at write time; the UNIQUE constraint on
-- (habit_id, period_start) enforces "at most one completion per period" and
-- makes toggling an idempotent upsert. ON DELETE CASCADE removes a habit's
-- logs when the habit is deleted.
CREATE TABLE IF NOT EXISTS habit_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id     INTEGER NOT NULL,
    completed_at TEXT    NOT NULL,
    period_start TEXT    NOT NULL,
    FOREIGN KEY (habit_id) REFERENCES habits (id) ON DELETE CASCADE,
    UNIQUE (habit_id, period_start)
);

CREATE INDEX IF NOT EXISTS idx_habit_logs_habit_id
    ON habit_logs (habit_id);

-- Key/value table for the schema version and the one-shot seeded flag, so
-- re-seeding on later runs is idempotent.
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO meta (key, value) VALUES ('seeded', '0');
