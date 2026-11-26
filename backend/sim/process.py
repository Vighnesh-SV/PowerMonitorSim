"""
Simulated Android process model: lifecycle states, App Standby Buckets,
CPU accounting, wakelocks, and resource demand profiles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ProcessState(str, Enum):
    FOREGROUND = "FOREGROUND"  # Top activity visible & interactive (highest priority)
    VISIBLE = "VISIBLE"        # Visible but not focused (e.g. split-screen / PiP)
    SERVICE = "SERVICE"        # Bound/started background service (e.g. Spotify audio)
    BACKGROUND = "BACKGROUND"  # Backgrounded, subject to Doze & bucket limits
    CACHED = "CACHED"          # In memory LRU cache, minimal/no CPU
    STOPPED = "STOPPED"        # Killed / not running


class StandbyBucket(str, Enum):
    ACTIVE = "ACTIVE"
    WORKING_SET = "WORKING_SET"
    FREQUENT = "FREQUENT"
    RARE = "RARE"
    RESTRICTED = "RESTRICTED"


@dataclass
class ResourceDemand:
    cpu: float = 0.0       # 0.0 - 1.0 normalized demand
    network: float = 0.0   # 0.0 - 1.0 normalized demand
    gps: float = 0.0       # 0.0 - 1.0 normalized demand
    wakelock: bool = False
    screen_brightness_bias: float = 0.6


@dataclass
class Process:
    pid: int
    package_name: str
    display_name: str
    category: str
    fg_demand: ResourceDemand
    bg_demand: ResourceDemand
    is_rogue: bool = False

    state: ProcessState = ProcessState.CACHED
    standby_bucket: StandbyBucket = StandbyBucket.WORKING_SET

    # OS accounting metrics
    cpu_time_ms: float = 0.0
    fg_time_s: float = 0.0
    bg_time_s: float = 0.0
    context_switches: int = 0
    wakelock_held: bool = False
    wakelock_duration_s: float = 0.0
    wakeups_count: int = 0
    last_used_sim_s: float = 0.0

    # Instantaneous power draw (mA) attributed on the last tick
    current_power_ma: float = 0.0
    component_power_ma: dict[str, float] = field(default_factory=lambda: {
        "cpu": 0.0, "screen": 0.0, "network": 0.0, "gps": 0.0, "wakelock": 0.0
    })

    def current_demand(self) -> ResourceDemand:
        if self.state in (ProcessState.FOREGROUND, ProcessState.VISIBLE):
            return self.fg_demand
        if self.state in (ProcessState.SERVICE, ProcessState.BACKGROUND):
            return self.bg_demand
        return ResourceDemand()

    def is_runnable(self) -> bool:
        return self.state in (
            ProcessState.FOREGROUND,
            ProcessState.VISIBLE,
            ProcessState.SERVICE,
            ProcessState.BACKGROUND,
        )

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "package_name": self.package_name,
            "display_name": self.display_name,
            "category": self.category,
            "state": self.state.value,
            "standby_bucket": self.standby_bucket.value,
            "cpu_time_ms": round(self.cpu_time_ms, 1),
            "fg_time_s": round(self.fg_time_s, 1),
            "bg_time_s": round(self.bg_time_s, 1),
            "context_switches": self.context_switches,
            "wakelock_held": self.wakelock_held,
            "wakelock_duration_s": round(self.wakelock_duration_s, 1),
            "wakeups_count": self.wakeups_count,
            "current_power_ma": round(self.current_power_ma, 1),
            "component_power_ma": {k: round(v, 2) for k, v in self.component_power_ma.items()},
            "is_rogue": self.is_rogue,
        }

