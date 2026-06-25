"""Config-flow integration tests (review E4): menu, room, system, dedup."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)

ROOM_INPUT: dict[str, Any] = {
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


async def test_user_menu_then_room_creates_entry(hass: HomeAssistant) -> None:
    """user -> menu -> room form -> CREATE_ENTRY with actuator as unique_id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "room"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "room"

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], ROOM_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Room"
    assert result["data"][CONF_ACTUATOR] == "climate.trv"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == "climate.trv"


async def test_duplicate_actuator_aborts(hass: HomeAssistant) -> None:
    """A second room on the same actuator is rejected (one entry per device)."""
    MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Existing"
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "room"}
    )
    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], ROOM_INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_system_hub_entry_is_tagged(hass: HomeAssistant) -> None:
    """The system branch creates the singleton hub entry (ENTRY_TYPE_SYSTEM)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "system"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "system"

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENTRY_TYPE] == ENTRY_TYPE_SYSTEM
