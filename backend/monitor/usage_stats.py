"""
Mimics Android's android.app.usage.UsageStatsManager.
Tracks foreground time, background time, and last-used timestamps per package.
"""

from __future__ import annotations

from backend.sim.process import Process


class UsageStatsManager:
    def query_usage_stats(self, processes: list[Process]) -> list[dict]:
        return [
            {
                "package_name": p.package_name,
                "display_name": p.display_name,
                "total_time_in_foreground_s": round(p.fg_time_s, 1),
                "total_time_in_background_s": round(p.bg_time_s, 1),
                "last_time_used_s": round(p.last_used_sim_s, 1),
            }
            for p in processes
        ]

