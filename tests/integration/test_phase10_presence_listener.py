"""Phase 10 — F-PRESENCE: presence entities are watched (CI-only).

Refactoring plan ``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md``
Befund 7; ADR-0058 (Nachtrag 2026-07-25).

The listener gap: a presence flip can end an active hold (ADR-0059 §1) and
switches the cool edge between the fixed and the free-running band
(ADR-0061) — yet presence/occupancy entities were NOT subscribed, so the
reaction waited for the next scheduled tick (up to 60 s after the user walked
into the room). Phase 1 built the ``InputRegistry`` for exactly this decision
but ``attach_listeners`` still carried its own inline tuple, so the registry
described the wiring without driving it.

F-PRESENCE promoted presence/occupancy to ``Reaction.IMMEDIATE`` AND made
``attach_listeners`` consume the registry, so the contract and the subscription
can no longer drift. Because the presence lists are the one hot-applied part of
the watched set, an options submit re-points the subscription.
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
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OCCUPANCY_SENSOR,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_PRESENCE_HOME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
)

_PRESENCE = "person.alice"
_OCCUPANCY = "binary_sensor.office_occupied"


def _data(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Office",
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
        CONF_PRESENCE_HOME: [_PRESENCE],
        CONF_OCCUPANCY_SENSOR: [_OCCUPANCY],
        **extra,
    }


def _states(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.room_temp", "20.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 20.0,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    hass.states.async_set(_PRESENCE, "home")
    hass.states.async_set(_OCCUPANCY, "on", {"device_class": "occupancy"})


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Office"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_presence_entities_are_subscribed(hass: HomeAssistant) -> None:
    """The subscription IS ``immediate_entities(registry)``: room sensor,
    actuator, presence and occupancy — in registration order."""
    entry = await _setup(hass, _data())
    coord: Any = entry.runtime_data
    assert coord._watched == ("sensor.room_temp", "climate.trv", _PRESENCE, _OCCUPANCY)
    assert coord._unsub_listeners is not None


async def test_presence_flip_requests_an_immediate_refresh(
    hass: HomeAssistant,
) -> None:
    """A presence change triggers a coalesced refresh instead of waiting for
    the next scheduled tick — the whole point of F-PRESENCE."""
    entry = await _setup(hass, _data())
    coord: Any = entry.runtime_data

    refreshes = {"n": 0}
    original = coord.async_request_refresh

    async def _counting() -> None:
        refreshes["n"] += 1
        await original()

    coord.async_request_refresh = _counting

    hass.states.async_set(_PRESENCE, "not_home")
    await hass.async_block_till_done()
    assert refreshes["n"] == 1, "a presence flip must request a refresh"

    hass.states.async_set(_OCCUPANCY, "off", {"device_class": "occupancy"})
    await hass.async_block_till_done()
    assert refreshes["n"] == 2, "an occupancy flip must request a refresh too"

    # unchanged state is still filtered out (the pre-existing churn guard)
    hass.states.async_set(_OCCUPANCY, "off", {"device_class": "occupancy"})
    await hass.async_block_till_done()
    assert refreshes["n"] == 2


async def test_unwatched_context_input_does_not_refresh(
    hass: HomeAssistant,
) -> None:
    """Non-vacuousness: an entity that is NOT in the registry's IMMEDIATE set
    still waits for the scheduled tick."""
    entry = await _setup(hass, _data())
    coord: Any = entry.runtime_data
    assert "person.bob" not in coord._watched

    refreshes = {"n": 0}
    original = coord.async_request_refresh

    async def _counting() -> None:
        refreshes["n"] += 1
        await original()

    coord.async_request_refresh = _counting

    hass.states.async_set("person.bob", "not_home")
    await hass.async_block_till_done()
    assert refreshes["n"] == 0


async def test_options_change_repoints_the_subscription(
    hass: HomeAssistant,
) -> None:
    """The presence lists are hot-applied, so an options submit must move the
    subscription with them — otherwise the newly configured sensor would be
    read by the tick but never trigger one."""
    entry = await _setup(hass, _data())
    coord: Any = entry.runtime_data
    first_unsub = coord._unsub_listeners
    assert _PRESENCE in coord._watched

    hass.config_entries.async_update_entry(
        entry, options={CONF_PRESENCE_HOME: ["person.bob"]}
    )
    await hass.async_block_till_done()

    assert "person.bob" in coord._watched
    assert _PRESENCE not in coord._watched
    assert coord._unsub_listeners is not first_unsub

    refreshes = {"n": 0}
    original = coord.async_request_refresh

    async def _counting() -> None:
        refreshes["n"] += 1
        await original()

    coord.async_request_refresh = _counting

    # the NEW entity now triggers ...
    hass.states.async_set("person.bob", "home")
    await hass.async_block_till_done()
    assert refreshes["n"] == 1
    # ... and the dropped one no longer does
    hass.states.async_set(_PRESENCE, "not_home")
    await hass.async_block_till_done()
    assert refreshes["n"] == 1
