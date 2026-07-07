"""Config-flow integration tests (review E4): menu, room, system, dedup."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_COOL_MIN_OUTDOOR,
    CONF_ENTRY_TYPE,
    CONF_MRT_SENSOR,
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

# Slim onboarding submit (Step 3): the essentials + the collapsed accuracy
# section; everything else defaults from const. Reconfigure still uses ROOM_INPUT.
ROOM_SETUP: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    "accuracy": {CONF_CATEGORY: "II", CONF_COMFORT_BASE: 21.0},
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
            result["flow_id"], ROOM_SETUP
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
            result["flow_id"], ROOM_SETUP
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "actuator_in_use"
    assert result["description_placeholders"] == {"zone": "Existing"}


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


async def test_reconfigure_updates_room(hass: HomeAssistant) -> None:
    """Reconfigure edits an existing room entry in place (learning preserved)."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ROOM_INPUT, CONF_COMFORT_BASE: 22.5}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # V2 (ADR-0007): the reconfigure reload migrates the still-V1 entry, so tuning
    # moves into options; the effective config the coordinator reads carries it.
    assert entry.version == 2
    assert {**entry.data, **entry.options}[CONF_COMFORT_BASE] == 22.5


async def test_reconfigure_overrides_stale_option(hass: HomeAssistant) -> None:
    """A shared field changed via reconfigure takes effect even if it was last set
    via the options flow — the stale option must not shadow it (review V7 b/c)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_INPUT,
        options={CONF_CLIMATE_MODE: "cool_only", CONF_COOL_MIN_OUTDOOR: 10.0},
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ROOM_INPUT, CONF_CLIMATE_MODE: "heat_only"}
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    # V2 (ADR-0007): the migrating reload moves tuning into options. The
    # reconfigured value wins over the stale option (cool_only is gone) and the
    # options-only field survives.
    assert entry.options[CONF_CLIMATE_MODE] == "heat_only"  # was stale cool_only
    assert {**entry.data, **entry.options}[CONF_CLIMATE_MODE] == "heat_only"
    assert entry.options[CONF_COOL_MIN_OUTDOOR] == 10.0  # options-only survives


async def test_reconfigure_full_replace_drops_cleared_field(
    hass: HomeAssistant,
) -> None:
    """Reconfigure fully replaces data, so an optional field omitted on re-submit
    is really removed, not merged over (review V7 a)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data={**ROOM_INPUT, CONF_MRT_SENSOR: "sensor.mrt"},
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], dict(ROOM_INPUT)
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert CONF_MRT_SENSOR not in entry.data


async def test_sensor_on_actuator_blocks_and_filters_own(
    hass: HomeAssistant,
) -> None:
    """The room sensor may not be the thermostat's built-in sensor (same device),
    and Poise's own entities are kept out of the pickers (no self-wiring)."""
    ent_reg = er.async_get(hass)
    # a Poise-owned entity must be excluded from the pickers
    ent_reg.async_get_or_create(
        "climate", DOMAIN, "own-zone", suggested_object_id="poise_own"
    )
    # a thermostat whose built-in temperature sensor sits on the same device
    dev_reg = dr.async_get(hass)
    donor = MockConfigEntry(domain="demo")
    donor.add_to_hass(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=donor.entry_id, identifiers={("demo", "trv")}
    )
    ent_reg.async_get_or_create(
        "sensor",
        "demo",
        "trv-temp",
        device_id=device.id,
        suggested_object_id="trv_temp",
        original_device_class="temperature",
    )
    ent_reg.async_get_or_create(
        "climate", "demo", "trv-act", device_id=device.id, suggested_object_id="trv_act"
    )
    hass.states.async_set("sensor.trv_temp", "21", {"device_class": "temperature"})
    hass.states.async_set("climate.trv_act", "heat", {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "room"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Bad",
            CONF_TEMP_SENSOR: "sensor.trv_temp",
            CONF_ACTUATOR: "climate.trv_act",
            "accuracy": {},
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_TEMP_SENSOR: "sensor_on_actuator"}


async def test_options_comfort_window_pair_error(hass: HomeAssistant) -> None:
    """A comfort window with only one bound set is rejected (both or neither)."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "comfort": {
                    CONF_CATEGORY: ROOM_INPUT[CONF_CATEGORY],
                    CONF_COMFORT_BASE: ROOM_INPUT[CONF_COMFORT_BASE],
                    CONF_CLIMATE_MODE: ROOM_INPUT[CONF_CLIMATE_MODE],
                    CONF_COMFORT_WEIGHT: ROOM_INPUT[CONF_COMFORT_WEIGHT],
                },
                "schedule": {
                    CONF_SETBACK_DELTA: ROOM_INPUT[CONF_SETBACK_DELTA],
                    CONF_OPTIMAL_START: ROOM_INPUT[CONF_OPTIMAL_START],
                    CONF_COMFORT_START: "22:00:00",
                },
                "heat_cool": {},
                "presence": {},
                "advanced": {},
                "energy": {},
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "comfort_window_pair"}
