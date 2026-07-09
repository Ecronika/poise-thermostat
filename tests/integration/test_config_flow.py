"""Config-flow integration tests (review E4): menu, room, system, dedup."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
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
    CONF_OUTDOOR_SENSOR,
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


async def test_reconfigure_preserves_tuning_and_updates_wiring(
    hass: HomeAssistant,
) -> None:
    """Reconfigure edits the wiring (a sensor) and carries tuning that sat in data
    over to options, so a comfort setting survives the now-shrunk form."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Test Room",
                CONF_TEMP_SENSOR: "sensor.room_temp",
                CONF_ACTUATOR: "climate.trv",
                "sensors": {CONF_OUTDOOR_SENSOR: "sensor.outdoor"},
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.version == 2
    merged = {**entry.data, **entry.options}
    assert merged[CONF_OUTDOOR_SENSOR] == "sensor.outdoor"  # wiring updated
    assert merged[CONF_COMFORT_BASE] == ROOM_INPUT[CONF_COMFORT_BASE]  # tuning kept
    assert entry.options[CONF_COMFORT_BASE] == ROOM_INPUT[CONF_COMFORT_BASE]


async def test_reconfigure_keeps_options_tuning(hass: HomeAssistant) -> None:
    """Reconfiguring the wiring preserves tuning last set via the options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_INPUT,
        options={CONF_CLIMATE_MODE: "heat_only", CONF_COOL_MIN_OUTDOOR: 10.0},
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Test Room",
                CONF_TEMP_SENSOR: "sensor.room_temp",
                CONF_ACTUATOR: "climate.trv",
                "sensors": {},
            },
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    merged = {**entry.data, **entry.options}
    assert merged[CONF_CLIMATE_MODE] == "heat_only"  # options tuning survived
    assert merged[CONF_COOL_MIN_OUTDOOR] == 10.0


async def test_reconfigure_drops_cleared_sensor(hass: HomeAssistant) -> None:
    """A sensor cleared on reconfigure is really removed (full replace of data),
    and is not resurrected into options since it is not tuning."""
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
            result["flow_id"],
            {
                CONF_NAME: "Test Room",
                CONF_TEMP_SENSOR: "sensor.room_temp",
                CONF_ACTUATOR: "climate.trv",
                "sensors": {},
            },
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert CONF_MRT_SENSOR not in entry.data
    assert CONF_MRT_SENSOR not in entry.options


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
                "advanced": {CONF_OPERATIVE_INPUT: ROOM_INPUT[CONF_OPERATIVE_INPUT]},
                "energy": {},
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "comfort_window_pair"}


async def test_hub_options_flow_aborts(hass: HomeAssistant) -> None:
    """F9: the system hub exposes no hot-tunable options — its options flow aborts,
    steering the user to Reconfigure instead of showing an empty room form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM},
        title="Poise System",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "hub_no_options"


async def test_system_setup_rejects_invalid_boiler_action(
    hass: HomeAssistant,
) -> None:
    """F11: a boiler action that doesn't parse is rejected at setup rather than
    silently leaving the hub shadow-only."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "system"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BOILER_ON_ACTION: "not a valid action"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "system"
    assert result["errors"] == {"base": "invalid_boiler_action"}


async def test_system_setup_accepts_valid_boiler_action(
    hass: HomeAssistant,
) -> None:
    """F11: a well-formed boiler action passes and the hub entry is created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "system"}
    )
    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_BOILER_ON_ACTION: "switch.boiler/switch.turn_on"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENTRY_TYPE] == ENTRY_TYPE_SYSTEM
    assert result["data"][CONF_BOILER_ON_ACTION] == "switch.boiler/switch.turn_on"


async def test_system_reconfigure_rejects_invalid_boiler_action(
    hass: HomeAssistant,
) -> None:
    """F11: the same validation guards the hub reconfigure step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM},
        title="Poise System",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BOILER_OFF_ACTION: "typo"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "invalid_boiler_action"}
