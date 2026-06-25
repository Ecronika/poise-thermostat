"""Tests for manual-override boundary validation (review C2/Ü2)."""

from __future__ import annotations

from custom_components.poise.const import DEVICE_MAX_C, FROST_FLOOR_C
from custom_components.poise.control.tick_resolve import sanitize_override


def test_sanitize_override_rejects_non_finite() -> None:
    assert sanitize_override(None, FROST_FLOOR_C, DEVICE_MAX_C) is None
    assert sanitize_override(float("nan"), FROST_FLOOR_C, DEVICE_MAX_C) is None
    assert sanitize_override(float("inf"), FROST_FLOOR_C, DEVICE_MAX_C) is None


def test_sanitize_override_clamps_to_range() -> None:
    assert sanitize_override(21.5, FROST_FLOOR_C, DEVICE_MAX_C) == 21.5
    assert sanitize_override(99.0, FROST_FLOOR_C, DEVICE_MAX_C) == DEVICE_MAX_C
    assert sanitize_override(-5.0, FROST_FLOOR_C, DEVICE_MAX_C) == FROST_FLOOR_C
