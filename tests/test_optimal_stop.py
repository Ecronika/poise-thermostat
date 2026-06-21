from __future__ import annotations

from custom_components.poise.control.optimal_stop import residual_fraction


def test_fresh_long_heating_has_high_residual() -> None:
    assert residual_fraction(0.0, heating_duration_h=2.0) > 0.9


def test_residual_decays_with_elapsed_time() -> None:
    early = residual_fraction(0.1, heating_duration_h=1.0)
    late = residual_fraction(1.0, heating_duration_h=1.0)
    assert late < early


def test_longer_heating_charges_more() -> None:
    short = residual_fraction(0.1, heating_duration_h=0.2)
    long = residual_fraction(0.1, heating_duration_h=2.0)
    assert long > short


def test_guards_return_zero() -> None:
    assert residual_fraction(-1.0, 1.0) == 0.0
    assert residual_fraction(1.0, 0.0) == 0.0


def test_bounded_unit_interval() -> None:
    assert 0.0 <= residual_fraction(0.0, 100.0) <= 1.0


# --- Optimal-stop coast-down (closed-form, ADR-0034) ---

from custom_components.poise.control.optimal_stop import (  # noqa: E402
    advise_stop,
    coastdown_minutes,
)
from custom_components.poise.estimation.thermal_ekf import ThermalModel  # noqa: E402

_M = ThermalModel(alpha=0.15, beta_h=3.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)


def test_coast_already_below_target_is_zero() -> None:
    assert coastdown_minutes(_M, room=19.0, target=20.0, t_out=5.0) == 0.0


def test_coast_reachable_when_room_above_target_and_cold_outside() -> None:
    lead = coastdown_minutes(_M, room=22.0, target=20.0, t_out=5.0)
    assert lead is not None and lead > 0.0


def test_coast_unreachable_when_equilibrium_too_warm() -> None:
    # solar equilibrium above target -> passive cooling never reaches it
    m = ThermalModel(alpha=0.15, beta_h=3.0, beta_c=0.0, beta_s=2.0, beta_o=0.0)
    assert coastdown_minutes(m, room=22.0, target=20.0, t_out=19.0, q_solar=1.0) is None


def test_coast_horizon_caps() -> None:
    # equilibrium just below target -> coast reaches it but exceeds the horizon
    assert coastdown_minutes(_M, room=22.0, target=20.0, t_out=19.85) is None


def test_advise_stop_now_when_deadline_within_lead() -> None:
    a = advise_stop(_M, room=22.0, target=20.0, t_out=5.0, minutes_to_setback=10.0)
    assert a.reachable and a.stop_now


def test_advise_waits_when_deadline_far() -> None:
    a = advise_stop(_M, room=22.0, target=20.0, t_out=5.0, minutes_to_setback=600.0)
    assert a.reachable and not a.stop_now


def test_advise_keeps_heating_when_unreachable() -> None:
    m = ThermalModel(alpha=0.15, beta_h=3.0, beta_c=0.0, beta_s=2.0, beta_o=0.0)
    a = advise_stop(
        m, room=22.0, target=20.0, t_out=19.0, minutes_to_setback=5.0, q_solar=1.0
    )
    assert not a.reachable and not a.stop_now
