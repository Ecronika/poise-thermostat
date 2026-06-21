"""Tests for capability-aware HVAC-mode mapping (review P2)."""

from __future__ import annotations

from custom_components.poise.devices.hvac_modes import (
    available_hvac_modes,
    climate_mode_for_hvac,
    current_hvac_mode,
)


def test_heat_only_is_unchanged() -> None:
    assert available_hvac_modes(True, False) == ("heat", "off")


def test_heat_and_cool_adds_cool() -> None:
    assert available_hvac_modes(True, True) == ("heat", "cool", "off")


def test_cool_only() -> None:
    assert available_hvac_modes(False, True) == ("cool", "off")


def test_current_mode_off_when_disabled() -> None:
    assert current_hvac_mode(False, "auto", True, True) == "off"


def test_current_mode_heat_default() -> None:
    assert current_hvac_mode(True, "auto", True, False) == "heat"


def test_current_mode_cool_when_selected_and_capable() -> None:
    assert current_hvac_mode(True, "cool", True, True) == "cool"
    # cool requested but device can't cool -> falls back to heat
    assert current_hvac_mode(True, "cool", True, False) == "heat"


def test_climate_mode_mapping() -> None:
    assert climate_mode_for_hvac("heat") == "heat"
    assert climate_mode_for_hvac("cool") == "cool"
    assert climate_mode_for_hvac("off") == "auto"


def test_current_mode_cool_only_device() -> None:
    assert current_hvac_mode(True, "auto", False, True) == "cool"


def test_current_mode_off_when_no_capability() -> None:
    assert current_hvac_mode(True, "auto", False, False) == "off"
