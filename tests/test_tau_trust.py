"""τ-trust gate for optimal-start/-stop (ADR-0034 N1)."""

from __future__ import annotations

import math

from custom_components.poise.estimation.tau_trust import (
    NEAR_BOUND_TAU_HIGH_H,
    TRUST_WINDOW_H,
    TauTrust,
    near_bound,
    observe_tau,
)
from custom_components.poise.estimation.thermal_ekf import ThermalEKF

_TICK_H = 1.0 / 60.0


def _feed(trust: TauTrust, taus: list[float], dt_h: float = _TICK_H) -> TauTrust:
    for tau in taus:
        trust = observe_tau(trust, tau_h=tau, dt_h=dt_h)
    return trust


def _hours(h: float) -> int:
    return int(round(h / _TICK_H))


def test_fresh_record_is_untrusted() -> None:
    t = TauTrust()
    assert not t.trusted
    assert math.isinf(t.spread_ratio)


def test_stable_tau_becomes_trusted_after_the_window() -> None:
    t = _feed(TauTrust(), [40.0] * _hours(TRUST_WINDOW_H - 1.0))
    assert not t.trusted  # not yet a full window
    t = _feed(t, [40.0] * _hours(1.5))
    assert t.trusted
    assert t.spread_ratio == 1.0


def test_swinging_tau_is_never_trusted() -> None:
    # daily swing 20 h -> 140 h (under the near-bound limit), as in the field
    n = _hours(48.0)
    taus = [
        20.0 + 120.0 * (0.5 - 0.5 * math.cos(2 * math.pi * i / _hours(24.0)))
        for i in range(n)
    ]
    t = _feed(TauTrust(), taus)
    assert t.clean_h >= TRUST_WINDOW_H
    assert t.spread_ratio > 2.0
    assert not t.trusted


def test_slow_drift_within_factor_two_is_trusted() -> None:
    n = _hours(30.0)
    t = _feed(TauTrust(), [40.0 + 30.0 * i / n for i in range(n)])  # 40 -> 70 h
    assert t.trusted


def test_near_bound_sample_clears_the_record() -> None:
    t = _feed(TauTrust(), [40.0] * _hours(30.0))
    assert t.trusted
    t = observe_tau(t, tau_h=NEAR_BOUND_TAU_HIGH_H, dt_h=_TICK_H)
    assert t == TauTrust()
    assert near_bound(199.9) and near_bound(0.6) and near_bound(math.nan)
    assert not near_bound(60.0)


def test_reset_clears_the_record() -> None:
    t = _feed(TauTrust(), [40.0] * _hours(30.0))
    assert observe_tau(t, tau_h=6.7, dt_h=_TICK_H, reset=True) == TauTrust()


def test_observation_gap_does_not_count_as_observed_time() -> None:
    t = observe_tau(TauTrust(), tau_h=40.0, dt_h=30.0)  # 30 h restart gap
    assert t.clean_h < 0.5
    assert not t.trusted


def test_window_is_bounded_and_roundtrips() -> None:
    t = _feed(TauTrust(), [50.0] * _hours(72.0))
    assert len(t.window) <= 24
    assert TauTrust.from_dict(t.to_dict()) == t


def test_malformed_dict_restores_untrusted() -> None:
    assert TauTrust.from_dict({"clean_h": "x"}) == TauTrust()
    assert TauTrust.from_dict({"window": [[1.0]]}) == TauTrust()
    assert TauTrust.from_dict({"clean_h": math.inf}) == TauTrust()
    assert TauTrust.from_dict(None) == TauTrust()


# --- wiring into the EKF ---------------------------------------------------


def _identified(ekf: ThermalEKF) -> ThermalEKF:
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.p[0][0] = 0.01
    assert ekf.identified
    return ekf


def test_identified_ekf_is_not_planning_ready_without_trust() -> None:
    ekf = _identified(ThermalEKF())
    assert not ekf.planning_ready


def test_planning_ready_with_trusted_tau() -> None:
    ekf = _identified(ThermalEKF())
    ekf.tau_trust = _feed(TauTrust(), [40.0] * _hours(25.0))
    assert ekf.planning_ready


def test_ekf_update_feeds_the_trust_record() -> None:
    ekf = ThermalEKF()
    ekf.predict(_TICK_H, t_out=10.0)
    ekf.update(ekf.x[0])
    assert ekf.tau_trust.clean_h > 0.0
    assert ekf.tau_trust.window


def test_runtime_recovery_reset_clears_trust() -> None:
    ekf = ThermalEKF()
    ekf.tau_trust = _feed(TauTrust(), [40.0] * _hours(25.0))
    ekf.x[1] = 0.005  # pegged at the 200 h cap
    ekf._alpha_pegged_count = 49
    ekf.predict(_TICK_H, t_out=10.0)
    ekf.update(ekf.x[0])
    assert ekf.tau_hours < 10.0  # reset to the prior
    assert ekf.tau_trust == TauTrust()


def test_trust_persists_and_legacy_store_starts_untrusted() -> None:
    ekf = ThermalEKF()
    ekf.x[1] = 1.0 / 40.0
    ekf.tau_trust = _feed(TauTrust(), [40.0] * _hours(25.0))
    data = ekf.to_dict()
    assert ThermalEKF.from_dict(data).tau_trust == ekf.tau_trust
    legacy = dict(data)
    del legacy["tau_trust"]
    assert ThermalEKF.from_dict(legacy).tau_trust == TauTrust()
