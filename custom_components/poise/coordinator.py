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
import sys
import time
from collections.abc import Callable, Sequence
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

from .clock import MonotonicClock
from .const import (
    CONF_CLIMATE_MODE,
    CONF_ENTRY_TYPE,
    DEFAULT_OVERRIDE_POLICY,
    DEVICE_MAX_C,
    DOMAIN,
    EKF_SAVE_EVERY_TICKS,
    ENTRY_TYPE_SYSTEM,
    FROST_FLOOR_C,
    TICK_INTERVAL_S,
)
from .control import override_runtime
from .control.mpc import MpcParams
from .control.override import (
    OverrideConfig,
    OverrideMode,
)
from .control.tick_budget import TickBudget
from .control.window_auto import (
    WindowAutoConfig,
)
from .diagnostics.collector import DiagnosticsCollector
from .ha.actuator_executor import ActuatorExecutor
from .ha.forecast_provider import ForecastProvider
from .ha.health_reporter import HealthReporter
from .ha.input_reader import InputReader
from .ha.tick_orchestrator import TickOrchestrator
from .persistence import codec as _codec
from .persistence.migrations import migrate_v0_bare_ekf
from .runtime.config import (
    HoldTuning,
    HotApplyConfig,
    MissingStructuralFieldError,
    ZoneConfig,
)
from .runtime.input_registry import build_input_registry, immediate_entities
from .runtime.tick_result import (
    CommitResult,
    ExecutionReport,
    OverrideEnded,
    PostExecutionAction,
)
from .runtime.zone_runtime import ZoneRuntime
from .storage import PoiseStore

# isort: off
# --- PATCH SURFACE (binding, do not "clean up") -------------------------------
# These names are imported here even though this module no longer calls them:
# the fault-injection tests patch ``custom_components.poise.coordinator.<name>``
# and ``ha.tick_orchestrator.TickOrchestrator`` resolves each one through THIS
# module at call time (``self._g.<name>``). Deleting an import, or importing the
# name in the orchestrator instead, turns the patch target into a dead name --
# the tests keep passing while testing nothing. Patched by tests today:
# is_frozen, ingest_temperature, effective_window_open, psychro_dewpoint,
# comfort_decide, resolve_write_target, humidity_decide, predict_peak_operative,
# plan_preheat. Documented as patch surface (not patched yet):
# resolve_desired_mode, mode_adopt_reason, setpoint_adopt_reason,
# shading_target_position, evaluate_thermal_shadow, _lifecycle.
from .comfort.dual_setpoint import decide as comfort_decide  # noqa: F401
from .comfort.humidity import humidity_decide  # noqa: F401
from .control.cover_shading import predict_peak_operative  # noqa: F401
from .control.cover_shading import shading_target_position  # noqa: F401
from .control.optimal_start import plan_preheat  # noqa: F401
from .control.override import mode_adopt_reason  # noqa: F401
from .control.override import setpoint_adopt_reason  # noqa: F401
from .control.tick_resolve import resolve_desired_mode  # noqa: F401
from .control.tick_resolve import resolve_write_target  # noqa: F401
from .control.window_auto import effective_window_open  # noqa: F401
from .estimation.psychrometrics import dewpoint as psychro_dewpoint  # noqa: F401
from .ingestion import ingest_temperature  # noqa: F401
from .multi import lifecycle as _lifecycle  # noqa: F401
from .multi.shadow import evaluate_thermal_shadow  # noqa: F401
from .safety.sensor_watchdog import is_frozen  # noqa: F401

# isort: on

_LOGGER = logging.getLogger(__name__)


def _utcnow_ts() -> float:
    """Wall-clock epoch for the override-lifecycle commands.

    Injected into ``control.override_runtime`` as ``now_utc_fn`` so the pure
    lifecycle functions read ``dt_util.utcnow()`` only on the paths that
    consult the clock (never, e.g., on a hold clear).
    """
    return float(dt_util.utcnow().timestamp())


