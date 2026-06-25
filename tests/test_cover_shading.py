"""Tests for predictive solar shading (ADR-0043)."""

from __future__ import annotations

from custom_components.poise.control.cover_shading import (
    CoverShadeConfig,
    cover_user_override,
    orientation_factor,
    predict_peak_operative,
    shading_target_position,
)

CFG = CoverShadeConfig()


def test_orientation_zero_when_sun_below_horizon_or_behind() -> None:
    assert orientation_factor(-5.0, 180.0, 180.0) == 0.0  # below horizon
    # sun due north (0°), surface faces south (180°) -> behind -> 0
    assert orientation_factor(30.0, 0.0, 180.0) == 0.0


def test_orientation_positive_when_sun_on_surface() -> None:
    # sun facing the surface (same azimuth), 30° elevation -> positive factor
    f = orientation_factor(30.0, 180.0, 180.0)
    assert 0.0 < f <= 1.0


def test_predict_peak_confident_warms_toward_solar_equilibrium() -> None:
    # t_eq = t_out + beta_s*q/alpha = 24 + 3*0.5/0.2 = 31.5; peak rises toward it.
    q = [0.5] * 96  # 8 h of strong sun at 5-min steps
    peak = predict_peak_operative(
        26.0, 24.0, q, alpha=0.2, beta_s=3.0, dt_h=5 / 60, confident=True
    )
    assert 28.0 < peak <= 31.5


def test_predict_peak_linear_fallback_when_not_confident() -> None:
    peak = predict_peak_operative(
        26.0, 24.0, [0.0, 0.4, 0.2], alpha=0.2, beta_s=3.0, dt_h=5 / 60, confident=False
    )
    assert peak == 26.0 + 3.0 * 0.4 * 1.0  # t_now + linear_beta_s*max(q)*lookahead


def test_decision_deploys_graded_then_retracts_with_hysteresis() -> None:
    # peak 4 K over the upper edge -> deploy a graded position.
    pos, reason = shading_target_position(
        peak=29.0, t_upper=25.0, current_position=0, oriented_q=0.5
    )
    assert reason == "deploy" and pos > 0
    # peak only 1.2 K over (between retract 1.0 and deploy 1.5) -> hold.
    pos2, r2 = shading_target_position(
        peak=26.2, t_upper=25.0, current_position=pos, oriented_q=0.5
    )
    assert r2 == "hold" and pos2 == pos
    # peak below the retract band -> fully open.
    pos3, r3 = shading_target_position(
        peak=25.5, t_upper=25.0, current_position=pos, oriented_q=0.5
    )
    assert r3 == "retract" and pos3 == 0


def test_decision_no_shade_when_sun_not_on_surface() -> None:
    pos, reason = shading_target_position(
        peak=40.0, t_upper=25.0, current_position=0, oriented_q=0.0
    )
    assert pos == 0 and reason == "no_sun"


def test_manual_override_detected_after_settle() -> None:
    # actual drifted 40% from commanded, 120 s after the command -> override.
    assert cover_user_override(60.0, 100.0, 120.0) is True
    # same drift but only 30 s after command (within settle) -> not yet trusted.
    assert cover_user_override(60.0, 100.0, 30.0) is False
