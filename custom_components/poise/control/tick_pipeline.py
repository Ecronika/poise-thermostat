"""Pure per-tick stage implementations.

``ZoneRuntime`` owns the domain state and all PURE prepare stages; this module
holds those stage *implementations* as plain functions over (state groups,
inputs, prior stage results).  The ``ZoneRuntime`` methods delegate here 1:1
and the coordinator's ``_stage_*`` methods are thin delegations onto the
runtime.  Substitution rules:

* domain-state reads/writes go to the ``ZoneRuntime`` group fields
  (``rt.user.override``, ``rt.learning.ekf``, ...); the ``dirty`` persistence
  flag lives directly on the runtime (``rt.dirty``).
* config-owned values (``ZoneTuning``/structure attributes, which stay on the
  coordinator) arrive as explicit keyword parameters.
* PATCH SURFACES: integration tests patch symbols on the COORDINATOR module
  (``custom_components.poise.coordinator.comfort_decide`` / ``is_frozen`` /
  ``ingest_temperature`` / ``effective_window_open`` / ``psychro_dewpoint``).
  Those callables are therefore INJECTED per call (``*_fn`` parameters): the
  coordinator's delegation resolves the name from its module globals at call
  time, so ``unittest.mock.patch`` on the coordinator module keeps hitting
  every dispatch.  They must never be bound early (module import or
  constructor) here.
* LOG CHANNELS are behaviour: the two swallow boundaries that log do so via an
  injected ``logging.Logger`` — the coordinator passes its own ``_LOGGER`` so
  every record keeps the baseline channel
  ``custom_components.poise.coordinator`` with identical text/level.

This module is hass-free (mypy --strict, py310-clean): the one HA type that
flows through (``State``, the tick's central positioned actuator read carried
by ``WriteTargetResult.act_state``) is imported under ``TYPE_CHECKING`` only.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..adaptive_cool import resolve_adaptive_cool
from ..comfort.mode_seam import mode_arbitration
from ..comfort.mold import mold_min_air_temperature_detail
from ..comfort.virtual_mrt import virtual_mrt
from ..const import (
    COMPRESSOR_GUARD_OFF,
    DEVICE_MAX_C,
    FROST_FLOOR_C,
    LOW_BATTERY_PCT,
    MIN_PLAUSIBLE_TAU_H,
    SENSOR_FREEZE_AFTER_S,
    SETPOINT_ADOPT_ECHO_WINDOW_S,
    WRITE_DEADBAND_C,
)
from ..contracts import Source
from ..control.cooling import cooling_intent, override_mode
from ..control.dynamics import PROFILES, classify_dynamics, regulation_throttled
from ..control.external_override import ExternalOverrideTracker
from ..control.mpc import MpcParams
from ..control.tick_resolve import (
    cool_drive_signal,
    heat_drive_signal,
    select_mrt,
    select_q_solar,
    select_t_rm,
    should_write,
    snap_to_step,
)
from ..control.window_auto import (
    WindowAutoState,
    adaptive_open_threshold,
    quantized_slope,
    step_window_auto,
)
from ..devices.capability import climate_capability
from ..devices.model_fixes import is_low_battery
from ..estimation.heatup_rate import sample_heatup_rate
from ..ingestion import RawSample
from ..multi.lifecycle import resolve_guard_policy
from ..runtime.tick_result import (
    ActuatorPlan,
    FinalizeContext,
    ForecastRequest,
    HealthUpdate,
    IngestResult,
    IntentsResult,
    ModeResolutionResult,
    ObservationResult,
    SafetyFloorsResult,
    ScheduleGateResult,
    SetpointObservation,
    TickStageError,
)
from ..safety.sensor_watchdog import sensor_at_heat_source, should_learn

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    from ..comfort.dual_setpoint import ComfortDecision
    from ..comfort.en16798 import Category
    from ..comfort.schedule import ComfortSchedule
    from ..control.dynamics import DeviceDynamics
    from ..control.window_auto import WindowAutoConfig
    from ..runtime.tick_inputs import TickInputs
    from ..runtime.tick_result import (
        ClimateBandResult,
        HoldRoutingResult,
        ModeAdoptionResult,
        ModeNudgeResult,
        OperativeResult,
        PreparedState,
        PresenceLevelResult,
        SchedulePresenceResult,
        WriteTargetResult,
    )
    from ..runtime.zone_runtime import ZoneRuntime

# Conservative outdoor default when neither a sensor nor the running mean is
# known — mirrors control.mpc_controller._FALLBACK_T_OUT_C (a cold-ish day
# keeps heating engaged rather than mild-locking it out).
_FALLBACK_OUTDOOR_C = 5.0


# ---------------------------------------------------------------------------
# Ingest & observations
# ---------------------------------------------------------------------------


def evaluate_health_issues(
    rt: ZoneRuntime,
    inputs: TickInputs,
    pending: list[HealthUpdate],
    *,
    entry_id: str,
    temp_entity: str,
    actuator_entity: str,
    sched_entity: str | None,
    adaptive_mode_entity: str | None,
    fault_entity: str | None,
    battery_entity: str | None,
    is_frozen_fn: Callable[[float | None, float], bool],
) -> tuple[bool, bool, bool, bool]:
    """Evaluate the device-health issues; return the status flags.

    The InputReader's DISCOVERY results (``sched_entity`` etc., static entity
    ids resolved at bootstrap, no live read) are injected as parameters, and
    ``is_frozen`` dispatches through the coordinator module global (patch
    surface, test_phase0_safety_precedence).  The evaluation appends
    ``HealthUpdate``s to the caller's ``pending`` list AS it evaluates — a
    fixed per-issue order, with conditional gates (an undiscovered guard
    entity produces NO update at all, not a clear) — and the ingest stage
    returns them for the stage-end checkpoint.  Appending into the caller's
    list keeps the mid-evaluation abort semantics: an exception after N
    appends leaves exactly the N updates already emitted, and the stage's
    ``TickStageError`` transport carries them out.  The returned flags stay
    live rule inputs of the pipeline.
    """
    # An actuator that dropped off the network (Zigbee/MQTT gone) keeps a
    # registered State object with state == "unavailable"; the snapshot's
    # ``state`` is None only for a never-registered/removed entity.  Both count
    # as unavailable so the offline device fires the repair issue.
    pending.append(
        HealthUpdate(
            issue_id=f"actuator_unavailable_{entry_id}",
            active=(
                inputs.actuator.state is None or inputs.actuator.state == "unavailable"
            ),
            translation_key="actuator_unavailable",
            placeholders={"entity": actuator_entity},
        )
    )
    frozen = is_frozen_fn(inputs.room.age_s, SENSOR_FREEZE_AFTER_S)
    pending.append(
        HealthUpdate(
            issue_id=f"sensor_frozen_{entry_id}",
            active=frozen,
            translation_key="sensor_frozen",
            placeholders={"entity": temp_entity},
        )
    )
    guards = inputs.device_guards
    sched_active = fault_active = False
    if sched_entity:
        sched_active = guards.sched_active
        pending.append(
            HealthUpdate(
                issue_id=f"device_schedule_{entry_id}",
                active=sched_active,
                translation_key="device_schedule",
                placeholders={"entity": sched_entity},
            )
        )
    if adaptive_mode_entity:
        # A switch reads "on"; a select reads the active option name.  Treat
        # any adaptive/smart-named option (or a plain "on") as the loop being
        # active -- an off/manual state clears the issue.
        active = guards.adaptive_mode is not None and (
            guards.adaptive_mode == "on"
            or "adaptive" in guards.adaptive_mode.lower()
            or "smart" in guards.adaptive_mode.lower()
        )
        pending.append(
            HealthUpdate(
                issue_id=f"adaptive_mode_{entry_id}",
                active=active,
                translation_key="adaptive_mode_active",
                placeholders={"entity": adaptive_mode_entity},
            )
        )
    if fault_entity:
        fault_active = guards.fault_active
        pending.append(
            HealthUpdate(
                issue_id=f"device_alarm_{entry_id}",
                active=fault_active,
                translation_key="device_alarm",
                placeholders={"entity": fault_entity},
            )
        )
    if battery_entity:
        pending.append(
            HealthUpdate(
                issue_id=f"low_battery_{entry_id}",
                active=is_low_battery(guards.battery, LOW_BATTERY_PCT),
                translation_key="low_battery",
                placeholders={"entity": battery_entity},
            )
        )
    heat_source_suspect = sensor_at_heat_source(
        rt.learning.ekf.tau_hours,
        rt.learning.ekf.identified,
        min_plausible_tau_h=MIN_PLAUSIBLE_TAU_H,
    )
    pending.append(
        HealthUpdate(
            issue_id=f"sensor_at_heat_source_{entry_id}",
            active=heat_source_suspect,
            translation_key="sensor_at_heat_source",
            placeholders={"entity": temp_entity},
        )
    )
    return frozen, sched_active, fault_active, heat_source_suspect


def stage_ingest(
    rt: ZoneRuntime,
    inputs: TickInputs,
    air: float,
    *,
    entry_id: str,
    temp_entity: str,
    actuator_entity: str,
    sched_entity: str | None,
    adaptive_mode_entity: str | None,
    fault_entity: str | None,
    battery_entity: str | None,
    is_frozen_fn: Callable[[float | None, float], bool],
    ingest_temperature_fn: Callable[..., Any],
) -> IngestResult:
    """Health flags + temperature/environment ingest.

    The health evaluation appends its updates to ``pending`` in emission
    order; the stage returns them for the stage-end checkpoint.  The
    ``TickStageError`` wrap transports already-collected updates out of a
    mid-body abort — with nothing pending the abort propagates bare.
    ``ingest_temperature`` dispatches through the injected coordinator module
    global (test_phase6_health_checkpoints patch surface).
    """
    pending: list[HealthUpdate] = []
    try:
        frozen, sched_active, fault_active, heat_source_suspect = (
            evaluate_health_issues(
                rt,
                inputs,
                pending,
                entry_id=entry_id,
                temp_entity=temp_entity,
                actuator_entity=actuator_entity,
                sched_entity=sched_entity,
                adaptive_mode_entity=adaptive_mode_entity,
                fault_entity=fault_entity,
                battery_entity=battery_entity,
                is_frozen_fn=is_frozen_fn,
            )
        )
        now = inputs.now_mono
        # Feed the last known-good room value so an implausible raw sample
        # (Zigbee glitch, a misread °F number, ...) degrades to that recent
        # real reading ("derived") instead of skipping straight to the
        # hardcoded 20.0 °C default (ADR-0012 degradation ladder).
        reading = ingest_temperature_fn(
            [RawSample(air, now)], now=now, last_good=rt.learning.prev_room
        )
        room = reading.value
        # A DEFAULT-source reading means there is no trustworthy room value AT
        # ALL (an implausible raw sample AND no prior good reading to derive
        # from) -- treat it exactly like a frozen/stale sensor (fail toward
        # warmth): control degrades to the health floor and learning pauses,
        # instead of regulating on -- and teaching the EKF -- a fabricated
        # constant (measured/estimated boundary, ADR-0012/0026).
        frozen = frozen or reading.source is Source.DEFAULT
        t_out = inputs.outdoor.value
        # internal EN 16798-1 running mean, used when no external T_rm.
        if t_out is not None:
            rt.learning.trm_tracker.observe(t_out, inputs.local_day_ordinal)
        t_rm, t_rm_source = select_t_rm(
            inputs.trm.value, rt.learning.trm_tracker.current, t_out
        )
        t_out_eff = (
            t_out
            if t_out is not None
            else (t_rm if t_rm is not None else _FALLBACK_OUTDOOR_C)
        )
        t_rm_eff = t_rm if t_rm is not None else t_out_eff
        rh = inputs.humidity.value
        # solar disturbance q_solar (normalised, ADR-0010): internal
        # clear-sky estimate always runs; a measured irradiance sensor
        # overrides the value used (shadow-estimator principle, ADR-0026).
        q_solar, q_solar_source, q_solar_internal = select_q_solar(
            inputs.sun_elevation, inputs.irradiance.value
        )
        # virtual MRT (shadow, ADR-0017/0026): exterior envelope pulls MRT
        # toward outdoor + a solar radiant bump; a measured globe/MRT
        # sensor overrides.
        mrt_internal = virtual_mrt(room, t_out_eff, q_solar)
        t_mrt, mrt_source = select_mrt(inputs.mrt.value, mrt_internal)
        return IngestResult(
            now=now,
            frozen=frozen,
            sched_active=sched_active,
            fault_active=fault_active,
            heat_source_suspect=heat_source_suspect,
            reading=reading,
            room=room,
            rh=rh,
            t_out_eff=t_out_eff,
            t_rm_eff=t_rm_eff,
            t_rm_source=t_rm_source,
            q_solar=q_solar,
            q_solar_source=q_solar_source,
            q_solar_internal=q_solar_internal,
            t_mrt=t_mrt,
            mrt_source=mrt_source,
            mrt_internal=mrt_internal,
            health_updates=tuple(pending),
        )
    except BaseException as err:  # transport-only; unwrapped in _run_once
        if pending:
            raise TickStageError(err, tuple(pending)) from err
        raise


def learn_step(
    rt: ZoneRuntime,
    room: float,
    t_out: float,
    *,
    now: float,
    logger: logging.Logger,
) -> None:
    """Passive EKF observer; paused on open window (ADR-0002/0024).

    ``now`` is the tick's snapshot monotonic instant.  The swallow boundary
    logs via the INJECTED coordinator logger so the record keeps the baseline
    channel.
    """
    try:
        if rt.learning.last_mono is not None:
            dt_h = (now - rt.learning.last_mono) / 3600.0
            if 0.0 < dt_h < 1.0:
                rt.learning.ekf.predict(
                    dt_h,
                    t_out=t_out,
                    u_h=rt.learning.last_u_h,
                    u_c=rt.learning.last_u_c,
                    q_solar=rt.learning.last_q_solar,
                )
                rt.learning.ekf.update(room)
    except Exception:  # noqa: BLE001 - learning must never break control
        logger.exception("Poise: EKF observer step failed")
    finally:
        rt.learning.last_mono = now


def observe_window_auto(
    rt: ZoneRuntime,
    room: float,
    t_out: float,
    *,
    now: float,
    cooling: bool = False,
    sensor_unavailable: bool = False,
    windows: list[str],
    window_auto_cfg: WindowAutoConfig,
) -> None:
    """Feed the sensorless slope detector (ADR-0041).

    Skipped only while a configured window sensor is actually reporting
    (ADR-0041 §2 exclusivity: a healthy sensor beats the heuristic).  A
    configured-but-*unavailable* sensor is the one exception -- §5's failsafe
    (heat as if no sensor) requires the slope detector to be live to fall back
    to, so it keeps stepping whenever the sensor itself cannot currently
    report.  The healthy-sensor case is a bare skip here -- the call site (just
    before ``effective_window_open``) already force-resets ``window_auto``/the
    ``wa_*`` anchors to a clean, non-latched state the moment the sensor is
    healthy again, in the SAME tick, before this function would otherwise get a
    chance to.  Observes every tick — a window can open whether or not we heat.
    The open threshold is adapted to the learned tau once the model is
    identified (steeper natural cooling -> higher threshold), else the fixed
    default.
    """
    if windows and not sensor_unavailable:
        return
    # ``now`` is the tick's snapshot monotonic instant.
    cfg = window_auto_cfg
    if rt.learning.ekf.identified:
        rt.window.wa_open_threshold = adaptive_open_threshold(
            rt.learning.ekf.tau_hours, room, t_out, cfg
        )
        cfg = replace(cfg, open_threshold=rt.window.wa_open_threshold)
    else:
        rt.window.wa_open_threshold = cfg.open_threshold
    # Measure the slope over the interval since the room last moved a full
    # sensor quantum, not per tick — a single 0.1 K quantization step on a
    # short tick would otherwise read as a steep drop and falsely open the
    # window.
    slope, rt.window.wa_ref_room, rt.window.wa_ref_mono = quantized_slope(
        room=room,
        ref_room=rt.window.wa_ref_room,
        ref_s=rt.window.wa_ref_mono,
        now_s=now,
        min_step=cfg.min_step,
    )
    if rt.window.wa_prev_mono is not None:
        dt_min = (now - rt.window.wa_prev_mono) / 60.0
        if 0.0 < dt_min < 60.0:
            # active cooling explains a drop -> neutralise the slope so it
            # cannot false-open (and still closes an earlier detection).
            rt.window.window_auto = step_window_auto(
                rt.window.window_auto, 0.0 if cooling else slope, dt_min, cfg
            )
    rt.window.wa_prev_mono = now


def observe_seasonless(
    rt: ZoneRuntime,
    room: float,
    t_out: float,
    *,
    now: float,
    day_ordinal: int,
) -> None:
    """Record a normalised heat-up rate while heating (shadow, ADR-0004/0026).

    The rate is sampled with an anchored accumulator (``heatup_rate``) instead
    of a per-tick delta: on a quantized sensor a per-tick ``(room-prev)/dt``
    with the ``rate>0`` filter keeps only the quantum up-crossings and biases
    the pooled rate — hence the beta_h cold-start seed — high.  The accumulator
    divides a real accumulated rise by the full elapsed interval (flat ticks
    included), which is unbiased regardless of the sensor quantum.

    ``now``/``day_ordinal`` are the tick's snapshot instants.
    """
    heating = rt.actuator.last_target is not None and rt.learning.last_u_h > 0.5
    rate = sample_heatup_rate(
        rt.learning.heatup_acc, heating=heating, room=room, mono=now
    )
    if rate is not None and rate > 0.0 and rt.actuator.last_target is not None:
        rt.learning.seasonless.observe(
            rate, rt.actuator.last_target, t_out, day_ordinal
        )
    rt.learning.prev_room = room
    rt.learning.prev_room_mono = now


def stage_observe(
    rt: ZoneRuntime,
    inputs: TickInputs,
    ing: IngestResult,
    *,
    entry_id: str,
    windows: list[str],
    actuator_entity: str,
    window_auto_cfg: WindowAutoConfig,
    adaptive_cool_cfg: str | bool,
    dynamics_override: DeviceDynamics | None,
    effective_window_open_fn: Callable[..., bool],
    set_mpc_params: Callable[[MpcParams], None],
    logger: logging.Logger,
) -> ObservationResult:
    """Window signals, capability, dynamics retune, EKF learn gate and
    window-auto observation.

    ``window_sensor_unavailable`` is collected and returned for the stage-end
    checkpoint; the ``TickStageError`` wrap transports it out of a mid-body
    abort (empty-pending aborts propagate bare).  ``effective_window_open``
    dispatches through the injected coordinator module global
    (test_phase6_health_checkpoints patch surface); ``set_mpc_params`` writes
    the coordinator's config-shaped ``_mpc_params`` attribute (ZoneTuning-owned
    — the one adapter-owned mutation of this stage, injected as a setter so the
    swallow boundary around the retune keeps its exact extent); the logger is
    the coordinator's (channel identity).
    """
    pending: list[HealthUpdate] = []
    try:
        return _stage_observe_guarded(
            rt,
            inputs,
            ing,
            pending,
            entry_id=entry_id,
            windows=windows,
            actuator_entity=actuator_entity,
            window_auto_cfg=window_auto_cfg,
            adaptive_cool_cfg=adaptive_cool_cfg,
            dynamics_override=dynamics_override,
            effective_window_open_fn=effective_window_open_fn,
            set_mpc_params=set_mpc_params,
            logger=logger,
        )
    except BaseException as err:  # transport-only; unwrapped in _run_once
        if pending:
            raise TickStageError(err, tuple(pending)) from err
        raise


def _stage_observe_guarded(
    rt: ZoneRuntime,
    inputs: TickInputs,
    ing: IngestResult,
    pending: list[HealthUpdate],
    *,
    entry_id: str,
    windows: list[str],
    actuator_entity: str,
    window_auto_cfg: WindowAutoConfig,
    adaptive_cool_cfg: str | bool,
    dynamics_override: DeviceDynamics | None,
    effective_window_open_fn: Callable[..., bool],
    set_mpc_params: Callable[[MpcParams], None],
    logger: logging.Logger,
) -> ObservationResult:
    """``stage_observe`` body under its transport wrap."""
    now = ing.now
    frozen = ing.frozen
    reading = ing.reading
    room = ing.room
    t_out_eff = ing.t_out_eff
    # The ``_window_open`` OR-fold on the snapshot contacts (ADR-0041 §5):
    # ``is_on`` is None exactly when a contact dropped off — flag it so the
    # caller falls back to slope/auto-detection instead of trusting stale
    # "closed" data; a confirmed "on" from any OTHER still-working contact is
    # trusted regardless (real positive evidence beats a sibling sensor's
    # dropout).
    sensor_window_open = any(bool(c.is_on) for c in inputs.windows)
    _window_sensor_unavailable = any(not c.available for c in inputs.windows)
    pending.append(
        HealthUpdate(
            issue_id=f"window_sensor_unavailable_{entry_id}",
            active=_window_sensor_unavailable,
            translation_key="window_sensor_unavailable",
            placeholders={"entity": ", ".join(windows)},
        )
    )
    # A healthy, configured sensor is authoritative (ADR-0041 §2 exclusivity)
    # and ``observe_window_auto`` below will not step the slope detector again
    # while it stays healthy -- so ``step_window_auto``'s own anti-stick
    # max-duration timer never gets another chance to run either.  An
    # ``open=True`` (or any stale slope/anchor state) latched during a PRIOR
    # sensor dropout (the §5 failsafe just below) would therefore stick
    # forever: the sensor correctly reports "closed" but the OR with a frozen
    # ``auto_open=True`` would pin the effective signal "open" regardless -- a
    # real room-stays-cold regression.  Reset BEFORE computing ``window_open``
    # below (not deferred into ``observe_window_auto``, which only runs later
    # this same tick) so the reset takes effect in the very tick the sensor
    # recovers, not one tick late.
    if windows and not _window_sensor_unavailable:
        if rt.window.window_auto != WindowAutoState():
            rt.window.window_auto = WindowAutoState()
            rt.dirty = True
        rt.window.wa_ref_room = None
        rt.window.wa_ref_mono = None
        rt.window.wa_prev_mono = None
    # ADR-0041 §5: a dropped-off window contact must not silently pin "closed"
    # -- an unavailable sensor already reads as ``sensor_window_open=False``
    # above (indistinguishable from a real "closed"), so the OR with
    # ``auto_open`` is what actually supplies the "heat as if no sensor"
    # failsafe signal here.
    window_open = effective_window_open_fn(
        sensor_open=sensor_window_open,
        auto_open=rt.window.window_auto.open,
        bypass=rt.user.window_bypass,
    )
    # ``_capability`` consumer rule on the snapshot's single actuator read:
    # empty/missing hvac_modes -> assume a heat-only TRV.
    can_heat, can_cool = (
        climate_capability(list(inputs.actuator.hvac_modes))
        if inputs.actuator.hvac_modes
        else (True, False)
    )
    # ADR-0008 tri-state: 'auto' follows cooling capability; a legacy bool is
    # honoured unchanged (True->on, False->off), so the upgrade is regression-free.
    adaptive_cool = resolve_adaptive_cool(adaptive_cool_cfg, can_cool=can_cool)
    # ADR-0052: retune the PI/MPC to the actuator's dynamics class so a fast
    # split AC is not driven by a 2 h radiator integrator (which oscillates).
    try:
        _modes_dyn = list(inputs.actuator.hvac_modes)
        rt.compressor.dynamics = classify_dynamics(
            domain=actuator_entity.split(".", 1)[0],
            can_cool=can_cool,
            can_fan="fan_only" in _modes_dyn,
            override=dynamics_override,
        )
        _prof = PROFILES[rt.compressor.dynamics]
        rt.learning.pi.apply_profile(
            kp=_prof.pi_kp, ki=_prof.pi_ki, offset_max=_prof.offset_max
        )
        set_mpc_params(
            MpcParams(horizon_blocks=_prof.mpc_horizon_blocks, dt_h=_prof.mpc_dt_h)
        )
    except Exception:  # noqa: BLE001 - tuning refresh must never break the tick
        logger.debug("Poise dynamics-profile refresh failed", exc_info=True)
    # ``_device_max`` consumer rule: absent/non-numeric -> DEVICE_MAX_C.
    device_max = (
        inputs.actuator.max_temp
        if inputs.actuator.max_temp is not None
        else DEVICE_MAX_C
    )

    if should_learn(
        window_open=window_open,
        frozen=frozen,
        heating_failed=rt.safety.prev_heating_failed,
    ):
        # Only ever teach the EKF from a genuinely MEASURED room reading -- a
        # DERIVED value (carried forward from ``last_good`` after a single
        # implausible raw sample) is a reasonable, frost-safe value to
        # *control* on, but it is not new information about the thermal plant,
        # so feeding it to the EKF would teach it a zero/stale delta as if the
        # room had truly stopped moving (ADR-0012 / ADR-0026).  This tick's
        # learning step is simply skipped -- unlike the learning-pause reset
        # below, the anchors are deliberately left untouched: a single glitchy
        # sample is not the "contaminated interval" the reset guards against,
        # and dropping ``prev_room`` here would erase the very last-good value
        # future ticks need to keep deriving from, regressing a short
        # flaky-sensor spell to the hard default one tick early.
        if reading.source is Source.MEASURED:
            learn_step(rt, room, t_out_eff, now=now, logger=logger)
            observe_seasonless(
                rt, room, t_out_eff, now=now, day_ordinal=inputs.local_day_ordinal
            )
    else:
        # While learning is paused (open window / frozen sensor, which now also
        # covers a DEFAULT-source reading -- see the ``frozen =`` assignment
        # above -- and a latched heating failure) drop the time anchors, so the
        # first step after resumption re-anchors from that tick instead of
        # integrating the whole contaminated interval.  A brief airing would
        # otherwise poison the EKF with a real-looking sub-hour dt (the 0<dt<1h
        # guard only rejects long gaps).  ADR-0024.
        rt.learning.last_mono = None
        rt.learning.prev_room = None
        rt.learning.prev_room_mono = None
        rt.learning.heatup_acc.reset()  # drop the heat-up anchor across the pause too
    observe_window_auto(
        rt,
        room,
        t_out_eff,
        now=now,
        cooling=rt.window.was_cooling,
        sensor_unavailable=_window_sensor_unavailable,
        windows=windows,
        window_auto_cfg=window_auto_cfg,
    )
    return ObservationResult(
        window_open=window_open,
        can_heat=can_heat,
        can_cool=can_cool,
        adaptive_cool=adaptive_cool,
        device_max=device_max,
        health_updates=tuple(pending),
    )


# ---------------------------------------------------------------------------
# Safety floors + schedule gate (plan 5.2)
# ---------------------------------------------------------------------------


def stage_safety_floors(
    ing: IngestResult,
    *,
    entry_id: str,
    humidity_entity: str | None,
    psychro_dewpoint_fn: Callable[[float, float], float],
) -> SafetyFloorsResult:
    """Mould floor + dewpoint cap from humidity.

    ``mould_protection_inactive`` is collected and returned for the stage-end
    checkpoint; the ``TickStageError`` wrap transports it out of a mid-body
    abort (empty-pending aborts propagate bare).  ``psychro_dewpoint``
    dispatches through the injected coordinator module global
    (test_phase6_health_checkpoints patch surface).
    """
    pending: list[HealthUpdate] = []
    try:
        room = ing.room
        rh = ing.rh
        t_out_eff = ing.t_out_eff
        # mould floor + dewpoint cap from humidity
        mold_min = None
        mold_capped = False
        dewpoint = None
        if rh is not None:
            dewpoint = psychro_dewpoint_fn(room, rh)
            # Keep a (conservative) mould floor even without an outdoor sensor
            # by using the effective outdoor proxy instead of skipping it.
            # Surface when the required floor is clipped at 24 °C -- the room
            # really needs dehumidification there, so protection is
            # insufficient.
            mold_min, mold_capped = mold_min_air_temperature_detail(t_out_eff, rh, room)
        # A configured humidity sensor that dropped out silently disables
        # mould protection (no floor computed) -> surface it.
        pending.append(
            HealthUpdate(
                issue_id=f"mould_protection_inactive_{entry_id}",
                active=humidity_entity is not None and rh is None,
                translation_key="mould_protection_inactive",
                placeholders={"entity": humidity_entity or ""},
            )
        )
        return SafetyFloorsResult(
            mold_min=mold_min,
            mold_capped=mold_capped,
            dewpoint=dewpoint,
            health_updates=tuple(pending),
        )
    except BaseException as err:  # transport-only; unwrapped in _run_once
        if pending:
            raise TickStageError(err, tuple(pending)) from err
        raise


def stage_schedule_gate(
    rt: ZoneRuntime,
    inputs: TickInputs,
    ing: IngestResult,
    obs: ObservationResult,
    *,
    schedule: ComfortSchedule,
    optimal_start: bool,
    optimal_stop: bool,
) -> ScheduleGateResult:
    """Schedule state + predictive decision -- the forecast seam."""
    t_out_eff = ing.t_out_eff
    can_heat = obs.can_heat
    # schedule: night setback + optimal-start preheat (ADR-0025).
    # Resolve the forecast outdoor (I/O) here, then let the pure planner
    # decide the effective base — the decision is unit-tested without HA.
    sched = schedule.state_at(inputs.local_minute)
    # A model is needed for the predictive plan in BOTH phases: preheat during
    # setback (lead = minutes to comfort) and coast/optimal-stop during comfort
    # (lead = minutes to setback).  Build it whenever the EKF is identified and
    # either feature is enabled.
    predictive = (
        can_heat and rt.learning.ekf.identified and (optimal_start or optimal_stop)
    )
    if predictive:
        lead_minutes = (
            sched.minutes_to_setback if sched.is_comfort else sched.minutes_to_comfort
        )
        # The prepare phase ENDS at the predictive decision.  The request only
        # NAMES the horizon -- ``float(lead_minutes)`` as the tick-current
        # horizon, ``t_out_eff`` as the provider fallback; ``_run_once``
        # resolves it under the lock.
        forecast_request: ForecastRequest | None = ForecastRequest(
            horizon_min=float(lead_minutes), fallback=t_out_eff
        )
    else:
        forecast_request = None
    return ScheduleGateResult(sched=sched, forecast_request=forecast_request)


# ---------------------------------------------------------------------------
# Comfort solve, intents, mode resolution
# ---------------------------------------------------------------------------


def stage_comfort_solve(
    rt: ZoneRuntime,
    ing: IngestResult,
    obs: ObservationResult,
    floors: SafetyFloorsResult,
    sp: SchedulePresenceResult,
    op: OperativeResult,
    lvl: PresenceLevelResult,
    *,
    category: Category,
    cool_min_outdoor: float,
    cool_lockout_enabled: bool,
    heat_max_outdoor: float,
    heat_lockout_enabled: bool,
    priority: float,
    cool_hard_cap: float,
    comfort_decide_fn: Callable[..., ComfortDecision],
) -> ComfortDecision:
    """The central comfort solver.

    ``comfort_decide`` dispatches through the injected coordinator module
    global (patch surface, test_phase0_health_emission); the callable is
    resolved by the coordinator's delegation at call time, never bound at
    construction.
    """
    t_out_eff = ing.t_out_eff
    t_rm_eff = ing.t_rm_eff
    can_heat = obs.can_heat
    can_cool = obs.can_cool
    adaptive_cool = obs.adaptive_cool
    mold_min = floors.mold_min
    dewpoint = floors.dewpoint
    base = sp.base
    room_decide = op.room_decide
    t_mrt_decide = op.t_mrt_decide
    _occupied = lvl.occupied
    _eco_widen = lvl.eco_widen
    _cool_ceiling = lvl.cool_ceiling
    decision = comfort_decide_fn(
        t_rm=t_rm_eff,
        room=room_decide,
        category=category,
        comfort_base=base,
        can_heat=can_heat,
        can_cool=can_cool,
        climate_mode=rt.user.climate_mode,
        cool_min_outdoor=(cool_min_outdoor if cool_lockout_enabled else None),
        heat_max_outdoor=(heat_max_outdoor if heat_lockout_enabled else None),
        t_out=t_out_eff,
        t_mrt=t_mrt_decide,
        frost_floor=FROST_FLOOR_C,
        mold_min=mold_min,
        dewpoint=dewpoint,
        priority=priority,
        occupied=_occupied,
        adaptive_cool=adaptive_cool,
        adaptive_cap=cool_hard_cap,
        eco_widen=_eco_widen,
        cool_ceiling_override=_cool_ceiling,
    )
    return decision


def stage_intents(
    rt: ZoneRuntime,
    ing: IngestResult,
    obs: ObservationResult,
    wt: WriteTargetResult,
) -> IntentsResult:
    """Heat/cool intent + EKF drive latches (ADR-0024)."""
    q_solar = ing.q_solar
    window_open = obs.window_open
    act_state = wt.act_state
    mode = wt.mode
    target = wt.target
    heating = rt.user.enabled and not window_open and mode == "heat"
    cooling = cooling_intent(
        enabled=rt.user.enabled, window_open=window_open, mode=mode
    )
    rt.window.was_cooling = mode == "cool"  # gate the window slope next tick
    # The EKF heating-drive uses the actuator's *real* running state when
    # reported (TRVZB running_state -> hvac_action), else our heat intent.
    rt.learning.last_u_h = heat_drive_signal(
        act_state.attributes.get("hvac_action") if act_state else None,
        fallback_heating=heating,
    )
    # β_c excitation (ADR-0024): the cooling counterpart, so cooling_identified
    # can leave False during the cooling season. Real hvac_action when reported
    # (AC "cooling"), else Poise's cool intent.
    rt.learning.last_u_c = cool_drive_signal(
        act_state.attributes.get("hvac_action") if act_state else None,
        fallback_cooling=cooling,
    )
    rt.learning.last_q_solar = q_solar
    rt.actuator.last_target = target
    return IntentsResult(heating=heating, cooling=cooling)


def stage_mode_resolution(
    rt: ZoneRuntime,
    ing: IngestResult,
    obs: ObservationResult,
    op: OperativeResult,
    wt: WriteTargetResult,
    band: ClimateBandResult,
    *,
    cool_min_outdoor: float,
    cool_lockout_enabled: bool,
    heat_max_outdoor: float,
    heat_lockout_enabled: bool,
    compressor_guard: str,
    comp_min_off_opt: float | None,
    comp_mode_hold_opt: float | None,
) -> ModeResolutionResult:
    """Mode arbitration + compressor-guard policy (ADR-0046 §8).

    INVARIANT (F1, ADR-0046 §9): ``final_mode`` and the guard policy are
    resolved UNCONDITIONALLY -- also while the zone is disabled -- so the
    always-on shadow lifecycle tracking stays alive.  Pinned by
    test_frost_rescue_disabled.
    """
    frozen = ing.frozen
    t_out_eff = ing.t_out_eff
    window_open = obs.window_open
    can_heat = obs.can_heat
    can_cool = obs.can_cool
    room_decide = op.room_decide
    act_state = wt.act_state
    mode = wt.mode
    target = wt.target
    _hum_action = band.hum_action
    _mode_nudge_blocked = ""  # ADR-0046 §8: compressor-guard suppression reason
    # Default for the unconditional shadow block below (no live mode nudge is
    # even considered while disabled, so "not blocked" is the honest value).
    _guard_block: str | None = None
    # Keep a controllable actuator in the mode that matches our write — cool
    # when we cool, heat otherwise — so it follows our setpoint instead of its
    # own off/auto schedule (TRVZB system_mode).
    act_modes = (act_state.attributes.get("hvac_modes") or []) if act_state else []
    # ADR-0050: fold active drying into the mode — dry wins ONLY when idle
    # (temp in band) + humidity asks + the device can dry; heat/cool/off/manual
    # pass through (temperature + safety primary).  Capability-gated: a
    # heat-only TRV has no "dry" mode -> dry_ok False -> no-op.
    # ADR-0059: an ACTIVE manual override must DRIVE the heat/cool/idle
    # direction, not only set the written value.  Collapse the band to a
    # hysteresis window around the commanded (clamped) override and reuse the
    # capability/outdoor-gated decide_mode, so a reversible AC flips to
    # cool/heat toward the manual value instead of idling in its last mode.
    # window/frozen keep precedence (they replace the "manual" tag upstream, so
    # mode != "manual" there); an "idle" ov_mode still flows through the seam
    # so dry-in-deadband can apply.  The WRITTEN target is unchanged -- only the
    # mode is derived here.
    # INVARIANT (F1, ADR-0046 §9 / ADR-0026): resolve mode + guard-policy
    # unconditionally so the always-on multi_lifecycle shadow never
    # UnboundLocalErrors (and freezes the wall-clock lifecycle) on a disabled
    # zone; only the WRITES below stay enabled-gated.
    _base_mode = mode
    if (
        rt.user.enabled
        and rt.user.override is not None
        and not window_open
        and not frozen
    ):
        _base_mode = override_mode(
            room=room_decide,
            override=target,
            hysteresis=0.5,
            outdoor=t_out_eff,
            climate_mode=rt.user.climate_mode,
            can_heat=can_heat,
            can_cool=can_cool,
            cool_min_outdoor=(cool_min_outdoor if cool_lockout_enabled else None),
            heat_max_outdoor=(heat_max_outdoor if heat_lockout_enabled else None),
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
    _guard_prof = PROFILES[rt.compressor.dynamics]
    _g_min_off = (
        comp_min_off_opt
        if comp_min_off_opt is not None
        else _guard_prof.compressor_min_off_s
    )
    _g_mode_hold = (
        comp_mode_hold_opt
        if comp_mode_hold_opt is not None
        else _guard_prof.compressor_mode_hold_s
    )
    _guard_pol = resolve_guard_policy(
        enabled=compressor_guard != COMPRESSOR_GUARD_OFF,
        can_condition=can_cool or "dry" in act_modes,
        min_off_s=_g_min_off,
        mode_hold_s=_g_mode_hold,
    )
    return ModeResolutionResult(
        final_mode=final_mode,
        act_modes=act_modes,
        guard_pol=_guard_pol,
        g_min_off=_g_min_off,
        g_mode_hold=_g_mode_hold,
        guard_block=_guard_block,
        mode_nudge_blocked=_mode_nudge_blocked,
    )


# ---------------------------------------------------------------------------
# Setpoint observation + write plan
# ---------------------------------------------------------------------------


def stage_setpoint_observe(
    rt: ZoneRuntime,
    ing: IngestResult,
    obs: ObservationResult,
    wt: WriteTargetResult,
    res: ModeResolutionResult,
    routing: HoldRoutingResult,
    nudge: ModeNudgeResult,
    *,
    actual_sp: float | None,
    step: float,
    adopt_external_setpoint: bool,
    setpoint_adopt_reason_fn: Callable[..., str],
) -> SetpointObservation:
    """Device setpoint observation, ADR-0052 §4 throttle, own-echo re-baseline
    and external-setpoint detection.

    ``actual_sp``/``step`` arrive PRE-PARSED by the coordinator's delegation
    (``parse_attr_number`` on the same ``wt.act_state`` object, incl. the
    ``or 0.1`` step fallback): the parse helper lives in ``ha/input_reader.py``,
    and importing it here would pull ``homeassistant`` into the pure py310
    suite.  Both parses are side-effect-free reads of the same frozen State
    object the stage already holds, so hoisting them to the call boundary is
    unobservable.

    The ONE ``ExternalOverrideTracker.observe_setpoint`` call yields decision
    AND reason; ``sp_adopt_reason`` travels in the returned
    ``SetpointObservation``.  ``setpoint_adopt_reason_fn`` resolves from the
    coordinator's module globals at call time (patch surface).
    """
    now = ing.now
    frozen = ing.frozen
    sched_active = ing.sched_active
    window_open = obs.window_open
    final_mode = res.final_mode
    _own_change = routing.own_change
    _mode_nudge = nudge.mode_nudge
    # Compare to the actuator's *actual* setpoint, not our last command, so we
    # re-assert when something external (e.g. an "off"/away automation) changed
    # it, while still skipping writes when it already matches.  ``actual_sp`` is
    # that parsed device setpoint; ``step`` snaps our target to the device's
    # setpoint step so a coarse TRV's rounded echo doesn't trigger a write every
    # tick.
    mode_changed = final_mode != rt.actuator.last_written_mode
    # ADR-0052 §4: a self-regulating climate entity (its own thermostat)
    # is nudged at most once per its dynamics regulation period, so Poise
    # does not thrash it (and its compressor) with per-tick comfort
    # adjustments. Mode changes, an open window, an override and a frozen
    # sensor bypass the throttle (safety/intent must be immediate). Dumb
    # setpoint actuators (regulation_period_s == 0, e.g. TRVs) are never
    # throttled -> heat-only test hardware is a no-op.
    _wprof = PROFILES[rt.compressor.dynamics]
    _reg_throttled = (
        _wprof.self_regulating
        and not mode_changed
        and not _mode_nudge
        and not window_open
        and rt.user.override is None
        and not frozen
        and regulation_throttled(
            now_s=now,
            last_write_s=rt.external.last_sp_write_ts,
            regulation_period_s=_wprof.regulation_period_s,
        )
    )
    # A device-side setpoint change (TRV wheel / vendor app) that differs from
    # what Poise last commanded is adopted as a manual hold with the zone's
    # override policy, instead of being overwritten.  Off while the device runs
    # its own schedule (the schedule, not the user, moves the setpoint) and
    # behind the opt-out; ``set_override`` clamps the adopted value to the norm
    # envelope.  Skipping this tick's write avoids overwriting the just-adopted
    # value -- next tick's target already reflects the new hold.
    # The reliable "is this our own write's echo?" signal.  If the actuator's
    # current state carries a Context Poise itself created (setpoint / mode
    # nudge), this reading is our write settling -- including a device
    # re-quantise / min-max clamp a push integration reports under our context
    # -- so accept the device's *actual* value as the new echo baseline and
    # never adopt it.  Only a change under a foreign/unknown context (a user via
    # IR/app, or an async echo a poll integration reports under a fresh context)
    # reaches the value/time detector below.
    # ``_own_change`` is computed once above (shared with the mode-adoption
    # gate); reuse it here for the setpoint echo re-baseline.
    tracker = ExternalOverrideTracker(rt.external)
    if _own_change and actual_sp is not None:
        # Accept the device's *actual* settled value (echo / clamp /
        # re-quantise) as the echo baseline so future reports of it are
        # recognised as echoes. Deliberately does NOT touch
        # last_sp_write_ts (see ``rebaseline_own_echo``): the echo window
        # and the ADR-0052 §4 regulation throttle both key off the real
        # last-*write* time.
        tracker.rebaseline_own_echo(actual_sp)
    # Decision AND reason from ONE observation — the Layer-1 glue gates
    # (opt-out, device schedule, own echo and the safety gates: an open window
    # or a frozen sensor must not let a device-side drop be grabbed as a
    # "manual" hold, the frost-drop phantom-hold class) run in chain order,
    # then the pure Layer-2 reason function classifies.
    observation = tracker.observe_setpoint(
        device_sp=actual_sp,
        now=now,
        echo_window_s=SETPOINT_ADOPT_ECHO_WINDOW_S,
        # At least one device step (the detector's documented contract).  The
        # step also serves the *echo classification*: a device that
        # settles/re-quantises our write within one step (e.g. 21.5 -> 21.8 on
        # a 0.5 K grid) must read as our echo, not a third value.  Lowering
        # this to the bare WRITE_DEADBAND_C (0.2) would let such a settle --
        # reported later under a *fresh* context -- be adopted as a phantom
        # "manual" hold on poll/sluggish devices; a real IR change is >= one
        # step.
        deadband=max(WRITE_DEADBAND_C, step),
        # A report at/below the frost floor is a TRV's own frost drop, never a
        # plausible user hold.
        frost_floor=FROST_FLOOR_C,
        adopt_enabled=adopt_external_setpoint,
        sched_active=sched_active,
        own_change=_own_change,
        window_open=window_open,
        frozen=frozen,
        setpoint_adopt_reason_fn=setpoint_adopt_reason_fn,
    )
    _adopted_sp: float | None = observation.adopt_setpoint
    return SetpointObservation(
        actual_sp=actual_sp,
        step=step,
        mode_changed=mode_changed,
        reg_throttled=_reg_throttled,
        adopted_sp=_adopted_sp,
        sp_adopt_reason=observation.reason,
    )


def plan_setpoint_write(
    rt: ZoneRuntime,
    wt: WriteTargetResult,
    adoption: ModeAdoptionResult,
    nudge: ModeNudgeResult,
    spo: SetpointObservation,
) -> ActuatorPlan:
    """Setpoint write gate → the tick's ``ActuatorPlan``.

    Pure decision at the gate position — directly before the dispatch, in the
    same await-free window, so the ``mode_override`` read keeps its place AFTER
    the nudge await and after this tick's adoption mutations.
    ``write_mode``/``hvac_mode`` RECORD the mode-nudge segment that already
    executed at its mandatory earlier position; ``write_setpoint`` gates the
    dispatch.  ``raw_setpoint`` goes on the wire; ``snapped_setpoint`` is the
    echo baseline the commit stamps (both None when no write was decided).
    """
    target = wt.target
    _actuator_online = wt.actuator_online
    _mode_nudge_blocked = nudge.mode_nudge_blocked
    actual_sp = spo.actual_sp
    step = spo.step
    mode_changed = spo.mode_changed
    _reg_throttled = spo.reg_throttled
    _adopted_sp = spo.adopted_sp
    write_setpoint = (
        _actuator_online
        and _adopted_sp is None  # adopted -> skip this tick's write
        # An ``off`` mode-hold writes no setpoint (the adopting tick still runs
        # this block; subsequent ticks take the frost-rescue branch).  A
        # setpoint into an off device would fight the user's off intent.
        and rt.user.mode_override != "off"
        # While the compressor guard holds a pending mode switch, defer the
        # *new regime's* setpoint.  Writing it now would push a cool setpoint
        # into a device still in heat (or vice versa); we hold the old regime
        # (mode + setpoint) until the guard clears.
        and not _mode_nudge_blocked
        and not _reg_throttled
        and should_write(
            actual_sp,
            snap_to_step(target, step),
            mode_changed=mode_changed,
            deadband=WRITE_DEADBAND_C,
        )
    )
    return ActuatorPlan(
        write_mode=nudge.mode_nudge,
        # hvac_mode records the intended *device* mode; the actuator currently
        # writes temperature only (the atomic mode+setpoint write stays opt-in
        # future work, ADR-0046 §8).  Kept for that future atomic path and for
        # command-level diagnostics.
        hvac_mode=adoption.desired_hvac,
        write_setpoint=write_setpoint,
        snapped_setpoint=snap_to_step(target, step) if write_setpoint else None,
        raw_setpoint=target if write_setpoint else None,
        reason="tick",
    )


# ---------------------------------------------------------------------------
# Finalize-context assembly
# ---------------------------------------------------------------------------


def build_finalize_context(
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
    """Assemble the prepare->finalize contract from the typed stage results.

    Pure construction -- no state reads, no I/O, no logging -- so building it
    before the savepoint await is unobservable; the field set is pinned by
    test_phase1_tick_result.
    """
    ing = state.ingest
    obs = state.observation
    floors = state.floors
    return FinalizeContext(
        now=ing.now,
        room=ing.room,
        room_decide=op.room_decide,
        reading_source=ing.reading.source,
        rh=ing.rh,
        dewpoint=floors.dewpoint,
        mold_min=floors.mold_min,
        mold_capped=floors.mold_capped,
        t_out_eff=ing.t_out_eff,
        t_rm_eff=ing.t_rm_eff,
        t_rm_source=ing.t_rm_source,
        q_solar=ing.q_solar,
        q_solar_source=ing.q_solar_source,
        q_solar_internal=ing.q_solar_internal,
        t_mrt=ing.t_mrt,
        mrt_source=ing.mrt_source,
        mrt_internal=ing.mrt_internal,
        sched=state.sched,
        frozen=ing.frozen,
        window_open=obs.window_open,
        decision=decision,
        eff_cool=wt.eff_cool,
        mode=wt.mode,
        target=wt.target,
        final_mode=res.final_mode,
        norm_binding=wt.norm_binding,
        binding_precedence=wt.binding_precedence,
        override_clamped=wt.override_clamped,
        heating=intents.heating,
        cooling=intents.cooling,
        failed=failed,
        adaptive_cool=obs.adaptive_cool,
        preheating=sp.preheating,
        preheat_outdoor=sp.preheat_outdoor,
        coasting=sp.coasting,
        act_state=wt.act_state,
        guard_pol=res.guard_pol,
        g_min_off=res.g_min_off,
        g_mode_hold=res.g_mode_hold,
        guard_block=guard_block,
        mode_nudge_blocked=mode_nudge_blocked,
        idle_park_mode=wt.idle_park_mode,
        mode_adopt_reason=mode_adopt_reason,
        sp_adopt_reason=sp_adopt_reason,
        climate_diag=band.climate_diag,
        sched_active=ing.sched_active,
        fault_active=ing.fault_active,
        heat_source_suspect=ing.heat_source_suspect,
        ext_num=op.ext_num,
        operative_active=op.operative_active,
    )
