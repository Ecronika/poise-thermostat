"""Tests for the override/preset model with timed auto-revert (ADR-0042)."""

from __future__ import annotations

from custom_components.poise.control.override import (
    OverrideConfig,
    OverrideMode,
    manual_override_expired,
    mode_comfort_base,
)

CFG = OverrideConfig()


def test_modes_offset_the_comfort_base() -> None:
    assert mode_comfort_base(OverrideMode.COMFORT, 21.0) == 21.0
    assert mode_comfort_base(OverrideMode.NONE, 21.0) == 21.0
    assert mode_comfort_base(OverrideMode.ECO, 21.0) == 21.0 - CFG.eco_offset
    assert mode_comfort_base(OverrideMode.BOOST, 21.0) == 21.0 + CFG.boost_offset
    assert mode_comfort_base(OverrideMode.AWAY, 21.0) == 21.0 - CFG.away_offset


def test_modes_are_offsets_not_free_temps() -> None:
    # A higher user base shifts every mode up by the same offset (norm-anchored).
    eco21 = mode_comfort_base(OverrideMode.ECO, 21.0)
    eco24 = mode_comfort_base(OverrideMode.ECO, 24.0)
    assert eco24 - eco21 == 3.0


def test_manual_override_auto_revert_window() -> None:
    set_at = 1000.0
    # Just before the 2 h window -> still active.
    assert manual_override_expired(set_at, set_at + 2 * 3600 - 1, CFG) is False
    # At/after the window -> expired (reverts).
    assert manual_override_expired(set_at, set_at + 2 * 3600, CFG) is True
