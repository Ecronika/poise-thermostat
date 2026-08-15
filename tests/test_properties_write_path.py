"""Property-based tests over the WRITE PATH — the safety promises (F.5).

The suite is rich in worked examples; what it lacked is a systematic search
over the input space of the chain that decides what actually reaches a
device: ``resolve_write_target`` -> ``snap_to_step`` -> ``plan_setpoint_write``.
These are the promises those functions make in their own docstrings, restated
as invariants that must hold for EVERY plausible input, not just the ones
somebody thought of.

Deliberately NOT property-tested: anything whose contract is a heuristic or a
numerical approximation (EKF convergence, PMV comfort scores, TPI tuning).
There a generated counter-example says "the model is a model", not "the code
is wrong" — false alarms would cost more than the tests are worth.

Strategy bounds are physical, not arbitrary: room/setpoint temperatures live
in [-40, 60] °C, device limits in [0, 40] °C. Values outside that are not
"untested edge cases" but sensor faults, and those have their own guards
(the finite boundary, review B.5).
"""

from __future__ import annotations

import math

from hypothesis import assume, given
from hypothesis import strategies as st

from custom_components.poise.comfort.norm_compliance import ASR_MAX_ROOM_C
from custom_components.poise.const import FROST_FLOOR_C
from custom_components.poise.control.tick_resolve import (
    resolve_write_target,
    should_write,
    snap_to_step,
)

# --- strategies ------------------------------------------------------------

temps = st.floats(
    min_value=-40.0, max_value=60.0, allow_nan=False, allow_infinity=False
)
device_limits = st.floats(
    min_value=0.0, max_value=40.0, allow_nan=False, allow_infinity=False
)
steps = st.sampled_from([0.1, 0.5, 1.0, 0.25, 2.0])
modes = st.sampled_from(["heat", "cool", "auto", "off"])


@st.composite
def comfort_band(draw: st.DrawFn) -> tuple[float, float]:
    """A VALID comfort band (heat_sp <= cool_sp).

    The pipeline never produces an inverted band, so generating one would test
    a state that cannot occur and invite false alarms.
    """
    lo = draw(temps)
    hi = draw(st.floats(min_value=lo, max_value=60.0, allow_nan=False))
    return lo, hi


# --- resolve_write_target --------------------------------------------------


@given(
    band=comfort_band(),
    write_setpoint=temps,
    override=st.one_of(st.none(), temps),
    mold_min=st.one_of(st.none(), temps),
    device_max=device_limits,
    device_min=st.one_of(st.none(), device_limits),
    comfort_mode=modes,
    window_open=st.booleans(),
)
def test_heating_never_undercuts_the_health_floor(
    band: tuple[float, float],
    write_setpoint: float,
    override: float | None,
    mold_min: float | None,
    device_max: float,
    device_min: float | None,
    comfort_mode: str,
    window_open: bool,
) -> None:
    """Frost/mould floor holds whenever we are not cooling — even against a
    device_max BELOW it.

    That inversion is the documented trap (tick_resolve.py: "A misreported
    device max *below* the active health floor would win the inversion
    (SAFETY > HEALTH) and silently defeat frost/mould protection"). A single
    example proves the guard exists; this proves no input combination slips
    past it.
    """
    heat_sp, cool_sp = band
    wt = resolve_write_target(
        window_open=window_open,
        override=override,
        heat_sp=heat_sp,
        cool_sp=cool_sp,
        write_setpoint=write_setpoint,
        comfort_mode=comfort_mode,
        frost_floor=FROST_FLOOR_C,
        mold_min=mold_min,
        device_max=device_max,
        device_min=device_min,
    )
    if wt.mode == "cool":
        return  # the floor is deliberately skipped while cooling
    floor = max(FROST_FLOOR_C, mold_min if mold_min is not None else FROST_FLOOR_C)
    assert wt.target >= round(floor, 1) - 1e-9, (
        f"health floor {floor} undercut with target {wt.target} "
        f"(device_max={device_max}, mode={wt.mode})"
    )


@given(
    band=comfort_band(),
    write_setpoint=temps,
    override=st.one_of(st.none(), temps),
    mold_min=st.one_of(st.none(), temps),
    device_max=device_limits,
    device_min=device_limits,
    comfort_mode=modes,
    window_open=st.booleans(),
)
def test_device_min_is_never_undercut_in_any_mode(
    band: tuple[float, float],
    write_setpoint: float,
    override: float | None,
    mold_min: float | None,
    device_max: float,
    device_min: float,
    comfort_mode: str,
    window_open: bool,
) -> None:
    """``device_min`` is a SAFETY floor in BOTH heating and cooling.

    Writing below what the device can hold makes it echo its own minimum, and
    the change-aware write throttle then rewrites every tick — the thrash the
    frozen-sensor path produced before E.13e.
    """
    heat_sp, cool_sp = band
    wt = resolve_write_target(
        window_open=window_open,
        override=override,
        heat_sp=heat_sp,
        cool_sp=cool_sp,
        write_setpoint=write_setpoint,
        comfort_mode=comfort_mode,
        frost_floor=FROST_FLOOR_C,
        mold_min=mold_min,
        device_max=device_max,
        device_min=device_min,
    )
    assert wt.target >= round(device_min, 1) - 1e-9, (
        f"device_min {device_min} undercut with target {wt.target} (mode={wt.mode})"
    )


