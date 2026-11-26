"""
Simulated smartphone hardware device: CPU, screen, radios, GPS, and battery.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.sim.battery import Battery
from backend.sim.power_model import PowerProfile


@dataclass
class DeviceState:
    screen_on: bool = True
    brightness: float = 0.65          # 0.0 - 1.0
    cpu_cores: int = 8
    cpu_freq_mhz: int = 1200
    wifi_connected: bool = True
    cellular_active: bool = False
    gps_active: bool = False
    doze_active: bool = False


class SimulatedDevice:
    """Holds hardware state and computes instantaneous hardware power draw."""

    FREQ_LEVELS = (600, 1200, 1800, 2400)

    def __init__(self, capacity_mah: float = 4500.0, initial_pct: float = 92.0):
        self.battery = Battery(capacity_mah=capacity_mah, initial_pct=initial_pct)
        self.profile = PowerProfile()
        self.state = DeviceState()
        self.max_cpu_freq_cap: int = 2400

    def select_cpu_freq(self, total_cpu_demand: float) -> int:
        """DVFS-like frequency scaling based on aggregate runnable CPU demand."""
        if total_cpu_demand <= 0.05:
            freq = 600
        elif total_cpu_demand <= 0.35:
            freq = 1200
        elif total_cpu_demand <= 0.70:
            freq = 1800
        else:
            freq = 2400
        self.state.cpu_freq_mhz = min(freq, self.max_cpu_freq_cap)
        return self.state.cpu_freq_mhz

    def compute_screen_ma(self) -> float:
        if not self.state.screen_on:
            return 0.0
        return self.profile.screen_on_base_ma + (
            self.state.brightness * self.profile.screen_full_brightness_ma
        )

    def to_dict(self) -> dict:
        return {
            "screen_on": self.state.screen_on,
            "brightness": round(self.state.brightness, 2),
            "cpu_cores": self.state.cpu_cores,
            "cpu_freq_mhz": self.state.cpu_freq_mhz,
            "wifi_connected": self.state.wifi_connected,
            "cellular_active": self.state.cellular_active,
            "gps_active": self.state.gps_active,
            "doze_active": self.state.doze_active,
        }

