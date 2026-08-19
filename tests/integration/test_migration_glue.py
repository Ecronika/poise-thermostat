"""Config-entry store migration to schema 2.3, end to end (glue, CI-only).

An old V1 entry (everything in ``data``, single-id pickers) must migrate on setup
to the V2 split (structural ``data`` + hot-applyable ``options``) with the
window/presence/occupancy ids normalized to lists — and the coordinator must then
read that list-form presence without breaking the tick. Outdoor is mild so the
ADR-0051 hot-day cool-raise stays inert; the empty-house (person 'not_home') AWAY
relaxation is the only thing moving the written cooling setpoint.

The second half pins MINOR_VERSION 3: a v2.2 entry created by the old onboarding
step still carries ``comfort_base``/``category`` in ``data``; HA must run the
migration on it (the minor bump is what triggers that at all), the values must
land in ``options`` unchanged, a value already in ``options`` must win, and the
whole thing must stay idempotent.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise import async_migrate_entry
from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_NAME,
    CONF_OUTDOOR_SENSOR,
    CONF_PRESENCE_HOME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_WINDOW_SENSOR,
    DOMAIN,
)


def _v1_data() -> dict[str, Any]:
    # V1 layout: every field lived in entry.data and the pickers were single ids.
    # A wide comfort window guarantees is_comfort=True.
    return {
        CONF_NAME: "Office",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_TRM_SENSOR: "sensor.trm",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_START: "00:00:00",
        CONF_COMFORT_END: "23:59:00",
        CONF_SETBACK_DELTA: 3.0,
        CONF_PRESENCE_HOME: "person.a",  # single id -> list on migrate
        CONF_WINDOW_SENSOR: "binary_sensor.win",  # single id -> list on migrate
    }


def _warm_room(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        "29",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("sensor.outdoor", "20", {"device_class": "temperature"})
    hass.states.async_set("sensor.trm", "22", {"device_class": "temperature"})
    hass.states.async_set("binary_sensor.win", "off", {"device_class": "window"})
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "heat", "off"],
            "temperature": 24.0,
            "current_temperature": 29.0,
            "target_temp_step": 0.5,
            "min_temp": 16,
            "max_temp": 32,
        },
    )


async def test_v1_entry_migrates_and_runs_list_presence(hass: HomeAssistant) -> None:
    """A V1 entry migrates to the V2 split; the tick reads the list-form presence."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _warm_room(hass)
    hass.states.async_set("person.a", "not_home")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_v1_data(),
        version=1,
        title="Office",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # migrated to V2; minor_version pinned to the current schema (2.3)
    assert entry.version == 2
    assert entry.minor_version == 3
    # tuning moved out of data into options; structural inputs stayed in data
    assert CONF_COMFORT_BASE not in entry.data
    assert entry.options[CONF_COMFORT_BASE] == 21.0
    assert CONF_TEMP_SENSOR in entry.data
    # single-id pickers normalized to one-element lists
    assert entry.options[CONF_PRESENCE_HOME] == ["person.a"]  # hot-applied set
    assert entry.data[CONF_WINDOW_SENSOR] == ["binary_sensor.win"]  # structural set
    # the coordinator read the list-form presence: person 'not_home' -> AWAY
    # relaxation wrote a cooling setpoint without breaking the tick.
    assert set_temp, "coordinator did not write a cooling setpoint after migration"


async def test_future_schema_version_is_refused(hass: HomeAssistant) -> None:
    """AR-19: a config entry from a NEWER schema (v3) is refused, not silently
    downgraded — async_migrate_entry returns False and leaves the entry untouched."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data={CONF_TEMP_SENSOR: "sensor.room_temp", CONF_ACTUATOR: "climate.ac"},
        version=3,
        title="Future",
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is False
    assert entry.version == 3  # not downgraded


async def test_migration_is_idempotent(hass: HomeAssistant) -> None:
    """AR-19: migrating an already-migrated (v2) entry again is a no-op split — the
    same data/options come back out, so a double migration cannot corrupt the store."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_v1_data(),
        version=1,
        title="Office",
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    data_once, options_once = dict(entry.data), dict(entry.options)

    # a second pass over the now-v2 entry must reproduce the same split
    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    assert dict(entry.data) == data_once
    assert dict(entry.options) == options_once


# --- MINOR_VERSION 3: onboarding tuning leaves entry.data -----------------------


def _v22_data() -> dict[str, Any]:
    """A v2.2 entry exactly as the OLD ``async_step_room`` created it: structural
    wiring plus the accuracy section's two tuning fields, all in ``data``."""
    return {
        CONF_NAME: "Office",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.ac",
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_COMFORT_BASE: 22.5,
        CONF_CATEGORY: "I",
    }


async def test_v22_entry_migrates_setup_tuning_into_options(
    hass: HomeAssistant,
) -> None:
    """HA runs the migration on a 2.2 entry (the minor bump is what makes it) and
    the two tuning values move to ``options`` with their values intact."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _warm_room(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_v22_data(),
        version=2,
        minor_version=2,
        title="Office",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (entry.version, entry.minor_version) == (2, 3)
    assert CONF_COMFORT_BASE not in entry.data
    assert CONF_CATEGORY not in entry.data
    assert entry.options[CONF_COMFORT_BASE] == 22.5
    assert entry.options[CONF_CATEGORY] == "I"
    # the wiring stayed where it belongs
    assert entry.data[CONF_TEMP_SENSOR] == "sensor.room_temp"
    assert entry.data[CONF_OUTDOOR_SENSOR] == "sensor.outdoor"
    # and the value the coordinator actually runs on is the migrated one
    assert entry.runtime_data._comfort_base == 22.5


async def test_v22_migration_keeps_the_newer_options_value(
    hass: HomeAssistant,
) -> None:
    """Collision rule: a value already in ``options`` was edited later than the
    ``data`` copy the onboarding step left behind, so it must win."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_v22_data(),
        options={CONF_COMFORT_BASE: 19.0},  # re-tuned via the options flow
        version=2,
        minor_version=2,
        title="Office",
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.options[CONF_COMFORT_BASE] == 19.0  # options wins, data dropped
    assert entry.options[CONF_CATEGORY] == "I"  # the uncontested one still moved
    assert CONF_COMFORT_BASE not in entry.data


async def test_v22_migration_is_idempotent(hass: HomeAssistant) -> None:
    """A second pass over the now-2.3 entry reproduces the same split."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.ac",
        data=_v22_data(),
        version=2,
        minor_version=2,
        title="Office",
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    data_once, options_once = dict(entry.data), dict(entry.options)
    assert await async_migrate_entry(hass, entry) is True
    assert (dict(entry.data), dict(entry.options)) == (data_once, options_once)
    assert (entry.version, entry.minor_version) == (2, 3)
