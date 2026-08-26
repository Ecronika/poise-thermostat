from __future__ import annotations

from custom_components.poise.contracts import ActuatorPath
from custom_components.poise.devices.capability import (
    DeviceCapabilities,
    capabilities_from_numbers,
    classify_number_entity,
    reliable_heat_mode_from,
    select_live_path,
    select_path,
)


def test_classify_valve_patterns() -> None:
    assert classify_number_entity("number.trv_valve_position") == "valve"
    assert classify_number_entity("number.x_pi_heating_demand") == "valve"


def test_valve_opening_degree_is_a_writable_valve() -> None:
    # TRVZB FW v1.1.4+: writable open-position -> usable as TPI duty target
    assert classify_number_entity("number.trvzb_valve_opening_degree") == "valve"
    # closing degree is excluded (writing it breaks the TRVZB running_state)
    assert classify_number_entity("number.trvzb_valve_closing_degree") == "max_limit"


def test_classify_calibration_and_unknown() -> None:
    assert (
        classify_number_entity("number.local_temperature_calibration") == "calibration"
    )
    # F3: a battery-level number must NOT be classified as a writable valve.
    assert classify_number_entity("number.battery_level_pct") is None
    assert classify_number_entity("number.unrelated") is None


def test_select_path_prefers_valve() -> None:
    caps = capabilities_from_numbers(["number.trv_valve_position"])
    assert select_path(caps) is ActuatorPath.TPI_VALVE


def test_trvzb_opening_degree_selects_valve_path() -> None:
    # TRVZB exposes opening + closing degree + calibration -> valve wins
    caps = capabilities_from_numbers(
        [
            "number.trvzb_valve_opening_degree",
            "number.trvzb_valve_closing_degree",
            "number.trvzb_local_temperature_calibration",
        ]
    )
    assert caps.writable_valve
    assert select_path(caps) is ActuatorPath.TPI_VALVE


def test_calibration_path_needs_heat_mode() -> None:
    caps = DeviceCapabilities(writable_calibration=True, reliable_heat_mode=True)
    assert select_path(caps) is ActuatorPath.CALIBRATION
    caps_no_heat = DeviceCapabilities(
        writable_calibration=True, reliable_heat_mode=False
    )
    assert select_path(caps_no_heat) is ActuatorPath.PI_SETPOINT


def test_climate_capability_from_hvac_modes() -> None:
    from custom_components.poise.devices.capability import climate_capability

    assert climate_capability(["heat", "off"]) == (True, False)
    assert climate_capability(["cool", "off"]) == (False, True)
    assert climate_capability(["heat_cool", "heat", "cool", "off"]) == (True, True)
    assert climate_capability(["off"]) == (False, False)
    # a radiator TRV with an internal-schedule "auto" mode must NOT be treated as
    # cool-capable (Sonoff TRVZB finding): auto implies heating only
    assert climate_capability(["off", "auto", "heat"]) == (True, False)
    assert climate_capability(["off", "auto"]) == (True, False)


def test_reliable_heat_mode_requires_literal_heat() -> None:
    # auto-only can heat (can_heat), but cannot be HELD in "heat"
    # (ha/phase_actuate.py: supported = desired in act_modes)
    assert reliable_heat_mode_from(["heat", "off"])
    assert reliable_heat_mode_from(["HEAT", "auto"])
    assert not reliable_heat_mode_from(["auto", "off"])
    assert not reliable_heat_mode_from(["heat_cool", "off"])


def test_live_path_ext_temp_reserved_beats_calibration() -> None:
    caps = DeviceCapabilities(writable_calibration=True, reliable_heat_mode=True)
    assert (
        select_live_path(caps, ext_temp_reserved=True, calibration_enabled=True)
        is ActuatorPath.SETPOINT
    )
    # top precedence rung: ext_temp_reserved beats the valve path too
    valve_caps = DeviceCapabilities(writable_valve=True, reliable_heat_mode=True)
    assert (
        select_live_path(
            valve_caps,
            ext_temp_reserved=True,
            calibration_enabled=True,
            valve_live=True,
        )
        is ActuatorPath.SETPOINT
    )


def test_live_path_calibration_requires_opt_in_and_heat() -> None:
    caps = DeviceCapabilities(writable_calibration=True, reliable_heat_mode=True)
    assert (
        select_live_path(caps, ext_temp_reserved=False, calibration_enabled=False)
        is ActuatorPath.SETPOINT
    )
    assert (
        select_live_path(caps, ext_temp_reserved=False, calibration_enabled=True)
        is ActuatorPath.CALIBRATION
    )
    no_heat = DeviceCapabilities(writable_calibration=True, reliable_heat_mode=False)
    assert (
        select_live_path(no_heat, ext_temp_reserved=False, calibration_enabled=True)
        is ActuatorPath.SETPOINT
    )


def test_live_path_valve_requires_valve_live() -> None:
    caps = DeviceCapabilities(
        writable_valve=True, writable_calibration=True, reliable_heat_mode=True
    )
    assert (
        select_live_path(caps, ext_temp_reserved=False, calibration_enabled=True)
        is ActuatorPath.CALIBRATION
    )
    assert (
        select_live_path(
            caps, ext_temp_reserved=False, calibration_enabled=True, valve_live=True
        )
        is ActuatorPath.TPI_VALVE
    )
    # defensive half of the guard: valve_live=True alone is not enough without
    # a writable valve — falls through to the calibration path
    no_valve = DeviceCapabilities(writable_calibration=True, reliable_heat_mode=True)
    assert (
        select_live_path(
            no_valve,
            ext_temp_reserved=False,
            calibration_enabled=True,
            valve_live=True,
        )
        is ActuatorPath.CALIBRATION
    )


def test_looks_like_valve_steps() -> None:
    from custom_components.poise.devices.model_fixes import looks_like_valve_steps

    assert looks_like_valve_steps("sensor.trvzb_closing_steps") == "closing"
    assert looks_like_valve_steps("sensor.trvzb_idle_steps") == "idle"
    assert looks_like_valve_steps("sensor.trvzb_battery") is None
    assert looks_like_valve_steps("number.trvzb_valve_opening_degree") is None
