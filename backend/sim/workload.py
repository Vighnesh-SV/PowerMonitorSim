"""
Seedable user workload generator.
Simulates a realistic smartphone day: morning commute (Maps/Spotify),
workday (WhatsApp/Gmail/Chrome), evening (YouTube/Instagram/3D Game),
night (screen off, Doze, RogueApp misbehaving in background).
"""

from __future__ import annotations

import random

from backend.sim.process import Process, ProcessState


class WorkloadGenerator:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self._next_event_sim_s: float = 0.0

    def reset(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self._next_event_sim_s = 0.0

    def step(self, sim_time_s: float, processes: list[Process], device_state) -> list[tuple[str, str, str]]:
        """
        Potentially trigger a user action (app switch, screen on/off).
        Returns list of (package_name, old_state, new_state) transitions.
        """
        transitions: list[tuple[str, str, str]] = []
        if sim_time_s < self._next_event_sim_s:
            return transitions

        hour = int((sim_time_s % 86400) // 3600)
        # Nighttime (00:00 - 06:30): screen mostly off
        if hour < 6 or (hour == 6 and self.rng.random() < 0.7):
            if device_state.screen_on:
                device_state.screen_on = False
                transitions.extend(self._background_all(processes))
            self._next_event_sim_s = sim_time_s + self.rng.randint(900, 2400)
            return transitions

        # Daytime: alternate between screen-on app sessions and screen-off idle
        if not device_state.screen_on or self.rng.random() < 0.28:
            device_state.screen_on = not device_state.screen_on
            if not device_state.screen_on:
                transitions.extend(self._background_all(processes))
                self._next_event_sim_s = sim_time_s + self.rng.randint(180, 900)
                return transitions

        # Screen is ON: pick a foreground app weighted by time of day
        candidates = [p for p in processes if not p.is_rogue]
        chosen = self._pick_app_for_hour(hour, candidates)
        if chosen:
            for p in processes:
                if p.pid == chosen.pid:
                    if p.state != ProcessState.FOREGROUND:
                        old = p.state.value
                        p.state = ProcessState.FOREGROUND
                        p.last_used_sim_s = sim_time_s
                        device_state.brightness = min(
                            1.0, max(0.3, chosen.fg_demand.screen_brightness_bias + self.rng.uniform(-0.1, 0.1))
                        )
                        transitions.append((p.package_name, old, p.state.value))
                elif p.state == ProcessState.FOREGROUND:
                    old = p.state.value
                    p.state = ProcessState.SERVICE if p.display_name == "Spotify" else ProcessState.BACKGROUND
                    transitions.append((p.package_name, old, p.state.value))

        # Ensure RogueApp periodically wakes up in background
        for p in processes:
            if p.is_rogue and p.state == ProcessState.CACHED and self.rng.random() < 0.4:
                old = p.state.value
                p.state = ProcessState.BACKGROUND
                p.wakeups_count += 1
                transitions.append((p.package_name, old, p.state.value))

        self._next_event_sim_s = sim_time_s + self.rng.randint(120, 600)
        return transitions

    def _background_all(self, processes: list[Process]) -> list[tuple[str, str, str]]:
        transitions = []
        for p in processes:
            if p.state in (ProcessState.FOREGROUND, ProcessState.VISIBLE):
                old = p.state.value
                p.state = ProcessState.SERVICE if p.display_name == "Spotify" else ProcessState.BACKGROUND
                transitions.append((p.package_name, old, p.state.value))
        return transitions

    def _pick_app_for_hour(self, hour: int, candidates: list[Process]) -> Process | None:
        if not candidates:
            return None
        weights = []
        for p in candidates:
            w = 1.0
            if 7 <= hour <= 9 and p.display_name in ("Google Maps", "Spotify", "Gmail"):
                w = 3.5
            elif 9 <= hour <= 17 and p.display_name in ("Chrome", "Gmail", "WhatsApp"):
                w = 3.0
            elif 18 <= hour <= 23 and p.display_name in ("YouTube", "Instagram", "3D Racers"):
                w = 4.0
            weights.append(w)
        return self.rng.choices(candidates, weights=weights, k=1)[0]

