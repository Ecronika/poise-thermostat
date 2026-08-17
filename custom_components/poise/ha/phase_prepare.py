"""The await-free PREPARE phase of the tick (plan step O.5).

Ingest -> observe -> safety floors -> schedule gate -> schedule/presence ->
operative -> presence level -> comfort solve -> write target -> climate band
-> intents -> failure detect -> fan-first.  The sequencer
(``ha/tick_orchestrator.py``) calls these stages in two runs, one on each side
of the forecast seam; the seam itself is an orchestration hook, not a phase
boundary, which is why both sides live in ONE class (plan section 5).

WHY THIS MODULE EXISTS AS ITS OWN FILE.  The split follows the AWAIT TOPOLOGY,
because that is what carries the behaviour proofs.  Everything here is
await-free, and the structure gate keeps it that way: 0 ``await`` expressions
in this module, and no ``ActuatorExecutor`` -- a phase that must not write
cannot even reach the writer (capability narrowing, plan section 9).

Receiver rules (binding, unchanged from the monolith): the collaborators are
the injected attributes ``self._runtime`` / ``self._reader`` /
``self._forecast`` / ``self._hass``, every coordinator EFFECT goes through
``self._ports`` (a ``PreparePorts`` view -- five capabilities, nothing else),
and the logger is the injected ``self._log`` (the logger CHANNEL is behaviour:
records must keep the name ``custom_components.poise.coordinator``).  Per-tick
data travels as an ARGUMENT (``bindings``, ``config``) or inside the frozen
stage results -- never as a field on this class.

PATCH SURFACE (binding, plan O.4/O.5).  **Patch where the name is looked up,
not where it is defined.**  Eight of the nine fault-injection functions are
called from this module, each imported as its OWNING MODULE and called as an
attribute of it, so the lookup happens at CALL time and the patch target is the
owner (``…poise.safety.sensor_watchdog.is_frozen`` and so on):

* ``safety.sensor_watchdog.is_frozen``, ``ingestion.ingest_temperature``,
  ``control.window_auto.effective_window_open``,
  ``estimation.psychrometrics.dewpoint``, ``comfort.dual_setpoint.decide``,
  ``control.tick_resolve.resolve_write_target``,
  ``comfort.humidity.humidity_decide``, ``control.optimal_start.plan_preheat``.

Those eight targets did NOT move with this step -- they name the owner module,
not this one.  ``compose_climate_band`` is the one patch target that DID move
here (it is a plain from-import, so it is patched where it is bound:
``…poise.ha.phase_prepare.compose_climate_band``); ``tests/integration/
test_phase0_fault_climate_domain.py`` proves that patch still bites.

Error boundaries are narrow by design (ADR-0065) and each one stays inside the
method that owned it: two independent boundaries in ``_stage_climate_band``
(live humidity / shadow composition), one around the ventilation-advice
emission, one around the cool-raise activation and one around the fan-first
evaluation.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .. import ingestion
from ..comfort import dual_setpoint, humidity
from ..comfort.dual_setpoint import ComfortDecision
from ..comfort.en16798 import HEATING_LOWER, HEATING_UPPER
from ..comfort.humidity import HumidityDecision
from ..comfort.operative import operative_temperature
from ..comfort.presence import (
    PresenceLevel,
    any_present,
    resolve_presence,
    step_room_absence,
)
from ..comfort.readiness import presence_control_ready, room_present
from ..comfort.schedule import ScheduleState
from ..comfort.thermal_shock import adaptive_cool_setpoint, rate_limit
from ..comfort.ventilation import advice_transition
from ..const import (
    DEVICE_MAX_C,
    EVENT_VENT_ADVICE,
    FROST_FLOOR_C,
    WINDOW_MOULD_SUPPRESS_S,
)
from ..control import optimal_start, tick_resolve, window_auto
from ..control.dynamics import PROFILES
from ..control.external_override import note_device_fan, observe_fan_foreign
from ..control.fan_first import FanFirstDecision, FanFirstState, fan_first_decision
from ..control.optimal_start import latched_forecast_day
from ..control.override import OverrideMode, hold_ends_at_preheat, mode_comfort_base
from ..control.tick_resolve import idle_park
from ..diagnostics.shadows import compose_climate_band
from ..estimation import psychrometrics
from ..estimation.psychrometrics import humidity_ratio
from ..estimation.thermal_ekf import ThermalModel
from ..runtime.tick_inputs import TickInputs
from ..runtime.tick_result import (
    ClimateBandResult,
    ClimateHumidityResult,
    FanFirstStageResult,
    HealthUpdate,
    IngestResult,
    IntentsResult,
    ObservationResult,
    OperativeResult,
    PresenceLevelResult,
    SafetyFloorsResult,
    ScheduleGateResult,
    SchedulePresenceResult,
    TickStageError,
    WriteTargetResult,
)
from ..runtime.zone_runtime import ZoneRuntime
from ..safety import sensor_watchdog
from ..safety.heating_failure import actuator_cooling, actuator_running
from ..safety.sensor_watchdog import frozen_safe_target
from .input_reader import InputReader
from .tick_snapshot import TickConfigSnapshot, ZoneBindings

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    from .forecast_provider import ForecastProvider
    from .tick_ports import PreparePorts


# The published ``humidity_reason`` when the LIVE humidity segment failed
# (ADR-0065): the failure is named instead of the key silently vanishing.
_HUM_FAILED_REASON = "humidity block failed"

# ADR-0066 B.5: notification wording per reason token (English, concise —
# persistent notifications have no i18n rail; the stable token itself travels
# on the bus event for automations).
_VENT_REASON_TEXT = {
    "mold_risk": "sustained surface humidity, mould risk",
    "moisture_out": "outside air is drier, airing removes moisture",
    "co2": "CO₂ is elevated",
}


class PreparePhase:
    """The seventeen await-free prepare stages; one instance per coordinator.

    Built by the composition root (``coordinator.py``) and handed to the
    sequencer, which calls the stages in text order.  The four collaborators
    are injected ONCE so the stage bodies keep their expressions verbatim --
    that literalness is the equivalence proof of the O.5 move.

    ``forecast`` is here for its ``.forecast`` cache READ only; the forecast
    AWAIT belongs to the sequencer's seam and stays there.
    """

    __slots__ = ("_forecast", "_hass", "_log", "_ports", "_reader", "_runtime")

    def __init__(
        self,
        *,
        runtime: ZoneRuntime,
        reader: InputReader,
        forecast: ForecastProvider,
        hass: HomeAssistant,
        ports: PreparePorts,
        logger: logging.Logger,
    ) -> None:
        self._runtime = runtime
        self._reader = reader
        self._forecast = forecast
        self._hass = hass
        self._ports = ports
        self._log = logger

    def _stage_ingest(
        self, inputs: TickInputs, air: float, bindings: ZoneBindings
    ) -> IngestResult:
        """Health flags + temperature/environment ingest.

        Body in ``pipeline_prepare.stage_ingest`` via the runtime (incl. the
        device-health evaluation, whose InputReader DISCOVERY entity ids —
        static bootstrap results, no live read — are injected here).
        ``is_frozen`` (patch surface for test_phase0_safety_precedence) and
        ``ingest_temperature`` (test_phase6_health_checkpoints) are read off
        their OWNING module at call time, so patching
        ``safety.sensor_watchdog.is_frozen`` / ``ingestion.ingest_temperature``
        keeps hitting every call.
        """
        reader = self._reader
        return self._runtime.stage_ingest(
            inputs,
            air,
            entry_id=bindings.entry_id,
            temp_entity=bindings.temp,
            actuator_entity=bindings.actuator,
            sched_entity=reader.sched_entity,
            adaptive_mode_entity=reader.adaptive_mode_entity,
            fault_entity=reader.fault_entity,
            battery_entity=reader.battery_entity,
            is_frozen_fn=sensor_watchdog.is_frozen,
            ingest_temperature_fn=ingestion.ingest_temperature,
        )

    def _stage_observe(
        self,
        inputs: TickInputs,
        ing: IngestResult,
        bindings: ZoneBindings,
        config: TickConfigSnapshot,
    ) -> ObservationResult:
        """Window signals, capability, dynamics retune, EKF learn gate and
        window-auto observation.

        Body in ``pipeline_prepare.stage_observe`` via the runtime (learn,
        window-auto and seasonless observations). ``effective_window_open``
        (test_phase6_health_checkpoints) is read off ``control.window_auto`` at
        call time; the module ``_LOGGER`` is injected so both
        swallow-boundary records keep the channel
        ``custom_components.poise.coordinator``.
        """
        return self._runtime.stage_observe(
            inputs,
            ing,
            entry_id=bindings.entry_id,
            windows=bindings.windows,
            actuator_entity=bindings.actuator,
            window_auto_cfg=config.window_auto_cfg,
            adaptive_cool_cfg=config.adaptive_cool_cfg,
            dynamics_override=config.dynamics_override,
            effective_window_open_fn=window_auto.effective_window_open,
            set_mpc_params=self._ports.set_mpc_params,
            logger=self._log,
        )

    def _stage_safety_floors(
        self, ing: IngestResult, bindings: ZoneBindings
    ) -> SafetyFloorsResult:
        """Mould floor + dewpoint cap from humidity.

        Body in ``pipeline_prepare.stage_safety_floors`` via the runtime;
        ``dewpoint`` (test_phase6_health_checkpoints) is read off
        ``estimation.psychrometrics`` at call time.
        """
        return self._runtime.stage_safety_floors(
            ing,
            entry_id=bindings.entry_id,
            humidity_entity=bindings.humidity,
            psychro_dewpoint_fn=psychrometrics.dewpoint,
        )

    def _stage_schedule_gate(
        self,
        inputs: TickInputs,
        ing: IngestResult,
        obs: ObservationResult,
        config: TickConfigSnapshot,
    ) -> ScheduleGateResult:
        """Schedule state + predictive decision -- the forecast seam.

        Body in ``pipeline_prepare.stage_schedule_gate`` via the runtime (no
        patch surface; config schedule/optimal-start/-stop injected).
        """
        return self._runtime.stage_schedule_gate(
            inputs,
            ing,
            obs,
            schedule=config.schedule,
            optimal_start=config.optimal_start,
            optimal_stop=config.optimal_stop,
        )

    def _stage_schedule_presence(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sched: ScheduleState,
        config: TickConfigSnapshot,
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
        lo, hi = HEATING_LOWER[config.category], HEATING_UPPER[config.category]

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
        _presence = self._reader.read_presence()
        _home = any_present(_presence.home)
        # ADR-0059 §1/§2: expire the timed Boost + manual hold here, once the house
        # gate is known and before the preset/override feed the plan and solver. A
        # Boost restore must land before _is_away/_base_preset read the preset.
        self._ports.expire_timed_states(_home)
        _is_away = self._runtime.user.preset is OverrideMode.AWAY or _home is False
        _base_preset = OverrideMode.NONE if _is_away else self._runtime.user.preset
        _comfort_target = mode_comfort_base(
            _base_preset, config.comfort_base, config.override_cfg
        )
        plan = optimal_start.plan_preheat(
            comfort_base=_comfort_target,
            is_comfort=sched.is_comfort,
            setback_offset=sched.setback_offset,
            minutes_to_comfort=float(sched.minutes_to_comfort),
            optimal_start_enabled=config.optimal_start and not _is_away,
            can_heat=can_heat,
            identified=self._runtime.learning.ekf.identified,
            model=model,
            room=room,
            t_out_lead=t_out_lead,
            heat_lower=lo,
            heat_upper=hi,
            optimal_stop_enabled=config.optimal_stop,
            minutes_to_setback=float(sched.minutes_to_setback),
            coast_lower=lo,
            was_preheating=self._runtime.latches.was_preheating,
            was_coasting=self._runtime.latches.was_coasting,
            max_lead_h=PROFILES[self._runtime.compressor.dynamics].max_lead_h,
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
        if self._runtime.user.override is not None and hold_ends_at_preheat(
            policy=config.override_policy,
            preheat_started=preheating and not self._runtime.latches.was_preheating,
            expiry_is_switchpoint=self._runtime.user.override_expiry_is_switchpoint,
            preheat_target=_comfort_target,
            held_value=self._runtime.user.override,
        ):
            self._ports.end_hold("schedule_point")
        # ADR-0025/0034 latch: carry this tick's engage state to the next tick so
        # the planner can hold instead of re-chattering at the deadline boundary.
        self._runtime.latches.was_preheating = preheating
        self._runtime.latches.was_coasting = coasting
        return SchedulePresenceResult(
            home=_home,
            presence=_presence,
            base=base,
            preheating=preheating,
            preheat_outdoor=preheat_outdoor,
            coasting=coasting,
        )

    def _stage_operative_mode(
        self,
        inputs: TickInputs,
        ing: IngestResult,
        bindings: ZoneBindings,
        config: TickConfigSnapshot,
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
            ext_num = bindings.trv_ext_temp or (
                inputs.device_guards.ext_temp_number if config.operative_input else None
            )
            # Positioned read: the feed target's availability is probed here,
            # after the forecast await.
            ext_ok = self._reader.ext_feed_target_ok(ext_num)
            operative_active = config.operative_input and ext_ok
            pending.append(
                HealthUpdate(
                    issue_id=f"operative_unsupported_{bindings.entry_id}",
                    active=config.operative_input and not ext_ok,
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
        config: TickConfigSnapshot,
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
        self._runtime.presence.room_absent_since = step_room_absence(
            self._runtime.presence.room_absent_since,
            present=_room_present,
            now=_presence_now,
        )
        _absent_min = (
            (_presence_now - self._runtime.presence.room_absent_since) / 60.0
            if self._runtime.presence.room_absent_since is not None
            else 0.0
        )
        _level = resolve_presence(
            home=_home,
            room_absent_min=_absent_min,
            is_comfort=sched.is_comfort,
            preheating=preheating,
            cfg=config.presence_cfg,
        )
        # ADR-0059 §5: cache the presence level + window state so a user setpoint
        # nudge recorded in set_override (no tick context) can skip AWAY/window.
        self._runtime.presence.last_presence_level = _level.value
        # Track the rising edge of the open-window episode on the tick's
        # monotonic clock (``now``) so the mould floor can be suppressed for
        # its first WINDOW_MOULD_SUPPRESS_S below.
        if window_open:
            if self._runtime.window.window_open_since is None:
                self._runtime.window.window_open_since = now
        else:
            self._runtime.window.window_open_since = None
        self._runtime.window.last_window_open = window_open
        _eco_widen: float
        _cool_ceiling: float | None
        if _level is PresenceLevel.AWAY:
            _occupied = False
            _eco_widen = config.override_cfg.away_offset
            _cool_ceiling = DEVICE_MAX_C
        elif _level is PresenceLevel.ROOM_ECO:
            _occupied = False
            _eco_widen = config.presence_cfg.eco_delta
            _cool_ceiling = config.cool_hard_cap
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
        config: TickConfigSnapshot,
    ) -> ComfortDecision:
        """The central comfort solver (already pure).

        Body in ``pipeline_prepare.stage_comfort_solve`` via the runtime;
        ``comfort.dual_setpoint.decide`` (patch surface for
        test_phase0_health_emission and test_review_v161_fixes) is read off its
        owning module at call time — resolved per call, never bound at import,
        so patches keep hitting.
        """
        return self._runtime.stage_comfort_solve(
            ing,
            obs,
            floors,
            sp,
            op,
            lvl,
            category=config.category,
            cool_min_outdoor=config.cool_min_outdoor,
            cool_lockout_enabled=config.cool_lockout_enabled,
            heat_max_outdoor=config.heat_max_outdoor,
            heat_lockout_enabled=config.heat_lockout_enabled,
            priority=config.priority,
            cool_hard_cap=config.cool_hard_cap,
            comfort_decide_fn=dual_setpoint.decide,
        )

    def _stage_write_target(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        op: OperativeResult,
        decision: ComfortDecision,
        config: TickConfigSnapshot,
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
        act_state = self._reader.actuator_state()
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
                category=config.category,
                device_max=device_max,
                hard_cap=config.cool_hard_cap,
                delta_k=config.thermal_shock_delta,
            )
            eff_cool = rate_limit(
                self._runtime.latches.cool_sp_eff_prev, _cool_ac.cool_sp_eff, 0.5
            )
            self._runtime.latches.cool_sp_eff_prev = eff_cool
        except Exception:  # noqa: BLE001 - the cool raise must never break the tick
            self._log.debug("Poise cool-raise activation failed", exc_info=True)
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
                and self._runtime.window.window_open_since is not None
                and (now - self._runtime.window.window_open_since)
                < WINDOW_MOULD_SUPPRESS_S
            )
            else mold_min
        )
        # Fresh read — same await-free window as the central actuator read
        # above; hoisted into a local so the frozen floor below binds the
        # SAME value (one read, two uses, unobservable reorder).
        _device_min = self._reader.device_min()
        wt = tick_resolve.resolve_write_target(
            window_open=window_open,
            override=self._runtime.user.override,
            heat_sp=decision.heat_sp,
            cool_sp=eff_cool,
            write_setpoint=cool_write,
            comfort_mode=decision.mode,
            frost_floor=FROST_FLOOR_C,
            mold_min=mold_min_write,
            device_max=device_max,
            device_min=_device_min,
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
                _floor = frozen_safe_target(FROST_FLOOR_C, mold_min)
                # Clamp up to the device's announced min_temp, exactly like
                # the sustained-loss safe state (``resolve_safe_state``: "so
                # a high-min AC does not thrash on the echo it cannot
                # honour"). The bare floor would otherwise be re-written
                # every tick to a device that can never report it back —
                # permanent write traffic which the C.8 watchdog then reads
                # as the device ignoring us.
                target = _floor if _device_min is None else max(_floor, _device_min)
                mode = "heat"
            else:
                mode = "off"
            self._runtime.actuator.last_target = target
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
        bindings: ZoneBindings,
        config: TickConfigSnapshot,
    ) -> ClimateBandResult:
        """Comfort stage, climate band — TWO independent boundaries
        (ADR-0065).

        ADR-0050/0051: a mostly-diagnostic block, but NOT "no writes" — the
        humidity action it computes drives the LIVE dry mode-nudge
        (mode_arbitration). Each half owns its boundary: a failing humidity
        decision costs the dry nudge and marks its own three keys, while the
        shadow fields keep being published; a failing shadow composition
        leaves the live nudge untouched. Warn-once per boundary is preserved.
        """
        live = self._climate_humidity(ing, lvl, op, decision, wt, bindings, config)
        climate_diag = self._climate_shadows(
            ing, obs, sp, lvl, op, decision, wt, live, bindings, config
        )
        self._announce_vent_advice(climate_diag, bindings, config)
        return ClimateBandResult(
            climate_diag=climate_diag,
            hum_action=live.decision.action,
        )

    def _announce_vent_advice(
        self,
        diag: Mapping[str, Any],
        bindings: ZoneBindings,
        config: TickConfigSnapshot,
    ) -> None:
        """ADR-0066 B.5 emission rail: bus event on every advice-ACTION change
        plus the opt-in self-clearing notification for "open" episodes.

        The decision is pure (``advice_transition``); this method only tracks
        the previous token and DELIVERS. Its own boundary: a delivery failure
        must never break the tick and never poisons the shadow boundary above.
        """
        action = str(diag.get("vent_action") or "")
        if not action:
            return  # composition failed or produced no advice — nothing moved
        prev = self._runtime.humidity.vent_last_action
        self._runtime.humidity.vent_last_action = action
        try:
            em = advice_transition(prev, action, notify_opt_in=config.vent_notify)
            if not em.fire_event:
                return
            payload: dict[str, Any] = {
                "zone": bindings.zone_name,
                "entry_id": bindings.entry_id,
                "action": action,
                "reason": str(diag.get("vent_reason") or ""),
                "delta_gm3": diag.get("vent_delta_gm3"),
            }
            self._hass.bus.async_fire(EVENT_VENT_ADVICE, payload)
            notification_id = f"poise_vent_{bindings.entry_id}"
            if em.notify_create:
                reason_txt = _VENT_REASON_TEXT.get(payload["reason"], payload["reason"])
                delta = payload["delta_gm3"]
                delta_txt = (
                    f" (inside {delta:+.1f} g/m³ vs outside)"
                    if isinstance(delta, int | float)
                    else ""
                )
                persistent_notification.async_create(
                    self._hass,
                    f"Airing recommended — {reason_txt}{delta_txt}.",
                    title=f"Poise · {bindings.zone_name}",
                    notification_id=notification_id,
                )
            elif em.notify_dismiss:
                persistent_notification.async_dismiss(self._hass, notification_id)
        except Exception:  # noqa: BLE001 - announcement must never break the tick
            self._log.debug("Poise ventilation-advice emission failed", exc_info=True)

    def _outdoor_rh(self, bindings: ZoneBindings) -> float | None:
        """Outdoor-humidity ladder (ADR-0066 B.3). Stage 1: the dedicated
        outdoor-RH sensor when configured; stage 2: the ``humidity`` attribute
        of the ALREADY-configured weather entity — zero extra hardware or
        config. Without any source the advice degrades silently to ``no_data``
        (design §9). Both reads routed through the InputReader (phase-4 read
        boundary) — the only module allowed to touch hass.states."""
        dedicated = self._reader.read(bindings.outdoor_humidity)
        if dedicated is not None:
            return dedicated
        return self._reader.attr_number(bindings.weather, "humidity")

    def _climate_humidity(
        self,
        ing: IngestResult,
        lvl: PresenceLevelResult,
        op: OperativeResult,
        decision: ComfortDecision,
        wt: WriteTargetResult,
        bindings: ZoneBindings,
        config: TickConfigSnapshot,
    ) -> ClimateHumidityResult:
        """The LIVE humidity/dry decision (ADR-0050 S2c) behind its own narrow
        boundary — the only non-diagnostic part of the climate band:
        ``action`` drives the dry mode-nudge and ``dry_active`` is the next
        tick's hysteresis latch.

        On failure the nudge falls back to "idle" and the latch keeps its
        previous value; the shadow composition still runs against the neutral
        decision returned here (ADR-0065), so the three humidity keys stay
        published and say what happened instead of vanishing with the rest of
        the band.
        """
        act_state = wt.act_state
        # Seeded, then overwritten inside the boundary: the shadow segment
        # consumes both, so partial progress before a failure point must
        # survive (a raising ``humidity_decide`` still leaves them computed).
        modes: list[str] = []
        abs_gkg: float | None = None
        try:
            modes = (
                [str(m) for m in (act_state.attributes.get("hvac_modes") or [])]
                if act_state
                else []
            )
            # ADR-0050/0051 coherence: compose humidity + diagnostics against the
            # SAME config-based, rate-limited cool band that is actually written
            # (_cool_ac / eff_cool), not a second default-config computation.
            abs_gkg = (
                humidity_ratio(ing.room, ing.rh)
                if ing.rh is not None and ing.room is not None
                else None
            )
            hum = humidity.humidity_decide(
                rh=ing.rh,
                too_warm=op.room_decide > wt.eff_cool,
                in_deadband=decision.heat_sp <= op.room_decide <= wt.eff_cool,
                can_dry="dry" in modes,
                can_fan_only="fan_only" in modes,
                prev_dry_active=self._runtime.humidity.dry_active,
                category=config.category,
                abs_humidity_gkg=abs_gkg,
                occupied=lvl.occupied,
            )
            self._runtime.humidity.dry_active = hum.dry_active
        except Exception:  # noqa: BLE001 - must never break the tick
            # Not purely shadow — on failure the LIVE dry mode-nudge silently
            # falls back to "idle". Surface it at WARNING once, then DEBUG after.
            if not self._runtime.diagnostics.hum_shadow_warned:
                self._runtime.diagnostics.hum_shadow_warned = True
                self._log.warning(
                    "Poise %s: climate-band/humidity block failed; the live dry "
                    "mode-nudge falls back to idle this tick (further at DEBUG)",
                    bindings.zone_name,
                    exc_info=True,
                )
            else:
                self._log.debug("Poise climate-band shadow failed", exc_info=True)
            # The latch is deliberately carried over, not reset: a failed
            # decision is no evidence that dehumidification ended.
            hum = HumidityDecision(
                "idle", self._runtime.humidity.dry_active, _HUM_FAILED_REASON
            )
        return ClimateHumidityResult(
            decision=hum, hvac_modes=modes, abs_humidity_gkg=abs_gkg
        )

    def _climate_shadows(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sp: SchedulePresenceResult,
        lvl: PresenceLevelResult,
        op: OperativeResult,
        decision: ComfortDecision,
        wt: WriteTargetResult,
        live: ClimateHumidityResult,
        bindings: ZoneBindings,
        config: TickConfigSnapshot,
    ) -> dict[str, object]:
        """The pure free-running/fan/PMV shadows + the ``climate_diag``
        assembly behind their own boundary (F-HUMSHADOW).

        Composition lives in ``diagnostics/shadows.py``; the actuator-attribute
        reads are hoisted into the (side-effect-free) argument construction of
        this guarded position. Nothing here writes runtime state, so a failure
        costs exactly the published diagnostic keys — never the dry nudge.
        """
        act_state = wt.act_state
        try:
            # ADR-0054 Nachtrag V1: today's forecast daily mean for the clo
            # blend, latched once per local day from the optimal-start cache
            # (empty cache -> None -> pure running-mean clo).
            diag_rt = self._runtime.diagnostics
            diag_rt.clo_forecast_key, diag_rt.clo_forecast_day = latched_forecast_day(
                diag_rt.clo_forecast_key,
                diag_rt.clo_forecast_day,
                dt_util.now().date().isoformat(),
                self._forecast.forecast,
            )
            band = compose_climate_band(
                heat_sp=decision.heat_sp,
                cool_sp=decision.cool_sp,
                room=ing.room,
                room_decide=op.room_decide,
                t_rm_eff=ing.t_rm_eff,
                t_mrt=ing.t_mrt,
                rh=ing.rh,
                eff_cool=wt.eff_cool,
                mode=wt.mode,
                window_open=obs.window_open,
                occupied=lvl.occupied,
                presence_level=lvl.level.value,
                absent_min=lvl.absent_min,
                home_present=sp.home,
                category=config.category,
                cool_hard_cap=config.cool_hard_cap,
                cool_ac=wt.cool_ac,
                hum=live.decision,
                abs_humidity_gkg=live.abs_humidity_gkg,
                hvac_modes=live.hvac_modes,
                has_fan_modes=bool(act_state and act_state.attributes.get("fan_modes")),
                fan_mode=act_state.attributes.get("fan_mode") if act_state else None,
                hvac_action=(
                    act_state.attributes.get("hvac_action") if act_state else None
                ),
                # ADR-0066 humidity axis (advice/monitor only). One tick minute
                # per call feeds the surface-RH EWMA — against tau = 48 h the
                # event-refresh error is negligible (Poise tick = 60 s,
                # ADR-0020); a real elapsed anchor is the cost increment's job.
                t_out_eff=ing.t_out_eff,
                rh_out=self._outdoor_rh(bindings),
                surface_rh_mean_prev=self._runtime.humidity.surface_rh_mean,
                surface_elapsed_min=1.0,
                co2=None,  # ADR-0049 §1 backend not built yet -> rule 4 inert
                prev_vent_active=self._runtime.humidity.vent_active,
                prev_vent_reason=self._runtime.humidity.vent_reason,
                t_forecast_day=diag_rt.clo_forecast_day,
                room_profile=config.room_profile,
                clo_offset=config.clo_offset,
            )
            # Fold the advice latch + persisted surface mean back (ADR-0066).
            self._runtime.humidity.vent_active = bool(
                band.get("vent_advice_active", False)
            )
            # Rule 3t dT hysteresis anchor (transient, restart -> dt_on again).
            self._runtime.humidity.vent_reason = str(band.get("vent_reason") or "")
            mean = band.get("surface_rh_mean")
            if isinstance(mean, int | float):
                self._runtime.humidity.surface_rh_mean = float(mean)
            return band
        except Exception:  # noqa: BLE001 - must never break the tick
            if not self._runtime.diagnostics.climate_shadow_warned:
                self._runtime.diagnostics.climate_shadow_warned = True
                self._log.warning(
                    "Poise %s: climate-band shadow composition failed; the live "
                    "dry decision stands, the band diagnostics degrade this tick "
                    "(further at DEBUG)",
                    bindings.zone_name,
                    exc_info=True,
                )
            else:
                self._log.debug("Poise climate-band shadow failed", exc_info=True)
            return {}

    def _stage_intents(
        self, ing: IngestResult, obs: ObservationResult, wt: WriteTargetResult
    ) -> IntentsResult:
        """Heat/cool intent + EKF drive latches (ADR-0024).

        Body in ``pipeline_prepare.stage_intents`` via the runtime (no patch
        surface, no config parameter)."""
        return self._runtime.stage_intents(ing, obs, wt)

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
            self._runtime.safety.failure.update(
                now_h=now / 3600.0,
                room=room,
                setpoint=target,
                running=running,
            )
            or fault_active
        )
        self._ports.notify_failure(failed)
        # Latch for the NEXT tick's learn gate (this tick's gate already ran).
        self._runtime.safety.prev_heating_failed = failed
        # C.8 cooling pendant: same stage, own detector/issue/latch. Pure
        # detector verdict only — ``fault_active`` stays a heating-side OR
        # (the generic device alarm historically rides there).
        cooling_running = actuator_cooling(
            act_state.attributes.get("hvac_action") if act_state else None,
            fallback=intents.cooling,
        )
        cool_failed = self._runtime.safety.cooling_failure.update(
            now_h=now / 3600.0,
            room=room,
            setpoint=target,
            running=cooling_running,
        )
        self._ports.notify_cooling_failure(cool_failed)
        self._runtime.safety.prev_cooling_failed = cool_failed
        return failed

    def _stage_fan_first(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        sched: ScheduleState,
        sp: SchedulePresenceResult,
        op: OperativeResult,
        wt: WriteTargetResult,
        config: TickConfigSnapshot,
    ) -> FanFirstStageResult:
        """ADR-0068 U6 fan-first FSM — computed BEFORE the mode resolution so
        its candidate can intercept a NORMAL cool at the seam (the seam stays
        the single mode authority). Await-free.

        Defensive: comfort glue must never break the tick. The ``try``
        boundary guards EXACTLY the statements it guarded inline and its debug
        log keeps channel, level and text; the pre-set defaults and the result
        construction stay outside, so a failure hands on the same partial
        values the inline block left behind.
        """
        _ff = FanFirstDecision(state=FanFirstState(), command="none", reason="disabled")
        _ff_requested = False
        _act_ff = wt.act_state
        _fan_modes_ff: tuple[str, ...] = ()
        _device_fan_ff: str | None = None
        _foreign_fan_ff = False
        _presence_ok_ff = False
        try:
            _fan_modes_ff = (
                tuple(_act_ff.attributes.get("fan_modes") or ())
                if _act_ff is not None
                else ()
            )
            _device_fan_ff = (
                _act_ff.attributes.get("fan_mode") if _act_ff is not None else None
            )
            _own_fan_ff = (
                _act_ff is not None
                and _act_ff.context is not None
                and _act_ff.context.id in self._runtime.external.own_write_ctx_ids
            )
            _foreign_fan_ff = observe_fan_foreign(
                self._runtime.external,
                device_fan=_device_fan_ff,
                own_change=_own_fan_ff,
                now=ing.now,
            )
            note_device_fan(
                self._runtime.external, device_fan=_device_fan_ff, now=ing.now
            )
            _occ_ff = sp.presence.occupancy
            _presence_ok_ff = presence_control_ready(_occ_ff) and room_present(_occ_ff)
            if config.active_comfort:
                _ff = fan_first_decision(
                    self._runtime.latches.fan_first,
                    now=ing.now,
                    cool_requested=wt.mode == "cool",
                    fan_first_allowed=(
                        not obs.window_open
                        and not ing.frozen
                        and self._runtime.user.override is None
                        and self._runtime.user.mode_override is None
                    ),
                    fan_only_capable=(
                        "fan_only"
                        in (
                            (_act_ff.attributes.get("hvac_modes") or [])
                            if _act_ff is not None
                            else []
                        )
                    ),
                    observed_hvac_mode=_act_ff.state if _act_ff is not None else None,
                    observed_hvac_action=(
                        _act_ff.attributes.get("hvac_action")
                        if _act_ff is not None
                        else None
                    ),
                    observed_fan_mode=_device_fan_ff,
                    advertised_modes=_fan_modes_ff,
                    operative_c=op.room_decide,
                    room_c=ing.room,
                    presence_ok=_presence_ok_ff,
                    window_open=obs.window_open,
                    in_comfort_window=sched.is_comfort,
                    foreign_fan_change=_foreign_fan_ff,
                )
            self._runtime.latches.fan_first = _ff.state
            self._runtime.diagnostics.fan_first_reason = _ff.reason
            _ff_requested = _ff.command == "fan_only" or _ff.state.phase in (
                "await_fan_only",
                "await_stage",
                "dwell",
            )
        except Exception:  # noqa: BLE001 - fan glue must never break the tick
            self._log.debug("Poise fan-first evaluation failed", exc_info=True)
        return FanFirstStageResult(
            decision=_ff,
            requested=_ff_requested,
            fan_modes=_fan_modes_ff,
            device_fan=_device_fan_ff,
            foreign_fan=_foreign_fan_ff,
            presence_ok=_presence_ok_ff,
        )
