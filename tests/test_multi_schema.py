from __future__ import annotations

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CLIMATE_MODE,
    CONF_NAME,
    CONF_TEMP_SENSOR,
)
from custom_components.poise.multi.discovery import (
    EntitySnapshot,
    transient_zone_device,
)
from custom_components.poise.multi.model import (
    Axis,
    DeviceCapability,
    Direction,
    ZoneDevice,
)
from custom_components.poise.multi.schema import (
    FIELD_AIR_MOVEMENT_CREDIT,
    FIELD_ARBITRATION,
    FIELD_COP_BALANCE,
    FIELD_HUMIDITY_CONTROL,
    build_options_fields,
    build_setup_fields,
    field_keys,
)


def _trv() -> ZoneDevice:
    return transient_zone_device(
        EntitySnapshot("climate.trv", "climate", hvac_modes=("heat", "off"))
    )


def _ac() -> ZoneDevice:
    return transient_zone_device(
        EntitySnapshot("climate.ac", "climate", hvac_modes=("heat", "cool", "off"))
    )


def _fan() -> ZoneDevice:
    return ZoneDevice(
        "fan.box",
        "FanAdapter",
        (DeviceCapability(Axis.AIR_MOVEMENT, Direction.RECIRCULATE),),
    )


def test_setup_is_exactly_three_fields() -> None:
    assert field_keys(build_setup_fields()) == {
        CONF_NAME,
        CONF_TEMP_SENSOR,
        CONF_ACTUATOR,
    }


def test_single_trv_options_hide_advanced_axes() -> None:
    keys = field_keys(build_options_fields((_trv(),)))
    assert FIELD_ARBITRATION not in keys
    assert FIELD_HUMIDITY_CONTROL not in keys
    assert FIELD_AIR_MOVEMENT_CREDIT not in keys
    assert CONF_CLIMATE_MODE not in keys  # heat-only -> no cool/mode field


def test_cool_capable_shows_climate_mode() -> None:
    assert CONF_CLIMATE_MODE in field_keys(build_options_fields((_ac(),)))


def test_two_thermal_sources_unlock_arbitration() -> None:
    keys = field_keys(build_options_fields((_trv(), _ac())))
    assert FIELD_ARBITRATION in keys
    assert FIELD_COP_BALANCE not in keys  # advanced-gated
    keys_adv = field_keys(build_options_fields((_trv(), _ac()), advanced=True))
    assert FIELD_COP_BALANCE in keys_adv


def test_air_movement_credit_needs_presence() -> None:
    assert FIELD_AIR_MOVEMENT_CREDIT not in field_keys(
        build_options_fields((_ac(), _fan()))
    )
    assert FIELD_AIR_MOVEMENT_CREDIT in field_keys(
        build_options_fields((_ac(), _fan()), has_presence=True)
    )


def test_humidity_axis_needs_sensor_and_actuator() -> None:
    only_sensor = field_keys(build_options_fields((_ac(),), has_humidity_sensor=True))
    assert FIELD_HUMIDITY_CONTROL not in only_sensor
    both = field_keys(
        build_options_fields(
            (_ac(),), has_humidity_sensor=True, has_humidity_actuator=True
        )
    )
    assert FIELD_HUMIDITY_CONTROL in both
