"""
Simulation engine: manages the simulated clock, tick loop, speed multiplier,
pause/resume, reset, and coordinates Device, Scheduler, PowerManager, and Workload.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, Awaitable

from backend.monitor.attribution import EnergyAttributionTracker
from backend.monitor.logger import HistoryLogger
from backend.sim.device import SimulatedDevice
from backend.sim.power_manager import PowerManager
from backend.sim.process import Process, ProcessState, ResourceDemand, StandbyBucket
from backend.sim.scheduler import OSScheduler
from backend.sim.workload import WorkloadGenerator

APPS_CONFIG_PATH = Path(__file__).resolve().parent / "apps_config.json"


def load_processes() -> list[Process]:
    raw = json.loads(APPS_CONFIG_PATH.read_text(encoding="utf-8"))
    procs: list[Process] = []
    for idx, item in enumerate(raw):
        fg = item["fg_demand"]
        bg = item["bg_demand"]
        procs.append(
            Process(
                pid=1001 + idx,
                package_name=item["package"],
                display_name=item["name"],
                category=item["category"],
                fg_demand=ResourceDemand(**fg),
                bg_demand=ResourceDemand(**bg),
                is_rogue=item.get("is_rogue", False),
                state=ProcessState.BACKGROUND if item.get("is_rogue") else ProcessState.CACHED,
                standby_bucket=StandbyBucket.ACTIVE if idx == 0 else StandbyBucket.WORKING_SET,
            )
        )
    if procs:
        procs[0].state = ProcessState.FOREGROUND
    return procs


class SimulationEngine:
    VALID_SPEEDS = (1, 10, 60, 300)

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.speed: int = 10
        self.running: bool = False
        self.sim_time_seconds: float = 8 * 3600.0
        self.tick_count: int = 0

        self.device = SimulatedDevice(capacity_mah=4500.0, initial_pct=92.0)
        self.scheduler = OSScheduler()
        self.power_manager = PowerManager()
        self.workload = WorkloadGenerator(seed=seed)
        self.processes: list[Process] = load_processes()
        self.attribution = EnergyAttributionTracker()
        self.logger = HistoryLogger(sample_interval_ticks=5)
        self.recent_transitions: list[dict] = []

        self._on_tick_callbacks: list[Callable[[dict], Awaitable[None]]] = []
        self._task: asyncio.Task | None = None

    def register_callback(self, cb: Callable[[dict], Awaitable[None]]) -> None:
        self._on_tick_callbacks.append(cb)

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        self.sim_time_seconds = 8 * 3600.0
        self.tick_count = 0
        self.device = SimulatedDevice(capacity_mah=4500.0, initial_pct=92.0)
        self.scheduler = OSScheduler()
        self.power_manager = PowerManager()
        self.workload.reset(self.seed)
        self.processes = load_processes()
        self.attribution.reset()
        self.logger.start_new_session(self.seed)
        self.recent_transitions.clear()

    def set_speed(self, speed: int) -> None:
        if speed in self.VALID_SPEEDS:
            self.speed = speed

    def launch_app(self, package_name: str) -> None:
        self.device.state.screen_on = True
        for p in self.processes:
            if p.package_name == package_name:
                p.state = ProcessState.FOREGROUND
                p.last_used_sim_s = self.sim_time_seconds
            elif p.state == ProcessState.FOREGROUND:
                p.state = ProcessState.SERVICE if p.display_name == "Spotify" else ProcessState.BACKGROUND

    def kill_app(self, package_name: str) -> None:
        for p in self.processes:
            if p.package_name == package_name:
                p.state = ProcessState.STOPPED
                p.wakelock_held = False
                p.current_power_ma = 0.0

    def set_bucket(self, package_name: str, bucket: str) -> None:
        for p in self.processes:
            if p.package_name == package_name:
                p.standby_bucket = StandbyBucket(bucket)

    def step_once(self) -> dict:
        dt_sim = float(self.speed)
        self.sim_time_seconds += dt_sim
        self.tick_count += 1

        # 1. Workload user behavior
        transitions = self.workload.step(self.sim_time_seconds, self.processes, self.device.state)
        for pkg, old_s, new_s in transitions:
            self.recent_transitions.append({
                "sim_time_s": self.sim_time_seconds,
                "package_name": pkg,
                "old_state": old_s,
                "new_state": new_s,
            })
        if len(self.recent_transitions) > 200:
            self.recent_transitions = self.recent_transitions[-200:]

        # 2. PowerManager (Doze & Standby Buckets)
        doze = self.power_manager.update(self.device.state.screen_on, self.processes, dt_sim)
        self.device.state.doze_active = doze

        # 3. Scheduler & CPU frequency scaling
        total_cpu_demand = 0.0
        any_gps = False
        any_net = False

        for p in self.processes:
            if p.state == ProcessState.FOREGROUND:
                p.fg_time_s += dt_sim
            elif p.state in (ProcessState.SERVICE, ProcessState.BACKGROUND):
                p.bg_time_s += dt_sim

            d = p.current_demand()
            tf = self.power_manager.throttle_factor(p)
            total_cpu_demand += d.cpu * tf
            if d.gps * tf > 0.05:
                any_gps = True
            if d.network * tf > 0.05:
                any_net = True

            # Wakelock accounting
            p.wakelock_held = bool(d.wakelock and p.is_runnable() and tf > 0.15)
            if p.wakelock_held:
                p.wakelock_duration_s += dt_sim

        self.device.state.gps_active = any_gps
        self.device.state.wifi_connected = True
        self.device.select_cpu_freq(total_cpu_demand)
        cpu_shares = self.scheduler.schedule_tick(self.processes, dt_sim)

        # 4. Compute hardware component power (mA)
        profile = self.device.profile
        cpu_total_ma = (
            profile.cpu_freq_ma.get(self.device.state.cpu_freq_mhz, 140.0)
            if total_cpu_demand > 0.01
            else profile.cpu_idle_ma
        )
        screen_ma = self.device.compute_screen_ma()
        net_total_ma = profile.wifi_active_ma if any_net else profile.wifi_idle_ma
        gps_total_ma = profile.gps_on_ma if any_gps else 0.0

        # 5. Attribute power per process
        total_net_demand = sum(p.current_demand().network * self.power_manager.throttle_factor(p) for p in self.processes)
        total_gps_demand = sum(p.current_demand().gps * self.power_manager.throttle_factor(p) for p in self.processes)

        total_load_ma = profile.doze_idle_ma if doze else 25.0  # base OS overhead
        total_load_ma += screen_ma + cpu_total_ma + net_total_ma + gps_total_ma

        for p in self.processes:
            d = p.current_demand()
            tf = self.power_manager.throttle_factor(p)
            p_cpu = cpu_total_ma * cpu_shares.get(p.pid, 0.0)
            p_screen = screen_ma if p.state == ProcessState.FOREGROUND else 0.0
            p_net = (net_total_ma * (d.network * tf / total_net_demand)) if total_net_demand > 0 else 0.0
            p_gps = (gps_total_ma * (d.gps * tf / total_gps_demand)) if total_gps_demand > 0 else 0.0
            p_wl = profile.wakelock_ma if p.wakelock_held else 0.0
            if p.wakelock_held:
                total_load_ma += p_wl

            p.component_power_ma = {
                "cpu": p_cpu,
                "screen": p_screen,
                "network": p_net,
                "gps": p_gps,
                "wakelock": p_wl,
            }
            p.current_power_ma = p_cpu + p_screen + p_net + p_gps + p_wl

        # 6. Record attribution & step battery
        self.attribution.record_tick(self.processes, dt_sim)
        self.device.battery.step(total_load_ma, dt_sim)
        snap = self.get_snapshot()
        tick_transitions = [
            {"sim_time_s": self.sim_time_seconds, "package_name": pkg, "old_state": old_s, "new_state": new_s}
            for pkg, old_s, new_s in transitions
        ]
        self.logger.log_tick(self.tick_count, snap, tick_transitions)
        return snap

    def get_snapshot(self) -> dict:
        total_sec = int(self.sim_time_seconds)
        day = (total_sec // 86400) + 1
        rem = total_sec % 86400
        hh = rem // 3600
        mm = (rem % 3600) // 60
        ss = rem % 60
        return {
            "tick": self.tick_count,
            "running": self.running,
            "speed": self.speed,
            "seed": self.seed,
            "sim_time_seconds": self.sim_time_seconds,
            "sim_clock": f"Day {day} · {hh:02d}:{mm:02d}:{ss:02d}",
            "battery": self.device.battery.to_dict(),
            "device": self.device.to_dict(),
            "processes": [p.to_dict() for p in self.processes],
            "attribution": self.attribution.get_summary(),
            "scheduler": {
                "total_context_switches": self.scheduler.total_context_switches,
            },
        }

    async def start_loop(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            if self.running:
                snapshot = self.step_once()
                for cb in list(self._on_tick_callbacks):
                    try:
                        await cb(snapshot)
                    except Exception:
                        pass
            await asyncio.sleep(1.0)
