"""Review write-floor glue: window vs. override, the mould-floor window
suppression (P2-1) and the actuator ``min_temp`` write floor (P3-1).

These drive the real actuating path (``_run_once`` -> ``resolve_write_target``
-> ``actuator.write``) and assert against the recorded ``climate.set_temperature``
/ ``climate.set_hvac_mode`` calls -- the glue the pure resolver tests can't reach.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
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
    CONF_HUMIDITY_SENSOR,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_SENSOR,
    DOMAIN,
    FROST_FLOOR_C,
)


def _room_data(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_WINDOW_SENSOR: "binary_sensor.window",
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


def _states(
    hass: HomeAssistant,
    *,
    room: float,
    sp: float,
    window_state: str = "off",
    min_temp: float = 5.0,
    rh: float | None = None,
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        "binary_sensor.window", window_state, {"device_class": "window"}
    )
    if rh is not None:
        hass.states.async_set(
            "sensor.room_rh",
            str(rh),
            {"device_class": "humidity", "unit_of_measurement": "%"},
        )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": sp,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": min_temp,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, *, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_p1_1_window_beats_active_override(hass: HomeAssistant) -> None:
    """P1-1: a window opening while a manual hold is active drives the write to
    the frost floor -- never the held value (window > override). A heat-capable
    TRV parks in ``heat`` at the floor (frost held by heating), never ``off``."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0, window_state="off")
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    # re-arm recorders AFTER setup so the real climate services don't shadow the
    # pre-setup mocks (see test_override_mode for the full rationale).
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")

    # a manual hold is active and being written...
    coord.set_override(24.0)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert set_temp, "the active hold should have been written first"
    held = set_temp[-1].data["temperature"]
    assert held > FROST_FLOOR_C + 5, "precondition: the hold is well above the floor"

    # ...then the window opens: the write collapses to the floor + off.
    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})
    await coord.async_refresh()
    await hass.async_block_till_done()

    # a heat-capable TRV is parked in heat at the floor (frost held by heating);
    # "off" is the cool-only case (V1 / resolve_desired_mode), so never here.
    assert not [c for c in set_mode if c.data.get("hvac_mode") == "off"]
    assert abs(set_temp[-1].data["temperature"] - FROST_FLOOR_C) < 0.6, (
        f"window write must be the frost floor, not the held {held}"
    )
    assert set_temp[-1].data["temperature"] < 12


async def test_p2_1_mould_floor_suppressed_under_fresh_window(
    hass: HomeAssistant,
) -> None:
    """P2-1: a humid room whose mould floor is ~20-24 C must, in the first 30 min
    of an open window, be written at ~frost floor (mould component suppressed) --
    while the diagnostics ``mould_floor`` keeps the real, unsuppressed value."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    # high RH at a mild room -> mould_min_air_temperature is well above frost.
    _states(hass, room=22.0, sp=21.0, window_state="off", rh=85.0)
    entry = await _setup(
        hass, data=_room_data(**{CONF_HUMIDITY_SENSOR: "sensor.room_rh"})
    )
    coord: Any = entry.runtime_data

    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    # the window opens: this is the rising edge, so t_open = 0 < 30 min.
    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert set_temp, "expected a write on the window-open tick"
    assert set_temp[-1].data["temperature"] <= FROST_FLOOR_C + 1.0, (
        "the mould write floor must be suppressed toward frost under a fresh window"
    )
    # diagnostics still expose the REAL (unsuppressed) mould floor.
    assert coord.data is not None
    assert coord.data["mould_floor"] is not None
    assert coord.data["mould_floor"] > FROST_FLOOR_C + 8, (
        "the diagnostic mould_floor must keep the real value, not the write floor"
    )


async def test_p3_1_device_min_temp_is_a_write_floor(hass: HomeAssistant) -> None:
    """P3-1: an actuator whose ``min_temp`` (17) exceeds the frost floor must never
    be written below its own minimum -- the coordinator now passes ``device_min``,
    so the window floor is clamped up to 17 instead of the sub-min frost value."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0, window_state="off", min_temp=17.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    # window opens: the bare floor would be frost (7), but device_min raises it.
    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert set_temp, "expected a write on the window-open tick"
    assert set_temp[-1].data["temperature"] >= 17.0 - 0.05, (
        "the write must respect the actuator min_temp (no sub-min write)"
    )


async def test_p3_1_actuator_without_min_temp_writes_bare_floor(
    hass: HomeAssistant,
) -> None:
    """P3-1 counterpart: an actuator that reports no ``min_temp`` yields
    ``device_min=None`` -- the write falls back to the bare frost floor (no clamp)."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0, window_state="off")
    # strip min_temp from the actuator so _device_min() returns None
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 19.0,
            "target_temperature_step": 0.5,
            "max_temp": 30,
        },
    )
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert set_temp, "expected a write on the window-open tick"
    assert set_temp[-1].data["temperature"] < 12  # bare frost floor, no min clamp


async def test_p2_8_heating_failure_is_a_repair_issue(hass: HomeAssistant) -> None:
    """P2-8: a heating failure is surfaced as the translated ``heating_failure``
    repair issue (raised, then cleared on recovery) -- not an English notification."""
    from homeassistant.helpers import issue_registry as ir

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    reg = ir.async_get(hass)
    issue_id = f"heating_failure_{coord._entry_id}"

    await coord._notify_failure(True)
    assert reg.async_get_issue(DOMAIN, issue_id) is not None
    await coord._notify_failure(False)
    assert reg.async_get_issue(DOMAIN, issue_id) is None
