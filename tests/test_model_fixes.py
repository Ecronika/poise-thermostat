from __future__ import annotations

from custom_components.poise.devices.model_fixes import (
    is_low_battery,
    looks_like_adaptive_mode_switch,
    looks_like_fault_alarm,
    looks_like_internal_schedule,
)


def test_low_battery_threshold() -> None:
    assert is_low_battery(10.0) is True
    assert is_low_battery(15.0) is True  # boundary inclusive
    assert is_low_battery(16.0) is False
    assert is_low_battery(None) is False
    assert is_low_battery(50.0, threshold=60.0) is True


def test_internal_schedule_classifier() -> None:
    assert looks_like_internal_schedule("switch.wohnzimmer_trv_schedule") is True
    assert looks_like_internal_schedule("switch.wohnzimmer_trv_child_lock") is False
    assert looks_like_internal_schedule("sensor.foo_schedule") is False  # not a switch


def test_adaptive_mode_switch_classifier() -> None:
    # R1: a device-internal adaptive/smart-temperature loop (doubled regulation)
    # is recognised on both switch. and select. entities, keyed on name tokens.
    assert looks_like_adaptive_mode_switch("switch.trv_smart_temperature_control")
    assert looks_like_adaptive_mode_switch("switch.wohnzimmer_adaptive_mode")
    assert looks_like_adaptive_mode_switch("select.trv_adaptive")
    assert looks_like_adaptive_mode_switch("switch.trv_child_lock") is False
    assert looks_like_adaptive_mode_switch("switch.trv_schedule") is False
    assert looks_like_adaptive_mode_switch("sensor.trv_adaptive") is False  # domain


def test_fault_alarm_classifier() -> None:
    assert looks_like_fault_alarm("binary_sensor.trv_valve_alarm") is True
    assert looks_like_fault_alarm("binary_sensor.trv_problem") is True
    assert looks_like_fault_alarm("binary_sensor.trv_window_open") is False
    assert looks_like_fault_alarm("switch.trv_valve_alarm") is False  # wrong domain


def test_external_temp_number_classifier() -> None:
    from custom_components.poise.devices.model_fixes import (
        looks_like_external_temp_number,
    )

    assert looks_like_external_temp_number(
        "number.wohnzimmer_trv_external_temperature_input", "temperature"
    )
    assert looks_like_external_temp_number("number.trv_external_input")  # no dc
    assert not looks_like_external_temp_number("number.trv_away_preset_temperature")
    assert not looks_like_external_temp_number(
        "sensor.external_temperature"
    )  # wrong domain


def test_external_sensor_select_classifier() -> None:
    from custom_components.poise.devices.model_fixes import is_external_sensor_select

    assert is_external_sensor_select("select.trv_sensor", ["internal", "external"])
    assert not is_external_sensor_select("select.trv_calibrate", ["calibrate"])
    assert not is_external_sensor_select("select.trv_sensor", None)
    assert not is_external_sensor_select(
        "switch.trv_sensor", ["internal", "external"]
    )  # wrong domain
