"""Silver test-coverage batch 3: the dense device-guard block, the Poise climate
entity's own setpoint override, and the untested config-flow branches (options
flow, system reconfigure, reconfigure collision).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOILER_COUNT_THRESHOLD,
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
    CONF_TRV_EXTERNAL_TEMP,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)

ROOM: dict[str, Any] = {
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


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=data[CONF_ACTUATOR], data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _climate_eid(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    reg = er.async_get(hass)
    for e in er.async_entries_for_config_entry(reg, entry.entry_id):
        if e.domain == "climate":
            return e.entity_id
    raise AssertionError("no climate entity")


async def test_device_guard_resolution_surfaces_diagnostics(
    hass: HomeAssistant,
) -> None:
    """When the actuator is a registered entity on a device, Poise auto-resolves
    the device's sibling entities (schedule / fault / battery / valve / external
    temp / sensor-select) and surfaces their state as diagnostics + repairs."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "select", "select_option")

    # a mock "TRV device" that owns the actuator + its sibling entities
    dev_entry = MockConfigEntry(domain="demo", title="TRV Device")
    dev_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=dev_entry.entry_id, identifiers={("demo", "trv1")}
    )
    ent_reg = er.async_get(hass)

    def _reg(domain: str, obj: str, uid: str, **kw: Any) -> str:
        return ent_reg.async_get_or_create(
            domain,
            "demo",
            uid,
            config_entry=dev_entry,
            device_id=device.id,
            suggested_object_id=obj,
            **kw,
        ).entity_id

    act = _reg("climate", "trv", "act")
    _reg("switch", "trv_schedule", "sched")
    _reg("binary_sensor", "trv_fault", "fault")
    _reg("sensor", "trv_battery", "batt", original_device_class="battery")
    _reg("number", "trv_external_temperature", "ext")
    _reg("select", "trv_sensor", "sel")
    _reg("number", "trv_valve_opening_degree", "valve")
    _reg("sensor", "trv_closing_steps", "close")
    _reg("sensor", "trv_idle_steps", "idle")

    hass.states.async_set("sensor.room_temp", "19.0", {"device_class": "temperature"})
    hass.states.async_set(
        act,
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 18.0,
            "current_temperature": 19.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    hass.states.async_set("switch.trv_schedule", "on")
    hass.states.async_set("binary_sensor.trv_fault", "on")
    hass.states.async_set("sensor.trv_battery", "8")
    hass.states.async_set("number.trv_external_temperature", "19.0")
    hass.states.async_set(
        "select.trv_sensor", "internal", {"options": ["internal", "external"]}
    )
    hass.states.async_set("number.trv_valve_opening_degree", "0")
    hass.states.async_set("sensor.trv_closing_steps", "0")
    hass.states.async_set("sensor.trv_idle_steps", "5")

    entry = await _setup(
        hass,
        {
            **ROOM,
            CONF_ACTUATOR: act,
            CONF_OPERATIVE_INPUT: True,
            CONF_TRV_EXTERNAL_TEMP: "number.trv_external_temperature",
        },
    )
    # The device-guard resolution iterated the actuator's sibling entities and
    # picked up the fault binary_sensor: its "on" state surfaces as device_alarm,
    # which in turn drives the tick into the heating-failure notify path. With the
    # notify service unregistered here, that path's persistent_notification call
    # must be swallowed so setup still completes — a regression guard, since the
    # unguarded call used to raise ServiceNotFound and crash the whole tick.
    d = entry.runtime_data.data
    assert d["device_alarm"] is True  # fault sibling auto-resolved from the device
    assert d["heating_failure"] is True  # -> notify path reached, tick survived it


async def test_poise_entity_set_temperature_sets_override(
    hass: HomeAssistant,
) -> None:
    """Setting a temperature on the Poise *climate* entity records a manual
    override on the coordinator (climate.async_set_temperature path)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "20", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 19.0,
            "current_temperature": 20.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = await _setup(hass, dict(ROOM))
    eid = _climate_eid(hass, entry)

    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": eid, "temperature": 22.5}, True
    )
    await hass.async_block_till_done()

    assert entry.runtime_data.data.get("override_active") is True


async def test_options_flow_creates_entry(hass: HomeAssistant) -> None:
    """The options flow shows its form and stores the submitted options."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"
        # The options schema is sectioned (ADR-0008): submit the nested shape.
        # Required-no-default fields must be present in their section; sections
        # whose fields are all optional/defaulted may be empty.
        opts = {
            "comfort": {
                CONF_CATEGORY: ROOM[CONF_CATEGORY],
                CONF_COMFORT_BASE: ROOM[CONF_COMFORT_BASE],
                CONF_CLIMATE_MODE: ROOM[CONF_CLIMATE_MODE],
                CONF_COMFORT_WEIGHT: ROOM[CONF_COMFORT_WEIGHT],
            },
            "schedule": {
                CONF_SETBACK_DELTA: ROOM[CONF_SETBACK_DELTA],
                CONF_OPTIMAL_START: ROOM[CONF_OPTIMAL_START],
            },
            "heat_cool": {},
            "presence": {},
            "advanced": {CONF_OPERATIVE_INPUT: ROOM[CONF_OPERATIVE_INPUT]},
            "energy": {},
        }
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], opts
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # flatten_sections stored the tuning flat (not nested under section keys)
    assert entry.options[CONF_COMFORT_BASE] == ROOM[CONF_COMFORT_BASE]


async def test_reconfigure_system_hub(hass: HomeAssistant) -> None:
    """Reconfiguring the singleton hub keeps the ENTRY_TYPE tag and updates it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_COUNT_THRESHOLD: 1},
        title="Poise System",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BOILER_COUNT_THRESHOLD: 2}
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ENTRY_TYPE] == ENTRY_TYPE_SYSTEM


async def test_reconfigure_collision_aborts(hass: HomeAssistant) -> None:
    """Reconfiguring a zone onto an actuator another zone already owns aborts."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.other",
        data={**ROOM, CONF_ACTUATOR: "climate.other"},
        title="Other",
    ).add_to_hass(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM, title="Test Room"
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ROOM, CONF_ACTUATOR: "climate.other"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
