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
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .adaptive_cool import adaptive_cool_mode
from .clock import Clock, MonotonicClock
from .comfort.dual_setpoint import ComfortDecision
from .comfort.dual_setpoint import decide as comfort_decide
from .comfort.en16798 import HEATING_LOWER, HEATING_UPPER
from .comfort.humidity import humidity_decide
from .comfort.operative import operative_temperature
from .comfort.presence import (
    PresenceLevel,
    any_present,
    resolve_presence,
    step_room_absence,
)
from .comfort.schedule import ScheduleState
from .comfort.thermal_shock import (
    adaptive_cool_setpoint,
    rate_limit,
)
from .const import (
    CONF_CLIMATE_MODE,
    CONF_ENTRY_TYPE,
    DEFAULT_OVERRIDE_POLICY,
    DEFAULT_TRACE_MAX_BYTES,
    DEVICE_MAX_C,
    DOMAIN,
    EKF_SAVE_EVERY_TICKS,
    ENTRY_TYPE_SYSTEM,
    EXTERNAL_FEED_KEEPALIVE_S,
    FROST_FLOOR_C,
    TICK_INTERVAL_S,
    UNAVAILABLE_SAFE_AFTER_S,
    WINDOW_MOULD_SUPPRESS_S,
    WRITE_DEADBAND_C,
)
from .contracts import ActuatorCommand, ActuatorPath
from .control import override_runtime
from .control.cover_shading import (
    predict_peak_operative,
    shading_target_position,
)
from .control.dynamics import (
    PROFILES,
    DeviceDynamics,
)
from .control.hdh_savings import HdhSavings
from .control.hub_aggregate import zone_heat_demand
from .control.lifecycle import resolve_safe_state
from .control.mpc import MpcParams
from .control.mpc_shadow import evaluate_shadow
from .control.optimal_start import plan_preheat
from .control.outcome_scoring import (
    OutcomeSession,
    OutcomeStats,
    observe_session,
)
from .control.override import (
    OverrideConfig,
    OverrideMode,
    hold_ends_at_preheat,
    mode_adopt_reason,
    mode_comfort_base,
    setpoint_adopt_reason,
)
from .control.pi import PiCompensator
from .control.pi_shadow import evaluate_pi_shadow
from .control.reference_offset import (
    OffsetEstimate,
    update_offset,
)
from .control.regulation_quality import RegulationQuality
from .control.scoring_expectation import model_expected_minutes
from .control.tick_budget import TickBudget
from .control.tick_resolve import (
    external_feed_due,
    frost_rescue_target,
    idle_park,
    needs_mode_nudge,
    resolve_desired_mode,
    resolve_write_target,
)
from .control.tpi_shadow import evaluate_tpi_shadow
from .control.window_auto import (
    WindowAutoConfig,
    WindowAutoState,
    effective_window_open,
)
from .devices.model_fixes import (
    ext_temp_number_is_implausible,
)
from .diagnostics.collector import DiagnosticsCollector
from .diagnostics.shadows import (
    assemble_shadow_objs,
    build_outcome_diag,
    capped_elapsed_min,
    compose_climate_band,
    evaluate_cover_shadow,
    evaluate_multi_shadow,
    neutral_shadow_objs,
)
from .diagnostics.trace import build_tick_record
from .estimation.heatup_rate import HeatupAccumulator
from .estimation.psychrometrics import dewpoint as psychro_dewpoint
from .estimation.psychrometrics import humidity_ratio
from .estimation.running_mean import RunningMeanTracker
from .estimation.seasonless_rate import SeasonlessRate
from .estimation.tau_settle import TauSettle, update_settle
from .estimation.thermal_ekf import ThermalEKF, ThermalModel
from .ha.actuator_executor import ActuatorExecutor
from .ha.forecast_provider import ForecastProvider
from .ha.input_reader import InputReader, parse_attr_number
from .ha.presenter import iso_utc as _iso_utc
from .ha.presenter import present as _present
from .ingestion import ingest_temperature
from .multi import lifecycle as _lifecycle
from .multi.model import DeviceHealth, Direction
from .multi.shadow import evaluate_thermal_shadow
from .persistence import codec as _codec
from .persistence.migrations import migrate_v0_bare_ekf
from .runtime.config import (
    HoldTuning,
    HotApplyConfig,
    MissingStructuralFieldError,
    ZoneConfig,
)
from .runtime.tick_inputs import TickInputs
from .runtime.tick_result import (
    ActuatorPlan,
    AvailableTickData,
    ClimateBandResult,
    CommitResult,
    EndHold,
    ExecutionReport,
    ExternalTemperaturePlan,
    FinalizeContext,
    HealthUpdate,
    HoldRoutingResult,
    IngestResult,
    IntentsResult,
    ModeAdoptionResult,
    ModeNudgeResult,
    ModeResolutionResult,
    ObservationResult,
    OperativeResult,
    OverrideEnded,
    PersistencePhase,
    PostExecutionAction,
    PrepareContinuation,
    PreparedState,
    PresenceLevelResult,
    SafetyFloorsResult,
    ScheduleGateResult,
    SchedulePresenceResult,
    SetpointObservation,
    ShadowStageResult,
    TickOutcome,
    TickPlan,
    TickStageError,
    UnavailableTickData,
    ValveHealthResult,
    WriteTargetResult,
)
from .runtime.zone_runtime import ZoneRuntime
from .safety.heating_failure import (
    HeatingFailureDetector,
    actuator_running,
)
from .safety.sensor_watchdog import (
    frozen_safe_target,
    is_frozen,
    unavailable_safe_engaged,
    valve_stuck,
)
from .storage import PoiseStore
from .trace.recorder import TraceRecorder

_LOGGER = logging.getLogger(__name__)
# Conservative outdoor default when neither a sensor nor the running mean is
# known — mirrors control.mpc_controller._FALLBACK_T_OUT_C (a cold-ish day keeps
# heating engaged rather than mild-locking it out).
_FALLBACK_OUTDOOR_C = 5.0
# Comfort mode -> thermal-arbitration direction (ADR-0046 P1 shadow). "idle" and
# any other value map to None (no thermal demand).
_THERMAL_DIR: dict[str, Direction] = {"heat": Direction.HEAT, "cool": Direction.COOL}


def _utcnow_ts() -> float:
    """Wall-clock epoch for the override-lifecycle commands.

    Injected into ``control.override_runtime`` as ``now_utc_fn`` so the pure
    lifecycle functions read ``dt_util.utcnow()`` only on the paths that
    consult the clock (never, e.g., on a hold clear).
    """
    return dt_util.utcnow().timestamp()


def _local_minute_now() -> int:
    """Local minute-of-day (the ``dt_util.now()`` read of the switchpoint
    lookup and the §5 stat's schedule phase), evaluated at call time."""
    _lnow = dt_util.now()
    return int(_lnow.hour * 60 + _lnow.minute)


class _ReaderClock:
    """Live view of the coordinator's injectable clock.

    The ``InputReader`` is constructed once in ``__init__``, but integration
    tests swap ``coord._clock`` for a fake after setup — so the reader gets
    this forwarder instead of a snapshot of the reference, and the snapshot
    instants follow the live clock exactly like every direct clock read.
    """

    __slots__ = ("_coordinator",)

    def __init__(self, coordinator: PoiseCoordinator) -> None:
        self._coordinator = coordinator

    def monotonic(self) -> float:
        return self._coordinator._clock.monotonic()


class PoiseCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """One coordinator per room; capability-aware dual-setpoint each tick."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_S),
            # The snapshot carries a per-tick monotonic heartbeat ("mono_ts",
            # ADR-0038 hub staleness) that differs every tick, so the data is
            # never equal tick-to-tick: always_update=False could never skip.
            # (Refresh storms from input churn are cut by the _on_change filter.)
            always_update=True,
        )
        # One ZoneRuntime owns the long-lived domain-state groups
        # (runtime/state.py) plus the injectable clock; every moved attribute
        # keeps its ``self._*`` name as a property proxy (getter+setter)
        # defined right after ``__init__``. ``climate_mode`` is Store-owned
        # user intent, deliberately OUTSIDE the shared parser: the
        # options/data value only seeds the very first start, async_bootstrap
        # restores the live selection, and async_apply_options never
        # re-applies the stale options form — so it is injected here instead
        # of taking the dataclass default.
        self._zone_runtime = ZoneRuntime(
            MonotonicClock(),
            climate_mode={**entry.data, **entry.options}.get(CONF_CLIMATE_MODE, "auto"),
        )
        # ADR-0041 window-auto config (config-owned, stays an adapter
        # attribute); ``WindowRuntime.wa_open_threshold`` defaults to this
        # config's ``open_threshold``.
        self._window_auto_cfg = WindowAutoConfig()
        # ``_dirty`` (override/enabled/mode changed -> persist next save) is
        # proxied below onto ``ZoneRuntime.dirty``: the moved pure bodies
        # (commit/teardown/mark_actuated/observe) mutate it, so the runtime
        # owns the flag and seeds it False.
        self._store = PoiseStore(hass, entry.entry_id)
        self._save_counter = 0
        # Silver log-when-unavailable: log the loss/recovery of the room sensor
        # exactly once each, not every 60 s tick.
        self._unavailable_logged = False
        self._entry_id = entry.entry_id
        self._data_snapshot: dict[str, Any] = dict(entry.data)  # reconfigure guard
        self._save_failures = 0  # consecutive store-save failures
        self._tick_failures = 0  # consecutive _run_once failures
        self._active_issues: set[str] = set()
        self._lock = asyncio.Lock()
        self._override_policy: str = DEFAULT_OVERRIDE_POLICY
        self._climate_entity_id: str | None = None  # for the ended-event payload
        self._override_cfg = OverrideConfig()
        # One parser (runtime/config.py) feeds __init__ and
        # async_apply_options: a single merged read, options over data, also
        # for structural keys; this adapter only assigns the parsed values
        # onto its attributes. HoldTuning parses first, mirroring the read
        # order (override options before the structural require reads).
        hold = HoldTuning.from_entry(entry)  # ADR-0059 §1/§2 hold/Boost tuning
        try:
            cfg = ZoneConfig.from_entry(entry)
        except MissingStructuralFieldError as err:
            # A corrupt entry missing a structural field must fail setup
            # cleanly (ConfigEntryError -> SETUP_ERROR + repair flow), not
            # raise an uncaught KeyError; the pure parser signals it and only
            # this adapter knows the entry id for the message.
            raise ConfigEntryError(
                f"Poise entry '{entry.entry_id}' is missing the required "
                f"'{err.key}' setting; reconfigure the zone."
            ) from err
        structure = cfg.structure
        self.zone_name: str = structure.zone_name
        # opt-in field-trace recorder (ADR-0011 golden-file replay); default off.
        self._trace_recorder: TraceRecorder | None = None
        self._trace_slug: str = entry.entry_id
        self._tick_budget = TickBudget()  # ADR-0020 per-tick compute-time budget
        self._temp: str = structure.temperature_sensor
        self._actuator: str = structure.actuator
        self._trm: str | None = structure.trm
        self._outdoor: str | None = structure.outdoor
        self._humidity: str | None = structure.humidity
        self._mrt: str | None = structure.mrt
        # window: multiple=True, structural (data) -> re-read only on reload.
        self._windows: list[str] = list(structure.windows)
        # ADR-0052: ``_mpc_params`` is per-tick derived tuning state (defaults
        # until the first tick derives it from the live actuator; an options
        # hot-apply never resets it) — config-shaped, so it stays an adapter
        # attribute; the sibling ``_dynamics`` profile lives in
        # ``CompressorRuntime``.
        self._mpc_params = MpcParams()
        self._weather: str | None = structure.weather
        self._irradiance: str | None = structure.irradiance
        self._trv_ext_temp: str | None = structure.trv_ext_temp
        # Adopt device-side setpoint/mode changes as manual holds. Parsed as
        # tuning but applied ONLY here: async_apply_options does not re-read
        # them, so they stay deliberately absent from _apply_hot_tuning.
        self._adopt_external_setpoint: bool = cfg.tuning.adopt_external_setpoint
        self._adopt_external_mode: bool = cfg.tuning.adopt_external_mode
        # The single READING HA adapter: owns every ``states.get`` primitive
        # plus the device-guard discovery state. Constructed BEFORE the
        # hot-tuning apply so the apply can sync the options-owned presence
        # lists into the reader unconditionally, and handed a live clock
        # forwarder so a test-swapped ``_clock`` governs the snapshot
        # instants too.
        self._input_reader = InputReader(hass, structure, _ReaderClock(self))
        # The single WRITING HA adapter: owns the four bare call primitives
        # (exact payloads, blocking=False, context passthrough) and the run_*
        # sequence methods with the per-effect try boundaries. This module's
        # ``_LOGGER`` is injected so every boundary record keeps the channel
        # ``custom_components.poise.coordinator`` (the logger channel is
        # behaviour).
        self._actuator_executor = ActuatorExecutor(hass, logger=_LOGGER)
        # Forecast fetch + TTL cache; the cache state lives in the provider.
        # Same live clock forwarder as the reader, so a test-swapped
        # ``_clock`` keeps governing the TTL/backoff instants. This module's
        # ``_LOGGER`` is passed in so the failure-path debug record keeps the
        # logger name ``custom_components.poise.coordinator`` (channel
        # identity for per-module logger configs).
        self._forecast_provider = ForecastProvider(hass, _ReaderClock(self), _LOGGER)
        # The ONE broad boundary for the pure outcome/savings diagnostics.
        # This module's ``_LOGGER`` is injected so the swallow record keeps
        # the channel ``custom_components.poise.coordinator``, with identical
        # text/level/exc_info.
        self._diag_collector = DiagnosticsCollector(_LOGGER)
        # Every hot-applyable field flows through the ONE shared apply method,
        # so the init and options paths can never drift. The already parsed
        # pieces are bundled without a re-parse: __init__ keeps its
        # require-before-tuning throw order, while async_apply_options parses
        # HotApplyConfig directly (no structural reads).
        self._apply_hot_tuning(HotApplyConfig.from_zone_config(cfg, hold))

    # ------------------------------------------------------------------
    # Property proxies onto the ZoneRuntime state groups.
    #
    # Every long-lived domain-state attribute that moved into
    # ``self._zone_runtime`` keeps its ``self._*`` name as a getter+setter
    # pair, so every internal reader, the persistence encode path and every
    # test pin keep working unchanged. The proxies are deliberately uniform
    # — one return / one assignment; the consistency gate
    # ``tests/test_phase6b_state_move.py`` parses exactly this shape and
    # cross-checks it against the state-group fields and their
    # ``PERSISTED_FIELDS``. The domain narratives live on the group fields
    # in ``runtime/state.py``.
    #
    # ``_clock`` proxies the runtime's injectable clock: the test idiom
    # ``coord._clock = FakeClock(...)`` replaces ``zone_runtime.clock``,
    # which every reader follows — direct ``self._clock`` reads here via
    # this property, the InputReader/ForecastProvider via their live
    # ``_ReaderClock`` forwarders (which call back into this property).
    # ------------------------------------------------------------------

    @property
    def _clock(self) -> Clock:
        return self._zone_runtime.clock

    @_clock.setter
    def _clock(self, value: Clock) -> None:
        self._zone_runtime.clock = value

    # The persistence-meta dirty flag lives on the runtime
    # (``ZoneRuntime.dirty``) because the moved pure bodies mutate it; the
    # save DECISION (``_maybe_save``) stays adapter logic and reads/clears it
    # through this proxy.

    @property
    def _dirty(self) -> bool:
        return self._zone_runtime.dirty

    @_dirty.setter
    def _dirty(self, value: bool) -> None:
        self._zone_runtime.dirty = value

    @property
    def _enabled(self) -> bool:
        return self._zone_runtime.user.enabled

    @_enabled.setter
    def _enabled(self, value: bool) -> None:
        self._zone_runtime.user.enabled = value

    @property
    def _preset(self) -> OverrideMode:
        return self._zone_runtime.user.preset

    @_preset.setter
    def _preset(self, value: OverrideMode) -> None:
        self._zone_runtime.user.preset = value

    # Store-owned; seeded from the entry at ZoneRuntime construction.
    @property
    def _climate_mode(self) -> str:
        return self._zone_runtime.user.climate_mode

    @_climate_mode.setter
    def _climate_mode(self, value: str) -> None:
        self._zone_runtime.user.climate_mode = value

    @property
    def _window_bypass(self) -> bool:
        return self._zone_runtime.user.window_bypass

    @_window_bypass.setter
    def _window_bypass(self, value: bool) -> None:
        self._zone_runtime.user.window_bypass = value

    @property
    def _override(self) -> float | None:
        return self._zone_runtime.user.override

    @_override.setter
    def _override(self, value: float | None) -> None:
        self._zone_runtime.user.override = value

    # Device-side hvac_mode adopted as a manual mode-hold; shares the
    # setpoint hold's lifecycle (an ``off`` hold routes through frost-rescue).
    @property
    def _mode_override(self) -> str | None:
        return self._zone_runtime.user.mode_override

    @_mode_override.setter
    def _mode_override(self, value: str | None) -> None:
        self._zone_runtime.user.mode_override = value

    @property
    def _override_set_wall(self) -> float | None:
        return self._zone_runtime.user.override_set_wall

    @_override_set_wall.setter
    def _override_set_wall(self, value: float | None) -> None:
        self._zone_runtime.user.override_set_wall = value

    @property
    def _override_requested(self) -> float | None:
        return self._zone_runtime.user.override_requested

    @_override_requested.setter
    def _override_requested(self, value: float | None) -> None:
        self._zone_runtime.user.override_requested = value

    @property
    def _override_expires_at(self) -> float | None:
        return self._zone_runtime.user.override_expires_at

    @_override_expires_at.setter
    def _override_expires_at(self, value: float | None) -> None:
        self._zone_runtime.user.override_expires_at = value

    @property
    def _override_expiry_is_switchpoint(self) -> bool:
        return self._zone_runtime.user.override_expiry_is_switchpoint

    @_override_expiry_is_switchpoint.setter
    def _override_expiry_is_switchpoint(self, value: bool) -> None:
        self._zone_runtime.user.override_expiry_is_switchpoint = value

    # Origin of the active hold (ui_setpoint / device_adopt_* / ...).
    @property
    def _override_reason(self) -> str | None:
        return self._zone_runtime.user.override_reason

    @_override_reason.setter
    def _override_reason(self, value: str | None) -> None:
        self._zone_runtime.user.override_reason = value

    @property
    def _boost_expires_at(self) -> float | None:
        return self._zone_runtime.user.boost_expires_at

    @_boost_expires_at.setter
    def _boost_expires_at(self, value: float | None) -> None:
        self._zone_runtime.user.boost_expires_at = value

    @property
    def _boost_prev_preset(self) -> OverrideMode | None:
        return self._zone_runtime.user.boost_prev_preset

    @_boost_prev_preset.setter
    def _boost_prev_preset(self, value: OverrideMode | None) -> None:
        self._zone_runtime.user.boost_prev_preset = value

    @property
    def _override_stats(self) -> list[dict[str, Any]]:
        return self._zone_runtime.user.override_stats

    @_override_stats.setter
    def _override_stats(self, value: list[dict[str, Any]]) -> None:
        self._zone_runtime.user.override_stats = value

    @property
    def _last_adopt_log(self) -> str:
        return self._zone_runtime.user.last_adopt_log

    @_last_adopt_log.setter
    def _last_adopt_log(self, value: str) -> None:
        self._zone_runtime.user.last_adopt_log = value

    # Echo baseline: the last commanded (snapped) setpoint.
    @property
    def _last_written_sp(self) -> float | None:
        return self._zone_runtime.external.last_written_sp

    @_last_written_sp.setter
    def _last_written_sp(self, value: float | None) -> None:
        self._zone_runtime.external.last_written_sp = value

    # Move-guard: device setpoint at the previous tick.
    @property
    def _prev_device_sp(self) -> float | None:
        return self._zone_runtime.external.prev_device_sp

    @_prev_device_sp.setter
    def _prev_device_sp(self, value: float | None) -> None:
        self._zone_runtime.external.prev_device_sp = value

    # Mode echo baseline (analogue of ``_last_written_sp``).
    @property
    def _last_commanded_hvac(self) -> str | None:
        return self._zone_runtime.external.last_commanded_hvac

    @_last_commanded_hvac.setter
    def _last_commanded_hvac(self, value: str | None) -> None:
        self._zone_runtime.external.last_commanded_hvac = value

    @property
    def _prev_device_mode(self) -> str | None:
        return self._zone_runtime.external.prev_device_mode

    @_prev_device_mode.setter
    def _prev_device_mode(self, value: str | None) -> None:
        self._zone_runtime.external.prev_device_mode = value

    # ADR-0052 §4 nudge throttle.
    @property
    def _last_sp_write_ts(self) -> float | None:
        return self._zone_runtime.external.last_sp_write_ts

    @_last_sp_write_ts.setter
    def _last_sp_write_ts(self, value: float | None) -> None:
        self._zone_runtime.external.last_sp_write_ts = value

    @property
    def _last_hvac_cmd_ts(self) -> float | None:
        return self._zone_runtime.external.last_hvac_cmd_ts

    @_last_hvac_cmd_ts.setter
    def _last_hvac_cmd_ts(self, value: float | None) -> None:
        self._zone_runtime.external.last_hvac_cmd_ts = value

    # Attempt-state: device setpoint captured immediately before our last
    # write (updated even when the write call fails).
    @property
    def _pre_write_sp(self) -> float | None:
        return self._zone_runtime.external.pre_write_sp

    @_pre_write_sp.setter
    def _pre_write_sp(self, value: float | None) -> None:
        self._zone_runtime.external.pre_write_sp = value

    # Attempt-state: own-write HA Context ids; ``commit_execution``
    # registers them even on a failed dispatch.
    @property
    def _own_write_ctx_ids(self) -> deque[str]:
        return self._zone_runtime.external.own_write_ctx_ids

    @_own_write_ctx_ids.setter
    def _own_write_ctx_ids(self, value: deque[str]) -> None:
        self._zone_runtime.external.own_write_ctx_ids = value

    @property
    def _last_target(self) -> float | None:
        return self._zone_runtime.actuator.last_target

    @_last_target.setter
    def _last_target(self, value: float | None) -> None:
        self._zone_runtime.actuator.last_target = value

    @property
    def _last_written_mode(self) -> str | None:
        return self._zone_runtime.actuator.last_written_mode

    @_last_written_mode.setter
    def _last_written_mode(self, value: str | None) -> None:
        self._zone_runtime.actuator.last_written_mode = value

    # True once any write SUCCEEDED this run; gates the teardown park.
    # Persisted + restored.
    @property
    def _has_actuated(self) -> bool:
        return self._zone_runtime.actuator.has_actuated

    @_has_actuated.setter
    def _has_actuated(self, value: bool) -> None:
        self._zone_runtime.actuator.has_actuated = value

    @property
    def _last_fed(self) -> float | None:
        return self._zone_runtime.actuator.last_fed

    @_last_fed.setter
    def _last_fed(self, value: float | None) -> None:
        self._zone_runtime.actuator.last_fed = value

    # External-feed keep-alive (monotonic).
    @property
    def _last_fed_ts(self) -> float:
        return self._zone_runtime.actuator.last_fed_ts

    @_last_fed_ts.setter
    def _last_fed_ts(self, value: float) -> None:
        self._zone_runtime.actuator.last_fed_ts = value

    @property
    def _ekf(self) -> ThermalEKF:
        return self._zone_runtime.learning.ekf

    @_ekf.setter
    def _ekf(self, value: ThermalEKF) -> None:
        self._zone_runtime.learning.ekf = value

    @property
    def _trm_tracker(self) -> RunningMeanTracker:
        return self._zone_runtime.learning.trm_tracker

    @_trm_tracker.setter
    def _trm_tracker(self, value: RunningMeanTracker) -> None:
        self._zone_runtime.learning.trm_tracker = value

    @property
    def _seasonless(self) -> SeasonlessRate:
        return self._zone_runtime.learning.seasonless

    @_seasonless.setter
    def _seasonless(self, value: SeasonlessRate) -> None:
        self._zone_runtime.learning.seasonless = value

    @property
    def _prev_room(self) -> float | None:
        return self._zone_runtime.learning.prev_room

    @_prev_room.setter
    def _prev_room(self, value: float | None) -> None:
        self._zone_runtime.learning.prev_room = value

    @property
    def _prev_room_mono(self) -> float | None:
        return self._zone_runtime.learning.prev_room_mono

    @_prev_room_mono.setter
    def _prev_room_mono(self, value: float | None) -> None:
        self._zone_runtime.learning.prev_room_mono = value

    @property
    def _heatup_acc(self) -> HeatupAccumulator:
        return self._zone_runtime.learning.heatup_acc

    @_heatup_acc.setter
    def _heatup_acc(self, value: HeatupAccumulator) -> None:
        self._zone_runtime.learning.heatup_acc = value

    @property
    def _last_mono(self) -> float | None:
        return self._zone_runtime.learning.last_mono

    @_last_mono.setter
    def _last_mono(self, value: float | None) -> None:
        self._zone_runtime.learning.last_mono = value

    @property
    def _last_u_h(self) -> float:
        return self._zone_runtime.learning.last_u_h

    @_last_u_h.setter
    def _last_u_h(self, value: float) -> None:
        self._zone_runtime.learning.last_u_h = value

    @property
    def _last_u_c(self) -> float:
        return self._zone_runtime.learning.last_u_c

    @_last_u_c.setter
    def _last_u_c(self, value: float) -> None:
        self._zone_runtime.learning.last_u_c = value

    @property
    def _last_q_solar(self) -> float:
        return self._zone_runtime.learning.last_q_solar

    @_last_q_solar.setter
    def _last_q_solar(self, value: float) -> None:
        self._zone_runtime.learning.last_q_solar = value

    # ADR-0056 actuator<->room reference offset.
    @property
    def _ref_offset(self) -> OffsetEstimate | None:
        return self._zone_runtime.learning.ref_offset

    @_ref_offset.setter
    def _ref_offset(self, value: OffsetEstimate | None) -> None:
        self._zone_runtime.learning.ref_offset = value

    @property
    def _ref_last_mono(self) -> float | None:
        return self._zone_runtime.learning.ref_last_mono

    @_ref_last_mono.setter
    def _ref_last_mono(self, value: float | None) -> None:
        self._zone_runtime.learning.ref_last_mono = value

    # Settle-based tau-confidence.
    @property
    def _tau_settle(self) -> TauSettle | None:
        return self._zone_runtime.learning.tau_settle

    @_tau_settle.setter
    def _tau_settle(self, value: TauSettle | None) -> None:
        self._zone_runtime.learning.tau_settle = value

    @property
    def _tau_last_mono(self) -> float | None:
        return self._zone_runtime.learning.tau_last_mono

    @_tau_last_mono.setter
    def _tau_last_mono(self, value: float | None) -> None:
        self._zone_runtime.learning.tau_last_mono = value

    # Transient by design (F-PIACC).
    @property
    def _pi(self) -> PiCompensator:
        return self._zone_runtime.learning.pi

    @_pi.setter
    def _pi(self, value: PiCompensator) -> None:
        self._zone_runtime.learning.pi = value

    @property
    def _window_auto(self) -> WindowAutoState:
        return self._zone_runtime.window.window_auto

    @_window_auto.setter
    def _window_auto(self, value: WindowAutoState) -> None:
        self._zone_runtime.window.window_auto = value

    @property
    def _was_cooling(self) -> bool:
        return self._zone_runtime.window.was_cooling

    @_was_cooling.setter
    def _was_cooling(self, value: bool) -> None:
        self._zone_runtime.window.was_cooling = value

    # Last distinct-move reference.
    @property
    def _wa_ref_room(self) -> float | None:
        return self._zone_runtime.window.wa_ref_room

    @_wa_ref_room.setter
    def _wa_ref_room(self, value: float | None) -> None:
        self._zone_runtime.window.wa_ref_room = value

    @property
    def _wa_ref_mono(self) -> float | None:
        return self._zone_runtime.window.wa_ref_mono

    @_wa_ref_mono.setter
    def _wa_ref_mono(self, value: float | None) -> None:
        self._zone_runtime.window.wa_ref_mono = value

    @property
    def _wa_prev_mono(self) -> float | None:
        return self._zone_runtime.window.wa_prev_mono

    @_wa_prev_mono.setter
    def _wa_prev_mono(self, value: float | None) -> None:
        self._zone_runtime.window.wa_prev_mono = value

    @property
    def _wa_open_threshold(self) -> float:
        return self._zone_runtime.window.wa_open_threshold

    @_wa_open_threshold.setter
    def _wa_open_threshold(self, value: float) -> None:
        self._zone_runtime.window.wa_open_threshold = value

    @property
    def _last_window_open(self) -> bool:
        return self._zone_runtime.window.last_window_open

    @_last_window_open.setter
    def _last_window_open(self, value: bool) -> None:
        self._zone_runtime.window.last_window_open = value

    # Rising-edge stamp of the open episode; gates the mould write-floor.
    @property
    def _window_open_since(self) -> float | None:
        return self._zone_runtime.window.window_open_since

    @_window_open_since.setter
    def _window_open_since(self, value: float | None) -> None:
        self._zone_runtime.window.window_open_since = value

    # ADR-0059 §1 house-gate flip tracking.
    @property
    def _prev_home(self) -> bool | None:
        return self._zone_runtime.presence.prev_home

    @_prev_home.setter
    def _prev_home(self, value: bool | None) -> None:
        self._zone_runtime.presence.prev_home = value

    @property
    def _last_presence_level(self) -> str:
        return self._zone_runtime.presence.last_presence_level

    @_last_presence_level.setter
    def _last_presence_level(self, value: str) -> None:
        self._zone_runtime.presence.last_presence_level = value

    @property
    def _room_absent_since(self) -> float | None:
        return self._zone_runtime.presence.room_absent_since

    @_room_absent_since.setter
    def _room_absent_since(self, value: float | None) -> None:
        self._zone_runtime.presence.room_absent_since = value

    # Dry-active hysteresis latch (persisted).
    @property
    def _dry_active(self) -> bool:
        return self._zone_runtime.humidity.dry_active

    @_dry_active.setter
    def _dry_active(self, value: bool) -> None:
        self._zone_runtime.humidity.dry_active = value

    # ADR-0046 P2: wall-clock anti-short-cycle lifecycle (persisted).
    @property
    def _multi_lifecycle(self) -> _lifecycle.DeviceLifecycle:
        return self._zone_runtime.compressor.multi_lifecycle

    @_multi_lifecycle.setter
    def _multi_lifecycle(self, value: _lifecycle.DeviceLifecycle) -> None:
        self._zone_runtime.compressor.multi_lifecycle = value

    # ADR-0052: derived from the live actuator each tick.
    @property
    def _dynamics(self) -> DeviceDynamics:
        return self._zone_runtime.compressor.dynamics

    @_dynamics.setter
    def _dynamics(self, value: DeviceDynamics) -> None:
        self._zone_runtime.compressor.dynamics = value

    @property
    def _failure(self) -> HeatingFailureDetector:
        return self._zone_runtime.safety.failure

    @_failure.setter
    def _failure(self, value: HeatingFailureDetector) -> None:
        self._zone_runtime.safety.failure = value

    # Previous tick's failure verdict; pauses EKF learning (VTherm #1428).
    @property
    def _prev_heating_failed(self) -> bool:
        return self._zone_runtime.safety.prev_heating_failed

    @_prev_heating_failed.setter
    def _prev_heating_failed(self, value: bool) -> None:
        self._zone_runtime.safety.prev_heating_failed = value

    # Sustained room-sensor loss anchor.
    @property
    def _unavailable_since(self) -> float | None:
        return self._zone_runtime.safety.unavailable_since

    @_unavailable_since.setter
    def _unavailable_since(self, value: float | None) -> None:
        self._zone_runtime.safety.unavailable_since = value

    @property
    def _outcome_stats(self) -> OutcomeStats:
        return self._zone_runtime.diagnostics.outcome_stats

    @_outcome_stats.setter
    def _outcome_stats(self, value: OutcomeStats) -> None:
        self._zone_runtime.diagnostics.outcome_stats = value

    @property
    def _regq(self) -> RegulationQuality:
        return self._zone_runtime.diagnostics.regq

    @_regq.setter
    def _regq(self, value: RegulationQuality) -> None:
        self._zone_runtime.diagnostics.regq = value

    @property
    def _ca_last_mono(self) -> float | None:
        return self._zone_runtime.diagnostics.ca_last_mono

    @_ca_last_mono.setter
    def _ca_last_mono(self, value: float | None) -> None:
        self._zone_runtime.diagnostics.ca_last_mono = value

    @property
    def _outcome_session(self) -> OutcomeSession:
        return self._zone_runtime.diagnostics.outcome_session

    @_outcome_session.setter
    def _outcome_session(self, value: OutcomeSession) -> None:
        self._zone_runtime.diagnostics.outcome_session = value

    # Real dt for the HDH/outcome observations.
    @property
    def _hdh_last_mono(self) -> float | None:
        return self._zone_runtime.diagnostics.hdh_last_mono

    @_hdh_last_mono.setter
    def _hdh_last_mono(self, value: float | None) -> None:
        self._zone_runtime.diagnostics.hdh_last_mono = value

    @property
    def _hdh(self) -> HdhSavings:
        return self._zone_runtime.diagnostics.hdh

    @_hdh.setter
    def _hdh(self, value: HdhSavings) -> None:
        self._zone_runtime.diagnostics.hdh = value

    # Warn once per run, not per 60 s tick.
    @property
    def _hum_shadow_warned(self) -> bool:
        return self._zone_runtime.diagnostics.hum_shadow_warned

    @_hum_shadow_warned.setter
    def _hum_shadow_warned(self, value: bool) -> None:
        self._zone_runtime.diagnostics.hum_shadow_warned = value

    # ADR-0025/0034 anti-chatter latch.
    @property
    def _was_preheating(self) -> bool:
        return self._zone_runtime.latches.was_preheating

    @_was_preheating.setter
    def _was_preheating(self, value: bool) -> None:
        self._zone_runtime.latches.was_preheating = value

    @property
    def _was_coasting(self) -> bool:
        return self._zone_runtime.latches.was_coasting

    @_was_coasting.setter
    def _was_coasting(self, value: bool) -> None:
        self._zone_runtime.latches.was_coasting = value

    # ADR-0051 rate-limit anchor.
    @property
    def _cool_sp_eff_prev(self) -> float | None:
        return self._zone_runtime.latches.cool_sp_eff_prev

    @_cool_sp_eff_prev.setter
    def _cool_sp_eff_prev(self, value: float | None) -> None:
        self._zone_runtime.latches.cool_sp_eff_prev = value

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        result = override_runtime.set_enabled(self._zone_runtime.user, value)
        if result.dirty:
            self._dirty = True

    def set_override(self, value: float | None, *, reason: str | None = None) -> None:
        """Set or clear the manual hold.

        The pure lifecycle body lives in ``control.override_runtime``
        (sanitize, the §4 set-time expiry announcement, the §5 stat hook and
        the hold origin). The immediate ``poise_override_ended`` on an
        explicit clear of an active hold arrives as ``CommandResult.events``
        and is fired RIGHT HERE, synchronously, before the dirty mark.
        """
        result = override_runtime.set_override(
            self._zone_runtime.user,
            value,
            reason=reason,
            policy=self._override_policy,
            timer_h=self._override_timer_h,
            max_h=self._override_max_h,
            frost_floor=FROST_FLOOR_C,
            device_max=DEVICE_MAX_C,
            now_utc_fn=_utcnow_ts,
            minutes_to_switchpoint_fn=self._minutes_to_switchpoint,
            record_stat_fn=self._record_override_stat,
        )
        for event in result.events:
            self._fire_override_ended(event.reason)
        if result.dirty:
            self._dirty = True

    def _set_mode_override(self, mode: str | None) -> None:
        """Adopt (or clear) a device-side hvac_mode as a manual mode-hold.

        Shares the setpoint hold's lifecycle: if no hold is running yet it
        starts one (set-time expiry via ``resolve_hold_expiry`` + the zone
        policy). A setpoint hold already active this frame keeps its announced
        expiry -- the common case where an IR remote sends mode + temperature
        in one frame, adopted together. Cleared by ``_end_hold`` alongside the
        setpoint hold; never a safety layer. Body in
        ``control.override_runtime.set_mode_override``.
        """
        result = override_runtime.set_mode_override(
            self._zone_runtime.user,
            mode,
            policy=self._override_policy,
            timer_h=self._override_timer_h,
            max_h=self._override_max_h,
            now_utc_fn=_utcnow_ts,
            minutes_to_switchpoint_fn=self._minutes_to_switchpoint,
        )
        if result.dirty:
            self._dirty = True

    def _apply_hot_tuning(self, hot: HotApplyConfig) -> None:
        """Fill the hot-applyable tuning attributes from a parsed config.

        The ONE write path shared by ``__init__`` and ``async_apply_options``
        — exactly the fields both paths re-read. Deliberately NOT here: the
        structural wiring and the adopt-external toggles (init-only),
        ``climate_mode`` (store-owned) and the per-tick derived
        ``_dynamics``/``_mpc_params``/PI profile (re-derived every tick in
        ``_run_once``; an options submit must never reset them).
        ``HotApplyConfig`` carries no structural fields at all, so this method
        cannot even reach for one.
        """
        tuning = hot.tuning
        hold = hot.hold
        # ADR-0059 §1/§2 hold/Boost tuning (hot-applyable; options>data).
        self._override_policy = tuning.override_policy
        self._override_timer_h = hold.override_timer_h
        self._override_max_h = hold.override_max_h
        self._override_end_on_presence = hold.override_end_on_presence
        self._boost_duration_min = hold.boost_duration_min
        self._comfort_base = tuning.comfort_base
        self._hdh_cfg = tuning.hdh_cfg  # ADR-0045 savings-report inputs
        # ADR-0052: the raw dynamics override; ``_dynamics`` itself is derived
        # from it (plus the live capabilities) each tick.
        self._dynamics_override = tuning.dynamics_override
        # ADR-0046 §8 (live): single-AC compressor guard — kill switch + timers
        # (option over the dynamics-profile default).
        self._compressor_guard = tuning.compressor_guard
        self._comp_min_off_opt = tuning.comp_min_off_opt
        self._comp_mode_hold_opt = tuning.comp_mode_hold_opt
        self._trace_enabled = tuning.trace_enabled
        # ADR-0058 presence coupling — options-owned and hot-applied although
        # modelled structurally; the coordinator keeps its list attributes.
        self._presence_home_entities = list(hot.presence_home_entities)
        self._occupancy_entities = list(hot.occupancy_entities)
        # The presence lists are the ONE options-owned, hot-applied piece of
        # the otherwise reload-only structure — the reader's structure
        # snapshot must follow, or read_presence() would keep reading the
        # setup-time lists after an options submit.
        self._input_reader.set_presence_entities(
            hot.presence_home_entities, hot.occupancy_entities
        )
        self._presence_cfg = tuning.presence_cfg
        # ADR-0051: heat-day cooling raise (live, rate-limited, cooling-only).
        self._thermal_shock_delta = tuning.thermal_shock_delta
        self._cool_hard_cap = tuning.cool_hard_cap
        self._adaptive_cool_cfg = tuning.adaptive_cool_cfg
        self._category = tuning.category  # fallback in the parser
        self._cool_min_outdoor = tuning.cool_min_outdoor
        self._heat_max_outdoor = tuning.heat_max_outdoor
        # Outdoor-lockout enable toggles. When off, None is passed into the
        # pure decide so that lockout edge is dropped (None already = "off" there).
        self._heat_lockout_enabled = tuning.heat_lockout_enabled
        self._cool_lockout_enabled = tuning.cool_lockout_enabled
        self._priority = tuning.priority
        self._schedule = tuning.schedule
        self._optimal_start = tuning.optimal_start
        # optimal-stop coasts to the lower comfort edge before window end; for
        # now coupled to optimal-start (predictive scheduling), splittable later.
        self._optimal_stop = tuning.optimal_stop
        self._operative_input = tuning.operative_input

    def set_climate_entity_id(self, entity_id: str) -> None:
        """Record the room's climate entity_id for the ended-event payload."""
        self._climate_entity_id = entity_id

    def _minutes_to_switchpoint(self) -> float | None:
        """Minutes to the next schedule switchpoint for a hold's expiry (§1).

        Pure lookup in ``control.override_runtime``; the one ``dt_util.now()``
        read stays here (evaluated at the call position inside the lifecycle
        commands / the restore recompute).
        """
        return override_runtime.minutes_to_switchpoint(
            self._schedule, _local_minute_now()
        )

    def _record_override_stat(self, clamped: float) -> None:
        """Append one L1 override observation (ADR-0059 §5; diagnostic only).

        The stat body is pure (``control.override_runtime``); the broad
        swallow boundary stays HERE so the debug record keeps its exact
        channel (``custom_components.poise.coordinator``) and text — the log
        channel is observable diagnosis.
        """
        try:
            override_runtime.record_override_stat(
                self._zone_runtime.user,
                clamped,
                presence_level=self._last_presence_level,
                window_open=self._last_window_open,
                comfort_base=self._comfort_base,
                override_cfg=self._override_cfg,
                schedule=self._schedule,
                local_minute_fn=_local_minute_now,
                now_utc_fn=_utcnow_ts,
            )
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

    def _teardown_hold(self, reason: str) -> OverrideEnded:
        """Clear the hold state WITHOUT firing the bus event.

        The body lives in ``ZoneRuntime.teardown_hold`` (state teardown is
        domain mutation); ``_end_hold`` keeps calling this facade so teardown
        + immediate fire stay one adapter step.
        """
        return self._zone_runtime.teardown_hold(reason)

    def _end_hold(self, reason: str) -> None:
        """Tear down an active manual hold and announce why (ADR-0059 §1/§3)."""
        self._teardown_hold(reason)
        self._fire_override_ended(reason)

    def commit_execution(
        self,
        report: ExecutionReport,
        # Sequence (not an inline variadic tuple) on purpose: an ellipsis in
        # the def signature would match the coverage exclude regex ``\.\.\.``
        # (meant for protocol stubs) and silently exclude this whole method
        # from the glue coverage gate. Callers pass ``TickPlan.post_actions``
        # (a tuple) unchanged.
        post_actions: Sequence[PostExecutionAction] = (),
        *,
        now: float | None = None,
    ) -> CommitResult:
        """Fold an ordered ``ExecutionReport`` into the domain state.

        The fold lives in ``ZoneRuntime.commit_execution`` — the single
        mutation path after I/O belongs to the runtime; this facade keeps the
        pinned call surface for the write sites. The adapter still fires
        ``CommitResult.events`` on the bus AFTER the commit returns (and
        before the ``_maybe_save`` checkpoint).
        """
        return self._zone_runtime.commit_execution(report, post_actions, now=now)

    def _expire_timed_states(self, home: bool | None) -> None:
        """Expire the timed Boost + manual hold on a tick (ADR-0059 §1/§2).

        Lifecycle body in ``control.override_runtime`` (Boost restore + hold
        expiry + reason derivation). The hold-end event arrives as
        ``CommandResult.events`` and fires RIGHT HERE at the in-stage
        position, after the dirty mark: teardown sets dirty BEFORE the fire,
        and a synchronous bus listener observing ``_dirty`` at event time must
        keep seeing ``True`` (pinned by the phase-0 frost matrix).
        """
        result = override_runtime.expire_timed_states(
            self._zone_runtime.user,
            self._zone_runtime.presence,
            home,
            end_on_presence=self._override_end_on_presence,
            boost_duration_min=self._boost_duration_min,
            now_utc_fn=_utcnow_ts,
        )
        if result.dirty:
            self._dirty = True
        for event in result.events:
            self._fire_override_ended(event.reason)

    def set_climate_mode(self, mode: str) -> None:
        result = override_runtime.set_climate_mode(self._zone_runtime.user, mode)
        if result.dirty:
            self._dirty = True

    def set_window_bypass(self, on: bool) -> None:
        result = override_runtime.set_window_bypass(self._zone_runtime.user, on)
        if result.dirty:
            self._dirty = True

    def set_preset(self, mode: OverrideMode) -> None:
        """Select a preset; Boost timer logic (ADR-0059 §2, VT#1961) is the
        pure ``control.override_runtime.set_preset``."""
        result = override_runtime.set_preset(
            self._zone_runtime.user,
            mode,
            boost_duration_min=self._boost_duration_min,
            now_utc_fn=_utcnow_ts,
        )
        if result.dirty:
            self._dirty = True

    @property
    def preset(self) -> OverrideMode:
        return self._preset

    @property
    def window_bypass(self) -> bool:
        return self._window_bypass

    # ------------------------------------------------------------------
    # The device-guard discovery state lives in the InputReader.
    # These two are proxied on the coordinator because integration tests pin
    # them directly (test_phase0_effect_sequences pins ``_sensor_select``,
    # test_phase0_fault_shadow_domain pins ``_valve_entity``); a pin survives
    # re-resolution because the discovery is idempotent.
    # ------------------------------------------------------------------

    @property
    def _sensor_select(self) -> str | None:
        return self._input_reader.sensor_select

    @_sensor_select.setter
    def _sensor_select(self, value: str | None) -> None:
        self._input_reader.sensor_select = value

    @property
    def _valve_entity(self) -> str | None:
        return self._input_reader.valve_entity

    @_valve_entity.setter
    def _valve_entity(self, value: str | None) -> None:
        self._input_reader.valve_entity = value

    # ------------------------------------------------------------------
    # The forecast cache lives in the ForecastProvider. Proxied on the
    # coordinator (same pattern as the device-guard pair above) because
    # integration tests poke/pin the attributes directly — test_forecast_backoff
    # and test_glue_coverage2/4 set ``_forecast_at``, test_phase0_forecast_gating
    # asserts it — and a poke must keep governing the provider's TTL/backoff.
    # ------------------------------------------------------------------

    @property
    def _forecast(self) -> list[tuple[float, float]]:
        return self._forecast_provider.forecast

    @_forecast.setter
    def _forecast(self, value: list[tuple[float, float]]) -> None:
        self._forecast_provider.forecast = value

    @property
    def _forecast_at(self) -> float | None:
        return self._forecast_provider.forecast_at

    @_forecast_at.setter
    def _forecast_at(self, value: float | None) -> None:
        self._forecast_provider.forecast_at = value

    @property
    def _forecast_fail_at(self) -> float | None:
        return self._forecast_provider.fail_at

    @_forecast_fail_at.setter
    def _forecast_fail_at(self, value: float | None) -> None:
        self._forecast_provider.fail_at = value

    @property
    def capability(self) -> tuple[bool, bool]:
        """(can_heat, can_cool) of the actuator."""
        return self._input_reader.capability()

    @property
    def via_device_id(self) -> tuple[str, str] | None:
        """Device-registry link from this zone to the system hub.

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
        # Re-adopt any repair issues this entry already owns so a coordinator
        # rebuilt after a crash/setup-retry can still clear them (otherwise they
        # are instance-local and orphaned once the condition resolves).
        try:
            _reg = ir.async_get(self.hass)
            self._active_issues = {
                iid
                for (dom, iid) in _reg.issues
                if dom == DOMAIN and iid.endswith(self._entry_id)
            }
        except Exception:  # noqa: BLE001 - registry read must never block setup
            pass
        # Keep store I/O and parsing failures separate. A transient load
        # error must NOT be mistaken for "no saved state" (which would silently
        # start fresh and overwrite the learned model on the next save) — fail
        # setup so HA retries. Only genuinely *corrupt* data is recovered below.
        try:
            data = await self._store.load()
        except Exception as err:  # noqa: BLE001 - transient I/O -> retry, don't wipe
            raise ConfigEntryNotReady(
                f"Poise {self.zone_name}: could not load persisted state"
            ) from err
        # Corruption recovery (narrowly scoped): the store FORMAT is owned by
        # ``persistence.codec``. ``decode()`` reproduces the pinned restore
        # gate (``isinstance(data, dict) and "ekf" in data``), the per-key
        # defensive coercions, the hold gates and the sequential prefix parse
        # of the model tail, so the cheap user-intent keys can never be lost
        # to a failure in the heavier learned-model parsing. The DOMAIN
        # restore semantics (echo re-stamping, hold-expiry recompute, section
        # application order) stay here, in ``_apply_decoded_state``.
        try:
            decoded = _codec.decode(data, now_wall=dt_util.utcnow().timestamp())
            if decoded.kind == "v1":
                self._apply_decoded_state(decoded)
                if decoded.model_error is not None:
                    # A structural throw stopped the model parse mid-tail:
                    # every model parsed BEFORE the throwing key was applied
                    # above, matching the sequential restore. Re-raise the
                    # ORIGINAL exception into the broad boundary below so the
                    # recovery log keeps its shape: ONE ``_LOGGER.exception``
                    # record with the caplog-pinned text, the exception class
                    # and traceback.
                    raise decoded.model_error
            elif decoded.kind == "legacy_bare_ekf":
                # Legacy: bare EKF dict (persistence/migrations.py). "corrupt
                # -> fresh" deliberately stays with the boundary below.
                self._ekf = migrate_v0_bare_ekf(data)
        except Exception:  # noqa: BLE001 - corrupt state must not block setup
            _LOGGER.exception("Poise: failed to restore learned model; starting fresh")
        # cold-start prior (ADR-0004): seed beta_h from the seasonless estimate
        # only while the EKF has never observed heating. The domain hook
        # ``ZoneRuntime.seed_ekf_cold_start`` runs UNCONDITIONALLY after the
        # recovery boundary, also on the fresh/legacy/corrupt paths; the
        # calendar lookup stays adapter-side, injected as a callable and
        # evaluated only under the seed condition.
        self._zone_runtime.seed_ekf_cold_start(
            comfort_base=self._comfort_base,
            day_ordinal_fn=lambda: dt_util.now().toordinal(),
        )
        # Vet the configured external-temp number once, now that _active_issues
        # has been re-adopted so a stale issue can be cleared on recovery.
        await self._validate_configured_ext_temp()

    def _apply_decoded_state(self, decoded: _codec.DecodedPersistence) -> None:
        """Apply a decoded v1 store onto the live state.

        The DOMAIN restore semantics live in ``ZoneRuntime.restore`` together
        with the domain hooks — the echo-window re-stamping (runtime clock)
        and the hold-expiry recompute (config policy/timers as parameters;
        the schedule switchpoint lookup is injected as a callable because it
        reads the wall clock, and stays evaluated only under the recompute
        condition). This facade feeds it the config-owned hold tuning.
        """
        self._zone_runtime.restore(
            decoded,
            override_policy=self._override_policy,
            override_timer_h=self._override_timer_h,
            override_max_h=self._override_max_h,
            minutes_to_switchpoint=self._minutes_to_switchpoint,
        )

    async def async_apply_options(self, entry: ConfigEntry) -> None:
        """Apply changed tuning options in place, without a reload.

        Re-reads the volatile tuning fields (options over data) and updates the
        live state, so an options change does **not** discard the learned EKF
        transient that a full reload would. Structural inputs are not options.

        The same parser + apply method as ``__init__``, so the two paths can
        never drift. ``HotApplyConfig`` reads NO structural key, so a merged
        mapping missing ``name``/``temp_sensor``/``actuator`` — a legacy entry
        holding the key only in ``options``, dropped by an options submit —
        still hot-applies cleanly instead of raising into the update listener.
        The parse is atomic: a corrupt value fails the whole hot-apply up
        front instead of tearing the tuning mid-sequence. ``climate_mode``
        stays store-owned: the climate entity sets it live via
        ``set_climate_mode()`` and it is persisted in the payload —
        re-applying the (stale) options form value here would clobber the
        live selection on every submit.
        """
        # The field mutations below race a concurrent tick (``_run_once``
        # reads many of these same attributes without any lock of its own) --
        # an options submit landing mid-tick could observe a torn mix of old and
        # new tuning. Take the same lock ``_async_update_data`` holds across a
        # tick to make this update atomic with respect to any tick. This MUST
        # NOT include ``async_request_refresh()`` below: ``asyncio.Lock`` is not
        # reentrant, and ``async_request_refresh`` awaits ``_async_update_data``,
        # which acquires this same lock -- held across that call, it would
        # deadlock immediately.
        async with self._lock:
            self._apply_hot_tuning(HotApplyConfig.from_entry(entry))
        await self.async_request_refresh()

    def attach_listeners(self, entry: ConfigEntry) -> None:
        """React promptly to input changes, not only on the 60 s tick.

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
            # Skip pure attribute churn. A watched entity may emit many
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

    def _emit_health_updates(self, updates: tuple[HealthUpdate, ...]) -> None:
        """Checkpoint primitive: apply stage-collected ``HealthUpdate``s to
        the issue registry, in order.

        Stages no longer write to the registry mid-body; they collect typed
        updates in per-issue evaluation order and the tick flow emits them at
        stage checkpoints whose positions preserve the emission points
        relative to the awaits. ``_issue`` keeps the transition-only
        create/delete semantics, so a collected clear (``active=False``)
        deletes exactly as an inline call would.
        """
        for update in updates:
            self._issue(
                update.issue_id,
                update.active,
                translation_key=update.translation_key,
                placeholders=(
                    dict(update.placeholders)
                    if update.placeholders is not None
                    else None
                ),
            )

    async def _validate_configured_ext_temp(self) -> None:
        """Vet the *configured* external-temp number once (not per tick).

        A value the user picked EXPLICITLY via CONF_TRV_EXTERNAL_TEMP is trusted
        unless it shows a POSITIVE non-temperature signal (a non-temperature
        device_class or unit, e.g. a valve's "%") — so a legitimately
        renamed/localised temperature input is NOT dropped on upgrade. On a real
        mismatch: stop feeding it AND hand the TRV's sensor source back to
        internal, or the device would keep regulating against a now-frozen
        external value; then raise a repair issue. When plausible or unset,
        clear it. A registry miss must never block setup.
        """
        issue_id = f"external_temp_implausible_{self._entry_id}"
        entity_id = self._trv_ext_temp
        if not entity_id:
            self._issue(issue_id, False, translation_key="external_temp_implausible")
            return
        try:
            # The registry/state signature read lives in the reader; its
            # errors propagate into THIS try — the "a registry miss must never
            # block setup" boundary stays here.
            device_class, unit = self._input_reader.configured_ext_temp_signature(
                entity_id
            )
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
        # internal so the device does not regulate against a frozen value.
        self._trv_ext_temp = None
        try:
            # Documented write-gate exception: this restore deliberately
            # DELEGATES to __init__.py's lifecycle helper (shared with entry
            # teardown and the config_flow park) instead of the tick executor
            # — a one-shot setup-time write with its own blocking semantics,
            # not a tick effect. The write-boundary gate's __init__.py
            # exception covers its service calls.
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

    async def _forecast_outdoor(self, horizon_min: float, fallback: float) -> float:
        """Mean forecast outdoor temp over the preheat window (ADR-0025).

        The body lives in ``ForecastProvider.mean_outdoor`` (fetch payload,
        TTL, backoff + last-good-cache fallback). The call stays an await
        inside the tick under the coordinator lock at the single
        predictive-gated call site; decoupling it from the tick is F-FORECAST
        (phase 10). Kept as a method because integration tests drive it
        directly (test_forecast_backoff, test_glue_coverage4).
        """
        return await self._forecast_provider.mean_outdoor(
            self._weather, horizon_min, fallback
        )

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
            # The snapshot+build sequence lives in the pure
            # ``diagnostics.trace.build_tick_record`` — the call stays INSIDE
            # this swallow boundary (a build failure is swallowed, the tick
            # lives) and the append below remains the last observable
            # statement under the lock. The ``ts=`` clock read now precedes
            # the snapshot build — a documented unobservable micro-reorder,
            # see the module docstring there.
            record = build_tick_record(
                data,
                self._ekf,
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

    def _notify_failure(self, failed: bool) -> None:
        """Surface a persistent heating failure as a translated repair issue.

        Raised while ``failed``, cleared when it recovers, so the message is
        localised via ``translations/*`` like every other Poise diagnostic.
        Runs as a synchronous checkpoint emission inside the failure-detect
        stage.
        """
        self._emit_health_updates(
            (
                HealthUpdate(
                    issue_id=f"heating_failure_{self._entry_id}",
                    active=failed,
                    translation_key="heating_failure",
                    placeholders={"zone": self.zone_name},
                ),
            )
        )

    def _save_payload(self) -> dict[str, Any]:
        """The v1 store payload — the FORMAT is owned by ``persistence.codec``.

        This adapter only snapshots the attribute values into the typed
        ``PersistedZoneState``; key set/order, the per-key transforms and the
        deliberate omissions (monotonic stamps like ``_window_open_since`` and
        the echo timestamps, and any ``_pi`` state) are documented and pinned
        in the codec. ``override_policy`` is the CONFIG value: stored for
        diagnostics, never applied on restore.
        """
        return _codec.encode(
            _codec.PersistedZoneState(
                ekf=self._ekf,
                trm_tracker=self._trm_tracker,
                seasonless=self._seasonless,
                window_auto=self._window_auto,
                multi_lifecycle=self._multi_lifecycle,
                ref_offset=self._ref_offset,
                tau_settle=self._tau_settle,
                outcome_stats=self._outcome_stats,
                regq=self._regq,
                hdh=self._hdh,
                dry_active=self._dry_active,
                enabled=self._enabled,
                preset=self._preset,
                climate_mode=self._climate_mode,
                window_bypass=self._window_bypass,
                has_actuated=self._has_actuated,
                override=self._override,
                mode_override=self._mode_override,
                override_set_wall=self._override_set_wall,
                override_requested=self._override_requested,
                override_policy=self._override_policy,
                override_expires_at=self._override_expires_at,
                override_expiry_is_switchpoint=self._override_expiry_is_switchpoint,
                boost_expires_at=self._boost_expires_at,
                boost_prev_preset=self._boost_prev_preset,
                override_stats=self._override_stats,
                override_reason=self._override_reason,
                last_written_sp=self._last_written_sp,
                prev_device_sp=self._prev_device_sp,
                last_commanded_hvac=self._last_commanded_hvac,
                prev_device_mode=self._prev_device_mode,
            )
        )

    async def _maybe_save(self) -> None:
        self._save_counter += 1
        if self._save_counter >= EKF_SAVE_EVERY_TICKS or self._dirty:
            self._save_counter = 0
            try:
                await self._store.save(self._save_payload())
                # Only clear the dirty flag on a SUCCESSFUL save. Clearing it
                # unconditionally would mark a fresh override/preset/enabled
                # change as "persisted" even when the write itself failed, so
                # a crash/restart in that window would silently lose the
                # user's intent until the next periodic (30-tick) save
                # happened to succeed.
                self._dirty = False
                self._note_save_result(ok=True)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Poise: failed to persist learned model")
                self._note_save_result(ok=False)

    def _mark_actuated(self) -> None:
        """Set the teardown-park gate, persisting the flip.

        The body lives in ``ZoneRuntime.mark_actuated`` (success-state commit
        mutation); facade kept for the pinned name.
        """
        self._zone_runtime.mark_actuated()

    def _note_save_result(self, *, ok: bool) -> None:
        """Escalate a persistently failing store to a repair issue.

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
        """Final save + repair-issue/notification cleanup on unload.

        The final save runs under the same lock as the tick / stop flush. If
        that save fails we KEEP (and raise) the ``persistence_failed`` issue
        instead of clearing it — a failed unload save can lose the last
        learning window, so this is honest, not an unconditional "no learning
        loss".
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
            # Surface + retain the persistence issue; it is re-adopted on the
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
        """True if only tuning options changed since setup.

        A change to ``entry.data`` means a reconfigure is reloading the entry, so
        the in-place options hot-apply must NOT run on this soon-to-be-discarded
        coordinator (the reload rebuilds it with the new data anyway).

        The data-dict comparison is deliberate: a field-wise ``ZoneStructure``
        comparison is NOT equivalent — room ``entry.data`` carries
        non-structure keys (the installation keys; on fresh entries also
        ``comfort_base``/``category``) whose changes must keep reading as
        structural, while the options-owned presence lists must stay out of
        this predicate (see ``runtime.config.structures_equal``).
        """
        return dict(entry.data) == self._data_snapshot

    async def async_flush_on_stop(self, _event: Any) -> None:
        """Persist learned state on HA shutdown (ADR-0007 flush).

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
            # A tick that raises out of ``_run_once`` is otherwise invisible
            # beyond DataUpdateCoordinator's own generic "update failed"
            # log/entity unavailability -- no Poise-specific signal, no
            # persistence, nothing to distinguish a one-off transient blip
            # from a zone stuck failing every tick. Track consecutive failures
            # the same way ``_note_save_result`` does for the store, and
            # surface a repair issue after N in a row; the exception itself is
            # always re-raised unchanged so DataUpdateCoordinator's own failure
            # handling is untouched.
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

    async def _write_unavailable_safe_state(self) -> None:
        """Command the frost/mould floor after a sustained room-sensor loss.

        A heat-capable actuator degrades to the health floor in heat (frost
        protection held by its own sensor -- fail toward warmth); a cool-only
        actuator is commanded off (it must not cool the room to the floor).
        Mirrors the frozen-sensor safe state for a fully unavailable sensor.
        The floor is clamped up to the device ``min_temp`` so a high-min AC
        does not thrash on an echo it cannot honour. Best-effort + idempotent;
        a failure must never break the tick.

        This is the unavailable path's plan_actuation + apply + commit node —
        ``resolve_safe_state`` produces the ``SafeStatePlan`` (or None =
        already safe), the executor sequence applies it, the commit folds the
        stamps. It stays positioned AFTER the BEFORE_EXECUTION save (see
        ``_run_unavailable_tick``): the actuator read below is await-relative
        behaviour, so the plan cannot be resolved in the prepare phase.
        """
        # Positioned read: this sits AFTER the unavailable path's conditional
        # dirty-flush save await — a device change during that save is
        # observable and must remain so.
        act = self._input_reader.actuator_state()
        modes = (
            [str(m) for m in (act.attributes.get("hvac_modes") or [])] if act else []
        )
        # Decide mode + setpoint together (pure), so a device in cool/auto/off
        # actually receives the set_hvac_mode('heat') it needs and does not
        # keep cooling toward the floor. Mode and setpoint writes are
        # independent and each idempotent.
        plan = resolve_safe_state(
            hvac_modes=modes,
            device_state=act.state if act is not None else None,
            device_setpoint=parse_attr_number(act, "temperature"),
            device_min=parse_attr_number(act, "min_temp"),
            floor=FROST_FLOOR_C,
        )
        if plan is None:
            return  # already in the safe state -> no re-write (idempotent)
        # The executor sequence owns the ONE shared boundary (a mode dispatch
        # error skips the setpoint write — F-SAFESEQ until phase 10), both
        # payloads (untagged; F-CONTEXT is phase 10) and the boundary log; the
        # commit right here folds the stamps. Mode part: ``last_written_mode``
        # only after a real nudge (our own safe-state mode is never a user
        # change — mode echo). Setpoint part: ``last_target``; clear the
        # adoption baseline (``last_written_sp=None``) so our own safe-state
        # setpoint is never re-read as a user hold on recovery;
        # ``_mark_actuated``. No timestamp on this path: the commit needs no
        # ``now=``.
        report = await self._actuator_executor.run_unavailable_safe(
            plan, entity_id=self._actuator, zone_name=self.zone_name
        )
        self.commit_execution(report)

    async def _run_once(self) -> dict[str, Any]:
        """One tick under the lock — the architecture-diagram target flow.

        ``prepare_until_forecast`` (owns the availability gate + snapshot) →
        unavailable short-circuit OR [forecast resolve if requested] →
        ``resume_prepare`` → ``TickPlan`` → pre_events → [BEFORE_EXECUTION
        save] → apply/commit → [AFTER_EXECUTION save] → ``finalize_tick`` →
        present. The apply/commit node runs as an ORDERED multi-segment
        program INSIDE ``resume_prepare`` (each segment: plan → exec → commit
        at its position) because the one-block ``apply(plan)`` hoist is not
        provably unobservable — the per-dependency proofs live in
        ``resume_prepare``'s docstring. ``_async_update_data`` keeps measuring
        the tick wall-time around this whole method (``tick_ms`` unchanged).

        Stages collect ``HealthUpdate``s and the prepare flow emits them at
        stage-end checkpoints. A stage that aborts mid-body AFTER collecting
        updates raises ``TickStageError(cause, pending_health_updates)``; the
        handler below emits the pending updates (exactly the transitions the
        inline code had already written before the failure point) and
        re-raises the ORIGINAL exception object, so the failure counting and
        DataUpdateCoordinator's error handling in ``_async_update_data`` see
        the unchanged exception class/message/identity.
        """
        try:
            prep = self.prepare_until_forecast()
            if isinstance(prep, TickPlan):
                # Unavailable short-circuit: the plan carries the
                # BEFORE_EXECUTION persistence directive; the safe-state
                # decision itself stays positioned AFTER that save (see
                # ``_run_unavailable_tick``).
                return await self._run_unavailable_tick(prep)
            # Forecast handshake: the await runs under the tick lock, under
            # exactly the condition ``forecast_request`` exists iff the
            # ``predictive`` gate held -- and with the tick-current lead
            # horizon plus the fallback value. The await stays in the adapter
            # so the prepare phase itself performs no I/O; F-FORECAST
            # (phase 10) is the only place this may ever move.
            if prep.forecast_request is not None:
                forecast: float | None = await self._forecast_outdoor(
                    prep.forecast_request.horizon_min, prep.forecast_request.fallback
                )
            else:
                forecast = None
            plan = await self.resume_prepare(prep, forecast)

            # pre_events seam: the hold-expiry and preheat-edge events fire
            # IMMEDIATELY inside the prepare stages, synchronously under the
            # lock — and a synchronous bus listener MAY write coordinator
            # state that later prepare stages read. Deferring those fires to
            # this seam is therefore NOT provably unobservable; the events
            # keep firing at their in-stage positions and ``pre_events`` stays
            # an EMPTY structural seam.
            for event in plan.pre_events:
                self._fire_override_ended(event.reason)

            # PersistencePhase directive: BEFORE_EXECUTION exists only on the
            # unavailable short-circuit above; on a normal tick this is a
            # no-op and the AFTER_EXECUTION save below runs unconditionally.
            if plan.persistence is PersistencePhase.BEFORE_EXECUTION and self._dirty:
                await self._maybe_save()

            # apply → commit(post_actions) → CommitResult.events: already
            # executed as the ordered in-stage program (``resume_prepare``);
            # the frost-rescue segment fired its ``CommitResult.events`` after
            # the rescue writes, before the save below.

            # INVARIANT (finding 12, ADR-0007): the AFTER_EXECUTION save sits
            # BETWEEN commits/events and finalize_tick — snapshot holds the
            # previous tick's finalize state; this tick's commit-dirty IS
            # flushed. Pinned by test_phase0_persistence_checkpoint.py.
            # F-SAVEPOINT (phase 10) is the only place this may ever change.
            if plan.persistence is PersistencePhase.AFTER_EXECUTION:
                await self._maybe_save()

            # The FinalizeContext (the whole TickPlan) is built at the END of
            # ``resume_prepare`` -- BEFORE the save await above. Unobservable
            # reorder (documented proof): the construction reads only
            # already-computed stage-result fields and constructs frozen
            # dataclasses -- no ``self`` reads, no I/O, no logging -- and each
            # field is an immutable value or an object reference that stays
            # the same object across the await (a reference mutation would be
            # equally visible from either position). The live ``self._*``
            # reads of the finalize segment stay INSIDE ``finalize_tick``,
            # after the save.
            ctx = plan.finalize_context
            assert ctx is not None  # resume_prepare always builds it
            outcome = await self.finalize_tick(ctx)
            # ``present`` lives in ``ha/presenter.py`` — for the available
            # form it returns ``outcome.diagnostics`` AS THE SAME OBJECT
            # (aliasing contract), see the module docstring.
            return _present(outcome)
        except TickStageError as err:
            pending = err.pending_health_updates
            cause = err.cause
        # Stage-abort checkpoint (pinned by test_phase0_health_emission incl.
        # the delete direction, exercised by test_phase6_health_checkpoints):
        # emit the transported updates, then re-raise the original. POSITION
        # PROOF: exception unwinding — also through the async frames — is
        # synchronous, so this emission runs in the SAME event-loop turn as
        # the failure, with no suspension point between the "already emitted
        # before the failure" state and this checkpoint. The raise sits
        # OUTSIDE the except block so no implicit exception context is chained
        # onto ``cause`` — its ``__context__``/``__cause__``/
        # ``__suppress_context__`` stay exactly as they were at the original
        # raise site. Known residual (documented): the traceback frame list
        # of an abort WITH pending updates loses the intermediate stage-call
        # frames (the exception object is re-raised from here); class,
        # message and identity are unchanged, and aborts WITHOUT pending
        # updates propagate bare and byte-identically (stages only wrap when
        # they have something to transport — nothing else changed on the
        # failure path, and the inline ``try`` adds no frame).
        self._emit_health_updates(pending)
        raise cause

    async def _run_unavailable_tick(self, plan: TickPlan) -> dict[str, Any]:
        """Unavailable short-circuit: [BEFORE_EXECUTION save] → safe-state
        plan/apply/commit → present(minimal).

        The anchor resets already ran inside ``prepare_until_forecast``
        (before the save). Everything below stays positioned AFTER the
        conditional dirty-flush await: the outage clock read (the engagement
        delta must include the save duration), the ``_unavailable_since``
        stamp, the warn-once log and the safe-state actuator read are all
        observable relative to that save (a device/clock change during the
        save is visible), so none of it may move into the prepare phase
        without a reorder proof — which does not exist. That is why the
        short-circuit ``TickPlan.actuator_plan`` is None: the ``SafeStatePlan``
        is resolved inside ``_write_unavailable_safe_state``.
        """
        # A user intent set via the switch/select (enabled / preset / mode)
        # while the room sensor is down must still be persisted — the normal
        # save sits after this early return, so flush a pending change here
        # too. The plan's BEFORE_EXECUTION directive models this checkpoint
        # position; the dirty gate is the exact condition.
        # INVARIANT (finding 12/F5, ADR-0007): on the unavailable path the
        # BEFORE_EXECUTION dirty-flush runs BEFORE the safe-state write.
        # Pinned by test_phase0_persistence_checkpoint.py. F-SAVEPOINT
        # (phase 10) is the only place this may ever change.
        if plan.persistence is PersistencePhase.BEFORE_EXECUTION and self._dirty:
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
        # A sustained loss must not hold a stale comfort setpoint indefinitely
        # (critical in external-feed mode). After the timeout, degrade to the
        # frost/mould floor -- the same safe state as a frozen sensor (fail
        # toward warmth).
        if unavailable_safe_engaged(
            now_mono - self._unavailable_since, UNAVAILABLE_SAFE_AFTER_S
        ):
            await self._write_unavailable_safe_state()
            # ``unavailable_safe=True`` is returned UNCONDITIONALLY once
            # engaged — independent of the safe plan (idempotent skip) and of
            # dispatch success.
            return _present(
                TickOutcome(
                    data=UnavailableTickData(unavailable_safe=True),
                    diagnostics={},
                    trace_record=None,
                )
            )
        return _present(
            TickOutcome(
                data=UnavailableTickData(unavailable_safe=False),
                diagnostics={},
                trace_record=None,
            )
        )

    def prepare_until_forecast(self) -> PrepareContinuation | TickPlan:
        """Prepare phase up to the forecast seam — or the unavailable
        short-circuit.

        Owns the availability gate and the snapshot: on an unavailable tick
        it returns the short-circuit ``TickPlan`` (``persistence=
        BEFORE_EXECUTION``) right after the anchor resets — the
        ``actuator_plan`` is deliberately None because the safe-state decision
        is positioned AFTER the dirty-flush save (see
        ``_run_unavailable_tick``). Otherwise the await-free prepare stages
        run (ingest -> observe -> safety floors -> schedule gate) and stop at
        the predictive decision; ``air`` stays the positioned pre-snapshot
        room read -- provably equal to ``inputs.room.value``
        (await-free-window proof) -- passed into the ingest stage so its body
        stays unchanged.

        Health checkpoints: the stages collect ``HealthUpdate``s and this
        orchestrator emits them at the stage-end checkpoints below. POSITION
        PROOF (valid for every checkpoint in this method): this entire phase
        is await-free, so between a stage's in-body emission point and its
        stage-end checkpoint no suspension point exists — on the
        single-threaded event loop no other task can interleave, and the
        registry sees the identical transitions in the identical order within
        the same loop turn. Residual (accepted): synchronous listeners of the
        repairs-registry-updated event run a few statements later in the same
        turn; that event is HA-internal housekeeping with no synchronous
        integration listeners — unlike the public ``poise_override_ended`` bus
        event, whose in-stage firing position is preserved (see
        ``_run_once``'s pre_events note).
        """
        # Positioned first read: the availability gate must run BEFORE the
        # pre-await snapshot — on an unavailable tick neither the guard
        # discovery nor any other read of the segment runs, and that error
        # path stays read-for-read identical.
        air = self._input_reader.read(self._temp)
        # Availability-gate checkpoint [1]: emitted at its EXACT statement
        # position (trivially position-identical), both directions. The
        # constraint holds by construction: the checkpoint lies BEFORE every
        # await of the tick and — on the unavailable path — BEFORE the
        # short-circuit return, hence before ``_run_once``'s persistence/apply
        # evaluation and the BEFORE_EXECUTION dirty-flush save.
        self._emit_health_updates(
            (
                HealthUpdate(
                    issue_id=f"sensor_unavailable_{self._entry_id}",
                    active=air is None,
                    translation_key="sensor_unavailable",
                    placeholders={"entity": self._temp},
                ),
            )
        )
        if air is None:
            # A fully unavailable room sensor is at least as untrustworthy as
            # an open window or a frozen reading, so it must drop the same
            # learning/window-auto anchors as the pause branch below --
            # otherwise the eventual reconnect re-anchors
            # ``_last_mono``/``_prev_room_mono`` across the whole outage and
            # the EKF integrates a real-looking dt over an interval it never
            # actually observed (ADR-0012/0024). The slope detector's own
            # reference point is reset too (``_wa_ref_*``, ``_wa_prev_mono``):
            # letting it survive an outage would let the next good sample
            # compute a rate/dt across the *sensor* gap rather than real room
            # movement, which is exactly the false-open risk the
            # quantized-slope anchor was built to avoid.
            self._last_mono = None
            self._prev_room = None
            self._prev_room_mono = None
            self._heatup_acc.reset()
            self._wa_ref_room = None
            self._wa_ref_mono = None
            self._wa_prev_mono = None
            return TickPlan(
                actuator_plan=None,
                external_temperature_plan=None,
                pre_events=(),
                post_actions=(),
                persistence=PersistencePhase.BEFORE_EXECUTION,
                control_data={},
                finalize_context=None,
            )
        self._unavailable_since = None
        if self._unavailable_logged:
            _LOGGER.info(
                "Poise %s: room temperature sensor %s is back; resuming control",
                self.zone_name,
                self._temp,
            )
            self._unavailable_logged = False
        # ONE snapshot bundles the contiguous pre-first-await read block.
        # Within this await-free segment nothing can change between reads, so
        # the re-read of the room here is provably the value the gate above
        # saw, and the segment's ad-hoc clock reads unify onto the snapshot
        # instants (sub-ms, unobservable). Every read AFTER the first await
        # stays a positioned InputReader call at exactly its place in the tick.
        inputs = self._input_reader.snapshot()
        ing = self._stage_ingest(inputs, air)
        # Ingest checkpoint [2-8]: the seven device-health updates, emitted at
        # the stage boundary within the same await-free segment (position
        # proof in the docstring above).
        self._emit_health_updates(ing.health_updates)
        obs = self._stage_observe(inputs, ing)
        # Observe checkpoint: window_sensor_unavailable, emitted mid-stage
        # before the reset — same await-free-segment proof.
        self._emit_health_updates(obs.health_updates)
        floors = self._stage_safety_floors(ing)
        # Safety-floors checkpoint: mould_protection_inactive, emitted at the
        # end of the block — same proof.
        self._emit_health_updates(floors.health_updates)
        gate = self._stage_schedule_gate(inputs, ing, obs)
        return PrepareContinuation(
            forecast_request=gate.forecast_request,
            prepared_state=PreparedState(
                inputs=inputs,
                ingest=ing,
                observation=obs,
                floors=floors,
                sched=gate.sched,
            ),
        )

    def _stage_ingest(self, inputs: TickInputs, air: float) -> IngestResult:
        """Health flags + temperature/environment ingest.

        Body in ``tick_pipeline.stage_ingest`` via the runtime (incl. the
        device-health evaluation, whose InputReader DISCOVERY entity ids —
        static bootstrap results, no live read — are injected here).
        ``is_frozen`` (patch surface for test_phase0_safety_precedence) and
        ``ingest_temperature`` (test_phase6_health_checkpoints) dispatch
        through THIS module's globals at call time, so patches on
        ``custom_components.poise.coordinator`` keep hitting every call.
        """
        reader = self._input_reader
        return self._zone_runtime.stage_ingest(
            inputs,
            air,
            entry_id=self._entry_id,
            temp_entity=self._temp,
            actuator_entity=self._actuator,
            sched_entity=reader.sched_entity,
            adaptive_mode_entity=reader.adaptive_mode_entity,
            fault_entity=reader.fault_entity,
            battery_entity=reader.battery_entity,
            is_frozen_fn=is_frozen,
            ingest_temperature_fn=ingest_temperature,
        )

    def _set_mpc_params(self, params: MpcParams) -> None:
        """Setter hook for the observe stage's ADR-0052 retune.

        ``_mpc_params`` is config-shaped per-tick derived tuning and stays a
        real adapter attribute; the pure stage mutates it through this
        injected setter so the retune's swallow boundary keeps its exact
        extent.
        """
        self._mpc_params = params

    def _stage_observe(
        self, inputs: TickInputs, ing: IngestResult
    ) -> ObservationResult:
        """Window signals, capability, dynamics retune, EKF learn gate and
        window-auto observation.

        Body in ``tick_pipeline.stage_observe`` via the runtime (learn,
        window-auto and seasonless observations). ``effective_window_open``
        (test_phase6_health_checkpoints) dispatches through THIS module's
        globals at call time; the module ``_LOGGER`` is injected so both
        swallow-boundary records keep the channel
        ``custom_components.poise.coordinator``.
        """
        return self._zone_runtime.stage_observe(
            inputs,
            ing,
            entry_id=self._entry_id,
            windows=self._windows,
            actuator_entity=self._actuator,
            window_auto_cfg=self._window_auto_cfg,
            adaptive_cool_cfg=self._adaptive_cool_cfg,
            dynamics_override=self._dynamics_override,
            effective_window_open_fn=effective_window_open,
            set_mpc_params=self._set_mpc_params,
            logger=_LOGGER,
        )

    def _stage_safety_floors(self, ing: IngestResult) -> SafetyFloorsResult:
        """Mould floor + dewpoint cap from humidity.

        Body in ``tick_pipeline.stage_safety_floors`` via the runtime;
        ``psychro_dewpoint`` (test_phase6_health_checkpoints) dispatches
        through THIS module's globals at call time.
        """
        return self._zone_runtime.stage_safety_floors(
            ing,
            entry_id=self._entry_id,
            humidity_entity=self._humidity,
            psychro_dewpoint_fn=psychro_dewpoint,
        )

    def _stage_schedule_gate(
        self, inputs: TickInputs, ing: IngestResult, obs: ObservationResult
    ) -> ScheduleGateResult:
        """Schedule state + predictive decision -- the forecast seam.

        Body in ``tick_pipeline.stage_schedule_gate`` via the runtime (no
        patch surface; config schedule/optimal-start/-stop injected).
        """
        return self._zone_runtime.stage_schedule_gate(
            inputs,
            ing,
            obs,
            schedule=self._schedule,
            optimal_start=self._optimal_start,
            optimal_stop=self._optimal_stop,
        )

    async def resume_prepare(
        self, prep: PrepareContinuation, forecast: float | None
    ) -> TickPlan:
        """Prepare phase after the forecast seam, through the write path;
        returns the tick's ``TickPlan``.

        Continues at the post-await position. The actuation is an ORDERED
        multi-segment program — Nudge-Plan→Nudge-Exec+Commit → Echo/Adoption
        → Setpoint-Gate/Plan→Setpoint-Exec+Commit →
        Ext-Temp-Read/Plan→Exec+Commit (or, on the disabled/off-held path,
        Rescue-Plan→Exec+Commit+Events) — NOT one ``apply(plan)`` block after
        all decisions. Reorder verdict, one proof-of-dependency per segment
        boundary (all verified against the executed code):

        1. The §4 regulation throttle (``_stage_setpoint_observe``) reads
           ``self._override`` AFTER the mode-nudge await, while the guard's
           ``is_safety`` gate (``_stage_mode_nudge``) reads it BEFORE that
           await. ``set_override`` is synchronous and lock-free — a user
           service call landing during the nudge dispatch is seen by the
           throttle but not by the guard. Both read positions are
           load-bearing → the nudge exec cannot move behind the setpoint
           decision, nor the decision ahead of the nudge.
        2. The setpoint write gate reads ``self._mode_override`` after the
           nudge await (same concurrency window, plus this-tick mutations
           by ``_stage_mode_adoption``'s ``_set_mode_override``/
           ``_end_hold``) → the gate stays after nudge + adoption.
        3. The adoption (``_stage_setpoint_adopt``) is a domain mutation
           BETWEEN the writes: ``set_override`` stamps the hold expiry with
           ``dt_util.utcnow()`` — wall time advanced by the nudge-dispatch
           duration is observable in ``override_expires_at`` — and moves
           the echo baselines (``_pre_write_sp``/``_last_written_sp``/
           ``_last_sp_write_ts``/``_prev_device_sp``) the write gate and
           next tick consume (``_adopted_sp`` skips this tick's write).
        4. The ext-temp select state is a positioned FRESH read after the
           mode/setpoint awaits → the ext segment stays last.

        The positioned post-await reads keep their places INSIDE their stages
        (presence, ext-feed probe, THE actuator read, device_min, the
        ext-select fresh read). Ends BEFORE the ``AFTER_EXECUTION`` savepoint
        with the fully built ``TickPlan``.
        """
        state = prep.prepared_state
        inputs = state.inputs
        ing = state.ingest
        obs = state.observation
        floors = state.floors
        sched = state.sched
        # The two arms of the ``if predictive:`` seam (the await itself moved
        # to ``_run_once``): ``forecast`` is non-None on the request arm --
        # ``_forecast_outdoor`` returns ``fallback`` on every failure -- so
        # the degenerate mypy guard degrades to exactly that same fallback
        # value and is unreachable in practice.
        if prep.forecast_request is not None:
            t_out_lead = forecast if forecast is not None else ing.t_out_eff
            model: ThermalModel | None = self._ekf.get_model()
        else:
            t_out_lead, model = ing.t_out_eff, None
        sp = self._stage_schedule_presence(
            ing, obs, sched, t_out_lead=t_out_lead, model=model
        )
        op = self._stage_operative_mode(inputs, ing)
        # Operative checkpoint: operative_unsupported, emitted mid-stage.
        # POSITION PROOF: that position and this checkpoint sit in the SAME
        # await-free window (between the forecast await and the
        # failure-detect/mode-nudge dispatches) — no suspension point between
        # them, so no other task can interleave; same
        # single-thread/registry-listener rationale as the prepare
        # checkpoints (``prepare_until_forecast`` docstring).
        self._emit_health_updates(op.health_updates)
        lvl = self._stage_presence_level(ing, obs, sched, sp)
        decision = self._stage_comfort_solve(ing, obs, floors, sp, op, lvl)
        wt = self._stage_write_target(ing, obs, floors, op, decision)
        band = self._stage_climate_band(ing, obs, sp, lvl, op, decision, wt)
        intents = self._stage_intents(ing, obs, wt)
        # ``_notify_failure``'s body is purely synchronous (awaiting a
        # never-suspending coroutine runs it to completion on the calling task
        # without yielding to the loop), so the plain call is
        # scheduling-identical at this position.
        failed = self._stage_failure_detect(ing, wt, intents)
        res = self._stage_mode_resolution(ing, obs, op, wt, band)
        routing = self._stage_hold_routing(wt)
        # Branch-dependent values: the defaults from the resolution and
        # routing stages hold on the disabled / off-held path; the enabled
        # path's stages return the updated values.
        guard_block = res.guard_block
        mode_nudge_blocked = res.mode_nudge_blocked
        mode_adopt_reason = routing.mode_adopt_reason
        sp_adopt_reason = routing.sp_adopt_reason
        actuator_plan: ActuatorPlan | None = None
        ext_plan: ExternalTemperaturePlan | None = None
        if self._enabled and not routing.off_held:
            adoption = self._stage_mode_adoption(ing, obs, wt, res, routing)
            mode_adopt_reason = adoption.mode_adopt_reason
            nudge = await self._stage_mode_nudge(
                ing, obs, wt, res, adoption, mode_nudge_blocked=mode_nudge_blocked
            )
            guard_block = nudge.guard_block
            mode_nudge_blocked = nudge.mode_nudge_blocked
            spo = self._stage_setpoint_observe(ing, obs, wt, res, routing, nudge)
            sp_adopt_reason = self._stage_setpoint_adopt(
                ing, obs, routing, spo, mode_adopt_reason=mode_adopt_reason
            )
            actuator_plan = await self._stage_setpoint_write(
                ing, wt, res, adoption, nudge, spo
            )
            ext_plan = await self._stage_ext_temp_feed(ing, op)
        else:
            actuator_plan = await self._stage_frost_rescue(
                ing, obs, floors, wt, routing
            )
        ctx = self._build_finalize_context(
            state=state,
            sp=sp,
            op=op,
            decision=decision,
            wt=wt,
            band=band,
            intents=intents,
            failed=failed,
            res=res,
            guard_block=guard_block,
            mode_nudge_blocked=mode_nudge_blocked,
            mode_adopt_reason=mode_adopt_reason,
            sp_adopt_reason=sp_adopt_reason,
        )
        # TickPlan assembly — pure frozen construction like the
        # FinalizeContext build above (same reorder proof: only
        # already-computed stage values, no ``self`` reads, no I/O, no
        # logging). ``pre_events``/``post_actions`` are EMPTY structural
        # seams: the expiry/preheat events fired at their in-stage positions
        # (deferral has no unobservability proof, see ``_run_once``) and the
        # rescue ``EndHold`` was applied by the rescue segment's own commit
        # (its events fired there too — Rescue-Plan→Exec+Commit+Events).
        # ``control_data`` stays empty: the FinalizeContext is the live
        # handover; the presenter/collector split populates it.
        return TickPlan(
            actuator_plan=actuator_plan,
            external_temperature_plan=ext_plan,
            pre_events=(),
            post_actions=(),
            persistence=PersistencePhase.AFTER_EXECUTION,
            control_data={},
            finalize_context=ctx,
        )

    def _stage_schedule_presence(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sched: ScheduleState,
        *,
        t_out_lead: float,
        model: ThermalModel | None,
    ) -> SchedulePresenceResult:
        """House-presence gate, timed-state expiry, preheat/coast plan
        (ADR-0058/0059, ADR-0025/0034).

        INVARIANT (pinned): the timed-state expiry runs BEFORE the preset is
        read (``_expire_timed_states`` before ``_base_preset``); the presence
        read is the positioned read AFTER the forecast await.
        """
        room = ing.room
        can_heat = obs.can_heat
        lo, hi = HEATING_LOWER[self._category], HEATING_UPPER[self._category]

        # ADR-0058 presence coupling. Resolve the house gate BEFORE the preheat
        # plan: an empty house (home is False) or a manual Away preset means
        # "away", whose depth is carried by the Eco band-widen below (not a base
        # shift), so we feed a NEUTRAL preset base into the plan to avoid a
        # cooling-edge double-dip, and an empty house is never preheated.
        # Positioned read AFTER the forecast await: a presence flip during the
        # fetch is observable and must remain so. The reader resolves the
        # presence tristates (a person/device_tracker reporting a named zone
        # is a confident "not home"); home and occupancy sit in the same
        # await-free window, so the merged PresenceSnapshot read is equivalent.
        _presence = self._input_reader.read_presence()
        _home = any_present(_presence.home)
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
        return SchedulePresenceResult(
            home=_home,
            presence=_presence,
            base=base,
            preheating=preheating,
            preheat_outdoor=preheat_outdoor,
            coasting=coasting,
        )

    def _stage_operative_mode(
        self, inputs: TickInputs, ing: IngestResult
    ) -> OperativeResult:
        """Operative TRV-input mode (ADR-0029). The ext-feed target probe is
        the positioned read after the forecast await.

        operative_unsupported is collected at its evaluation position and
        returned for the stage-end checkpoint; the ``TickStageError`` wrap
        transports it out of a mid-body abort (empty-pending aborts propagate
        bare).
        """
        pending: list[HealthUpdate] = []
        try:
            room = ing.room
            t_mrt = ing.t_mrt
            # operative TRV-input mode (ADR-0029): write the operative target
            # and feed the operative temperature, IF the thermostat can be
            # calibrated to an external sensor (i.e. a valid
            # external-temperature input). Otherwise fall back to air-side
            # control and flag a repair issue (fault tolerance).
            # external-temp input: explicit config, else auto-detected on the
            # device (pavax-verified). The number is write-only, so a
            # "unknown" state is fine; only "unavailable" means the device is
            # offline (ADR-0029).
            ext_num = self._trv_ext_temp or (
                inputs.device_guards.ext_temp_number if self._operative_input else None
            )
            # Positioned read: the feed target's availability is probed here,
            # after the forecast await.
            ext_ok = self._input_reader.ext_feed_target_ok(ext_num)
            operative_active = self._operative_input and ext_ok
            pending.append(
                HealthUpdate(
                    issue_id=f"operative_unsupported_{self._entry_id}",
                    active=self._operative_input and not ext_ok,
                    translation_key="operative_unsupported",
                    placeholders={"entity": ext_num or "—"},
                )
            )
            if operative_active:
                room_decide = operative_temperature(room, t_mrt)
                t_mrt_decide: float | None = None  # MRT lives in the fed values
            else:
                room_decide = room
                t_mrt_decide = t_mrt
            return OperativeResult(
                ext_num=ext_num,
                ext_ok=ext_ok,
                operative_active=operative_active,
                room_decide=room_decide,
                t_mrt_decide=t_mrt_decide,
                health_updates=tuple(pending),
            )
        except BaseException as err:  # transport-only; unwrapped in _run_once
            if pending:
                raise TickStageError(err, tuple(pending)) from err
            raise

    def _stage_presence_level(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sched: ScheduleState,
        sp: SchedulePresenceResult,
    ) -> PresenceLevelResult:
        """Presence level, room absence, window episode, eco widen (ADR-0058)."""
        now = ing.now
        window_open = obs.window_open
        preheating = sp.preheating
        _presence = sp.presence
        _home = sp.home
        # ADR-0058: resolve the presence level (the house gate is already folded
        # into _is_away above). Room-absence only modulates inside the comfort
        # window and never overrides a preheat. Level -> (occupied, eco_widen,
        # cool ceiling): COMFORT keeps the base behaviour; ROOM_ECO widens by the
        # Eco delta capped at the cool hard cap; AWAY widens by the away offset up
        # to the device max. No base shift -- the widen carries the whole depth.
        _presence_now = dt_util.utcnow().timestamp()
        _room_present = any_present(_presence.occupancy)
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
        # Track the rising edge of the open-window episode on the tick's
        # monotonic clock (``now``) so the mould floor can be suppressed for
        # its first WINDOW_MOULD_SUPPRESS_S below.
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
        return PresenceLevelResult(
            level=_level,
            absent_min=_absent_min,
            occupied=_occupied,
            eco_widen=_eco_widen,
            cool_ceiling=_cool_ceiling,
        )

    def _stage_comfort_solve(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        sp: SchedulePresenceResult,
        op: OperativeResult,
        lvl: PresenceLevelResult,
    ) -> ComfortDecision:
        """The central comfort solver (already pure).

        Body in ``tick_pipeline.stage_comfort_solve`` via the runtime;
        ``comfort_decide`` (patch surface for test_phase0_health_emission and
        test_review_v161_fixes) dispatches through THIS module's globals at
        call time — resolved per call, never bound at construction, so patches
        keep hitting.
        """
        return self._zone_runtime.stage_comfort_solve(
            ing,
            obs,
            floors,
            sp,
            op,
            lvl,
            category=self._category,
            cool_min_outdoor=self._cool_min_outdoor,
            cool_lockout_enabled=self._cool_lockout_enabled,
            heat_max_outdoor=self._heat_max_outdoor,
            heat_lockout_enabled=self._heat_lockout_enabled,
            priority=self._priority,
            cool_hard_cap=self._cool_hard_cap,
            comfort_decide_fn=comfort_decide,
        )

    def _stage_write_target(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        op: OperativeResult,
        decision: ComfortDecision,
    ) -> WriteTargetResult:
        """Actuator snapshot, cool raise, idle park, write-target resolution
        and frozen degradation (ADR-0051).

        ``act_state`` is THE central positioned actuator read (after the
        forecast await); safety-beats-override (frozen) replaces the resolved
        target.
        """
        now = ing.now
        frozen = ing.frozen
        t_out_eff = ing.t_out_eff
        t_rm_eff = ing.t_rm_eff
        window_open = obs.window_open
        can_heat = obs.can_heat
        can_cool = obs.can_cool
        device_max = obs.device_max
        mold_min = floors.mold_min
        room_decide = op.room_decide
        # Positioned read: THE central actuator read stays exactly here, after
        # the forecast await — a device change during the fetch is observable;
        # every later attribute access this tick reads this ONE State object,
        # never a fresh read.
        act_state = self._input_reader.actuator_state()
        # A genuinely offline actuator (state=="unavailable") reports no
        # trustworthy setpoint, so should_write()'s "actual is None -> write"
        # rule would fire on EVERY tick -- a write storm into a dead
        # Zigbee/MQTT device. Setpoint (and mode-nudge) writes are gated on
        # this below.
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
        # Idle-park: when idle, park toward the edge the room is closest to —
        # a warm reversible AC parks in cool at the cool edge, not in heat at
        # the low heat idle-hold (which needs a many-K drop to act and never
        # responds to a warming room). ONE decision drives both the written
        # value and the mode nudge (idle_park_mode below) so they never
        # disagree; a heat-only TRV always parks in heat (can_cool False ->
        # unchanged).
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
        # DIN 4108-2 is a steady-state criterion. Under an open window the
        # write target collapses to the floor (= max(frost, mould)); a humid
        # room would then heat toward ~24 C against the ventilation. Suppress
        # only the mould component for the first WINDOW_MOULD_SUPPRESS_S of the
        # episode -- the frost floor (FROST_FLOOR_C) is NEVER suppressed.
        # Diagnostics keep the real ``mold_min`` (see the ``mould_floor``
        # attribute below).
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
            # Fresh read — same await-free window as the central actuator
            # read above.
            device_min=self._input_reader.device_min(),
        )
        target, mode, norm_binding = wt.target, wt.mode, wt.norm_binding
        binding_precedence = wt.binding_precedence
        # Surface a silently band-clamped manual override (moot when frozen,
        # where the frost floor below replaces the override target entirely).
        override_clamped = wt.override_clamped and not frozen
        if frozen:
            # The room sensor is stale -> do not chase a comfort target on a
            # dead value. A heat-capable device degrades to the health floor
            # in heat (frost protection, held by the actuator's own sensor,
            # fail toward warmth); a cool-only device must NOT be pinned to
            # the floor in cool (it would cool the room to ~7 C) -> command off.
            if can_heat:
                target = frozen_safe_target(FROST_FLOOR_C, mold_min)
                mode = "heat"
            else:
                mode = "off"
            self._last_target = target
        return WriteTargetResult(
            act_state=act_state,
            actuator_online=_actuator_online,
            cool_ac=_cool_ac,
            idle_park_mode=_idle_park_mode,
            eff_cool=eff_cool,
            target=target,
            mode=mode,
            norm_binding=norm_binding,
            binding_precedence=binding_precedence,
            override_clamped=override_clamped,
        )

    def _stage_climate_band(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sp: SchedulePresenceResult,
        lvl: PresenceLevelResult,
        op: OperativeResult,
        decision: ComfortDecision,
        wt: WriteTargetResult,
    ) -> ClimateBandResult:
        """Comfort stage, climate band -- the LEGACY climate-band error
        domain, resolved by F-HUMSHADOW (phase 10 only): humidity/dry LIVE
        decision -> free-running -> fan -> PMV -> ``climate_diag`` under ONE
        unsplittable boundary, warn-once preserved (pinned by
        test_phase0_fault_climate_domain). The grouped unpack keeps the domain
        within the stage-size bound."""
        room, rh, t_mrt, t_rm_eff = ing.room, ing.rh, ing.t_mrt, ing.t_rm_eff
        window_open, _home, room_decide = obs.window_open, sp.home, op.room_decide
        _level, _occupied, _absent_min = lvl.level, lvl.occupied, lvl.absent_min
        act_state, eff_cool = wt.act_state, wt.eff_cool
        mode, _cool_ac = wt.mode, wt.cool_ac
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
            # The pure free-running/fan/PMV shadow composition +
            # ``climate_diag`` assembly lives in ``diagnostics/shadows.py``;
            # the call stays INSIDE this one legacy try, so a failure anywhere
            # still degrades the whole dict together. The actuator-attribute
            # reads are hoisted into the (side-effect-free) argument
            # construction of the same guarded position.
            climate_diag = compose_climate_band(
                heat_sp=decision.heat_sp,
                cool_sp=decision.cool_sp,
                room=room,
                room_decide=room_decide,
                t_rm_eff=t_rm_eff,
                t_mrt=t_mrt,
                rh=rh,
                eff_cool=eff_cool,
                mode=mode,
                window_open=window_open,
                occupied=_occupied,
                presence_level=_level.value,
                absent_min=_absent_min,
                home_present=_home,
                category=self._category,
                cool_hard_cap=self._cool_hard_cap,
                cool_ac=_cool_ac,
                hum=_hum,
                abs_humidity_gkg=_w,
                hvac_modes=_modes_cl,
                has_fan_modes=bool(act_state and act_state.attributes.get("fan_modes")),
                fan_mode=act_state.attributes.get("fan_mode") if act_state else None,
                hvac_action=(
                    act_state.attributes.get("hvac_action") if act_state else None
                ),
            )
        except Exception:  # noqa: BLE001 - must never break the tick
            # Not purely shadow — on failure the LIVE dry mode-nudge silently
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
        return ClimateBandResult(climate_diag=climate_diag, hum_action=_hum_action)

    def _stage_intents(
        self, ing: IngestResult, obs: ObservationResult, wt: WriteTargetResult
    ) -> IntentsResult:
        """Heat/cool intent + EKF drive latches (ADR-0024).

        Body in ``tick_pipeline.stage_intents`` via the runtime (no patch
        surface, no config parameter)."""
        return self._zone_runtime.stage_intents(ing, obs, wt)

    def _stage_failure_detect(
        self, ing: IngestResult, wt: WriteTargetResult, intents: IntentsResult
    ) -> bool:
        """Heating-failure detector + notification.

        ``_notify_failure`` runs as a synchronous checkpoint emission at its
        position below (its body is purely synchronous, no suspension point,
        so the stage is an ordinary sync call). No stage-end deferral and no
        ``TickStageError`` wrap needed: the emission is immediate, so a later
        abort in this stage can never strand a pending update.
        """
        now = ing.now
        room = ing.room
        fault_active = ing.fault_active
        act_state = wt.act_state
        target = wt.target
        heating = intents.heating
        # The failure detector keys on the actuator's real running state
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
        self._notify_failure(failed)
        # Latch for the NEXT tick's learn gate (this tick's gate already ran).
        self._prev_heating_failed = failed
        return failed

    def _stage_mode_resolution(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        op: OperativeResult,
        wt: WriteTargetResult,
        band: ClimateBandResult,
    ) -> ModeResolutionResult:
        """Mode arbitration + compressor-guard policy (ADR-0046 paragraph 8).

        Body in ``tick_pipeline.stage_mode_resolution`` via the runtime — the
        invariant (unconditional ``final_mode``/guard resolution, pinned by
        test_frost_rescue_disabled) lives in the moved body."""
        return self._zone_runtime.stage_mode_resolution(
            ing,
            obs,
            op,
            wt,
            band,
            cool_min_outdoor=self._cool_min_outdoor,
            cool_lockout_enabled=self._cool_lockout_enabled,
            heat_max_outdoor=self._heat_max_outdoor,
            heat_lockout_enabled=self._heat_lockout_enabled,
            compressor_guard=self._compressor_guard,
            comp_min_off_opt=self._comp_min_off_opt,
            comp_mode_hold_opt=self._comp_mode_hold_opt,
        )

    def _stage_hold_routing(self, wt: WriteTargetResult) -> HoldRoutingResult:
        """Own-write echo + off-hold routing + user-resume escape.

        INVARIANT (pinned): the off-hold frost route keeps its one-tick delay
        -- ``off_held`` reads the persisted hold at tick start; the adopting
        tick still runs the enabled block.

        Body in ``external_override.stage_hold_routing`` via the runtime. The
        user-resume escape's ``_end_hold`` is injected, so its teardown +
        IMMEDIATE bus fire keep their in-stage position.
        """
        return self._zone_runtime.stage_hold_routing(wt, end_hold_fn=self._end_hold)

    def _stage_mode_adoption(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        routing: HoldRoutingResult,
    ) -> ModeAdoptionResult:
        """External-mode adoption, guard-reference freeze, hold pinning.

        INVARIANT (pinned): an active mode-hold pins the desired mode unless
        window/frost took over this tick (safety beats hold).

        Body in ``external_override.stage_mode_adoption`` via the runtime,
        with the unified ONE-call observation (decision AND reason; see the
        module docstring there). ``resolve_desired_mode``/``mode_adopt_reason``
        resolve from THIS module's globals at call time (patch surface); the
        injected command facades keep the ``dt_util`` reads and the
        ``poise_override_ended`` fire at their in-stage positions.
        """
        return self._zone_runtime.stage_mode_adoption(
            ing,
            obs,
            wt,
            res,
            routing,
            adopt_external_mode=self._adopt_external_mode,
            resolve_desired_mode_fn=resolve_desired_mode,
            mode_adopt_reason_fn=mode_adopt_reason,
            set_mode_override_fn=self._set_mode_override,
            end_hold_fn=self._end_hold,
        )

    async def _stage_mode_nudge(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        adoption: ModeAdoptionResult,
        *,
        mode_nudge_blocked: str,
    ) -> ModeNudgeResult:
        """Mode-nudge segment: Nudge-Plan → Nudge-Exec + Commit.

        The decision (nudge need + compressor-guard block) is resolved first
        and travels typed in ``ModeNudgeResult``; the ``ActuatorPlan`` later
        RECORDS it (``write_mode``/``hvac_mode``). This segment must execute
        BEFORE the setpoint observation/gate: the ``is_safety`` read of
        ``self._override`` below sits before the nudge await while the §4
        throttle's read sits after it — both positions are load-bearing
        (reorder proof 1 in ``resume_prepare``)."""
        now = ing.now
        frozen = ing.frozen
        window_open = obs.window_open
        act_state = wt.act_state
        _guard_pol = res.guard_pol
        act_modes = res.act_modes
        desired_hvac = adoption.desired_hvac
        _mode_nudge_blocked = mode_nudge_blocked
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
            # An active manual override is deliberately exempt from the
            # compressor-guard hold, same as a genuine safety trip (open
            # window / frozen sensor) -- ADR-0046 states this explicitly
            # (is_safety covers window->off, frost, override and frozen, never
            # blocked). A user's manual intent must not be held hostage by a
            # min-off/mode-hold timer.
            is_safety=window_open or frozen or self._override is not None,
        )
        if _mode_nudge and _guard_block:
            _mode_nudge = False  # compressor protection: hold this tick's nudge
            _mode_nudge_blocked = _guard_block
        if _mode_nudge:
            # The executor sequence owns the boundary, the own-context
            # creation (tag our own mode change; the id reports even when the
            # dispatch throws — attempt state, test_phase0_attempt_success)
            # and the boundary log. The commit right HERE folds the stamps —
            # it must stay a SEPARATE commit from the setpoint write's below:
            # the code between the two sites reads the mode stamps. Stamp the
            # mode echo baseline so our own nudge is never re-read as an
            # external mode change next tick. Only re-arm the echo window on a
            # mode *change* -- re-arming on every identical re-nudge (a device
            # that never follows) would keep the window open forever and
            # permanently block adoption; evaluated at DISPATCH time, before
            # the stamp moves the ``_last_commanded_hvac`` baseline.
            report = await self._actuator_executor.run_mode_nudge(
                self._actuator,
                desired_hvac,
                mode_changed=desired_hvac != self._last_commanded_hvac,
            )
            self.commit_execution(report, now=now)
        return ModeNudgeResult(
            mode_nudge=_mode_nudge,
            guard_block=_guard_block,
            mode_nudge_blocked=_mode_nudge_blocked,
        )

    def _stage_setpoint_observe(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        routing: HoldRoutingResult,
        nudge: ModeNudgeResult,
    ) -> SetpointObservation:
        """Device setpoint observation, ADR-0052 paragraph-4 throttle,
        own-echo re-baseline and external-setpoint detection.

        Body in ``tick_pipeline.stage_setpoint_observe`` via the runtime. The
        two ``parse_attr_number`` reads of the tick's ONE actuator State
        object (incl. the ``or 0.1`` step fallback) are pre-parsed here: the
        helper lives in ``ha/`` and importing it into the pipeline would pull
        homeassistant into the pure py310 suite. Both are side-effect-free
        reads of the same frozen State object the stage consumes, so the hoist
        to this call boundary is unobservable (no patch surface on either).

        The stage's ONE tracker observation yields the adoption decision AND
        the ``sp_adopt_reason`` (carried in the ``SetpointObservation``);
        ``setpoint_adopt_reason`` resolves from THIS module's globals at call
        time (patch surface).
        """
        return self._zone_runtime.stage_setpoint_observe(
            ing,
            obs,
            wt,
            res,
            routing,
            nudge,
            actual_sp=parse_attr_number(wt.act_state, "temperature"),
            step=parse_attr_number(wt.act_state, "target_temperature_step") or 0.1,
            adopt_external_setpoint=self._adopt_external_setpoint,
            setpoint_adopt_reason_fn=setpoint_adopt_reason,
        )

    def _stage_setpoint_adopt(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        routing: HoldRoutingResult,
        spo: SetpointObservation,
        *,
        mode_adopt_reason: str,
    ) -> str:
        """Adoption-reason surfacing, debounced log, prev-update and the
        adoption itself.

        Returns the tick's ``sp_adopt_reason`` (the diagnosis string).

        Body in ``external_override.stage_setpoint_adopt`` via the runtime.
        The reason travels IN ``spo`` — computed together with the decision
        by the ONE observation in ``_stage_setpoint_observe`` from
        character-equal arguments (the re-derivation here saw the same
        ``prev_device_sp``: the prev-update sat AFTER the reason call).
        ``obs``/``routing`` stay in the pinned facade signature; the unified
        chain consumed them in the observe stage. ``set_override`` (full hold
        lifecycle + immediate events) is injected and runs at its in-stage
        position, the debounce log keeps this module's logger channel.
        """
        return self._zone_runtime.stage_setpoint_adopt(
            ing,
            spo,
            mode_adopt_reason=mode_adopt_reason,
            actuator_entity=self._actuator,
            logger=_LOGGER,
            set_override_fn=self.set_override,
        )

    def _plan_setpoint_write(
        self,
        wt: WriteTargetResult,
        adoption: ModeAdoptionResult,
        nudge: ModeNudgeResult,
        spo: SetpointObservation,
    ) -> ActuatorPlan:
        """Setpoint write gate → the tick's ``ActuatorPlan`` (gate position —
        see the reorder proofs in ``resume_prepare``).

        Body in ``tick_pipeline.plan_setpoint_write`` via the runtime."""
        return self._zone_runtime.plan_setpoint_write(wt, adoption, nudge, spo)

    async def _stage_setpoint_write(
        self,
        ing: IngestResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        adoption: ModeAdoptionResult,
        nudge: ModeNudgeResult,
        spo: SetpointObservation,
    ) -> ActuatorPlan:
        """Setpoint segment: gate/plan → dispatch → commit.

        The write DECISION is the ``ActuatorPlan`` from
        ``_plan_setpoint_write`` (same reads, same order, same await-free
        window as the inline gate); the executor sequence dispatches it and
        the commit folds the stamps. Returns the plan as the tick's
        actuator-write record for the ``TickPlan``.
        """
        now = ing.now
        final_mode = res.final_mode
        actual_sp = spo.actual_sp
        plan = self._plan_setpoint_write(wt, adoption, nudge, spo)
        if plan.write_setpoint:
            # By construction: values + the intended device mode
            # (``adoption.desired_hvac``, always a str) are set whenever
            # write_setpoint is.
            assert plan.raw_setpoint is not None
            assert plan.snapped_setpoint is not None
            assert plan.hvac_mode is not None
            cmd = ActuatorCommand(
                actuator_id=self._actuator,
                path=ActuatorPath.SETPOINT,
                value=plan.raw_setpoint,  # RAW on the wire
                hvac_mode=plan.hvac_mode,
                reason=plan.reason,
            )
            # The executor sequence owns the boundary, the own-context
            # creation (tag the call so the resulting state change carries a
            # Context we recognise as our own next tick — echo / clamp) and
            # the boundary log; the commit right here folds the stamps.
            # Attempt state commits even when the dispatch throws:
            # ``pre_write_sp`` — the device's reported setpoint just before
            # this write, the only other value a legit in-window echo can
            # carry (poll lag), remembered for next tick's three-value
            # adoption test — and the context-id registration. Success stamps
            # the SNAPPED target as the echo baseline (the raw value went on
            # the wire).
            report = await self._actuator_executor.run_setpoint_write(
                cmd,
                pre_write_value=actual_sp,
                snapped_value=plan.snapped_setpoint,
                final_mode=final_mode,
            )
            self.commit_execution(report, now=now)
        return plan

    async def _stage_ext_temp_feed(
        self, ing: IngestResult, op: OperativeResult
    ) -> ExternalTemperaturePlan | None:
        """External-temperature segment: read → plan → dispatch → commit
        (ADR-0029). The select's state stays a positioned fresh read inside
        the write path, after the mode/setpoint awaits (reorder proof 4 in
        ``resume_prepare``). Returns the executed ``ExternalTemperaturePlan``
        (None when the segment did not run) as the record for the
        ``TickPlan``."""
        now = ing.now
        room = ing.room
        t_mrt = ing.t_mrt
        ext_num = op.ext_num
        ext_ok = op.ext_ok
        operative_active = op.operative_active
        # feed the true room temperature to a TRV external-temperature input
        # (ADR-0029): the thermostat then modulates against the real sensor.
        if ext_num and ext_ok:
            # ensure the TRV uses its external sensor (pavax-verified); on
            # the tick we switch it, skip the write so the device can settle
            # — the select-success -> feed-skip coupling is sequence-INTERNAL
            # and owned by the executor (``skip_feed_on_select_success``; a
            # failed select still feeds). It never surfaces as a commit stamp.
            # Positioned read: the select's state is read FRESH in the write
            # path, after the mode-nudge/setpoint awaits — a select change
            # during those service calls is observable and stays so. ``None``
            # covers both "no select discovered" and "no State object".
            _sel_state = self._input_reader.ext_select_state()
            _select_external = _sel_state is not None and _sel_state not in (
                "external",
                "unavailable",
            )
            fed = round(
                operative_temperature(room, t_mrt) if operative_active else room,
                1,
            )
            # Both plan gates are decided BEFORE the sequence runs.
            # ``external_feed_due`` is pure and reads only state the select
            # never touches (``_last_fed``/``_last_fed_ts``), so evaluating it
            # up front is unobservable; ``feed_value=None`` = no feed planned
            # this tick ("not due" — nothing dispatched, nothing stamped).
            # ``ext_select_state()`` returns non-None only when a sensor
            # select was discovered, so the proxied id is never None when the
            # select is planned. Both calls stay untagged until F-CONTEXT
            # (phase 10); the commit right here folds the feed stamps.
            plan = ExternalTemperaturePlan(
                select_external=_select_external,
                feed_value=(
                    fed
                    if external_feed_due(
                        self._last_fed,
                        fed,
                        last_fed_ts=self._last_fed_ts,
                        now=now,
                        keepalive_s=EXTERNAL_FEED_KEEPALIVE_S,
                        deadband=0.1,
                    )
                    else None
                ),
            )
            report = await self._actuator_executor.run_ext_temp(
                plan,
                select_entity_id=self._sensor_select,
                number_entity_id=ext_num,
            )
            self.commit_execution(report, now=now)
            return plan
        return None

    async def _stage_frost_rescue(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        wt: WriteTargetResult,
        routing: HoldRoutingResult,
    ) -> ActuatorPlan | None:
        """Disabled/off-held path: Rescue-Plan → Exec + Commit + Events.

        The rescue gates (rescue_ok, ``frost_rescue_target``, the online
        gate, the heat-nudge need) decide the rescue ``ActuatorPlan``
        (``reason="frost_rescue"``: the floor travels raw; NO snapped echo
        baseline — the commit clears it). The ``EndHold("frost_rescue")``
        post-action stays decoupled from write success (pinned by the phase-0
        frost-rescue matrix); the events fire right here after the commit —
        after the write attempts, before the savepoint — which is why this
        segment keeps them instead of the coordinator seam
        (Rescue-Plan→Exec+Commit+Events). Returns the executed plan (None when
        no rescue write ran) for the ``TickPlan``.
        """
        now = ing.now
        room = ing.room
        can_heat = obs.can_heat
        mold_min = floors.mold_min
        act_state = wt.act_state
        _actuator_online = wt.actuator_online
        _off_held = routing.off_held
        # A disabled zone still gets unconditional frost/mould protection
        # (README promise) — but rescue-only, so a reasonable manual setpoint
        # above the floor is never fought; a cool-only device has no frost
        # duty and is left alone (frost_rescue_target -> None). A user-held
        # ``off`` (device switched off via the remote, Poise still enabled) is
        # honoured like a disabled zone -- but unlike a truly disabled zone we
        # must NOT treat the warm off device as perpetual frost demand
        # (``frost_rescue_target`` rescues an off heater on principle), or we
        # would restart the device the user deliberately switched off. So an
        # off-HELD zone is rescued only when the ROOM is actually at the
        # frost/mould floor; a disabled zone keeps the unconditional rescue.
        _rescue_ok = (
            (not _off_held)
            or room <= FROST_FLOOR_C
            or (mold_min is not None and room <= mold_min)
        )
        rescue = (
            frost_rescue_target(
                can_heat=can_heat,
                actual_sp=parse_attr_number(act_state, "temperature"),
                device_state=act_state.state if act_state else None,
                frost_floor=FROST_FLOOR_C,
                mold_min=mold_min,
                deadband=WRITE_DEADBAND_C,
            )
            if _rescue_ok
            else None
        )
        # ``frost_rescue_target`` treats "unavailable" as "inactive" on
        # purpose (an off/unknown/unavailable device below the floor all
        # legitimately need the rescue floor) -- but that means it returns a
        # non-None target on EVERY tick for a genuinely offline actuator, so
        # unlike the enabled-branch setpoint write above, this write is gated
        # on ``_actuator_online``: otherwise a disabled zone with a dead
        # actuator would dispatch a real ``climate.set_temperature`` into the
        # void every tick. Off/unknown (actuator present, just not in "heat")
        # still get the rescue write.
        if rescue is not None and _actuator_online:
            _rmodes = (
                (act_state.attributes.get("hvac_modes") or []) if act_state else []
            )
            _cur = act_state.state if act_state else None
            # The decided rescue plan — the nudge need is evaluated directly
            # for the run_frost_rescue call.
            plan = ActuatorPlan(
                write_mode=_cur != "heat" and "heat" in _rmodes,
                hvac_mode="heat",
                write_setpoint=True,
                snapped_setpoint=None,  # no echo baseline for the floor
                raw_setpoint=rescue,
                reason="frost_rescue",
            )
            # The executor sequence owns the TWO INDEPENDENT boundaries — a
            # failed mode-nudge must never skip the safety setpoint write (the
            # floor still has to be sent) — plus both untagged payloads and
            # the boundary logs. The commit right here folds the stamps:
            # frost-rescue heat is our own safety mode, never a user change —
            # mode echo baseline, ts re-armed UNCONDITIONALLY; the frost floor
            # is our own value, not user intent -> ``last_written_sp=None``;
            # plus ``_mark_actuated``.
            report = await self._actuator_executor.run_frost_rescue(
                self._actuator,
                rescue,
                nudge=plan.write_mode,
            )
            # A frost/mould rescue that fires while an ``off`` hold is active
            # supersedes the user's off intent -- end the hold with an
            # accurate reason ("frost_rescue") instead of leaving the device
            # escape to end it next tick under the generic "user_resume". The
            # ``EndHold`` post-action (require_success=False) runs AFTER the
            # report fold and is never coupled to write success (phase-0
            # frost-rescue matrix, all four cells); the adapter fires the
            # returned ``poise_override_ended`` event right after the commit —
            # after the write attempts, before the ``_maybe_save`` checkpoint.
            commit = self.commit_execution(
                report,
                post_actions=((EndHold("frost_rescue"),) if _off_held else ()),
                now=now,
            )
            for ev in commit.events:
                self._fire_override_ended(ev.reason)
            return plan
        return None

    def _build_finalize_context(
        self,
        *,
        state: PreparedState,
        sp: SchedulePresenceResult,
        op: OperativeResult,
        decision: ComfortDecision,
        wt: WriteTargetResult,
        band: ClimateBandResult,
        intents: IntentsResult,
        failed: bool,
        res: ModeResolutionResult,
        guard_block: str | None,
        mode_nudge_blocked: str,
        mode_adopt_reason: str,
        sp_adopt_reason: str,
    ) -> FinalizeContext:
        """Assemble the prepare->finalize contract from the typed stage
        results (pure construction — no ``self`` reads, no I/O).

        Body in ``tick_pipeline.build_finalize_context`` via the runtime; the
        field set (50 names, pinned by test_phase1_tick_result) is unchanged."""
        return self._zone_runtime.build_finalize_context(
            state=state,
            sp=sp,
            op=op,
            decision=decision,
            wt=wt,
            band=band,
            intents=intents,
            failed=failed,
            res=res,
            guard_block=guard_block,
            mode_nudge_blocked=mode_nudge_blocked,
            mode_adopt_reason=mode_adopt_reason,
            sp_adopt_reason=sp_adopt_reason,
        )

    async def finalize_tick(self, ctx: FinalizeContext) -> TickOutcome:
        """Everything after the AFTER_EXECUTION savepoint, split into stage
        methods.

        Orchestrates the finalize stages in text order: the neutral shadow
        seed + the LEGACY shadow error domain (``_stage_shadow_domain``),
        valve health with its immediate issue emission
        (``_stage_valve_health``), the outcome/HDH/RegQ/ref-offset/tau-settle
        collector boundary (``_stage_outcome_diag``), the ``_tick_data``
        assembly plus ``heat_demand`` (``_stage_assemble_tick_data``), then
        the trace record+append. Runs strictly AFTER the save checkpoint, so
        every runtime the stages advance (lifecycle fold, PI accumulator,
        outcome/HDH/RegQ/offset/settle) is captured by the NEXT save only.
        Every stage is synchronous — the segment stays await-free up to the
        trace append inside ``_maybe_record_trace``, which remains the LAST
        observable statement of the tick under the lock (F-TRACEIO is
        phase 10) — only pure, side-effect-free ``TickOutcome`` construction
        follows it.
        """
        now, room, rh, t_mrt = ctx.now, ctx.room, ctx.rh, ctx.t_mrt
        t_out_eff, t_rm_eff, act_state = ctx.t_out_eff, ctx.t_rm_eff, ctx.act_state
        heating, frozen = ctx.heating, ctx.frozen
        operative = operative_temperature(room, t_mrt)
        # Predictive solar-shading shadow (ADR-0043): forecast the peak operative
        # temperature (Tier-2 linear while the EKF is not identified, e.g. summer)
        # and what a cover *would* do — diagnostic only, no cover is moved yet.
        # --- Diagnostics-only shadows ---------------------------------------
        # The setpoint is already written above. A failure in any predictive
        # shadow (e.g. a degenerate value from a not-yet-identified EKF) must
        # NEVER take control reporting offline — so the whole block is guarded and
        # degrades to neutral diagnostics while the written setpoint stands.
        # The neutral fallback literal lives in ``diagnostics/shadows.py`` —
        # still WITHOUT the compressor_gate_* keys, so the degraded key set
        # keeps shrinking by exactly two keys. The neutral values double as
        # the shadow stage's seed — the stage initialises its locals from this
        # result and the domain's ONE ``try`` overwrites them step by step, so
        # partial progress before a failure stays observable.
        neutral = ShadowStageResult(
            operative=operative,
            binding="en16798",
            cover_peak=operative,
            cover_pos=0.0,
            cover_reason="",
            shadow_objs=neutral_shadow_objs(self._multi_lifecycle.health),
        )
        # LEGACY error domain, resolved by F-TPI / F-LIFECYCLE / F-PIACC
        # (phase 10 only): peak forecast → MPC → TPI → PI(+acc) → lifecycle
        # fold → thermal arbitration → shadow_objs share this ONE boundary. A
        # failure in ANY earlier step therefore degrades tpi_duty to None,
        # skips the lifecycle fold and freezes ``_pi.acc`` for the tick —
        # observable behaviour pinned by test_phase0_fault_shadow_domain; the
        # fallback ``shadow_objs`` above (WITHOUT the compressor_gate_* keys)
        # is the degraded payload.
        shadow = self._stage_shadow_domain(ctx, neutral)
        valve = self._stage_valve_health()
        # Valve checkpoint: kept at its EXACT position — the finalize
        # segment's only issue emission sits between the savepoint await and
        # the trace-append await, and the only later stage boundary lies
        # BEYOND that trace await, so a stage-end deferral would move the
        # emission across an await. No unobservability proof exists for that;
        # per the reorder rule the order is preserved structurally (the
        # emission merely goes through the typed checkpoint primitive). No
        # ``TickStageError`` wrap either: the emission is immediate, nothing
        # can be stranded.
        self._emit_health_updates(valve.health_updates)
        outcome_diag = self._stage_outcome_diag(ctx)
        _tick_data = self._stage_assemble_tick_data(
            ctx, shadow=shadow, valve=valve, outcome_diag=outcome_diag
        )
        # Capture the REAL actuator mode + action so a replayed trace can
        # explain a dehumidification episode — the thermal ``mode``
        # (idle/cool/heat/off) alone never carries the humidity/device axis,
        # so dry episodes would be invisible on disk.
        _tick_data["device_hvac_mode"] = act_state.state if act_state else ""
        _tick_data["hvac_action"] = (
            (act_state.attributes.get("hvac_action") or "") if act_state else ""
        )
        # INVARIANT: the trace append inside this call is the LAST observable
        # statement of the tick under the lock — its I/O duration counts into
        # ``tick_ms``. The record build stays fused with the append inside
        # ``_maybe_record_trace``'s guarded boundary (``_trace_enabled`` gate
        # + swallow-all): splitting the build out as a pure pre-step would
        # move a swallowed build failure onto the tick's error path. Only the
        # build INSTRUCTIONS live in the pure ``diagnostics/trace.py``; the
        # call site stays inside that boundary and ``TickOutcome.trace_record``
        # stays ``None`` until F-TRACEIO (phase 10).
        await self._maybe_record_trace(
            _tick_data, room=room, t_out=t_out_eff, rh=rh, t_rm=t_rm_eff, now=now
        )
        # Pure, side-effect-free construction only below this point: the hub
        # contract fields are lifted from the assembled payload verbatim, and
        # ``diagnostics`` carries the payload dict itself (the presenter
        # pre-form returns the SAME object, so ``coordinator.data`` and the
        # traced dict stay identical).
        return TickOutcome(
            data=AvailableTickData(
                mono_ts=now,
                heating=heating,
                sensor_frozen=frozen,
                current_temperature=_tick_data["current_temperature"],
                heat_sp=_tick_data["heat_sp"],
                tpi_duty=_tick_data.get("tpi_duty"),
                heat_demand=_tick_data["heat_demand"],
            ),
            diagnostics=_tick_data,
            trace_record=None,
        )

    def _stage_shadow_domain(
        self, ctx: FinalizeContext, neutral: ShadowStageResult
    ) -> ShadowStageResult:
        """The LEGACY shadow error domain as ONE stage, resolved only by
        F-TPI / F-LIFECYCLE / F-PIACC (phase 10): peak forecast → MPC → TPI →
        PI(+acc) → lifecycle fold → thermal arbitration → shadow_objs share
        the single ``try`` below, never cut through —
        test_phase0_fault_shadow_domain is the arbiter. The locals are seeded
        from ``neutral`` and overwritten step by step INSIDE the boundary, so
        a failure keeps the partial progress plus the neutral remainder (the
        fallback ``shadow_objs`` lacks the two compressor_gate_* keys).

        This stage deliberately exceeds the soft ~150-line stage bound — the
        body is the ONE indivisible legacy try domain (any further cut would
        move the pinned error boundary) plus the grouped ctx unpack; shrinking
        it would split the fault-pinned domain body."""
        room, t_out_eff, t_rm_eff = ctx.room, ctx.t_out_eff, ctx.t_rm_eff
        q_solar, mold_min, decision = ctx.q_solar, ctx.mold_min, ctx.decision
        act_state, final_mode = ctx.act_state, ctx.final_mode
        _guard_pol, _g_min_off = ctx.guard_pol, ctx.g_min_off
        _g_mode_hold, _guard_block = ctx.g_mode_hold, ctx.guard_block
        operative, binding = neutral.operative, neutral.binding
        _cover_peak, _cover_pos = neutral.cover_peak, neutral.cover_pos
        _cover_reason, shadow_objs = neutral.cover_reason, neutral.shadow_objs
        try:
            # Composition in ``diagnostics/shadows.py``; the two kernels are
            # passed as ``*_fn`` resolved from THIS module's globals at call
            # time, so patching ``coordinator.predict_peak_operative``
            # (test_phase0_fault_shadow_domain) keeps hitting the dispatch.
            _cover_peak, _cover_pos, _cover_reason, binding = evaluate_cover_shadow(
                operative=operative,
                t_out_eff=t_out_eff,
                q_solar=q_solar,
                cool_sp=decision.cool_sp,
                heat_sp=decision.heat_sp,
                mold_min=mold_min,
                model=self._ekf.get_model(),
                identified=self._ekf.identified,
                temperature_std=self._ekf.temperature_std,
                predict_peak_operative_fn=predict_peak_operative,
                shading_target_position_fn=shading_target_position,
            )
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
                external=t_out_eff,  # real outdoor temp
                dt_h=TICK_INTERVAL_S / 3600.0,
            )
            # The shadow is pure — advance the persisted integrator here,
            # exactly once per tick, instead of as a hidden side effect of the
            # read.
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
            # Fold the actuator's run-state into the per-device lifecycle on a
            # wall-clock basis, then derive the resolver's min-off / health gate.
            _now_wall = dt_util.utcnow().timestamp()
            _act_action = act_state.attributes.get("hvac_action") if act_state else None
            # INVARIANT (K2b, ADR-0046 §9): lifecycle observe() runs after
            # guard diagnosis; the pre-observe gate mirrors the write-path
            # guard. Pinned by test_dry_nudge_when_humid_and_idle. Folding
            # observe first would let the guard judge against its own intent
            # and self-armed mode hold (see the note at
            # ``_stage_hold_routing``).
            # ADR-0046 §8 compressor protection (LIVE): the same decision the
            # write path above already applied (_guard_block), surfaced here
            # as a diagnostic; the display policy uses the effective timers so
            # the remaining-time attributes match the live gate.
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
            # EntitySnapshot/ThermalDemand construction and the shadow_objs
            # assembly live in ``diagnostics/shadows.py``; the kernels keep
            # dispatching through THIS module's globals at call time
            # (``evaluate_thermal_shadow``, ``_lifecycle.*``).
            multi_shadow = evaluate_multi_shadow(
                entity_id=self._actuator,
                hvac_modes=_act_modes,
                available=_act_avail,
                direction=_THERMAL_DIR.get(decision.mode),
                target=decision.target,
                runtime=_multi_runtime,
                evaluate_thermal_shadow_fn=evaluate_thermal_shadow,
            )
            shadow_objs = assemble_shadow_objs(
                pi=pi,
                multi_shadow=multi_shadow,
                tpi=tpi,
                shadow=shadow,
                lifecycle=self._multi_lifecycle,
                now_wall=_now_wall,
                multi_policy=_multi_policy,
                comp_pol=_comp_pol,
                comp_block=_comp_block,
                min_off_remaining_fn=_lifecycle.min_off_remaining,
                mode_hold_remaining_fn=_lifecycle.mode_hold_remaining,
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            _LOGGER.exception(
                "Poise: shadow evaluation failed; the written setpoint stands, "
                "diagnostics degraded this tick"
            )
        return ShadowStageResult(
            operative=operative,
            binding=binding,
            cover_peak=_cover_peak,
            cover_pos=_cover_pos,
            cover_reason=_cover_reason,
            shadow_objs=shadow_objs,
        )

    def _stage_valve_health(self) -> ValveHealthResult:
        """Valve-stuck detection over the POSITIONED fresh read: the
        calibration counts are read AFTER the save-checkpoint await. Returns
        the finalize segment's only ``HealthUpdate`` for the caller's
        immediate emission."""
        # valve health: a near-zero closing-step count means the motorised
        # valve failed calibration / is jammed — advisory diagnostic + repair
        # issue. Positioned reads: the valve calibration counts are read FRESH
        # after the save-checkpoint await.
        closing_steps, idle_steps = self._input_reader.valve_steps()
        v_stuck = valve_stuck(closing_steps)
        valve_health = (
            "stuck" if v_stuck else ("ok" if closing_steps is not None else "unknown")
        )
        return ValveHealthResult(
            closing_steps=closing_steps,
            idle_steps=idle_steps,
            valve_health=valve_health,
            health_updates=(
                HealthUpdate(
                    issue_id=f"valve_stuck_{self._entry_id}",
                    active=v_stuck,
                    translation_key="valve_stuck",
                    placeholders={
                        "entity": self._input_reader.valve_closing_steps or "—"
                    },
                ),
            ),
        )

    def _stage_outcome_diag(self, ctx: FinalizeContext) -> dict[str, Any]:
        """ADR-0044/0045 outcome scoring + savings diagnostics behind the ONE
        collector boundary (``DiagnosticsCollector.safe_collect``). The
        returned mapping IS this stage's typed cross-stage value:
        ``safe_collect``'s replace-on-success dict — the collected 19 keys, or
        the 7-key defaults on failure (the second observable key-shrink
        mechanism); a wrapper dataclass would only re-wrap the collector
        contract's own typed return."""
        now, room, heating = ctx.now, ctx.room, ctx.heating
        decision, t_out_eff, q_solar = ctx.decision, ctx.t_out_eff, ctx.q_solar
        sched, window_open, frozen = ctx.sched, ctx.window_open, ctx.frozen
        room_decide, eff_cool, mode = ctx.room_decide, ctx.eff_cool, ctx.mode
        act_state = ctx.act_state
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

        # The boundary itself is ``DiagnosticsCollector.safe_collect`` — the
        # closure below runs the five state folds + assembly in text order
        # INSIDE that one try, so an exception in fold N still leaves
        # ``outcome_diag`` on the defaults, skips folds N+1… and freezes the
        # metrics until the next healthy tick (F-OUTFOLD, a documented
        # phase-10 candidate, would change that). The LIVE reads
        # (``self._enabled``, ``self._override``, ``dt_util.now().month``)
        # stay at their in-boundary positions and are evaluated at call time.
        def _collect_outcome_diag() -> dict[str, Any]:
            _tick_min = TICK_INTERVAL_S / 60.0
            # Real elapsed dt (event-driven refreshes book < 60 s, not a flat
            # tick -- same reasoning as the CA/offset dt below), capped so a
            # masked gap adds ~2 ticks instead of silently over/under-crediting
            # the HDH savings estimate and the outcome-session heating-time
            # integral.
            _hdh_dt = capped_elapsed_min(self._hdh_last_mono, now, _tick_min)
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
            # ADR-0055 regulation-quality metric (EN 15500-1 CA), SHADOW:
            # score only unmasked comfort ticks (room_decide vs the effective
            # band); the metric gates nothing yet — it must earn trust first.
            if (
                self._enabled
                and not window_open
                and not frozen
                and self._override is None
                and sched.is_comfort
            ):
                # Real elapsed (event-driven refreshes book < 60 s, not a flat
                # tick), capped so a masked gap adds ~2 ticks.
                _ca_dt = capped_elapsed_min(self._ca_last_mono, now, _tick_min)
                self._ca_last_mono = now
                self._regq = self._regq.observe(
                    room=room_decide,
                    heat_sp=decision.heat_sp,
                    cool_sp=eff_cool,
                    mode=mode,
                    dt_min=_ca_dt,
                )
            # ADR-0056 SHADOW: actuator<->room reference-frame offset (no writes).
            # Fold in a sample only while the actuator is actually conditioning
            # — its internal sensor carries the placement bias only under
            # active airflow/heat, so idle ticks would drag the offset toward
            # zero. Reuse the EKF drive signal (real hvac_action, intent
            # fallback); the warm-up therefore counts real conditioning time.
            # Diagnostic only: the write path stays room-referenced until
            # flip-gated live (ADR-0055).
            _ref_dt = capped_elapsed_min(self._ref_last_mono, now, _tick_min)
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
            # SHADOW: settle-based τ-confidence — has α (=1/τ) actually
            # converged, not just been counted (ADR-0024)? Fed only on
            # learn-active ticks (the same excitation signal, where α can
            # move); diagnostic only, no writes, until it clamps the preheat
            # lead live (ADR-0055).
            _tau_dt = capped_elapsed_min(self._tau_last_mono, now, _tick_min)
            self._tau_last_mono = now
            self._tau_settle = update_settle(
                self._tau_settle,
                alpha=self._ekf.x[1],
                dt_min=_tau_dt,
                learn_active=_ref_conditioning,
            )
            return build_outcome_diag(
                outcome_stats=self._outcome_stats,
                hdh=self._hdh,
                hdh_cfg=self._hdh_cfg,
                regq=self._regq,
                ref_offset=self._ref_offset,
                ref_conditioning=_ref_conditioning,
                tau_settle=self._tau_settle,
                eff_cool=eff_cool,
            )

        return self._diag_collector.safe_collect(_collect_outcome_diag, outcome_diag)

    def _stage_assemble_tick_data(
        self,
        ctx: FinalizeContext,
        *,
        shadow: ShadowStageResult,
        valve: ValveHealthResult,
        outcome_diag: dict[str, Any],
    ) -> dict[str, Any]:
        """The ``_tick_data`` assembly (presenter pre-form) plus
        ``heat_demand``, which MUST follow the assembly — it reads
        ``tpi_duty`` back out of the dict. Returns THE dict object itself: the
        trace consumes it, ``TickOutcome.diagnostics`` carries it and
        ``_present`` republishes it, so ``coordinator.data`` stays identical
        BY OBJECT to the traced payload (aliasing contract; the ``tick_ms*``
        attach in ``_async_update_data`` builds on the same dict).

        This stage deliberately exceeds the soft ~150-line stage bound — the
        ~115-line dict literal is kept verbatim as the aliasing-contract proof
        body; a cosmetic split would weaken the verbatim evidence without
        shrinking the proof surface."""
        now, room, rh, target = ctx.now, ctx.room, ctx.rh, ctx.target
        t_out_eff, t_rm_eff, t_rm_source = ctx.t_out_eff, ctx.t_rm_eff, ctx.t_rm_source
        q_solar, q_solar_source = ctx.q_solar, ctx.q_solar_source
        q_solar_internal, t_mrt = ctx.q_solar_internal, ctx.t_mrt
        mrt_source, mrt_internal = ctx.mrt_source, ctx.mrt_internal
        decision, mode, adaptive_cool = ctx.decision, ctx.mode, ctx.adaptive_cool
        heating, cooling, final_mode = ctx.heating, ctx.cooling, ctx.final_mode
        act_state, window_open, failed = ctx.act_state, ctx.window_open, ctx.failed
        override_clamped, mold_capped = ctx.override_clamped, ctx.mold_capped
        mold_min, dewpoint, sched = ctx.mold_min, ctx.dewpoint, ctx.sched
        reading_source, preheating = ctx.reading_source, ctx.preheating
        preheat_outdoor, coasting = ctx.preheat_outdoor, ctx.coasting
        frozen, norm_binding = ctx.frozen, ctx.norm_binding
        binding_precedence, sched_active = ctx.binding_precedence, ctx.sched_active
        fault_active, heat_source_suspect = ctx.fault_active, ctx.heat_source_suspect
        ext_num, operative_active = ctx.ext_num, ctx.operative_active
        climate_diag = ctx.climate_diag
        _mode_nudge_blocked = ctx.mode_nudge_blocked
        _idle_park_mode = ctx.idle_park_mode
        _mode_adopt_reason = ctx.mode_adopt_reason
        _sp_adopt_reason = ctx.sp_adopt_reason
        operative, binding = shadow.operative, shadow.binding
        _cover_peak, _cover_pos = shadow.cover_peak, shadow.cover_pos
        _cover_reason, shadow_objs = shadow.cover_reason, shadow.shadow_objs
        valve_health, closing_steps = valve.valve_health, valve.closing_steps
        idle_steps = valve.idle_steps
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
            # ADR-0038: monotonic stamp of when this snapshot was produced, so
            # the system hub can detect a silently stale zone (age-based
            # staleness).
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
            # Display contract: publish the arbitrated direction (final_mode)
            # and the actuator's own reported action so the entity's
            # hvac_action stays truthful during an override (where the raw
            # mode is "manual") and can prefer the device's real state.
            # "cooling" is published symmetric to "heating" (raw intent) to
            # close the asymmetry.
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
            # A mode-hold (possibly without a setpoint) is an active hold too,
            # so the Card shows the pill / "gilt bis …" / resume for it.
            "override_active": (
                self._override is not None or self._mode_override is not None
            ),
            "mode_override": self._mode_override,
            # Hold origin (ui_setpoint / device_adopt_*) + why this tick
            # did/did not adopt a device change (diagnostics; "" when nothing
            # seen).
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
            "mold_capped": mold_capped,  # mould floor clipped at 24 °C
            # ADR-0057: publish the mould-protection floor + dewpoint so the card
            # can draw the "Schimmel" tick on the dial (display only, no control).
            "mould_floor": round(mold_min, 1) if mold_min is not None else None,
            "dewpoint": round(dewpoint, 1) if dewpoint is not None else None,
            "source": reading_source.value,
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
        # Surface this zone's own boiler heat-demand (0..1) -- exactly the
        # value the hub aggregates from our data, so per-zone visibility can't
        # drift.
        _tick_data["heat_demand"] = zone_heat_demand(
            heating=heating,
            tpi_duty=_tick_data.get("tpi_duty"),
            frozen=frozen,
        )
        return _tick_data
