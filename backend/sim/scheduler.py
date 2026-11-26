"""
OS CPU Scheduler simulation:
Assigns CPU slices to runnable processes per tick using priority + round-robin
(FOREGROUND > VISIBLE > SERVICE > BACKGROUND), tracks context switches and CPU time.
"""

from __future__ import annotations

from backend.sim.process import Process, ProcessState


STATE_PRIORITY = {
    ProcessState.FOREGROUND: 4,
    ProcessState.VISIBLE: 3,
    ProcessState.SERVICE: 2,
    ProcessState.BACKGROUND: 1,
    ProcessState.CACHED: 0,
    ProcessState.STOPPED: -1,
}


class OSScheduler:
    def __init__(self):
        self.total_context_switches: int = 0
        self._last_pid: int | None = None

    def schedule_tick(self, processes: list[Process], dt_sim_s: float) -> dict[int, float]:
        """
        Allocate CPU time (in ms) to runnable processes for this tick.
        Returns a mapping pid -> cpu_share (0.0 - 1.0 of total CPU capacity).
        """
        runnable = [p for p in processes if p.is_runnable() and p.current_demand().cpu > 0.0]
        if not runnable:
            return {}

        # Sort by priority descending, then round-robin via pid
        runnable.sort(key=lambda p: (-STATE_PRIORITY[p.state], p.pid))

        weighted: dict[int, float] = {}
        total_weight = 0.0
        for p in runnable:
            w = p.current_demand().cpu * STATE_PRIORITY[p.state]
            weighted[p.pid] = w
            total_weight += w

        shares: dict[int, float] = {}
        for p in runnable:
            share = weighted[p.pid] / total_weight if total_weight > 0 else 0.0
            shares[p.pid] = share
            p.cpu_time_ms += share * dt_sim_s * 1000.0 * min(1.0, p.current_demand().cpu + 0.1)
            if self._last_pid != p.pid:
                p.context_switches += 1
                self.total_context_switches += 1
                self._last_pid = p.pid

        return shares

