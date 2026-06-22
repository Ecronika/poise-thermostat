from __future__ import annotations

from custom_components.poise.contracts import ActuatorPath
from custom_components.poise.devices.capability import (
    DeviceCapabilities,
    capabilities_from_numbers,
    classify_number_entity,
    select_path,
)


def test_classify_valve_patterns() -> None:
    assert classify_number_entity("number.trv_valve_position") == "valve"
    assert classify_number_entity("number.x_pi_heating_demand") == "valve"


def test_valve_opening_degree_is_excluded() -> None:
    # max-opening limit, NOT live position -> must not be treated as a valve
    assert classify_number_entity("number.trvzb_valve_opening_degree") == "max_limit"


def test_classify_calibration_and_unknown() -> None:
    assert (
        classify_number_entity("number.local_temperature_calibration") == "calibration"
    )
    assert classify_number_entity("number.battery_level_pct") == "valve"  # 'level'
    assert classify_number_entity("number.unrelated") is None


def test_select_path_prefers_valve() -> None:
    caps = capabilities_from_numbers(["number.trv_valve_position"])
    assert select_path(caps) is ActuatorPath.TPI_VALVE


def test_valve_opening_degree_only_falls_through_to_setpoint() -> None:
    caps = capabilities_from_numbers(["number.trvzb_valve_opening_degree"])
    assert not caps.writable_valve
    assert select_path(caps) is ActuatorPath.PI_SETPOINT


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
