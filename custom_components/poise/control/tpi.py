"""TPI valve control with learned coefficients (ADR-0004).

Duty cycle:  duty = coef_int·(target-room) + coef_ext·(target-outdoor), clamped.
Seed from the EKF model (physical, cold-start safe), then nudge online via a
ratio-error EMA (Versatile-style) with hard clamps and a per-step change guard.
"""

from __future__ import annotations

COEF_INT_BOUNDS = (0.15, 1.2)
COEF_EXT_BOUNDS = (0.002, 0.06)
_MAX_RATIO = 1.5  # max +-50 % change per learning step
_PROPORTIONAL_RATIO = 50.0  # coef_int ~ 50x the steady-state coef_ext


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def tpi_duty(
    coef_int: float, coef_ext: float, target: float, room: float, outdoor: float
) -> float:
    """Proportional + outdoor-feedforward duty in [0, 1]."""
    duty = coef_int * (target - room) + coef_ext * (target - outdoor)
    return _clamp(duty, 0.0, 1.0)


def seed_from_model(alpha: float, beta_h: float) -> tuple[float, float]:
    """Physical seed: steady-state balance duty ~ (alpha/beta_h)·(target-outdoor)."""
    coef_ext = _clamp(alpha / beta_h, *COEF_EXT_BOUNDS)
    coef_int = _clamp(_PROPORTIONAL_RATIO * coef_ext, *COEF_INT_BOUNDS)
    return coef_int, coef_ext


class TpiLearner:
    """Online nudge of the TPI coefficients from observed vs expected rise.

    STAGED, not yet wired (review M5): online coefficient adaptation is a proven
    best-of feature (Versatile Thermostat ships an opt-in Auto-TPI learner), but
    it can only learn once Poise actually *drives* the valve — which is the
    cold-season-gated active-TPI step (ADR-0036). Built + unit-tested now; it is
    deliberately not instantiated until active valve writing lands, at which
    point it becomes the opt-in Auto-TPI manager (VTherm pattern: learn ->
    update coefficients -> stateless per-cycle duty law consumes them).
    """

    """Online nudging of ``coef_int`` from observed vs expected temperature rise."""

    def __init__(self, coef_int: float, coef_ext: float, alpha: float = 0.15) -> None:
        self.coef_int = _clamp(coef_int, *COEF_INT_BOUNDS)
        self.coef_ext = _clamp(coef_ext, *COEF_EXT_BOUNDS)
        self._alpha = alpha

    def update(self, expected_rise: float, actual_rise: float) -> None:
        """Nudge ``coef_int`` toward correcting the rise error (ratio-error EMA)."""
        if actual_rise <= 0.0 or expected_rise <= 0.0:
            return  # not observable — skip (mode/learn gate)
        ratio = _clamp(expected_rise / actual_rise, 1.0 / _MAX_RATIO, _MAX_RATIO)
        target = _clamp(self.coef_int * ratio, *COEF_INT_BOUNDS)
        self.coef_int = (1.0 - self._alpha) * self.coef_int + self._alpha * target
