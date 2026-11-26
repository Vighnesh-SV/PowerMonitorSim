"""
SQLite database schema and connection helper for historical power & activity logging.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "power_monitor.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seed INTEGER NOT NULL,
            started_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS battery_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            sim_time_s REAL NOT NULL,
            level_pct REAL NOT NULL,
            current_ma REAL NOT NULL,
            voltage_mv INTEGER NOT NULL,
            temperature_c REAL NOT NULL,
            charging_state TEXT NOT NULL,
            screen_on INTEGER NOT NULL,
            doze_active INTEGER NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS app_energy_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            sim_time_s REAL NOT NULL,
            package_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            total_mah REAL NOT NULL,
            fg_mah REAL NOT NULL,
            bg_mah REAL NOT NULL,
            cpu_mah REAL NOT NULL,
            screen_mah REAL NOT NULL,
            network_mah REAL NOT NULL,
            gps_mah REAL NOT NULL,
            wakelock_mah REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS process_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            sim_time_s REAL NOT NULL,
            package_name TEXT NOT NULL,
            old_state TEXT NOT NULL,
            new_state TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        """
    )
    conn.commit()
    conn.close()

