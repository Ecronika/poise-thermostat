"""Tests for pure diagnostics assembly + redaction (review P3)."""

from __future__ import annotations

from custom_components.poise.diagnostics_data import (
    REDACT_KEYS,
    REDACTED,
    build_diagnostics,
    redact,
)


def test_redacts_entity_ids_keeps_other_values() -> None:
    out = redact({"actuator": "climate.trv", "name": "Living room"}, REDACT_KEYS)
    assert out["actuator"] == REDACTED
    assert out["name"] == "Living room"  # non-secret kept


def test_build_diagnostics_structure() -> None:
    diag = build_diagnostics(
        {"name": "Bath", "temp_sensor": "sensor.bath", "category": "II"},
        {"target_temperature": 21.0},
    )
    assert diag["config"]["temp_sensor"] == REDACTED
    assert diag["config"]["name"] == "Bath"
    assert diag["data"] == {"target_temperature": 21.0}


def test_build_diagnostics_handles_no_data() -> None:
    diag = build_diagnostics({"name": "X"}, None)
    assert diag["data"] is None


def test_build_diagnostics_merges_options_options_win() -> None:
    # F19: the V2 migration moves tuning into entry.options — the dump must
    # merge data + options (options win) so the tuning is not lost.
    diag = build_diagnostics(
        {"name": "Bath", "comfort_weight": 70},
        None,
        entry_options={"comfort_weight": 33, "setback_delta": 3.0},
    )
    assert diag["config"]["comfort_weight"] == 33  # options override data
    assert diag["config"]["setback_delta"] == 3.0  # options-only tuning present
    assert diag["config"]["name"] == "Bath"  # data-only key retained


def test_all_sensor_keys_redacted() -> None:
    payload = {k: f"entity.{k}" for k in REDACT_KEYS}
    out = redact(payload, REDACT_KEYS)
    assert all(v == REDACTED for v in out.values())


def test_presence_and_occupancy_ids_are_redacted() -> None:
    # R2 (2026-07 competitor code audit): presence_home/occupancy_sensor carry
    # person./device_tracker./occupancy ids and reach the dump via the options
    # merge. They must never appear verbatim (RoomMind "person ids in the dump"
    # class; ADR-0022 makes redaction mandatory).
    diag = build_diagnostics(
        {"name": "Living room", "temp_sensor": "sensor.lr"},
        None,
        entry_options={
            "presence_home": ["person.alice", "device_tracker.bob_phone"],
            "occupancy_sensor": ["binary_sensor.lr_motion"],
        },
    )
    assert diag["config"]["presence_home"] == REDACTED
    assert diag["config"]["occupancy_sensor"] == REDACTED
    # and no person id survives anywhere in the serialised payload
    assert "person.alice" not in repr(diag)
    assert "device_tracker.bob_phone" not in repr(diag)


def test_coordinator_data_redacts_entity_ids() -> None:
    # Privacy: the live attributes leak tpi_valve_entity (a real entity id) ->
    # it must be redacted while ordinary diagnostic values pass through.
    diag = build_diagnostics(
        {"name": "Bath"},
        {"tpi_valve_entity": "number.trv_valve_opening_degree", "confidence": 0.7},
    )
    assert diag["data"]["tpi_valve_entity"] == REDACTED
    assert diag["data"]["confidence"] == 0.7
