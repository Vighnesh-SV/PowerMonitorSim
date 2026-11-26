"""
What-If Battery Optimizer:
Re-runs the same seeded day under baseline vs user-selected OS power policies
(Battery Saver, aggressive Doze, restrict RogueApp, cap brightness, cap CPU freq)
to quantify OS power-management impact.
"""

from __future__ import annotations

from backend.monitor.attribution import EnergyAttributionTracker
from backend.sim.device import SimulatedDevice
from backend.sim.power_manager import PowerManager, PowerPolicy
from backend.sim.process import ProcessState
from backend.sim.scheduler import OSScheduler
from backend.sim.workload import WorkloadGenerator
from backend.sim.engine import load_processes


def _run_headless_day(seed: int, policy: PowerPolicy, hours: int = 8) -> dict:
    device = SimulatedDevice(capacity_mah=4500.0, initial_pct=92.0)
    device.max_cpu_freq_cap = policy.max_cpu_freq_mhz
    scheduler = OSScheduler()
    pm = PowerManager()
    pm.policy = policy
    workload = WorkloadGenerator(seed=seed)
    processes = load_processes()
    attribution = EnergyAttributionTracker()

    dt_sim = 60.0  # 1 simulated minute per step
    total_steps = hours * 60
    sim_time = 8 * 3600.0
    curve: list[float] = []

    for step in range(total_steps):
        sim_time += dt_sim
        workload.step(sim_time, processes, device.state)
        if device.state.screen_on:
            device.state.brightness = min(device.state.brightness, policy.max_brightness)

        doze = pm.update(device.state.screen_on, processes, dt_sim)
        device.state.doze_active = doze

        total_cpu = 0.0
        any_gps = False
        any_net = False
        for p in processes:
            d = p.current_demand()
            tf = pm.throttle_factor(p)
            total_cpu += d.cpu * tf
            if d.gps * tf > 0.05:
                any_gps = True
            if d.network * tf > 0.05:
                any_net = True
            p.wakelock_held = bool(d.wakelock and p.is_runnable() and tf > 0.15)

        device.state.gps_active = any_gps
        device.select_cpu_freq(total_cpu)
        cpu_shares = scheduler.schedule_tick(processes, dt_sim)

        prof = device.profile
        cpu_ma = prof.cpu_freq_ma.get(device.state.cpu_freq_mhz, 140.0) if total_cpu > 0.01 else prof.cpu_idle_ma
        screen_ma = device.compute_screen_ma()
        net_ma = prof.wifi_active_ma if any_net else prof.wifi_idle_ma
        gps_ma = prof.gps_on_ma if any_gps else 0.0

        tot_net = sum(p.current_demand().network * pm.throttle_factor(p) for p in processes)
        tot_gps = sum(p.current_demand().gps * pm.throttle_factor(p) for p in processes)
        load_ma = (prof.doze_idle_ma if doze else 25.0) + screen_ma + cpu_ma + net_ma + gps_ma

        for p in processes:
            d = p.current_demand()
            tf = pm.throttle_factor(p)
            p_cpu = cpu_ma * cpu_shares.get(p.pid, 0.0)
            p_scr = screen_ma if p.state == ProcessState.FOREGROUND else 0.0
            p_net = (net_ma * (d.network * tf / tot_net)) if tot_net > 0 else 0.0
            p_gps = (gps_ma * (d.gps * tf / tot_gps)) if tot_gps > 0 else 0.0
            p_wl = prof.wakelock_ma if p.wakelock_held else 0.0
            if p.wakelock_held:
                load_ma += p_wl
            p.component_power_ma = {"cpu": p_cpu, "screen": p_scr, "network": p_net, "gps": p_gps, "wakelock": p_wl}
            p.current_power_ma = p_cpu + p_scr + p_net + p_gps + p_wl

        attribution.record_tick(processes, dt_sim)
        device.battery.step(load_ma, dt_sim)
        if step % 30 == 0:
            curve.append(device.battery.state.level_pct)

    return {
        "final_level_pct": device.battery.state.level_pct,
        "remaining_mah": round(device.battery.state.remaining_mah, 1),
        "curve": curve,
        "attribution": attribution.get_summary(),
    }


def run_what_if(
    seed: int,
    battery_saver: bool = False,
    aggressive_doze: bool = False,
    restrict_rogue: bool = True,
    max_brightness: float = 0.7,
    max_cpu_freq_mhz: int = 1800,
) -> dict:
    baseline = _run_headless_day(seed, PowerPolicy())
    opt_policy = PowerPolicy(
        battery_saver=battery_saver,
        aggressive_doze=aggressive_doze,
        max_brightness=max_brightness,
        max_cpu_freq_mhz=max_cpu_freq_mhz,
        restricted_packages={"com.shady.roguecleaner"} if restrict_rogue else None,
    )
    optimized = _run_headless_day(seed, opt_policy)
    return {
        "baseline": baseline,
        "optimized": optimized,
        "pct_saved": round(optimized["final_level_pct"] - baseline["final_level_pct"], 2),
        "mah_saved": round(optimized["remaining_mah"] - baseline["remaining_mah"], 1),
    }
