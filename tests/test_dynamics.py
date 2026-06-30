"""ADR-0052 actuator dynamics profiles (pure)."""

from __future__ import annotations

from custom_components.poise.control.dynamics import (
    DeviceDynamics,
    classify_dynamics,
    profile_for,
)
from custom_components.poise.control.pi import PiCompensator


def test_cooling_climate_is_fast_air() -> None:
    got = classify_dynamics(domain="climate", can_cool=True, can_fan=False)
    assert got is DeviceDynamics.FAST_AIR


def test_fan_climate_is_fast_air() -> None:
    got = classify_dynamics(domain="climate", can_cool=False, can_fan=True)
    assert got is DeviceDynamics.FAST_AIR


def test_heat_only_climate_is_slow_hydronic() -> None:
    got = classify_dynamics(domain="climate", can_cool=False, can_fan=False)
    assert got is DeviceDynamics.SLOW_HYDRONIC


def test_valve_number_is_slow_hydronic() -> None:
    got = classify_dynamics(domain="number", can_cool=False, can_fan=False)
    assert got is DeviceDynamics.SLOW_HYDRONIC


def test_override_wins_and_auto_falls_through() -> None:
    # explicit override forces the class even for a cooling AC
    forced = classify_dynamics(
        domain="climate", can_cool=True, can_fan=False, override="very_slow"
    )
    assert forced is DeviceDynamics.VERY_SLOW
    # "auto" -> auto-detect (cooling climate -> fast air)
    auto = classify_dynamics(
        domain="climate", can_cool=True, can_fan=False, override="auto"
    )
    assert auto is DeviceDynamics.FAST_AIR
    # unknown override -> safe auto-detect (heat-only -> slow)
    junk = classify_dynamics(
        domain="climate", can_cool=False, can_fan=False, override="garbage"
    )
    assert junk is DeviceDynamics.SLOW_HYDRONIC


def test_fast_air_is_minute_scale_and_clamps_tighter() -> None:
    fast = profile_for(domain="climate", can_cool=True, can_fan=False)
    slow = profile_for(domain="climate", can_cool=False, can_fan=False)
    assert fast.integral_time_h < 0.25  # ~10 min, not hours
    assert abs(slow.integral_time_h - 2.0) < 1e-6  # today's 2 h unchanged
    assert fast.offset_max < slow.offset_max  # tighter anti-windup clamp
    assert fast.mpc_dt_h < slow.mpc_dt_h  # shorter MPC blocks
    assert fast.self_regulating is True and slow.self_regulating is False


def test_apply_profile_retunes_pi_and_keeps_acc() -> None:
    pi = PiCompensator()  # default slow: Ti = 2 h, clamp 2 K
    pi.acc = 1.5
    fast = profile_for(domain="climate", can_cool=True, can_fan=False)
    pi.apply_profile(kp=fast.pi_kp, ki=fast.pi_ki, offset_max=fast.offset_max)
    assert pi.acc == 1.5  # integrator preserved across the retune
    # a large error: the offset is now clamped to the fast profile's tighter
    # 0.8 K (not 2 K), but still pushes the setpoint up.
    sp, _ = pi.evaluate(target=24.0, room=18.0, external=18.0, dt_h=1.0 / 60.0)
    assert sp <= 24.0 + fast.offset_max + 1e-9
    assert sp >= 24.0 + 0.5
