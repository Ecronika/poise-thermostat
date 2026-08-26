"""Config-flow integration tests (review E4): menu, room, system, dedup."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, section
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector as ha_selector
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.config_schema import (
    _OPTIONS_SECTIONS,
    _options_schema,
    _options_sections,
    _schedule_window_fields,
)
from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_ADAPTIVE_COOL,
    CONF_ADOPT_EXTERNAL_MODE,
    CONF_ADOPT_EXTERNAL_SETPOINT,
    CONF_BOILER_OFF_ACTION,
    CONF_BOILER_ON_ACTION,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_DAYS,
    CONF_COMFORT_END,
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


def _add_room(hass: HomeAssistant, unique_id: str = "climate.existing") -> None:
    """A pre-existing room entry — AR-30 only offers 'system' once a zone exists."""
    MockConfigEntry(
        domain=DOMAIN, unique_id=unique_id, data=ROOM_INPUT, title="Existing Room"
    ).add_to_hass(hass)


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
    # Schema 2.3: entry.data is STRUCTURE. The accuracy section's two tuning
    # fields are created in options, so the reload-vs-hot-apply predicate
    # (structural_unchanged) never sees a tuning edit on a fresh entry either.
    assert (entry.version, entry.minor_version) == (2, 3)
    assert CONF_COMFORT_BASE not in entry.data
    assert CONF_CATEGORY not in entry.data
    assert entry.options[CONF_COMFORT_BASE] == 21.0
    assert entry.options[CONF_CATEGORY] == "II"
    assert entry.data[CONF_TEMP_SENSOR] == "sensor.room_temp"


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
    _add_room(hass)  # AR-30: 'system' is only offered once a room exists
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
                    CONF_COMFORT_WEIGHT: ROOM_INPUT[CONF_COMFORT_WEIGHT],
                },
                "schedule": {
                    CONF_SETBACK_DELTA: ROOM_INPUT[CONF_SETBACK_DELTA],
                    CONF_OPTIMAL_START: ROOM_INPUT[CONF_OPTIMAL_START],
                    CONF_COMFORT_START: "22:00:00",
                },
                "manual_override": {},
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
    silently leaving the hub shadow-only.

    The action is entered field by field now (roadmap 6), so the submitted value
    is a mapping; ``turn_on`` without a domain is the free-text escape of the
    service combobox being misused. See tests/integration/
    test_boiler_action_fields.py for the rest of the structured-input contract.
    """
    _add_room(hass)  # AR-30: 'system' is only offered once a room exists
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "system"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_BOILER_ON_ACTION: {"entity_id": "switch.boiler", "action": "turn_on"}},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "system"
    assert result["errors"] == {"base": "invalid_boiler_action_fields"}


async def test_system_setup_accepts_valid_boiler_action(
    hass: HomeAssistant,
) -> None:
    """F11: a well-formed boiler action passes and the hub entry is created."""
    _add_room(hass)  # AR-30: 'system' is only offered once a room exists
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "system"}
    )
    action = {"entity_id": "switch.boiler", "action": "switch.turn_on"}
    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BOILER_ON_ACTION: action}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENTRY_TYPE] == ENTRY_TYPE_SYSTEM
    assert result["data"][CONF_BOILER_ON_ACTION] == action


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
            result["flow_id"],
            {
                CONF_BOILER_OFF_ACTION: {
                    "entity_id": "switch.boiler",
                    "action": "switch.turn_off",
                    "data": "not a mapping",
                }
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "invalid_boiler_action_fields"}


