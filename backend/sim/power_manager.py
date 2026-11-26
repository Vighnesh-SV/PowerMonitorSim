"""
Android PowerManager simulation:
- Doze mode: engages when screen is off and no foreground/active media service is holding
  the device awake (except rogue/explicit wakelocks).
- App Standby Buckets: throttles background network/CPU for RARE and RESTRICTED apps.
- Battery Saver policy flags (used by What-If Optimizer as well).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.sim.process import Process, ProcessState, StandbyBucket


@dataclass
class PowerPolicy:
    battery_saver: bool = False
    aggressive_doze: bool = False
    max_brightness: float = 1.0
    max_cpu_freq_mhz: int = 2400
    restricted_packages: set[str] | None = None


class PowerManager:
    def __init__(self):
        self.screen_off_duration_s: float = 0.0
        self.doze_active: bool = False
        self.policy = PowerPolicy()

    def update(self, screen_on: bool, processes: list[Process], dt_sim_s: float) -> bool:
        if screen_on:
            self.screen_off_duration_s = 0.0
            self.doze_active = False
        else:
            self.screen_off_duration_s += dt_sim_s
            threshold = 60.0 if self.policy.aggressive_doze else 300.0
            if self.screen_off_duration_s >= threshold:
                self.doze_active = True

        # Apply policy-level restrictions
        if self.policy.restricted_packages:
            for p in processes:
                if p.package_name in self.policy.restricted_packages:
                    p.standby_bucket = StandbyBucket.RESTRICTED

        return self.doze_active

    def throttle_factor(self, proc: Process) -> float:
        """
        Returns 0.0-1.0 multiplier on background resource demand based on
        Doze mode, Battery Saver, and App Standby Bucket.
        """
        if proc.state in (ProcessState.FOREGROUND, ProcessState.VISIBLE):
            return 1.0

        factor = 1.0
        if proc.standby_bucket == StandbyBucket.RARE:
            factor *= 0.4
        elif proc.standby_bucket == StandbyBucket.RESTRICTED:
            factor *= 0.1

        if self.doze_active and not proc.wakelock_held:
            factor *= 0.2

        if self.policy.battery_saver:
            factor *= 0.5

        return factor

