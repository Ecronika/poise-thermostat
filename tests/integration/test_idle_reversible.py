"""Finding 1 (v0.108.0): a reversible AC idling in the dead-band is kept in its
current cool mode with a cool-edge hold — not flipped to heat each cycle
(compressor/reversing-valve thrash) and not cooled toward the heat hold. A
heat-only TRV is unchanged (glue, CI-only).
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
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
)


def _data(actuator: str) -> dict[str, Any]:
    return {
        CONF_NAME: "Zone",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: actuator,
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_TRM_SENSOR: "sensor.trm",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: True,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
    }


def _sensors(hass: HomeAssistant) -> None:
    # room clearly inside the dead-band (heat_sp ~20, cool_sp ~24) -> idle
    hass.states.async_set("sensor.room_temp", "21.5", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "18", {"device_class": "temperature"})
    hass.states.async_set("sensor.trm", "20", {"device_class": "temperature"})


async def test_idle_reversible_ac_stays_in_cool(hass: HomeAssistant) -> None:
    """Idle + a reversible AC currently cooling: no heat nudge, cool-edge hold."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    _sensors(hass)
    hass.states.async_set(
        "climate.ac",
        "cool",  # the device is currently cooling
        {
            "hvac_modes": ["cool", "heat", "off"],
            "temperature": 24.0,
            "current_temperature": 21.5,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 32,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=_data("climate.ac"), title="Zone"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # never flipped into heat (no compressor cool->heat thrash)
    assert not [c for c in set_mode if c.data.get("hvac_mode") == "heat"]
    # the idle hold is the cool edge, not the (low) heat hold -> no overcool
    assert set_temp, "expected an idle setpoint write"
    assert set_temp[-1].data["temperature"] > 22.0


async def test_idle_heat_only_trv_unchanged(hass: HomeAssistant) -> None:
    """A heat-only TRV idling is never nudged toward cool (capability gate)."""
    async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    _sensors(hass)
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 21.5,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_data("climate.trv"), title="Zone"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert not [c for c in set_mode if c.data.get("hvac_mode") == "cool"]