async def test_user_menu_hides_system_until_a_room_exists(
    hass: HomeAssistant,
) -> None:
    """AR-30: a fresh install (no zone yet) is offered only 'room'; the singleton
    system hub appears in the menu once at least one room entry exists."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["room"]

    _add_room(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.MENU
    assert "system" in result["menu_options"]


async def test_options_first_save_keeps_optimal_start_and_weight_defaults(
    hass: HomeAssistant,
) -> None:
    """AR-16: the first options-save of a fresh entry must not flip the coordinator
    defaults — optimal_start stays True and comfort_weight stays 70 when the user
    leaves those (now default-carrying) fields untouched."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "manual_override": {},
                "comfort": {CONF_CATEGORY: "II", CONF_COMFORT_BASE: 21.0},
                "schedule": {CONF_SETBACK_DELTA: 3.0},
                "heat_cool": {},
                "presence": {},
                "advanced": {CONF_OPERATIVE_INPUT: False},
                "energy": {},
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_OPTIMAL_START] is True
    assert entry.options[CONF_COMFORT_WEIGHT] == 70


async def test_reconfigure_new_actuator_parks_old(hass: HomeAssistant) -> None:
    """AR-12: repointing a zone to a different actuator releases the OLD one — a
    heat-capable device is parked to heat at the setback (comfort_base 21 - setback
    3 = 18 °C) so it does not stay frozen against Poise's external feed after the
    reload adopts the new actuator."""
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(
        "climate.trv", "heat", {"hvac_modes": ["heat", "off"], "min_temp": 5}
    )
    hass.states.async_set("climate.new", "heat", {"hvac_modes": ["heat", "off"]})
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Test Room",
                CONF_TEMP_SENSOR: "sensor.room_temp",
                CONF_ACTUATOR: "climate.new",
                "sensors": {},
            },
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ACTUATOR] == "climate.new"  # new actuator adopted
    old_mode = [c for c in set_mode if c.data["entity_id"] == "climate.trv"]
    old_temp = [c for c in set_temp if c.data["entity_id"] == "climate.trv"]
    assert old_mode and old_mode[-1].data["hvac_mode"] == "heat"
    assert old_temp and old_temp[-1].data["temperature"] == 18.0


def _section_suggested(result: Any, section_key: str) -> dict[str, Any]:
    """Suggested values of one options-form section, HA-version-agnostic.

    HA <= 2025.x: add_suggested_values_to_schema puts the whole nested dict on
    the SECTION marker's description; HA 2026.2+ recurses into the section
    schema instead — each inner field marker carries its own suggested_value
    (E.11 latest job).
    """
    schema = result["data_schema"].schema
    marker = next(k for k in schema if k.schema == section_key)
    if marker.description is not None:
        return dict(marker.description["suggested_value"])
    inner = schema[marker].schema
    return {
        k.schema: (k.description or {}).get("suggested_value") for k in inner.schema
    }


def _options_submit(**schedule_extra: Any) -> dict[str, Any]:
    """A minimal valid sectioned options submit; extra schedule fields merge in."""
    return {
        "comfort": {
            CONF_CATEGORY: ROOM_INPUT[CONF_CATEGORY],
            CONF_COMFORT_BASE: ROOM_INPUT[CONF_COMFORT_BASE],
            CONF_COMFORT_WEIGHT: ROOM_INPUT[CONF_COMFORT_WEIGHT],
        },
        "schedule": {
            CONF_SETBACK_DELTA: ROOM_INPUT[CONF_SETBACK_DELTA],
            CONF_OPTIMAL_START: ROOM_INPUT[CONF_OPTIMAL_START],
            **schedule_extra,
        },
        "heat_cool": {},
        "presence": {},
        "manual_override": {},
        "advanced": {CONF_OPERATIVE_INPUT: ROOM_INPUT[CONF_OPERATIVE_INPUT]},
        "energy": {},
    }


