"""
Simulated smartphone battery model.

Models capacity (mAh), state of charge (%), realistic non-linear Li-ion
voltage curve, thermal dynamics (temperature rise under load, ambient cooling),
charging/discharging states, and battery health degradation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChargingState(str, Enum):
    DISCHARGING = "DISCHARGING"
    CHARGING = "CHARGING"
    FULL = "FULL"


@dataclass
class BatteryState:
    capacity_mah: float = 4500.0
    remaining_mah: float = 4050.0  # Starts at 90%
    level_pct: float = 90.0
    voltage_mv: int = 4120
    temperature_c: float = 28.5
    current_ma: float = 0.0  # Positive = discharging, Negative = charging
    charging_state: ChargingState = ChargingState.DISCHARGING
    health_pct: float = 98.0
    charge_rate_ma: float = 2400.0  # Fast charger ~2.4A


class Battery:
    """Li-ion smartphone battery physics and state model."""

    AMBIENT_TEMP_C = 25.0
    MIN_VOLTAGE_MV = 3300
    MAX_VOLTAGE_MV = 4350

    def __init__(self, capacity_mah: float = 4500.0, initial_pct: float = 90.0, health_pct: float = 98.0):
        effective_cap = capacity_mah * (health_pct / 100.0)
        self.state = BatteryState(
            capacity_mah=effective_cap,
            remaining_mah=effective_cap * (initial_pct / 100.0),
            level_pct=initial_pct,
            health_pct=health_pct,
        )
        self._update_voltage()

    def _update_voltage(self) -> None:
        """
        Approximate Li-ion open-circuit voltage curve (3.3V empty -> 4.35V full)
        with a slight internal-resistance sag under high discharge current.
        """
        soc = max(0.0, min(1.0, self.state.level_pct / 100.0))
        # S-curve approximation: steep at ends, flatter in 20%-80% plateau
        if soc < 0.15:
            ocv = 3300 + (soc / 0.15) * 400
        elif soc < 0.85:
            ocv = 3700 + ((soc - 0.15) / 0.70) * 400
        else:
            ocv = 4100 + ((soc - 0.85) / 0.15) * 250

        # Internal resistance sag (~0.12 ohm -> 0.12 mV per mA)
        sag = self.state.current_ma * 0.08
        self.state.voltage_mv = int(max(3100, min(4400, ocv - sag)))

    def step(self, load_ma: float, dt_seconds: float) -> None:
        """
        Advance battery state by dt_seconds given instantaneous system load (mA).
        """
        dt_hours = dt_seconds / 3600.0

        if self.state.charging_state == ChargingState.CHARGING:
            # Net current: charger supplies charge_rate_ma, load consumes load_ma
            # Taper charging above 80% SoC (CC-CV behavior)
            taper = 1.0 if self.state.level_pct < 80.0 else max(0.2, (100.0 - self.state.level_pct) / 20.0)
            charge_in = self.state.charge_rate_ma * taper
            net_ma = load_ma - charge_in  # negative means net charging
            self.state.current_ma = round(net_ma, 1)
            self.state.remaining_mah = min(
                self.state.capacity_mah,
                max(0.0, self.state.remaining_mah - net_ma * dt_hours),
            )
            if self.state.remaining_mah >= self.state.capacity_mah - 0.5:
                self.state.remaining_mah = self.state.capacity_mah
                self.state.charging_state = ChargingState.FULL
                self.state.current_ma = 0.0
        elif self.state.charging_state == ChargingState.FULL:
            self.state.current_ma = 0.0
        else:
            self.state.current_ma = round(load_ma, 1)
            self.state.remaining_mah = max(0.0, self.state.remaining_mah - load_ma * dt_hours)

        self.state.level_pct = round((self.state.remaining_mah / self.state.capacity_mah) * 100.0, 2)

        # Thermal model: Joule heating proportional to |current|, Newton cooling to ambient
        heat_gain = (abs(self.state.current_ma) / 1000.0) * 0.45 * (dt_seconds / 60.0)
        cooling = (self.state.temperature_c - self.AMBIENT_TEMP_C) * 0.06 * (dt_seconds / 60.0)
        self.state.temperature_c = round(max(20.0, min(55.0, self.state.temperature_c + heat_gain - cooling)), 2)

        self._update_voltage()

    def set_charging(self, charging: bool) -> None:
        if charging:
            if self.state.level_pct >= 99.9:
                self.state.charging_state = ChargingState.FULL
            else:
                self.state.charging_state = ChargingState.CHARGING
        else:
            self.state.charging_state = ChargingState.DISCHARGING

    def estimated_time_remaining_min(self) -> float | None:
        """Estimate minutes until empty (discharging) or full (charging)."""
        if self.state.charging_state == ChargingState.DISCHARGING and self.state.current_ma > 1.0:
            return round((self.state.remaining_mah / self.state.current_ma) * 60.0, 1)
        if self.state.charging_state == ChargingState.CHARGING and self.state.current_ma < -1.0:
            needed = self.state.capacity_mah - self.state.remaining_mah
            return round((needed / abs(self.state.current_ma)) * 60.0, 1)
        return None

    def to_dict(self) -> dict:
        return {
            "capacity_mah": round(self.state.capacity_mah, 1),
            "remaining_mah": round(self.state.remaining_mah, 1),
            "level_pct": self.state.level_pct,
            "voltage_mv": self.state.voltage_mv,
            "temperature_c": self.state.temperature_c,
            "current_ma": self.state.current_ma,
            "charging_state": self.state.charging_state.value,
            "health_pct": self.state.health_pct,
            "eta_minutes": self.estimated_time_remaining_min(),
        }

