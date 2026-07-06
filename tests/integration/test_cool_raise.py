"""ADR-0051 S1: the live heat-day cool-raise write (glue, CI-only).

With the ASR cap raised to 30 (employer opt-in) and a hot outdoor, a cool-capable
AC must get a cooling setpoint lifted above the fixed EN 26 — but rate-limited and
clamped under the EN adaptive upper. A heat-only device would never see this
(decide_mode gates cool on can_cool). This secures the config->write wiring the
pure rate_limit/adaptive_cool_setpoint tests cannot reach.
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
    CONF_ADAPTIVE_COOL,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COOL_HARD_CAP,
    CONF_NAME,
    CONF_OUTDOOR_SENSOR,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
)


async def test_cool_raise_writes_lifted_setpoint(hass: HomeAssistant) -> None:
    """Cap 30 + hot outdoor -> written cooling setpoint lifted above the base 26."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set(
        "sensor.room_temp",
        "29",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("sensor.outdoor", "35", {"device_class": "temperature"})
    # a controlled running mean so the EN adaptive upper is deterministic
    hass.states.async_set("sensor.trm", "24", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "heat", "off"],
            "temperature": 20.0,
            "current_temperature": 29.0,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 32,
        },
    )
    data: dict[str, Any] = {
        CONF_NAME: "Office",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_TRM_SENSOR: "sensor.trm",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        # adaptive_cool now defaults to "auto" (ADR-0008 tri-state); this test
        # targets the FIXED-band heat-day raise, so pin it off explicitly.
        CONF_ADAPTIVE_COOL: "off",
        CONF_COOL_HARD_CAP: 30.0,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=data, title="Office"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert set_temp, "coordinator did not write a cooling setpoint"
    written = set_temp[-1].data["temperature"]
    # lifted above the fixed EN cool (26) toward outdoor-7=28, capped <= EN upper
    assert 26.0 < written <= 30.5
