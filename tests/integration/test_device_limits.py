"""The climate entity publishes the ACTUATOR's setpoint envelope, not constants.

``min_temp`` / ``max_temp`` / ``target_temp_step`` used to be class attributes
(``FROST_FLOOR_C``, ``DEVICE_MAX_C``, 0.5), so the UI offered setpoints the
device cannot reach and hid the ones it can. They are properties now and
publish the INTERSECTION of the device's own limits with Poise's accepted hold
envelope ``[FROST_FLOOR_C, DEVICE_MAX_C]`` -- the range HA validates
``climate.set_temperature`` against, and the range ``set_override`` keeps
unchanged.

The four contracts pinned here: the constants still apply while no device
values are known, real device values are published, the frost floor is never
undercut, and a runtime change of the device is visible without a reload.

CI-only: needs the pytest-homeassistant-custom-component harness (no HA in the
dev sandbox).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DEVICE_MAX_C,
    DOMAIN,
    FROST_FLOOR_C,
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: True,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}

# The entity's published defaults before this change -- the fallback contract.
FALLBACK_STEP_C = 0.5


def _room(hass: HomeAssistant, temp: float = 19.0) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(temp),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )


def _actuator(hass: HomeAssistant, state: str = "heat", **attrs: Any) -> None:
    """Set the actuator state; ``attrs`` overrides/adds the reported limits."""
    hass.states.async_set(
        "climate.trv",
        state,
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 19.0,
            **attrs,
        },
    )


async def _setup_zone(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _climate_entity_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    reg = er.async_get(hass)
    for e in er.async_entries_for_config_entry(reg, entry.entry_id):
        if e.domain == "climate":
            return e.entity_id
    raise AssertionError("no climate entity for entry")


def _envelope(hass: HomeAssistant, eid: str) -> tuple[float, float, float]:
    """(min_temp, max_temp, target_temp_step) as published in the state.

    All three are HA *capability* attributes, so they are part of the state
    even while the entity reports unavailable -- exactly why a ``None`` or a
    raise in these properties would be fatal rather than cosmetic.
    """
    attrs = hass.states.get(eid).attributes
    return attrs["min_temp"], attrs["max_temp"], attrs["target_temp_step"]


async def _mock_write_services(hass: HomeAssistant) -> None:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")


# --- fallback: no device values -------------------------------------------


async def test_offline_actuator_keeps_the_constants(hass: HomeAssistant) -> None:
    """An unavailable device reports no attributes -> today's constants."""
    await _mock_write_services(hass)
    _room(hass)
    hass.states.async_set("climate.trv", "unavailable", {})
    entry = await _setup_zone(hass)

    eid = _climate_entity_id(hass, entry)
    assert _envelope(hass, eid) == (FROST_FLOOR_C, DEVICE_MAX_C, FALLBACK_STEP_C)


async def test_device_without_limit_attributes_keeps_the_constants(
    hass: HomeAssistant,
) -> None:
    """An online device that simply reports no limits -> today's constants."""
    await _mock_write_services(hass)
    _room(hass)
    _actuator(hass)  # no min_temp / max_temp / target_temp_step
    entry = await _setup_zone(hass)

    eid = _climate_entity_id(hass, entry)
    assert _envelope(hass, eid) == (FROST_FLOOR_C, DEVICE_MAX_C, FALLBACK_STEP_C)


async def test_non_finite_limits_are_rejected_like_absent_ones(
    hass: HomeAssistant,
) -> None:
    """NaN limits must read as "absent", never fail-open the envelope."""
    await _mock_write_services(hass)
    _room(hass)
    nan = float("nan")
    _actuator(hass, min_temp=nan, max_temp=nan, target_temp_step=nan)
    entry = await _setup_zone(hass)

    eid = _climate_entity_id(hass, entry)
    assert _envelope(hass, eid) == (FROST_FLOOR_C, DEVICE_MAX_C, FALLBACK_STEP_C)


async def test_zero_step_falls_back(hass: HomeAssistant) -> None:
    """A 0 step would make HA's stepping arithmetic degenerate."""
    await _mock_write_services(hass)
    _room(hass)
    _actuator(hass, min_temp=5, max_temp=30, target_temp_step=0)
    entry = await _setup_zone(hass)

    assert _envelope(hass, _climate_entity_id(hass, entry))[2] == FALLBACK_STEP_C


# --- the device's own values ----------------------------------------------


async def test_device_values_are_published(hass: HomeAssistant) -> None:
    """A high-minimum AC: 16..28 with a 1 K step reaches the UI verbatim."""
    await _mock_write_services(hass)
    _room(hass)
    _actuator(hass, min_temp=16, max_temp=28, target_temp_step=1.0)
    entry = await _setup_zone(hass)

    assert _envelope(hass, _climate_entity_id(hass, entry)) == (16.0, 28.0, 1.0)