async def test_options_prefills_stored_adopt_external_mode(
    hass: HomeAssistant,
) -> None:
    """Regression: a stored adopt_external_mode=False must pre-fill the form.

    The field was rendered in the manual_override section but missing from
    _OPTIONS_SECTIONS, so nest_by_section dropped the stored value: every open
    showed the schema default True and every unedited submit wrote True back.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_INPUT,
        options={
            CONF_ADOPT_EXTERNAL_SETPOINT: False,
            CONF_ADOPT_EXTERNAL_MODE: False,
        },
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    suggested = _section_suggested(result, "manual_override")
    # control: the sibling flag has always round-tripped
    assert suggested.get(CONF_ADOPT_EXTERNAL_SETPOINT) is False
    assert suggested.get(CONF_ADOPT_EXTERNAL_MODE) is False


async def test_options_prefills_legacy_adaptive_cool_bool(
    hass: HomeAssistant,
) -> None:
    """A stored legacy adaptive_cool=True pre-fills as the canonical "on".

    The tri-state dropdown only knows the mode strings, so the options flow
    converts the legacy boolean before nest_by_section builds the prefill
    (E.12 coverage: the conversion branch in async_step_init).
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_INPUT,
        options={CONF_ADAPTIVE_COOL: True},
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert _section_suggested(result, "heat_cool").get(CONF_ADAPTIVE_COOL) == "on"


async def test_options_extra_window_half_pair_errors(hass: HomeAssistant) -> None:
    """An extra window with only one bound re-shows the form with the pair error.

    Covers the _renumber_windows validation path plus its propagation into
    errors["base"] (E.12 coverage).
    """
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            _options_submit(**{f"{CONF_COMFORT_START}_2": "06:00:00"}),
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "comfort_window_pair"}


