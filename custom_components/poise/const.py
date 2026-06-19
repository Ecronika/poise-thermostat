"""Constants and reasoned defaults for Poise (ADR-0008 default-derivation table)."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "poise"
VERSION: Final = "0.2.0"

# Tick / execution (ADR-0006, ADR-0020)
TICK_INTERVAL_S: Final = 60.0

# Comfort / safety defaults (ADR-0008). Each value is derivable & on the safe side.
DEFAULT_TARGET_C: Final = 21.0
FROST_FLOOR_C: Final = 7.0
DEVICE_MAX_C: Final = 30.0
BANGBANG_HYSTERESIS_C: Final = 0.3

# Thermal model defaults (ADR-0009; ~6.7 h time constant, moderate residential room)
DEFAULT_ALPHA_PER_S: Final = 0.15 / 3600.0
DEFAULT_FULL_POWER_RISE_C: Final = 20.0

# Plausibility (ADR-0012 ingestion)
TEMP_PLAUSIBLE_MIN_C: Final = -50.0
TEMP_PLAUSIBLE_MAX_C: Final = 60.0
SENSOR_FREEZE_AFTER_S: Final = 1800.0

# Config-flow keys (ADR-0008)
CONF_NAME: Final = "name"
CONF_TEMP_SENSOR: Final = "temp_sensor"
CONF_ACTUATOR: Final = "actuator"
CONF_TRM_SENSOR: Final = "trm_sensor"
CONF_OUTDOOR_SENSOR: Final = "outdoor_sensor"
CONF_HUMIDITY_SENSOR: Final = "humidity_sensor"
CONF_MRT_SENSOR: Final = "mrt_sensor"
CONF_CATEGORY: Final = "category"
