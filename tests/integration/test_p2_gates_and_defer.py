"""v0.167 Block 1 — coverage for the v0.166 config-flow gates (P1-2 imperial,
P2-4 heat_cool-only) plus the P2-3 compressor-guard setpoint defer, which the
v0.166 simplification left untested (review finding B1).

Self-contained (own helpers) so it never touches the fragile existing test files.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.config_flow import _reconfigure_schema
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
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)
from custom_components.poise.multi.lifecycle import DeviceLifecycle

# --- shared fixtures --------------------------------------------------------

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

# Slim room-onboarding submit: essentials + the collapsed accuracy section.
ROOM_SETUP: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    "accuracy": {CONF_CATEGORY: "II", CONF_COMFORT_BASE: 21.0},
}


def _heat_cool_only_actuator(hass: HomeAssistant, eid: str = "climate.hc") -> None:
    """A device that offers ONLY the combined heat_cool mode (no single heat/cool)."""
    hass.states.async_set(
        eid,
        "heat_cool",
        {
            "hvac_modes": ["heat_cool", "off"],
            "target_temp_high": 25.0,
            "target_temp_low": 20.0,
            "current_temperature": 22.0,
            "min_temp": 16,
            "max_temp": 30,
        },
    )


# --- P1-2: imperial (°F) is rejected up front (config_flow 843 / 914) --------


async def test_user_step_aborts_on_imperial(hass: HomeAssistant) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "imperial_not_supported"


async def test_reconfigure_aborts_on_imperial(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    hass.config.units = US_CUSTOMARY_SYSTEM
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "imperial_not_supported"


# --- P2-4: a heat_cool-only actuator is rejected (config_flow 865 / 959) -----


async def test_room_rejects_heat_cool_only(hass: HomeAssistant) -> None:
    _heat_cool_only_actuator(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "room"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ROOM_SETUP, CONF_ACTUATOR: "climate.hc"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_ACTUATOR] == "heat_cool_only"


async def test_reconfigure_rejects_heat_cool_only(hass: HomeAssistant) -> None:
    _heat_cool_only_actuator(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.hc",
        data={**ROOM_DATA, CONF_ACTUATOR: "climate.hc"},
        title="HC Room",
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "HC Room",
            CONF_TEMP_SENSOR: "sensor.room_temp",
            CONF_ACTUATOR: "climate.hc",
            "sensors": {},
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_ACTUATOR] == "heat_cool_only"


# --- room name is derived from the actuator when left blank (881-882) --------


async def test_room_name_derived_from_actuator(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "climate.trv",
        "heat",
        {"hvac_modes": ["heat", "off"], "friendly_name": "Wohnzimmer"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "room"}
    )
    submit = {k: v for k, v in ROOM_SETUP.items() if k != CONF_NAME}
    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], submit
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wohnzimmer"  # derived from the actuator's name


# --- F9: the system hub has no options flow (config_flow 1071) ---------------


async def test_hub_options_flow_aborts(hass: HomeAssistant) -> None:
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


# --- _reconfigure_schema default hub-existence probe (259) -------------------


def test_reconfigure_schema_probes_hub_existence(hass: HomeAssistant) -> None:
    # called with hub_exists=None (the default) -> the `is None` branch queries
    # the entries itself; with no hub present the anlagen section is omitted.
    schema = _reconfigure_schema(hass)
    keys = {str(k) for k in schema.schema}
    assert CONF_TEMP_SENSOR in keys
    assert "anlagen" not in keys


# --- P2-3: the compressor guard defers the setpoint write (coordinator) ------


def _guard_data() -> dict[str, Any]:
    return {
        CONF_NAME: "AC Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: False,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
    }


def _hot_cool_ac(hass: HomeAssistant) -> None:
    """A cool-capable AC currently OFF in a hot room -> Poise wants to start cool."""
    hass.states.async_set("sensor.room_temp", "28.0", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "30.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.ac",
        "off",
        {
            "hvac_modes": ["heat", "cool", "off"],
            "temperature": 24.0,
            "current_temperature": 28.0,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 30,
        },
    )


async def test_guard_defers_setpoint_write_under_min_off(hass: HomeAssistant) -> None:
    """While the compressor guard holds the pending cool switch, the new regime's
    setpoint is deferred -- no ``climate.set_temperature`` slips through the tick
    (the coordinator's ``and not _mode_nudge_blocked`` write gate)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _hot_cool_ac(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=_guard_data(), title="AC Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data

    # seed the lifecycle as if the compressor just stopped -> min-off is running
    coord._multi_lifecycle = DeviceLifecycle(
        is_on=False, last_off_wall=dt_util.utcnow().timestamp()
    )
    # re-arm the recorders AFTER setup: the climate-platform forward registers the
    # real services and shadows any pre-setup mock, so only a recorder installed
    # now captures (or, here, proves the absence of) this tick's writes.
    setpoints = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    await coord.async_refresh()
    await hass.async_block_till_done()

    # the cool start (off -> cool) is genuinely held by min-off ...
    assert str(coord.data["mode_nudge_blocked"]).startswith("min-off")
    # ... so the new-regime setpoint write is deferred this tick.
    assert setpoints == []
