"""
Mimics Android's android.os.BatteryManager API.
Exposes instantaneous battery properties from the simulated device.
"""

from __future__ import annotations

from backend.sim.device import SimulatedDevice


class BatteryManager:
    def __init__(self, device: SimulatedDevice):
        self._device = device

    def get_snapshot(self) -> dict:
        return self._device.battery.to_dict()

