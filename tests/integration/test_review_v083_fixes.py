"""Integration tests pinning the P0 fixes from the external v0.83 review.

H1 — a cooling-capable actuator must be nudged into ``cool`` (not ``heat``) and
     receive the cool setpoint when Poise decides to cool.
H3 — the system hub must drop a zone whose coordinator's last update failed
     (``last_update_success`` is False) instead of calling for heat on stale data.
H2 — with an identified model and optimal-stop enabled, the comfort-phase coast
     branch is reachable (a model is built during comfort, not only during setback).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_BOILER_COUNT_THRESHOLD,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_END,
    CONF_COMFORT_START,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    DOMAIN,
    ENTRY_TYPE_SYSTEM,
)


def _base(**extra: Any) -> dict[str, Any]:
    return {
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
        **extra,
    }


async def _setup(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --------------------------------------------------------------------------- H1
async def test_cooling_nudges_cool_not_heat(hass: HomeAssistant) -> None:
    """H1: when Poise cools, it commands set_hvac_mode('cool'), never 'heat'."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_hvac = async_mock_service(hass, "climate", "set_hvac_mode")
    # hot room + warm outside (clears the cool>=16 °C outdoor lockout) + a
    # cool-capable TRV left in 'off' so the mode nudge fires.
    hass.states.async_set("sensor.room_temp", "33.0", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "30.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "off",
        {
            "hvac_modes": ["heat", "cool", "off"],
            "temperature": 24.0,
            "current_temperature": 33.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 35,
        },
    )
    await _setup(
        hass,
        _base(
            **{CONF_CLIMATE_MODE: "cool_only", CONF_OUTDOOR_SENSOR: "sensor.outdoor"}
        ),
    )

    cool_nudges = [c for c in set_hvac if c.data.get("hvac_mode") == "cool"]
    heat_nudges = [c for c in set_hvac if c.data.get("hvac_mode") == "heat"]
    assert cool_nudges, "cooling did not nudge the actuator into 'cool'"
    assert not heat_nudges, "cooling wrongly nudged the actuator into 'heat'"
    assert set_temp, "no setpoint written while cooling"
    # the cool setpoint is below the hot room, not floored up to a heat target
    assert set_temp[-1].data["temperature"] < 33.0


# --------------------------------------------------------------------------- H3
async def test_hub_drops_zone_with_failed_update(hass: HomeAssistant) -> None:
    """H3: a zone whose last coordinator update failed is excluded from the hub."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "16.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 16.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    zone = await _setup(hass, _base(**{CONF_CONTROLS_BOILER: True}))

    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_COUNT_THRESHOLD: 1},
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    # cold room → the healthy zone calls for heat and the hub counts it
    await hub.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hub.runtime_data.data["controlling_zones"] >= 1

    # now the zone's coordinator update fails (sensor/actuator glitch): the hub
    # must NOT keep calling for heat on the stale snapshot
    zone.runtime_data.last_update_success = False
    await hub.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hub.runtime_data.data["controlling_zones"] == 0


# --------------------------------------------------------------------------- H2
async def test_optimal_stop_coast_reachable_in_comfort(hass: HomeAssistant) -> None:
    """H2: an identified EKF builds a model during comfort, enabling the coast path.

    Before the fix the model was only built during setback, so the comfort-phase
    coast branch (optimal-stop) was dead. We force identification and assert the
    coordinator computes a coast decision (``coasting`` present) without error.
    """
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "22.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 22.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = await _setup(hass, _base())
    coord = entry.runtime_data

    # force the EKF past its identification gate (as the closed-loop harness does)
    ekf = coord._ekf
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.p[0][0] = 0.01
    assert ekf.identified is True

    await coord.async_refresh()
    await hass.async_block_till_done()

    # the comfort tick reached the coast logic and produced a boolean decision
    assert coord.data.get("coasting") in (True, False)
    assert coord.data.get("available") is True


# ----------------------------------------------------- Silver: log-when-unavailable
async def test_sensor_loss_and_recovery_log_once_each(
    hass: HomeAssistant, caplog
) -> None:
    """A lost room sensor logs WARNING once, recovery logs INFO once (not per tick)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "20.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 20.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = await _setup(hass, _base())
    coord = entry.runtime_data
    logger = "custom_components.poise.coordinator"

    with caplog.at_level(logging.INFO, logger=logger):
        # sensor disappears; refresh twice — only ONE loss warning despite two ticks
        hass.states.async_set("sensor.room_temp", "unavailable")
        await coord.async_refresh()
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert coord.data.get("available") is False
        warns = [
            r
            for r in caplog.records
            if r.name == logger
            and r.levelno == logging.WARNING
            and "unavailable" in r.getMessage()
        ]
        assert len(warns) == 1, f"expected exactly one loss warning, got {len(warns)}"

        # sensor returns; exactly ONE recovery info
        hass.states.async_set(
            "sensor.room_temp", "20.0", {"device_class": "temperature"}
        )
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert coord.data.get("available") is True
        recoveries = [
            r
            for r in caplog.records
            if r.name == logger
            and r.levelno == logging.INFO
            and "is back" in r.getMessage()
        ]
        assert len(recoveries) == 1, f"expected one recovery, got {len(recoveries)}"


