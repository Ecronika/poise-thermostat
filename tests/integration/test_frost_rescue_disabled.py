"""Review V4: even DISABLED, a zone keeps the unconditional frost/mould floor —
but rescue-only, so a reasonable manual setpoint above the floor is never fought,
and a cool-only device (no frost duty) is left alone. Glue, CI-only.

Mirrors the proven config + helpers of test_entity_actions (ROOM_DATA, no outdoor
/ TRM entities) so the disabled second tick stays socket-free, exactly like the
existing test_disabled_skips_actuator_write.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: True,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}


def _actuator(
    hass: HomeAssistant, *, state: str, sp: float, modes: list[str], room: float = 18.0
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        state,
        {
            "hvac_modes": modes,
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _disable_and_tick(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    coord: Any = entry.runtime_data
    coord.set_enabled(False)
    await coord.async_refresh()
    await hass.async_block_till_done()


async def test_disabled_heat_device_below_floor_gets_frost_rescue(
    hass: HomeAssistant,
) -> None:
    """Disabled zone, heat-capable device below the floor -> floor written and
    nudged to heat (the README 'unconditional safety floor' promise)."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, state="off", sp=5.0, modes=["heat", "off"])
    entry = await _setup(hass)
    set_temp.clear()
    set_mode.clear()

    await _disable_and_tick(hass, entry)

    modes = [c.data.get("hvac_mode") for c in set_mode]
    assert set_temp, "disabled zone must still rescue a device below the frost floor"
    assert all(c.data.get("temperature") >= 7.0 for c in set_temp)
    assert "heat" in modes, "frost rescue must nudge the device into heat"


async def test_disabled_reasonable_setpoint_not_fought(hass: HomeAssistant) -> None:
    """Disabled zone with a sane manual setpoint above the floor -> hands-off."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, state="heat", sp=19.0, modes=["heat", "off"])
    entry = await _setup(hass)
    set_temp.clear()

    await _disable_and_tick(hass, entry)

    assert not set_temp, "a reasonable setpoint above the floor must not be overwritten"


async def test_disabled_cool_only_device_left_alone(hass: HomeAssistant) -> None:
    """Disabled zone, cool-only device below the floor -> no frost duty, no write."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _actuator(hass, state="off", sp=5.0, modes=["cool", "off"])
    entry = await _setup(hass)
    set_temp.clear()

    await _disable_and_tick(hass, entry)

    assert not set_temp, "a cool-only device has no frost duty when disabled"
