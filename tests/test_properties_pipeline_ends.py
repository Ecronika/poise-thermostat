"""Property-based tests for the two ENDS of the control pipeline (F.5).

``test_properties_write_path`` covers the middle (target resolution and
snapping). This covers what feeds it and what guards the exit:

* ``comfort.dual_setpoint.decide`` — the band solver at the entrance. Its
  promises are structural ("never invert the band", "never below the health
  floors", "never cool into condensation"), which is exactly what a generator
  can attack from every side at once.
* ``constraints.resolve_constraints`` — the precedence solver every clamp in
  the system funnels through. Its contract is algebraic (idempotent, invents
  no values, ties go health-first), and today it rests on a handful of worked
  examples.
* ``control.pipeline_actuate.plan_setpoint_write`` — the write gate. One promise
  matters above all: no write escapes a gate.

Strategy bounds follow the measured traps (see the F.5 mapping): a comfort
band is never inverted, ``device_min <= device_max``, steps come from the set
real devices report, and floor comparisons carry a 0.05 K tolerance because
the resolver rounds its result to 0.1 K at the end.
"""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from custom_components.poise.clock import ManualClock
from custom_components.poise.comfort import dual_setpoint
from custom_components.poise.constraints import Constraint, ConstraintKind
from custom_components.poise.constraints import resolve_constraints as solve
from custom_components.poise.contracts import Precedence
from custom_components.poise.control.pipeline_actuate import plan_setpoint_write
from custom_components.poise.control.tick_resolve import snap_to_step
from custom_components.poise.runtime.tick_result import (
    ModeAdoptionResult,
    ModeNudgeResult,
    SetpointObservation,
    WriteTargetResult,
)
from custom_components.poise.runtime.zone_runtime import ZoneRuntime

ROUNDING_SLACK = 0.05 + 1e-9  # the resolver rounds to 0.1 K at the very end

temps = st.floats(
    min_value=-20.0, max_value=60.0, allow_nan=False, allow_infinity=False
)
real_steps = st.sampled_from([0.1, 0.2, 0.25, 0.5, 1.0])


# --- constraint solver -----------------------------------------------------

precedences = st.sampled_from(list(Precedence))
kinds = st.sampled_from(list(ConstraintKind))


@st.composite
def constraint(draw: st.DrawFn) -> Constraint:
    return Constraint(
        draw(temps),
        draw(st.text(min_size=1, max_size=8)),
        draw(kinds),
        draw(precedences),
    )


constraint_sets = st.lists(constraint(), min_size=0, max_size=5)


@given(desired=temps, cs=constraint_sets)
def test_solver_is_idempotent(desired: float, cs: list[Constraint]) -> None:
    """Re-clamping an already-clamped value changes nothing.

    Every stage that clamps runs through this solver; if it were not
    idempotent, composing two stages could walk a value further each tick.
    """
    once = solve(desired, cs).value
    assert solve(once, cs).value == once


@given(desired=temps, cs=constraint_sets)
def test_solver_invents_no_values(desired: float, cs: list[Constraint]) -> None:
    """The result is either the desired value or exactly one of the bounds.

    A value that is neither would mean the solver computed a compromise — and
    a silently invented setpoint is the one thing a safety clamp must not do.
    """
    res = solve(desired, cs)
    allowed = {desired} | {c.value for c in cs}
    assert res.value in allowed


@given(desired=temps, cs=constraint_sets)
def test_unbound_result_is_the_desired_value(
    desired: float, cs: list[Constraint]
) -> None:
    """No binding constraint reported => the value passed through untouched.

    Only this direction holds: on an inversion a binding IS reported while the
    value may coincidentally equal ``desired`` (measured trap from the F.5
    mapping), so the converse must not be asserted.
    """
    res = solve(desired, cs)
    if res.binding is None:
        assert res.value == desired


