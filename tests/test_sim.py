import pytest

from backend.sim.battery import Battery, ChargingState
from backend.sim.engine import SimulationEngine
from backend.sim.optimizer import run_what_if
from backend.sim.process import Process, ProcessState, ResourceDemand
from backend.sim.scheduler import OSScheduler


def test_battery_discharge_and_charge():
    b = Battery(capacity_mah=4000.0, initial_pct=50.0, health_pct=100.0)
    b.step(load_ma=400.0, dt_seconds=3600.0)  # 400 mAh drain = 10%
    assert b.state.level_pct == pytest.approx(40.0, abs=0.2)

    b.set_charging(True)
    assert b.state.charging_state == ChargingState.CHARGING
    b.step(load_ma=200.0, dt_seconds=1800.0)
    assert b.state.level_pct > 40.0


def test_scheduler_foreground_priority():
    sched = OSScheduler()
    p_fg = Process(
        pid=1, package_name="fg", display_name="FG", category="Test",
        fg_demand=ResourceDemand(cpu=0.5), bg_demand=ResourceDemand(cpu=0.1),
        state=ProcessState.FOREGROUND,
    )
    p_bg = Process(
        pid=2, package_name="bg", display_name="BG", category="Test",
        fg_demand=ResourceDemand(cpu=0.5), bg_demand=ResourceDemand(cpu=0.5),
        state=ProcessState.BACKGROUND,
    )
    shares = sched.schedule_tick([p_fg, p_bg], dt_sim_s=10.0)
    assert shares[1] > shares[2]
    assert p_fg.cpu_time_ms > p_bg.cpu_time_ms


def test_attribution_and_what_if_optimizer():
    eng = SimulationEngine(seed=42)
    for _ in range(15):
        eng.step_once()
    summary = eng.attribution.get_summary()
    assert len(summary) == 10
    assert sum(a["total_mah"] for a in summary) > 0

    res = run_what_if(seed=42, battery_saver=True, aggressive_doze=True, restrict_rogue=True)
    assert res["optimized"]["final_level_pct"] >= res["baseline"]["final_level_pct"]

