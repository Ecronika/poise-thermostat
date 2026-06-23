from __future__ import annotations

import math

from custom_components.poise.estimation.thermal_ekf import ThermalEKF, ThermalModel


def _true_step(
    t: float, u_h: float, alpha: float, beta_h: float, t_out: float, dt_h: float
) -> float:
    ex = math.exp(-alpha * dt_h)
    t_eq = t_out + (beta_h * u_h) / alpha
    return t_eq + (t - t_eq) * ex


def _drive_ekf(
    ekf: ThermalEKF,
    *,
    alpha_true: float,
    beta_h_true: float,
    t_out: float = 5.0,
    dt_h: float = 1.0 / 30.0,
    steps: int = 4000,
    target: float = 21.0,
) -> None:
    """Feed the EKF data from a known true 1R1C model (bang-bang excitation)."""
    t = 18.0
    for _ in range(steps):
        u_h = 1.0 if t < target else 0.0
        t = _true_step(t, u_h, alpha_true, beta_h_true, t_out, dt_h)
        ekf.predict(dt_h, t_out=t_out, u_h=u_h)
        ekf.update(t)


def test_ekf_learns_toward_true_parameters() -> None:
    alpha_true, beta_h_true = 0.08, 2.0
    ekf = ThermalEKF()  # starts at defaults alpha=0.15, beta_h=3.0
    a0 = abs(ekf.x[1] - alpha_true)
    b0 = abs(ekf.x[2] - beta_h_true)
    _drive_ekf(ekf, alpha_true=alpha_true, beta_h_true=beta_h_true)
    model = ekf.get_model()
    # learned parameters are markedly closer to ground truth than the prior
    assert abs(model.alpha - alpha_true) < 0.5 * a0
    assert abs(model.beta_h - beta_h_true) < 0.5 * b0


def test_ekf_covariance_stays_psd_and_symmetric() -> None:
    ekf = ThermalEKF()
    _drive_ekf(ekf, alpha_true=0.1, beta_h_true=2.5, steps=1000)
    for i in range(6):
        assert ekf.p[i][i] >= 0.0
        for j in range(6):
            assert math.isclose(ekf.p[i][j], ekf.p[j][i], abs_tol=1e-9)


def test_ekf_respects_parameter_bounds() -> None:
    ekf = ThermalEKF()
    _drive_ekf(ekf, alpha_true=0.05, beta_h_true=1.0, steps=2000)
    assert 0.005 <= ekf.x[1] <= 2.0  # alpha
    assert 0.1 <= ekf.x[2] <= 200.0  # beta_h


def test_prediction_std_decreases_with_data() -> None:
    ekf = ThermalEKF()
    initial = ekf.temperature_std
    _drive_ekf(ekf, alpha_true=0.1, beta_h_true=2.0, steps=500)
    assert ekf.temperature_std < initial
    assert 0.0 <= ekf.confidence <= 1.0


def test_outlier_is_soft_rejected() -> None:
    ekf = ThermalEKF()
    _drive_ekf(ekf, alpha_true=0.1, beta_h_true=2.0, steps=1000)
    before = ekf.get_model()
    ekf.predict(1.0 / 30.0, t_out=5.0, u_h=1.0)
    ekf.update(999.0)  # absurd spike
    after = ekf.get_model()
    assert abs(after.alpha - before.alpha) < 0.05
    assert abs(after.beta_h - before.beta_h) < 1.0


def test_serialization_roundtrip() -> None:
    ekf = ThermalEKF()
    _drive_ekf(ekf, alpha_true=0.1, beta_h_true=2.0, steps=300)
    restored = ThermalEKF.from_dict(ekf.to_dict())
    assert restored.x == ekf.x
    assert restored.p == ekf.p
    assert restored.n_updates == ekf.n_updates


def test_recovery_resets_pegged_alpha_keeps_counters() -> None:
    ekf = ThermalEKF()
    ekf.n_updates = 123
    ekf.x[1] = 2.0  # alpha pegged at the upper bound
    restored = ThermalEKF.from_dict(ekf.to_dict())
    assert restored.x[1] == 0.15  # reset to default
    assert restored.n_updates == 123  # counters preserved


def test_thermal_model_predict_matches_analytic_solution() -> None:
    model = ThermalModel(alpha=0.1, beta_h=2.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)
    # full power: equilibrium = t_out + beta_h/alpha = 5 + 20 = 25
    t = 15.0
    for _ in range(2000):
        t = model.predict(t, dt_h=1.0 / 30.0, t_out=5.0, u_h=1.0)
    assert abs(t - 25.0) < 0.2


def test_mode_counters_increment() -> None:
    ekf = ThermalEKF()
    ekf.predict(1.0 / 30.0, t_out=5.0, u_h=1.0)
    ekf.update(18.1)  # heating tick
    ekf.predict(1.0 / 30.0, t_out=5.0, u_h=0.0)
    ekf.update(18.0)  # idle tick
    assert ekf.n_heating >= 1
    assert ekf.n_idle >= 1


def test_confidence_reflects_identifiability() -> None:
    ekf = ThermalEKF()
    assert ekf.confidence == 0.0  # no observations -> not identifiable yet
    assert not ekf.identified
    _drive_ekf(ekf, alpha_true=0.1, beta_h_true=2.0, steps=4000)
    assert ekf.confidence > 0.0
    assert ekf.identified


def test_runtime_recovery_resets_pegged_alpha() -> None:
    ekf = ThermalEKF()
    ekf.x[1] = 0.005  # alpha pegged at the lower bound
    for _ in range(60):
        ekf.update(ekf.x[0])  # near-zero innovation keeps it pegged
    assert ekf.x[1] > 0.005  # runtime recovery reset it toward the default


def test_learning_phase_tracks_identifiability() -> None:
    ekf = ThermalEKF()
    assert ekf.learning_phase == "cold"
    ekf.predict(1.0 / 30.0, t_out=5.0, u_h=1.0)
    ekf.update(18.1)
    assert ekf.learning_phase in ("early", "learning")
    _drive_ekf(ekf, alpha_true=0.1, beta_h_true=2.0, steps=4000)
    assert ekf.learning_phase == "identified"


def test_from_dict_roundtrip_preserves_state() -> None:
    ekf = ThermalEKF()
    ekf.n_heating = 7
    restored = ThermalEKF.from_dict(ekf.to_dict())
    assert restored.n_heating == 7


def test_from_dict_bad_matrix_shape_recovers() -> None:
    # M8: a corrupt P (wrong shape) must recover with a fresh model, not crash.
    bad = ThermalEKF().to_dict()
    bad["p"] = [[1.0, 2.0], [3.0, 4.0]]  # 2x2 instead of 6x6
    ekf = ThermalEKF.from_dict(bad)
    assert isinstance(ekf, ThermalEKF)
    assert len(ekf.p) == 6 and all(len(row) == 6 for row in ekf.p)


def test_from_dict_version_mismatch_recovers() -> None:
    bad = ThermalEKF().to_dict()
    bad["ekf_version"] = 999
    ekf = ThermalEKF.from_dict(bad)
    assert ekf.n_heating == 0  # fresh model


def test_from_dict_non_finite_recovers() -> None:
    bad = ThermalEKF().to_dict()
    bad["x"][0] = float("nan")
    ekf = ThermalEKF.from_dict(bad)
    assert all(math.isfinite(v) for v in ekf.x)
