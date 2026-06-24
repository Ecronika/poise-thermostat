from __future__ import annotations

from custom_components.poise.control.mpc import MpcParams, optimize_power
from custom_components.poise.estimation.thermal_ekf import ThermalModel

_MODEL = ThermalModel(alpha=0.1, beta_h=2.0, beta_c=4.0, beta_s=0.0, beta_o=0.0)


def test_cold_room_commands_high_power() -> None:
    power = optimize_power(
        _MODEL, t0=17.0, target=21.0, lower=19.0, upper=25.0, t_out=5.0
    )
    assert power > 0.5


def test_warm_room_commands_low_power() -> None:
    power = optimize_power(
        _MODEL, t0=24.5, target=21.0, lower=19.0, upper=25.0, t_out=5.0
    )
    assert power < 0.3


def test_optimizer_is_deterministic() -> None:
    a = optimize_power(_MODEL, 18.0, 21.0, 19.0, 25.0, 5.0)
    b = optimize_power(_MODEL, 18.0, 21.0, 19.0, 25.0, 5.0)
    assert a == b


def test_mpc_holds_band_in_plant_without_overshoot() -> None:
    params = MpcParams()
    t = 18.0
    final_max = t
    for _ in range(240):  # 240 * 5 min = 20 h
        power = optimize_power(_MODEL, t, 21.0, 19.0, 25.0, 5.0, params)
        t = _MODEL.predict(t, params.dt_h, 5.0, u_h=power)
        final_max = max(final_max, t)
    assert 19.0 <= t <= 25.0  # stays within the comfort band
    assert final_max <= 25.5  # asymmetric penalty curbs overshoot


def test_in_band_room_is_not_driven_up() -> None:
    # M4: with a dead-zone band cost, a room already inside [lower, upper] gets
    # ~no heating power (no point-chasing above the lower edge).
    power = optimize_power(
        _MODEL, t0=21.5, target=21.0, lower=21.0, upper=24.0, t_out=5.0
    )
    assert power < 0.15


def test_overshoot_candidate_is_rejected_over_horizon() -> None:
    # M4: a first-step power that would push the room above `upper` later in the
    # horizon must cost more than a moderate one (overshoot charged every step).
    from custom_components.poise.control.mpc import MpcParams, _rollout_cost

    p = MpcParams()
    hot = _rollout_cost(
        _MODEL, t0=23.8, first_power=1.0, lower=21.0, upper=24.0, t_out=5.0, params=p
    )
    mild = _rollout_cost(
        _MODEL, t0=23.8, first_power=0.0, lower=21.0, upper=24.0, t_out=5.0, params=p
    )
    assert hot > mild  # full power into the upper edge is penalised
