"""Home Assistant coordinator — wires the pure pipeline to HA (ADR-0006/0013/0023).

Each tick reads the zone's entities, builds the capability-aware dual-setpoint
comfort decision (ADR-0023), applies the comfort schedule / night setback and
optimal-start preheat (ADR-0025), and writes exactly one capability-correct
command to the actuator (single writer). The EKF (ADR-0002/0024) learns in the
background and is persisted per room (ADR-0007). Live safety: window-open pause
and heating-failure notification (ADR-0012).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import actuator as actuator_mod
from .adaptive_cool import adaptive_cool_mode, resolve_adaptive_cool
from .clock import MonotonicClock
from .comfort.dual_setpoint import decide as comfort_decide
from .comfort.en16798 import HEATING_LOWER, HEATING_UPPER, Category
from .comfort.fan_circulation import FAN_ONLY_LOW, fan_circulation
from .comfort.fan_cooling import fan_cool_setpoint, fan_velocity
from .comfort.free_running import free_running_widen
from .comfort.humidity import humidity_decide, rh_high_for_category
from .comfort.mode_seam import mode_arbitration
from .comfort.mold import mold_min_air_temperature_detail
from .comfort.operative import operative_temperature
from .comfort.pmv import pmv_ppd, seasonal_clo
from .comfort.presence import (
    PresenceConfig,
    PresenceLevel,
    any_present,
    resolve_presence,
    step_room_absence,
)
from .comfort.schedule import ComfortSchedule, ComfortWindow, parse_hhmm
from .comfort.thermal_shock import (
    DEFAULT_HARD_CAP_C,
    DEFAULT_SHOCK_DELTA_K,
    adaptive_cool_setpoint,
    rate_limit,
)
from .comfort.virtual_mrt import virtual_mrt
from .const import (
    COMPRESSOR_GUARD_AUTO,
    COMPRESSOR_GUARD_OFF,
    CONF_ABSENCE_AFTER_MIN,
    CONF_ACTUATOR,
    CONF_ADAPTIVE_COOL,
    CONF_ADOPT_EXTERNAL_MODE,
    CONF_ADOPT_EXTERNAL_SETPOINT,
    CONF_ANNUAL_KWH,
    CONF_BOOST_DURATION_MIN,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_COMPRESSOR_GUARD,
    CONF_COMPRESSOR_MIN_OFF,
    CONF_COMPRESSOR_MODE_HOLD,
    CONF_COOL_HARD_CAP,
    CONF_COOL_LOCKOUT_ENABLED,
    CONF_COOL_MIN_OUTDOOR,
    CONF_DYNAMICS,
    CONF_ENTRY_TYPE,
    CONF_HEAT_LOCKOUT_ENABLED,
    CONF_HEAT_MAX_OUTDOOR,
    CONF_HUMIDITY_SENSOR,
    CONF_IRRADIANCE,
    CONF_MRT_SENSOR,
    CONF_NAME,
    CONF_OCCUPANCY_SENSOR,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_OVERRIDE_END_ON_PRESENCE,
    CONF_OVERRIDE_MAX_H,
    CONF_OVERRIDE_POLICY,
    CONF_OVERRIDE_TIMER_H,
    CONF_PRESENCE_HOME,
    CONF_PRICE_EUR_KWH,
    CONF_SETBACK_DELTA,
    CONF_SOURCE_POLICY,
    CONF_TEMP_SENSOR,
    CONF_THERMAL_SHOCK_DELTA,
    CONF_TRACE_RECORDING,
    CONF_TRM_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    CONF_WEATHER,
    CONF_WINDOW_SENSOR,
    DEFAULT_ABSENCE_AFTER_MIN,
    DEFAULT_ADAPTIVE_COOL,
    DEFAULT_ADOPT_EXTERNAL_MODE,
    DEFAULT_ADOPT_EXTERNAL_SETPOINT,
    DEFAULT_ANNUAL_KWH,
    DEFAULT_BOOST_DURATION_MIN,
    DEFAULT_COMFORT_BASE,
    DEFAULT_COMFORT_WEIGHT,
    DEFAULT_COOL_LOCKOUT_ENABLED,
    DEFAULT_COOL_MIN_OUTDOOR_C,
    DEFAULT_DYNAMICS,
    DEFAULT_HEAT_LOCKOUT_ENABLED,
    DEFAULT_HEAT_MAX_OUTDOOR_C,
    DEFAULT_OVERRIDE_END_ON_PRESENCE,
    DEFAULT_OVERRIDE_MAX_H,
    DEFAULT_OVERRIDE_POLICY,
    DEFAULT_OVERRIDE_TIMER_H,
    DEFAULT_PRICE_EUR_KWH,
    DEFAULT_PRICE_GAS_EUR_KWH,
    DEFAULT_SETBACK_DELTA,
    DEFAULT_TRACE_MAX_BYTES,
    DEVICE_MAX_C,
    DOMAIN,
    EKF_SAVE_EVERY_TICKS,
    ENTRY_TYPE_SYSTEM,
    EXTERNAL_FEED_KEEPALIVE_S,
    FORECAST_TTL_S,
    FROST_FLOOR_C,
    LOW_BATTERY_PCT,
    MIN_PLAUSIBLE_TAU_H,
    OVERRIDE_POLICY_SCHEDULE,
    SENSOR_FREEZE_AFTER_S,
    SETPOINT_ADOPT_ECHO_WINDOW_S,
    TICK_INTERVAL_S,
    UNAVAILABLE_SAFE_AFTER_S,
    WINDOW_MOULD_SUPPRESS_S,
    WRITE_DEADBAND_C,
)
from .contracts import ActuatorCommand, ActuatorPath, Source
from .control.cooling import cooling_intent, override_mode
from .control.cover_shading import (
    predict_peak_operative,
    shading_target_position,
)
from .control.dynamics import (
    PROFILES,
    DeviceDynamics,
    classify_dynamics,
    regulation_throttled,
)
from .control.hdh_savings import HdhConfig, HdhSavings, report_price_eur_kwh
from .control.hub_aggregate import zone_heat_demand
from .control.lifecycle import resolve_safe_state
from .control.mpc import MpcParams
from .control.mpc_shadow import evaluate_shadow
from .control.optimal_start import (
    forecast_samples_from_response,
    mean_forecast_outdoor,
    plan_preheat,
)
from .control.outcome_scoring import (
    OutcomeSession,
    OutcomeStats,
    observe_session,
)
from .control.override import (
    OverrideConfig,
    OverrideMode,
    detect_external_mode,
    detect_external_setpoint,
    hold_ends_at_preheat,
    hold_expired,
    mode_adopt_reason,
    mode_comfort_base,
    resolve_boost_expiry,
    resolve_hold_expiry,
    setpoint_adopt_reason,
)
from .control.pi import PiCompensator
from .control.pi_shadow import evaluate_pi_shadow
from .control.reference_offset import (
    OffsetEstimate,
    compensated_setpoint,
    update_offset,
)
from .control.regulation_quality import RegulationQuality
from .control.scoring_expectation import model_expected_minutes
from .control.tick_budget import TickBudget
from .control.tick_resolve import (
    cool_drive_signal,
    external_feed_due,
    frost_rescue_target,
    heat_drive_signal,
    idle_park,
    needs_mode_nudge,
    resolve_desired_mode,
    resolve_write_target,
    sanitize_override,
    select_mrt,
    select_q_solar,
    select_t_rm,
    should_write,
    snap_to_step,
)
from .control.tpi_shadow import evaluate_tpi_shadow
from .control.window_auto import (
    WindowAutoConfig,
    WindowAutoState,
    adaptive_open_threshold,
    effective_window_open,
    quantized_slope,
    step_window_auto,
)
from .devices.capability import classify_number_entity, climate_capability
from .devices.model_fixes import (
    ext_temp_number_is_implausible,
    is_external_sensor_select,
    is_low_battery,
    looks_like_adaptive_mode_switch,
    looks_like_external_temp_number,
    looks_like_fault_alarm,
    looks_like_internal_schedule,
    looks_like_valve_steps,
)
from .estimation.heatup_rate import HeatupAccumulator, sample_heatup_rate
from .estimation.psychrometrics import dewpoint as psychro_dewpoint
from .estimation.psychrometrics import humidity_ratio
from .estimation.running_mean import RunningMeanTracker
from .estimation.seasonless_rate import SeasonlessRate
from .estimation.tau_settle import TauSettle, settle_confidence, update_settle
from .estimation.thermal_ekf import ThermalEKF
from .ingestion import RawSample, ingest_temperature, parse_finite
from .migration import as_entity_list
from .multi import lifecycle as _lifecycle
from .multi.discovery import EntitySnapshot
from .multi.model import DeviceHealth, Direction
from .multi.resolvers import ThermalDemand
from .multi.shadow import evaluate_thermal_shadow
from .safety.heating_failure import (
    HeatingFailureDetector,
    actuator_running,
)
from .safety.sensor_watchdog import (
    frozen_safe_target,
    is_frozen,
    sensor_age_seconds,
    sensor_at_heat_source,
    should_learn,
    unavailable_safe_engaged,
    valve_stuck,
)
from .storage import PoiseStore
from .trace.recorder import TraceRecorder
from .trace.schema import ModelSnapshot, build_record

_LOGGER = logging.getLogger(__name__)
# Conservative outdoor default when neither a sensor nor the running mean is
# known — mirrors control.mpc_controller._FALLBACK_T_OUT_C (a cold-ish day keeps
# heating engaged rather than mild-locking it out).
_FALLBACK_OUTDOOR_C = 5.0
# A hung weather.get_forecasts call must not stall the tick: it runs under the
# coordinator lock, so bound it and degrade to the constant outdoor (review V8).
_WEATHER_CALL_TIMEOUT_S = 10.0
# Comfort mode -> thermal-arbitration direction (ADR-0046 P1 shadow). "idle" and
# any other value map to None (no thermal demand).
_THERMAL_DIR: dict[str, Direction] = {"heat": Direction.HEAT, "cool": Direction.COOL}

_INVALID = {"unknown", "unavailable", ""}


def _num(state: State | None) -> float | None:
    if state is None or state.state in _INVALID:
        return None
    return parse_finite(state.state)  # rejects NaN/Inf at the boundary (C1)


def _num_attr(state: State | None, key: str) -> float | None:
    """Read a numeric attribute (e.g. a climate setpoint) or None."""
    if state is None or state.state == "unavailable":
        return None
    return parse_finite(state.attributes.get(key))


def _iso_utc(ts: float | None) -> str | None:
    """UTC ISO-8601 string for a wall-clock epoch, or None (ADR-0059 §4 attrs)."""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts is not None else None


class PoiseCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """One coordinator per room; capability-aware dual-setpoint each tick."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_S),
            # H-5: the snapshot carries a per-tick monotonic heartbeat ("mono_ts",
            # ADR-0038 hub staleness) that necessarily differs every tick, so the
            # data is never equal tick-to-tick -- always_update=False could never
            # skip and was a no-op. Be honest: every tick is a genuinely new state.
            # (Refresh storms from input churn are cut by the _on_change filter, H-1.)
            always_update=True,
        )
        self._clock = MonotonicClock()
        self._ekf = ThermalEKF()
        self._trm_tracker = RunningMeanTracker()
        self._seasonless = SeasonlessRate()
        # Sensorless open-window detection (shadow, ADR-0041): slope-based,
        # decoupled prev-sample so it observes regardless of heating.
        self._window_auto = WindowAutoState()
        self._was_cooling = False  # last tick cooled -> gate the window slope
        self._window_auto_cfg = WindowAutoConfig()
        self._wa_ref_room: float | None = None  # last distinct-move reference (V6)
        self._wa_ref_mono: float | None = None
        self._wa_prev_mono: float | None = None  # last tick, for the minutes_open dt
        self._window_bypass: bool = False  # ignore window reaction (ADR-0041 stage 2)
        self._wa_open_threshold: float = self._window_auto_cfg.open_threshold
        self._pi = PiCompensator()
        self._prev_room: float | None = None
        self._prev_room_mono: float | None = None
        # anti-quantization anchor for the seasonless heat-up rate (ADR-0004/0009)
        self._heatup_acc = HeatupAccumulator()
        self._last_target: float | None = None
        self._last_written_mode: str | None = None
        # K2: a device-side hvac_mode the user set (IR remote), adopted as a manual
        # mode-hold that shares the setpoint hold's lifecycle. Pins ``desired_hvac``
        # so Poise stops nudging it back; an ``off`` hold routes the zone through the
        # disabled/frost-rescue branch (frost + mould protection stay active).
        self._mode_override: str | None = None
        # last hvac_mode Poise itself commanded (nudge / frost / safe-state) + its
        # monotonic stamp -- the mode echo baseline (analogue of _last_written_sp).
        self._last_commanded_hvac: str | None = None
        self._last_hvac_cmd_ts: float | None = None
        # device mode at the previous tick -- the mode move-guard (a mode unchanged
        # since last reading is not a fresh user action).
        self._prev_device_mode: str | None = None
        self._last_written_sp: float | None = None  # P1-4a: last commanded (snapped)
        # P1-4a fix (v0.170.1): the device setpoint at the previous tick. A genuine
        # user change *moves* the setpoint; a value the device merely settled our
        # write at (its own re-quantise / min-max clamp) is stable tick-over-tick,
        # so requiring a move blocks re-adopting our own settled write as a hold
        # (the live "card-X resume springs back to manual" bug). Runtime-only.
        self._prev_device_sp: float | None = None
        # V2 (analysis 2026-07-14): HA ``Context`` ids of Poise's own actuator
        # service calls (setpoint / mode nudge). The next tick reads the actuator
        # state's context: if it is one of ours the change is our own write's echo
        # (incl. a device re-quantise / min-max clamp under a push integration) and
        # is re-baselined, never adopted -- the reliable signal the value/time
        # heuristic can only approximate. Bounded so it never grows unbounded.
        self._own_write_ctx_ids: deque[str] = deque(maxlen=16)
        # V1: the device's reported setpoint captured immediately before our last
        # write. Inside the echo window a legit echo can only be the commanded value
        # or this pre-write value; anything else is a provable user change.
        self._pre_write_sp: float | None = None
        # AR-11: True once any setpoint/mode write to the actuator has SUCCEEDED
        # this run (tick, unavailable-safe, or frost rescue). Persisted + restored;
        # gates the teardown park so a zone that never actuated is not "parked".
        self._has_actuated = False
        self._last_sp_write_ts: float | None = None  # ADR-0052 §4 nudge throttle
        self._last_fed: float | None = None
        self._last_fed_ts: float = 0.0  # P2-2 external-feed keep-alive (monotonic)
        self._dirty = False  # override/enabled/mode changed -> persist next save
        self._store = PoiseStore(hass, entry.entry_id)
        self._failure = HeatingFailureDetector()
        # R3: the heating-failure verdict is computed late in the tick, after the
        # learn gate runs; latch the previous tick's value so the gate can pause
        # EKF learning during a boiler-off/valve-open episode (VTherm #1428).
        self._prev_heating_failed: bool = False
        self._last_mono: float | None = None
        self._last_u_h: float = 0.0
        self._last_u_c: float = 0.0
        self._last_q_solar: float = 0.0
        self._unavailable_since: float | None = None  # review #7: sustained loss
        self._save_counter = 0
        # Silver log-when-unavailable: log the loss/recovery of the room sensor
        # exactly once each, not every 60 s tick.
        self._unavailable_logged = False
        self._entry_id = entry.entry_id
        self._data_snapshot: dict[str, Any] = dict(entry.data)  # F14 reconfigure guard
        self._save_failures = 0  # F24: consecutive store-save failures
        self._tick_failures = 0  # F12: consecutive _run_once failures
        self._active_issues: set[str] = set()
        self._lock = asyncio.Lock()
        self._enabled = True
        self._override: float | None = None
        self._override_set_wall: float | None = None
        # ADR-0059 manual-hold + timed-Boost lifecycle (all wall-clock; persisted).
        self._override_requested: float | None = None  # pre-clamp user ask
        self._override_expires_at: float | None = None  # announced at set-time
        # ADR-0059 §1: was the announced expiry the switchpoint (not the timer
        # fallback / max_h cap)? -> _expire_timed_states' reason accuracy.
        self._override_expiry_is_switchpoint: bool = False
        self._override_policy: str = DEFAULT_OVERRIDE_POLICY
        self._override_stats: list[dict[str, Any]] = []  # §5 L1 (observe-only)
        # K3 (Inc 3): origin of the active hold (ui_setpoint / device_adopt_* / …),
        # persisted; + the last suppression reason logged, to debounce the debug log.
        self._override_reason: str | None = None
        self._last_adopt_log: str = ""
        self._boost_expires_at: float | None = None
        self._boost_prev_preset: OverrideMode | None = None  # VT#1961 restore
        self._prev_home: bool | None = None  # §1 house-gate flip tracking
        self._last_presence_level: str = "comfort"  # cached for the §5 stat
        self._last_window_open: bool = False  # cached for the §5 stat
        # P2-1: monotonic stamp of the current open-window episode's rising edge;
        # gates the mould write-floor for its first WINDOW_MOULD_SUPPRESS_S.
        self._window_open_since: float | None = None
        self._climate_entity_id: str | None = None  # for the ended-event payload
        # ADR-0046 P2: per-device anti-short-cycle lifecycle (wall-clock, survives
        # restart). Shadow-only today — tracks the actuator's run-state + health to
        # report the min-off / health gate; actuates nothing until P3.
        self._multi_lifecycle = _lifecycle.DeviceLifecycle()
        self._preset: OverrideMode = OverrideMode.NONE
        self._override_cfg = OverrideConfig()
        # options override data for hot-applyable tuning (A10); structural
        # inputs (sensors/actuator) live only in data.
        data = {**entry.data, **entry.options}
        self._read_override_options(data)  # ADR-0059 §1/§2 hold/Boost tuning

        def _require(key: str) -> str:
            # AR-34: a corrupt entry missing a structural field must fail setup
            # cleanly (ConfigEntryError -> SETUP_ERROR + repair flow), not raise an
            # uncaught KeyError from ``data[key]``.
            val = data.get(key)
            if not isinstance(val, str) or not val:
                raise ConfigEntryError(
                    f"Poise entry '{entry.entry_id}' is missing the required "
                    f"'{key}' setting; reconfigure the zone."
                )
            return val

        self.zone_name: str = _require(CONF_NAME)
        # opt-in field-trace recorder (ADR-0011 golden-file replay); default off.
        self._trace_enabled: bool = bool(data.get(CONF_TRACE_RECORDING, False))
        self._trace_recorder: TraceRecorder | None = None
        self._trace_slug: str = entry.entry_id
        self._tick_budget = TickBudget()  # ADR-0020 per-tick compute-time budget
        self._temp: str = _require(CONF_TEMP_SENSOR)
        self._actuator: str = _require(CONF_ACTUATOR)
        self._trm: str | None = data.get(CONF_TRM_SENSOR)
        self._outdoor: str | None = data.get(CONF_OUTDOOR_SENSOR)
        self._humidity: str | None = data.get(CONF_HUMIDITY_SENSOR)
        self._mrt: str | None = data.get(CONF_MRT_SENSOR)
        # ADR-0058 presence coupling (optional; empty -> today's behaviour). Both
        # are multiple=True (ADR-0007): OR-reduced across the set, str-tolerant.
        self._presence_home_entities: list[str] = as_entity_list(
            data.get(CONF_PRESENCE_HOME)
        )
        self._occupancy_entities: list[str] = as_entity_list(
            data.get(CONF_OCCUPANCY_SENSOR)
        )
        self._presence_cfg = PresenceConfig(
            absence_after_min=float(
                data.get(CONF_ABSENCE_AFTER_MIN, DEFAULT_ABSENCE_AFTER_MIN)
            ),
            eco_delta=self._override_cfg.eco_offset,
        )
        self._room_absent_since: float | None = None  # transient; restart->present
        # window: multiple=True, structural (data) -> re-read only on reload.
        self._windows: list[str] = as_entity_list(data.get(CONF_WINDOW_SENSOR))
        # AR-34: an unknown/corrupt category string must not throw in __init__; fall
        # back to the norm default rather than failing setup on a tuning value.
        try:
            self._category = Category(data.get(CONF_CATEGORY, "II"))
        except ValueError:
            self._category = Category("II")
        self._comfort_base: float = float(
            data.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE)
        )
        # ADR-0044 outcome scoring + ADR-0045 efficiency report (diagnostic only)
        self._outcome_stats = OutcomeStats()
        self._regq = RegulationQuality()  # ADR-0055 M1 control-quality (shadow)
        self._ca_last_mono: float | None = None  # real dt for the CA metric
        self._ref_offset: OffsetEstimate | None = None  # ADR-0056 actuator↔room
        self._ref_last_mono: float | None = None  # real dt for the offset EWMA
        self._tau_settle: TauSettle | None = None  # settle-based τ-confidence (T343)
        self._tau_last_mono: float | None = None  # real dt for the τ settle EWMA
        self._outcome_session = OutcomeSession()
        self._hdh_last_mono: float | None = None  # F9: real dt for HDH/outcome obs
        self._hdh = HdhSavings()
        self._hdh_cfg = HdhConfig(
            annual_kwh=float(data.get(CONF_ANNUAL_KWH, DEFAULT_ANNUAL_KWH)),
            price_eur_kwh=report_price_eur_kwh(
                data.get(CONF_PRICE_EUR_KWH),
                data.get(CONF_SOURCE_POLICY),
                gas=DEFAULT_PRICE_GAS_EUR_KWH,
                electric=DEFAULT_PRICE_EUR_KWH,
            ),
        )
        # ADR-0052: per-actuator dynamics profile (PI/MPC tuning by speed class).
        self._dynamics_override: str = data.get(CONF_DYNAMICS, DEFAULT_DYNAMICS)
        self._dynamics = DeviceDynamics.SLOW_HYDRONIC
        self._mpc_params = MpcParams()
        # ADR-0046 §8 (live): single-AC compressor guard — kill switch + timers
        # (option over the dynamics-profile default). Also re-read in apply_options.
        self._compressor_guard: str = str(
            data.get(CONF_COMPRESSOR_GUARD, COMPRESSOR_GUARD_AUTO)
        )
        _cmo = data.get(CONF_COMPRESSOR_MIN_OFF)
        self._comp_min_off_opt: float | None = float(_cmo) if _cmo is not None else None
        _cmh = data.get(CONF_COMPRESSOR_MODE_HOLD)
        self._comp_mode_hold_opt: float | None = (
            float(_cmh) if _cmh is not None else None
        )
        # ADR-0050/0051: humidity dry-active hysteresis state (shadow).
        self._dry_active = False
        # AR-32: warn once (not every 60 s tick) when the climate-band/humidity
        # block throws — its humidity action drives the *live* dry mode-nudge, so a
        # silent fall back to "idle" is worth surfacing the first time.
        self._hum_shadow_warned = False
        # ADR-0025/0034: optimal-start/stop anti-chatter latch — the prior tick's
        # engage state, so the planner holds preheat/coast until the room crosses
        # target instead of flapping at the boundary. Not persisted (re-latches).
        self._was_preheating = False
        self._was_coasting = False
        # ADR-0051: heat-day cooling raise (live, rate-limited, cooling-only).
        self._thermal_shock_delta = float(
            data.get(CONF_THERMAL_SHOCK_DELTA, DEFAULT_SHOCK_DELTA_K)
        )
        self._cool_hard_cap = float(data.get(CONF_COOL_HARD_CAP, DEFAULT_HARD_CAP_C))
        self._adaptive_cool_cfg = data.get(CONF_ADAPTIVE_COOL, DEFAULT_ADAPTIVE_COOL)
        self._cool_sp_eff_prev: float | None = None
        self._climate_mode: str = data.get(CONF_CLIMATE_MODE, "auto")
        self._cool_min_outdoor: float = float(
            data.get(CONF_COOL_MIN_OUTDOOR, DEFAULT_COOL_MIN_OUTDOOR_C)
        )
        self._heat_max_outdoor: float = float(
            data.get(CONF_HEAT_MAX_OUTDOOR, DEFAULT_HEAT_MAX_OUTDOOR_C)
        )
        # F4a: outdoor-lockout enable toggles. When off, None is passed into the
        # pure decide so that lockout edge is dropped (None already = "off" there).
        self._heat_lockout_enabled: bool = bool(
            data.get(CONF_HEAT_LOCKOUT_ENABLED, DEFAULT_HEAT_LOCKOUT_ENABLED)
        )
        self._cool_lockout_enabled: bool = bool(
            data.get(CONF_COOL_LOCKOUT_ENABLED, DEFAULT_COOL_LOCKOUT_ENABLED)
        )
        weight = float(data.get(CONF_COMFORT_WEIGHT, DEFAULT_COMFORT_WEIGHT))
        self._priority: float = weight / 100.0
        delta = float(data.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA))
        start = parse_hhmm(data.get(CONF_COMFORT_START))
        end = parse_hhmm(data.get(CONF_COMFORT_END))
        if start is not None and end is not None and delta > 0.0:
            self._schedule = ComfortSchedule.from_windows(
                [ComfortWindow(start, end)], delta
            )
        else:
            self._schedule = ComfortSchedule.always_comfort()
        self._optimal_start: bool = bool(data.get(CONF_OPTIMAL_START, True))
        # optimal-stop coasts to the lower comfort edge before window end; for
        # now coupled to optimal-start (predictive scheduling), splittable later.
        self._optimal_stop: bool = self._optimal_start
        self._weather: str | None = data.get(CONF_WEATHER)
        self._irradiance: str | None = data.get(CONF_IRRADIANCE)
        self._trv_ext_temp: str | None = data.get(CONF_TRV_EXTERNAL_TEMP)
        # P1-4a: adopt a device-side setpoint change (TRV wheel) as a manual hold.
        self._adopt_external_setpoint: bool = bool(
            data.get(CONF_ADOPT_EXTERNAL_SETPOINT, DEFAULT_ADOPT_EXTERNAL_SETPOINT)
        )
        # K2: adopt a device-side hvac_mode change (IR remote) as a manual mode-hold.
        self._adopt_external_mode: bool = bool(
            data.get(CONF_ADOPT_EXTERNAL_MODE, DEFAULT_ADOPT_EXTERNAL_MODE)
        )
        self._operative_input: bool = bool(data.get(CONF_OPERATIVE_INPUT, False))
        self._guards_resolved = False
        self._sched_entity: str | None = None
        self._fault_entity: str | None = None
        self._adaptive_mode_entity: str | None = None  # R1: device adaptive loop
        self._battery_entity: str | None = None
        self._ext_temp_auto: str | None = None
        self._sensor_select: str | None = None
        self._valve_entity: str | None = None
        self._valve_closing_steps: str | None = None
        self._valve_idle_steps: str | None = None
        self._forecast: list[tuple[float, float]] = []
        self._forecast_at: float | None = None
        self._forecast_fail_at: float | None = None  # F10: backoff after a failure

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value
        self._dirty = True

    def set_override(self, value: float | None, *, reason: str | None = None) -> None:
        # Validate at the trust boundary: reject non-finite, clamp to the safe
        # envelope so a bad manual setpoint can never reach the actuator (C2).
        was_active = self._override is not None  # Defekt-2: only a real hold ends
        self._override = sanitize_override(value, FROST_FLOOR_C, DEVICE_MAX_C)
        if self._override is not None:
            # ADR-0059 §4: announce the hold's expiry at set-time so the Card can
            # show "gilt bis …" the instant the user intervenes.
            set_at = dt_util.utcnow().timestamp()
            self._override_set_wall = set_at
            # Keep the pre-clamp requested value (was discarded): the Card shows
            # what the user asked for vs the norm-clamped hold that is applied.
            self._override_requested = float(value) if value is not None else None
            mins = self._minutes_to_switchpoint()
            self._override_expires_at = resolve_hold_expiry(
                policy=self._override_policy,
                set_at=set_at,
                timer_h=self._override_timer_h,
                max_h=self._override_max_h,
                minutes_to_switchpoint=mins,
            )
            # Was the announced expiry the switchpoint itself (not the timer
            # fallback / max_h cap)? -> _expire_timed_states reason accuracy (§1).
            self._override_expiry_is_switchpoint = (
                self._override_policy == OVERRIDE_POLICY_SCHEDULE
                and mins is not None
                and mins > 0
                and set_at + mins * 60.0 <= set_at + self._override_max_h * 3600.0
            )
            self._record_override_stat(self._override)  # §5 L1 (observe-only)
            # K3: record the hold's origin. A UI setpoint change defaults to
            # "ui_setpoint"; device adoption passes reason="device_adopt_setpoint".
            self._override_reason = reason or "ui_setpoint"
        else:
            # Clearing the hold: drop the whole lifecycle + announce the reason.
            self._override_set_wall = None
            self._override_expires_at = None
            self._override_requested = None
            self._override_expiry_is_switchpoint = False
            self._override_reason = None  # K3: no hold -> no origin
            # Defekt-2: fire only when a hold was actually active, so a
            # mode_change or a resume on a hold-less zone raises no false event.
            if value is None and was_active:  # explicit clear of an active hold
                self._fire_override_ended(reason or "user_resume")
        self._dirty = True

    def _set_mode_override(self, mode: str | None) -> None:
        """Adopt (or clear) a device-side hvac_mode as a manual mode-hold (K2).

        Shares the setpoint hold's lifecycle: if no hold is running yet it starts one
        (set-time expiry via ``resolve_hold_expiry`` + the zone policy). A setpoint
        hold already active this frame keeps its announced expiry -- the common case
        where an IR remote sends mode + temperature in one frame, adopted together.
        Cleared by ``_end_hold`` alongside the setpoint hold; never a safety layer.
        """
        self._mode_override = mode
        if mode is not None:
            self._override_reason = "device_adopt_mode"  # K3: origin of this hold
        if mode is not None and self._override_set_wall is None:
            set_at = dt_util.utcnow().timestamp()
            self._override_set_wall = set_at
            mins = self._minutes_to_switchpoint()
            self._override_expires_at = resolve_hold_expiry(
                policy=self._override_policy,
                set_at=set_at,
                timer_h=self._override_timer_h,
                max_h=self._override_max_h,
                minutes_to_switchpoint=mins,
            )
            self._override_expiry_is_switchpoint = (
                self._override_policy == OVERRIDE_POLICY_SCHEDULE
                and mins is not None
                and mins > 0
                and set_at + mins * 60.0 <= set_at + self._override_max_h * 3600.0
            )
        self._dirty = True

    def _read_override_options(self, data: dict[str, Any]) -> None:
        """Read the ADR-0059 hold/Boost tuning (hot-applyable; options>data)."""
        self._override_policy = str(
            data.get(CONF_OVERRIDE_POLICY, DEFAULT_OVERRIDE_POLICY)
        )
        self._override_timer_h = float(
            data.get(CONF_OVERRIDE_TIMER_H, DEFAULT_OVERRIDE_TIMER_H)
        )
        self._override_max_h = float(
            data.get(CONF_OVERRIDE_MAX_H, DEFAULT_OVERRIDE_MAX_H)
        )
        self._override_end_on_presence = bool(
            data.get(CONF_OVERRIDE_END_ON_PRESENCE, DEFAULT_OVERRIDE_END_ON_PRESENCE)
        )
        self._boost_duration_min = float(
            data.get(CONF_BOOST_DURATION_MIN, DEFAULT_BOOST_DURATION_MIN)
        )

    def set_climate_entity_id(self, entity_id: str) -> None:
        """Record the room's climate entity_id for the ended-event payload."""
        self._climate_entity_id = entity_id

    def _minutes_to_switchpoint(self) -> float | None:
        """Minutes to the next schedule switchpoint for a hold's expiry (§1).

        The nearer of the upcoming setback/comfort edges; None when there is no
        upcoming switchpoint (always-comfort) -> the timer fallback applies.

        This is the plain set-time switchpoint for the *announced* expiry. ADR-0059
        §3 (end the hold already at the optimal-start preheat-start, so the room is
        warm at comfort time) is resolved in the tick -- where the model/forecast
        preheat decision lives -- by ``hold_ends_at_preheat`` in ``_run_once``.
        """
        sched = self._schedule.state_at(self._local_minute())
        cands = [
            float(m)
            for m in (sched.minutes_to_setback, sched.minutes_to_comfort)
            if m is not None and m > 0
        ]
        return min(cands) if cands else None

    def _record_override_stat(self, clamped: float) -> None:
        """Append one L1 override observation (ADR-0059 §5; diagnostic only).

        A capped rolling log of user setpoint nudges: direction/delta vs the
        effective preset base, the schedule phase and the presence level at set
        time. AWAY / window-open nudges are skipped (not representative). No
        behaviour and no suggestions -- L2 (suggestions) is a v2 feature.
        """
        try:
            if (
                self._preset is OverrideMode.AWAY
                or self._last_presence_level == PresenceLevel.AWAY.value
                or self._last_window_open
            ):
                return
            base = mode_comfort_base(
                self._preset, self._comfort_base, self._override_cfg
            )
            delta = clamped - base
            phase = (
                "comfort"
                if self._schedule.state_at(self._local_minute()).is_comfort
                else "setback"
            )
            self._override_stats.append(
                {
                    "ts": dt_util.utcnow().timestamp(),
                    "direction": 1 if delta >= 0 else -1,
                    "delta": round(delta, 2),
                    "phase": phase,
                    "presence_level": self._last_presence_level,
                }
            )
            del self._override_stats[:-50]  # keep the last 50
        except Exception:  # noqa: BLE001 - a diagnostic stat must never break a set
            _LOGGER.debug("Poise override-stat record failed", exc_info=True)

    def _fire_override_ended(self, reason: str) -> None:
        """Announce a manual-hold end on the HA bus (ADR-0059 §4).

        Reasons: expired_timer | schedule_point | presence_change | user_resume |
        mode_change. The Card/automations subscribe to surface "Auto wieder aktiv".
        """
        payload: dict[str, Any] = {
            "zone": self.zone_name,
            "entry_id": self._entry_id,
            "reason": reason,
        }
        if self._climate_entity_id is not None:
            payload["entity_id"] = self._climate_entity_id
        self.hass.bus.async_fire("poise_override_ended", payload)

    def _end_hold(self, reason: str) -> None:
        """Tear down an active manual hold and announce why (ADR-0059 §1/§3)."""
        self._override = None
        self._mode_override = None  # K2: mode-hold shares the setpoint hold's end
        self._override_set_wall = None
        self._override_expires_at = None
        self._override_requested = None
        self._override_reason = None  # K3: origin cleared with the hold
        self._override_expiry_is_switchpoint = False
        self._dirty = True
        self._fire_override_ended(reason)

    def _expire_timed_states(self, home: bool | None) -> None:
        """Expire the timed Boost + manual hold on a tick (ADR-0059 §1/§2).

        A house-gate presence flip (either direction) since the last tick, or the
        hold's announced wall-clock expiry, ends a manual hold; a timed Boost
        restores the preset frozen at activation. Wall-clock throughout, so a
        state restored after a restart expires on real elapsed time (review C5).
        Runs under any active layer (window/frozen): the layer keeps regulating.
        """
        now = dt_util.utcnow().timestamp()
        presence_changed = (
            self._prev_home is not None and home is not None and home != self._prev_home
        )
        self._prev_home = home
        # timed Boost (§2): restore the frozen preset; then Boost is stateless.
        if self._boost_expires_at is not None and now >= self._boost_expires_at:
            self.set_preset(self._boost_prev_preset or OverrideMode.NONE)
        # manual hold (§1): value-independent expiry announced at set-time. K2: a
        # mode-hold (possibly without a setpoint hold) expires on the same triggers.
        if (
            self._override is not None or self._mode_override is not None
        ) and hold_expired(
            expires_at=self._override_expires_at,
            now=now,
            presence_changed=presence_changed,
            end_on_presence=self._override_end_on_presence,
        ):
            if presence_changed and self._override_end_on_presence:
                reason = "presence_change"
            elif self._override_expiry_is_switchpoint:
                # schedule policy AND the announced expiry was the switchpoint
                # (not the timer fallback / max_h cap) -> a true schedule end.
                reason = "schedule_point"
            else:
                # timer policy, or schedule with no switchpoint / max_h-capped.
                reason = "expired_timer"
            self._end_hold(reason)

    def set_climate_mode(self, mode: str) -> None:
        self._climate_mode = mode
        self._dirty = True

    def set_window_bypass(self, on: bool) -> None:
        self._window_bypass = on
        self._dirty = True

    def set_preset(self, mode: OverrideMode) -> None:
        if mode is OverrideMode.BOOST:
            # ADR-0059 §2: Boost is the one timed preset. Freeze the preset active
            # at activation (VT#1961) so expiry restores it, and announce the
            # expiry up front; re-pressing Boost re-arms from now without stacking
            # BOOST onto itself as the frozen preset.
            if self._preset is not OverrideMode.BOOST:
                self._boost_prev_preset = self._preset
            self._boost_expires_at = resolve_boost_expiry(
                set_at=dt_util.utcnow().timestamp(),
                boost_duration_min=self._boost_duration_min,
            )
        else:
            # Any stateless preset (Eco/Comfort/Away/None) drops the Boost timer.
            self._boost_expires_at = None
            self._boost_prev_preset = None
        self._preset = mode
        self._dirty = True

    @property
    def preset(self) -> OverrideMode:
        return self._preset

    @property
    def window_bypass(self) -> bool:
        return self._window_bypass

    @property
    def capability(self) -> tuple[bool, bool]:
        """(can_heat, can_cool) of the actuator (review P2 cooling modes)."""
        return self._capability()

    @property
    def via_device_id(self) -> tuple[str, str] | None:
        """Device-registry link from this zone to the system hub (M9).

        Returns the hub device identifier when a system entry is configured, so
        zones nest under the Poise System device; ``None`` (no link) otherwise.
        """
        for e in self.hass.config_entries.async_entries(DOMAIN):
            if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_SYSTEM:
                return (DOMAIN, e.entry_id)
        return None

    @property
    def climate_mode(self) -> str:
        return self._climate_mode

    async def async_bootstrap(self) -> None:
        """Restore the learned EKF before the first control tick (ADR-0007)."""
        # F17: re-adopt any repair issues this entry already owns so a coordinator
        # rebuilt after a crash/setup-retry can still clear them (otherwise they are
        # instance-local and orphaned once the condition resolves).
        try:
            _reg = ir.async_get(self.hass)
            self._active_issues = {
                iid
                for (dom, iid) in _reg.issues
                if dom == DOMAIN and iid.endswith(self._entry_id)
            }
        except Exception:  # noqa: BLE001 - registry read must never block setup
            pass
        # AR-20: keep store I/O and parsing failures separate. A transient load
        # error must NOT be mistaken for "no saved state" (which would silently
        # start fresh and overwrite the learned model on the next save) — fail setup
        # so HA retries. Only genuinely *corrupt* data is recovered below.
        try:
            data = await self._store.load()
        except Exception as err:  # noqa: BLE001 - transient I/O -> retry, don't wipe
            raise ConfigEntryNotReady(
                f"Poise {self.zone_name}: could not load persisted state"
            ) from err
        # Corruption recovery (narrowly scoped): restore the cheap user-intent keys
        # FIRST and each defensively, so a later failure in the heavier learned-model
        # from_dict parsing cannot lose enabled / preset / override / mode.
        try:
            if isinstance(data, dict) and "ekf" in data:
                self._enabled = bool(data.get("enabled", True))
                try:
                    self._preset = OverrideMode(data.get("preset", "none"))
                except ValueError:
                    self._preset = OverrideMode.NONE
                ov = data.get("override")
                self._override = float(ov) if isinstance(ov, (int, float)) else None
                # K2: restore a manual mode-hold (shares the setpoint hold lifecycle
                # restored below, so it expires on real elapsed wall-clock time).
                mov = data.get("mode_override")
                self._mode_override = mov if isinstance(mov, str) else None
                # K2: the shared hold lifecycle is active if EITHER a setpoint or a
                # mode hold was persisted (an ``off`` hold carries no setpoint).
                _hold_active = (
                    self._override is not None or self._mode_override is not None
                )
                # K3 (Inc 3): restore the hold's origin so "device"/"app" provenance
                # survives a restart (only while a hold actually lives).
                orr = data.get("override_reason")
                self._override_reason = (
                    orr if _hold_active and isinstance(orr, str) else None
                )
                # B5 (review v0.173.0-alpha §4.3): restore the adoption baseline, so
                # a device-side intervention made right after a restart is adopted
                # instead of classifying as ``no_baseline`` and being reverted by the
                # next write. Note this is NOT gated on an active hold: the baseline
                # describes the actuator, not the hold.
                #
                # Restoring ``_prev_device_*`` next to the command is what makes this
                # safe rather than a regression: on the first tick a device that
                # reports a constant offset to our command, or that simply never
                # moved while HA was down, then still classifies as
                # ``stable_offset`` / ``stable_prev`` instead of being grabbed as a
                # phantom hold (the F1/F2 class from the v0.171.0 RC review). Without
                # the prev-values the ``stable_*`` guard is skipped (None) and every
                # offset device would self-adopt on every restart.
                _lws = data.get("last_written_sp")
                self._last_written_sp = (
                    float(_lws) if isinstance(_lws, (int, float)) else None
                )
                _pds = data.get("prev_device_sp")
                self._prev_device_sp = (
                    float(_pds) if isinstance(_pds, (int, float)) else None
                )
                _lch = data.get("last_commanded_hvac")
                self._last_commanded_hvac = _lch if isinstance(_lch, str) else None
                _pdm = data.get("prev_device_mode")
                self._prev_device_mode = _pdm if isinstance(_pdm, str) else None
                # The echo windows are monotonic and process-local, so a persisted
                # stamp would be nonsense after a restart. Semantically no echo can
                # be in flight across one, so the window must read as long expired --
                # ``_stale`` guarantees ``(now - ts) >= echo_window`` on the first
                # tick, which is also the honest input for the ADR-0052 §4 nudge
                # throttle (no write happened recently). Only stamped where a
                # baseline actually exists, so ``no_baseline`` still wins otherwise.
                _stale = self._clock.monotonic() - SETPOINT_ADOPT_ECHO_WINDOW_S * 2.0
                if self._last_written_sp is not None:
                    self._last_sp_write_ts = _stale
                if self._last_commanded_hvac is not None:
                    self._last_hvac_cmd_ts = _stale
                # C5: restore the *wall-clock* set-time so the 2 h auto-revert
                # measures real elapsed time and a hold cannot outlive a restart.
                osw = data.get("override_set_wall")
                self._override_set_wall = (
                    float(osw)
                    if _hold_active and isinstance(osw, (int, float))
                    else None
                )
                # ADR-0059: restore the manual-hold + timed-Boost lifecycle on a
                # wall-clock basis, each defensively, so a hold/Boost survives a
                # restart and still expires on real elapsed time (review C5).
                orq = data.get("override_requested")
                self._override_requested = (
                    float(orq)
                    if self._override is not None and isinstance(orq, (int, float))
                    else None
                )
                # F13: ``override_policy`` (like the rest of the ADR-0059 hold/Boost
                # tuning) is a "hot-apply-fähig" config-entry OPTION, already correctly
                # read from options/data by ``_read_override_options`` in ``__init__``
                # -- restoring it from the persisted store here would silently revert
                # a user's option change on every restart. Deliberately not restored.
                oea = data.get("override_expires_at")
                self._override_expires_at = (
                    float(oea)
                    if _hold_active and isinstance(oea, (int, float))
                    else None
                )
                # ADR-0059 §1: restore the reason-accuracy flag (default False so
                # a pre-upgrade hold degrades to "expired_timer", never crashes).
                self._override_expiry_is_switchpoint = bool(
                    data.get("override_expiry_is_switchpoint", False)
                )
                # F7: a hold persisted by a pre-ADR-0059 build (or one that otherwise
                # lost its expiry) restores with ``_override_expires_at is None`` --
                # not "permanent" but simply never computed. Recompute it now the same
                # way a fresh override-set does, so the hold still expires on real
                # elapsed time instead of silently running forever after a restart.
                if (
                    _hold_active
                    and self._override_expires_at is None
                    and self._override_set_wall is not None
                ):
                    self._override_expires_at = resolve_hold_expiry(
                        policy=self._override_policy,
                        set_at=self._override_set_wall,
                        timer_h=self._override_timer_h,
                        max_h=self._override_max_h,
                        minutes_to_switchpoint=self._minutes_to_switchpoint(),
                    )
                try:
                    bpp = data.get("boost_prev_preset")
                    self._boost_prev_preset = (
                        OverrideMode(bpp) if isinstance(bpp, str) else None
                    )
                except ValueError:
                    self._boost_prev_preset = None
                bea = data.get("boost_expires_at")
                self._boost_expires_at = (
                    float(bea) if isinstance(bea, (int, float)) else None
                )
                ostats = data.get("override_stats")
                self._override_stats = (
                    [r for r in ostats if isinstance(r, dict)][-50:]
                    if isinstance(ostats, list)
                    else []
                )
                self._window_bypass = bool(data.get("window_bypass", False))
                cm = data.get("climate_mode")
                if isinstance(cm, str):
                    self._climate_mode = cm
                # AR-11: restore the actuation latch so the teardown-park gate
                # survives a restart.
                self._has_actuated = bool(data.get("has_actuated", False))
                # heavier learned-model parsing (a failure here must not lose the
                # user intent already restored above)
                self._ekf = ThermalEKF.from_dict(data["ekf"])
                if isinstance(data.get("trm"), dict):
                    self._trm_tracker = RunningMeanTracker.from_dict(data["trm"])
                if isinstance(data.get("seasonless"), dict):
                    self._seasonless = SeasonlessRate.from_dict(data["seasonless"])
                if isinstance(data.get("window_auto"), dict):
                    self._window_auto = WindowAutoState.from_dict(data["window_auto"])
                if isinstance(data.get("multi_lifecycle"), dict):
                    # ADR-0046 P2: restore the wall-clock lifecycle so a compressor
                    # min-off keeps counting across a restart (conservative on a
                    # skewed clock — a future stamp is clamped, never trusted long).
                    self._multi_lifecycle = _lifecycle.from_dict(
                        data["multi_lifecycle"], now=dt_util.utcnow().timestamp()
                    )
                if isinstance(data.get("outcome_stats"), dict):
                    self._outcome_stats = OutcomeStats.from_dict(data["outcome_stats"])
                if isinstance(data.get("regulation_quality"), dict):
                    self._regq = RegulationQuality.from_dict(data["regulation_quality"])
                if isinstance(data.get("ref_offset"), dict):
                    self._ref_offset = OffsetEstimate.from_dict(data["ref_offset"])
                if isinstance(data.get("tau_settle"), dict):
                    self._tau_settle = TauSettle.from_dict(data["tau_settle"])
                if isinstance(data.get("hdh_savings"), dict):
                    self._hdh = HdhSavings.from_dict(data["hdh_savings"])
                if isinstance(data.get("dry_active"), bool):
                    self._dry_active = data["dry_active"]  # R9: survive restart
            elif data is not None:
                self._ekf = ThermalEKF.from_dict(data)  # legacy: bare EKF dict
        except Exception:  # noqa: BLE001 - corrupt state must not block setup
            _LOGGER.exception("Poise: failed to restore learned model; starting fresh")
        # cold-start prior (ADR-0004): seed beta_h from the seasonless estimate
        # only while the EKF has never observed heating (e.g. new season); once it
        # learns from real heating it owns the parameter (never parallel, G6).
        if self._ekf.n_heating == 0 and self._seasonless.phase in (
            "learning",
            "mature",
        ):
            t_out = self._seasonless.mean_outdoor
            if t_out is not None:
                prior = self._seasonless.heat_rate_prior(
                    self._comfort_base, t_out, dt_util.now().toordinal()
                )
                if prior is not None:
                    self._ekf.seed_beta_h(prior)
        # F2: vet the configured external-temp number once, now that _active_issues
        # has been re-adopted (F17) so a stale issue can be cleared on recovery.
        await self._validate_configured_ext_temp()

    async def async_apply_options(self, entry: ConfigEntry) -> None:
        """Apply changed tuning options in place, without a reload (A10).

        Re-reads the volatile tuning fields (options over data) and updates the
        live state, so an options change does **not** discard the learned EKF
        transient that a full reload would. Structural inputs are not options.
        """
        # F14: the field mutations below race a concurrent tick (``_run_once``
        # reads many of these same attributes without any lock of its own) --
        # an options submit landing mid-tick could observe a torn mix of old and
        # new tuning. Take the same lock ``_async_update_data`` holds across a
        # tick to make this update atomic with respect to any tick. This MUST
        # NOT include ``async_request_refresh()`` below: ``asyncio.Lock`` is not
        # reentrant, and ``async_request_refresh`` awaits ``_async_update_data``,
        # which acquires this same lock -- held across that call, it would
        # deadlock immediately.
        async with self._lock:
            data = {**entry.data, **entry.options}
            self._read_override_options(data)  # ADR-0059 §1/§2 hot-apply
            self._comfort_base = float(
                data.get(CONF_COMFORT_BASE, DEFAULT_COMFORT_BASE)
            )
            self._hdh_cfg = HdhConfig(
                annual_kwh=float(data.get(CONF_ANNUAL_KWH, DEFAULT_ANNUAL_KWH)),
                price_eur_kwh=report_price_eur_kwh(
                    data.get(CONF_PRICE_EUR_KWH),
                    data.get(CONF_SOURCE_POLICY),
                    gas=DEFAULT_PRICE_GAS_EUR_KWH,
                    electric=DEFAULT_PRICE_EUR_KWH,
                ),
            )
            self._dynamics_override = data.get(CONF_DYNAMICS, DEFAULT_DYNAMICS)
            self._compressor_guard = str(
                data.get(CONF_COMPRESSOR_GUARD, COMPRESSOR_GUARD_AUTO)
            )
            _cmo = data.get(CONF_COMPRESSOR_MIN_OFF)
            self._comp_min_off_opt = float(_cmo) if _cmo is not None else None
            _cmh = data.get(CONF_COMPRESSOR_MODE_HOLD)
            self._comp_mode_hold_opt = float(_cmh) if _cmh is not None else None
            self._trace_enabled = bool(data.get(CONF_TRACE_RECORDING, False))
            self._presence_home_entities = as_entity_list(data.get(CONF_PRESENCE_HOME))
            self._occupancy_entities = as_entity_list(data.get(CONF_OCCUPANCY_SENSOR))
            self._presence_cfg = PresenceConfig(
                absence_after_min=float(
                    data.get(CONF_ABSENCE_AFTER_MIN, DEFAULT_ABSENCE_AFTER_MIN)
                ),
                eco_delta=self._override_cfg.eco_offset,
            )
            self._thermal_shock_delta = float(
                data.get(CONF_THERMAL_SHOCK_DELTA, DEFAULT_SHOCK_DELTA_K)
            )
            self._cool_hard_cap = float(
                data.get(CONF_COOL_HARD_CAP, DEFAULT_HARD_CAP_C)
            )
            self._adaptive_cool_cfg = data.get(
                CONF_ADAPTIVE_COOL, DEFAULT_ADAPTIVE_COOL
            )
            # F11: mirror the init guard (AR-34) so a corrupt category string cannot
            # throw in the hot-apply either; fall back to the norm default.
            try:
                self._category = Category(data.get(CONF_CATEGORY, "II"))
            except ValueError:
                self._category = Category("II")
            # AR-04: climate_mode is Store-owned — the climate entity sets it live
            # via set_climate_mode() and it is persisted in the payload. Do NOT
            # re-apply the (stale) options form value here; that clobbered the
            # live selection on every options submit (double ownership).
            self._cool_min_outdoor = float(
                data.get(CONF_COOL_MIN_OUTDOOR, DEFAULT_COOL_MIN_OUTDOOR_C)
            )
            self._heat_max_outdoor = float(
                data.get(CONF_HEAT_MAX_OUTDOOR, DEFAULT_HEAT_MAX_OUTDOOR_C)
            )
            # F4a: keep the lockout toggles in lockstep with the init read.
            self._heat_lockout_enabled = bool(
                data.get(CONF_HEAT_LOCKOUT_ENABLED, DEFAULT_HEAT_LOCKOUT_ENABLED)
            )
            self._cool_lockout_enabled = bool(
                data.get(CONF_COOL_LOCKOUT_ENABLED, DEFAULT_COOL_LOCKOUT_ENABLED)
            )
            self._priority = (
                float(data.get(CONF_COMFORT_WEIGHT, DEFAULT_COMFORT_WEIGHT)) / 100.0
            )
            delta = float(data.get(CONF_SETBACK_DELTA, DEFAULT_SETBACK_DELTA))
            start = parse_hhmm(data.get(CONF_COMFORT_START))
            end = parse_hhmm(data.get(CONF_COMFORT_END))
            if start is not None and end is not None and delta > 0.0:
                self._schedule = ComfortSchedule.from_windows(
                    [ComfortWindow(start, end)], delta
                )
            else:
                self._schedule = ComfortSchedule.always_comfort()
            self._optimal_start = bool(data.get(CONF_OPTIMAL_START, True))
            self._optimal_stop = self._optimal_start
            self._operative_input = bool(data.get(CONF_OPERATIVE_INPUT, False))
        await self.async_request_refresh()

    def attach_listeners(self, entry: ConfigEntry) -> None:
        """React promptly to input changes, not only on the 60 s tick (A6).

        Subscribes to the room sensor, the window sensor and the actuator; any
        change requests a refresh (coalesced by the coordinator's own debounce).
        The tick still owns learning/safety -- this only cuts *reaction* latency
        (notably an open window) from up to a tick to near-instant. Removed on
        unload via ``entry.async_on_unload``.
        """
        from homeassistant.core import Event
        from homeassistant.helpers.event import async_track_state_change_event

        watched = [e for e in (self._temp, *self._windows, self._actuator) if e]

        async def _on_change(event: Event) -> None:
            # H-1: skip pure attribute churn. A watched entity may emit many
            # state-change events per tick while the value Poise reacts to is
            # unchanged; refresh only on a real change (the state itself, or --
            # for the actuator -- its hvac_action attribute).
            new = event.data.get("new_state")
            if new is None:
                return
            old = event.data.get("old_state")
            if old is not None and old.state == new.state:
                old_action = old.attributes.get("hvac_action")
                new_action = new.attributes.get("hvac_action")
                is_actuator = event.data.get("entity_id") == self._actuator
                if not (is_actuator and old_action != new_action):
                    return
            await self.async_request_refresh()

        entry.async_on_unload(
            async_track_state_change_event(self.hass, watched, _on_change)
        )

    def _resolve_device_guards(self) -> None:
        """Find schedule/fault/battery entities on the actuator's device (once)."""
        if self._guards_resolved:
            return
        self._guards_resolved = True
        try:
            from homeassistant.helpers import entity_registry as er

            reg = er.async_get(self.hass)
            ent = reg.async_get(self._actuator)
            if ent is None or ent.device_id is None:
                return
            for e in er.async_entries_for_device(
                reg, ent.device_id, include_disabled_entities=False
            ):
                eid = e.entity_id
                # R1: a device-internal adaptive/smart-temperature loop is
                # orthogonal to the roles below and can be a switch. OR a select.,
                # so detect it independently of the elif chain (a select. would
                # otherwise be consumed by the sensor-select branch first).
                if (
                    self._adaptive_mode_entity is None
                    and looks_like_adaptive_mode_switch(eid)
                ):
                    self._adaptive_mode_entity = eid
                if self._sched_entity is None and looks_like_internal_schedule(eid):
                    self._sched_entity = eid
                elif self._fault_entity is None and looks_like_fault_alarm(eid):
                    self._fault_entity = eid
                elif (
                    self._battery_entity is None
                    and eid.startswith("sensor.")
                    and e.original_device_class == "battery"
                ):
                    self._battery_entity = eid
                elif self._ext_temp_auto is None and looks_like_external_temp_number(
                    eid, e.original_device_class
                ):
                    self._ext_temp_auto = eid
                elif self._sensor_select is None and eid.startswith("select."):
                    sel = self.hass.states.get(eid)
                    if is_external_sensor_select(
                        eid, sel.attributes.get("options") if sel else None
                    ):
                        self._sensor_select = eid
                elif (
                    self._valve_entity is None
                    and eid.startswith("number.")
                    and classify_number_entity(eid) == "valve"
                ):
                    self._valve_entity = eid
                elif looks_like_valve_steps(eid) == "closing":
                    self._valve_closing_steps = eid
                elif looks_like_valve_steps(eid) == "idle":
                    self._valve_idle_steps = eid
        except Exception:  # noqa: BLE001 - guard resolution must never break setup
            _LOGGER.debug("Poise: device-guard resolution failed", exc_info=True)

    def _issue(
        self,
        issue_id: str,
        active: bool,
        *,
        translation_key: str,
        placeholders: dict[str, str] | None = None,
    ) -> None:
        """Raise/clear a Home Assistant repair issue on transitions (ADR-0012)."""
        if active and issue_id not in self._active_issues:
            self._active_issues.add(issue_id)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=translation_key,
                translation_placeholders=placeholders or {},
            )
        elif not active and issue_id in self._active_issues:
            self._active_issues.discard(issue_id)
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    async def _validate_configured_ext_temp(self) -> None:
        """F2: vet the *configured* external-temp number once (not per tick).

        A value the user picked EXPLICITLY via CONF_TRV_EXTERNAL_TEMP is trusted
        unless it shows a POSITIVE non-temperature signal (a non-temperature
        device_class or unit, e.g. a valve's "%") — so a legitimately
        renamed/localised temperature input is NOT dropped on upgrade. On a real
        mismatch: stop feeding it AND hand the TRV's sensor source back to
        internal, or the device would keep regulating against a now-frozen
        external value (AR-12); then raise a repair issue. When plausible or
        unset, clear it. A registry miss must never block setup.
        """
        issue_id = f"external_temp_implausible_{self._entry_id}"
        entity_id = self._trv_ext_temp
        if not entity_id:
            self._issue(issue_id, False, translation_key="external_temp_implausible")
            return
        try:
            from homeassistant.helpers import entity_registry as er

            reg = er.async_get(self.hass)
            ent = reg.async_get(entity_id)
            device_class: str | None = None
            unit: str | None = None
            if ent is not None:
                device_class = ent.device_class or ent.original_device_class
                unit = ent.unit_of_measurement
            st = self.hass.states.get(entity_id)
            if st is not None:
                device_class = device_class or st.attributes.get("device_class")
                unit = unit or st.attributes.get("unit_of_measurement")
            implausible = ext_temp_number_is_implausible(entity_id, device_class, unit)
        except Exception:  # noqa: BLE001 - a registry miss must not block setup
            _LOGGER.debug(
                "Poise: external-temp validation failed for %s",
                entity_id,
                exc_info=True,
            )
            return
        if not implausible:
            self._issue(issue_id, False, translation_key="external_temp_implausible")
            return
        # Implausible: never feed it, and hand the TRV sensor source back to
        # internal so the device does not regulate against a frozen value (AR-12).
        self._trv_ext_temp = None
        try:
            from . import _restore_trv_internal

            await _restore_trv_internal(self.hass, self._actuator)
        except Exception:  # noqa: BLE001 - best-effort restore must not block setup
            _LOGGER.debug(
                "Poise: TRV sensor-source restore after ext-temp reject failed",
                exc_info=True,
            )
        self._issue(
            issue_id,
            True,
            translation_key="external_temp_implausible",
            placeholders={"entity": entity_id, "name": self.zone_name},
        )

    def _read(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        return _num(self.hass.states.get(entity_id))

    def _sensor_age(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        # last_changed (the value-change time, per the watchdog contract): a
        # dead/stuck sensor that keeps re-publishing the SAME value still bumps
        # last_updated, so only last_changed detects "available but frozen".
        # "Sensor lost / unavailable" is handled separately by the ingestion
        # degradation ladder. Threshold is long (hours) so a legitimately stable
        # room never false-positives (best-of: VTherm/BT, review F1).
        return sensor_age_seconds(dt_util.utcnow(), state.last_changed)

    def _local_minute(self) -> int:
        now = dt_util.now()
        return int(now.hour * 60 + now.minute)

    def _window_open(self) -> tuple[bool, bool]:
        """OR across the picker: any configured contact reporting "on" = open.

        Returns ``(sensor_open, sensor_unavailable)``. F4a / ADR-0041 §5: a
        contact that drops off (``unavailable``/``unknown``) previously read
        as indistinguishable from "closed" here (neither is ``== "on"``), so a
        window sensor that had merely lost battery/network silently held the
        zone in full heating with no signal and no warning. The failsafe is
        "heizen wie ohne Sensor" -- flag it (repair issue, at the call site)
        and let the caller fall back to slope/auto-detection instead of
        trusting stale/missing "closed" data. A confirmed "on" from any OTHER
        still-working contact is trusted regardless (real positive evidence
        beats a sibling sensor's dropout), so this never early-returns.
        """
        open_found = False
        unavailable = False
        for entity_id in self._windows:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unavailable", "unknown"):
                unavailable = True
                continue
            if state.state == "on":
                open_found = True
        return open_found, unavailable

    def _capability(self) -> tuple[bool, bool]:
        act = self.hass.states.get(self._actuator)
        modes = act.attributes.get("hvac_modes") if act else None
        if modes:
            return climate_capability([str(m) for m in modes])
        return True, False  # default: assume a heat-only TRV

    def _device_max(self) -> float:
        act = self.hass.states.get(self._actuator)
        if act is not None:
            mx = act.attributes.get("max_temp")
            if isinstance(mx, (int, float)):
                return float(mx)
        return DEVICE_MAX_C

    def _device_min(self) -> float | None:
        """The actuator's own ``min_temp`` (a physical write floor), if known.

        Returns ``None`` when absent/non-numeric so resolve_write_target skips
        the SAFETY floor clamp entirely (review P3-1).
        """
        act = self.hass.states.get(self._actuator)
        if act is not None:
            mn = act.attributes.get("min_temp")
            if isinstance(mn, (int, float)):
                return float(mn)
        return None

    def _sun_elevation(self) -> float | None:
        sun = self.hass.states.get("sun.sun")
        if sun is None:
            return None
        elev = sun.attributes.get("elevation")
        return float(elev) if isinstance(elev, (int, float)) else None

    async def _forecast_outdoor(self, horizon_min: float, fallback: float) -> float:
        """Mean forecast outdoor temp over the preheat window (ADR-0025).

        Refreshes the cached hourly forecast at most every FORECAST_TTL_S. A
        missing weather entity degrades to ``fallback`` (the constant current
        outdoor), so optimal-start never depends on a forecast.

        F10: a fetch failure no longer hardcodes ``fallback`` -- it falls through
        to ``mean_forecast_outdoor`` on the last successfully cached samples (if
        any), which is normally a better preheat estimate than a flat constant,
        and degrades to ``fallback`` itself only once that cache is empty/expired
        beyond use. A failure also starts a FORECAST_TTL_S backoff
        (``_forecast_fail_at``) before the next retry, instead of re-attempting
        the (possibly slow/rate-limited) service call on every single tick for as
        long as the weather integration stays down.
        """
        if not self._weather:
            return fallback
        now = self._clock.monotonic()
        stale = self._forecast_at is None or (now - self._forecast_at) >= FORECAST_TTL_S
        backed_off = (
            self._forecast_fail_at is not None
            and (now - self._forecast_fail_at) < FORECAST_TTL_S
        )
        if stale and not backed_off:
            try:
                async with asyncio.timeout(_WEATHER_CALL_TIMEOUT_S):
                    resp = await self.hass.services.async_call(
                        "weather",
                        "get_forecasts",
                        {"type": "hourly", "entity_id": self._weather},
                        blocking=True,
                        return_response=True,
                    )
                self._forecast = forecast_samples_from_response(
                    resp, self._weather, dt_util.utcnow()
                )
                self._forecast_at = now
                self._forecast_fail_at = None
            except Exception:  # noqa: BLE001 - forecast must never break the tick
                _LOGGER.debug("Poise: weather forecast unavailable; using stale cache")
                self._forecast_fail_at = now
        return mean_forecast_outdoor(self._forecast, horizon_min, fallback)

    def _learn(self, room: float, t_out: float) -> None:
        """Passive EKF observer; paused on open window (ADR-0002/0024)."""
        now = self._clock.monotonic()
        try:
            if self._last_mono is not None:
                dt_h = (now - self._last_mono) / 3600.0
                if 0.0 < dt_h < 1.0:
                    self._ekf.predict(
                        dt_h,
                        t_out=t_out,
                        u_h=self._last_u_h,
                        u_c=self._last_u_c,
                        q_solar=self._last_q_solar,
                    )
                    self._ekf.update(room)
        except Exception:  # noqa: BLE001 - learning must never break control
            _LOGGER.exception("Poise: EKF observer step failed")
        finally:
            self._last_mono = now

    def _observe_window_auto(
        self,
        room: float,
        t_out: float,
        *,
        cooling: bool = False,
        sensor_unavailable: bool = False,
    ) -> None:
        """Feed the sensorless slope detector (ADR-0041).

        Skipped only while a configured window sensor is actually reporting
        (decision §2: "Sensor schlägt Heuristik (Exklusivität, wie VTherm)" --
        deliberate, not amended by the stage-2 Nachtrag, which documents the
        *combination* wiring of ``effective_window_open`` without retracting
        the exclusivity policy). F4b: a configured-but-*unavailable* sensor is
        the one documented exception -- §5's failsafe ("heizen wie ohne
        Sensor") requires the slope detector to actually be live to fall back
        to, so it keeps stepping (instead of staying cold forever, as the
        previous unconditional ``if self._windows: return`` did) whenever the
        sensor itself cannot currently report. The healthy-sensor case is a
        bare skip here -- the call site (just before ``effective_window_open``)
        already force-resets ``self._window_auto``/the ``_wa_*`` anchors to a
        clean, non-latched state the moment the sensor is healthy again, in the
        SAME tick, before this function would otherwise get a chance to.
        Observes every tick — a window can open whether or not we heat. The open
        threshold is adapted to the learned tau once the model is identified
        (steeper natural cooling -> higher threshold), else the fixed default.
        """
        if self._windows and not sensor_unavailable:
            return
        now = self._clock.monotonic()
        cfg = self._window_auto_cfg
        if self._ekf.identified:
            self._wa_open_threshold = adaptive_open_threshold(
                self._ekf.tau_hours, room, t_out, cfg
            )
            cfg = replace(cfg, open_threshold=self._wa_open_threshold)
        else:
            self._wa_open_threshold = cfg.open_threshold
        # V6: measure the slope over the interval since the room last moved a full
        # sensor quantum, not per tick — a single 0.1 K quantization step on a short
        # tick would otherwise read as a steep drop and falsely open the window.
        slope, self._wa_ref_room, self._wa_ref_mono = quantized_slope(
            room=room,
            ref_room=self._wa_ref_room,
            ref_s=self._wa_ref_mono,
            now_s=now,
            min_step=cfg.min_step,
        )
        if self._wa_prev_mono is not None:
            dt_min = (now - self._wa_prev_mono) / 60.0
            if 0.0 < dt_min < 60.0:
                # active cooling explains a drop -> neutralise the slope so it
                # cannot false-open (and still closes an earlier detection).
                self._window_auto = step_window_auto(
                    self._window_auto, 0.0 if cooling else slope, dt_min, cfg
                )
        self._wa_prev_mono = now

    def _observe_seasonless(self, room: float, t_out: float) -> None:
        """Record a normalised heat-up rate while heating (shadow, ADR-0004/0026).

        The rate is sampled with an anchored accumulator (``heatup_rate``) instead
        of a per-tick delta: on a quantized sensor a per-tick ``(room-prev)/dt``
        with the ``rate>0`` filter keeps only the quantum up-crossings and biases
        the pooled rate — hence the beta_h cold-start seed — high. The accumulator
        divides a real accumulated rise by the full elapsed interval (flat ticks
        included), which is unbiased regardless of the sensor quantum.
        """
        now = self._clock.monotonic()
        heating = self._last_target is not None and self._last_u_h > 0.5
        rate = sample_heatup_rate(
            self._heatup_acc, heating=heating, room=room, mono=now
        )
        if rate is not None and rate > 0.0 and self._last_target is not None:
            self._seasonless.observe(
                rate, self._last_target, t_out, dt_util.now().toordinal()
            )
        self._prev_room = room
        self._prev_room_mono = now

    async def _maybe_record_trace(
        self,
        data: dict[str, Any],
        *,
        room: float,
        t_out: float,
        rh: float | None,
        t_rm: float | None,
        now: float,
    ) -> None:
        """Append this tick to the opt-in field trace (ADR-0011 golden-file
        replay). Best-effort pure observation (ADR-0026): the EKF drive inputs +
        model snapshot make it replay-sufficient, and any failure is swallowed so
        trace capture can never disturb control."""
        if not self._trace_enabled:
            return
        try:
            if self._trace_recorder is None:
                path = self.hass.config.path(
                    "poise_traces", f"{self._trace_slug}.jsonl"
                )
                self._trace_recorder = TraceRecorder(
                    self.hass, path, DEFAULT_TRACE_MAX_BYTES
                )
            ekf = self._ekf
            snapshot = ModelSnapshot(
                alpha=ekf.x[1],
                beta_h=ekf.x[2],
                beta_c=ekf.x[3],
                beta_s=ekf.x[4],
                beta_o=ekf.x[5],
                t_std=ekf.temperature_std,
                n_idle=ekf.n_idle,
                n_heating=ekf.n_heating,
                n_cooling=ekf.n_cooling,
                identified=ekf.identified,
            )
            record = build_record(
                data,
                snapshot,
                ts=dt_util.utcnow().timestamp(),
                mono=now,
                room=room,
                t_out=t_out,
                u_h=self._last_u_h,
                u_c=self._last_u_c,
                q_solar=self._last_q_solar,
                rh=rh,
                t_rm=t_rm,
            )
            await self._trace_recorder.append(record.to_json_line())
        except Exception:  # noqa: BLE001 - trace capture must never break the tick
            _LOGGER.debug("Poise trace capture failed", exc_info=True)

    async def _notify_failure(self, failed: bool) -> None:
        """Surface a persistent heating failure as a translated repair issue.

        P2-8: replaces the former English persistent_notification with a repair
        issue (raised while ``failed``, cleared when it recovers) so the message
        is localised via ``translations/*`` like every other Poise diagnostic.
        """
        self._issue(
            f"heating_failure_{self._entry_id}",
            failed,
            translation_key="heating_failure",
            placeholders={"zone": self.zone_name},
        )

    def _own_ctx(self) -> Context:
        """A fresh HA ``Context`` for one of Poise's own actuator service calls.

        Its id is remembered (bounded) so the next tick can identify the resulting
        state change as our own write's echo -- including a device re-quantise /
        min-max clamp a push integration reports under this context -- and re-baseline
        instead of mis-adopting it as an external change (V2, analysis 2026-07-14).
        """
        ctx = Context()
        self._own_write_ctx_ids.append(ctx.id)
        return ctx

    def _save_payload(self) -> dict[str, Any]:
        return {
            "ekf": self._ekf.to_dict(),
            "trm": self._trm_tracker.to_dict(),
            "seasonless": self._seasonless.to_dict(),
            "window_auto": self._window_auto.to_dict(),
            "multi_lifecycle": _lifecycle.to_dict(self._multi_lifecycle),
            "outcome_stats": self._outcome_stats.to_dict(),
            "regulation_quality": self._regq.to_dict(),
            "ref_offset": (
                self._ref_offset.to_dict() if self._ref_offset is not None else None
            ),
            "tau_settle": (
                self._tau_settle.to_dict() if self._tau_settle is not None else None
            ),
            "hdh_savings": self._hdh.to_dict(),
            # R9: the humidity dry-active latch is otherwise runtime-only, so a
            # restart between 55-60 %RH drops the room out of dry mode until RH
            # re-crosses 60 % (a behaviour jump, dual_smart #553). ``_window_open_
            # since`` is deliberately NOT persisted here: it is a monotonic stamp
            # (resets on restart) and would need a wall-clock rework to survive.
            "dry_active": self._dry_active,
            "window_bypass": self._window_bypass,
            "preset": self._preset.value,
            "enabled": self._enabled,
            "override": self._override,
            "mode_override": self._mode_override,  # K2: manual mode-hold
            "override_set_wall": self._override_set_wall,
            # ADR-0059 manual-hold + timed-Boost lifecycle (wall-clock; review C5).
            "override_requested": self._override_requested,
            "override_policy": self._override_policy,
            "override_expires_at": self._override_expires_at,
            "override_expiry_is_switchpoint": self._override_expiry_is_switchpoint,
            "boost_expires_at": self._boost_expires_at,
            "boost_prev_preset": (
                self._boost_prev_preset.value
                if self._boost_prev_preset is not None
                else None
            ),
            "override_stats": self._override_stats,
            "override_reason": self._override_reason,  # K3: persisted hold origin
            # B5 (review v0.173.0-alpha §4.3): the adoption baseline is otherwise
            # runtime-only, so the first device-side intervention after a restart has
            # nothing to compare against and is silently reverted. Persist BOTH what
            # we last commanded and what the device last reported -- the reported
            # value is what makes the restored baseline safe (see the restore side).
            # Timestamps are deliberately left out: they are monotonic and
            # process-local, hence meaningless across a restart.
            "last_written_sp": self._last_written_sp,
            "prev_device_sp": self._prev_device_sp,
            "last_commanded_hvac": self._last_commanded_hvac,
            "prev_device_mode": self._prev_device_mode,
            "climate_mode": self._climate_mode,
            "has_actuated": self._has_actuated,  # AR-11: teardown-park gate
        }

    async def _maybe_save(self) -> None:
        self._save_counter += 1
        if self._save_counter >= EKF_SAVE_EVERY_TICKS or self._dirty:
            self._save_counter = 0
            try:
                await self._store.save(self._save_payload())
                # F6: only clear the dirty flag on a SUCCESSFUL save. Clearing it
                # unconditionally (as before) marked a fresh override/preset/enabled
                # change as "persisted" even when the write itself failed, so a
                # crash/restart in that window silently lost the user's intent
                # until the next periodic (30-tick) save happened to succeed.
                self._dirty = False
                self._note_save_result(ok=True)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Poise: failed to persist learned model")
                self._note_save_result(ok=False)

    def _mark_actuated(self) -> None:
        """Set the AR-11 teardown-park gate, persisting the flip (F16).

        A bare ``self._has_actuated = True`` never set ``_dirty``, so a restart
        shortly after the FIRST actuation of a run (e.g. mid a sensor outage,
        where the periodic 30-tick save is not running either) could still
        restore ``has_actuated=False`` — teardown then would not park an
        actuator Poise had, in fact, already commanded. Only the first flip
        needs to persist; repeating it is a harmless no-op write skip.
        """
        if not self._has_actuated:
            self._dirty = True
        self._has_actuated = True

    def _note_save_result(self, *, ok: bool) -> None:
        """Escalate a persistently failing store to a repair issue (F24).

        A single transient failure is only logged; N in a row means the store is
        broken and the learned model is silently not being persisted — surface it.
        """
        self._save_failures = 0 if ok else self._save_failures + 1
        self._issue(
            f"persistence_failed_{self._entry_id}",
            self._save_failures >= 5,  # after 5 consecutive failures
            translation_key="persistence_failed",
        )

    async def async_persist_and_cleanup(self) -> None:
        """Final save + repair-issue/notification cleanup on unload (review P1.3).

        AR-28: the final save runs under the same lock as the tick / stop flush.
        AR-21: if that save fails we KEEP (and raise) the ``persistence_failed``
        issue instead of clearing it — a failed unload save can lose the last
        learning window, so this is honest, not an unconditional "no learning loss".
        """
        saved = False
        async with self._lock:
            try:
                await self._store.save(self._save_payload())
                saved = True
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Poise: final save on unload failed")
        keep: set[str] = set()
        if not saved:
            # Surface + retain the persistence issue; it is re-adopted (F17) on the
            # next setup and cleared once a save finally succeeds.
            pid = f"persistence_failed_{self._entry_id}"
            self._issue(pid, True, translation_key="persistence_failed")
            keep.add(pid)
        for issue_id in list(self._active_issues):
            if issue_id in keep:
                continue
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            self._active_issues.discard(issue_id)

    def structural_unchanged(self, entry: ConfigEntry) -> bool:
        """True if only tuning options changed since setup (F14).

        A change to ``entry.data`` means a reconfigure is reloading the entry, so
        the in-place options hot-apply must NOT run on this soon-to-be-discarded
        coordinator (the reload rebuilds it with the new data anyway).
        """
        return dict(entry.data) == self._data_snapshot

    async def async_flush_on_stop(self, _event: Any) -> None:
        """Persist learned state on HA shutdown (F7 / ADR-0007 flush).

        HA does not call async_unload_entry on a normal stop, so without this the
        last <=30 ticks of EKF learning and any pending user intent are lost.
        """
        async with self._lock:
            try:
                await self._store.save(self._save_payload())
            except Exception:  # noqa: BLE001 - shutdown save is best-effort
                _LOGGER.exception("Poise: save on HA stop failed")

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            _t0 = time.perf_counter()
            # F12: a tick that raises out of ``_run_once`` was previously invisible
            # beyond DataUpdateCoordinator's own generic "update failed" log/entity
            # unavailability -- no Poise-specific signal, no persistence, nothing to
            # distinguish a one-off transient blip from a zone stuck failing every
            # tick. Track consecutive failures the same way ``_note_save_result``
            # already does for the store, and surface a repair issue after N in a
            # row; the exception itself is always re-raised unchanged so
            # DataUpdateCoordinator's own failure handling is untouched.
            try:
                data = await self._run_once()
            except Exception:
                self._tick_failures += 1
                self._issue(
                    f"tick_failing_{self._entry_id}",
                    self._tick_failures >= 3,  # after 3 consecutive failures
                    translation_key="tick_failing",
                )
                raise
            self._tick_failures = 0
            self._issue(
                f"tick_failing_{self._entry_id}", False, translation_key="tick_failing"
            )
            # ADR-0020: the tick's wall-time (it holds the lock across the forecast
            # and any trace append) against the budget — an early scaling signal.
            self._tick_budget.observe((time.perf_counter() - _t0) * 1000.0)
            # Attach the timing diagnostics to a normal payload only; the minimal
            # degraded/safe-state dicts ({"available": False, ...}) stay a pristine
            # contract that the entity availability gate and its tests rely on.
            if data.get("available", True) is not False:
                data["tick_ms"] = round(self._tick_budget.last_ms, 1)
                data["tick_ms_ewma"] = round(self._tick_budget.ewma_ms, 1)
                data["tick_ms_max"] = round(self._tick_budget.max_ms, 1)
                data["tick_over_budget"] = self._tick_budget.over_budget
            return data

    def _emit_health_issues(self) -> tuple[bool, bool, bool, bool]:
        """Raise/clear device-health repair issues; return the status flags."""
        # F2: an actuator that dropped off the network (Zigbee/MQTT gone) keeps a
        # registered State object with state=="unavailable" -- states.get(...) is
        # None only for a never-registered/removed entity, which is the rarer
        # case. Checking only the None case missed the common real-world failure
        # (device offline), so no repair issue ever fired for it.
        _act_health = self.hass.states.get(self._actuator)
        self._issue(
            f"actuator_unavailable_{self._entry_id}",
            _act_health is None or _act_health.state == "unavailable",
            translation_key="actuator_unavailable",
            placeholders={"entity": self._actuator},
        )
        frozen = is_frozen(self._sensor_age(self._temp), SENSOR_FREEZE_AFTER_S)
        self._issue(
            f"sensor_frozen_{self._entry_id}",
            frozen,
            translation_key="sensor_frozen",
            placeholders={"entity": self._temp},
        )
        self._resolve_device_guards()
        sched_active = fault_active = False
        if self._sched_entity:
            st = self.hass.states.get(self._sched_entity)
            sched_active = st is not None and st.state == "on"
            self._issue(
                f"device_schedule_{self._entry_id}",
                sched_active,
                translation_key="device_schedule",
                placeholders={"entity": self._sched_entity},
            )
        if self._adaptive_mode_entity:
            st = self.hass.states.get(self._adaptive_mode_entity)
            # R1: a switch reads "on"; a select reads the active option name.
            # Treat any adaptive/smart-named option (or a plain "on") as the loop
            # being active -- an off/manual state clears the issue.
            active = st is not None and (
                st.state == "on"
                or "adaptive" in st.state.lower()
                or "smart" in st.state.lower()
            )
            self._issue(
                f"adaptive_mode_{self._entry_id}",
                active,
                translation_key="adaptive_mode_active",
                placeholders={"entity": self._adaptive_mode_entity},
            )
        if self._fault_entity:
            st = self.hass.states.get(self._fault_entity)
            fault_active = st is not None and st.state == "on"
            self._issue(
                f"device_alarm_{self._entry_id}",
                fault_active,
                translation_key="device_alarm",
                placeholders={"entity": self._fault_entity},
            )
        if self._battery_entity:
            self._issue(
                f"low_battery_{self._entry_id}",
                is_low_battery(self._read(self._battery_entity), LOW_BATTERY_PCT),
                translation_key="low_battery",
                placeholders={"entity": self._battery_entity},
            )
        heat_source_suspect = sensor_at_heat_source(
            self._ekf.tau_hours,
            self._ekf.identified,
            min_plausible_tau_h=MIN_PLAUSIBLE_TAU_H,
        )
        self._issue(
            f"sensor_at_heat_source_{self._entry_id}",
            heat_source_suspect,
            translation_key="sensor_at_heat_source",
            placeholders={"entity": self._temp},
        )
        return frozen, sched_active, fault_active, heat_source_suspect

    async def _write_unavailable_safe_state(self) -> None:
        """Command the frost/mould floor after a sustained room-sensor loss.

        A heat-capable actuator degrades to the health floor in heat (frost
        protection held by its own sensor -- fail toward warmth); a cool-only
        actuator is commanded off (it must not cool the room to the floor).
        Mirrors the frozen-sensor safe state (C3/Ü3) for a fully unavailable
        sensor. The floor is clamped up to the device ``min_temp`` so a high-min
        AC does not thrash on an echo it cannot honour. Best-effort + idempotent;
        a failure must never break the tick (review #7).
        """
        act = self.hass.states.get(self._actuator)
        modes = (
            [str(m) for m in (act.attributes.get("hvac_modes") or [])] if act else []
        )
        # F1: decide mode + setpoint together (pure), so a device in cool/auto/off
        # actually receives the set_hvac_mode('heat') it needs — the old check only
        # skipped a re-write when state=='heat', and never emitted the mode nudge for
        # a multi-mode device (it would keep cooling toward the floor). Mode and
        # setpoint writes are independent and each idempotent.
        plan = resolve_safe_state(
            hvac_modes=modes,
            device_state=act.state if act is not None else None,
            device_setpoint=_num_attr(act, "temperature"),
            device_min=_num_attr(act, "min_temp"),
            floor=FROST_FLOOR_C,
        )
        if plan is None:
            return  # already in the safe state -> no re-write (idempotent)
        try:
            if plan.write_mode:
                await self.hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {"entity_id": self._actuator, "hvac_mode": plan.hvac_mode},
                    blocking=False,
                )
                self._last_written_mode = plan.hvac_mode  # only after a real nudge
                # K2: our own safe-state mode is never a user change (mode echo).
                self._last_commanded_hvac = plan.hvac_mode
            if plan.write_setpoint and plan.setpoint is not None:
                await actuator_mod.write(
                    self.hass,
                    ActuatorCommand(
                        actuator_id=self._actuator,
                        path=ActuatorPath.SETPOINT,
                        value=plan.setpoint,
                        hvac_mode=plan.hvac_mode,
                        reason="unavailable_safe",
                    ),
                )
                self._last_target = plan.setpoint
                # B2 (review v0.168.0): clear the adoption baseline so our own
                # safe-state setpoint is never re-read as a user hold on recovery.
                self._last_written_sp = None
                self._mark_actuated()  # AR-11 (+F16: persist the flip)
        except Exception:  # noqa: BLE001 - safe-state write must never kill the tick
            _LOGGER.exception("Poise %s: unavailable-safe write failed", self.zone_name)

    async def _run_once(self) -> dict[str, Any]:
        air = self._read(self._temp)
        self._issue(
            f"sensor_unavailable_{self._entry_id}",
            air is None,
            translation_key="sensor_unavailable",
            placeholders={"entity": self._temp},
        )
        if air is None:
            # Review F5: a fully unavailable room sensor is at least as untrustworthy
            # as an open window or a frozen reading, so it must drop the same
            # learning/window-auto anchors as the V5 pause branch below -- otherwise
            # the eventual reconnect re-anchors ``_last_mono``/``_prev_room_mono``
            # across the whole outage and the EKF integrates a real-looking dt over
            # an interval it never actually observed (ADR-0012/0024). The slope
            # detector's own reference point is reset too (``_wa_ref_*``,
            # ``_wa_prev_mono``): letting it survive an outage would let the next
            # good sample compute a rate/dt across the *sensor* gap rather than
            # real room movement, which is exactly the false-open risk the V6
            # quantized-slope anchor was built to avoid.
            self._last_mono = None
            self._prev_room = None
            self._prev_room_mono = None
            self._heatup_acc.reset()
            self._wa_ref_room = None
            self._wa_ref_mono = None
            self._wa_prev_mono = None
            # F5: a user intent set via the switch/select (enabled / preset / mode)
            # while the room sensor is down must still be persisted — the normal
            # save sits after this early return, so flush a pending change here too.
            if self._dirty:
                await self._maybe_save()
            now_mono = self._clock.monotonic()
            if self._unavailable_since is None:
                self._unavailable_since = now_mono
            if not self._unavailable_logged:
                _LOGGER.warning(
                    "Poise %s: room temperature sensor %s is unavailable; "
                    "holding the entity in its last state until it returns",
                    self.zone_name,
                    self._temp,
                )
                self._unavailable_logged = True
            # review #7: a sustained loss must not hold a stale comfort setpoint
            # indefinitely (critical in external-feed mode). After the timeout,
            # degrade to the frost/mould floor -- the same safe state as a frozen
            # sensor (fail toward warmth).
            if unavailable_safe_engaged(
                now_mono - self._unavailable_since, UNAVAILABLE_SAFE_AFTER_S
            ):
                await self._write_unavailable_safe_state()
                return {"available": False, "unavailable_safe": True}
            return {"available": False}
        self._unavailable_since = None
        if self._unavailable_logged:
            _LOGGER.info(
                "Poise %s: room temperature sensor %s is back; resuming control",
                self.zone_name,
                self._temp,
            )
            self._unavailable_logged = False
        frozen, sched_active, fault_active, heat_source_suspect = (
            self._emit_health_issues()
        )
        now = self._clock.monotonic()
        # F3: feed the last known-good room value so an implausible raw sample
        # (Zigbee glitch, a misread °F number, ...) degrades to that recent real
        # reading ("derived") instead of skipping straight past it to the
        # hardcoded 20.0 °C default -- the ladder's middle rung was dead code
        # without this (ADR-0012 degradation ladder).
        reading = ingest_temperature(
            [RawSample(air, now)], now=now, last_good=self._prev_room
        )
        room = reading.value
        # F3: a DEFAULT-source reading means there is no trustworthy room value
        # AT ALL (an implausible raw sample AND no prior good reading to derive
        # from) -- treat it exactly like a frozen/stale sensor (fail toward
        # warmth): control degrades to the health floor and learning pauses,
        # instead of regulating on -- and teaching the EKF -- a fabricated
        # constant (measured/estimated boundary, ADR-0012/0026).
        frozen = frozen or reading.source is Source.DEFAULT
        t_out = self._read(self._outdoor)
        # internal EN 16798-1 running mean, used when no external T_rm sensor.
        if t_out is not None:
            self._trm_tracker.observe(t_out, dt_util.now().toordinal())
        t_rm, t_rm_source = select_t_rm(
            self._read(self._trm), self._trm_tracker.current, t_out
        )
        t_out_eff = (
            t_out
            if t_out is not None
            else (t_rm if t_rm is not None else _FALLBACK_OUTDOOR_C)
        )
        t_rm_eff = t_rm if t_rm is not None else t_out_eff
        rh = self._read(self._humidity)
        # solar disturbance q_solar (normalised, ADR-0010): internal clear-sky
        # estimate always runs; a measured irradiance sensor overrides the value
        # used (shadow-estimator principle, ADR-0026).
        q_solar, q_solar_source, q_solar_internal = select_q_solar(
            self._sun_elevation(), self._read(self._irradiance)
        )
        # virtual MRT (shadow, ADR-0017/0026): exterior envelope pulls MRT toward
        # outdoor + a solar radiant bump; a measured globe/MRT sensor overrides.
        mrt_internal = virtual_mrt(room, t_out_eff, q_solar)
        t_mrt, mrt_source = select_mrt(self._read(self._mrt), mrt_internal)
        sensor_window_open, _window_sensor_unavailable = self._window_open()
        self._issue(
            f"window_sensor_unavailable_{self._entry_id}",
            _window_sensor_unavailable,
            translation_key="window_sensor_unavailable",
            placeholders={"entity": ", ".join(self._windows)},
        )
        # F4b follow-up: a healthy, configured sensor is authoritative (ADR-0041
        # §2 exclusivity) and ``_observe_window_auto`` below will not step the
        # slope detector again while it stays healthy -- so ``step_window_auto``'s
        # own anti-stick max-duration timer never gets another chance to run
        # either. An ``open=True`` (or any stale slope/anchor state) latched
        # during a PRIOR sensor dropout (the §5 failsafe just below) would
        # therefore stick forever: the sensor correctly reports "closed" but the
        # OR with a frozen ``auto_open=True`` would pin the effective signal
        # "open" regardless -- a real room-stays-cold regression, and worse than
        # the pre-F4a behaviour (which never ran the detector at all while a
        # sensor was configured, so it could never latch). Reset BEFORE computing
        # ``window_open`` below (not deferred into ``_observe_window_auto``,
        # which only runs later this same tick) so the reset takes effect in the
        # very tick the sensor recovers, not one tick late.
        if self._windows and not _window_sensor_unavailable:
            if self._window_auto != WindowAutoState():
                self._window_auto = WindowAutoState()
                self._dirty = True
            self._wa_ref_room = None
            self._wa_ref_mono = None
            self._wa_prev_mono = None
        # F4a/ADR-0041 §5: a dropped-off window contact must not silently pin
        # "closed" -- an unavailable sensor already reads as
        # ``sensor_window_open=False`` above (indistinguishable from a real
        # "closed"), so the OR with ``auto_open`` is what actually supplies the
        # "heizen wie ohne Sensor" failsafe signal here.
        window_open = effective_window_open(
            sensor_open=sensor_window_open,
            auto_open=self._window_auto.open,
            bypass=self._window_bypass,
        )
        can_heat, can_cool = self._capability()
        # ADR-0008 tri-state: 'auto' follows cooling capability; a legacy bool is
        # honoured unchanged (True->on, False->off), so the upgrade is regression-free.
        adaptive_cool = resolve_adaptive_cool(
            self._adaptive_cool_cfg, can_cool=can_cool
        )
        # ADR-0052: retune the PI/MPC to the actuator's dynamics class so a fast
        # split AC is not driven by a 2 h radiator integrator (which oscillates).
        try:
            _act_dyn = self.hass.states.get(self._actuator)
            _modes_dyn = (
                [str(m) for m in (_act_dyn.attributes.get("hvac_modes") or [])]
                if _act_dyn
                else []
            )
            self._dynamics = classify_dynamics(
                domain=self._actuator.split(".", 1)[0],
                can_cool=can_cool,
                can_fan="fan_only" in _modes_dyn,
                override=self._dynamics_override,
            )
            _prof = PROFILES[self._dynamics]
            self._pi.apply_profile(
                kp=_prof.pi_kp, ki=_prof.pi_ki, offset_max=_prof.offset_max
            )
            self._mpc_params = MpcParams(
                horizon_blocks=_prof.mpc_horizon_blocks, dt_h=_prof.mpc_dt_h
            )
        except Exception:  # noqa: BLE001 - tuning refresh must never break the tick
            _LOGGER.debug("Poise dynamics-profile refresh failed", exc_info=True)
        device_max = self._device_max()

        if should_learn(
            window_open=window_open,
            frozen=frozen,
            heating_failed=self._prev_heating_failed,
        ):
            # F3: only ever teach the EKF from a genuinely MEASURED room reading --
            # a DERIVED value (carried forward from ``last_good`` after a single
            # implausible raw sample) is a reasonable, frost-safe value to
            # *control* on, but it is not new information about the thermal
            # plant, so feeding it to the EKF would teach it a zero/stale delta
            # as if the room had truly stopped moving (ADR-0012 / ADR-0026). This
            # tick's learning step is simply skipped -- unlike the V5 pause below,
            # the anchors are deliberately left untouched: a single glitchy
            # sample is not the "contaminated interval" the V5 reset guards
            # against, and dropping ``self._prev_room`` here would erase the very
            # last-good value future ticks need to keep deriving from, regressing
            # a short flaky-sensor spell to the hard default one tick early.
            if reading.source is Source.MEASURED:
                self._learn(room, t_out_eff)
                self._observe_seasonless(room, t_out_eff)
        else:
            # V5: while learning is paused (open window / frozen sensor, which
            # now also covers a DEFAULT-source reading -- see the ``frozen =``
            # assignment above -- and, R3, a latched heating failure) drop the
            # time anchors, so the first step after
            # resumption re-anchors from that tick instead of integrating the
            # whole contaminated interval. A short Stoßlüften would otherwise
            # poison the EKF with a real-looking sub-hour dt (the 0<dt<1h guard
            # only rejects long gaps). ADR-0024.
            self._last_mono = None
            self._prev_room = None
            self._prev_room_mono = None
            self._heatup_acc.reset()  # drop the heat-up anchor across the pause too
        self._observe_window_auto(
            room,
            t_out_eff,
            cooling=self._was_cooling,
            sensor_unavailable=_window_sensor_unavailable,
        )

        # mould floor + dewpoint cap from humidity
        mold_min = None
        mold_capped = False
        dewpoint = None
        if rh is not None:
            dewpoint = psychro_dewpoint(room, rh)
            # C8: keep a (conservative) mould floor even without an outdoor sensor
            # by using the effective outdoor proxy instead of skipping it.
            # F15: surface when the required floor is clipped at 24 °C -- the room
            # really needs dehumidification there, so protection is insufficient.
            mold_min, mold_capped = mold_min_air_temperature_detail(t_out_eff, rh, room)
        # review #7: a configured humidity sensor that dropped out silently
        # disables mould protection (no floor computed) -> surface it.
        self._issue(
            f"mould_protection_inactive_{self._entry_id}",
            self._humidity is not None and rh is None,
            translation_key="mould_protection_inactive",
            placeholders={"entity": self._humidity or ""},
        )

        # schedule: night setback + optimal-start preheat (ADR-0025).
        # Resolve the forecast outdoor (I/O) here, then let the pure planner
        # decide the effective base — the decision is unit-tested without HA.
        sched = self._schedule.state_at(self._local_minute())
        # A model is needed for the predictive plan in BOTH phases: preheat during
        # setback (lead = minutes to comfort) and coast/optimal-stop during comfort
        # (lead = minutes to setback). H2: build it whenever the EKF is identified
        # and either feature is enabled — it was previously built only during
        # setback, which left the comfort-phase coast (optimal-stop) branch dead.
        predictive = (
            can_heat
            and self._ekf.identified
            and (self._optimal_start or self._optimal_stop)
        )
        if predictive:
            lead_minutes = (
                sched.minutes_to_setback
                if sched.is_comfort
                else sched.minutes_to_comfort
            )
            t_out_lead = await self._forecast_outdoor(float(lead_minutes), t_out_eff)
            model = self._ekf.get_model()
        else:
            t_out_lead, model = t_out_eff, None
        lo, hi = HEATING_LOWER[self._category], HEATING_UPPER[self._category]

        # ADR-0058 presence coupling. Resolve the house gate BEFORE the preheat
        # plan: an empty house (home is False) or a manual Away preset means
        # "away", whose depth is carried by the Eco band-widen below (not a base
        # shift), so we feed a NEUTRAL preset base into the plan to avoid a
        # cooling-edge double-dip, and an empty house is never preheated.
        def _tristate(entity_id: str | None) -> bool | None:
            if not entity_id:
                return None
            st = self.hass.states.get(entity_id)
            if st is None or st.state in ("unknown", "unavailable"):
                return None
            s = st.state.lower()
            if s in ("home", "on", "true"):
                return True
            if s in ("not_home", "off", "false", "away"):
                return False
            # F8: a person/device_tracker can report a named zone ("Work", "Gym",
            # ...) as its state -- that is a resolved, confident "not home", not a
            # sensor failure. Falling through to None here made ``any_present``'s
            # fail-safe (unresolved -> present) misread a person confirmed to be
            # away at a custom zone as "home", the opposite of a fail-safe. Any
            # other domain's odd/custom state is left genuinely unresolved (None).
            if entity_id.split(".", 1)[0] in ("person", "device_tracker"):
                return False
            return None

        _home = any_present(_tristate(e) for e in self._presence_home_entities)
        # ADR-0059 §1/§2: expire the timed Boost + manual hold here, once the house
        # gate is known and before the preset/override feed the plan and solver. A
        # Boost restore must land before _is_away/_base_preset read the preset.
        self._expire_timed_states(_home)
        _is_away = self._preset is OverrideMode.AWAY or _home is False
        _base_preset = OverrideMode.NONE if _is_away else self._preset
        _comfort_target = mode_comfort_base(
            _base_preset, self._comfort_base, self._override_cfg
        )
        plan = plan_preheat(
            comfort_base=_comfort_target,
            is_comfort=sched.is_comfort,
            setback_offset=sched.setback_offset,
            minutes_to_comfort=float(sched.minutes_to_comfort),
            optimal_start_enabled=self._optimal_start and not _is_away,
            can_heat=can_heat,
            identified=self._ekf.identified,
            model=model,
            room=room,
            t_out_lead=t_out_lead,
            heat_lower=lo,
            heat_upper=hi,
            optimal_stop_enabled=self._optimal_stop,
            minutes_to_setback=float(sched.minutes_to_setback),
            coast_lower=lo,
            was_preheating=self._was_preheating,
            was_coasting=self._was_coasting,
            max_lead_h=PROFILES[self._dynamics].max_lead_h,
        )
        base = plan.base
        preheating = plan.preheating
        preheat_outdoor = plan.preheat_outdoor
        coasting = plan.coasting
        # ADR-0059 §3: end a schedule-hold the moment optimal-start *begins*
        # preheating toward the comfort window its expiry points at, when the
        # preheat target is warmer than the held value -- so the room is warm at
        # comfort time instead of the hold clamping the preheat into a cold
        # block-start (Danfoss schedule_with_preheat). Rising edge only (so a hold
        # set *during* an active preheat is respected); runs before the latch below.
        if self._override is not None and hold_ends_at_preheat(
            policy=self._override_policy,
            preheat_started=preheating and not self._was_preheating,
            expiry_is_switchpoint=self._override_expiry_is_switchpoint,
            preheat_target=_comfort_target,
            held_value=self._override,
        ):
            self._end_hold("schedule_point")
        # ADR-0025/0034 latch: carry this tick's engage state to the next tick so
        # the planner can hold instead of re-chattering at the deadline boundary.
        self._was_preheating = preheating
        self._was_coasting = coasting

        # operative TRV-input mode (ADR-0029): write the operative target and feed
        # the operative temperature, IF the thermostat can be calibrated to an
        # external sensor (i.e. a valid external-temperature input). Otherwise fall
        # back to air-side control and flag a repair issue (fault tolerance).
        # external-temp input: explicit config, else auto-detected on the device
        # (pavax-verified). The number is write-only, so a "unknown" state is fine;
        # only "unavailable" means the device is offline (ADR-0029).
        ext_num = self._trv_ext_temp or (
            self._ext_temp_auto if self._operative_input else None
        )
        ext_state = self.hass.states.get(ext_num) if ext_num else None
        ext_ok = ext_state is not None and ext_state.state != "unavailable"
        operative_active = self._operative_input and ext_ok
        self._issue(
            f"operative_unsupported_{self._entry_id}",
            self._operative_input and not ext_ok,
            translation_key="operative_unsupported",
            placeholders={"entity": ext_num or "—"},
        )
        if operative_active:
            room_decide = operative_temperature(room, t_mrt)
            t_mrt_decide: float | None = None  # MRT lives in the fed/written values
        else:
            room_decide = room
            t_mrt_decide = t_mrt
        # ADR-0058: resolve the presence level (the house gate is already folded
        # into _is_away above). Room-absence only modulates inside the comfort
        # window and never overrides a preheat. Level -> (occupied, eco_widen,
        # cool ceiling): COMFORT keeps today's behaviour; ROOM_ECO widens by the
        # Eco delta capped at the cool hard cap; AWAY widens by the away offset up
        # to the device max. No base shift -- the widen carries the whole depth.
        _presence_now = dt_util.utcnow().timestamp()
        _room_present = any_present(_tristate(e) for e in self._occupancy_entities)
        self._room_absent_since = step_room_absence(
            self._room_absent_since, present=_room_present, now=_presence_now
        )
        _absent_min = (
            (_presence_now - self._room_absent_since) / 60.0
            if self._room_absent_since is not None
            else 0.0
        )
        _level = resolve_presence(
            home=_home,
            room_absent_min=_absent_min,
            is_comfort=sched.is_comfort,
            preheating=preheating,
            cfg=self._presence_cfg,
        )
        # ADR-0059 §5: cache the presence level + window state so a user setpoint
        # nudge recorded in set_override (no tick context) can skip AWAY/window.
        self._last_presence_level = _level.value
        # P2-1: track the rising edge of the open-window episode on the tick's
        # monotonic clock (``now``, established ~line 1849) so the mould floor can
        # be suppressed for its first WINDOW_MOULD_SUPPRESS_S below.
        if window_open:
            if self._window_open_since is None:
                self._window_open_since = now
        else:
            self._window_open_since = None
        self._last_window_open = window_open
        _eco_widen: float
        _cool_ceiling: float | None
        if _level is PresenceLevel.AWAY:
            _occupied = False
            _eco_widen = self._override_cfg.away_offset
            _cool_ceiling = DEVICE_MAX_C
        elif _level is PresenceLevel.ROOM_ECO:
            _occupied = False
            _eco_widen = self._presence_cfg.eco_delta
            _cool_ceiling = self._cool_hard_cap
        else:  # COMFORT
            _occupied = sched.is_comfort or preheating
            _eco_widen = 0.0
            _cool_ceiling = None
        decision = comfort_decide(
            t_rm=t_rm_eff,
            room=room_decide,
            category=self._category,
            comfort_base=base,
            can_heat=can_heat,
            can_cool=can_cool,
            climate_mode=self._climate_mode,
            cool_min_outdoor=(
                self._cool_min_outdoor if self._cool_lockout_enabled else None
            ),
            heat_max_outdoor=(
                self._heat_max_outdoor if self._heat_lockout_enabled else None
            ),
            t_out=t_out_eff,
            t_mrt=t_mrt_decide,
            frost_floor=FROST_FLOOR_C,
            mold_min=mold_min,
            dewpoint=dewpoint,
            priority=self._priority,
            occupied=_occupied,
            adaptive_cool=adaptive_cool,
            adaptive_cap=self._cool_hard_cap,
            eco_widen=_eco_widen,
            cool_ceiling_override=_cool_ceiling,
        )

        act_state = self.hass.states.get(self._actuator)
        # F2: a genuinely offline actuator (state=="unavailable") reports no
        # trustworthy setpoint, so should_write()'s "actual is None -> write"
        # rule fired on EVERY tick -- a write storm into a dead Zigbee/MQTT
        # device. Setpoint (and mode-nudge) writes are gated on this below.
        _actuator_online = act_state is not None and act_state.state != "unavailable"
        # ADR-0051 activation: on a hot day raise the cooling setpoint toward the
        # EN adaptive upper (capped; the default ASR-26 cap makes it a no-op
        # until the cap is raised), rate-limited <=0.5 K/tick. Cooling-only:
        # decide_mode gates "cool" on can_cool, so a heat-only TRV never sees it.
        eff_cool = decision.cool_sp
        _cool_ac = None
        try:
            _cool_ac = adaptive_cool_setpoint(
                cool_sp_en=decision.cool_sp,
                t_out_smooth=t_out_eff,
                t_rm=t_rm_eff,
                category=self._category,
                device_max=device_max,
                hard_cap=self._cool_hard_cap,
                delta_k=self._thermal_shock_delta,
            )
            eff_cool = rate_limit(self._cool_sp_eff_prev, _cool_ac.cool_sp_eff, 0.5)
            self._cool_sp_eff_prev = eff_cool
        except Exception:  # noqa: BLE001 - the cool raise must never break the tick
            _LOGGER.debug("Poise cool-raise activation failed", exc_info=True)
        # Finding 1 follow-up (idle-park): when idle, park toward the edge the room
        # is closest to — a warm reversible AC parks in cool at the cool edge, not
        # in heat at the low heat idle-hold (which needs a many-K drop to act and
        # never responds to a warming room). ONE decision drives both the written
        # value and the mode nudge (idle_park_mode below) so they never disagree; a
        # heat-only TRV always parks in heat (can_cool False -> unchanged).
        _idle_park_mode: str | None = None
        if decision.mode == "cool":
            cool_write = eff_cool
        elif decision.mode == "idle":
            _idle_park_mode, cool_write = idle_park(
                room=room_decide,
                heat_sp=decision.heat_sp,
                cool_sp=eff_cool,
                can_heat=can_heat,
                can_cool=can_cool,
                can_fan_only=(
                    act_state is not None
                    and "fan_only" in (act_state.attributes.get("hvac_modes") or [])
                ),
                current_mode=act_state.state if act_state else None,
            )
        else:
            cool_write = decision.write_setpoint
        # P2-1: DIN 4108-2 is a steady-state criterion. Under an open window the
        # write target collapses to the floor (= max(frost, mould)); a humid room
        # would then heat toward ~24 C against the ventilation. Suppress only the
        # mould component for the first WINDOW_MOULD_SUPPRESS_S of the episode --
        # the frost floor (FROST_FLOOR_C) is NEVER suppressed. Diagnostics keep
        # the real ``mold_min`` (see the ``mould_floor`` attribute below).
        mold_min_write = (
            None
            if (
                window_open
                and self._window_open_since is not None
                and (now - self._window_open_since) < WINDOW_MOULD_SUPPRESS_S
            )
            else mold_min
        )
        wt = resolve_write_target(
            window_open=window_open,
            override=self._override,
            heat_sp=decision.heat_sp,
            cool_sp=eff_cool,
            write_setpoint=cool_write,
            comfort_mode=decision.mode,
            frost_floor=FROST_FLOOR_C,
            mold_min=mold_min_write,
            device_max=device_max,
            device_min=self._device_min(),
        )
        target, mode, norm_binding = wt.target, wt.mode, wt.norm_binding
        binding_precedence = wt.binding_precedence
        # V10: surface a silently band-clamped manual override (moot when frozen,
        # where the frost floor below replaces the override target entirely).
        override_clamped = wt.override_clamped and not frozen
        if frozen:
            # C3/Ü3 + review V1: the room sensor is stale -> do not chase a comfort
            # target on a dead value. A heat-capable device degrades to the health
            # floor in heat (frost protection, held by the actuator's own sensor,
            # fail toward warmth); a cool-only device must NOT be pinned to the
            # floor in cool (it would cool the room to ~7 C) -> command off.
            if can_heat:
                target = frozen_safe_target(FROST_FLOOR_C, mold_min)
                mode = "heat"
            else:
                mode = "off"
            self._last_target = target
        # ADR-0050/0051: mostly-diagnostic climate-band block, but NOT "no writes" —
        # the humidity action it computes (_hum_action) drives the LIVE dry
        # mode-nudge below (mode_arbitration). Composed against the *effective*
        # (raised) cool band; the fan/PMV/free-running fields are the shadow parts.
        climate_diag: dict[str, object] = {}
        _hum_action = "idle"  # ADR-0050 S2c: drives the live dry mode-nudge below
        try:
            _modes_cl = (
                [str(m) for m in (act_state.attributes.get("hvac_modes") or [])]
                if act_state
                else []
            )
            # ADR-0050/0051 coherence: compose humidity + diagnostics against the
            # SAME config-based, rate-limited cool band that is actually written
            # (_cool_ac / eff_cool), not a second default-config computation.
            _w = (
                humidity_ratio(room, rh)
                if rh is not None and room is not None
                else None
            )
            _hum = humidity_decide(
                rh=rh,
                too_warm=room_decide > eff_cool,
                in_deadband=decision.heat_sp <= room_decide <= eff_cool,
                can_dry="dry" in _modes_cl,
                can_fan_only="fan_only" in _modes_cl,
                prev_dry_active=self._dry_active,
                category=self._category,
                abs_humidity_gkg=_w,
                occupied=_occupied,
            )
            self._dry_active = _hum.dry_active
            _hum_action = _hum.action
            # ADR-0023 §1 free-running widening (shadow): the EN adaptive band
            # widens the dead-band only while the room floats in the fixed band.
            _fr = free_running_widen(
                heat_op=decision.heat_sp,
                cool_op=decision.cool_sp,
                room=room_decide,
                t_rm=t_rm_eff,
                category=self._category,
            )
            # ADR-0053 idle-recirculation SHADOW (preview, no writes): show what
            # enabling would do on this device. No presence entity yet -> the
            # presence-less opt-in path; policy forced on for the preview only.
            _can_recirc = "fan_only" in _modes_cl or bool(
                act_state and act_state.attributes.get("fan_modes")
            )
            _fan = fan_circulation(
                occupied=_occupied,
                in_deadband=decision.heat_sp <= room_decide <= eff_cool,
                active_mode=mode,
                window_open=window_open,
                can_recirculate=_can_recirc,
                policy=FAN_ONLY_LOW,
                presence_optin=True,
            )
            # Roadmap M3 (ASHRAE 55 elevated air speed) SHADOW: what a running fan
            # (at the configured air speed) would let the cooling setpoint rise to —
            # comfort-preserving and ASR/EN-capped. Fan-capable device = the preview
            # basis; no writes yet (activation is a follow-up after validation).
            # Estimate the occupied-zone air speed from the actuator's real fan
            # state (still air unless the indoor fan is actually moving air),
            # instead of the fan-capability proxy — feeds the fan-CE + PMV SHADOW
            # only; the write path (operative.py / decide) keeps the 0.1 baseline.
            _fan_mode = act_state.attributes.get("fan_mode") if act_state else None
            _hvac_act = act_state.attributes.get("hvac_action") if act_state else None
            _fan_v = fan_velocity(
                fan_mode=_fan_mode, hvac_action=_hvac_act, can_recirculate=_can_recirc
            )
            _fan_cool_sp, _fan_ce = fan_cool_setpoint(
                cool_sp=eff_cool,
                air_speed=_fan_v,
                fan_running=_can_recirc,
                upper_cap=self._cool_hard_cap,
            )
            # ADR-0054 SHADOW: ISO 7730 PMV/PPD — humidity and the (estimated) fan
            # velocity finally enter the comfort evaluation; diagnostic only, no
            # writes (the norm temperature band stays the control variable).
            _pmv = pmv_ppd(
                t_air=room,
                t_mrt=t_mrt if t_mrt is not None else room,
                rh=rh if rh is not None else 50.0,
                velocity=_fan_v,
                clo=seasonal_clo(t_rm_eff),
            )
            climate_diag = {
                "cool_sp_eff": _cool_ac.cool_sp_eff if _cool_ac else decision.cool_sp,
                "cool_sp_active": round(eff_cool, 1),
                "cool_raised": _cool_ac.raised if _cool_ac else False,
                "cool_raise_reason": _cool_ac.reason if _cool_ac else "n/a",
                "en_cool_upper": _cool_ac.en_upper if _cool_ac else 0.0,
                "humidity_action": _hum.action,
                "dry_active": _hum.dry_active,
                "humidity_reason": _hum.reason,
                "abs_humidity_gkg": (round(_w, 1) if _w is not None else None),
                "rh_high_used": rh_high_for_category(self._category),
                "fr_active": _fr.active,
                "fr_heat_sp": round(_fr.heat_op, 1),
                "fr_cool_sp": round(_fr.cool_op, 1),
                "fr_adaptive_lower": round(_fr.adaptive_lower, 1),
                "fr_adaptive_upper": round(_fr.adaptive_upper, 1),
                "fan_circ_shadow": _fan.action,
                "fan_ce_k": _fan_ce,
                "fan_cool_sp_shadow": _fan_cool_sp,
                "fan_velocity_ms": round(_fan_v, 2),
                "fan_circ_reason": _fan.reason,
                "occupied": _occupied,
                "presence_level": _level.value,
                "room_absent_min": round(_absent_min, 1),
                "home_present": _home,
                "pmv": _pmv.pmv,
                "ppd": _pmv.ppd,
                "pmv_category": _pmv.category,
            }
        except Exception:  # noqa: BLE001 - must never break the tick
            # AR-32: not purely shadow — on failure the LIVE dry mode-nudge silently
            # falls back to "idle". Surface it at WARNING once, then DEBUG after.
            if not self._hum_shadow_warned:
                self._hum_shadow_warned = True
                _LOGGER.warning(
                    "Poise %s: climate-band/humidity block failed; the live dry "
                    "mode-nudge falls back to idle this tick (further at DEBUG)",
                    self.zone_name,
                    exc_info=True,
                )
            else:
                _LOGGER.debug("Poise climate-band shadow failed", exc_info=True)
        heating = self._enabled and not window_open and mode == "heat"
        cooling = cooling_intent(
            enabled=self._enabled, window_open=window_open, mode=mode
        )
        self._was_cooling = mode == "cool"  # gate the window slope next tick
        # A1: the EKF heating-drive uses the actuator's *real* running state when
        # reported (TRVZB running_state -> hvac_action), else our heat intent.
        self._last_u_h = heat_drive_signal(
            act_state.attributes.get("hvac_action") if act_state else None,
            fallback_heating=heating,
        )
        # β_c excitation (ADR-0024): the cooling counterpart, so cooling_identified
        # can leave False during the cooling season. Real hvac_action when reported
        # (AC "cooling"), else Poise's cool intent.
        self._last_u_c = cool_drive_signal(
            act_state.attributes.get("hvac_action") if act_state else None,
            fallback_cooling=cooling,
        )
        self._last_q_solar = q_solar
        self._last_target = target

        # C6: the failure detector keys on the actuator's real running state
        # (hvac_action) when reported, not just our heat intent.
        running = actuator_running(
            act_state.attributes.get("hvac_action") if act_state else None,
            fallback=heating,
        )
        failed = (
            self._failure.update(
                now_h=now / 3600.0,
                room=room,
                setpoint=target,
                running=running,
            )
            or fault_active
        )
        await self._notify_failure(failed)
        # R3: latch for the NEXT tick's learn gate (this tick's gate already ran).
        self._prev_heating_failed = failed

        _mode_nudge_blocked = ""  # ADR-0046 §8: compressor-guard suppression reason
        # F1: default for the unconditional shadow block below (no live mode nudge
        # is even considered while disabled, so "not blocked" is the honest value).
        _guard_block: str | None = None
        # H1/A2: keep a controllable actuator in the mode that matches our
        # write — cool when we cool, heat otherwise — so it follows our
        # setpoint instead of its own off/auto schedule (TRVZB system_mode).
        act_modes = (act_state.attributes.get("hvac_modes") or []) if act_state else []
        # ADR-0050 S2c: fold active drying into the mode — dry wins ONLY when
        # idle (temp in band) + humidity asks + the device can dry; heat/cool/
        # off/manual pass through (temperature + safety primary). Capability-
        # gated: a heat-only TRV has no "dry" mode -> dry_ok False -> no-op.
        # ADR-0059 control-loop fix: an ACTIVE manual override must DRIVE the
        # heat/cool/idle direction, not only set the written value. Collapse
        # the band to a hysteresis window around the commanded (clamped)
        # override and reuse the capability/outdoor-gated decide_mode, so a
        # reversible AC flips to cool/heat toward the manual value instead of
        # idling in its last mode. window/frozen keep precedence (they replace
        # the "manual" tag upstream, so mode != "manual" there); an "idle"
        # ov_mode still flows through the seam so dry-in-deadband can apply.
        # The WRITTEN target is unchanged -- only the mode is derived here.
        # F1: this mode/guard-policy resolution used to sit entirely inside
        # ``if self._enabled:`` below, but the unconditional shadow block
        # further down (multi_lifecycle observation, ADR-0046 P2) reads
        # ``final_mode``/``_guard_pol``/``_g_min_off``/``_g_mode_hold`` on
        # EVERY tick regardless of ``self._enabled`` -- a disabled zone raised
        # an UnboundLocalError there every tick (swallowed by the shadow
        # block's broad except), which silently froze the wall-clock
        # compressor lifecycle for the whole time the zone stayed disabled.
        # Resolving them here, unconditionally, keeps that shadow tracking
        # alive (ADR-0026: shadow estimators always run) while only the
        # actual mode/setpoint WRITES below stay enabled-gated.
        _base_mode = mode
        if (
            self._enabled
            and self._override is not None
            and not window_open
            and not frozen
        ):
            _base_mode = override_mode(
                room=room_decide,
                override=target,
                hysteresis=0.5,
                outdoor=t_out_eff,
                climate_mode=self._climate_mode,
                can_heat=can_heat,
                can_cool=can_cool,
                cool_min_outdoor=(
                    self._cool_min_outdoor if self._cool_lockout_enabled else None
                ),
                heat_max_outdoor=(
                    self._heat_max_outdoor if self._heat_lockout_enabled else None
                ),
            )
        final_mode = mode_arbitration(
            base_mode=_base_mode,
            humidity_action=_hum_action,
            dry_ok="dry" in act_modes,
        )
        # ADR-0046 §8 (live): hold back a mode nudge that would short-cycle the
        # compressor — start it within min-off, or flip cool<->dry within
        # mode-hold. Capability-gated (cool/dry only) + kill switch; never a
        # stop and never a safety action. The comfort request stands and
        # re-fires once the lock clears, so _mode_nudge_blocked reads as intent
        # (a blocked dry entry keeps dry_active latched, surfaced on the card).
        _guard_prof = PROFILES[self._dynamics]
        _g_min_off = (
            self._comp_min_off_opt
            if self._comp_min_off_opt is not None
            else _guard_prof.compressor_min_off_s
        )
        _g_mode_hold = (
            self._comp_mode_hold_opt
            if self._comp_mode_hold_opt is not None
            else _guard_prof.compressor_mode_hold_s
        )
        _guard_pol = _lifecycle.resolve_guard_policy(
            enabled=self._compressor_guard != COMPRESSOR_GUARD_OFF,
            can_condition=can_cool or "dry" in act_modes,
            min_off_s=_g_min_off,
            mode_hold_s=_g_mode_hold,
        )
        # K2b (review v0.173.0-alpha §4.2) — ATTEMPTED AND REVERTED in v0.174.0.
        # Moving ``_lifecycle.observe()`` up here, ahead of ``guard_block_reason``
        # below, looks like a pure reordering but is NOT safe, for two independent
        # reasons the integration suite proved:
        #   1. ``compressor_running(_act_action, final_mode)`` falls back to Poise's
        #      OWN INTENT when the device reports no hvac_action. Folded in before
        #      the guard, the intent to start ("we want cool") marks the device as
        #      running, min-off evaporates and the guard can never brake a start --
        #      it would judge against its own intent. Circular, and the exact
        #      opposite of what the guard is for.
        #   2. ``observe()`` stamps ``mode_changed_wall = now`` whenever the observed
        #      mode differs from the stored one -- and on the first tick the stored
        #      mode is None. The guard would then block that same tick's nudge
        #      against a hold it had just armed itself: no dry/cool/heat entry on the
        #      first tick after any restart (test_dry_nudge_when_humid_and_idle).
        # The late call is therefore deliberate: it folds this tick's outcome for the
        # NEXT tick's verdict. A correct K2b has to fold only the device-*reported*
        # run-state (never the intent fallback) and must not arm the mode hold on a
        # first observation -- a designed change to multi/lifecycle.py with its own
        # pure tests, not a reordering. Tracked as follow-up; the un-braked revert on
        # a non-adopted intervention (T-4) stays open until then.
        # V2/K2: is the actuator's current state Poise's own write echo (our Context)?
        # Computed once, reused by the mode-adoption gate here and the setpoint gate
        # below (a change under our own context is never adopted, mode or setpoint).
        _own_change = bool(
            act_state is not None
            and act_state.context is not None
            and act_state.context.id in self._own_write_ctx_ids
        )
        # K2: an ``off`` mode-hold routes the zone through the disabled/frost-rescue
        # branch below (frost + mould protection stay active), exactly like a
        # user-disabled zone. Read from the persisted hold at tick start; the tick
        # that first adopts ``off`` still runs the enabled block (pins desired=off,
        # skips the setpoint write) and only the next tick takes the frost route.
        _off_held = self._mode_override == "off"
        # M3: an off-hold is escapable at the device -- if the user switches the AC
        # back on (a foreign-context mode change away from off), end the hold so the
        # zone resumes control instead of holding a stale off while the device runs.
        # ``_hold_resumed`` then suppresses this tick's adoption so we do not re-grab
        # the mode the user just switched to as a fresh hold (resume != re-adopt).
        _hold_resumed = False
        if (
            _off_held
            and not _own_change
            and (act_state.state if act_state else None)
            not in ("off", None, "unknown", "unavailable")
        ):
            self._end_hold("user_resume")
            _off_held = False
            _hold_resumed = True
        # K3 (Inc 3): why this tick did/did not adopt a device change, surfaced as
        # diagnostics (stays "" on the disabled / off-held path that skips below).
        _mode_adopt_reason = ""
        _sp_adopt_reason = ""
        if self._enabled and not _off_held:
            desired_hvac = resolve_desired_mode(
                final_mode=final_mode,
                current_device_mode=act_state.state if act_state else None,
                can_cool=can_cool,
                can_heat=can_heat,
                idle_park_mode=_idle_park_mode,
            )
            # K2: adopt a device-side hvac_mode change (the IR remote) as a manual
            # mode-hold instead of nudging it straight back. Behind the opt-out and
            # the Context check (our own nudge echo is never adopted); off while a
            # safety layer is active (window/frost beat a mode-hold -- it is comfort,
            # not safety); only modes the device lists (heat_cool excluded, B7).
            _cur_mode = act_state.state if act_state else None
            _mode_adopt = (
                detect_external_mode(
                    device_mode=_cur_mode,
                    desired_mode=desired_hvac,
                    last_commanded_mode=self._last_commanded_hvac,
                    last_cmd_ts=self._last_hvac_cmd_ts,
                    now=now,
                    echo_window_s=SETPOINT_ADOPT_ECHO_WINDOW_S,
                    supported_modes=tuple(act_modes),
                    prev_mode=self._prev_device_mode,
                )
                if (
                    self._adopt_external_mode
                    and not window_open
                    and not frozen
                    and not _own_change
                    and not _hold_resumed
                )
                else None
            )
            # K3: classify why the mode change was or was not adopted -- Layer-1 glue
            # gates first, then the pure Layer-2 detector reason -- so a suppressed
            # user mode change is explainable in diagnostics.
            if not self._adopt_external_mode:
                _mode_adopt_reason = "opt_out"
            elif window_open:
                _mode_adopt_reason = "safety_window"
            elif frozen:
                _mode_adopt_reason = "safety_frozen"
            elif _own_change:
                _mode_adopt_reason = "own_echo"
            elif _hold_resumed:
                _mode_adopt_reason = "hold_resumed"
            else:
                _mode_adopt_reason = mode_adopt_reason(
                    device_mode=_cur_mode,
                    desired_mode=desired_hvac,
                    last_commanded_mode=self._last_commanded_hvac,
                    last_cmd_ts=self._last_hvac_cmd_ts,
                    now=now,
                    echo_window_s=SETPOINT_ADOPT_ECHO_WINDOW_S,
                    supported_modes=tuple(act_modes),
                    prev_mode=self._prev_device_mode,
                )
            # M2: freeze the mode move-guard reference while the echo window is open,
            # so an in-window observation of the user's mode never poisons the guard
            # (the mode analogue of the setpoint prev-freeze; the B1 poisoning class).
            if (
                self._last_hvac_cmd_ts is None
                or (now - self._last_hvac_cmd_ts) >= SETPOINT_ADOPT_ECHO_WINDOW_S
            ):
                self._prev_device_mode = _cur_mode
            if _mode_adopt is not None:
                self._set_mode_override(_mode_adopt)
            # M3: a mode-hold is escapable AT THE DEVICE -- if the user selects the
            # plan mode again (a foreign-context change back to what Poise wants),
            # end the hold instead of pinning them off it (detect_external_mode
            # returns None for device==desired, so it is resolved here).
            elif (
                self._mode_override is not None
                and not _own_change
                and _cur_mode == desired_hvac
                and _cur_mode != self._mode_override
                and not window_open
                and not frozen
            ):
                self._end_hold("user_resume")
            # An active mode-hold pins the desired mode (no nudge; the setpoint keeps
            # regulating within it) unless a safety layer has taken over this tick --
            # window-open / frost still beat the hold (I6), and the hold resumes once
            # the layer clears.
            if self._mode_override is not None and not window_open and not frozen:
                desired_hvac = self._mode_override
            # A device hvac_mode change this tick must carry its setpoint with it,
            # so it bypasses the §4 setpoint throttle below: a mode nudge without
            # its matching setpoint would e.g. flip an AC to cool while it still
            # holds the heat idle-hold (17.5) and overcool until the throttle clears
            # (idle-park heat->cool transition).
            _mode_nudge = needs_mode_nudge(
                act_state.state if act_state else None,
                desired_hvac,
                supported=desired_hvac in act_modes,
            )
            _guard_block = _lifecycle.guard_block_reason(
                _guard_pol,
                self._multi_lifecycle,
                dt_util.utcnow().timestamp(),
                desired=desired_hvac,
                current=act_state.state if act_state else None,
                # F11 (review, refuted as a bug): an active manual override is
                # deliberately exempt from the compressor-guard hold, same as a
                # genuine safety trip (open window / frozen sensor) -- ADR-0046's
                # Nachtrag (2026-07-04, v0.140.0 -> v0.145.0) states this
                # explicitly: "is_safety unverändert (Fenster->off/Frost/
                # Override/Frozen nie geblockt)". A user's manual intent must not
                # be held hostage by a min-off/mode-hold timer.
                is_safety=window_open or frozen or self._override is not None,
            )
            if _mode_nudge and _guard_block:
                _mode_nudge = False  # compressor protection: hold this tick's nudge
                _mode_nudge_blocked = _guard_block
            if _mode_nudge:
                try:
                    await self.hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {"entity_id": self._actuator, "hvac_mode": desired_hvac},
                        blocking=False,
                        context=self._own_ctx(),  # V2: tag our own mode change
                    )
                    # K2: stamp the mode echo baseline so our own nudge is never
                    # re-read as an external mode change next tick. M2: only re-arm
                    # the echo window on a mode *change* -- re-arming on every
                    # identical re-nudge (a device that never follows) would keep the
                    # window open forever and permanently block adoption (B1 class).
                    if desired_hvac != self._last_commanded_hvac:
                        self._last_hvac_cmd_ts = now
                    self._last_commanded_hvac = desired_hvac
                except Exception:  # noqa: BLE001 - mode nudge is best-effort
                    _LOGGER.exception(
                        "Poise: set_hvac_mode(%s) failed for %s",
                        desired_hvac,
                        self._actuator,
                    )
            # Compare to the actuator's *actual* setpoint, not our last command, so
            # we re-assert when something external (e.g. an "off"/away automation)
            # changed it, while still skipping writes when it already matches
            # (review P1.2; live-test finding 2026-06-21).
            actual_sp = _num_attr(act_state, "temperature")
            # snap our target to the device's setpoint step so a coarse TRV's
            # rounded echo doesn't trigger a write every tick (review R2)
            step = _num_attr(act_state, "target_temperature_step") or 0.1
            mode_changed = final_mode != self._last_written_mode
            # ADR-0052 §4: a self-regulating climate entity (its own thermostat)
            # is nudged at most once per its dynamics regulation period, so Poise
            # does not thrash it (and its compressor) with per-tick comfort
            # adjustments. Mode changes, an open window, an override and a frozen
            # sensor bypass the throttle (safety/intent must be immediate). Dumb
            # setpoint actuators (regulation_period_s == 0, e.g. TRVs) are never
            # throttled -> heat-only test hardware is a no-op.
            _wprof = PROFILES[self._dynamics]
            _reg_throttled = (
                _wprof.self_regulating
                and not mode_changed
                and not _mode_nudge
                and not window_open
                and self._override is None
                and not frozen
                and regulation_throttled(
                    now_s=now,
                    last_write_s=self._last_sp_write_ts,
                    regulation_period_s=_wprof.regulation_period_s,
                )
            )
            # P1-4a: a device-side setpoint change (TRV wheel / vendor app) that
            # differs from what Poise last commanded is adopted as a manual hold
            # with the zone's override policy, instead of being overwritten. Off
            # while the device runs its own schedule (the schedule, not the user,
            # moves the setpoint) and behind the opt-out; ``set_override`` clamps
            # the adopted value to the norm envelope. Skipping this tick's write
            # avoids overwriting the just-adopted value -- next tick's target
            # already reflects the new hold.
            # V2 (analysis 2026-07-14): the reliable "is this our own write's echo?"
            # signal. If the actuator's current state carries a Context Poise itself
            # created (setpoint / mode nudge), this reading is our write settling --
            # including a device re-quantise / min-max clamp a push integration
            # reports under our context -- so accept the device's *actual* value as
            # the new echo baseline and never adopt it. Only a change under a
            # foreign/unknown context (a user via IR/app, or an async echo a poll
            # integration reports under a fresh context) reaches the value/time
            # detector below. This is what the pure heuristic can only approximate,
            # and why V2 ships together with V1.
            # ``_own_change`` is computed once above (shared with the K2 mode-adoption
            # gate); reuse it here for the setpoint echo re-baseline.
            if _own_change and actual_sp is not None:
                # Accept the device's *actual* settled value (echo / clamp /
                # re-quantise) as the echo baseline so future reports of it are
                # recognised as echoes. Do NOT touch _last_sp_write_ts: the echo
                # window and the ADR-0052 §4 regulation throttle both key off the
                # real last-*write* time; refreshing it every echo tick would keep
                # the window/throttle open as long as the device echoes our context
                # and could defer a legitimate new-target write past its period.
                self._last_written_sp = actual_sp
            _adopted_sp: float | None = (
                detect_external_setpoint(
                    device_sp=actual_sp,
                    last_written_sp=self._last_written_sp,
                    last_write_ts=self._last_sp_write_ts,
                    now=now,
                    echo_window_s=SETPOINT_ADOPT_ECHO_WINDOW_S,
                    # At least one device step (the detector's documented contract).
                    # The step also serves the *echo classification*: a device that
                    # settles/re-quantises our write within one step (e.g. 21.5 -> 21.8
                    # on a 0.5 K grid) must read as our echo, not a third value. RC
                    # review F1: lowering this to the bare WRITE_DEADBAND_C (0.2, the
                    # V4 "symmetry" idea) let such a settle -- reported later under a
                    # *fresh* context, so V2 can't catch it -- be adopted as a phantom
                    # "manual" hold on poll/sluggish devices (the old card-X bug class).
                    # A real IR change is >= one step, so B1 stays fully fixed.
                    deadband=max(WRITE_DEADBAND_C, step),
                    # P1-4a fix: only a value the device *moved* to is a user
                    # change; a stable settle/clamp of our own write is not.
                    prev_device_sp=self._prev_device_sp,
                    # V1: inside the echo window, a value differing from BOTH our
                    # command and the pre-write reading is a provable user change.
                    pre_write_sp=self._pre_write_sp,
                    # R4 (2026-07 competitor audit): a report at/below the frost
                    # floor is a TRV's own frost drop, never a plausible user hold.
                    frost_floor=FROST_FLOOR_C,
                )
                if (
                    self._adopt_external_setpoint
                    and not sched_active
                    and not _own_change
                    # R4: gate on safety like the mode-adoption path -- an open
                    # window or a frozen sensor must not let a device-side drop be
                    # grabbed as a "manual" hold (the frost-drop phantom-hold class).
                    and not window_open
                    and not frozen
                )
                else None
            )
            # K3: classify why the reported setpoint was or was not adopted, using the
            # SAME prev_device_sp the detector saw (captured before it is updated just
            # below); Layer-1 glue gates first, then the pure Layer-2 detector reason.
            if not self._adopt_external_setpoint:
                _sp_adopt_reason = "opt_out"
            elif sched_active:
                _sp_adopt_reason = "schedule_active"
            elif _own_change:
                _sp_adopt_reason = "own_echo"
            elif window_open:
                _sp_adopt_reason = "safety_window"
            elif frozen:
                _sp_adopt_reason = "safety_frozen"
            else:
                _sp_adopt_reason = setpoint_adopt_reason(
                    device_sp=actual_sp,
                    last_written_sp=self._last_written_sp,
                    last_write_ts=self._last_sp_write_ts,
                    now=now,
                    echo_window_s=SETPOINT_ADOPT_ECHO_WINDOW_S,
                    deadband=max(WRITE_DEADBAND_C, step),
                    prev_device_sp=self._prev_device_sp,
                    pre_write_sp=self._pre_write_sp,
                    frost_floor=FROST_FLOOR_C,
                )
            # K3: log a suppressed device change once (debounced on the reason) so a
            # user whose remote change "did nothing" can see why in the debug log.
            _sup = next(
                (
                    r
                    for r in (_mode_adopt_reason, _sp_adopt_reason)
                    if r
                    in (
                        "echo_window",
                        "own_echo",
                        "opt_out",
                        "safety_window",
                        "safety_frozen",
                        "hold_resumed",
                        "stable_prev",
                        "stable_offset",
                        "no_baseline",
                        "unsupported",
                        "schedule_active",
                    )
                ),
                "",
            )
            if _sup and _sup != self._last_adopt_log:
                _LOGGER.debug(
                    "Poise %s: device change not adopted (mode=%s setpoint=%s)",
                    self._actuator,
                    _mode_adopt_reason or "-",
                    _sp_adopt_reason or "-",
                )
            self._last_adopt_log = _sup
            # P1-4a fix: remember this tick's device reading so next tick can tell a
            # fresh move (user) from a value the device is merely holding (echo of
            # our write, re-quantised/clamped). Updated every tick regardless of the
            # branch below, so a settled offset never re-triggers adoption.
            self._prev_device_sp = actual_sp
            if _adopted_sp is not None:
                self.set_override(_adopted_sp, reason="device_adopt_setpoint")
                # B1 (review v0.168.0): the device now reports the adopted value,
                # so make it the echo baseline. Without this an in-band adoption
                # (the common case, where no write follows because target==device)
                # would be re-detected every tick -> set_override recomputes the
                # expiry from now() forever (the hold never ends, resume_schedule /
                # card-X are undone within a tick) and a store-save fires per tick.
                # Out-of-band adoptions self-correct: the clamped write that follows
                # re-stamps _last_written_sp below.
                # RC review F2: after an adoption the only other legit echo value still
                # in flight is our *previous* command, so make it the pre-write
                # reference. Otherwise a late echo of that command (fresh context,
                # sluggish device) differs from both the adopted value and a stale
                # pre-write -> the three-value rule would re-adopt it and replace the
                # user's hold with a phantom hold of our own old setpoint.
                self._pre_write_sp = self._last_written_sp
                self._last_written_sp = snap_to_step(_adopted_sp, step)
                self._last_sp_write_ts = now
                self._dirty = True  # persist the adopted hold across restarts
            if (
                _actuator_online
                and _adopted_sp is None  # P1-4a: adopted -> skip this tick's write
                # K2: an ``off`` mode-hold writes no setpoint (the adopting tick still
                # runs this block; subsequent ticks take the frost-rescue branch). A
                # setpoint into an off device would fight the user's off intent.
                and self._mode_override != "off"
                # P2-3: while the compressor guard holds a pending mode switch,
                # defer the *new regime's* setpoint. Writing it now would push a
                # cool setpoint into a device still in heat (or vice versa); we
                # hold the old regime (mode + setpoint) until the guard clears.
                and not _mode_nudge_blocked
                and not _reg_throttled
                and should_write(
                    actual_sp,
                    snap_to_step(target, step),
                    mode_changed=mode_changed,
                    deadband=WRITE_DEADBAND_C,
                )
            ):
                cmd = ActuatorCommand(
                    actuator_id=self._actuator,
                    path=ActuatorPath.SETPOINT,
                    value=target,
                    # hvac_mode records the intended *device* mode; the actuator
                    # currently writes temperature only (P2-3 atomic mode+setpoint
                    # write was reverted -- see ADR-0046 §8). Kept for the future
                    # opt-in atomic path and for command-level diagnostics.
                    hvac_mode=desired_hvac,
                    reason="tick",
                )
                try:
                    # V1: the device's reported setpoint just before this write is
                    # the only other value a legit in-window echo can carry (poll
                    # lag), so remember it for next tick's three-value adoption test.
                    self._pre_write_sp = actual_sp
                    # V2: tag the call so the resulting state change carries a
                    # Context we recognise as our own next tick (echo / clamp).
                    await actuator_mod.write(self.hass, cmd, context=self._own_ctx())
                    self._last_written_mode = final_mode
                    self._last_sp_write_ts = now
                    self._last_written_sp = snap_to_step(target, step)  # P1-4a echo
                    self._mark_actuated()  # AR-11 (+F16: persist the flip)
                except Exception:  # noqa: BLE001 - never let actuator I/O kill the tick
                    _LOGGER.exception(
                        "Poise: actuator write failed for %s", self._actuator
                    )
            # feed the true room temperature to a TRV external-temperature input
            # (ADR-0029): the thermostat then modulates against the real sensor.
            if ext_num and ext_ok:
                # ensure the TRV uses its external sensor (pavax-verified); on the
                # tick we switch it, skip the write so the device can settle.
                switched = False
                if self._sensor_select:
                    sel = self.hass.states.get(self._sensor_select)
                    if sel is not None and sel.state not in ("external", "unavailable"):
                        try:
                            await self.hass.services.async_call(
                                "select",
                                "select_option",
                                {
                                    "entity_id": self._sensor_select,
                                    "option": "external",
                                },
                                blocking=False,
                            )
                            switched = True
                        except Exception:  # noqa: BLE001
                            _LOGGER.exception("Poise: sensor-select switch failed")
                if not switched:
                    fed = round(
                        operative_temperature(room, t_mrt)
                        if operative_active
                        else room,
                        1,
                    )
                    if external_feed_due(
                        self._last_fed,
                        fed,
                        last_fed_ts=self._last_fed_ts,
                        now=now,
                        keepalive_s=EXTERNAL_FEED_KEEPALIVE_S,
                        deadband=0.1,
                    ):
                        try:
                            await self.hass.services.async_call(
                                "number",
                                "set_value",
                                {"entity_id": ext_num, "value": fed},
                                blocking=False,
                            )
                            self._last_fed = fed
                            self._last_fed_ts = now
                        except Exception:  # noqa: BLE001 - feed is best-effort
                            _LOGGER.exception(
                                "Poise: external-temp write failed for %s", ext_num
                            )
        else:
            # review V4: a disabled zone still gets unconditional frost/mould
            # protection (README promise) — but rescue-only, so a reasonable
            # manual setpoint above the floor is never fought; a cool-only device
            # has no frost duty and is left alone (frost_rescue_target -> None).
            # K2: a user-held ``off`` (device switched off via the remote, Poise
            # still enabled) is honoured like a disabled zone -- but unlike a truly
            # disabled zone we must NOT treat the warm off device as perpetual frost
            # demand (``frost_rescue_target`` rescues an off heater on principle),
            # or we would restart the device the user deliberately switched off. So
            # an off-HELD zone is rescued only when the ROOM is actually at the
            # frost/mould floor; a disabled zone keeps the unconditional rescue.
            _rescue_ok = (
                (not _off_held)
                or room <= FROST_FLOOR_C
                or (mold_min is not None and room <= mold_min)
            )
            rescue = (
                frost_rescue_target(
                    can_heat=can_heat,
                    actual_sp=_num_attr(act_state, "temperature"),
                    device_state=act_state.state if act_state else None,
                    frost_floor=FROST_FLOOR_C,
                    mold_min=mold_min,
                    deadband=WRITE_DEADBAND_C,
                )
                if _rescue_ok
                else None
            )
            # F2 follow-up: ``frost_rescue_target`` treats "unavailable" as
            # "inactive" on purpose (an off/unknown/unavailable device below the
            # floor all legitimately need the rescue floor) -- but that means it
            # returns a non-None target on EVERY tick for a genuinely offline
            # actuator, and unlike the enabled-branch setpoint write above, this
            # write was never gated on ``_actuator_online``: a disabled zone with
            # a dead actuator got a real ``climate.set_temperature`` dispatched
            # into the void every single tick. Off/unknown (actuator present,
            # just not in "heat") still get the rescue write as before.
            if rescue is not None and _actuator_online:
                _rmodes = (
                    (act_state.attributes.get("hvac_modes") or []) if act_state else []
                )
                _cur = act_state.state if act_state else None
                # Nudge and write are INDEPENDENT: a failed mode-nudge must never
                # skip the safety setpoint write (the floor still has to be sent).
                if _cur != "heat" and "heat" in _rmodes:
                    try:
                        await self.hass.services.async_call(
                            "climate",
                            "set_hvac_mode",
                            {"entity_id": self._actuator, "hvac_mode": "heat"},
                            blocking=False,
                        )
                        # K2: frost-rescue heat is our own safety mode, never a user
                        # change -- stamp the mode echo baseline so it is not adopted.
                        self._last_commanded_hvac = "heat"
                        self._last_hvac_cmd_ts = now
                    except Exception:  # noqa: BLE001 - nudge is best-effort
                        _LOGGER.exception(
                            "Poise: frost rescue nudge failed for %s", self._actuator
                        )
                try:
                    await actuator_mod.write(
                        self.hass,
                        ActuatorCommand(
                            actuator_id=self._actuator,
                            path=ActuatorPath.SETPOINT,
                            value=rescue,
                            hvac_mode="heat",
                            reason="frost_rescue",
                        ),
                    )
                    # B2: the frost floor is our own value, not user intent.
                    self._last_written_sp = None
                    self._mark_actuated()  # AR-11 (+F16: persist the flip)
                except Exception:  # noqa: BLE001 - frost rescue write is best-effort
                    _LOGGER.exception(
                        "Poise: frost rescue write failed for %s", self._actuator
                    )
                # K3 (Inc 3): a frost/mould rescue that fires while an ``off`` hold is
                # active supersedes the user's off intent -- end the hold here with an
                # accurate reason ("frost_rescue") instead of leaving the M3 device
                # escape to end it next tick under the generic "user_resume".
                if _off_held:
                    self._end_hold("frost_rescue")

        await self._maybe_save()

        operative = operative_temperature(room, t_mrt)
        # Predictive solar-shading shadow (ADR-0043): forecast the peak operative
        # temperature (Tier-2 linear while the EKF is not identified, e.g. summer)
        # and what a cover *would* do — diagnostic only, no cover is moved yet.
        # --- Diagnostics-only shadows (review P2/R-4) -----------------------
        # The setpoint is already written above. A failure in any predictive
        # shadow (e.g. a degenerate value from a not-yet-identified EKF) must
        # NEVER take control reporting offline — so the whole block is guarded and
        # degrades to neutral diagnostics while the written setpoint stands.
        binding = "en16798"
        _cover_peak = operative
        _cover_pos = 0.0
        _cover_reason = ""
        shadow_objs: dict[str, Any] = {
            "pi_active": False,
            "pi_setpoint": None,
            "pi_offset": None,
            "multi_active_source": None,
            "multi_reason": "shadow_error",
            "multi_severity": "info",
            "multi_blocked": [],
            "multi_min_off_remaining": 0,
            "multi_device_health": self._multi_lifecycle.health,
            "tpi_active": False,
            "tpi_duty": None,
            "tpi_valve_percent": None,
            "mpc_active": False,
            "mpc_power": None,
            "mpc_weight": None,
            "mpc_setpoint": None,
            "mpc_regime": "hold",
        }
        try:
            _cm = self._ekf.get_model()
            _cover_peak = predict_peak_operative(
                operative,
                t_out_eff,
                [q_solar] * 36,
                alpha=_cm.alpha,
                beta_s=_cm.beta_s,
                dt_h=5.0 / 60.0,
                confident=self._ekf.identified and self._ekf.temperature_std < 0.5,
            )
            _cover_pos, _cover_reason = shading_target_position(
                peak=_cover_peak,
                t_upper=decision.cool_sp,
                current_position=0.0,
                oriented_q=q_solar,
            )
            binding = "mold" if mold_min and mold_min >= decision.heat_sp else "en16798"
            # shadow MPC (ADR-0033): what the predictive controller *would* command
            # against the live EKF state; reported only, dormant until identified.
            shadow = evaluate_shadow(
                identified=self._ekf.identified,
                t_air=room,
                t_out=t_out_eff,
                t_rm=t_rm_eff,
                tau_hours=self._ekf.tau_hours,
                model=self._ekf.get_model(),
                prediction_std=self._ekf.temperature_std,
                confidence=self._ekf.confidence,
                target=decision.heat_sp,
                lower=decision.heat_sp,
                upper=decision.cool_sp,
                params=self._mpc_params,
            )
            # shadow direct-valve TPI duty (ADR-0036): computed + reported only.
            tpi = evaluate_tpi_shadow(
                valve_available=self._valve_entity is not None,
                model=self._ekf.get_model(),
                target=decision.heat_sp,
                room=room,
                t_out=t_out_eff,
            )
            # PI-compensated setpoint shadow (ADR-0037): setpoint-only devices.
            pi = evaluate_pi_shadow(
                self._pi,
                applies=self._valve_entity is None,
                target=decision.heat_sp,
                room=room,
                external=t_out_eff,  # real outdoor temp (review F-1: external==room
                dt_h=TICK_INTERVAL_S / 3600.0,  # killed the k_ext feed-forward term)
            )
            # F-1: the shadow is pure now — advance the persisted integrator here,
            # exactly once per tick, instead of as a hidden side effect of the read.
            if pi.next_acc is not None:
                self._pi.acc = pi.next_acc
            # Phase-1/2 thermal-arbitration shadow (ADR-0046): transient ZoneDevice.
            _act_modes = (
                (act_state.attributes.get("hvac_modes") or []) if act_state else []
            )
            _act_avail = act_state is not None and act_state.state not in (
                "unavailable",
                "unknown",
            )
            # P2: fold the actuator's run-state into the per-device lifecycle on a
            # wall-clock basis, then derive the resolver's min-off / health gate.
            _now_wall = dt_util.utcnow().timestamp()
            _act_action = act_state.attributes.get("hvac_action") if act_state else None
            # ADR-0046 §8 compressor protection (LIVE): the same decision the write
            # path above already applied (_guard_block) — surfaced here as a
            # diagnostic. Evaluated against the pre-observe lifecycle (this tick's
            # run-state is folded in just below) — deliberately, see the K2b note at
            # the guard: folding first would let the guard judge against its own
            # intent and self-armed mode hold. The display policy uses the effective
            # timers so the remaining-time attributes match the live gate.
            _comp_pol = _guard_pol or _lifecycle.LifecyclePolicy(
                min_off_s=_g_min_off, min_mode_hold_s=_g_mode_hold
            )
            _comp_block = _guard_block
            # Fix the conditioning signal: an AC that reports no hvac_action (many
            # ESPHome/IR bridges) would otherwise read as permanently off and never
            # accrue a min-off lock. Fall back to Poise's intended mode (ADR-0024
            # cool-drive parity).
            self._multi_lifecycle = _lifecycle.observe(
                self._multi_lifecycle,
                conditioning=_lifecycle.compressor_running(_act_action, final_mode),
                mode=act_state.state if (act_state and _act_avail) else None,
                now=_now_wall,
                health=(
                    DeviceHealth.OK.value
                    if _act_avail
                    else DeviceHealth.UNAVAILABLE.value
                ),
            )
            _multi_policy = _lifecycle.LifecyclePolicy()
            _multi_runtime = _lifecycle.to_runtime(
                self._multi_lifecycle, _now_wall, _multi_policy
            )
            multi_shadow = evaluate_thermal_shadow(
                EntitySnapshot(
                    entity_id=self._actuator,
                    domain="climate",
                    hvac_modes=tuple(str(m) for m in _act_modes),
                    available=_act_avail,
                ),
                ThermalDemand(_THERMAL_DIR.get(decision.mode), decision.target),
                runtime=_multi_runtime,
            )
            shadow_objs = {
                "pi_active": pi.active,
                "pi_setpoint": pi.setpoint,
                "pi_offset": pi.offset,
                "multi_active_source": multi_shadow.active_source,
                "multi_reason": multi_shadow.reason,
                "multi_severity": multi_shadow.severity,
                "multi_blocked": list(multi_shadow.blocked),
                "multi_min_off_remaining": round(
                    _lifecycle.min_off_remaining(
                        self._multi_lifecycle, _now_wall, _multi_policy
                    )
                ),
                "multi_device_health": self._multi_lifecycle.health,
                "compressor_gate_would_block": _comp_block or "",
                "compressor_mode_hold_remaining": round(
                    _lifecycle.mode_hold_remaining(
                        self._multi_lifecycle, _now_wall, _comp_pol
                    )
                ),
                "tpi_active": tpi.active,
                "tpi_duty": tpi.duty,
                "tpi_valve_percent": tpi.valve_percent,
                "mpc_active": shadow.active,
                "mpc_power": shadow.power,
                "mpc_weight": shadow.weight,
                "mpc_setpoint": shadow.setpoint,
                "mpc_regime": shadow.regime,
            }
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            _LOGGER.exception(
                "Poise: shadow evaluation failed; the written setpoint stands, "
                "diagnostics degraded this tick"
            )
        # valve health (A3): a near-zero closing-step count means the motorised
        # valve failed calibration / is jammed — advisory diagnostic + repair issue.
        closing_steps = self._read(self._valve_closing_steps)
        idle_steps = self._read(self._valve_idle_steps)
        v_stuck = valve_stuck(closing_steps)
        valve_health = (
            "stuck" if v_stuck else ("ok" if closing_steps is not None else "unknown")
        )
        self._issue(
            f"valve_stuck_{self._entry_id}",
            v_stuck,
            translation_key="valve_stuck",
            placeholders={"entity": self._valve_closing_steps or "—"},
        )
        # ADR-0044 outcome scoring + ADR-0045 efficiency report (diagnostic only;
        # never raises — a scoring slip must not break the control tick).
        outcome_diag: dict[str, Any] = {
            "outcome_last_score": None,
            "outcome_ts_avg": None,
            "outcome_obs_avg": None,
            "outcome_n": 0,
            "savings_kwh_month": 0.0,
            "savings_eur_month": 0.0,
            "savings_pct": 0.0,
        }
        try:
            _tick_min = TICK_INTERVAL_S / 60.0
            # F9: real elapsed dt (event-driven refreshes book < 60 s, not a flat
            # tick -- same reasoning as the CA/offset dt below), capped so a masked
            # gap adds ~2 ticks instead of silently over/under-crediting the HDH
            # savings estimate and the outcome-session heating-time integral.
            if self._hdh_last_mono is not None:
                _hd = (now - self._hdh_last_mono) / 60.0
                _hdh_dt = min(max(_hd, 0.0), 2.0 * _tick_min)
            else:
                _hdh_dt = _tick_min
            self._hdh_last_mono = now
            self._hdh = self._hdh.observe(
                comfort=self._comfort_base,
                setpoint=decision.heat_sp,
                outdoor=t_out_eff,
                dt_min=_hdh_dt,
                now_month=dt_util.now().month,
                cfg=self._hdh_cfg,
            )
            self._outcome_session, _fin = observe_session(
                self._outcome_session,
                temp=room,
                target=decision.heat_sp,
                heating=heating,
                controlling=self._enabled,
                dt_min=_hdh_dt,
                expected_minutes=model_expected_minutes(
                    self._ekf.get_model() if self._ekf.identified else None,
                    room=room,
                    target=decision.heat_sp,
                    t_out=t_out_eff,
                    q_solar=q_solar,
                    fallback=float(sched.minutes_to_comfort),
                ),
                q_solar=q_solar,
                outdoor=t_out_eff,
            )
            if _fin is not None:
                self._outcome_stats = self._outcome_stats.observe(
                    _fin.score, _fin.controller
                )
            # ADR-0055 M1 regulation-quality metric (EN 15500-1 CA), SHADOW:
            # score only unmasked comfort ticks (room_decide vs the effective
            # band); the metric gates nothing yet — it must earn trust first.
            if (
                self._enabled
                and not window_open
                and not frozen
                and self._override is None
                and sched.is_comfort
            ):
                # review finding 2: real elapsed (event-driven refreshes book
                # < 60 s, not a flat tick), capped so a masked gap adds ~2 ticks.
                if self._ca_last_mono is not None:
                    _dt = (now - self._ca_last_mono) / 60.0
                    _ca_dt = min(max(_dt, 0.0), 2.0 * _tick_min)
                else:
                    _ca_dt = _tick_min
                self._ca_last_mono = now
                self._regq = self._regq.observe(
                    room=room_decide,
                    heat_sp=decision.heat_sp,
                    cool_sp=eff_cool,
                    mode=mode,
                    dt_min=_ca_dt,
                )
            # ADR-0056 SHADOW: actuator<->room reference-frame offset (no writes).
            # Task 351: fold in a sample only while the actuator is actually
            # conditioning — its internal sensor carries the placement bias only
            # under active airflow/heat, so idle ticks would drag the offset toward
            # zero. Reuse the EKF drive signal (real hvac_action, intent fallback);
            # the warm-up therefore counts real conditioning time. Diagnostic only:
            # the write path stays room-referenced until flip-gated live (ADR-0055).
            if self._ref_last_mono is not None:
                _rd = (now - self._ref_last_mono) / 60.0
                _ref_dt = min(max(_rd, 0.0), 2.0 * _tick_min)
            else:
                _ref_dt = _tick_min
            self._ref_last_mono = now
            _act_raw = (
                act_state.attributes.get("current_temperature") if act_state else None
            )
            try:
                _act_f = float(_act_raw) if _act_raw is not None else None
            except (TypeError, ValueError):
                _act_f = None
            _ref_conditioning = self._last_u_h > 0.0 or self._last_u_c > 0.0
            self._ref_offset = update_offset(
                self._ref_offset,
                actuator_temp=_act_f,
                room_temp=room,
                dt_min=_ref_dt,
                conditioning=_ref_conditioning,
            )
            # Task 343 SHADOW: settle-based τ-confidence — has α (=1/τ) actually
            # converged, not just been counted (ADR-0024)? Fed only on learn-active
            # ticks (the same excitation signal, where α can move); diagnostic only,
            # no writes, until it clamps the preheat lead live (Phase 4, ADR-0055).
            if self._tau_last_mono is not None:
                _td = (now - self._tau_last_mono) / 60.0
                _tau_dt = min(max(_td, 0.0), 2.0 * _tick_min)
            else:
                _tau_dt = _tick_min
            self._tau_last_mono = now
            self._tau_settle = update_settle(
                self._tau_settle,
                alpha=self._ekf.x[1],
                dt_min=_tau_dt,
                learn_active=_ref_conditioning,
            )
            _rep = self._hdh.report(self._hdh_cfg)
            outcome_diag = {
                "outcome_last_score": self._outcome_stats.last_score,
                "outcome_ts_avg": self._outcome_stats.ts_avg,
                "outcome_obs_avg": self._outcome_stats.obs_avg,
                "outcome_n": self._outcome_stats.ts_n + self._outcome_stats.obs_n,
                "savings_kwh_month": _rep["kwh"],
                "savings_eur_month": _rep["eur"],
                "savings_pct": _rep["pct"],
                "ca_deviation_k": round(self._regq.deviation_k, 3),
                "ca_time_in_band": self._regq.time_in_band_pct,
                "ca_cycles_per_h": round(self._regq.cycles_per_hour, 2),
                "ca_minutes": round(self._regq.minutes, 0),
                "ref_offset": (
                    round(self._ref_offset.offset, 2)
                    if self._ref_offset is not None
                    else None
                ),
                "ref_offset_dev": (
                    round(self._ref_offset.deviation, 2)
                    if self._ref_offset is not None
                    else None
                ),
                "ref_offset_trusted": (
                    self._ref_offset.trusted if self._ref_offset is not None else None
                ),
                "ref_offset_conditioning": _ref_conditioning,
                "tau_confidence": round(settle_confidence(self._tau_settle), 3),
                "tau_settled": (
                    self._tau_settle.settled if self._tau_settle is not None else None
                ),
                "tau_settle_minutes": (
                    round(self._tau_settle.minutes, 0)
                    if self._tau_settle is not None
                    else None
                ),
                "cool_sp_compensated": (
                    compensated_setpoint(eff_cool, self._ref_offset, enabled=True)
                    if self._ref_offset is not None
                    else None
                ),
            }
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            _LOGGER.debug("Poise outcome/savings diagnostics failed", exc_info=True)
        _tick_data: dict[str, Any] = {
            "available": True,
            **outcome_diag,
            **climate_diag,
            "dynamics_profile": self._dynamics.value,
            "pi_integral_time_h": round(PROFILES[self._dynamics].integral_time_h, 3),
            "reg_period_s": PROFILES[self._dynamics].regulation_period_s,
            # ADR-0046 §8 (live): the compressor-guard suppression reason this tick
            # ("" = not blocked). When set, dry_active reads as intent (queued),
            # not "drying now" — the card shows "drying soon (compressor guard)".
            "mode_nudge_blocked": _mode_nudge_blocked,
            # H3/ADR-0038: monotonic stamp of when this snapshot was produced, so
            # the system hub can detect a silently stale zone (age-based staleness).
            "mono_ts": now,
            "current_temperature": round(room, 1),
            "current_humidity": round(rh, 1) if rh is not None else None,
            "target_temperature": target,
            "operative_temperature": round(operative, 1),
            "t_rm": round(t_rm_eff, 1),
            "t_rm_source": t_rm_source,
            "t_rm_internal": (
                round(self._trm_tracker.current, 1)
                if self._trm_tracker.current is not None
                else None
            ),
            "q_solar": round(q_solar, 3),
            "q_solar_source": q_solar_source,
            "q_solar_internal": round(q_solar_internal, 3),
            "beta_s": round(self._ekf.get_model().beta_s, 3),
            "mrt": round(t_mrt, 1),
            "mrt_source": mrt_source,
            "mrt_internal": round(mrt_internal, 1),
            "heat_sp": decision.heat_sp,
            "cool_sp": decision.cool_sp,
            "mode": mode,
            "comfort_low": decision.heat_sp,
            "comfort_high": decision.cool_sp,
            "binding_lower_cause": binding,
            "category": self._category.value,
            "adaptive_cool": adaptive_cool,
            "adaptive_cool_mode": adaptive_cool_mode(self._adaptive_cool_cfg),
            "heating": heating,
            # Display contract (review 2026-07-13, D2-D4): publish the arbitrated
            # direction (final_mode) and the actuator's own reported action so the
            # entity's hvac_action stays truthful during an override (where the raw
            # mode is "manual") and can prefer the device's real state. "cooling" is
            # published symmetric to "heating" (raw intent) to close the asymmetry.
            "cooling": cooling,
            "final_mode": final_mode,
            "actuator_hvac_action": (
                act_state.attributes.get("hvac_action") if act_state else None
            ),
            "idle_park_mode": _idle_park_mode,
            "window_open": window_open,
            "window_auto_detected": self._window_auto.open,
            "window_auto_threshold": round(self._wa_open_threshold, 1),
            "window_bypass": self._window_bypass,
            "preset": self._preset.value,
            # K2 (M4): a mode-hold (possibly without a setpoint) is an active hold too,
            # so the Card shows the pill / "gilt bis …" / resume for it.
            "override_active": (
                self._override is not None or self._mode_override is not None
            ),
            "mode_override": self._mode_override,
            # K3 (Inc 3): hold origin (ui_setpoint / device_adopt_*) + why this tick
            # did/did not adopt a device change (diagnostics; "" when nothing seen).
            "override_reason": self._override_reason,
            "mode_adopt_reason": _mode_adopt_reason,
            "sp_adopt_reason": _sp_adopt_reason,
            # ADR-0059 §4: the manual-hold lifecycle for the Card ("gilt bis …").
            "override_expires_at": _iso_utc(self._override_expires_at),
            "override_policy": self._override_policy,
            "override_requested": self._override_requested,
            # ADR-0059 §5: the persisted L1 nudge log (observe-only). A shadow key
            # (absent from _ATTRS) -> diagnostics-only, never a recorded attribute.
            "override_stats": list(self._override_stats),
            "boost_expires_at": _iso_utc(self._boost_expires_at),
            "override_clamped": override_clamped,
            "cover_predicted_peak": round(_cover_peak, 1),
            "cover_would_shade": _cover_pos > 0,
            "cover_shade_position": _cover_pos,
            "cover_shade_reason": _cover_reason,
            "window_auto_slope": self._window_auto.ema_slope,
            "heating_failure": failed,
            "mold_capped": mold_capped,  # F15: mould floor clipped at 24 °C
            # ADR-0057: publish the mould-protection floor + dewpoint so the card
            # can draw the "Schimmel" tick on the dial (display only, no control).
            "mould_floor": round(mold_min, 1) if mold_min is not None else None,
            "dewpoint": round(dewpoint, 1) if dewpoint is not None else None,
            "source": reading.source.value,
            "tau_hours": round(self._ekf.tau_hours, 1),
            "confidence": round(self._ekf.confidence, 2),
            "identified": self._ekf.identified,
            "learning_phase": self._ekf.learning_phase,
            "identification_progress": round(self._ekf.data_factor, 2),
            "schedule_state": "comfort" if sched.is_comfort else "setback",
            "minutes_to_comfort": sched.minutes_to_comfort,
            "preheating": preheating,
            "preheat_outdoor": preheat_outdoor,
            "coasting": coasting,
            "minutes_to_setback": sched.minutes_to_setback,
            "sensor_frozen": frozen,
            "norm_binding": norm_binding,
            "binding_precedence": binding_precedence,
            "device_schedule_active": sched_active,
            "device_alarm": fault_active,
            "sensor_placement_suspect": heat_source_suspect,
            "trv_input_mode": (
                "operative" if operative_active else ("air" if ext_num else "none")
            ),
            "valve_health": valve_health,
            "valve_closing_steps": closing_steps,
            "valve_idle_steps": idle_steps,
            **shadow_objs,
            "tpi_valve_entity": self._valve_entity,
            "seasonless_phase": self._seasonless.phase,
            "seasonless_rate": (
                round(p, 3)
                if (
                    p := self._seasonless.heat_rate_prior(
                        decision.heat_sp, t_out_eff, dt_util.now().toordinal()
                    )
                )
                is not None
                else None
            ),
        }
        # R13: surface this zone's own boiler heat-demand (0..1) -- exactly the
        # value the hub aggregates from our data, so per-zone visibility can't drift.
        _tick_data["heat_demand"] = zone_heat_demand(
            heating=heating,
            tpi_duty=_tick_data.get("tpi_duty"),
            frozen=frozen,
        )
        # R11 trace v2: capture the REAL actuator mode + action so a replayed
        # trace can explain a dehumidification episode. The v1 schema recorded
        # only Poise's thermal ``mode`` (idle/cool/heat/off) and never the
        # humidity/device axis, so dry episodes were invisible on disk.
        _tick_data["device_hvac_mode"] = act_state.state if act_state else ""
        _tick_data["hvac_action"] = (
            (act_state.attributes.get("hvac_action") or "") if act_state else ""
        )
        await self._maybe_record_trace(
            _tick_data, room=room, t_out=t_out_eff, rh=rh, t_rm=t_rm_eff, now=now
        )
        return _tick_data
