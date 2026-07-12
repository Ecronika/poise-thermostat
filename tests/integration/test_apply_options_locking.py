"""Review F14: ``async_apply_options`` takes the same lock a tick holds
(``_async_update_data``) across its field mutations, so an options submit
landing mid-tick cannot observe (or leave behind) a torn mix of old/new
tuning. The one thing this MUST NOT do is hold that lock across the trailing
``await self.async_request_refresh()`` -- ``asyncio.Lock`` is not reentrant,
and ``async_request_refresh`` itself awaits ``_async_update_data``, which
acquires the very same lock. Holding it there would deadlock every options
submit permanently.

This is a safety-net regression test for the fix's own correctness (a
mis-placed lock is the failure mode, not the absence of any lock at all --
the pre-fix code raced instead of deadlocking, which is not itself easy to
observe deterministically). It asserts the concurrent-tick scenario the fix
is meant to serialize completes promptly, catching a regression where a
future edit widens the locked region to include the refresh call.
"""

from __future__ import annotations

import asyncio
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


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set(
        "sensor.room_temp",
        "18.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 19.0,
            "current_temperature": 18.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_apply_options_concurrent_with_a_tick_does_not_deadlock(
    hass: HomeAssistant,
) -> None:
    entry = await _setup(hass)
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data

    # a tick and an options-apply racing each other must both complete; the
    # lock only serializes the apply's own field mutations against a tick, it
    # must never leave either call hanging on the other.
    await asyncio.wait_for(
        asyncio.gather(
            coord.async_refresh(),
            coord.async_apply_options(entry),
        ),
        timeout=5.0,
    )
    await hass.async_block_till_done()
    assert coord.last_update_success is True
