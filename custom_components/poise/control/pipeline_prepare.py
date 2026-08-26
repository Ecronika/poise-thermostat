"""HA-free synchronous prepare-phase tick stage implementations.

The eleven stages behind ``PreparePhase``: the device-health evaluation and
the temperature/environment ingest, the observation family (EKF learn gate,
window-auto slope detector, seasonless heat-up rate), the safety floors, the
schedule/forecast gate, the central comfort solve and the intent latches.

"HA-free synchronous" rather than "pure", and the distinction is not
pedantic: five of these functions mutate the ``ZoneRuntime`` passed to them
(``learn_step``, ``observe_window_auto``, ``observe_seasonless``,
``_stage_observe_guarded``, ``stage_intents``), two of those log, and five
carry an error boundary.  What they do NOT do is touch Home Assistant, await,
or reach a device -- every effect they have lands on an object handed in by
the caller.  ``pipeline_finalize`` is the one module here that really is pure
construction.

``ZoneRuntime`` owns the domain state and all prepare stages; this module
holds those stage *implementations* as plain functions over (state groups,
inputs, prior stage results).  The ``ZoneRuntime`` methods delegate here 1:1
and the coordinator's ``_stage_*`` methods are thin delegations onto the
runtime.  Substitution rules:

* domain-state reads/writes go to the ``ZoneRuntime`` group fields
  (``rt.user.override``, ``rt.learning.ekf``, ...); the ``dirty`` persistence
  flag lives directly on the runtime (``rt.dirty``).
* config-owned values (``ZoneTuning``/structure attributes, which stay on the
  coordinator) arrive as explicit keyword parameters.
* PATCH SURFACES: integration tests patch these symbols on their OWNING module
  (``comfort.dual_setpoint.decide`` / ``safety.sensor_watchdog.is_frozen`` /
  ``ingestion.ingest_temperature`` /
  ``control.window_auto.effective_window_open`` /
  ``estimation.psychrometrics.dewpoint``).  Those callables are therefore
  INJECTED per call (``*_fn`` parameters): the orchestrator's delegation reads
  the name off the owning MODULE object at call time, so ``unittest.mock.patch``
  on the owner keeps hitting every dispatch.  They must never be bound early
  (module import or constructor) here.  All five of them are consumed by the
  stages in THIS module.
* LOG CHANNELS are behaviour: the two swallow boundaries that log do so via an
  injected ``logging.Logger`` — the coordinator passes its own ``_LOGGER`` so
  every record keeps the baseline channel
  ``custom_components.poise.coordinator`` with identical text/level.  Both of
  them live here: the EKF observer step in ``learn_step``
  (``logger.exception``) and the dynamics-profile retune in
  ``_stage_observe_guarded`` (``logger.debug``).
* ERROR TRANSPORT: three stages (``stage_ingest``, ``stage_observe``,
  ``stage_safety_floors``) wrap their body in ``except BaseException`` and
  re-raise as ``TickStageError`` so the ``HealthUpdate``s already appended
  travel out of a mid-body abort; ``_run_once`` unwraps them.  With nothing
  pending the abort propagates bare.

This module is hass-free (mypy --strict, py310-clean): the one HA type that
flows through (``State``, the tick's central positioned actuator read carried
by ``WriteTargetResult.act_state``) is imported under ``TYPE_CHECKING`` only.

Split out of ``control/tick_pipeline.py`` by plan P.1; the actuation and
finalize stages live in ``control/pipeline_actuate.py`` and
``control/pipeline_finalize.py``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..adaptive_cool import resolve_adaptive_cool
from ..comfort.mold import mold_min_air_temperature_detail
from ..comfort.virtual_mrt import virtual_mrt
from ..const import (
    DEVICE_MAX_C,
    FROST_FLOOR_C,
    LOW_BATTERY_PCT,
    MIN_PLAUSIBLE_TAU_H,
    SENSOR_FREEZE_AFTER_S,
)
from ..contracts import Source
from ..control.cooling import cooling_intent
from ..control.dynamics import PROFILES, classify_dynamics
from ..control.mpc import MpcParams
from ..control.tick_resolve import (
    cool_drive_signal,
    heat_drive_signal,
    select_mrt,
    select_q_solar,
    select_t_rm,
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
from ..runtime.tick_result import (
    ForecastRequest,
    HealthUpdate,
    IngestResult,
    IntentsResult,
    ObservationResult,
    SafetyFloorsResult,
    ScheduleGateResult,
    TickStageError,
)
from ..safety.sensor_watchdog import sensor_at_heat_source, should_learn

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable, Sequence

    from ..comfort.dual_setpoint import ComfortDecision
    from ..comfort.en16798 import Category
    from ..comfort.schedule import ComfortSchedule
    from ..control.dynamics import DeviceDynamics
    from ..control.window_auto import WindowAutoConfig
    from ..runtime.tick_inputs import TickInputs
    from ..runtime.tick_result import (
        OperativeResult,
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
    ``is_frozen`` is read off ``safety.sensor_watchdog`` at call time (patch
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
    windows: Sequence[str],
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
        # Reject a >1 h gap (restart/suspend): the slope detector must not
        # integrate an interval it never observed.
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
    windows: Sequence[str],
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
    is read off ``control.window_auto`` at call time
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
    windows: Sequence[str],
    actuator_entity: str,
    window_auto_cfg: WindowAutoConfig,
    adaptive_cool_cfg: str | bool,
    dynamics_override: DeviceDynamics | None,
    effective_window_open_fn: Callable[..., bool],
    set_mpc_params: Callable[[MpcParams], None],
    logger: logging.Logger,
) -> ObservationResult:
    """``stage_observe`` body under its transport wrap.

    One narrative, chained by data in this order: window health (and the ADR-0041
    §5 reset) -> effective window signal -> actuator capability + dynamics retune
    -> learning gate -> window-auto update -> result. Only the retune is wrapped;
    the ``try`` below covers those three statements and nothing else, so a failing
    tuning refresh costs the profile and leaves window handling and learning
    untouched.

    NOT split, and that is a decision on record (plan P.2, outcome P.2b,
    2026-08-17). The capability/retune block is the one genuine seam - it owns
    that whole boundary and shares no state with the window chain - but
    extracting it measured out at +29 code lines in the module to save 15 here,
    with the four config parameters degraded to pass-throughs. The call cannot
    move earlier to avoid that: today a window-block abort means the retune has
    NOT run, and reordering would change that. The ratchet row carries the full
    reasoning.
    """
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
        cooling_failed=rt.safety.prev_cooling_failed,
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
        # While learning is paused (open window / frozen sensor, which now
        # also covers a DEFAULT-source reading -- see the ``frozen =``
        # assignment above -- and a latched heating or cooling failure) drop
        # the time anchors, so the first step after resumption re-anchors
        # from that tick instead of integrating the whole contaminated
        # interval.  A brief airing would otherwise poison the EKF with a
        # real-looking sub-hour dt (the 0<dt<1h guard only rejects long
        # gaps).  ADR-0024.
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
    abort (empty-pending aborts propagate bare).  ``dewpoint``
    is read off ``estimation.psychrometrics`` at call time
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
    sched = schedule.state_at(inputs.local_minute, inputs.local_weekday)
    # A model is needed for the predictive plan in BOTH phases: preheat during
    # setback (lead = minutes to comfort) and coast/optimal-stop during comfort
    # (lead = minutes to setback).  Build it whenever the EKF is identified and
    # either feature is enabled.
    predictive = (
        can_heat and rt.learning.ekf.identified and (optimal_start or optimal_stop)
    )
    lead_minutes = (
        sched.minutes_to_setback if sched.is_comfort else sched.minutes_to_comfort
    )
    if predictive and lead_minutes is not None:
        # The prepare phase ENDS at the predictive decision.  The request only
        # NAMES the horizon -- ``float(lead_minutes)`` as the tick-current
        # horizon, ``t_out_eff`` as the provider fallback; ``_run_once``
        # resolves it under the lock.  ``lead_minutes is None`` means the
        # upcoming transition DOES NOT EXIST (always-comfort/always-setback,
        # P2.1) -- same no-request path as an unidentified model: no forecast
        # is fetched and optimal start/stop stays inactive.
        forecast_request: ForecastRequest | None = ForecastRequest(
            horizon_min=float(lead_minutes), fallback=t_out_eff
        )
    else:
        forecast_request = None
    return ScheduleGateResult(sched=sched, forecast_request=forecast_request)


# ---------------------------------------------------------------------------
# Comfort solve + intents
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
        # ADR-0069 U7/U8: previous-tick tier-2 inputs from the activation
        # step (0.0 unless the respective latch is LIVE and its per-tick
        # conditions held — the outcome stage owns that decision).
        cool_edge_credit=rt.latches.fan_ce_credit_k,
        pmv_offset_k=rt.latches.pmv_offset_k,
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
