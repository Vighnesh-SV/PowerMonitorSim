"""
Cumulative per-app energy attribution (mAh) broken down by hardware component
(cpu, screen, network, gps, wakelock) and foreground vs background split.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.sim.process import Process, ProcessState


@dataclass
class AppEnergyRecord:
    package_name: str
    display_name: str
    cpu_mah: float = 0.0
    screen_mah: float = 0.0
    network_mah: float = 0.0
    gps_mah: float = 0.0
    wakelock_mah: float = 0.0
    fg_mah: float = 0.0
    bg_mah: float = 0.0

    @property
    def total_mah(self) -> float:
        return self.cpu_mah + self.screen_mah + self.network_mah + self.gps_mah + self.wakelock_mah

    def to_dict(self, total_all_mah: float) -> dict:
        tot = self.total_mah
        pct = (tot / total_all_mah * 100.0) if total_all_mah > 0 else 0.0
        return {
            "package_name": self.package_name,
            "display_name": self.display_name,
            "total_mah": round(tot, 3),
            "pct_of_total": round(pct, 1),
            "cpu_mah": round(self.cpu_mah, 3),
            "screen_mah": round(self.screen_mah, 3),
            "network_mah": round(self.network_mah, 3),
            "gps_mah": round(self.gps_mah, 3),
            "wakelock_mah": round(self.wakelock_mah, 3),
            "fg_mah": round(self.fg_mah, 3),
            "bg_mah": round(self.bg_mah, 3),
        }


class EnergyAttributionTracker:
    def __init__(self):
        self.records: dict[str, AppEnergyRecord] = {}

    def reset(self) -> None:
        self.records.clear()

    def record_tick(self, processes: list[Process], dt_sim_s: float) -> None:
        dt_h = dt_sim_s / 3600.0
        for p in processes:
            rec = self.records.get(p.package_name)
            if rec is None:
                rec = AppEnergyRecord(package_name=p.package_name, display_name=p.display_name)
                self.records[p.package_name] = rec

            cp = p.component_power_ma
            rec.cpu_mah += cp.get("cpu", 0.0) * dt_h
            rec.screen_mah += cp.get("screen", 0.0) * dt_h
            rec.network_mah += cp.get("network", 0.0) * dt_h
            rec.gps_mah += cp.get("gps", 0.0) * dt_h
            rec.wakelock_mah += cp.get("wakelock", 0.0) * dt_h

            tick_mah = p.current_power_ma * dt_h
            if p.state in (ProcessState.FOREGROUND, ProcessState.VISIBLE):
                rec.fg_mah += tick_mah
            else:
                rec.bg_mah += tick_mah

    def get_summary(self) -> list[dict]:
        total_all = sum(r.total_mah for r in self.records.values())
        items = [r.to_dict(total_all) for r in self.records.values()]
        items.sort(key=lambda x: x["total_mah"], reverse=True)
        return items