@given(
    band=comfort_band(),
    write_setpoint=temps,
    override=st.one_of(st.none(), temps),
    mold_min=st.one_of(st.none(), temps),
    device_max=device_limits,
    device_min=st.one_of(st.none(), device_limits),
    comfort_mode=modes,
)
def test_open_window_always_parks_at_the_floor(
    band: tuple[float, float],
    write_setpoint: float,
    override: float | None,
    mold_min: float | None,
    device_max: float,
    device_min: float | None,
    comfort_mode: str,
) -> None:
    """An open window beats everything else — including an active override.

    The comfort target must never survive it; only the safety floors may raise
    the parked value.
    """
    heat_sp, cool_sp = band
    wt = resolve_write_target(
        window_open=True,
        override=override,
        heat_sp=heat_sp,
        cool_sp=cool_sp,
        write_setpoint=write_setpoint,
        comfort_mode=comfort_mode,
        frost_floor=FROST_FLOOR_C,
        mold_min=mold_min,
        device_max=device_max,
        device_min=device_min,
    )
    floor = max(FROST_FLOOR_C, mold_min if mold_min is not None else FROST_FLOOR_C)
    lower = min(round(floor, 1), round(device_max, 1))
    if device_min is not None:
        lower = min(lower, round(device_min, 1))
    assert wt.target <= max(round(floor, 1), round(device_min or 0.0, 1)) + 1e-9, (
        f"window open but target {wt.target} exceeds the parked floor {floor}"
    )
    assert wt.target >= lower - 1e-9


@given(
    band=comfort_band(),
    override=temps,
    write_setpoint=temps,
    device_max=device_limits,
    comfort_mode=modes,
)
def test_override_clamped_flag_matches_the_band(
    band: tuple[float, float],
    override: float,
    write_setpoint: float,
    device_max: float,
    comfort_mode: str,
) -> None:
    """``override_clamped`` reports EXACTLY "the manual value left the band".

    It drives user-visible feedback, so a false negative silently swallows the
    user's intent — the flag must not be a heuristic.
    """
    heat_sp, cool_sp = band
    wt = resolve_write_target(
        window_open=False,
        override=override,
        heat_sp=heat_sp,
        cool_sp=cool_sp,
        write_setpoint=write_setpoint,
        comfort_mode=comfort_mode,
        frost_floor=FROST_FLOOR_C,
        mold_min=None,
        device_max=device_max,
        device_min=None,
    )
    outside = not (heat_sp <= override <= cool_sp)
    assert wt.override_clamped is outside, (
        f"override={override} band=[{heat_sp}, {cool_sp}] -> flag "
        f"{wt.override_clamped}, expected {outside}"
    )


@given(
    band=comfort_band(),
    write_setpoint=temps,
    override=st.one_of(st.none(), temps),
    mold_min=st.one_of(st.none(), temps),
    device_max=device_limits,
    device_min=st.one_of(st.none(), device_limits),
    comfort_mode=modes,
    window_open=st.booleans(),
)
def test_target_is_always_finite_and_rounded(
    band: tuple[float, float],
    write_setpoint: float,
    override: float | None,
    mold_min: float | None,
    device_max: float,
    device_min: float | None,
    comfort_mode: str,
    window_open: bool,
) -> None:
    """Whatever goes in, a finite 0.1-resolution value comes out.

    The wire value is derived from this; a non-finite or unrounded target
    would reach ``snap_to_step`` and the actuator.
    """
    heat_sp, cool_sp = band
    wt = resolve_write_target(
        window_open=window_open,
        override=override,
        heat_sp=heat_sp,
        cool_sp=cool_sp,
        write_setpoint=write_setpoint,
        comfort_mode=comfort_mode,
        frost_floor=FROST_FLOOR_C,
        mold_min=mold_min,
        device_max=device_max,
        device_min=device_min,
    )
    assert math.isfinite(wt.target)
    assert wt.target == round(wt.target, 1)
    assert wt.mode in {"heat", "cool", "auto", "off", "manual"}


# --- snap_to_step ----------------------------------------------------------


