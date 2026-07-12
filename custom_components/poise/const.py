"""Constants and reasoned defaults for Poise (ADR-0008 default-derivation table)."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "poise"
VERSION: Final = "0.166.0"

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
# P2-1: while a window is open, suppress the mould floor (heating toward ~24 °C
# fights the ventilation) for this many seconds — the frost floor always remains.
# DIN 4108-2 is a steady-state criterion, not a minute-scale window event.
WINDOW_MOULD_SUPPRESS_S: Final = 1800.0
BANGBANG_HYSTERESIS_C: Final = 0.3
# Only (re)write the actuator setpoint on a change of at least this much, or a
# mode change — spares battery/Zigbee TRVs from per-tick traffic (ADR-0012).
WRITE_DEADBAND_C: Final = 0.2

# P2-2: re-push the room temperature to a TRV external-temperature input at least
# this often, even when the value is unchanged. Some TRVs time out an external
# input and silently fall back to their own (mounted) sensor, so a stable room
# would otherwise let the feed go stale. 0 disables the time-based re-push.
EXTERNAL_FEED_KEEPALIVE_S: Final = 600.0

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
# ADR-0047: the outdoor lockout is a deactivatable efficiency guardrail
# (None = off). The number field always carries a value, so a per-direction
# enable toggle (default on) makes "lockout off" reachable in the UI; when off
# the coordinator passes None to decide_mode. Backward compatible (absent =
# enabled = today's behaviour).
CONF_HEAT_LOCKOUT_ENABLED: Final = "heat_lockout_enabled"
CONF_COOL_LOCKOUT_ENABLED: Final = "cool_lockout_enabled"
DEFAULT_HEAT_LOCKOUT_ENABLED: Final = True
DEFAULT_COOL_LOCKOUT_ENABLED: Final = True

# Efficiency report (ADR-0045): an *estimate* from a configured annual figure,
# not metered energy. Defaults are sane EU values; override per zone.
CONF_ANNUAL_KWH: Final = "annual_heating_kwh"
CONF_PRICE_EUR_KWH: Final = "price_eur_kwh"
DEFAULT_ANNUAL_KWH: Final = 12000.0
DEFAULT_PRICE_EUR_KWH: Final = 0.30  # electricity
DEFAULT_PRICE_GAS_EUR_KWH: Final = 0.11  # gas radiator (report-only fallback)

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
# ADR-0023 §1: use the EN adaptive cooling edge (capped at the ASR ceiling
# above) instead of the fixed summer band, so a warm free-running room is not
# over-cooled toward 23 °C. "auto" = capability-default: active on any
# cool-capable device (see README); set "off" to force the fixed summer band.
CONF_ADAPTIVE_COOL: Final = "adaptive_cool"
DEFAULT_ADAPTIVE_COOL: Final = "auto"  # tri-state auto|on|off (ADR-0008)

# Manual-override lifecycle (ADR-0059): a manual setpoint hold carries an explicit
# return policy + an expiry announced at set-time; Boost is timed; learning is
# observe-only (L1 capture in v1; L2 suggestions are v2, field latent).
CONF_OVERRIDE_POLICY: Final = "override_policy"
CONF_OVERRIDE_TIMER_H: Final = "override_timer_h"
CONF_OVERRIDE_MAX_H: Final = "override_max_h"
CONF_OVERRIDE_END_ON_PRESENCE: Final = "override_end_on_presence_change"
CONF_BOOST_DURATION_MIN: Final = "boost_duration_min"
CONF_OVERRIDE_SUGGESTIONS: Final = "override_suggestions"  # L2 (v2), latent
OVERRIDE_POLICY_SCHEDULE: Final = "schedule"
OVERRIDE_POLICY_TIMER: Final = "timer"
OVERRIDE_POLICY_PERMANENT: Final = "permanent"
# Read-fallback = schedule (new zones); async_migrate_entry stamps EXISTING room
# entries with "timer" so their fixed-2 h behaviour is preserved (ADR-0059 §7).
DEFAULT_OVERRIDE_POLICY: Final = "schedule"
DEFAULT_OVERRIDE_TIMER_H: Final = 2.0
DEFAULT_OVERRIDE_MAX_H: Final = 8.0
DEFAULT_OVERRIDE_END_ON_PRESENCE: Final = True
DEFAULT_BOOST_DURATION_MIN: Final = 60.0
DEFAULT_OVERRIDE_SUGGESTIONS: Final = True

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

# Boiler actuation (ADR-0039 Stufe 2). Actions optional -> shadow-only if unset.
CONF_BOILER_ON_ACTION: Final = "boiler_on_action"
CONF_BOILER_OFF_ACTION: Final = "boiler_off_action"
CONF_BOILER_ACTIVATION_DELAY: Final = "boiler_activation_delay_s"
CONF_BOILER_KEEPALIVE: Final = "boiler_keepalive_s"
CONF_BOILER_MIN_ON: Final = "boiler_min_on_s"
CONF_BOILER_MIN_OFF: Final = "boiler_min_off_s"
DEFAULT_BOILER_ACTIVATION_DELAY_S: Final = 0.0
DEFAULT_BOILER_KEEPALIVE_S: Final = 300.0  # review V2c: self-healing on by default
DEFAULT_BOILER_MIN_ON_S: Final = 300.0
DEFAULT_BOILER_MIN_OFF_S: Final = 300.0
# F9/review 2026-07-10: min-on/min-off are a physical anti-short-cycle dwell —
# 0 has no valid "off" meaning (unlike keepalive=0 or activation_delay=0). The
# read path clamps both up to this floor so a stored/typed 0 cannot switch the
# boiler every tick. 120 s = 2 ticks, the smallest dwell that actually binds
# (tick = 60 s). Applied uniformly (incl. shadow-only); clamp direction is
# always the safe one.
BOILER_MIN_DWELL_FLOOR_S: Final = 120.0

# Load shedding (S3) + compressor groups (S4) — both ADR-0013, shadow stage
CONF_MAX_POWER_SENSOR: Final = "max_power_sensor"
CONF_CURRENT_POWER_SENSOR: Final = "current_power_sensor"
CONF_COMPRESSOR_GROUP: Final = "compressor_group"
CONF_DECLARED_POWER: Final = "declared_power"

# Flow-temperature allocator (S5, ADR-0013) — highest request wins, capped, hysteresis
CONF_FLOW_TEMP: Final = "design_flow_temp"
CONF_MAX_FLOW_TEMP: Final = "max_flow_temp"
CONF_FLOW_HYSTERESIS: Final = "flow_hysteresis"
DEFAULT_MAX_FLOW_TEMP_C: Final = 60.0
DEFAULT_FLOW_HYSTERESIS_C: Final = 2.5

# Energy-aware source policy (S6, ADR-0013) — external layer steers, Poise routes
CONF_SOURCE_POLICY: Final = "source_policy"
CONF_DEFAULT_SOURCE: Final = "default_heat_source"
DEFAULT_HEAT_SOURCE: Final = "radiator"

# Bundled Lovelace card, served + auto-registered by the integration (ADR-0040)
CARD_URL_BASE: Final = "/poise"
CARD_MODULES: Final = ({"name": "Poise Card", "filename": "poise-card.js"},)