async def test_options_extra_windows_renumber_gaplessly(hass: HomeAssistant) -> None:
    """Clearing a middle window renumbers the later one down (no stranding).

    Stored windows _2 and _3; the submit keeps only the _3 pair — it must be
    stored as the new _2, and the old _3 keys must vanish (form-owned keys keep
    replace semantics, review A.3 / E.12 coverage of the compaction loop).
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_INPUT,
        options={
            f"{CONF_COMFORT_START}_2": "06:00:00",
            f"{CONF_COMFORT_END}_2": "08:00:00",
            f"{CONF_COMFORT_START}_3": "17:00:00",
            f"{CONF_COMFORT_END}_3": "21:00:00",
        },
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            _options_submit(
                **{
                    f"{CONF_COMFORT_START}_3": "17:00:00",
                    f"{CONF_COMFORT_END}_3": "21:00:00",
                }
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[f"{CONF_COMFORT_START}_2"] == "17:00:00"
    assert entry.options[f"{CONF_COMFORT_END}_2"] == "21:00:00"
    assert f"{CONF_COMFORT_START}_3" not in entry.options
    assert f"{CONF_COMFORT_END}_3" not in entry.options


async def test_options_sections_match_rendered_schema(hass: HomeAssistant) -> None:
    """The section map must list exactly the fields the options schema renders.

    nest_by_section can only pre-fill listed fields, so a rendered-but-unlisted
    field silently resets to its schema default on every options round-trip.
    Since ADR-0070 both sides are built from the same ``current`` (the schedule
    section is dynamic), so the parity is checked per state: empty config
    (base pair + exactly ONE empty numbered pair) and a configured window 2
    (base + _2 + the next empty _3 pair) — pinning the n+1 pattern too.
    """
    for current in (
        {},
        {"comfort_start_2": "06:00:00", "comfort_end_2": "09:00:00"},
    ):
        rendered = {
            key.schema: {marker.schema for marker in val.schema.schema}
            for key, val in _options_schema(hass, current).schema.items()
            if isinstance(val, section)
        }
        declared = {
            name: set(fields) for name, fields in _options_sections(current).items()
        }
        assert rendered == declared
    # n+1 pattern pins: empty -> exactly the _2 pair offered; window 2 set ->
    # _2 kept and exactly the _3 pair offered next.
    empty_sched = set(_options_sections({})["schedule"])
    assert {"comfort_start_2", "comfort_end_2"} <= empty_sched
    assert "comfort_start_3" not in empty_sched
    with_two = set(
        _options_sections({"comfort_start_2": "06:00:00", "comfort_end_2": "09:00:00"})[
            "schedule"
        ]
    )
    assert {"comfort_start_2", "comfort_end_2"} <= with_two
    assert {"comfort_start_3", "comfort_end_3"} <= with_two
    assert "comfort_start_4" not in with_two
    # The static map stays the fallback contract for every non-schedule section.
    assert set(_options_sections({})) == set(_OPTIONS_SECTIONS)


# ---------------------------------------------------------------------------
# P2.3: per-window weekday selection — typed n+1 builder, fail-closed
# _days_mask parse (tested purely, tests/test_phase2_config_parser.py),
# orphan-safe renumbering (this file, HA-runtime: config_flow.py/
# config_schema.py both import homeassistant.helpers.selector at module
# level, so they cannot be exercised by the pure suite at all).
# ---------------------------------------------------------------------------


def test_schedule_window_fields_carry_a_days_sibling() -> None:
    """Every triple (base + every CONFIGURED numbered pair + the ONE empty
    n+1 pair) carries a ``comfort_days(_N)`` field alongside start/end."""
    assert _schedule_window_fields({}) == (
        CONF_COMFORT_START,
        CONF_COMFORT_END,
        CONF_COMFORT_DAYS,
        f"{CONF_COMFORT_START}_2",
        f"{CONF_COMFORT_END}_2",
        f"{CONF_COMFORT_DAYS}_2",
    )
    with_two = _schedule_window_fields(
        {f"{CONF_COMFORT_START}_2": "06:00:00", f"{CONF_COMFORT_END}_2": "09:00:00"}
    )
    assert f"{CONF_COMFORT_DAYS}_2" in with_two  # the configured window
    assert f"{CONF_COMFORT_DAYS}_3" in with_two  # the n+1 empty pair's days field
    assert f"{CONF_COMFORT_DAYS}_4" not in with_two  # only ONE empty pair offered
    # F30: a day-only key (no start/end_N pair) must never grow the window
    # set on its own — the builder is still driven off _extra_window_ns.
    days_only = _schedule_window_fields({f"{CONF_COMFORT_DAYS}_5": ["mon"]})
    assert days_only == _schedule_window_fields({})


async def test_window_selector_maps_days_to_multiselect_and_times_to_time(
    hass: HomeAssistant,
) -> None:
    """F14 regression + P2.3: comfort_days(_N) renders as a multi-select
    weekday picker; every start/end field (base or numbered) keeps the plain
    time selector — the exact mapping ``_window_selector`` must produce."""
    current = {
        f"{CONF_COMFORT_START}_2": "06:00:00",
        f"{CONF_COMFORT_END}_2": "09:00:00",
    }
    top = _options_schema(hass, current).schema
    schedule_marker = next(k for k in top if k.schema == "schedule")
    inner = {k.schema: v for k, v in top[schedule_marker].schema.schema.items()}
    days_fields = (
        CONF_COMFORT_DAYS,
        f"{CONF_COMFORT_DAYS}_2",
        f"{CONF_COMFORT_DAYS}_3",
    )
    for field in days_fields:
        assert isinstance(inner[field], ha_selector.SelectSelector), field
        assert inner[field].config["multiple"] is True
    for field in (
        CONF_COMFORT_START,
        CONF_COMFORT_END,
        f"{CONF_COMFORT_START}_2",
        f"{CONF_COMFORT_END}_2",
    ):
        assert isinstance(inner[field], ha_selector.TimeSelector), field


async def test_options_empty_days_on_configured_window_errors(
    hass: HomeAssistant,
) -> None:
    """An explicit empty day selection on a window WITH times is a save-time
    error (UI nudge) — the runtime parser stays defensive independently."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            _options_submit(
                **{
                    CONF_COMFORT_START: "06:00:00",
                    CONF_COMFORT_END: "22:00:00",
                    CONF_COMFORT_DAYS: [],
                }
            ),
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "schedule_days_empty"}