# --------------------------------------------------------------- M9: via_device
async def test_zone_device_nests_under_hub(hass: HomeAssistant) -> None:
    """M9: with a system hub configured, a zone device links to it via via_device."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    # the hub is set up first so its device exists when the zone links to it
    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_COUNT_THRESHOLD: 1},
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("sensor.room_temp", "20.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 20.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    zone = await _setup(hass, _base())

    assert zone.runtime_data.via_device_id == (DOMAIN, hub.entry_id)
    reg = dr.async_get(hass)
    zone_dev = reg.async_get_device(identifiers={(DOMAIN, zone.entry_id)})
    hub_dev = reg.async_get_device(identifiers={(DOMAIN, hub.entry_id)})
    assert zone_dev is not None and hub_dev is not None
    assert zone_dev.via_device_id == hub_dev.id  # nested under the hub


async def test_zone_without_hub_has_no_via_device(hass: HomeAssistant) -> None:
    """A standalone zone (no hub) sets no via_device link."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "20.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 20.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    zone = await _setup(hass, _base())
    assert zone.runtime_data.via_device_id is None


# ------------------------------------------------ H3 residual: age-based staleness
async def test_hub_drops_silently_stale_zone(hass: HomeAssistant) -> None:
    """H3/ADR-0038: a zone whose snapshot is too old is dropped even when its
    coordinator still reports success (a silently hung update loop)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "16.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 16.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    zone = await _setup(hass, _base(**{CONF_CONTROLS_BOILER: True}))

    hub = MockConfigEntry(
        domain=DOMAIN,
        unique_id="poise_system",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_COUNT_THRESHOLD: 1},
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()

    # cold room → the fresh zone calls for heat and the hub counts it
    await hub.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hub.runtime_data.data["controlling_zones"] >= 1

    # the update still "succeeds" but the snapshot is far older than the staleness
    # window — the hub must stop calling for heat on it
    assert zone.runtime_data.last_update_success is True
    zone.runtime_data.data["mono_ts"] = zone.runtime_data._clock.monotonic() - 1000.0
    await hub.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hub.runtime_data.data["controlling_zones"] == 0


# --------------------------------------------- H2 (strong): coasting becomes True
async def test_optimal_stop_coasts_near_window_end(
    hass: HomeAssistant, freezer
) -> None:
    """H2: identified EKF + comfort window ending soon + warm room over a cold
    outside → the wiring actually produces ``coasting`` True (not just no-crash)."""
    freezer.move_to("2026-01-15 12:00:00")  # frozen so the schedule is deterministic
    now_local = dt_util.now()
    start = (now_local - timedelta(hours=2)).strftime("%H:%M")
    end = (now_local + timedelta(minutes=5)).strftime("%H:%M")

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("sensor.room_temp", "25.0", {"device_class": "temperature"})
    hass.states.async_set("sensor.outdoor", "4.0", {"device_class": "temperature"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 25.0,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = await _setup(
        hass,
        _base(
            **{
                CONF_COMFORT_START: start,
                CONF_COMFORT_END: end,
                CONF_OUTDOOR_SENSOR: "sensor.outdoor",
            }
        ),
    )
    coord = entry.runtime_data
    ekf = coord._ekf
    ekf.n_idle = 1000
    ekf.n_heating = 1000
    ekf.p[0][0] = 0.01
    assert ekf.identified is True

    await coord.async_refresh()
    await hass.async_block_till_done()

    # warm room far above the lower comfort edge with the window ending in ~5 min
    # and a cold outside → stop heating now and coast down
    assert coord.data.get("coasting") is True
