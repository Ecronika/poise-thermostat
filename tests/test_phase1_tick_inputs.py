"""Phase-1 contract tests: ``runtime.tick_inputs`` + ``runtime.input_registry``.

Pure (no Home Assistant import): construction of every snapshot type, the
frozen (immutable) contract, and the reaction registry — whose IMMEDIATE set
must equal today's watched list and whose presence entries must stay
NEXT_TICK (plan finding 7, F-PRESENCE deferred to phase 10).
"""

from __future__ import annotations

import dataclasses

import pytest

from custom_components.poise.runtime.input_registry import (
    InputRegistry,
    InputSpec,
    Reaction,
    build_input_registry,
    immediate_entities,
)
from custom_components.poise.runtime.tick_inputs import (
    ActuatorSnapshot,
    BinarySensorSnapshot,
    DeviceGuardSnapshot,
    PresenceSnapshot,
    SensorValue,
    TickInputs,
)


def _actuator(state: str | None = "heat") -> ActuatorSnapshot:
    return ActuatorSnapshot(
        state=state,
        hvac_modes=("heat", "off"),
        actual_setpoint=21.5,
        target_temperature_step=0.5,
        min_temp=5.0,
        max_temp=30.0,
        hvac_action="heating",
        fan_mode=None,
        fan_modes=(),
        context_id="ctx-1",
    )


def _guards() -> DeviceGuardSnapshot:
    return DeviceGuardSnapshot(
        sched_active=False,
        fault_active=False,
        battery=87.0,
        adaptive_mode="off",
        ext_temp_number="number.trv_ext",
        sensor_select_state="external",
        valve_closing_steps=120.0,
        valve_idle_steps=8.0,
    )


def _inputs() -> TickInputs:
    return TickInputs(
        now_mono=1000.0,
        now_wall=1_753_000_000.0,
        local_minute=8 * 60 + 30,
        sun_elevation=12.5,
        room=SensorValue(21.2, age_s=30.0, entity_id="sensor.room"),
        outdoor=SensorValue(4.0, entity_id="sensor.outdoor"),
        humidity=SensorValue(55.0, entity_id="sensor.humidity"),
        trm=SensorValue(None),
        mrt=SensorValue(None),
        irradiance=SensorValue(None),
        windows=(
            BinarySensorSnapshot("binary_sensor.window", is_on=False, available=True),
        ),
        presence=PresenceSnapshot(home=(True,), occupancy=(None,)),
        actuator=_actuator(),
        device_guards=_guards(),
    )


# ---------------------------------------------------------------------------
# tick_inputs: construction + invariants
# ---------------------------------------------------------------------------


def test_sensor_value_defaults() -> None:
    value = SensorValue(21.0)
    assert value.value == 21.0
    assert value.age_s is None
    assert value.entity_id is None


def test_actuator_online_gate_f2() -> None:
    """F2: a missing entity and an 'unavailable' device are both offline;
    every other state — including a real 'off' — is online."""
    assert _actuator("heat").online
    assert _actuator("off").online
    assert not _actuator("unavailable").online
    assert not _actuator(None).online


def test_binary_sensor_unavailable_is_not_closed() -> None:
    """F4a: a dropped contact (is_on None) stays distinguishable from a
    confirmed 'closed' (is_on False)."""
    dropped = BinarySensorSnapshot("binary_sensor.w", is_on=None, available=False)
    assert dropped.is_on is None
    assert not dropped.available
    closed = BinarySensorSnapshot("binary_sensor.w", is_on=False, available=True)
    assert closed.is_on is False
    assert closed.available


def test_presence_snapshot_carries_tristates() -> None:
    presence = PresenceSnapshot(home=(True, None), occupancy=(False,))
    assert presence.home == (True, None)
    assert presence.occupancy == (False,)


def test_device_guard_snapshot_construction() -> None:
    guards = _guards()
    assert guards.sched_active is False
    assert guards.fault_active is False
    assert guards.battery == 87.0
    assert guards.adaptive_mode == "off"
    assert guards.ext_temp_number == "number.trv_ext"
    assert guards.sensor_select_state == "external"
    assert guards.valve_closing_steps == 120.0
    assert guards.valve_idle_steps == 8.0


def test_tick_inputs_assembles_all_groups() -> None:
    inputs = _inputs()
    assert inputs.now_mono == 1000.0
    assert inputs.now_wall == 1_753_000_000.0
    assert inputs.local_minute == 510
    assert inputs.sun_elevation == 12.5
    assert inputs.room.value == 21.2
    assert inputs.room.age_s == 30.0
    assert inputs.outdoor.entity_id == "sensor.outdoor"
    assert inputs.humidity.value == 55.0
    assert inputs.trm.value is None
    assert inputs.mrt.value is None
    assert inputs.irradiance.value is None
    assert inputs.windows[0].entity_id == "binary_sensor.window"
    assert inputs.presence.home == (True,)
    assert inputs.actuator.hvac_modes == ("heat", "off")
    assert inputs.device_guards.battery == 87.0