async def test_options_base_window_days_round_trip(hass: HomeAssistant) -> None:
    """The unnumbered base pair's days field passes through renumbering
    untouched — it is never part of the numbered-window compaction loop."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_INPUT, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            _options_submit(
                **{
                    CONF_COMFORT_START: "06:00:00",
                    CONF_COMFORT_END: "22:00:00",
                    CONF_COMFORT_DAYS: ["mon", "tue"],
                }
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_COMFORT_DAYS] == ["mon", "tue"]


async def test_options_renumber_moves_days_with_its_window(hass: HomeAssistant) -> None:
    """Deleting window 2 (Mo) lets window 3 (Di) take its place — the DAYS
    key must move WITH it, at the new index (review Rev. 2.2/2.3 blocker)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_INPUT,
        options={
            f"{CONF_COMFORT_START}_2": "06:00:00",
            f"{CONF_COMFORT_END}_2": "08:00:00",
            f"{CONF_COMFORT_DAYS}_2": ["mon"],
            f"{CONF_COMFORT_START}_3": "17:00:00",
            f"{CONF_COMFORT_END}_3": "21:00:00",
            f"{CONF_COMFORT_DAYS}_3": ["tue"],
        },
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            _options_submit(
                **{
                    f"{CONF_COMFORT_START}_3": "17:00:00",
                    f"{CONF_COMFORT_END}_3": "21:00:00",
                    f"{CONF_COMFORT_DAYS}_3": ["tue"],
                }
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[f"{CONF_COMFORT_START}_2"] == "17:00:00"
    assert entry.options[f"{CONF_COMFORT_DAYS}_2"] == ["tue"]
    assert f"{CONF_COMFORT_START}_3" not in entry.options
    assert f"{CONF_COMFORT_DAYS}_3" not in entry.options


async def test_options_renumber_keeps_legacy_window_maskless(
    hass: HomeAssistant,
) -> None:
    """A legacy window that never had a comfort_days key still doesn't get
    one materialized by renumbering — ALL_DAYS is never written explicitly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_INPUT,
        options={
            f"{CONF_COMFORT_START}_2": "06:00:00",
            f"{CONF_COMFORT_END}_2": "08:00:00",
            # no comfort_days_2 at all -> pre-P2.3 window
            f"{CONF_COMFORT_START}_3": "17:00:00",
            f"{CONF_COMFORT_END}_3": "21:00:00",
        },
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            _options_submit(
                **{
                    f"{CONF_COMFORT_START}_3": "17:00:00",
                    f"{CONF_COMFORT_END}_3": "21:00:00",
                }
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[f"{CONF_COMFORT_START}_2"] == "17:00:00"
    assert f"{CONF_COMFORT_DAYS}_2" not in entry.options


async def test_options_renumber_pops_orphan_days_when_pair_cleared(
    hass: HomeAssistant,
) -> None:
    """F30 / review Rev. 2.3 point 4: clearing a window's start/end but
    leaving its days multi-select untouched in the SAME submit orphans the
    days key (``_extra_window_ns`` never indexes it, since it matches only
    start/end) — the separate ``day_ns`` scan must still pop it, and it must
    never be rewritten under a new index."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=ROOM_INPUT,
        options={
            f"{CONF_COMFORT_START}_2": "06:00:00",
            f"{CONF_COMFORT_END}_2": "08:00:00",
            f"{CONF_COMFORT_DAYS}_2": ["mon"],
        },
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        # start_2/end_2 cleared (absent from the submit); comfort_days_2's
        # prior selection rides along untouched, exactly as a real form
        # submit would carry a multi-select the user never touched.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            _options_submit(**{f"{CONF_COMFORT_DAYS}_2": ["mon"]}),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert f"{CONF_COMFORT_START}_2" not in entry.options
    assert f"{CONF_COMFORT_DAYS}_2" not in entry.options
