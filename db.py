import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("SPRINKLER_DB", "/data/sprinkler.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    relay_host TEXT NOT NULL,
    relay_channel INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    photo_filename TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    days_of_week TEXT NOT NULL,       -- comma separated: mon,tue,wed,thu,fri,sat,sun
    start_time TEXT NOT NULL,         -- "HH:MM" 24-hour
    duration_minutes INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id INTEGER,
    zone_name TEXT,
    schedule_id INTEGER,
    event_time TEXT NOT NULL,
    action TEXT NOT NULL,             -- started, stopped, skipped_rain, manual_start, manual_stop, error
    detail TEXT
);
"""

DEFAULT_SETTINGS = {
    "latitude": "41.5037",     # Cheshire, CT default — editable in UI
    "longitude": "-72.9048",
    "rain_check_enabled": "1",
    "rain_skip_threshold": "50",   # skip watering if precipitation probability >= this %
    "timezone": "America/New_York",
}


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # migration for DBs created before photo support existed
        try:
            conn.execute("ALTER TABLE zones ADD COLUMN photo_filename TEXT")
        except sqlite3.OperationalError:
            pass
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def rows_to_dicts(rows):
    return [dict(r) for r in rows]
