"""Tests for the pure reconfigure reconcile helper (review V7)."""

from __future__ import annotations

from custom_components.poise.config_reconcile import reconcile_reconfigure
from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_COMFORT_BASE,
    CONF_CONTROLS_BOILER,
    CONF_DECLARED_POWER,
    CONF_FLOW_TEMP,
    CONF_NAME,
    CONF_SOURCE_POLICY,
    CONF_TEMP_SENSOR,
)


def test_reconcile_keeps_structural_data_keys_form_omits() -> None:
    # F10: a shrunk reconfigure (no plant fields rendered) must not drop the
    # structural data keys the form doesn't offer — controls_boiler /
    # declared_power / flow_temp / source_policy stay in data, untouched, and
    # never leak into options (they are structural, not tuning).
    old_data = {
        CONF_NAME: "Office",
        CONF_TEMP_SENSOR: "sensor.t",
        CONF_ACTUATOR: "climate.ac",
        CONF_CONTROLS_BOILER: True,
        CONF_DECLARED_POWER: 1500.0,
        CONF_FLOW_TEMP: 45,
        CONF_SOURCE_POLICY: "heat_pump",
        CONF_COMFORT_BASE: 22.0,  # tuning that still lived in data (old entry)
    }
    user_input = {
        CONF_NAME: "Office",
        CONF_TEMP_SENSOR: "sensor.t",
        CONF_ACTUATOR: "climate.ac",
    }
    new_data, new_options = reconcile_reconfigure(
        user_input, old_data, {}, {CONF_COMFORT_BASE}
    )
    # structural plant keys survived in data, unchanged
    assert new_data[CONF_CONTROLS_BOILER] is True
    assert new_data[CONF_DECLARED_POWER] == 1500.0
    assert new_data[CONF_FLOW_TEMP] == 45
    assert new_data[CONF_SOURCE_POLICY] == "heat_pump"
    # and did not leak into options
    for key in (
        CONF_CONTROLS_BOILER,
        CONF_DECLARED_POWER,
        CONF_FLOW_TEMP,
        CONF_SOURCE_POLICY,
    ):
        assert key not in new_options
    # tuning still in data was carried into options (never silently dropped)
    assert new_options[CONF_COMFORT_BASE] == 22.0
    assert CONF_COMFORT_BASE not in new_data


def test_reconcile_form_value_wins_over_old_structural() -> None:
    # A structural key the form *does* render keeps the submitted value; a
    # structural key it omits is carried from old data as-is.
    old_data = {CONF_ACTUATOR: "climate.old", CONF_CONTROLS_BOILER: True}
    new_data, new_options = reconcile_reconfigure(
        {CONF_ACTUATOR: "climate.new"}, old_data, {}, set()
    )
    assert new_data[CONF_ACTUATOR] == "climate.new"  # form value wins
    assert new_data[CONF_CONTROLS_BOILER] is True  # omitted -> carried
    assert new_options == {}


def test_reconcile_structural_section_rendered_drops_cleared_key() -> None:
    # AR-09: when the structural section IS rendered, a _STRUCTURAL_CARRY key
    # absent from user_input means the user cleared it, so it must NOT be carried
    # back from old_data. When the section is hidden (default) the same absence
    # means "not shown" and the key IS carried back into data unchanged.
    old_data = {CONF_ACTUATOR: "climate.a", CONF_CONTROLS_BOILER: True}
    user_input = {CONF_ACTUATOR: "climate.a"}
    # section rendered -> cleared -> dropped from data (and not leaked to options)
    new_data, new_options = reconcile_reconfigure(
        user_input, old_data, {}, set(), structural_section_rendered=True
    )
    assert CONF_CONTROLS_BOILER not in new_data
    assert CONF_CONTROLS_BOILER not in new_options
    # section hidden (default) -> not shown -> carried back into data unchanged
    new_data_hidden, _ = reconcile_reconfigure(
        user_input, old_data, {}, set(), structural_section_rendered=False
    )
    assert new_data_hidden[CONF_CONTROLS_BOILER] is True