@given(desired=temps, cs=constraint_sets)
def test_without_inversion_the_result_respects_both_bounds(
    desired: float, cs: list[Constraint]
) -> None:
    """Floors compose to their max, caps to their min — unless they invert."""
    res = solve(desired, cs)
    floors = [c for c in cs if c.kind is ConstraintKind.FLOOR]
    caps = [c for c in cs if c.kind is ConstraintKind.CAP]
    if not floors or not caps:
        return
    hi_floor = max(c.value for c in floors)
    lo_cap = min(c.value for c in caps)
    if hi_floor > lo_cap:
        return  # inversion: precedence decides, tested below
    assert hi_floor - 1e-9 <= res.value <= lo_cap + 1e-9


@given(
    desired=temps,
    floor_v=temps,
    cap_v=temps,
    floor_p=precedences,
    cap_p=precedences,
)
def test_inversion_is_decided_by_precedence_ties_to_the_floor(
    desired: float,
    floor_v: float,
    cap_v: float,
    floor_p: Precedence,
    cap_p: Precedence,
) -> None:
    """On inversion the higher precedence wins; equal precedence goes to the
    FLOOR — "health-first", the rule that keeps a misreported device cap from
    defeating frost protection."""
    if floor_v <= cap_v:
        return
    floor = Constraint(floor_v, "f", ConstraintKind.FLOOR, floor_p)
    cap = Constraint(cap_v, "c", ConstraintKind.CAP, cap_p)
    res = solve(desired, [floor, cap])
    winner = floor if int(floor_p) <= int(cap_p) else cap
    assert res.value == winner.value
    assert res.binding is winner


# --- comfort band solver ---------------------------------------------------


@given(
    t_rm=st.floats(min_value=-10.0, max_value=35.0, allow_nan=False),
    room=st.floats(min_value=0.0, max_value=40.0, allow_nan=False),
    t_out=st.floats(min_value=-25.0, max_value=45.0, allow_nan=False),
    comfort_base=st.floats(min_value=16.0, max_value=26.0, allow_nan=False),
    can_heat=st.booleans(),
    can_cool=st.booleans(),
    frost_floor=st.floats(min_value=5.0, max_value=12.0, allow_nan=False),
    mold_min=st.one_of(
        st.none(), st.floats(min_value=10.0, max_value=24.0, allow_nan=False)
    ),
    dewpoint=st.one_of(
        st.none(), st.floats(min_value=0.0, max_value=25.0, allow_nan=False)
    ),
    priority=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    occupied=st.booleans(),
    climate_mode=st.sampled_from(["auto", "heat", "cool", "off"]),
)
def test_comfort_band_is_never_inverted_and_respects_health_floors(
    t_rm: float,
    room: float,
    t_out: float,
    comfort_base: float,
    can_heat: bool,
    can_cool: bool,
    frost_floor: float,
    mold_min: float | None,
    dewpoint: float | None,
    priority: float,
    occupied: bool,
    climate_mode: str,
) -> None:
    """The band solver's structural promises, over the whole input space.

    An inverted band (cool below heat) would make every downstream clamp
    nonsensical — the override clamp ``min(max(o, heat), cool)`` would snap to
    the cool edge and silently discard user intent.
    """
    d = dual_setpoint.decide(
        t_rm=t_rm,
        room=room,
        comfort_base=comfort_base,
        can_heat=can_heat,
        can_cool=can_cool,
        climate_mode=climate_mode,
        t_out=t_out,
        frost_floor=frost_floor,
        mold_min=mold_min,
        dewpoint=dewpoint,
        priority=priority,
        occupied=occupied,
    )
    assert d.cool_sp >= d.heat_sp - 1e-9, (
        f"band inverted: heat={d.heat_sp} cool={d.cool_sp}"
    )
    health_floor = max(frost_floor, mold_min if mold_min is not None else frost_floor)
    assert d.heat_sp >= health_floor - ROUNDING_SLACK, (
        f"heat edge {d.heat_sp} below the health floor {health_floor}"
    )
    assert math.isfinite(d.heat_sp) and math.isfinite(d.cool_sp)
    if d.target is not None:
        assert math.isfinite(d.target)
    assert d.mode in {"heat", "cool", "idle", "off", "dry", "fan_only", "manual"}


# --- the write gate --------------------------------------------------------