def _local_minute_now() -> int:
    """Local minute-of-day (the ``dt_util.now()`` read of the switchpoint
    lookup and the §5 stat's schedule phase), evaluated at call time."""
    _lnow = dt_util.now()
    return int(_lnow.hour * 60 + _lnow.minute)


class _ReaderClock:
    """Live view of the coordinator's injectable clock.

    The ``InputReader`` is constructed once in ``__init__``, but integration
    tests swap ``coord.runtime.clock`` for a fake after setup — so the reader
    gets this forwarder instead of a snapshot of the reference, and the
    snapshot instants follow the live clock exactly like every direct clock
    read.
    """

    __slots__ = ("_coordinator",)

    def __init__(self, coordinator: PoiseCoordinator) -> None:
        self._coordinator = coordinator

    def monotonic(self) -> float:
        return self._coordinator.runtime.clock.monotonic()


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
        self._tick_budget = TickBudget()  # ADR-0020 per-tick compute-time budget
        self._temp: str = structure.temperature_sensor
        self._actuator: str = structure.actuator
        self._trm: str | None = structure.trm
        self._outdoor: str | None = structure.outdoor
        self._humidity: str | None = structure.humidity
        # ADR-0066 B.3: outdoor-RH ladder stage 1 (dedicated sensor).
        self._outdoor_humidity: str | None = structure.outdoor_humidity
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
        # State-change subscription over the registry's IMMEDIATE set. Held as
        # an unsub handle (not only via ``entry.async_on_unload``) because the
        # hot-applied presence lists can change the watched set at runtime —
        # see ``attach_listeners``/``_subscribe_inputs``.
        self._unsub_listeners: Callable[[], None] | None = None
        self._watched: tuple[str, ...] = ()
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
        # The repair-issue surface (``ha/health_reporter.py``): the
        # transition-only ``issue`` primitive, the ``emit`` checkpoint the tick
        # flow drives, the heating-failure notify and the setup-time ext-temp
        # validation. ``_active_issues`` stays a coordinator attribute (it is
        # REBOUND by async_bootstrap) and the reporter reads it through its
        # backreference. This module's ``_LOGGER`` is injected so the two debug
        # records keep the channel ``custom_components.poise.coordinator``.
        self._health = HealthReporter(
            self, hass=hass, logger=_LOGGER, input_reader=self._input_reader
        )
        # Every hot-applyable field flows through the ONE shared apply method,
        # so the init and options paths can never drift. The already parsed
        # pieces are bundled without a re-parse: __init__ keeps its
        # require-before-tuning throw order, while async_apply_options parses
        # HotApplyConfig directly (no structural reads).
        self._apply_hot_tuning(HotApplyConfig.from_zone_config(cfg, hold))
        # The whole per-tick program (8 tick methods + 26 stages) lives in
        # ``ha/tick_orchestrator.py``; this class keeps the HA coupling. Built
        # LAST so every collaborator handed over already exists. ``sys.modules
        # [__name__]`` hands the orchestrator THIS module object so it can
        # resolve the fault-injection patch surface at call time — see that
        # module's docstring for the binding rules. The two CHECKPOINTS are
        # deliberately NOT handed over as bound methods: the orchestrator
        # calls ``self._c._maybe_save()`` and ``self._c._health.emit(...)``,
        # i.e. it re-resolves both on THIS instance at call time, exactly as
        # the pre-move ``self._maybe_save()``/``self._emit_health_updates()``
        # did.
        self._tick = TickOrchestrator(
            self,
            coordinator_module=sys.modules[__name__],
            logger=_LOGGER,
            runtime=self._zone_runtime,
            input_reader=self._input_reader,
            actuator_executor=self._actuator_executor,
            diag_collector=self._diag_collector,
            trace_slug=entry.entry_id,
        )

    # Public read-only accessors onto the injected runtime containers. Tests
    # reach the migrated domain-state fields through these
    # (``coord.runtime.<group>.<field>``, ``coord.forecast_provider.<field>``,
    # ``coord.input_reader.<field>``). No setter is needed: the ZoneRuntime
    # groups are plain mutable dataclasses, so callers mutate the leaf field
    # and never rebind the container itself.

    @property
    def runtime(self) -> ZoneRuntime:
        return self._zone_runtime

    @property
    def forecast_provider(self) -> ForecastProvider:
        return self._forecast_provider

    @property
    def input_reader(self) -> InputReader:
        return self._input_reader

    @property
    def enabled(self) -> bool:
        return self._zone_runtime.user.enabled

    def set_enabled(self, value: bool) -> None:
        result = override_runtime.set_enabled(self._zone_runtime.user, value)
        if result.dirty:
            self._zone_runtime.dirty = True

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
            self._zone_runtime.dirty = True

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
            self._zone_runtime.dirty = True

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
        # ADR-0054 V2: met/clo room profile for the PMV shadow (hot-applied).
        self._room_profile = tuning.room_profile
        self._trace_enabled = tuning.trace_enabled
        # ADR-0066 B.5: opt-in ventilation-advice notification (hot-applied).
        self._vent_notify = tuning.vent_notify
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
        # F-PRESENCE made those lists part of the WATCHED set, so an options
        # submit that changes them must re-point the state-change listener too
        # — otherwise the new sensor would only be seen by the scheduled tick,
        # which is exactly the latency the fix removed. Guarded on a real
        # change so the common no-op apply does not churn the subscription;
        # ``__init__`` runs this before ``attach_listeners``, where
        # ``_watched`` is still empty and no subscription exists yet.
        if self._unsub_listeners is not None and self._watched_entities() != (
            self._watched
        ):
            self._detach_listeners()
            self._subscribe_inputs()
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
                presence_level=self._zone_runtime.presence.last_presence_level,
                window_open=self._zone_runtime.window.last_window_open,
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
            self._zone_runtime.dirty = True
        for event in result.events:
            self._fire_override_ended(event.reason)

    def set_climate_mode(self, mode: str) -> None:
        result = override_runtime.set_climate_mode(self._zone_runtime.user, mode)
        if result.dirty:
            self._zone_runtime.dirty = True

    def set_window_bypass(self, on: bool) -> None:
        result = override_runtime.set_window_bypass(self._zone_runtime.user, on)
        if result.dirty:
            self._zone_runtime.dirty = True

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
            self._zone_runtime.dirty = True

    @property
    def preset(self) -> OverrideMode:
        return self._zone_runtime.user.preset

    @property
    def window_bypass(self) -> bool:
        return self._zone_runtime.user.window_bypass

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
        return self._zone_runtime.user.climate_mode

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
                self._zone_runtime.learning.ekf = migrate_v0_bare_ekf(data)
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
        await self._health.validate_configured_ext_temp()

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

        Subscribes to every ``Reaction.IMMEDIATE`` entity of the input registry
        (``runtime/input_registry.py``, the single source of truth): the room
        sensor, the window sensors, the actuator and — since F-PRESENCE —
        presence/occupancy. Any real change requests a refresh (coalesced by
        the coordinator's own debounce). The tick still owns learning/safety;
        this only cuts *reaction* latency (an open window, someone entering the
        room) from up to a tick to near-instant.

        The presence lists are the one hot-applied part of the watched set, so
        ``_apply_hot_tuning`` re-subscribes when they change; the subscription
        is torn down on unload via ``entry.async_on_unload``.
        """
        entry.async_on_unload(self._detach_listeners)
        self._subscribe_inputs()

    def _watched_entities(self) -> tuple[str, ...]:
        """The registry's IMMEDIATE set, in registration order."""
        return immediate_entities(
            build_input_registry(
                temp=self._temp,
                windows=self._windows,
                actuator=self._actuator,
                presence_entities=self._presence_home_entities,
                occupancy_entities=self._occupancy_entities,
                outdoor=self._outdoor,
                humidity=self._humidity,
                trm=self._trm,
                mrt=self._mrt,
                irradiance=self._irradiance,
                weather=self._weather,
                trv_ext_temp=self._trv_ext_temp,
            )
        )

    def _subscribe_inputs(self) -> None:
        """(Re)subscribe the state-change listener to the current watched set."""
        from homeassistant.core import Event
        from homeassistant.helpers.event import async_track_state_change_event

        watched = self._watched_entities()
        self._watched = watched
        if not watched:
            self._unsub_listeners = None
            return

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

        self._unsub_listeners = async_track_state_change_event(
            self.hass, list(watched), _on_change
        )

    def _detach_listeners(self) -> None:
        """Drop the current subscription (unload, or before a re-subscribe)."""
        if self._unsub_listeners is not None:
            self._unsub_listeners()
            self._unsub_listeners = None

    async def _forecast_outdoor(self, horizon_min: float, fallback: float) -> float:
        """Mean forecast outdoor temp over the preheat window (ADR-0025).

        The body lives in ``ForecastProvider.mean_outdoor`` (fetch payload,
        TTL, backoff + last-good-cache fallback). Since F-FORECAST (phase 10)
        it only awaits real I/O on a COLD cache; a stale-but-present cache is
        served immediately and refreshed in the background. Kept as a method
        because integration tests drive it directly (test_forecast_backoff,
        test_glue_coverage4).
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
        replay).

        The body lives in ``TickOrchestrator._maybe_record_trace`` (gate,
        swallow boundary, lazy recorder, record build + append). It stays a
        coordinator method because ``finalize_tick`` dispatches it through the
        coordinator INSTANCE: test_phase8_presenter replaces
        ``coord._maybe_record_trace`` with a spy that wraps the original, and
        that replacement must be seen at the call site.
        """
        await self._tick._maybe_record_trace(
            data, room=room, t_out=t_out, rh=rh, t_rm=t_rm, now=now
        )

    def _notify_failure(self, failed: bool) -> None:
        """Surface a persistent heating failure as a translated repair issue.

        The body lives in ``HealthReporter.notify_failure``. It stays a
        coordinator method because ``_stage_failure_detect`` dispatches it
        through the coordinator INSTANCE and test_review_write_floor drives
        ``coord._notify_failure`` directly; it must stay SYNCHRONOUS (an
        in-stage checkpoint emission, never deferred to the stage end).
        """
        self._health.notify_failure(failed)

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
                ekf=self._zone_runtime.learning.ekf,
                trm_tracker=self._zone_runtime.learning.trm_tracker,
                seasonless=self._zone_runtime.learning.seasonless,
                window_auto=self._zone_runtime.window.window_auto,
                multi_lifecycle=self._zone_runtime.compressor.multi_lifecycle,
                ref_offset=self._zone_runtime.learning.ref_offset,
                tau_settle=self._zone_runtime.learning.tau_settle,
                outcome_stats=self._zone_runtime.diagnostics.outcome_stats,
                regq=self._zone_runtime.diagnostics.regq,
                hdh=self._zone_runtime.diagnostics.hdh,
                dry_active=self._zone_runtime.humidity.dry_active,
                vent_active=self._zone_runtime.humidity.vent_active,
                surface_rh_mean=self._zone_runtime.humidity.surface_rh_mean,
                enabled=self._zone_runtime.user.enabled,
                preset=self._zone_runtime.user.preset,
                climate_mode=self._zone_runtime.user.climate_mode,
                window_bypass=self._zone_runtime.user.window_bypass,
                has_actuated=self._zone_runtime.actuator.has_actuated,
                override=self._zone_runtime.user.override,
                mode_override=self._zone_runtime.user.mode_override,
                override_set_wall=self._zone_runtime.user.override_set_wall,
                override_requested=self._zone_runtime.user.override_requested,
                override_policy=self._override_policy,
                override_expires_at=self._zone_runtime.user.override_expires_at,
                override_expiry_is_switchpoint=self._zone_runtime.user.override_expiry_is_switchpoint,
                boost_expires_at=self._zone_runtime.user.boost_expires_at,
                boost_prev_preset=self._zone_runtime.user.boost_prev_preset,
                override_stats=self._zone_runtime.user.override_stats,
                override_reason=self._zone_runtime.user.override_reason,
                last_written_sp=self._zone_runtime.external.last_written_sp,
                prev_device_sp=self._zone_runtime.external.prev_device_sp,
                last_commanded_hvac=self._zone_runtime.external.last_commanded_hvac,
                prev_device_mode=self._zone_runtime.external.prev_device_mode,
            )
        )

    async def _maybe_save(self) -> None:
        self._save_counter += 1
        if self._save_counter >= EKF_SAVE_EVERY_TICKS or self._zone_runtime.dirty:
            self._save_counter = 0
            try:
                await self._store.save(self._save_payload())
                # Only clear the dirty flag on a SUCCESSFUL save. Clearing it
                # unconditionally would mark a fresh override/preset/enabled
                # change as "persisted" even when the write itself failed, so
                # a crash/restart in that window would silently lose the
                # user's intent until the next periodic (30-tick) save
                # happened to succeed.
                self._zone_runtime.dirty = False
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
        self._health.issue(
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
        # F-TRACEIO: the tick only enqueues trace lines, so the queue is
        # flushed here — after the lock, which guarantees no tick is still
        # producing. Best-effort; it can never fail the unload.
        await self._tick.flush_traces()
        # F-FORECAST: cancel an in-flight background refresh so no task
        # outlives the entry.
        await self._forecast_provider.async_close()
        keep: set[str] = set()
        if not saved:
            # Surface + retain the persistence issue; it is re-adopted on the
            # next setup and cleared once a save finally succeeds.
            pid = f"persistence_failed_{self._entry_id}"
            self._health.issue(pid, True, translation_key="persistence_failed")
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
                self._health.issue(
                    f"tick_failing_{self._entry_id}",
                    self._tick_failures >= 3,  # after 3 consecutive failures
                    translation_key="tick_failing",
                )
                raise
            self._tick_failures = 0
            self._health.issue(
                f"tick_failing_{self._entry_id}", False, translation_key="tick_failing"
            )
            # ADR-0020: the tick's wall-time against the budget — an early
            # scaling signal. Since F-TRACEIO/F-FORECAST (phase 10) this
            # measures the CONTROL path only: the trace append is drained off
            # the tick and the forecast refresh runs in the background, so a
            # slow disk or a slow weather integration no longer inflates the
            # number. A deliberate, documented change to this diagnostic.
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

        The body lives in ``TickOrchestrator._write_unavailable_safe_state``
        (resolve → executor sequence → commit). It stays a coordinator method
        because ``_run_unavailable_tick`` dispatches it through the coordinator
        INSTANCE: test_phase0_persistence_checkpoint replaces
        ``coord._write_unavailable_safe_state`` to record the checkpoint order,
        and that replacement must be seen at the call site.
        """
        await self._tick._write_unavailable_safe_state()

    async def _run_once(self) -> dict[str, Any]:
        """One tick under the lock — the whole flow lives in
        ``TickOrchestrator._run_once``.

        It stays a coordinator method because ``_async_update_data`` dispatches
        it through the coordinator INSTANCE (test_tick_failing_issue patches
        ``coord._run_once`` to force the consecutive-failure repair issue), and
        because the tick wall-time measurement in ``_async_update_data`` is
        defined as "around this call".
        """
        return await self._tick._run_once()

    def _set_mpc_params(self, params: MpcParams) -> None:
        """Setter hook for the observe stage's ADR-0052 retune.

        ``_mpc_params`` is config-shaped per-tick derived tuning and stays a
        real adapter attribute; the pure stage mutates it through this
        injected setter so the retune's swallow boundary keeps its exact
        extent.
        """
        self._mpc_params = params
