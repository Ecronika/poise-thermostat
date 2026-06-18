"""Constants and reasoned defaults for Poise (ADR-0008 default-derivation table)."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "poise"
VERSION: Final = "0.1.0"

# Tick / execution (ADR-0006, ADR-0020)
TICK_INTERVAL_S: Final = 60.0  # base interval; event-driven refresh on top

# Comfort / safety defaults (ADR-0008). Each value is derivable & on the safe side.
DEFAULT_TARGET_C: Final = 21.0  # EN 16798-1 Cat. II neutral, sedentary
FROST_FLOOR_C: Final = 7.0  # unconditional anti-frost floor (charter precedence)
DEVICE_MAX_C: Final = 30.0  # typical TRV upper limit
BANGBANG_HYSTERESIS_C: Final = 0.3  # Phase-0 trivial controller only

# Thermal model defaults (ADR-0009; ~6.7 h time constant, moderate residential room)
DEFAULT_ALPHA_PER_S: Final = 0.15 / 3600.0  # 1/s
DEFAULT_FULL_POWER_RISE_C: Final = 20.0  # equilibrium rise at full power

# Plausibility (ADR-0012 ingestion)
TEMP_PLAUSIBLE_MIN_C: Final = -50.0
TEMP_PLAUSIBLE_MAX_C: Final = 60.0
SENSOR_FREEZE_AFTER_S: Final = 1800.0
