"""
Android-style power profile (analogous to frameworks/base/core/res/res/xml/power_profile.xml).
Defines baseline mA draw for hardware components in each power state.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PowerProfile:
    # CPU cluster active draw (mA) by frequency level (MHz)
    cpu_freq_ma: dict[int, float] = field(default_factory=lambda: {
        600: 28.0,
        1200: 65.0,
        1800: 130.0,
        2400: 240.0,
    })
    cpu_idle_ma: float = 6.0

    # Display: base when screen on + variable up to max brightness
    screen_on_base_ma: float = 55.0
    screen_full_brightness_ma: float = 190.0

    # Radios
    wifi_active_ma: float = 85.0
    wifi_idle_ma: float = 8.0
    cellular_active_ma: float = 150.0
    cellular_idle_ma: float = 18.0

    # GPS & Wakelock
    gps_on_ma: float = 95.0
    wakelock_ma: float = 18.0
    doze_idle_ma: float = 8.0

