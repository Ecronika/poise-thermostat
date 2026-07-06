"""Tests for the V1->V2 config-entry store migration (ADR-0007)."""

from __future__ import annotations

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_OCCUPANCY_SENSOR,
    CONF_PRESENCE_HOME,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_SENSOR,
)
from custom_components.poise.migration import as_entity_list, migrate_room_entry


def test_tuning_moves_to_options_structure_stays() -> None:
    data = {
        CONF_NAME: "Büro",
        CONF_TEMP_SENSOR: "sensor.t",
        CONF_ACTUATOR: "climate.ac",
        CONF_COMFORT_BASE: 22.0,  # tuning, lived in data under V1
        CONF_COMFORT_WEIGHT: 60,  # tuning, lived in data under V1
    }
    new_data, new_options = migrate_room_entry(data, {})
    assert new_data == {
        CONF_NAME: "Büro",
        CONF_TEMP_SENSOR: "sensor.t",
        CONF_ACTUATOR: "climate.ac",
    }
    assert new_options == {CONF_COMFORT_BASE: 22.0, CONF_COMFORT_WEIGHT: 60}


def test_options_win_over_data_on_conflict() -> None:
    data = {CONF_ACTUATOR: "climate.ac", CONF_COMFORT_BASE: 21.0}
    options = {CONF_COMFORT_BASE: 23.5}  # user re-tuned via the options flow
    _new_data, new_options = migrate_room_entry(data, options)
    assert new_options[CONF_COMFORT_BASE] == 23.5


def test_multi_entity_single_becomes_list() -> None:
    data = {CONF_ACTUATOR: "climate.ac", CONF_WINDOW_SENSOR: "binary_sensor.w"}
    options = {
        CONF_PRESENCE_HOME: "person.a",
        CONF_OCCUPANCY_SENSOR: "binary_sensor.pir",
    }
    new_data, new_options = migrate_room_entry(data, options)
    assert new_data[CONF_WINDOW_SENSOR] == ["binary_sensor.w"]  # structural
    assert new_options[CONF_PRESENCE_HOME] == ["person.a"]  # hot-applied
    assert new_options[CONF_OCCUPANCY_SENSOR] == ["binary_sensor.pir"]


def test_multi_entity_already_list_passes_through() -> None:
    data = {CONF_ACTUATOR: "climate.ac", CONF_WINDOW_SENSOR: ["a", "b"]}
    new_data, _new_options = migrate_room_entry(data, {})
    assert new_data[CONF_WINDOW_SENSOR] == ["a", "b"]


def test_system_entry_untouched() -> None:
    data = {CONF_ENTRY_TYPE: "system", "boiler_min_on_s": 300}
    new_data, new_options = migrate_room_entry(data, {})
    assert new_data == data
    assert new_options == {}


def test_as_entity_list_normalizes() -> None:
    assert as_entity_list("person.a") == ["person.a"]  # single -> one-element
    assert as_entity_list("") == []  # empty string -> empty
    assert as_entity_list(None) == []  # missing -> empty
    assert as_entity_list(["a", "b"]) == ["a", "b"]  # list passes through
    assert as_entity_list(["a", "", None]) == ["a"]  # falsy members filtered
    assert as_entity_list(("x",)) == ["x"]  # tuple -> list
