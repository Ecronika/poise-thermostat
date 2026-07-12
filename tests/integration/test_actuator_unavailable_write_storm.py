"""Review F2 regression: an actuator that goes truly offline (state ==
"unavailable", not a removed entity) must raise the ``actuator_unavailable``
repair issue and must NOT be written to every tick.

Previously ``_emit_health_issues`` only checked ``states.get(...) is None``
(a removed/never-registered entity), which missed the common real-world case
of a device that dropped off Zigbee/MQTT but keeps a registered ``unavailable``
State object -- no issue ever fired. Separately, ``should_write()`` treats an
unknown actuator setpoint (``actual is None``, which ``_num_attr`` returns for
an unavailable state) as "always write", so Poise dispatched
``climate.set_temperature`` into the dead device on every 60 s tick.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
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


async def test_unavailable_actuator_raises_issue_and_is_not_spammed(
    hass: HomeAssistant,
) -> None:
    entry = await _setup(hass)
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    coord: Any = entry.runtime_data

    # the device drops off the network: state flips to "unavailable" (attributes
    # typically clear too, mirroring a real Zigbee/MQTT loss).
    hass.states.async_set("climate.trv", "unavailable", {})

    for _ in range(3):
        await coord.async_refresh()
        await hass.async_block_till_done()

    issue_id = f"actuator_unavailable_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    assert len(set_temp) == 0, (
        f"a dead actuator must not be written to: {[c.data for c in set_temp]}"
    )

    # recovery: the issue clears and control resumes.
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
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
