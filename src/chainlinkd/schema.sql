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
-- No separate index on habit_id is needed: the UNIQUE constraint above
-- creates a composite index whose leftmost column already serves lookups
-- (and ORDER BY period_start) for a single habit.

-- Key/value table for the schema version and the one-shot seeded flag, so
-- re-seeding on later runs is idempotent.
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO meta (key, value) VALUES ('seeded', '0');
-- IANA timezone the app derives period boundaries from. Empty until set on
-- first run (the presentation layer prompts, defaulting to the system zone).
INSERT OR IGNORE INTO meta (key, value) VALUES ('timezone', '');
-- High-water mark of the wall clock, used to detect the system clock being
-- turned backwards between runs. Empty until the first write/startup.
INSERT OR IGNORE INTO meta (key, value) VALUES ('last_seen_at', '');
