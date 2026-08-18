"""Phase-4 integration tests: ``ha.input_reader.InputReader`` against real hass.

The reader is NOT wired into the coordinator yet (that is the next phase-4
step) — these tests pin the moved read primitives 1:1 against live
``hass.states`` / registry data so the module is covered by the CI glue gate
from day one:

* ``snapshot()`` bundles exactly the pre-first-await read block (values,
  entity ids, unified clock fields, raw actuator capability view, guard
  defaults),
* the F4a window OR/unavailable semantics,
* the capability heat-only default and the DEVICE_MAX_C fallback,
* ``sensor_age`` measuring from ``last_changed`` (not ``last_updated``),
* device-guard registry discovery incl. the idempotency gate and the
  swallowed-failure boundary,
* the positioned post-await reads (actuator, presence tristates, ext-feed
  target, sensor-select, valve steps).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA 2023.7 skips.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poise.clock import ManualClock
from custom_components.poise.ha.input_reader import (
    _GUARD_MAX_ATTEMPTS,
    _GUARD_RETRY_SPACING_S,
    InputReader,
    actuator_snapshot,
    parse_attr_number,
    parse_state_number,
)
from custom_components.poise.runtime.config import ZoneStructure


def _structure(**overrides: Any) -> ZoneStructure:
    base: dict[str, Any] = {
        "zone_name": "Test Room",
        "temperature_sensor": "sensor.room_temp",
        "actuator": "climate.trv",
        "trm": "sensor.trm",
        "outdoor": "sensor.outdoor",
        "humidity": "sensor.humidity",
        "outdoor_humidity": None,
        "mrt": "sensor.mrt",
        "presence_home_entities": (),
        "occupancy_entities": (),
        "windows": (),
        "weather": None,
        "irradiance": "sensor.irradiance",
        "trv_ext_temp": None,
    }
    base.update(overrides)
    return ZoneStructure(**base)


def _reader(
    hass: HomeAssistant, *, mono: float = 1000.0, **overrides: Any
) -> InputReader:
    return InputReader(hass, _structure(**overrides), ManualClock(mono))


def _set_actuator(hass: HomeAssistant, state: str = "heat", **extra: Any) -> None:
    attrs: dict[str, Any] = {
        "hvac_modes": ["heat", "off"],
        "temperature": 18.0,
        "current_temperature": 19.0,
        "target_temp_step": 0.5,
        "min_temp": 5,
        "max_temp": 30,
        "hvac_action": "heating",
        "fan_mode": "auto",
        "fan_modes": ["auto", "low"],
    }
    attrs.update(extra)
    hass.states.async_set("climate.trv", state, attrs)


# --- snapshot(): the pre-first-await read block --------------------------------


async def test_snapshot_bundles_pre_first_await_reads(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.room_temp", "19.5")
    hass.states.async_set("sensor.outdoor", "4.0")
    hass.states.async_set("sensor.trm", "6.5")
    hass.states.async_set("sensor.humidity", "55")
    hass.states.async_set("sensor.mrt", "18.5")
    hass.states.async_set("sensor.irradiance", "120")
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 30.0})
    hass.states.async_set("binary_sensor.w1", "on")
    hass.states.async_set("binary_sensor.w2", "off")
    _set_actuator(hass)

    reader = _reader(
        hass, mono=1234.5, windows=("binary_sensor.w1", "binary_sensor.w2")
    )
    before = dt_util.utcnow().timestamp()
    inputs = reader.snapshot()
    after = dt_util.utcnow().timestamp()

    # unified clock fields, captured once at snapshot time
    assert inputs.now_mono == 1234.5
    assert before <= inputs.now_wall <= after
    local = dt_util.now()
    assert inputs.local_minute in (
        local.hour * 60 + local.minute,
        (local.hour * 60 + local.minute - 1) % 1440,  # minute rollover tolerance
    )
    assert inputs.local_day_ordinal in (local.toordinal(), local.toordinal() - 1)
    assert inputs.sun_elevation == 30.0

    # sensor values + provenance
    assert inputs.room.value == 19.5
    assert inputs.room.entity_id == "sensor.room_temp"
    assert inputs.room.age_s is not None and inputs.room.age_s >= 0.0
    assert inputs.outdoor.value == 4.0
    assert inputs.outdoor.entity_id == "sensor.outdoor"
    assert inputs.trm.value == 6.5
    assert inputs.humidity.value == 55.0
    assert inputs.mrt.value == 18.5
    assert inputs.irradiance.value == 120.0
    # age is only consulted for the room sensor (freeze watchdog)
    assert inputs.outdoor.age_s is None

    # windows: per-contact snapshots, healthy contacts are available
    assert [w.entity_id for w in inputs.windows] == [
        "binary_sensor.w1",
        "binary_sensor.w2",
    ]
    assert inputs.windows[0].is_on is True and inputs.windows[0].available
    assert inputs.windows[1].is_on is False and inputs.windows[1].available

    # raw actuator capability view (ONE read for the whole segment)
    assert inputs.actuator.state == "heat"
    assert inputs.actuator.hvac_modes == ("heat", "off")
    assert inputs.actuator.max_temp == 30.0

    # no guard entities discovered (actuator not in the registry) -> neutral
    # defaults, and the discovery gate has latched
    assert reader.guards_resolved
    assert inputs.device_guards.sched_active is False
    assert inputs.device_guards.fault_active is False
    assert inputs.device_guards.battery is None
    assert inputs.device_guards.adaptive_mode is None
    assert inputs.device_guards.ext_temp_number is None


async def test_snapshot_missing_entities_read_as_none(hass: HomeAssistant) -> None:
    """A zone with only the required wiring: every optional read is None and
    the raw actuator view carries no defaults (heat-only / DEVICE_MAX_C stay
    consumer rules)."""
    reader = _reader(
        hass,
        trm=None,
        outdoor=None,
        humidity=None,
        mrt=None,
        irradiance=None,
    )
    inputs = reader.snapshot()

    assert inputs.room.value is None  # sensor missing entirely
    assert inputs.room.age_s is None
    assert inputs.outdoor.value is None
    assert inputs.outdoor.entity_id is None
    assert inputs.trm.value is None
    assert inputs.humidity.value is None
    assert inputs.mrt.value is None
    assert inputs.irradiance.value is None
    assert inputs.sun_elevation is None  # no sun.sun in this hass
    assert inputs.windows == ()
    assert inputs.actuator.state is None
    assert inputs.actuator.hvac_modes == ()
    assert inputs.actuator.max_temp is None

    # the primitive helpers carry today's read-time defaults (pinned by
    # test_glue_coverage4 for the coordinator originals); the DEVICE_MAX_C
    # fallback is a consumer rule on the snapshot's max_temp (B.5 removed the
    # dead device_max() reader).
    assert reader.capability() == (True, False)
    assert reader.device_min() is None


async def test_capability_and_limits_from_live_state(hass: HomeAssistant) -> None:
    _set_actuator(hass, hvac_modes=["heat", "cool", "off"])
    reader = _reader(hass)
    assert reader.capability() == (True, True)
    assert reader.snapshot().actuator.max_temp == 30.0
    assert reader.device_min() == 5.0
    # non-numeric limits: max reads absent (consumer falls back), min skips
    # the floor clamp (P3-1)
    _set_actuator(hass, min_temp="low", max_temp="high")
    assert reader.snapshot().actuator.max_temp is None
    assert reader.device_min() is None
    # non-numeric sun elevation reads as None
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": "high"})
    assert reader.sun_elevation() is None


# --- window contacts (F4a / ADR-0041 §5) ---------------------------------------


async def test_window_or_and_unavailable_semantics(hass: HomeAssistant) -> None:
    windows = ("binary_sensor.w1", "binary_sensor.w2", "binary_sensor.w3")
    reader = _reader(hass, windows=windows)

    # one dropped ("unavailable"), one missing entirely, one confirmed closed
    hass.states.async_set("binary_sensor.w1", "off")
    hass.states.async_set("binary_sensor.w2", "unavailable")
    assert reader.window_open() == (False, True)
    contacts = reader.read_windows()
    assert contacts[0].is_on is False and contacts[0].available
    assert contacts[1].is_on is None and not contacts[1].available
    assert contacts[2].is_on is None and not contacts[2].available

    # a confirmed "on" from a still-working contact beats a sibling's dropout
    hass.states.async_set("binary_sensor.w1", "on")
    hass.states.async_set("binary_sensor.w2", "unknown")  # unknown == dropped
    hass.states.async_set("binary_sensor.w3", "off")
    assert reader.window_open() == (True, True)

    # all healthy and closed
    hass.states.async_set("binary_sensor.w1", "off")
    hass.states.async_set("binary_sensor.w2", "off")
    assert reader.window_open() == (False, False)


# --- sensor age (last_changed, not last_updated) -------------------------------


async def test_sensor_age_measures_from_last_changed(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.room_temp", "19.0", {"seq": 1})
    reader = _reader(hass)

    state = hass.states.get("sensor.room_temp")
    assert state is not None
    anchor = state.last_changed + timedelta(seconds=120)
    assert reader.sensor_age("sensor.room_temp", now=anchor) == 120.0

    # re-publishing the SAME value bumps last_updated but not last_changed —
    # the age keeps growing (the "available but frozen" contract)
    hass.states.async_set("sensor.room_temp", "19.0", {"seq": 2})
    stale = hass.states.get("sensor.room_temp")
    assert stale is not None
    assert stale.last_updated > stale.last_changed  # sanity: only updated moved
    assert reader.sensor_age("sensor.room_temp", now=anchor) == 120.0

    # missing sensor has no age; the ad-hoc call path (no anchor) works too
    assert reader.sensor_age("sensor.ghost") is None
    fresh = reader.sensor_age("sensor.room_temp")
    assert fresh is not None and fresh >= 0.0


# --- scalar parse primitives ---------------------------------------------------


async def test_parse_primitives_conserve_coordinator_semantics(
    hass: HomeAssistant,
) -> None:
    reader = _reader(hass)
    # _num: unknown/unavailable/empty -> None; NaN/Inf rejected (C1)
    for bad in ("unknown", "unavailable", "", "NaN", "inf", "bogus"):
        hass.states.async_set("sensor.x", bad)
        assert parse_state_number(hass.states.get("sensor.x")) is None
    hass.states.async_set("sensor.x", "21.5")
    assert parse_state_number(hass.states.get("sensor.x")) == 21.5
    assert parse_state_number(None) is None
    assert reader.read("sensor.x") == 21.5
    assert reader.read(None) is None
    assert reader.read("") is None

    # _num_attr: attributes are read even while the state is "unknown", but
    # never from an "unavailable" device
    hass.states.async_set("climate.trv", "unknown", {"temperature": 18.5})
    assert parse_attr_number(hass.states.get("climate.trv"), "temperature") == 18.5
    hass.states.async_set("climate.trv", "unavailable", {"temperature": 18.5})
    assert parse_attr_number(hass.states.get("climate.trv"), "temperature") is None
    assert parse_attr_number(None, "temperature") is None


# --- presence tristates (F8) ---------------------------------------------------


async def test_tristate_f8_and_positioned_presence_read(hass: HomeAssistant) -> None:
    hass.states.async_set("person.a", "Work")  # named zone -> confident False
    hass.states.async_set("person.b", "home")
    hass.states.async_set("device_tracker.phone", "Gym")
    hass.states.async_set("binary_sensor.occ", "on")
    hass.states.async_set("sensor.odd", "weird_state")  # non-presence domain
    hass.states.async_set("binary_sensor.occ2", "unavailable")

    reader = _reader(
        hass,
        presence_home_entities=("person.a", "person.b", "device_tracker.phone"),
        occupancy_entities=("binary_sensor.occ", "binary_sensor.occ2", "sensor.odd"),
    )
    assert reader.tristate("person.a") is False  # F8: named zone
    assert reader.tristate("person.b") is True
    assert reader.tristate("device_tracker.phone") is False
    assert reader.tristate("binary_sensor.occ") is True
    assert reader.tristate("binary_sensor.occ2") is None  # dropped -> unresolved
    assert reader.tristate("sensor.odd") is None  # odd state, odd domain
    assert reader.tristate("binary_sensor.ghost") is None  # never registered
    assert reader.tristate(None) is None
    assert reader.tristate("binary_sensor.off_contact") is None  # missing
    hass.states.async_set("binary_sensor.off_contact", "off")
    assert reader.tristate("binary_sensor.off_contact") is False

    snap = reader.read_presence()
    assert snap.home == (False, True, False)
    assert snap.occupancy == (True, None, None)


# --- device-guard discovery ----------------------------------------------------


def _register_trv_device(hass: HomeAssistant, *, extra_steps_pair: bool = False) -> str:
    """A mock TRV device owning the actuator + its sibling entities."""
    dev_entry = MockConfigEntry(domain="demo", title="TRV Device")
    dev_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=dev_entry.entry_id, identifiers={("demo", "trv1")}
    )
    ent_reg = er.async_get(hass)

    def _reg(domain: str, obj: str, uid: str, **kw: Any) -> str:
        return ent_reg.async_get_or_create(
            domain,
            "demo",
            uid,
            config_entry=dev_entry,
            device_id=device.id,
            suggested_object_id=obj,
            **kw,
        ).entity_id

    act = _reg("climate", "trv", "act")
    _reg("switch", "trv_adaptive", "adaptive")
    _reg("switch", "trv_schedule", "sched")
    _reg("binary_sensor", "trv_fault", "fault")
    _reg("sensor", "trv_battery", "batt", original_device_class="battery")
    _reg("number", "trv_external_temperature", "ext")
    _reg("select", "trv_mode", "mode")  # no options state -> NOT the sensor select
    _reg("select", "trv_sensor", "sel")
    _reg("number", "trv_valve_opening_degree", "valve")
    _reg("sensor", "trv_closing_steps", "close")
    _reg("sensor", "trv_idle_steps", "idle")
    if extra_steps_pair:
        _reg("sensor", "trv_closing_steps_2", "close2")
        _reg("sensor", "trv_idle_steps_2", "idle2")
    return act


async def test_guard_discovery_resolves_and_is_idempotent(
    hass: HomeAssistant,
) -> None:
    act = _register_trv_device(hass)
    hass.states.async_set(
        "select.trv_sensor", "internal", {"options": ["internal", "external"]}
    )
    hass.states.async_set("switch.trv_schedule", "on")
    hass.states.async_set("switch.trv_adaptive", "on")
    hass.states.async_set("binary_sensor.trv_fault", "on")
    hass.states.async_set("sensor.trv_battery", "8")

    reader = _reader(hass, actuator=act)
    reader.resolve_device_guards()
    assert reader.guards_resolved
    assert reader.sched_entity == "switch.trv_schedule"
    assert reader.adaptive_mode_entity == "switch.trv_adaptive"
    assert reader.fault_entity == "binary_sensor.trv_fault"
    assert reader.battery_entity == "sensor.trv_battery"
    assert reader.ext_temp_auto == "number.trv_external_temperature"
    assert reader.sensor_select == "select.trv_sensor"
    assert reader.valve_entity == "number.trv_valve_opening_degree"
    assert reader.valve_closing_steps == "sensor.trv_closing_steps"
    assert reader.valve_idle_steps == "sensor.trv_idle_steps"

    # idempotency gate: a pinned entity survives later resolution calls
    # (test_phase0_effect_sequences relies on this for the coordinator)
    reader.sensor_select = "select.pinned"
    reader.resolve_device_guards()
    assert reader.sensor_select == "select.pinned"

    # the snapshot consumes the discovered guards' live states
    inputs = reader.snapshot()
    assert inputs.device_guards.sched_active is True
    assert inputs.device_guards.fault_active is True
    assert inputs.device_guards.battery == 8.0
    assert inputs.device_guards.adaptive_mode == "on"
    assert inputs.device_guards.ext_temp_number == "number.trv_external_temperature"


async def test_reads_reject_non_finite_values(hass: HomeAssistant) -> None:
    """NaN/Inf from device attributes must die at the trust boundary (B.5).

    A NaN ``max_temp``/``min_temp`` used to pass the isinstance capture and
    silently fail-open the SAFETY clamps downstream (NaN never binds in the
    constraint solver); a NaN ``current_temperature`` poisoned the ADR-0056
    deviation EMA until restart. All must read as None now.
    """
    _set_actuator(
        hass,
        min_temp=float("nan"),
        max_temp=float("inf"),
        current_temperature=float("nan"),
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": float("-inf")})

    reader = _reader(hass)
    snap = reader.read_actuator()
    assert snap.min_temp is None
    assert snap.max_temp is None
    assert snap.current_temperature is None
    assert reader.device_min() is None
    assert reader.sun_elevation() is None
    # the pre-await capability view captures the same boundary
    inputs = reader.snapshot()
    assert inputs.actuator.max_temp is None


async def test_guard_discovery_valve_steps_first_match_wins(
    hass: HomeAssistant,
) -> None:
    """A second matching steps sensor must not overwrite the first.

    Parity with every other guard role: first-match-wins across the one
    discovery pass (review plan A.2).
    """
    act = _register_trv_device(hass, extra_steps_pair=True)
    reader = _reader(hass, actuator=act)
    reader.resolve_device_guards()
    assert reader.valve_closing_steps == "sensor.trv_closing_steps"
    assert reader.valve_idle_steps == "sensor.trv_idle_steps"


async def test_guard_discovery_failure_is_swallowed(hass: HomeAssistant) -> None:
    """A registry error never escapes (setup boundary) — but it is not final.

    The swallow is unchanged; what changed is that a raise no longer burns the
    single lifetime attempt.  ``guards_resolved`` now means "no further attempt
    will be made", so it stays False while retries are still owed (the bounded
    retry itself is pinned by the tests below).
    """
    reader = _reader(hass)
    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        side_effect=RuntimeError("registry down"),
    ):
        reader.resolve_device_guards()  # must not raise (setup boundary)
    assert reader.guards_resolved is False
    assert reader.sched_entity is None


# --- device-guard discovery: bounded retry -------------------------------------


async def test_guard_discovery_success_is_never_retried(hass: HomeAssistant) -> None:
    """Success is FINAL: one registry access, ever (today's semantics)."""
    act = _register_trv_device(hass)
    clock = ManualClock(1000.0)
    reader = InputReader(hass, _structure(actuator=act), clock)

    with patch(
        "homeassistant.helpers.entity_registry.async_get", wraps=er.async_get
    ) as spy:
        reader.resolve_device_guards()
        assert reader.guards_resolved
        assert spy.call_count == 1
        clock.advance(86_400.0)  # a day past every backoff window
        reader.resolve_device_guards()
        assert spy.call_count == 1
    assert reader.sched_entity == "switch.trv_schedule"


async def test_guard_discovery_transient_error_retries_once_then_succeeds(
    hass: HomeAssistant,
) -> None:
    """The bug this budget fixes: a transient miss no longer waits for reload.

    Attempt 1 raises, the next call INSIDE the spacing window does not even
    reach the registry, and the first call after it resolves the guards for
    good.
    """
    act = _register_trv_device(hass)
    clock = ManualClock(0.0)
    reader = InputReader(hass, _structure(actuator=act), clock)

    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        side_effect=RuntimeError("registry down"),
    ) as spy:
        reader.resolve_device_guards()
        assert reader.guards_resolved is False
        assert spy.call_count == 1
        clock.advance(_GUARD_RETRY_SPACING_S[0] - 0.1)
        reader.resolve_device_guards()
        assert spy.call_count == 1  # spacing not elapsed: no registry access

    clock.advance(0.1)
    with patch(
        "homeassistant.helpers.entity_registry.async_get", wraps=er.async_get
    ) as spy:
        reader.resolve_device_guards()
        assert spy.call_count == 1  # exactly ONE retry
        assert reader.guards_resolved
        clock.advance(86_400.0)
        reader.resolve_device_guards()
        assert spy.call_count == 1  # ... and success is final

    assert reader.sched_entity == "switch.trv_schedule"
    assert reader.battery_entity == "sensor.trv_battery"


