"""ADR-0059 override-lifecycle glue, end to end (CI-only).

Covers the manual-hold + timed-Boost lifecycle that the coordinator/glue own: the
announced wall-clock expiry at set-time (§4), the schedule/timer expiry policies
(§1), the ``poise_override_ended`` event + the ``poise.resume_schedule`` service
(§6), the "OFF keeps the hold / an active mode resumes" rule (§5), the timed
Boost restore (§2), the minor_version 1->2 policy stamp (§7) and the wall-clock
persistence of the whole lifecycle across a reload (review C5).

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.climate import HVACMode
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_mock_service,
)

from custom_components.poise import async_migrate_entry
from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOOST_DURATION_MIN,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_OVERRIDE_END_ON_PRESENCE,
    CONF_OVERRIDE_MAX_H,
    CONF_OVERRIDE_POLICY,
    CONF_OVERRIDE_TIMER_H,
    CONF_PRESENCE_HOME,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
    FROST_FLOOR_C,
    OVERRIDE_POLICY_SCHEDULE,
    OVERRIDE_POLICY_TIMER,
)
from custom_components.poise.control.override import OverrideMode


def _room_data(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_SETBACK_DELTA: 3.0,
        **extra,
    }


def _states(hass: HomeAssistant, *, room: float = 19.0, sp: float = 15.0) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


async def _setup_zone(
    hass: HomeAssistant,
    *,
    data: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=data or _room_data(),
        options=options or {},
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _climate_eid(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    reg = er.async_get(hass)
    for e in er.async_entries_for_config_entry(reg, entry.entry_id):
        if e.domain == "climate":
            return e.entity_id
    raise AssertionError("no climate entity for entry")


def _climate_entity(hass: HomeAssistant, eid: str) -> Any:
    """The live poise climate entity object, to drive its service methods."""
    component = hass.data[CLIMATE_DOMAIN]
    return next(e for e in component.entities if e.entity_id == eid)


# --- §4: set_override announces the expiry and keeps the requested value -------
async def test_set_override_announces_expiry_keeps_requested(
    hass: HomeAssistant,
) -> None:
    """set_override stamps override_expires_at (~ now + timer_h) and surfaces the
    pre-clamp requested value + active/policy on the climate entity (ADR-0059 §4)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(
        hass,
        options={
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER,
            CONF_OVERRIDE_TIMER_H: 3.0,
        },
    )
    coord = entry.runtime_data
    eid = _climate_eid(hass, entry)

    before = dt_util.utcnow().timestamp()
    coord.set_override(24.0)
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord._override_policy == OVERRIDE_POLICY_TIMER
    assert coord._override_expires_at is not None
    assert abs(coord._override_expires_at - (before + 3.0 * 3600.0)) < 60.0
    state = hass.states.get(eid)
    assert state is not None
    assert state.attributes["override_requested"] == 24.0
    assert state.attributes["override_active"] is True
    assert state.attributes["override_policy"] == OVERRIDE_POLICY_TIMER
    assert state.attributes["override_expires_at"] is not None


# --- §1: the schedule policy ends at the next switchpoint (capped by max_h) -----
async def test_schedule_policy_expiry_reflects_switchpoint(
    hass: HomeAssistant,
) -> None:
    """With a real comfort window + schedule policy, the hold expiry is the next
    switchpoint, never past the override_max_h safety cap (ADR-0059 §1)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    data = _room_data(
        **{
            CONF_COMFORT_START: "06:00:00",
            CONF_COMFORT_END: "22:00:00",
            CONF_SETBACK_DELTA: 3.0,
        }
    )
    entry = await _setup_zone(
        hass,
        data=data,
        options={
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_SCHEDULE,
            CONF_OVERRIDE_MAX_H: 8.0,
            CONF_OVERRIDE_TIMER_H: 2.0,
        },
    )
    coord = entry.runtime_data

    set_at = dt_util.utcnow().timestamp()
    coord.set_override(22.0)

    assert coord._override_policy == OVERRIDE_POLICY_SCHEDULE
    assert coord._override_expires_at is not None
    assert set_at < coord._override_expires_at <= set_at + 8.0 * 3600.0 + 1.0


# --- §1: a timer hold expires, fires poise_override_ended and clears ------------
async def test_timer_expiry_fires_event_and_clears(hass: HomeAssistant) -> None:
    """Driving the announced wall-clock expiry into the past then ticking clears
    the hold and fires one poise_override_ended (reason expired_timer)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(
        hass,
        options={
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER,
            CONF_OVERRIDE_TIMER_H: 2.0,
        },
    )
    coord = entry.runtime_data

    coord.set_override(24.0)
    assert coord._override is not None
    events = async_capture_events(hass, "poise_override_ended")
    coord._override_expires_at = dt_util.utcnow().timestamp() - 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord._override is None
    assert coord._override_expires_at is None
    assert len(events) == 1
    assert events[0].data["reason"] == "expired_timer"
    assert events[0].data["entry_id"] == entry.entry_id


