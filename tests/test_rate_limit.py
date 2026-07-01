"""ADR-0051 §4 setpoint rate-limit (anti-churn, pure)."""

from __future__ import annotations

from custom_components.poise.comfort.thermal_shock import rate_limit


def test_first_sample_no_limit() -> None:
    assert rate_limit(None, 28.0, 0.5) == 28.0


def test_steps_up_by_at_most_max() -> None:
    assert rate_limit(26.0, 28.0, 0.5) == 26.5


def test_steps_down_by_at_most_max() -> None:
    assert rate_limit(28.0, 26.0, 0.5) == 27.5


def test_reaches_target_within_step() -> None:
    assert rate_limit(26.0, 26.3, 0.5) == 26.3
    assert rate_limit(28.0, 27.8, 0.5) == 27.8


def test_zero_max_step_passthrough() -> None:
    assert rate_limit(26.0, 30.0, 0.0) == 30.0