def _plan(
    *,
    target: float,
    actuator_online: bool,
    mode_override: str | None,
    mode_nudge_blocked: str,
    reg_throttled: bool,
    adopted_sp: float | None,
    actual_sp: float | None,
    step: float,
    mode_changed: bool,
) -> tuple[object, ZoneRuntime]:
    """Fresh runtime per example — a leaked one would look like flakiness."""
    rt = ZoneRuntime(ManualClock(10_000.0))
    rt.user.mode_override = mode_override
    wt = WriteTargetResult(
        act_state=None,
        actuator_online=actuator_online,
        cool_ac=None,
        idle_park_mode=None,
        eff_cool=26.0,
        target=target,
        mode="heat",
        norm_binding=None,
        binding_precedence=None,
        override_clamped=False,
    )
    spo = SetpointObservation(
        actual_sp=actual_sp,
        step=step,
        mode_changed=mode_changed,
        reg_throttled=reg_throttled,
        adopted_sp=adopted_sp,
    )
    plan = plan_setpoint_write(
        rt,
        wt,
        ModeAdoptionResult(desired_hvac="heat", mode_adopt_reason=""),
        ModeNudgeResult(
            mode_nudge=False, guard_block=None, mode_nudge_blocked=mode_nudge_blocked
        ),
        spo,
    )
    return plan, rt


@given(
    target=st.one_of(temps, st.sampled_from([math.nan, math.inf, -math.inf])),
    actuator_online=st.booleans(),
    mode_override=st.sampled_from([None, "off", "heat", "cool"]),
    mode_nudge_blocked=st.sampled_from(["", "min-off 120s", "mode-hold 300s"]),
    reg_throttled=st.booleans(),
    adopted_sp=st.one_of(st.none(), temps),
    actual_sp=st.one_of(st.none(), temps),
    step=real_steps,
    mode_changed=st.booleans(),
)
def test_no_write_escapes_a_gate(
    target: float,
    actuator_online: bool,
    mode_override: str | None,
    mode_nudge_blocked: str,
    reg_throttled: bool,
    adopted_sp: float | None,
    actual_sp: float | None,
    step: float,
    mode_changed: bool,
) -> None:
    """``write_setpoint`` implies EVERY gate was open — no exception.

    Each gate exists for a reason someone paid for once: an offline actuator,
    a non-finite target (B.5), a just-adopted user hold, an ``off`` hold, the
    compressor guard, the ADR-0052 §4 throttle. This asserts the conjunction
    holds for every combination, not just the ones with a worked example.
    """
    plan, _rt = _plan(
        target=target,
        actuator_online=actuator_online,
        mode_override=mode_override,
        mode_nudge_blocked=mode_nudge_blocked,
        reg_throttled=reg_throttled,
        adopted_sp=adopted_sp,
        actual_sp=actual_sp,
        step=step,
        mode_changed=mode_changed,
    )
    if plan.write_setpoint:
        assert actuator_online
        assert math.isfinite(target)
        assert adopted_sp is None
        assert mode_override != "off"
        assert not mode_nudge_blocked
        assert not reg_throttled
        # ... and the deadband actually asked for it.
        assert (
            actual_sp is None
            or mode_changed
            or round(abs(snap_to_step(target, step) - actual_sp), 3) >= 0.2
        )
    else:
        assert plan.raw_setpoint is None
        assert plan.snapped_setpoint is None


@given(
    target=temps,
    actual_sp=st.one_of(st.none(), temps),
    step=real_steps,
    mode_changed=st.booleans(),
)
def test_wire_value_is_raw_and_baseline_is_snapped(
    target: float, actual_sp: float | None, step: float, mode_changed: bool
) -> None:
    """When a write happens: RAW goes on the wire, SNAPPED is the echo baseline.

    Mixing the two is a subtle, expensive bug — the throttle would compare
    against a value the device never received and rewrite every tick.
    """
    plan, _rt = _plan(
        target=target,
        actuator_online=True,
        mode_override=None,
        mode_nudge_blocked="",
        reg_throttled=False,
        adopted_sp=None,
        actual_sp=actual_sp,
        step=step,
        mode_changed=mode_changed,
    )
    if plan.write_setpoint:
        assert plan.raw_setpoint == target
        assert plan.snapped_setpoint == snap_to_step(target, step)