# --- §6: poise.resume_schedule clears a targeted zone (reason user_resume) ------
async def test_resume_schedule_service_clears_targeted_zone(
    hass: HomeAssistant,
) -> None:
    """A targeted poise.resume_schedule drops the hold + preset and announces the
    return to automatic (ADR-0059 §6)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(hass)
    coord = entry.runtime_data
    eid = _climate_eid(hass, entry)

    coord.set_override(22.0)
    assert coord._override is not None
    assert hass.services.has_service(DOMAIN, "resume_schedule")
    events = async_capture_events(hass, "poise_override_ended")

    await hass.services.async_call(
        DOMAIN, "resume_schedule", {ATTR_ENTITY_ID: eid}, blocking=True
    )
    await hass.async_block_till_done()

    assert coord._override is None
    assert coord.preset is OverrideMode.NONE
    assert any(e.data["reason"] == "user_resume" for e in events)


# --- §6: the no-target resume sweeps every room zone and skips the hub ----------
async def test_resume_schedule_all_zones_skips_hub(hass: HomeAssistant) -> None:
    """The no-target resume touches every room zone; a system hub entry is skipped
    (the _is_system guard) without crashing the sweep (ADR-0059 §6)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(hass)
    coord = entry.runtime_data
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM},
        title="Poise System",
    )
    hub.add_to_hass(hass)

    coord.set_override(22.0)
    events = async_capture_events(hass, "poise_override_ended")

    await hass.services.async_call(DOMAIN, "resume_schedule", {}, blocking=True)
    await hass.async_block_till_done()

    assert coord._override is None
    assert any(
        e.data["reason"] == "user_resume" and e.data["entry_id"] == entry.entry_id
        for e in events
    )


# --- §5: set_hvac_mode(OFF) keeps the hold; an active mode clears it ------------
async def test_off_keeps_hold_active_mode_clears(hass: HomeAssistant) -> None:
    """OFF must not clear a manual hold (enables "off, then resume later"); an
    ACTIVE mode returns to automatic and clears it (reason mode_change, §5)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(
        hass,
        options={
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER,
            CONF_OVERRIDE_TIMER_H: 2.0,
        },
    )
    coord = entry.runtime_data
    entity = _climate_entity(hass, _climate_eid(hass, entry))

    coord.set_override(23.0)
    assert coord._override is not None
    events = async_capture_events(hass, "poise_override_ended")

    await entity.async_set_hvac_mode(HVACMode.OFF)
    await hass.async_block_till_done()
    assert coord._override is not None
    assert not events

    await entity.async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()
    assert coord._override is None
    assert any(e.data["reason"] == "mode_change" for e in events)


# --- §2: Boost is the one timed preset; expiry restores the frozen preset -------
async def test_boost_is_timed_and_restores_previous_preset(
    hass: HomeAssistant,
) -> None:
    """set_preset(BOOST) arms a wall-clock expiry and freezes the prior preset;
    the tick past expiry restores it and drops the Boost timer (ADR-0059 §2)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(hass, options={CONF_BOOST_DURATION_MIN: 60.0})
    coord = entry.runtime_data

    coord.set_preset(OverrideMode.COMFORT)
    coord.set_preset(OverrideMode.BOOST)
    assert coord.preset is OverrideMode.BOOST
    assert coord._boost_expires_at is not None
    assert coord._boost_prev_preset is OverrideMode.COMFORT

    coord._boost_expires_at = dt_util.utcnow().timestamp() - 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord.preset is OverrideMode.COMFORT
    assert coord._boost_expires_at is None


