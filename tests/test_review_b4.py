"""Pure numeric/safety fixes from the follow-up review (F22, F15, F7)."""

from __future__ import annotations

from custom_components.poise.comfort.mold import (
    mold_min_air_temperature,
    mold_min_air_temperature_detail,
)
from custom_components.poise.estimation.thermal_ekf import _Q, _T, ThermalEKF
from custom_components.poise.safety.heating_failure import HeatingFailureDetector

# --- F22: heating-failure detector tolerates a non-monotonic clock ----------


def test_heating_failure_backward_clock_does_not_stall() -> None:
    det = HeatingFailureDetector(delay_h=0.5, cmd_delta=2.0, min_rise=0.2)
    det.update(now_h=100.0, room=18.0, setpoint=21.0, running=True)  # arm
    # clock steps back 10 h (DST/NTP); without the F22 re-anchor the elapsed goes
    # negative and detection freezes for the whole offset.
    det.update(now_h=90.0, room=18.0, setpoint=21.0, running=True)
    failed = det.update(now_h=90.6, room=18.0, setpoint=21.0, running=True)
    assert failed is True


def test_heating_failure_monotonic_still_trips() -> None:
    det = HeatingFailureDetector(delay_h=0.5, cmd_delta=2.0, min_rise=0.2)
    assert det.update(now_h=0.0, room=18.0, setpoint=21.0, running=True) is False
    assert det.update(now_h=0.6, room=18.0, setpoint=21.0, running=True) is True


# --- F15: mould cap surfaces silent under-protection ------------------------


def test_mold_cap_flags_insufficient_protection() -> None:
    # very cold outside + nearly saturated room -> required temp >> 24 C ceiling
    capped, was_capped = mold_min_air_temperature_detail(
        t_out=-15.0, rh_percent=95.0, t_air_ref=21.0
    )
    assert capped == 24.0
    assert was_capped is True


def test_mold_normal_case_not_capped() -> None:
    capped, was_capped = mold_min_air_temperature_detail(
        t_out=5.0, rh_percent=50.0, t_air_ref=21.0
    )
    assert was_capped is False
    assert capped < 24.0
    assert mold_min_air_temperature(5.0, 50.0, 21.0) == capped  # back-compat


# --- F7: EKF process noise scales with step length --------------------------


def _zero_p(ekf: ThermalEKF) -> None:
    for i in range(len(ekf.p)):
        for j in range(len(ekf.p[i])):
            ekf.p[i][j] = 0.0


def test_ekf_q_scales_linearly_with_dt() -> None:
    # with P started at 0 and idle drive, predict leaves only the T-state Q, so
    # p[T][T] == _Q[T] * (dt_h / nominal). A double-length step injects double Q.
    nominal = ThermalEKF()
    longer = ThermalEKF()
    _zero_p(nominal)
    _zero_p(longer)
    nominal.predict(dt_h=1.0 / 60.0, t_out=5.0)
    longer.predict(dt_h=2.0 / 60.0, t_out=5.0)
    assert abs(nominal.p[_T][_T] - _Q[_T]) < 1e-6
    assert abs(longer.p[_T][_T] - 2.0 * _Q[_T]) < 1e-6
