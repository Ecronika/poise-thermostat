from __future__ import annotations

import pytest

from custom_components.poise.estimation.seasonless_rate import (
    SeasonlessRate,
    gaussian_weight,
    half_life_weight,
    normalized_rate,
)


def test_normalized_rate_divides_by_drive() -> None:
    # 2 °C/h heat-up against a 20 K drive -> 0.1 per K
    assert normalized_rate(2.0, target=21.0, outdoor=1.0) == pytest.approx(0.1)


def test_normalized_rate_guards_tiny_drive() -> None:
    assert normalized_rate(2.0, target=21.0, outdoor=20.5) is None


def test_season_invariance_same_norm_different_outdoor() -> None:
    # Same building: heat_rate scales with drive, so the *normalised* rate matches.
    r_mild = normalized_rate(1.0, 21.0, 11.0)  # drive 10 -> 0.1
    r_cold = normalized_rate(2.0, 21.0, 1.0)  # drive 20 -> 0.1
    assert r_mild == pytest.approx(r_cold)


def test_gaussian_and_half_life_weights() -> None:
    assert gaussian_weight(0.0, 5.0) == pytest.approx(1.0)
    assert gaussian_weight(5.0, 5.0) == pytest.approx(0.6065, abs=1e-3)
    assert half_life_weight(0.0) == 1.0
    assert half_life_weight(180.0) == pytest.approx(0.5, abs=1e-6)


def test_estimate_prefers_similar_outdoor() -> None:
    s = SeasonlessRate()
    s.observe(heat_rate=1.0, target=21.0, outdoor=10.0, day=0)  # r=0.0909
    s.observe(heat_rate=4.0, target=21.0, outdoor=1.0, day=0)  # r=0.2
    near_cold = s.estimate_norm(outdoor=1.0, now_day=0)
    near_mild = s.estimate_norm(outdoor=10.0, now_day=0)
    assert near_cold is not None and near_mild is not None
    assert near_cold > near_mild  # cold query weighted toward the cold obs


def test_heat_rate_prior_reconstructs_rate() -> None:
    s = SeasonlessRate()
    s.observe(heat_rate=2.0, target=21.0, outdoor=1.0, day=0)  # r=0.1
    prior = s.heat_rate_prior(target=21.0, outdoor=6.0, now_day=0)  # 0.1*15
    assert prior == pytest.approx(1.5)


def test_phase_thresholds() -> None:
    s = SeasonlessRate()
    assert s.phase == "cold"
    for i in range(5):
        s.observe(1.0, 21.0, 1.0, day=i)
    assert s.phase == "early"


def test_history_capped() -> None:
    s = SeasonlessRate()
    for i in range(250):
        s.observe(1.0, 21.0, 1.0, day=i)
    assert s.count == 200


def test_persistence_roundtrip() -> None:
    s = SeasonlessRate()
    for i, t_out in enumerate([1.0, 5.0, 9.0]):
        s.observe(2.0, 21.0, t_out, day=i)
    restored = SeasonlessRate.from_dict(s.to_dict())
    assert restored.count == s.count
    assert restored.estimate_norm(5.0, 3) == pytest.approx(s.estimate_norm(5.0, 3))


def test_empty_estimate_is_none() -> None:
    assert SeasonlessRate().estimate_norm(5.0, 0) is None
    assert SeasonlessRate().heat_rate_prior(21.0, 5.0, 0) is None


def test_ekf_seed_beta_h_clamps() -> None:
    from custom_components.poise.estimation.thermal_ekf import ThermalEKF

    ekf = ThermalEKF()
    ekf.seed_beta_h(5.0)
    assert ekf.get_model().beta_h == 5.0
    ekf.seed_beta_h(99999.0)  # clamped to upper bound
    assert ekf.get_model().beta_h <= 200.0
    ekf.seed_beta_h(-10.0)  # clamped to lower bound
    assert ekf.get_model().beta_h >= 0.1