# --- §7: a pre-0.162 (minor_version 1) zone is stamped with the timer policy ----
async def test_migration_minor_1_to_2_stamps_timer_policy(
    hass: HomeAssistant,
) -> None:
    """A V2 room stored below minor_version 2 (no explicit policy) is pinned to the
    fixed-timer hold and its (version, minor_version) becomes (2, 2) (ADR-0059 §7)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=_room_data(),
        version=2,
        minor_version=1,
        title="Test Room",
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    assert entry.minor_version == 2
    assert entry.options[CONF_OVERRIDE_POLICY] == OVERRIDE_POLICY_TIMER


# --- C5: the whole hold lifecycle survives a reload on wall-clock time ----------
async def test_reload_restores_hold_policy_and_expiry(hass: HomeAssistant) -> None:
    """A reload rebuilds the coordinator; the persisted hold value, requested,
    policy and announced expiry restore verbatim on wall-clock time (review C5)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(
        hass,
        options={
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER,
            CONF_OVERRIDE_TIMER_H: 4.0,
        },
    )
    coord = entry.runtime_data

    coord.set_override(23.5)
    expires = coord._override_expires_at
    assert expires is not None

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    restored = entry.runtime_data
    assert restored is not coord  # a genuine reload built a fresh coordinator
    assert restored._override == 23.5
    assert restored._override_requested == 23.5
    assert restored._override_policy == OVERRIDE_POLICY_TIMER
    assert restored._override_expires_at is not None
    assert abs(restored._override_expires_at - expires) < 1.0


# --- §1/ADR-0058: a house-gate presence flip ends the hold (presence_change) ----
async def test_presence_change_ends_hold(hass: HomeAssistant) -> None:
    """With override_end_on_presence_change on, flipping the house gate home->away
    ends the manual hold "until the next change" (ADR-0059 §1 / ADR-0058)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    hass.states.async_set("person.someone", "home")
    entry = await _setup_zone(
        hass,
        options={
            CONF_PRESENCE_HOME: "person.someone",
            CONF_OVERRIDE_END_ON_PRESENCE: True,
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER,
            CONF_OVERRIDE_TIMER_H: 4.0,
        },
    )
    coord = entry.runtime_data

    coord.set_override(22.0)
    assert coord._override is not None
    events = async_capture_events(hass, "poise_override_ended")

    hass.states.async_set("person.someone", "not_home")
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord._override is None
    assert any(e.data["reason"] == "presence_change" for e in events)


# --- Schedy#35: hold expiry under an open window returns to the window floor ----
async def test_expiry_under_open_window_returns_to_plan_not_manual(
    hass: HomeAssistant,
) -> None:
    """A manual hold whose timer lapses while the window is open expires silently:
    _expire_timed_states runs before the solver even under an active layer, so the
    hold clears and the command stays at the window frost/mould floor -- it never
    snaps back to the stale held value (Schedy#35)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})
    entry = await _setup_zone(
        hass,
        data=_room_data(**{CONF_WINDOW_SENSOR: "binary_sensor.window"}),
        options={
            CONF_OVERRIDE_POLICY: OVERRIDE_POLICY_TIMER,
            CONF_OVERRIDE_TIMER_H: 2.0,
        },
    )
    coord = entry.runtime_data
    eid = _climate_eid(hass, entry)

    coord.set_override(24.0)
    assert coord._override == 24.0
    events = async_capture_events(hass, "poise_override_ended")

    # the window opens AND the announced expiry falls into the past: the tick must
    # expire the hold under the active window layer, not chase the held value.
    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})
    coord._override_expires_at = dt_util.utcnow().timestamp() - 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert coord._override is None
    assert coord._override_expires_at is None
    assert any(e.data["reason"] == "expired_timer" for e in events)
    state = hass.states.get(eid)
    assert state is not None
    assert state.attributes["override_active"] is False
    # the window layer keeps regulating at the frost/mould floor, NOT the held 24.0
    assert abs(coord._last_target - FROST_FLOOR_C) < 0.05


# --- VT#1961: a second Boost press keeps the first frozen preset (not BOOST) ---
async def test_double_boost_keeps_frozen_previous_preset(
    hass: HomeAssistant,
) -> None:
    """The first set_preset(BOOST) freezes the pre-boost preset as the restore
    target; pressing Boost again only re-arms the timer -- it must NOT re-freeze
    BOOST onto itself, so the return target stays the original preset (VT#1961)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass)
    entry = await _setup_zone(hass, options={CONF_BOOST_DURATION_MIN: 60.0})
    coord = entry.runtime_data

    coord.set_preset(OverrideMode.COMFORT)
    coord.set_preset(OverrideMode.BOOST)
    assert coord.preset is OverrideMode.BOOST
    assert coord._boost_prev_preset is OverrideMode.COMFORT

    # a second Boost press re-arms from now but must leave the frozen restore
    # target untouched -- never stacking BOOST onto itself (VT#1961).
    coord.set_preset(OverrideMode.BOOST)
    assert coord.preset is OverrideMode.BOOST
    assert coord._boost_prev_preset is OverrideMode.COMFORT

    # and the expiry restores that original preset, not BOOST
    coord._boost_expires_at = dt_util.utcnow().timestamp() - 1.0
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.preset is OverrideMode.COMFORT
    assert coord._boost_expires_at is None