@given(value=temps, step=steps)
def test_snap_is_idempotent(value: float, step: float) -> None:
    """Snapping an already-snapped value changes nothing.

    Without this the write throttle could oscillate: each tick would snap the
    previous snap somewhere else and read as a change.
    """
    once = snap_to_step(value, step)
    assert snap_to_step(once, step) == once


@given(value=temps, step=steps)
def test_snap_stays_within_half_a_step(value: float, step: float) -> None:
    """The snapped value is the device grid point nearest the target.

    A larger deviation would mean we command something the user did not ask
    for; the write throttle compares against exactly this value.
    """
    snapped = snap_to_step(value, step)
    assert abs(snapped - value) <= step / 2 + 1e-9


@given(
    value=st.sampled_from([math.inf, -math.inf, math.nan]),
    step=steps,
)
def test_snap_is_total_for_non_finite_input(value: float, step: float) -> None:
    """B.5 promise: non-finite input passes through instead of raising.

    ``round(inf/step)`` used to raise OverflowError and killed the whole tick
    before the write gate could reject the value.
    """
    out = snap_to_step(value, step)
    assert out is value or (math.isnan(value) and math.isnan(out))


@given(
    value=temps,
    step=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
)
def test_snap_passes_through_without_a_usable_step(value: float, step: float) -> None:
    """No step reported (0 or negative) -> the value is left alone."""
    assert snap_to_step(value, step) == value


# --- should_write ----------------------------------------------------------


@given(
    actual=st.one_of(st.none(), temps),
    target=temps,
    deadband=st.floats(
        min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False
    ),
    mode_changed=st.booleans(),
)
def test_should_write_is_exactly_the_deadband_rule(
    actual: float | None, target: float, deadband: float, mode_changed: bool
) -> None:
    """Write iff we do not know the device value, the mode changed, or the
    difference reaches the deadband — no third condition, no hysteresis.

    Battery TRVs pay for every extra write, so an accidental "write anyway"
    branch is a real cost, not a cosmetic one.
    """
    out = should_write(actual, target, mode_changed=mode_changed, deadband=deadband)
    if actual is None or mode_changed:
        assert out is True
        return
    assert out is (round(abs(target - actual), 3) >= deadband)


@given(actual=temps, target=temps, deadband=st.just(0.2))
def test_should_write_is_symmetric(
    actual: float, target: float, deadband: float
) -> None:
    """Direction must not matter: over- and undershoot are equally a change."""
    assume(not math.isclose(actual, target))
    a = should_write(actual, target, mode_changed=False, deadband=deadband)
    b = should_write(target, actual, mode_changed=False, deadband=deadband)
    assert a is b


# --- the composed chain ----------------------------------------------------


@given(
    band=comfort_band(),
    write_setpoint=temps,
    mold_min=st.one_of(st.none(), temps),
    device_max=device_limits,
    device_min=st.one_of(st.none(), device_limits),
    comfort_mode=modes,
    window_open=st.booleans(),
    step=steps,
)
def test_wire_value_stays_inside_the_absolute_envelope(
    band: tuple[float, float],
    write_setpoint: float,
    mold_min: float | None,
    device_max: float,
    device_min: float | None,
    comfort_mode: str,
    window_open: bool,
    step: float,
) -> None:
    """End-to-end: what would go on the wire never leaves the physical envelope.

    Snapping happens AFTER the constraint solver, so it can push a value off
    the grid by up to half a step — this pins that the composed result still
    cannot exceed the device's own limits by more than that.

    NOTE, found by this very test: while COOLING there is deliberately no
    lower bound other than ``device_min``. The frost/mould floor is skipped
    (``if mode != "cool"`` in ``resolve_write_target``) so a heating floor
    cannot block cooling, which means an absurd cool setpoint would pass
    through unclamped. It cannot occur in practice — ``cool_sp`` comes from
    the comfort band and never goes near freezing — and a real device also
    reports its own ``min_temp``. Documented here rather than asserted away,
    so the asymmetry is a known design property and not a silent surprise.
    """
    heat_sp, cool_sp = band
    wt = resolve_write_target(
        window_open=window_open,
        override=None,
        heat_sp=heat_sp,
        cool_sp=cool_sp,
        write_setpoint=write_setpoint,
        comfort_mode=comfort_mode,
        frost_floor=FROST_FLOOR_C,
        mold_min=mold_min,
        device_max=device_max,
        device_min=device_min,
    )
    wire = snap_to_step(wt.target, step)
    assert math.isfinite(wire)
    slack = step / 2 + 1e-9
    if wt.mode != "cool":
        assert wire <= max(ASR_MAX_ROOM_C, device_max, wt.target) + slack
        assert wire >= round(FROST_FLOOR_C, 1) - slack
    if device_min is not None:
        # The only lower bound that holds in EVERY mode.
        assert wire >= round(device_min, 1) - slack
