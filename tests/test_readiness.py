"""Tests for the ADR-0069 control-readiness predicates (pure)."""

from __future__ import annotations

from custom_components.poise.comfort.readiness import (
    pmv_control_ready,
    presence_control_ready,
    room_present,
)


def test_pmv_control_ready_requires_real_rh_and_valid_domain() -> None:
    # Without a real RH sensor value the shadow computes PMV on an assumed
    # 50 % — diagnostically fine, but never a basis for a live setpoint shift.
    assert pmv_control_ready(rh=None, pmv_valid=True) is False
    # A real RH does not rescue an out-of-domain PMV (bedroom met 0.7).
    assert pmv_control_ready(rh=48.0, pmv_valid=False) is False
    assert pmv_control_ready(rh=48.0, pmv_valid=True) is True


def test_presence_control_ready_is_signal_availability_not_occupancy() -> None:
    # Nothing configured -> not ready (the thermal fail-safe "assume present"
    # must never enable an elevated fan stage).
    assert presence_control_ready(()) is False
    # Configured but unresolved (dead tracker) -> not ready.
    assert presence_control_ready((None,)) is False
    # A resolvable "nobody in the room" IS ready — readiness is not occupancy.
    assert presence_control_ready((False,)) is True
    assert presence_control_ready((True, None)) is True


def test_room_present_is_confirmed_occupancy_only() -> None:
    # Only a confirmed present resolves True — None (fail-safe lane) does not.
    assert room_present((True,)) is True
    assert room_present((False,)) is False
    assert room_present((None,)) is False
    assert room_present(()) is False
    assert room_present((False, True)) is True
