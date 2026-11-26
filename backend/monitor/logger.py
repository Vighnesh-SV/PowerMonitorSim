"""
Periodic & event-based logger into SQLite.
- Periodic sampling: battery_samples & app_energy_samples every `sample_interval_ticks`.
- Event-based logging: process_events whenever a process changes state.
"""

from __future__ import annotations

from backend.db.database import get_connection, init_db


class HistoryLogger:
    def __init__(self, sample_interval_ticks: int = 5):
        init_db()
        self.sample_interval_ticks = sample_interval_ticks
        self.session_id: int = self._create_session(seed=42)

    def _create_session(self, seed: int) -> int:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO sessions (seed) VALUES (?)", (seed,))
        sid = cur.lastrowid
        conn.commit()
        conn.close()
        return int(sid)

    def start_new_session(self, seed: int) -> None:
        self.session_id = self._create_session(seed)

    def log_tick(self, tick: int, snapshot: dict, transitions: list[dict]) -> None:
        conn = get_connection()
        cur = conn.cursor()

        # Event-based logging: state transitions
        for tr in transitions:
            cur.execute(
                """
                INSERT INTO process_events (session_id, sim_time_s, package_name, old_state, new_state)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.session_id, tr["sim_time_s"], tr["package_name"], tr["old_state"], tr["new_state"]),
            )

        # Periodic sampling
        if tick % self.sample_interval_ticks == 0:
            b = snapshot["battery"]
            d = snapshot["device"]
            cur.execute(
                """
                INSERT INTO battery_samples
                (session_id, sim_time_s, level_pct, current_ma, voltage_mv, temperature_c, charging_state, screen_on, doze_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.session_id,
                    snapshot["sim_time_seconds"],
                    b["level_pct"],
                    b["current_ma"],
                    b["voltage_mv"],
                    b["temperature_c"],
                    b["charging_state"],
                    1 if d["screen_on"] else 0,
                    1 if d["doze_active"] else 0,
                ),
            )
            for app in snapshot.get("attribution", []):
                cur.execute(
                    """
                    INSERT INTO app_energy_samples
                    (session_id, sim_time_s, package_name, display_name, total_mah, fg_mah, bg_mah, cpu_mah, screen_mah, network_mah, gps_mah, wakelock_mah)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.session_id,
                        snapshot["sim_time_seconds"],
                        app["package_name"],
                        app["display_name"],
                        app["total_mah"],
                        app["fg_mah"],
                        app["bg_mah"],
                        app["cpu_mah"],
                        app["screen_mah"],
                        app["network_mah"],
                        app["gps_mah"],
                        app["wakelock_mah"],
                    ),
                )

        conn.commit()
        conn.close()