async def test_guard_discovery_permanent_error_stops_after_the_budget(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A registry that never recovers costs N attempts and two log lines.

    Driven at the real tick rate (one call per TICK_INTERVAL_S over two
    hours): the spacing, not the caller's frequency, decides — so the tick is
    never slowed by more than the float comparison, and the log escalates once
    per STAGE (first failure, give-up) instead of once per attempt.
    """
    caplog.set_level(logging.DEBUG, logger="custom_components.poise.ha.input_reader")
    act = _register_trv_device(hass)
    clock = ManualClock(0.0)
    reader = InputReader(hass, _structure(actuator=act), clock)

    with patch(
        "homeassistant.helpers.entity_registry.async_get",
        side_effect=RuntimeError("registry down"),
    ) as spy:
        for _ in range(120):
            reader.resolve_device_guards()
            clock.advance(60.0)
        assert spy.call_count == _GUARD_MAX_ATTEMPTS == 3

    assert reader.guards_resolved  # terminal: no attempt will follow
    assert reader.sched_entity is None
    messages = [r.getMessage() for r in caplog.records]
    assert sum("device-guard resolution failed" in m for m in messages) == 1
    assert sum("gave up after 3 attempts" in m for m in messages) == 1


async def test_guard_discovery_retry_spacing_is_the_declared_backoff(
    hass: HomeAssistant,
) -> None:
    """The attempt INSTANTS are the declared spacing (ManualClock proof).

    One call per second for an hour; the recorded monotonic instants must be
    exactly ``0, 0+60, 60+300`` and then stop.
    """
    clock = ManualClock(0.0)
    reader = InputReader(hass, _structure(), clock)
    seen: list[float] = []

    def _exploding_registry(_hass: HomeAssistant) -> er.EntityRegistry:
        seen.append(clock.monotonic())
        raise RuntimeError("registry down")

    with patch(
        "homeassistant.helpers.entity_registry.async_get", new=_exploding_registry
    ):
        for _ in range(3600):
            reader.resolve_device_guards()
            clock.advance(1.0)

    assert seen == [0.0, 60.0, 360.0]
    assert len(seen) == _GUARD_MAX_ATTEMPTS
    assert list(_GUARD_RETRY_SPACING_S) == [
        seen[1] - seen[0],
        seen[2] - seen[1],
    ]
    assert reader.guards_resolved


async def test_guard_discovery_registryless_actuator_is_final(
    hass: HomeAssistant,
) -> None:
    """A live State without a registry entry can never gain one.

    ``EntityPlatform._async_add_entity`` creates the registry entry BEFORE the
    state is written, so an actuator that HAS a state and NO entry carries no
    unique_id — the ordinary ``generic_thermostat``/template setup.  Spending
    retries on that permanent answer would be pure waste, so it is final on
    the first attempt.
    """
    _set_actuator(hass)  # state only, never registered
    clock = ManualClock(0.0)
    reader = InputReader(hass, _structure(), clock)

    with patch(
        "homeassistant.helpers.entity_registry.async_get", wraps=er.async_get
    ) as spy:
        reader.resolve_device_guards()
        assert reader.guards_resolved
        clock.advance(86_400.0)
        reader.resolve_device_guards()
        assert spy.call_count == 1
    assert reader.sched_entity is None


async def test_guard_discovery_deviceless_entity_is_final(
    hass: HomeAssistant,
) -> None:
    """Registered but device-less: the registry gave a definitive answer."""
    dev_entry = MockConfigEntry(domain="demo", title="Device-less")
    dev_entry.add_to_hass(hass)
    act = (
        er.async_get(hass)
        .async_get_or_create(
            "climate", "demo", "lonely", config_entry=dev_entry, suggested_object_id="l"
        )
        .entity_id
    )
    clock = ManualClock(0.0)
    reader = InputReader(hass, _structure(actuator=act), clock)

    with patch(
        "homeassistant.helpers.entity_registry.async_get", wraps=er.async_get
    ) as spy:
        reader.resolve_device_guards()
        assert reader.guards_resolved
        clock.advance(86_400.0)
        reader.resolve_device_guards()
        assert spy.call_count == 1


async def test_guard_discovery_picks_up_a_late_arriving_actuator(
    hass: HomeAssistant,
) -> None:
    """Neither entry nor state = a race with a still-starting integration.

    This is the transient case the old "one attempt per reload" gate lost: the
    TRV's integration finishes registering its entities between two ticks and
    the retry finds the guards it would otherwise have missed until reload.
    """
    clock = ManualClock(0.0)
    reader = InputReader(hass, _structure(), clock)  # climate.trv: nothing yet
    reader.resolve_device_guards()
    assert reader.guards_resolved is False
    assert reader.sched_entity is None

    assert _register_trv_device(hass) == "climate.trv"
    clock.advance(_GUARD_RETRY_SPACING_S[0])
    reader.resolve_device_guards()

    assert reader.guards_resolved
    assert reader.sched_entity == "switch.trv_schedule"
    assert reader.valve_entity == "number.trv_valve_opening_degree"


async def test_snapshot_drives_the_retry_on_the_injected_clock(
    hass: HomeAssistant,
) -> None:
    """The backoff anchor is snapshot()'s own unified instant.

    Ten ticks on a frozen ManualClock cost exactly ONE registry access; only
    advancing the injected clock releases the next attempt.  (A wall/monotonic
    read inside the method would make this untestable and would break the
    module's "one instant per pre-await segment" rule.)
    """
    clock = ManualClock(0.0)
    reader = InputReader(hass, _structure(), clock)  # climate.trv absent entirely

    with patch(
        "homeassistant.helpers.entity_registry.async_get", wraps=er.async_get
    ) as spy:
        for _ in range(10):
            reader.snapshot()
        assert spy.call_count == 1
        clock.advance(_GUARD_RETRY_SPACING_S[0])
        reader.snapshot()
        assert spy.call_count == 2
    assert reader.guards_resolved is False


# --- positioned post-await reads -----------------------------------------------


async def test_positioned_actuator_read_captures_one_object(
    hass: HomeAssistant,
) -> None:
    _set_actuator(hass)
    reader = _reader(hass)

    raw = reader.actuator_state()
    assert raw is not None and raw.state == "heat"

    snap = reader.read_actuator()
    assert snap.state == "heat"
    assert snap.hvac_modes == ("heat", "off")
    assert snap.actual_setpoint == 18.0
    assert snap.target_temperature_step == 0.5
    assert snap.min_temp == 5.0
    assert snap.max_temp == 30.0
    assert snap.hvac_action == "heating"
    assert snap.fan_mode == "auto"
    assert snap.fan_modes == ("auto", "low")
    assert snap.context_id == raw.context.id
    assert snap.current_temperature == 19.0
    assert snap.online

    # unavailable device: the _num_attr gate blanks the setpoint, while the
    # raw isinstance limits and the ungated current_temperature survive —
    # exactly today's per-site parse asymmetry
    _set_actuator(hass, state="unavailable")
    snap = reader.read_actuator()
    assert not snap.online
    assert snap.actual_setpoint is None
    assert snap.min_temp == 5.0
    assert snap.current_temperature == 19.0

    # unparseable current_temperature -> None (plain float() semantics)
    _set_actuator(hass, current_temperature="bogus")
    assert reader.read_actuator().current_temperature is None

    # never-registered actuator -> all-None snapshot
    assert actuator_snapshot(None).state is None
    assert actuator_snapshot(None).hvac_modes == ()
    assert not actuator_snapshot(None).online


async def test_positioned_feed_select_and_valve_reads(hass: HomeAssistant) -> None:
    reader = _reader(hass)

    # ext-temp feed target: only "unavailable" (or missing) means offline;
    # the number is write-only, so "unknown" is fine (ADR-0029)
    assert reader.ext_feed_target_ok(None) is False
    assert reader.ext_feed_target_ok("number.ghost") is False
    hass.states.async_set("number.trv_ext", "unavailable")
    assert reader.ext_feed_target_ok("number.trv_ext") is False
    hass.states.async_set("number.trv_ext", "unknown")
    assert reader.ext_feed_target_ok("number.trv_ext") is True
    hass.states.async_set("number.trv_ext", "19.0")
    assert reader.ext_feed_target_ok("number.trv_ext") is True

    # sensor-select: None without a discovered select or without a State
    assert reader.ext_select_state() is None
    reader.sensor_select = "select.trv_sensor"
    assert reader.ext_select_state() is None
    hass.states.async_set(
        "select.trv_sensor", "internal", {"options": ["internal", "external"]}
    )
    assert reader.ext_select_state() == "internal"

    # valve steps: undiscovered -> (None, None); discovered -> numeric reads
    assert reader.valve_steps() == (None, None)
    reader.valve_closing_steps = "sensor.trv_closing_steps"
    reader.valve_idle_steps = "sensor.trv_idle_steps"
    hass.states.async_set("sensor.trv_closing_steps", "0")
    hass.states.async_set("sensor.trv_idle_steps", "5")
    assert reader.valve_steps() == (0.0, 5.0)


# --- configured ext-temp signature (bootstrap read half) -----------------------


async def test_configured_ext_temp_signature_merges_registry_and_state(
    hass: HomeAssistant,
) -> None:
    reader = _reader(hass)

    # registry-backed entity: original_device_class + unit from the registry
    dev_entry = MockConfigEntry(domain="demo", title="TRV Device")
    dev_entry.add_to_hass(hass)
    ent = er.async_get(hass).async_get_or_create(
        "number",
        "demo",
        "extnum",
        config_entry=dev_entry,
        suggested_object_id="trv_external_temperature",
        original_device_class="temperature",
        unit_of_measurement="°C",
    )
    assert reader.configured_ext_temp_signature(ent.entity_id) == (
        "temperature",
        "°C",
    )

    # state-only entity: the live attributes fill the gaps
    hass.states.async_set(
        "number.loose",
        "19.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    assert reader.configured_ext_temp_signature("number.loose") == (
        "temperature",
        "°C",
    )
    # neither registry nor state -> both unknown
    assert reader.configured_ext_temp_signature("number.ghost") == (None, None)

    # registry errors PROPAGATE — the "never block setup" boundary stays with
    # the caller (today's surrounding try in _validate_configured_ext_temp)
    with (
        patch(
            "homeassistant.helpers.entity_registry.async_get",
            side_effect=RuntimeError("registry down"),
        ),
        pytest.raises(RuntimeError),
    ):
        reader.configured_ext_temp_signature("number.loose")
