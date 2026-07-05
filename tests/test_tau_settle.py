"""Tests for the pure settle-based τ-confidence (ADR-0024 companion, Task 343)."""

from __future__ import annotations

from custom_components.poise.estimation.tau_settle import (
    TauSettle,
    settle_confidence,
    update_settle,
)


def _feed(alphas, *, dt_min=5.0, prev=None, **kw):
    est = prev
    for a in alphas:
        est = update_settle(est, alpha=a, dt_min=dt_min, **kw)
    return est


def test_first_sample_not_settled() -> None:
    e = update_settle(None, alpha=0.1, dt_min=5.0)
    assert e is not None
    assert e.mean == 0.1 and e.var == 0.0 and e.minutes == 5.0
    assert e.settled is False


def test_idle_and_missing_hold() -> None:
    e = update_settle(None, alpha=0.1, dt_min=5.0)
    # not learn-active, or missing / non-positive α -> hold the prior by identity
    assert update_settle(e, alpha=0.1, dt_min=5.0, learn_active=False) is e
    assert update_settle(e, alpha=None, dt_min=5.0) is e
    assert update_settle(e, alpha=0.0, dt_min=5.0) is e
    assert update_settle(e, alpha=-0.3, dt_min=5.0) is e


def test_steady_alpha_settles_and_is_confident() -> None:
    # a converged α (steady 0.10) past the 60-min learn-active warm-up
    e = _feed([0.10] * 15, dt_min=5.0)  # 75 min
    assert e is not None
    assert e.minutes == 75.0
    assert e.rel_spread < 1e-9  # no spread -> fully settled
    assert e.settled is True
    assert settle_confidence(e) == 1.0


def test_drifting_alpha_not_settled() -> None:
    # a sign-flipping / non-converged α keeps the spread wide
    e = _feed([0.08, 0.14] * 10, dt_min=5.0)  # 100 min, warmed up but unstable
    assert e is not None
    assert e.minutes >= 60.0
    assert e.rel_spread > 0.04  # above the settle gate
    assert e.settled is False
    assert settle_confidence(e) == 0.0  # spread beyond 2·rel_gate -> zero


def test_confidence_zero_before_warmup() -> None:
    e = _feed([0.10] * 6, dt_min=5.0)  # 30 min < 60-min warm-up
    assert e is not None
    assert e.settled is False
    assert settle_confidence(e) == 0.0


def test_learn_active_window_not_polluted_by_idle() -> None:
    # interleave real learning ticks (0.10) with idle ticks carrying an absurd α;
    # the idle ticks must not fold in, so the mean stays ~0.10 and still settles.
    e = None
    for _ in range(15):
        e = update_settle(e, alpha=0.10, dt_min=5.0)
        e = update_settle(e, alpha=5.0, dt_min=30.0, learn_active=False)
    assert e is not None
    assert 0.09 < e.mean < 0.11  # the 5.0 idle reads never entered the average
    assert e.minutes == 75.0  # only the 15×5 learn-active minutes counted
    assert e.settled is True


def test_roundtrip_restore_conservative() -> None:
    e = _feed([0.10] * 15, dt_min=5.0)
    assert e is not None and e.settled is True
    r = TauSettle.from_dict(e.to_dict())
    assert abs(r.mean - e.mean) < 1e-9
    assert abs(r.minutes - e.minutes) < 1e-9
    assert r.settled is False  # never trust τ straight after a restart
