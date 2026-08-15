"""E.13d safety net: a reconfigure must actually RELOAD the entry.

The existing reconfigure tests patch ``async_setup_entry`` away, so they
verify the stored data but not that the entry is rebuilt. That distinction
is exactly what the HA-2026.12 deprecation forces us to touch (the reload
moves from the flow method into the update listener), so it needs a test
that fails if the reload silently disappears.

Both halves of the contract are pinned here:

* structural change (``entry.data``) -> the entry is reloaded, i.e. a NEW
  coordinator object is built (the old one is discarded together with its
  in-memory learning state);
* options-only change -> NO reload; the very same coordinator hot-applies
  the tuning, which is the whole reason the update listener exists
  (a reload would throw away the learned model).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
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
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
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


def _states(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        "19.5",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "sensor.outdoor",
        "5.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 19.5,
            "target_temp_step": 0.5,
            "min_temp": 5.0,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_structural_reconfigure_rebuilds_the_coordinator(
    hass: HomeAssistant,
) -> None:
    """Wiring change -> the entry is reloaded (new coordinator instance)."""
    entry = await _setup(hass)
    before = entry.runtime_data

    result = await entry.start_reconfigure_flow(hass)
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

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_OUTDOOR_SENSOR] == "sensor.outdoor"  # wiring stored
    assert entry.runtime_data is not before, (
        "a structural reconfigure must reload the entry — the coordinator has "
        "to be rebuilt from the new wiring, not keep serving the old one"
    )


async def test_system_reconfigure_rebuilds_the_hub(hass: HomeAssistant) -> None:
    """The hub has no hot-apply path (F9), so any update must reload it.

    Its reconfigure only stores now, and the hub entry historically carried NO
    update listener at all — without one the new boiler wiring would sit
    unused in the entry until the next restart.
    """
    from custom_components.poise.const import CONF_ENTRY_TYPE, ENTRY_TYPE_SYSTEM

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM},
        title="Poise System",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    before = entry.runtime_data

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.runtime_data is not before, (
        "a hub reconfigure must reload the entry — nothing else applies the "
        "new boiler wiring"
    )


async def test_reconfigure_repairs_an_entry_that_failed_setup(
    hass: HomeAssistant,
) -> None:
    """The repair case: a zone whose setup failed has NO update listener.

    Missing actuator -> ``ConfigEntryNotReady`` -> SETUP_RETRY, and nothing is
    registered that could react to an entry update. Reconfigure is exactly how
    a user fixes this, so the flow schedules the reload itself there. Without
    that branch the corrected wiring would sit unused in the entry (and a
    pending schema migration would not run) until the next HA restart.
    """
    from homeassistant.config_entries import ConfigEntryState

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set(
        "sensor.room_temp",
        "19.5",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    # NO climate.trv state -> setup cannot complete.
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert getattr(entry, "runtime_data", None) is None

    # The user fixes the wiring: the actuator exists now and is reconfigured.
    _states(hass)
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
    assert entry.state is ConfigEntryState.LOADED, (
        "a reconfigure that repairs a failed entry must reload it — no update "
        "listener exists on an unloaded entry to do it"
    )


async def test_hub_rename_does_not_reload(hass: HomeAssistant) -> None:
    """Renaming the hub must NOT tear it down (adversarial-review finding).

    ``async_update_entry`` fires the update listeners for ANY entry change —
    a UI rename, ``pref_disable_polling``, … — not just a reconfigure. The
    hub listener therefore needs the same structural guard as a room: a
    reload cancels the boiler tick timer and drops the activation-delay /
    keep-alive anchors, so a rename would silently restart a running
    activation delay.
    """
    from custom_components.poise.const import CONF_ENTRY_TYPE, ENTRY_TYPE_SYSTEM

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM},
        title="Poise System",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    before = entry.runtime_data

    hass.config_entries.async_update_entry(entry, title="Heizung Keller")
    await hass.async_block_till_done()

    assert entry.runtime_data is before, (
        "a rename is not a structural change — reloading the hub here drops "
        "the boiler timers for nothing"
    )


async def test_options_only_change_keeps_the_coordinator(
    hass: HomeAssistant,
) -> None:
    """Tuning-only change -> NO reload; the same coordinator hot-applies it.

    This is the reason the update listener exists: a reload would discard the
    learned model for what is only a comfort tweak.
    """
    entry = await _setup(hass)
    before = entry.runtime_data

    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_COMFORT_BASE: 22.5}
    )
    await hass.async_block_till_done()

    assert entry.runtime_data is before, (
        "an options-only change must NOT reload the entry (the in-memory "
        "learning state would be lost)"
    )
