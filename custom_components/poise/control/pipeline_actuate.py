"""HA-free synchronous actuation-phase tick stage implementations.

The three stages behind ``ActuatePhase``: the mode arbitration plus
compressor-guard policy, the device-setpoint observation (ADR-0052 §4
throttle, own-echo re-baseline, external-setpoint detection) and the setpoint
write gate that yields the tick's ``ActuatorPlan``.

``ZoneRuntime`` owns the domain state; this module holds the stage
*implementations* as plain functions over (state groups, inputs, prior stage
results), and the ``ZoneRuntime`` methods delegate here 1:1.  Substitution
rules:

* domain-state reads/writes go to the ``ZoneRuntime`` group fields
  (``rt.user.override``, ``rt.actuator.last_written_mode``,
  ``rt.external.last_sp_write_ts``, ...).
* config-owned values (``ZoneTuning``/structure attributes, which stay on the
  coordinator) arrive as explicit keyword parameters.
* NO PATCH SURFACE lives in this module.  ``setpoint_adopt_reason_fn`` is
  injected for layering, not for patching: it is a plain import in the
  orchestrator since plan O.4, and no test ever patched it.  The awaits of the
  actuation phase stay in ``ha/phase_actuate.py`` — these stages are the
  decisions between them.
* NO ERROR BOUNDARY lives here either: an exception in one of these stages
  propagates to ``_run_once`` unwrapped, because none of them collects
  ``HealthUpdate``s that would need transporting out.

This module is hass-free (mypy --strict, py310-clean): the one HA type that
flows through (``State``, the tick's central positioned actuator read carried
by ``WriteTargetResult.act_state``) is imported under ``TYPE_CHECKING`` only.

Split out of ``control/tick_pipeline.py`` by plan P.1; the prepare and
finalize stages live in ``control/pipeline_prepare.py`` and
``control/pipeline_finalize.py``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..comfort.mode_seam import mode_arbitration
from ..const import (
    COMPRESSOR_GUARD_OFF,
    FROST_FLOOR_C,
    SETPOINT_ADOPT_ECHO_WINDOW_S,
    WRITE_DEADBAND_C,
)
from ..control.cooling import override_mode
from ..control.dynamics import PROFILES, regulation_throttled
from ..control.external_override import ExternalOverrideTracker
from ..control.tick_resolve import should_write, snap_to_step
from ..multi.lifecycle import resolve_guard_policy
from ..runtime.tick_result import (
    ActuatorPlan,
    IngestResult,
    ModeResolutionResult,
    ObservationResult,
    SetpointObservation,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..runtime.tick_result import (
        ClimateBandResult,
        HoldRoutingResult,
        ModeAdoptionResult,
        ModeNudgeResult,
        OperativeResult,
        WriteTargetResult,
    )
    from ..runtime.zone_runtime import ZoneRuntime


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------


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
    fan_first_requested: bool = False,
) -> ModeResolutionResult:
    """Mode arbitration + compressor-guard policy (ADR-0046 §8).

    INVARIANT (F1, ADR-0046 §9): ``final_mode`` and the guard policy are
    resolved UNCONDITIONALLY -- also while the zone is disabled -- so the
    always-on shadow lifecycle tracking stays alive.  Pinned by
    test_frost_rescue_disabled.

    ADR-0068 U5: ``fan_first_requested`` is the fan-first FSM's mode
    candidate; it may intercept ONLY a NORMAL ``cool`` — the intent
    provenance is derived here, at the one site that knows both manual
    channels (setpoint hold AND mode hold) plus the safety signals.
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
    # Defaults only — the live guard block and the nudge-suppression reason
    # are decided in the orchestrator's mode-nudge stage; a disabled zone
    # keeps these defaults ("not blocked" is the honest value there).
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
            hysteresis=0.5,  # K band around the manual value (see override_mode)
            outdoor=t_out_eff,
            climate_mode=rt.user.climate_mode,
            can_heat=can_heat,
            can_cool=can_cool,
            cool_min_outdoor=(cool_min_outdoor if cool_lockout_enabled else None),
            heat_max_outdoor=(heat_max_outdoor if heat_lockout_enabled else None),
        )
    # ADR-0068 U5 intent provenance: safety (window/frozen) beats manual
    # beats normal. BOTH manual channels count — the setpoint hold and the
    # adopted mode hold.
    if window_open or frozen:
        _origin = "safety"
    elif rt.user.override is not None or rt.user.mode_override is not None:
        _origin = "manual"
    else:
        _origin = "normal"
    _fan_first = fan_first_requested and _origin == "normal"
    final_mode = mode_arbitration(
        base_mode=_base_mode,
        humidity_action=_hum_action,
        dry_ok="dry" in act_modes,
        fan_first=_fan_first,
    )
    # ADR-0046 §8 (live): resolve the guard POLICY here so the write path can
    # hold back a mode nudge that would short-cycle the compressor — start it
    # within min-off, or flip cool<->dry within mode-hold. Capability-gated
    # (cool/dry only) + kill switch; the block decision itself is made in the
    # orchestrator's mode-nudge stage.
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
        intent_origin=_origin,
        fan_first_allowed=_fan_first and final_mode == "fan_only",
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
    ``SetpointObservation``.  ``setpoint_adopt_reason_fn`` is a plain import in
    the orchestrator since plan O.4 (no test ever patched it).
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
    # A fan-first entry/exit flips ``final_mode`` too, so every FSM transition
    # counts as a mode change here — it bypasses the §4 throttle and forces a
    # setpoint write (ADR-0069 U5 note).
    mode_changed = final_mode != rt.actuator.last_written_mode
    # ADR-0052 §4: a self-regulating climate entity (its own thermostat)
    # is nudged at most once per its dynamics regulation period, so Poise
    # does not thrash it (and its compressor) with per-tick comfort
    # adjustments. Mode changes, an open window, an override and a frozen
    # sensor bypass the throttle (safety/intent must be immediate). Only
    # self-regulating actuators throttle; a dumb setpoint actuator (TRV) is
    # never throttled -> heat-only test hardware is a no-op.
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
    # behind the opt-out; ``set_override`` clamps the adopted value into the
    # safe envelope [FROST_FLOOR_C, DEVICE_MAX_C] — the norm envelope (ASR cap
    # / mould floor) binds the written target in ``resolve_write_target``, not
    # the stored hold.  Skipping this tick's write avoids overwriting the
    # just-adopted value -- next tick's target already reflects the new hold.
    # The reliable "is this our own write's echo?" signal.  If the actuator's
    # current state carries a Context Poise itself created (setpoint / mode
    # nudge), this reading is our write settling -- including a device
    # re-quantise / min-max clamp a push integration reports under our context
    # -- so accept the device's *actual* value as the new echo baseline and
    # never adopt it.  Only a change under a foreign/unknown context (a user via
    # IR/app, or an async echo a poll integration reports under a fresh context)
    # reaches the value/time detector below.
    # ``_own_change`` comes from the hold-routing stage (one Context check per
    # tick, shared with the mode-adoption gate); reuse it here for the
    # setpoint echo re-baseline.
    tracker = ExternalOverrideTracker(rt.external)
    # C.8f: is this reading a late echo of a SUPERSEDED command? ``own_change``
    # matches the shared 16-slot context ring (mode/fan writes included), so a
    # sluggish push device confirming an older command still reads as "ours" —
    # judging it against the newest command would count a healthy device as
    # divergent. Such a reading is no convergence evidence in either direction.
    _settle_ctx = (
        wt.act_state.context.id
        if wt.act_state is not None and wt.act_state.context is not None
        else None
    )
    stale_own_echo = _own_change and _settle_ctx != rt.external.last_sp_ctx_id
    if _own_change and actual_sp is not None:
        # Accept the device's *actual* settled value (echo / clamp /
        # re-quantise) as the echo baseline so future reports of it are
        # recognised as echoes (adoption stays suppressed either way). The
        # convergence watchdog deliberately does NOT use this baseline — it
        # judges against ``last_cmd_sp``, which the commit stamps and nothing
        # re-baselines, so a clamped device cannot read as "converged".
        # Deliberately does NOT touch last_sp_write_ts (see
        # ``rebaseline_own_echo``): the echo window and the ADR-0052 §4
        # regulation throttle both key off the real last-*write* time.
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
        stale_own_echo=stale_own_echo,
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
        # B.5 final guard (defense-in-depth behind the read boundary): a
        # non-finite target must never go on the wire — and must be rejected
        # BEFORE snap_to_step/should_write see it.
        and math.isfinite(target)
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
