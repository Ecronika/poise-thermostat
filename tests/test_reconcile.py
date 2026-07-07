"""Pure round-trip tests for the shrunk reconfigure reconcile (Step 4)."""

from __future__ import annotations

from custom_components.poise.config_reconcile import reconcile_reconfigure

TUNING = frozenset({"category", "comfort_base", "climate_mode", "operative_input"})


def test_fresh_entry_data_tuning_is_carried_to_options() -> None:
    """A fresh entry stored category/comfort_base in data; the shrunk form omits
    them → they must move to options, not vanish."""
    old_data = {
        "name": "Office",
        "temp_sensor": "sensor.t",
        "actuator": "climate.a",
        "category": "I",
        "comfort_base": 22.5,
    }
    user_input = {"name": "Office", "temp_sensor": "sensor.t", "actuator": "climate.a"}
    new_data, new_options = reconcile_reconfigure(user_input, old_data, {}, TUNING)
    assert new_data == user_input
    assert new_options == {"category": "I", "comfort_base": 22.5}


def test_migrated_entry_options_tuning_survives() -> None:
    """A migrated entry keeps its tuning in options; reconfigure preserves it."""
    old_data = {"name": "Office", "temp_sensor": "sensor.t", "actuator": "climate.a"}
    old_options = {"category": "II", "climate_mode": "heat_only"}
    user_input = {"name": "Office", "temp_sensor": "sensor.t", "actuator": "climate.a"}
    _, new_options = reconcile_reconfigure(user_input, old_data, old_options, TUNING)
    assert new_options == {"category": "II", "climate_mode": "heat_only"}


def test_live_option_wins_over_carried_data() -> None:
    """If a key sits in both data (stale) and options (edited later), the option
    value wins — it is the more recent user choice."""
    old_data = {"actuator": "climate.a", "category": "III"}
    old_options = {"category": "I"}
    user_input = {"actuator": "climate.a"}
    _, new_options = reconcile_reconfigure(user_input, old_data, old_options, TUNING)
    assert new_options["category"] == "I"


def test_form_owned_key_dropped_from_stale_option() -> None:
    """A field the reconfigure form writes into data must not stay shadowed by a
    stale option of the same key (the V7 divergence)."""
    old_data = {"actuator": "climate.old"}
    old_options = {"actuator": "climate.stale"}
    user_input = {"actuator": "climate.new"}
    new_data, new_options = reconcile_reconfigure(
        user_input, old_data, old_options, TUNING
    )
    assert new_data["actuator"] == "climate.new"
    assert "actuator" not in new_options


def test_non_tuning_data_key_not_carried() -> None:
    """A dropped data key that is NOT tuning (e.g. a removed sensor) is really
    removed, not resurrected into options."""
    old_data = {"actuator": "climate.a", "mrt_sensor": "sensor.mrt"}
    user_input = {"actuator": "climate.a"}
    new_data, new_options = reconcile_reconfigure(user_input, old_data, {}, TUNING)
    assert "mrt_sensor" not in new_data
    assert "mrt_sensor" not in new_options