async def test_fine_grained_device_step_is_published(hass: HomeAssistant) -> None:
    """The step comes from the HA wire key ``target_temp_step`` (review A.4).

    A device advertising 0.1 K must not be coarsened to the old 0.5 default --
    which is what reading the *property* name instead of the wire key would do.
    """
    await _mock_write_services(hass)
    _room(hass)
    _actuator(hass, min_temp=5, max_temp=30, target_temp_step=0.1)
    entry = await _setup_zone(hass)

    assert _envelope(hass, _climate_entity_id(hass, entry))[2] == 0.1


# --- Poise's own safety limits --------------------------------------------


async def test_frost_floor_wins_over_a_lower_device_minimum(
    hass: HomeAssistant,
) -> None:
    """Zigbee TRVs commonly report 5 °C; Poise never holds below the frost floor.

    Publishing the raw 5 °C would offer a setpoint ``set_override`` silently
    pulls back up to 7 °C -- the published minimum must be the value the hold
    actually keeps.
    """
    await _mock_write_services(hass)
    _room(hass)
    _actuator(hass, min_temp=5, max_temp=30, target_temp_step=0.5)
    entry = await _setup_zone(hass)

    low, high, _ = _envelope(hass, _climate_entity_id(hass, entry))
    assert (low, high) == (FROST_FLOOR_C, DEVICE_MAX_C)
    # and the device value really was seen (it is simply not the binding one)
    assert entry.runtime_data.input_reader.read_actuator().min_temp == 5.0


async def test_device_maximum_above_poises_ceiling_is_capped(
    hass: HomeAssistant,
) -> None:
    """A 35 °C device ceiling would advertise setpoints sanitize pulls to 30 °C."""
    await _mock_write_services(hass)
    _room(hass)
    _actuator(hass, min_temp=16, max_temp=35, target_temp_step=0.5)
    entry = await _setup_zone(hass)

    low, high, _ = _envelope(hass, _climate_entity_id(hass, entry))
    assert (low, high) == (16.0, DEVICE_MAX_C)


async def test_envelope_never_inverts(hass: HomeAssistant) -> None:
    """A device whose whole range sits above the ceiling still yields min <= max.

    An inverted pair makes the HA slider unusable and fails every set call, so
    the minimum is clamped down to the published maximum.
    """
    await _mock_write_services(hass)
    _room(hass)
    _actuator(hass, min_temp=31, max_temp=35, target_temp_step=0.5)
    entry = await _setup_zone(hass)

    low, high, _ = _envelope(hass, _climate_entity_id(hass, entry))
    assert low == high == DEVICE_MAX_C


async def test_published_bounds_are_kept_by_a_manual_hold(
    hass: HomeAssistant,
) -> None:
    """The envelope's meaning: a bound is a value the hold keeps UNCHANGED.

    HA rejects anything outside ``[min_temp, max_temp]`` with
    ``temp_out_of_range``; everything it lets through is sanitised by
    ``set_override``. Both bounds must therefore survive that sanitising, and
    a value just outside must not (else the UI would silently lie).
    """
    await _mock_write_services(hass)
    _room(hass)
    _actuator(hass, min_temp=5, max_temp=35, target_temp_step=0.5)
    entry = await _setup_zone(hass)
    coord = entry.runtime_data

    low, high, _ = _envelope(hass, _climate_entity_id(hass, entry))
    for bound in (low, high):
        coord.set_override(bound)
        assert coord.runtime.user.override == bound

    coord.set_override(low - 1.0)
    assert coord.runtime.user.override == low
    coord.set_override(high + 1.0)
    assert coord.runtime.user.override == high


# --- runtime change --------------------------------------------------------


async def test_envelope_follows_the_device_at_runtime(hass: HomeAssistant) -> None:
    """Device comes online / is swapped: the published envelope moves with it.

    The whole point of the property rewrite -- a class attribute is read once
    per class, so an actuator that publishes its limits only after it has
    joined the network (or a reconfigure onto a different device) would keep
    the stale constants forever.
    """
    await _mock_write_services(hass)
    _room(hass)
    hass.states.async_set("climate.trv", "unavailable", {})
    entry = await _setup_zone(hass)
    eid = _climate_entity_id(hass, entry)

    assert _envelope(hass, eid) == (FROST_FLOOR_C, DEVICE_MAX_C, FALLBACK_STEP_C)

    # the device joins and reports its real limits
    _actuator(hass, min_temp=16, max_temp=28, target_temp_step=1.0)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _envelope(hass, eid) == (16.0, 28.0, 1.0)

    # ... and it drops off again -- back to the usable fallback
    hass.states.async_set("climate.trv", "unavailable", {})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _envelope(hass, eid) == (FROST_FLOOR_C, DEVICE_MAX_C, FALLBACK_STEP_C)
