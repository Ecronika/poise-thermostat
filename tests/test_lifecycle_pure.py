"""Pure tests for the lifecycle/teardown resolvers (review F1/F3/F4/F12)."""

from __future__ import annotations

from custom_components.poise import orphan_entry_id
from custom_components.poise.control.lifecycle import (
    ParkPlan,
    SafeStatePlan,
    resolve_hub_unload_off,
    resolve_park_command,
    resolve_safe_state,
)

FLOOR = 7.0


# --- F1: safe state after room-sensor loss -------------------------------------
def test_safe_state_heat_device_in_cool_writes_mode_and_setpoint() -> None:
    plan = resolve_safe_state(
        hvac_modes=["heat", "cool"],
        device_state="cool",
        device_setpoint=24.0,
        device_min=16.0,
        floor=FLOOR,
    )
    assert plan == SafeStatePlan("heat", 16.0, write_mode=True, write_setpoint=True)


def test_safe_state_heat_device_already_holding_is_noop() -> None:
    plan = resolve_safe_state(
        hvac_modes=["heat"],
        device_state="heat",
        device_setpoint=16.0,
        device_min=16.0,
        floor=FLOOR,
    )
    assert plan is None


def test_safe_state_right_mode_wrong_setpoint() -> None:
    plan = resolve_safe_state(
        hvac_modes=["heat"],
        device_state="heat",
        device_setpoint=21.0,
        device_min=None,
        floor=FLOOR,
    )
    assert plan == SafeStatePlan("heat", FLOOR, write_mode=False, write_setpoint=True)


def test_safe_state_cool_only_on_is_commanded_off() -> None:
    plan = resolve_safe_state(
        hvac_modes=["cool", "fan_only"],
        device_state="cool",
        device_setpoint=23.0,
        device_min=17.0,
        floor=FLOOR,
    )
    assert plan == SafeStatePlan("off", None, write_mode=True, write_setpoint=False)


def test_safe_state_cool_only_already_off_is_noop() -> None:
    assert (
        resolve_safe_state(
            hvac_modes=["cool"],
            device_state="off",
            device_setpoint=None,
            device_min=None,
            floor=FLOOR,
        )
        is None
    )


# --- F3: capability-dependent park on delete -----------------------------------
def test_park_valve_closes() -> None:
    assert resolve_park_command(
        is_valve=True,
        hvac_modes=[],
        heats_for_zone=False,
        setback_setpoint=18.0,
        floor=FLOOR,
    ) == ParkPlan("valve", None, None, 0.0)


def test_park_heater_parks_heat_at_setback_floored() -> None:
    assert resolve_park_command(
        is_valve=False,
        hvac_modes=["heat", "cool"],
        heats_for_zone=True,
        setback_setpoint=18.0,
        floor=FLOOR,
    ) == ParkPlan("climate", "heat", 18.0, None)
    # setback below the frost floor is clamped up
    assert resolve_park_command(
        is_valve=False,
        hvac_modes=["heat"],
        heats_for_zone=True,
        setback_setpoint=5.0,
        floor=FLOOR,
    ) == ParkPlan("climate", "heat", FLOOR, None)


def test_park_cool_only_or_no_heat_duty_turns_off() -> None:
    assert resolve_park_command(
        is_valve=False,
        hvac_modes=["cool", "fan_only"],
        heats_for_zone=False,
        setback_setpoint=None,
        floor=FLOOR,
    ) == ParkPlan("climate", "off", None, None)
    # heat-capable but not the zone's heat source -> off
    assert resolve_park_command(
        is_valve=False,
        hvac_modes=["heat", "cool"],
        heats_for_zone=False,
        setback_setpoint=18.0,
        floor=FLOOR,
    ) == ParkPlan("climate", "off", None, None)


# --- F4/F12: boiler off only at a genuine hand-over ----------------------------
def test_hub_unload_off_disable_while_actuating() -> None:
    assert resolve_hub_unload_off(
        was_actuating=True, disabled=True, still_actuating=True
    )


def test_hub_unload_off_actuation_dropped_by_reconfigure() -> None:
    assert resolve_hub_unload_off(
        was_actuating=True, disabled=False, still_actuating=False
    )


def test_hub_unload_off_plain_reload_keeps_hands_off() -> None:
    assert not resolve_hub_unload_off(
        was_actuating=True, disabled=False, still_actuating=True
    )


def test_hub_unload_off_shadow_only_never_fires() -> None:
    assert not resolve_hub_unload_off(
        was_actuating=False, disabled=True, still_actuating=False
    )


# --- v0.193.1: repair issues whose config entry is gone ------------------------
_LIVE = frozenset({"01KZPKHG90KT78G9N3WV56A91F", "01KZHTAMRPNX7JRS99F9KN27HN"})


def test_an_issue_of_a_deleted_entry_is_an_orphan() -> None:
    """The case found in the field: a per-entry issue standing since June whose
    config entry no longer exists — invisible in the repairs UI (the dialog
    needs the entry to render) and therefore not even dismissable."""
    assert (
        orphan_entry_id("sensor_frozen_01KVF397VFR36MSTDMKBTDHCN8", _LIVE)
        == "01KVF397VFR36MSTDMKBTDHCN8"
    )
    # A pre-2022 install carries 32-char hex entry ids instead of a ULID.
    assert orphan_entry_id(f"heating_failure_{'a' * 32}", _LIVE) == "a" * 32


def test_a_live_entrys_issue_is_never_touched() -> None:
    """The half that matters: deleting one of these would erase a standing
    warning about a zone that still exists."""
    for issue_id in (
        "declared_step_mismatch_01KZPKHG90KT78G9N3WV56A91F",
        "override_suggestion_01KZHTAMRPNX7JRS99F9KN27HN",
    ):
        assert orphan_entry_id(issue_id, _LIVE) is None


def test_a_global_issue_is_not_mistaken_for_a_per_entry_one() -> None:
    """``frost_zone_not_controlling_boiler`` has no entry id at all — its tail
    is the word ``boiler``. The shape test (26 or 32 alphanumerics) is what
    keeps it, and any future global issue, out of the sweep."""
    assert orphan_entry_id("frost_zone_not_controlling_boiler", _LIVE) is None
    assert orphan_entry_id("some_issue_without_any_entry", _LIVE) is None
    assert orphan_entry_id("no_separator", _LIVE) is None
    assert orphan_entry_id("_" + "a" * 26, _LIVE) is None  # no key half
