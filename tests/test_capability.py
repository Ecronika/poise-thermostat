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


def test_valve_opening_degree_is_a_writable_valve() -> None:
    # TRVZB FW v1.1.4+: writable open-position -> usable as TPI duty target
    assert classify_number_entity("number.trvzb_valve_opening_degree") == "valve"
    # closing degree is excluded (writing it breaks the TRVZB running_state)
    assert classify_number_entity("number.trvzb_valve_closing_degree") == "max_limit"


def test_classify_calibration_and_unknown() -> None:
    assert (
        classify_number_entity("number.local_temperature_calibration") == "calibration"
    )
    assert classify_number_entity("number.battery_level_pct") == "valve"  # 'level'
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
