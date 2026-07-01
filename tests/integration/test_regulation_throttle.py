"""ADR-0052 §4: the self-regulating nudge throttle must not block a device's
*first* setpoint write (last-write stamp is None -> never throttled), and a
heat-only TRV (regulation_period_s == 0) is never throttled at all. The
per-period suppression itself is unit-tested in test_dynamics (pure). CI-only.
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


async def test_self_regulating_ac_writes_first_setpoint(hass: HomeAssistant) -> None:
    """A cool-capable AC (fast_air, self-regulating) still writes on the first
    tick — the throttle never blocks the initial nudge."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    # a hot room so the AC actively cools -> a setpoint is written
    hass.states.async_set("sensor.room_temp", "27", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "30", {"device_class": "temperature"})
    hass.states.async_set("sensor.trm", "26", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "heat", "off"],
            "temperature": 24.0,
            "current_temperature": 27.0,
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

    assert set_temp, "self-regulating AC did not write its first setpoint"
