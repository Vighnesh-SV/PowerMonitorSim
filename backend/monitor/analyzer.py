"""
Power & Activity Analyzer:
1. Daily summary reports (total drain, screen-on time, top 5 drainers, hourly drain).
2. Anomaly / Rogue App detection:
   - Detects apps with abnormal background drain, long-held wakelocks while screen is off,
     excessive wakeups, or drain disproportionate to foreground usage.
"""

from __future__ import annotations

import csv
import io

from backend.sim.process import Process, ProcessState


def generate_report(processes: list[Process], attribution_summary: list[dict], sim_time_s: float) -> dict:
    total_mah = sum(a["total_mah"] for a in attribution_summary)
    screen_on_s = sum(p.fg_time_s for p in processes)
    top5 = attribution_summary[:5]

    return {
        "sim_hours_elapsed": round(max(0.01, (sim_time_s - 8 * 3600.0) / 3600.0), 2),
        "total_drain_mah": round(total_mah, 2),
        "screen_on_minutes": round(screen_on_s / 60.0, 1),
        "top_5_drainers": top5,
        "all_apps": attribution_summary,
    }


def export_report_csv(attribution_summary: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "App", "Package", "Total (mAh)", "Share (%)",
        "Foreground (mAh)", "Background (mAh)",
        "CPU (mAh)", "Screen (mAh)", "Network (mAh)", "GPS (mAh)", "Wakelock (mAh)"
    ])
    for a in attribution_summary:
        writer.writerow([
            a["display_name"], a["package_name"], a["total_mah"], a["pct_of_total"],
            a["fg_mah"], a["bg_mah"], a["cpu_mah"], a["screen_mah"],
            a["network_mah"], a["gps_mah"], a["wakelock_mah"]
        ])
    return buf.getvalue()


def detect_anomalies(processes: list[Process], attribution_summary: list[dict]) -> list[dict]:
    """
    Rule-based + ratio-based anomaly detection for rogue/misbehaving apps.
    """
    attr_map = {a["package_name"]: a for a in attribution_summary}
    alerts: list[dict] = []

    for p in processes:
        if p.state == ProcessState.STOPPED:
            continue
        a = attr_map.get(p.package_name, {})
        bg_mah = a.get("bg_mah", 0.0)
        fg_mah = a.get("fg_mah", 0.0)

        # 1. Excessive wakelock duration in background
        if p.wakelock_duration_s >= 60.0 and p.fg_time_s < 30.0:
            alerts.append({
                "severity": "HIGH",
                "package_name": p.package_name,
                "display_name": p.display_name,
                "reason": f"{p.display_name} held a wakelock for {round(p.wakelock_duration_s / 60.0, 1)} min with minimal foreground use.",
                "suggested_action": "RESTRICT",
            })
        # 2. Disproportionate background drain vs foreground
        elif bg_mah > 5.0 and bg_mah > (fg_mah * 2.5 + 2.0):
            alerts.append({
                "severity": "MEDIUM",
                "package_name": p.package_name,
                "display_name": p.display_name,
                "reason": f"{p.display_name} consumed {bg_mah:.1f} mAh in background vs {fg_mah:.1f} mAh in foreground.",
                "suggested_action": "RESTRICT",
            })
        # 3. Excessive wakeups
        elif p.wakeups_count >= 5:
            alerts.append({
                "severity": "MEDIUM",
                "package_name": p.package_name,
                "display_name": p.display_name,
                "reason": f"{p.display_name} triggered {p.wakeups_count} background wakeups.",
                "suggested_action": "KILL",
            })

    return alerts

