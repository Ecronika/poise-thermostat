"""Default-enabled entity surface for a fresh zone (review P2-9 + P1-4b).

A new install should show a *lean* set: the main climate entity, the
window-bypass switch, the three most useful diagnostic sensors (operative
temperature, learning phase, model confidence) and -- since P1-4b -- the manual
hold's expiry timestamp, so the override end-time is visible without the card.
Every other diagnostic sensor is registered but ``disabled_by == INTEGRATION`` so
it stays out of the default dashboard until the user opts in.

CI-only: needs the pytest-homeassistant-custom-component harness (no HA in
the dev sandbox).
"""

from __future__ import annotations

from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
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

# has_entity_name=True + device "Test Room" -> "test_room" slug prefix.
# The sensor suffixes come from the translated entity names:
#   operative_temperature -> "Operative temperature"
#   learning_phase        -> "Learning phase"
#   confidence            -> "Model confidence"
#   override_expires_at   -> "Override expires at"  (P1-4b, enabled by default)
EXPECTED_ENABLED = {
    "climate.test_room",
    "switch.test_room_ignore_open_window_reaction",
    "sensor.test_room_operative_temperature",
    "sensor.test_room_learning_phase",
    "sensor.test_room_model_confidence",
    "sensor.test_room_override_expires_at",
}


def _set_room_and_actuator(hass: HomeAssistant, *, room: float, sp: float) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def test_default_enabled_entities_are_lean(hass: HomeAssistant) -> None:
    """Only climate + bypass + 3 sensors are enabled; the rest are INTEGRATION-off."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_room_and_actuator(hass, room=19.5, sp=18.0)

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(reg, entry.entry_id)

    enabled = {e.entity_id for e in entries if e.disabled_by is None}
    assert enabled == EXPECTED_ENABLED, enabled

    # every remaining (disabled) entity is a diagnostic sensor turned off by us
    disabled = [e for e in entries if e.disabled_by is not None]
    assert disabled, "expected the diagnostic sensors to be registered-but-disabled"
    assert all(e.disabled_by is RegistryEntryDisabler.INTEGRATION for e in disabled), [
        (e.entity_id, e.disabled_by) for e in disabled
    ]

    # representative disabled sensors are registered and INTEGRATION-disabled
    by_unique = {e.unique_id: e for e in entries}
    for key in ("mpc_power", "tick_duration_ms"):
        rep = by_unique[f"{entry.entry_id}_{key}"]
        assert rep.disabled_by is RegistryEntryDisabler.INTEGRATION


async def test_override_expiry_sensor_renders_timestamp(hass: HomeAssistant) -> None:
    """P1-4b: the override-expiry sensor turns the wall-clock epoch the coordinator
    tracks into a timestamp state (and reads ``unknown`` while no hold is active)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_room_and_actuator(hass, room=19.5, sp=18.0)

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data
    eid = "sensor.test_room_override_expires_at"

    # no active hold -> the coordinator carries None -> the sensor is unknown
    assert hass.states.get(eid).state == "unknown"

    # an announced expiry (wall-clock epoch) renders as an ISO timestamp
    expiry = 1_800_000_000.0
    coord.data["override_expires_at"] = expiry
    coord.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == dt_util.utc_from_timestamp(expiry).isoformat()
