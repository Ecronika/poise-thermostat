"""Tests for the V1->V2 config-entry store migration (ADR-0007)."""

from __future__ import annotations

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_OCCUPANCY_SENSOR,
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_PRESENCE_HOME,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_SENSOR,
)
from custom_components.poise.migration import (
    SETUP_TUNING_KEYS,
    STRUCTURAL_KEYS,
    as_entity_list,
    migrate_room_entry,
)


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


def test_structural_key_is_data_owned_options_cannot_shadow() -> None:
    # F20: a structural key in both data and options keeps the DATA value — options
    # (hot-tuned) must not win for a data-owned structural field on the merge.
    data = {CONF_TEMP_SENSOR: "sensor.correct", CONF_CONTROLS_BOILER: True}
    options = {CONF_TEMP_SENSOR: "sensor.stale", CONF_CONTROLS_BOILER: False}
    new_data, new_options = migrate_room_entry(data, options)
    assert new_data[CONF_TEMP_SENSOR] == "sensor.correct"  # data wins, not options
    assert new_data[CONF_CONTROLS_BOILER] is True
    assert CONF_TEMP_SENSOR not in new_options
    assert CONF_CONTROLS_BOILER not in new_options


def test_non_system_entry_type_room_still_migrates() -> None:
    # F21: hub detection keys on ENTRY_TYPE_SYSTEM, not merely "entry_type present".
    # A room entry carrying a non-system entry_type must still get the V2 split,
    # not pass through untouched.
    data = {
        CONF_ENTRY_TYPE: "legacy_room",
        CONF_TEMP_SENSOR: "sensor.t",
        CONF_ACTUATOR: "climate.ac",
        CONF_COMFORT_BASE: 22.0,  # tuning must still split out to options
    }
    new_data, new_options = migrate_room_entry(data, {})
    assert new_options[CONF_COMFORT_BASE] == 22.0  # split happened
    assert CONF_COMFORT_BASE not in new_data
    assert new_data[CONF_TEMP_SENSOR] == "sensor.t"  # structural stayed in data
    assert new_data[CONF_ENTRY_TYPE] == "legacy_room"  # entry_type is data-owned


def test_as_entity_list_normalizes() -> None:
    assert as_entity_list("person.a") == ["person.a"]  # single -> one-element
    assert as_entity_list("") == []  # empty string -> empty
    assert as_entity_list(None) == []  # missing -> empty
    assert as_entity_list(["a", "b"]) == ["a", "b"]  # list passes through
    assert as_entity_list(["a", "", None]) == ["a"]  # falsy members filtered
    assert as_entity_list(("x",)) == ["x"]  # tuple -> list


# --- MINOR_VERSION 3: the onboarding tuning leaves entry.data -------------------


def test_setup_tuning_keys_are_disjoint_from_structural_keys() -> None:
    """The contract that makes the plain V2 split the WHOLE minor-3 rule.

    ``async_step_room`` writes ``SETUP_TUNING_KEYS`` into ``options``; for
    entries created before that, the migration relocates them. It does so only
    because they are not in ``STRUCTURAL_KEYS`` — so a future setup-form tuning
    field is migrated by construction, and one accidentally declared structural
    would silently stay in ``data``. That must fail here instead.
    """
    assert SETUP_TUNING_KEYS
    assert SETUP_TUNING_KEYS.isdisjoint(STRUCTURAL_KEYS)


def test_setup_tuning_moves_out_of_data_on_reprocess() -> None:
    """A v2.2 entry as ``async_step_room`` used to create it: structure plus the
    two tuning fields in ``data``, nothing in ``options``. The split relocates
    exactly those two and leaves every structural key where it is."""
    data = {
        CONF_NAME: "Büro",
        CONF_TEMP_SENSOR: "sensor.t",
        CONF_ACTUATOR: "climate.ac",
        CONF_OUTDOOR_HUMIDITY_SENSOR: "sensor.rh_out",
        CONF_COMFORT_BASE: 22.0,
        CONF_CATEGORY: "I",
    }
    new_data, new_options = migrate_room_entry(dict(data), {})
    assert new_options == {CONF_COMFORT_BASE: 22.0, CONF_CATEGORY: "I"}
    assert new_data == {
        CONF_NAME: "Büro",
        CONF_TEMP_SENSOR: "sensor.t",
        CONF_ACTUATOR: "climate.ac",
        CONF_OUTDOOR_HUMIDITY_SENSOR: "sensor.rh_out",
    }


def test_outdoor_humidity_sensor_is_structural() -> None:
    """ADR-0066 B.3 wiring must not be filed as tuning by the split.

    It is a ``ZoneStructure`` field and the reconfigure form owns it, so a copy
    left behind in ``options`` would be reanimated after the user cleared it.
    """
    assert CONF_OUTDOOR_HUMIDITY_SENSOR in STRUCTURAL_KEYS


def test_options_value_wins_over_the_data_copy_of_setup_tuning() -> None:
    """Collision rule for minor 3: the options value was edited later, so it is
    the newer one and must survive the relocation."""
    data = {CONF_ACTUATOR: "climate.ac", CONF_COMFORT_BASE: 21.0, CONF_CATEGORY: "II"}
    options = {CONF_COMFORT_BASE: 23.5}  # re-tuned via the options flow
    new_data, new_options = migrate_room_entry(dict(data), dict(options))
    assert new_options == {CONF_COMFORT_BASE: 23.5, CONF_CATEGORY: "II"}
    assert CONF_COMFORT_BASE not in new_data
