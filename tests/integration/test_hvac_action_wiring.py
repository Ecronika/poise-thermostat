"""Wiring for the display contract (review 2026-07-13, D2/D3): the climate
entity's ``hvac_action`` is derived from the published ``final_mode`` +
``actuator_hvac_action`` (real-actuator-preferred), never the raw "manual"
override tag. The exhaustive mapping matrix lives in ``tests/test_hvac_action.py``;
this pins that ``PoiseClimate`` reads the right published keys."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate.const import HVACAction
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poise.climate import PoiseClimate
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


def _base() -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: False,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
    }


async def _entity(hass: HomeAssistant) -> tuple[PoiseClimate, Any]:
    hass.states.async_set("sensor.room_temp", "20.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {"hvac_modes": ["heat", "cool", "off"], "temperature": 20.0},
    )
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=_base(), title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data
    return PoiseClimate(coord, entry), coord


def _data(**kw: Any) -> dict[str, Any]:
    base = {"available": True, "final_mode": "idle", "actuator_hvac_action": None}
    base.update(kw)
    return base


async def test_override_cool_silent_device_reads_cooling(hass: HomeAssistant) -> None:
    ent, coord = await _entity(hass)
    coord._enabled = True
    coord.data = _data(final_mode="cool", actuator_hvac_action=None)
    assert ent.hvac_action == HVACAction.COOLING


async def test_override_heat_silent_device_reads_heating(hass: HomeAssistant) -> None:
    ent, coord = await _entity(hass)
    coord._enabled = True
    coord.data = _data(final_mode="heat", actuator_hvac_action=None)
    assert ent.hvac_action == HVACAction.HEATING


async def test_device_cooling_wins_over_idle_intent(hass: HomeAssistant) -> None:
    ent, coord = await _entity(hass)
    coord._enabled = True
    coord.data = _data(final_mode="idle", actuator_hvac_action="cooling")
    assert ent.hvac_action == HVACAction.COOLING


async def test_guard_held_reads_idle(hass: HomeAssistant) -> None:
    ent, coord = await _entity(hass)
    coord._enabled = True
    coord.data = _data(final_mode="cool", actuator_hvac_action="idle")
    assert ent.hvac_action == HVACAction.IDLE


async def test_dry_in_deadband_reads_drying(hass: HomeAssistant) -> None:
    ent, coord = await _entity(hass)
    coord._enabled = True
    coord.data = _data(final_mode="dry", actuator_hvac_action=None)
    assert ent.hvac_action == HVACAction.DRYING


async def test_window_off_reads_idle(hass: HomeAssistant) -> None:
    ent, coord = await _entity(hass)
    coord._enabled = True
    coord.data = _data(final_mode="off", actuator_hvac_action=None)
    assert ent.hvac_action == HVACAction.IDLE


async def test_disabled_reads_off(hass: HomeAssistant) -> None:
    ent, coord = await _entity(hass)
    coord._enabled = False
    coord.data = _data(final_mode="cool", actuator_hvac_action="cooling")
    assert ent.hvac_action == HVACAction.OFF
