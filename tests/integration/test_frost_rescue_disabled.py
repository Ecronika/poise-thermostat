"""Review V4: even DISABLED, a zone keeps the unconditional frost/mould floor —
but rescue-only, so a reasonable manual setpoint above the floor is never fought,
and a cool-only device (no frost duty) is left alone. Glue, CI-only.

Mirrors the proven config + helpers of test_entity_actions (ROOM_DATA, no outdoor
/ TRM entities, ``before``-count assertions) so the disabled second tick behaves
exactly like the passing test_disabled_skips_actuator_write.
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
    """Disabled zone, heat-capable device off/below the floor -> the frost floor is
    still written and the device nudged to heat (README safety-floor promise)."""
    _actuator(hass, state="off", sp=5.0, modes=["heat", "off"])
    entry = await _setup(hass)
    # Mock the climate services AFTER setup: forwarding to the climate platform
    # re-registers the real set_temperature/set_hvac_mode handlers, which would
    # clobber a pre-setup mock, so the rescue write would be dispatched to the
    # real (no-op for a bare mock state) handler and never observed. Mocking here
    # captures the disabled-tick writes (harness finding 2026-07-02).
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data
    before_t, before_m = len(set_temp), len(set_mode)

    await _disable_and_tick(hass, entry)

    new_temps = [c.data.get("temperature") for c in set_temp[before_t:]]
    new_modes = [c.data.get("hvac_mode") for c in set_mode[before_m:]]
    _aid = coord._actuator
    _act = hass.states.get(_aid)
    _d = coord.data or {}
    assert new_temps, (
        f"no rescue: actuator={_aid!r} state={_act.state if _act else 'NONE'} "
        f"temp={_act.attributes.get('temperature') if _act else None} "
        f"last_ok={coord.last_update_success} mode={_d.get('mode')} nudges={new_modes}"
    )
    assert all(t >= 7.0 for t in new_temps)
    assert "heat" in new_modes


async def test_disabled_reasonable_setpoint_not_fought(hass: HomeAssistant) -> None:
    """Disabled zone with a sane manual setpoint above the floor -> hands-off."""
    _actuator(hass, state="heat", sp=19.0, modes=["heat", "off"])
    entry = await _setup(hass)
    set_temp = async_mock_service(hass, "climate", "set_temperature")  # after setup
    async_mock_service(hass, "climate", "set_hvac_mode")
    before_t = len(set_temp)

    await _disable_and_tick(hass, entry)

    assert len(set_temp) == before_t, "a reasonable setpoint above the floor is kept"


async def test_disabled_cool_only_device_left_alone(hass: HomeAssistant) -> None:
    """Disabled zone, cool-only device below the floor -> no frost duty, no write."""
    _actuator(hass, state="off", sp=5.0, modes=["cool", "off"])
    entry = await _setup(hass)
    set_temp = async_mock_service(hass, "climate", "set_temperature")  # after setup
    async_mock_service(hass, "climate", "set_hvac_mode")
    before_t = len(set_temp)

    await _disable_and_tick(hass, entry)

    assert len(set_temp) == before_t, "a cool-only device has no frost duty"
