import json
import os
import sqlite3
from contextlib import contextmanager

from .config import db_path


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
 username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, salt BLOB NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','guardian')), display_name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS assignments (
 username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
 patient_id INTEGER NOT NULL CHECK(patient_id > 0), UNIQUE(username, patient_id)
);
CREATE TABLE IF NOT EXISTS ticks (
 session_id TEXT NOT NULL, tick INTEGER NOT NULL, tick_time TEXT NOT NULL,
 patient_id INTEGER NOT NULL, status TEXT NOT NULL, confidence REAL NOT NULL,
 heart_rate REAL, systolic_bp REAL, diastolic_bp REAL, body_temp REAL, spo2 REAL,
 activity TEXT NOT NULL, attention TEXT NOT NULL,
 PRIMARY KEY(session_id,tick,patient_id)
);
CREATE INDEX IF NOT EXISTS ticks_patient ON ticks(patient_id,session_id,tick);
CREATE INDEX IF NOT EXISTS ticks_session ON ticks(session_id,tick);
CREATE TABLE IF NOT EXISTS predictions (
 session_id TEXT NOT NULL, tick INTEGER NOT NULL, computed_at_time TEXT NOT NULL,
 patient_id INTEGER NOT NULL, risk_label TEXT NOT NULL, risk_score REAL NOT NULL,
 top_factors TEXT NOT NULL, PRIMARY KEY(session_id,tick,patient_id)
);
CREATE INDEX IF NOT EXISTS predictions_patient ON predictions(patient_id,session_id,tick);
"""


def initialize():
    path = db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def current_session(conn):
    row = conn.execute("SELECT session_id FROM ticks ORDER BY rowid DESC LIMIT 1").fetchone()
    return row[0] if row else None


def json_dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
