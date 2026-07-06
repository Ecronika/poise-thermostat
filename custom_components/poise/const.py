"""Constants and reasoned defaults for Poise (ADR-0008 default-derivation table)."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "poise"
VERSION: Final = "0.153.0"

# Tick / execution (ADR-0006, ADR-0020)
TICK_INTERVAL_S: Final = 60.0
# Hub staleness (ADR-0038): a zone whose snapshot is older than this — even if its
# coordinator still reports success — is dropped from the boiler aggregate, so a
# silently hung zone cannot call for heat forever (3 missed ticks).
HUB_ZONE_STALE_AFTER_S: Final = 180.0

# Comfort / safety defaults (ADR-0008). Each value is derivable & on the safe side.
DEFAULT_TARGET_C: Final = 21.0
FROST_FLOOR_C: Final = 7.0
DEVICE_MAX_C: Final = 30.0
BANGBANG_HYSTERESIS_C: Final = 0.3
# Only (re)write the actuator setpoint on a change of at least this much, or a
# mode change — spares battery/Zigbee TRVs from per-tick traffic (ADR-0012).
WRITE_DEADBAND_C: Final = 0.2

# Thermal model defaults (ADR-0009; ~6.7 h time constant, moderate residential room)
DEFAULT_ALPHA_PER_S: Final = 0.15 / 3600.0
DEFAULT_FULL_POWER_RISE_C: Final = 20.0

# Plausibility (ADR-0012 ingestion)
TEMP_PLAUSIBLE_MIN_C: Final = -50.0
TEMP_PLAUSIBLE_MAX_C: Final = 60.0
SENSOR_FREEZE_AFTER_S: Final = (
    7200.0  # 2 h: last_changed-based (F1), avoids false alarms on stable rooms
)
# After this long fully unavailable (not just frozen), degrade to the frost/mould
# floor like a frozen sensor -- fail toward warmth (review #7). Longer than a tick
# so brief drop-outs / restarts just hold the last state.
UNAVAILABLE_SAFE_AFTER_S: Final = 1800.0  # 30 min
LOW_BATTERY_PCT: Final = 15.0
# Below this learned time constant a sensor is likely on/near the heat source
MIN_PLAUSIBLE_TAU_H: Final = 1.0

# Config-flow keys (ADR-0008)
CONF_NAME: Final = "name"
CONF_TEMP_SENSOR: Final = "temp_sensor"
CONF_ACTUATOR: Final = "actuator"
CONF_TRM_SENSOR: Final = "trm_sensor"
CONF_OUTDOOR_SENSOR: Final = "outdoor_sensor"
CONF_HUMIDITY_SENSOR: Final = "humidity_sensor"
CONF_MRT_SENSOR: Final = "mrt_sensor"
CONF_CATEGORY: Final = "category"
CONF_WINDOW_SENSOR: Final = "window_sensor"
CONF_COMFORT_BASE: Final = "comfort_base"
CONF_CLIMATE_MODE: Final = "climate_mode"
CONF_COOL_MIN_OUTDOOR: Final = "cool_min_outdoor"
CONF_HEAT_MAX_OUTDOOR: Final = "heat_max_outdoor"
CONF_COMFORT_WEIGHT: Final = "comfort_weight"
CONF_COMFORT_START: Final = "comfort_start"
CONF_COMFORT_END: Final = "comfort_end"
CONF_SETBACK_DELTA: Final = "setback_delta"
CONF_OPTIMAL_START: Final = "optimal_start"
CONF_WEATHER: Final = "weather_entity"
CONF_IRRADIANCE: Final = "irradiance_sensor"
CONF_TRV_EXTERNAL_TEMP: Final = "trv_external_temp_input"
CONF_OPERATIVE_INPUT: Final = "operative_input"
DEFAULT_COMFORT_BASE: Final = 21.0
DEFAULT_COMFORT_WEIGHT: Final = 70
DEFAULT_SETBACK_DELTA: Final = 3.0
# Outdoor lockouts (ADR-0047): cool only when outdoor >= cool_min, heat only when
# outdoor <= heat_max. Defaults from ADR-0023/RoomMind; configurable per zone.
# For internal-gain rooms (servers, kitchen, sun-facing), set the cool floor very
# low so the room cools regardless of a mild outdoor temperature.
DEFAULT_COOL_MIN_OUTDOOR_C: Final = 16.0
DEFAULT_HEAT_MAX_OUTDOOR_C: Final = 22.0

# Efficiency report (ADR-0045): an *estimate* from a configured annual figure,
# not metered energy. Defaults are sane EU values; override per zone.
CONF_ANNUAL_KWH: Final = "annual_heating_kwh"
CONF_PRICE_EUR_KWH: Final = "price_eur_kwh"
DEFAULT_ANNUAL_KWH: Final = 12000.0
DEFAULT_PRICE_EUR_KWH: Final = 0.30

# Actuator dynamics profile (ADR-0052): retune PI/MPC to the device's speed
# class. "auto" derives it from the actuator's capabilities; override per zone.
CONF_DYNAMICS: Final = "actuator_dynamics"
DEFAULT_DYNAMICS: Final = "auto"

# Single-AC compressor guard (ADR-0046 §8, live). Hold back a mode nudge that
# would short-cycle the compressor: start it after a recent stop (min-off) or
# flip cool<->dry (mode-hold). The device firmware already enforces ~180 s, so
# this is wear/efficiency hygiene on top — 300/300 by default (not the 600 s hub
# group value). Zone options override the dynamics-profile default; "off" is the
# kill switch. Capability-gated (a heat-only TRV never gets a gate) and it never
# blocks a stop or a safety action (frost / window / frozen / unavailable-safe).
CONF_COMPRESSOR_GUARD: Final = "compressor_guard"
CONF_COMPRESSOR_MIN_OFF: Final = "compressor_min_off_s"
CONF_COMPRESSOR_MODE_HOLD: Final = "compressor_mode_hold_s"
COMPRESSOR_GUARD_AUTO: Final = "auto"
COMPRESSOR_GUARD_OFF: Final = "off"
DEFAULT_COMPRESSOR_MIN_OFF_S: Final = 300.0
DEFAULT_COMPRESSOR_MODE_HOLD_S: Final = 300.0

# Field-trace recorder (ADR-0011 golden-file replay); opt-in, default off.
CONF_TRACE_RECORDING: Final = "trace_recording"
DEFAULT_TRACE_MAX_BYTES: Final = 20 * 1024 * 1024

# Presence coupling (ADR-0058): optional home/room entities feed `occupied`
# hierarchically; absent both -> today's behaviour, zero regression.
CONF_PRESENCE_HOME: Final = "presence_home"  # person/device_tracker/group
CONF_OCCUPANCY_SENSOR: Final = "occupancy_sensor"  # binary_sensor motion/occupancy
CONF_ABSENCE_AFTER_MIN: Final = "absence_after_min"
DEFAULT_ABSENCE_AFTER_MIN: Final = 30.0

# Heat-day cooling raise (ADR-0051): raise the cool setpoint toward outdoor-ΔT,
# capped at the ASR office ceiling (raising the cap is an employer opt-in).
# Defaults live in comfort/thermal_shock.py. With the default 26 °C cap the
# raise is a no-op until the cap is raised.
CONF_THERMAL_SHOCK_DELTA: Final = "thermal_shock_delta_k"
CONF_COOL_HARD_CAP: Final = "cool_hard_cap_c"
# ADR-0023 §1 (opt-in per zone): use the EN adaptive cooling edge (capped
# at the ASR ceiling above) instead of the fixed summer band, so a warm
# free-running room is not over-cooled toward 23 °C.
CONF_ADAPTIVE_COOL: Final = "adaptive_cool"
DEFAULT_ADAPTIVE_COOL: Final = "auto"  # tri-state auto|on|off (ADR-0008)

# Persistence (ADR-0007)
EKF_SAVE_EVERY_TICKS: Final = 30

# Optimal-start forecast (ADR-0025); refresh the weather forecast at most this often
FORECAST_TTL_S: Final = 900.0

# Multi-zone hub & boiler-demand aggregate (ADR-0038/0039)
CONF_ENTRY_TYPE: Final = "entry_type"
ENTRY_TYPE_SYSTEM: Final = "system"
CONF_BOILER_COUNT_THRESHOLD: Final = "boiler_count_threshold"
CONF_BOILER_POWER_THRESHOLD: Final = "boiler_power_threshold"
CONF_CONTROLS_BOILER: Final = "controls_boiler"
DEFAULT_BOILER_COUNT_THRESHOLD: Final = 1

# Boiler actuation (ADR-0039 Stufe 2). Actions optional -> sha