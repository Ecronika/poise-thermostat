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


def test_all_sensor_keys_redacted() -> None:
    payload = {k: f"entity.{k}" for k in REDACT_KEYS}
    out = redact(payload, REDACT_KEYS)
    assert all(v == REDACTED for v in out.values())


def test_coordinator_data_redacts_entity_ids() -> None:
    # Privacy: the live attributes leak tpi_valve_entity (a real entity id) ->
    # it must be redacted while ordinary diagnostic values pass through.
    diag = build_diagnostics(
        {"name": "Bath"},
        {"tpi_valve_entity": "number.trv_valve_opening_degree", "confidence": 0.7},
    )
    assert diag["data"]["tpi_valve_entity"] == REDACTED
    assert diag["data"]["confidence"] == 0.7
