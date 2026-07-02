"""Tests for the pure reconfigure reconcile helper (review V7)."""

from __future__ import annotations

from custom_components.poise.config_reconcile import reconfigure_options


def test_reconfigure_drops_shadowing_option() -> None:
    # a shared field set via the options flow is dropped from options on
    # reconfigure so it no longer shadows the new data value the form just set.
    kept = reconfigure_options(
        {"climate_mode": "heat_only", "temp_sensor": "sensor.x"},
        {"climate_mode": "cool_only", "cool_min_outdoor": 10.0},
    )
    assert kept == {"cool_min_outdoor": 10.0}


def test_reconfigure_keeps_options_only_keys() -> None:
    # a key the reconfigure form does not own stays in options
    assert reconfigure_options({"a": 9}, {"a": 1, "b": 2}) == {"b": 2}


def test_reconfigure_empty() -> None:
    assert reconfigure_options({}, {}) == {}
    assert reconfigure_options({"a": 1}, {}) == {}
