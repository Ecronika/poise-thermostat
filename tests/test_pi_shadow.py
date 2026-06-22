"""Tests for the live shadow PI-compensated setpoint (ADR-0037)."""

from __future__ import annotations

from custom_components.poise.control.pi import PiCompensator
from custom_components.poise.control.pi_shadow import evaluate_pi_shadow


def test_inactive_on_valve_device() -> None:
    s = evaluate_pi_shadow(
        PiCompensator(), applies=False, target=21.0, room=18.0, external=18.0
    )
    assert s.active is False and s.setpoint is None and s.offset is None


def test_active_pushes_setpoint_above_target_when_cold() -> None:
    s = evaluate_pi_shadow(
        PiCompensator(), applies=True, target=21.0, room=18.0, external=18.0
    )
    assert s.active is True
    assert s.setpoint is not None and s.setpoint > 21.0  # cold room -> push up
    assert s.offset is not None and s.offset > 0.0


def test_offset_clamped_to_bounds() -> None:
    pi = PiCompensator()
    for _ in range(2000):  # wind the integral well past saturation
        s = evaluate_pi_shadow(pi, applies=True, target=21.0, room=15.0, external=15.0)
    assert s.offset is not None and s.offset <= 2.0  # offset_max
