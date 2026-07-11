"""Integration tests pinning the v0.161.0 external-review fixes (glue, CI-only).

F2  — a CONFIGURED ``trv_external_temp_input`` is vetted at setup: a value the
      user picked is trusted unless it shows a POSITIVE non-temperature signal
      (device_class/unit, e.g. a valve's "%"), in which case it is dropped (never
      fed), the TRV sensor source is handed back to internal (AR-12) and a repair
      issue is raised; a plausible/renamed temperature number passes silently.
F3  — the room reconfigure step rejects a temp sensor on the actuator's own
      device (``sensor_on_actuator``), mirroring the setup path.
F4a — with the per-direction outdoor lockout toggles off, the coordinator passes
      ``None`` for both gates into the cooling decision (lockout disabled).
F9  — a hub with ``boiler_min_on_s``/``boiler_min_off_s`` 0 ends up with the
      effective min-dwell clamped up to the 120 s floor, while ``keepalive`` 0
      (a valid "off") stays 0.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.comfort.dual_setpoint import decide as _real_decide
from custom_components.poise.const import (
    BOILER_MIN_DWELL_FLOOR_S,
    CONF_ACTUATOR,
    CONF_BOILER_KEEPALIVE,
    CONF_BOILER_MIN_OFF,
    CONF_BOILER_MIN_ON,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_COOL_LOCKOUT_ENABLED,
    CONF_ENTRY_TYPE,
    CONF_HEAT_LOCKOUT_ENABLED,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRV_EXTERNAL_TEMP,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)


def _base(**extra: Any) -> dict[str, Any]:
    return {
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
        **extra,
    }


def _room_states(hass: HomeAssistant, *, room: float = 20.0) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup_zone(
    hass: HomeAssistant,
    data: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=data,
        options=options or {},
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --------------------------------------------------------------------------- F2
async def test_f2_implausible_ext_temp_dropped_restores_select_no_write(
    hass: HomeAssistant,
) -> None:
    """F2: a configured external-temp input with a POSITIVE non-temperature signal
    (a valve position in "%") is dropped (never written to), the TRV sensor source
    is handed back to internal (AR-12), and a repair issue is raised."""
    set_value = async_mock_service(hass, "number", "set_value")
    select_opt = async_mock_service(hass, "select", "select_option")
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    # actuator + its sensor-source select share a device; the select currently
    # points at "external" (Poise fed it), so the reject must flip it back to
    # internal or the TRV would regulate against a now-frozen value.
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    donor = MockConfigEntry(domain="demo")
    donor.add_to_hass(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=donor.entry_id, identifiers={("demo", "trv")}
    )
    ent_reg.async_get_or_create(
        "climate", "demo", "trv-act", device_id=device.id, suggested_object_id="trv"
    )
    sel = ent_reg.async_get_or_create(
        "select", "demo", "src", device_id=device.id, suggested_object_id="trv_src"
    )
    hass.states.async_set("sensor.room_temp", "20", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 20.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    hass.states.async_set(
        sel.entity_id, "external", {"options": ["internal", "external"]}
    )
    hass.states.async_set(
        "number.trv_valve_position", "50", {"unit_of_measurement": "%"}
    )
    entry = await _setup_zone(
        hass, _base(**{CONF_TRV_EXTERNAL_TEMP: "number.trv_valve_position"})
    )

    issue_id = f"external_temp_implausible_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    # the implausible feed was dropped, so nothing is ever written to it
    assert entry.runtime_data._trv_ext_temp is None
    assert not [
        c for c in set_value if c.data.get("entity_id") == "number.trv_valve_position"
    ]
    # AR-12: the TRV sensor source was handed back to internal
    assert [
        c
        for c in select_opt
        if c.data.get("entity_id") == sel.entity_id
        and c.data.get("option") == "internal"
    ], "TRV sensor-source select was not restored to internal"


async def test_f2_plausible_ext_temp_number_no_issue(hass: HomeAssistant) -> None:
    """F2: a real external-temperature number passes validation — no repair issue,
    and the configured feed is kept."""
    async_mock_service(hass, "number", "set_value")
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_states(hass)
    hass.states.async_set(
        "number.trv_external_temperature", "21", {"device_class": "temperature"}
    )
    entry = await _setup_zone(
        hass, _base(**{CONF_TRV_EXTERNAL_TEMP: "number.trv_external_temperature"})
    )

    issue_id = f"external_temp_implausible_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert entry.runtime_data._trv_ext_temp == "number.trv_external_temperature"


async def test_f2_renamed_temp_number_kept(hass: HomeAssistant) -> None:
    """F2 regression: a legitimately renamed/localised external-temp number (no
    "external" in the id, no temperature device_class, but a °C unit) must NOT be
    dropped on upgrade — the user picked it explicitly. Guards the upgrade
    regression that the old name-only heuristic would have caused."""
    async_mock_service(hass, "number", "set_value")
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_states(hass)
    hass.states.async_set(
        "number.trv_buero_temperatur_extern", "20.5", {"unit_of_measurement": "°C"}
    )
    entry = await _setup_zone(
        hass, _base(**{CONF_TRV_EXTERNAL_TEMP: "number.trv_buero_temperatur_extern"})
    )

    issue_id = f"external_temp_implausible_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert entry.runtime_data._trv_ext_temp == "number.trv_buero_temperatur_extern"


# --------------------------------------------------------------------------- F3
async def test_f3_reconfigure_rejects_sensor_on_actuator(
    hass: HomeAssistant,
) -> None:
    """F3: on reconfigure, a room sensor sitting on the actuator's own device is
    rejected (sensor_on_actuator); the form is re-shown and the entry unchanged."""
    ent_reg = er.async_get(hass)
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
        "climate",
        "demo",
        "trv-act",
        device_id=device.id,
        suggested_object_id="trv_act",
    )
    hass.states.async_set("sensor.trv_temp", "21", {"device_class": "temperature"})
    hass.states.async_set("climate.trv_act", "heat", {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv_act",
        data=_base(**{CONF_ACTUATOR: "climate.trv_act"}),
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Test Room",
                CONF_TEMP_SENSOR: "sensor.trv_temp",
                CONF_ACTUATOR: "climate.trv_act",
                "sensors": {},
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {CONF_TEMP_SENSOR: "sensor_on_actuator"}
    # the entry was NOT updated — the free-standing sensor is still configured
    assert entry.data[CONF_TEMP_SENSOR] == "sensor.room_temp"


# -------------------------------------------------------------------------- F4a
async def test_f4a_lockout_disabled_passes_none_to_decision(
    hass: HomeAssistant,
) -> None:
    """F4a: with both outdoor-lockout toggles off, the coordinator passes None for
    heat_max_outdoor and cool_min_outdoor into the cooling decision."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _room_states(hass)
    hass.states.async_set("sensor.outdoor", "30.0", {"device_class": "temperature"})

    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _real_decide(**kwargs)

    with patch("custom_components.poise.coordinator.comfort_decide", side_effect=_spy):
        await _setup_zone(
            hass,
            _base(**{CONF_OUTDOOR_SENSOR: "sensor.outdoor"}),
            options={
                CONF_HEAT_LOCKOUT_ENABLED: False,
                CONF_COOL_LOCKOUT_ENABLED: False,
            },
        )

    assert captured, "the cooling decision was never reached"
    assert captured["heat_max_outdoor"] is None
    assert captured["cool_min_outdoor"] is None


# --------------------------------------------------------------------------- F9
async def test_f9_boiler_min_dwell_clamped_keepalive_stays_zero(
    hass: HomeAssistant,
) -> None:
    """F9: min_on/min_off 0 clamp UP to the 120 s dwell floor; keepalive 0 (a
    valid "off") is left untouched."""
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_MIN_ON: 0,
            CONF_BOILER_MIN_OFF: 0,
            CONF_BOILER_KEEPALIVE: 0,
        },
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    coord = hub.runtime_data
    assert coord._min_on == BOILER_MIN_DWELL_FLOOR_S == 120.0
    assert coord._min_off == BOILER_MIN_DWELL_FLOOR_S == 120.0
    assert coord._keepalive == 0.0