def test_all_snapshot_types_are_frozen() -> None:
    """The snapshot is an immutable per-tick value object — mutation must
    raise, or a pipeline stage could observe a mid-tick 'state change'."""
    inputs = _inputs()
    samples: list[tuple[object, str, object]] = [
        (inputs, "now_mono", 0.0),
        (inputs.room, "value", 0.0),
        (inputs.windows[0], "is_on", True),
        (inputs.presence, "home", ()),
        (inputs.actuator, "state", "off"),
        (inputs.device_guards, "battery", 1.0),
    ]
    for obj, field, value in samples:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, field, value)


# ---------------------------------------------------------------------------
# input_registry: reaction classes
# ---------------------------------------------------------------------------


def _registry() -> InputRegistry:
    return build_input_registry(
        temp="sensor.room",
        windows=("binary_sensor.w1", "binary_sensor.w2"),
        actuator="climate.trv",
        presence_entities=("person.a", "device_tracker.phone"),
        occupancy_entities=("binary_sensor.occ",),
        outdoor="sensor.outdoor",
        humidity="sensor.humidity",
        trm="sensor.trm",
        mrt="sensor.mrt",
        irradiance="sensor.irradiance",
        weather="weather.home",
        trv_ext_temp="number.trv_ext",
    )


def test_input_registry_is_an_ordered_tuple() -> None:
    """``InputRegistry`` (the plan's named deliverable) is a plain tuple.

    Ordering is contract — the IMMEDIATE entries appear in listener
    registration order — and the registry is immutable once built.
    """
    registry: InputRegistry = _registry()
    assert isinstance(registry, tuple)
    assert all(isinstance(spec, InputSpec) for spec in registry)


def test_immediate_set_is_exactly_todays_watched_list() -> None:
    """IMMEDIATE == {temp} | windows | {actuator} — nothing more.

    ``attach_listeners`` subscribes to ``(temp, *windows, actuator)`` and
    nothing else (coordinator.py line 1193); the registry must reproduce that
    set AND its order verbatim so the listener wiring can consume it as-is.
    """
    specs = _registry()
    watched = ("sensor.room", "binary_sensor.w1", "binary_sensor.w2", "climate.trv")
    assert immediate_entities(specs) == watched
    assert {s.entity_id for s in specs if s.reaction is Reaction.IMMEDIATE} == set(
        watched
    )


def test_presence_and_occupancy_are_next_tick() -> None:
    """Finding 7 (plan section 1.7): the listener gap is CONSERVED.

    A presence flip can end a hold (coordinator.py lines 787-804), but the
    presence entities are not in the watched list (line 1193) — the reaction
    waits for the next tick. The registry pins today's behaviour; promoting
    presence/occupancy to IMMEDIATE is behaviour fix F-PRESENCE (phase 10).
    """
    by_id = {s.entity_id: s for s in _registry()}
    for entity_id in ("person.a", "device_tracker.phone", "binary_sensor.occ"):
        assert by_id[entity_id].reaction is Reaction.NEXT_TICK


def test_every_other_input_is_next_tick() -> None:
    next_tick = {s.entity_id for s in _registry() if s.reaction is Reaction.NEXT_TICK}
    assert next_tick == {
        "person.a",
        "device_tracker.phone",
        "binary_sensor.occ",
        "sensor.outdoor",
        "sensor.humidity",
        "sensor.trm",
        "sensor.mrt",
        "sensor.irradiance",
        "weather.home",
        "number.trv_ext",
    }


def test_roles_are_assigned() -> None:
    roles = {s.entity_id: s.role for s in _registry()}
    assert roles["sensor.room"] == "temp_sensor"
    assert roles["binary_sensor.w1"] == "window_sensor"
    assert roles["climate.trv"] == "actuator"
    assert roles["person.a"] == "presence_home"
    assert roles["binary_sensor.occ"] == "occupancy"
    assert roles["weather.home"] == "weather"
    assert roles["number.trv_ext"] == "trv_external_temp"


def test_unset_and_empty_ids_are_skipped() -> None:
    """Mirrors the ``if e`` filter of today's watched list (line 1193)."""
    specs = build_input_registry(
        temp="",
        windows=("", "binary_sensor.w"),
        actuator="climate.trv",
    )
    assert immediate_entities(specs) == ("binary_sensor.w", "climate.trv")
    assert all(s.entity_id for s in specs)
    assert {s.role for s in specs} == {"window_sensor", "actuator"}


def test_input_spec_is_frozen() -> None:
    spec = InputSpec("sensor.x", Reaction.NEXT_TICK, "outdoor_sensor")
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.reaction = Reaction.IMMEDIATE  # type: ignore[misc]


def test_reaction_members() -> None:
    assert list(Reaction) == [Reaction.IMMEDIATE, Reaction.NEXT_TICK]
    assert {reaction.value for reaction in Reaction} == {"immediate", "next_tick"}
