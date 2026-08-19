"""ADR-0066 B.5/N2 emission rail (glue, CI-only).

The pure decision is covered in ``tests/test_feuchte_achse.py`` and the seam in
``tests/test_phase8_shadows.py``; what only a real runtime can show is that the
advice actually LEAVES the tick: the ``poise_ventilation_advice`` bus event with
its payload, and the attributes the card reads. Until N2 the whole rail had no
glue coverage at all.

The scenario is the live kitchen case (2026-08-19) in miniature, and it needs
TWO ticks because the defect lives in the gap between two time scales: the
48-h surface-RH mean (rule 1, the mould CAUSE) is deliberately slow, so a wall
that has just cooled down carries an acute surface RH the mean has not caught
up with. Tick 1 seeds the mean on dry air; tick 2 raises the room humidity, at
which point the mould floor climbs over the cooling edge — the published
comfort band collapses onto the protection value — while the mean still sits
far below rule 1's line. Before N2, rule 3t read that bound edge as a comfort
target and advised airing the room down onto the mould floor.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
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
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    CONF_VENT_NOTIFY,
    CONF_WINDOW_SENSOR,
    DOMAIN,
    EVENT_VENT_ADVICE,
)

# Tick 1: 23 °C at 40 % RH over a 6 °C outside — dry walls (surface RH ~55 %),
# which is what the 48-h mean is seeded with.
_SENSORS = {
    "sensor.room_temp": ("23", {"device_class": "temperature"}),
    "sensor.rh": ("40", {"device_class": "humidity"}),
    "sensor.outdoor": ("6", {"device_class": "temperature"}),
    "sensor.outdoor_rh": ("85", {"device_class": "humidity"}),
    "sensor.trm": ("5", {"device_class": "temperature"}),
}
# Tick 2: the same room at 60 % RH — surface RH ~82 % against a 58 % safe
# ceiling, mould floor ~23.6 °C, i.e. ON the Cat-III cooling edge.
_WET_RH = "60"


def _data() -> dict[str, Any]:
    return {
        CONF_NAME: "Kitchen",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_HUMIDITY_SENSOR: "sensor.rh",
        CONF_OUTDOOR_SENSOR: "sensor.outdoor",
        CONF_OUTDOOR_HUMIDITY_SENSOR: "sensor.outdoor_rh",
        CONF_TRM_SENSOR: "sensor.trm",
        CONF_WINDOW_SENSOR: "binary_sensor.window",
        CONF_CATEGORY: "III",
        CONF_COMFORT_BASE: 17.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: True,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        CONF_VENT_NOTIFY: True,
    }


async def _setup(hass: HomeAssistant, *, window_open: bool) -> MockConfigEntry:
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    for eid, (state, attrs) in _SENSORS.items():
        hass.states.async_set(eid, state, attrs)
    hass.states.async_set(
        "binary_sensor.window",
        "on" if window_open else "off",
        {"device_class": "window"},
    )
    # Window-only zone: a heat-only TRV can neither cool nor move air — the
    # capability set rule 3t exists for.
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 20.0,
            "current_temperature": 23.0,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        data=_data(),
        title="Kitchen",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _wet_the_walls(hass: HomeAssistant) -> dict[str, Any]:
    """Second tick: the room humidity rises; the 48-h mean barely moves."""
    hass.states.async_set("sensor.rh", _WET_RH, {"device_class": "humidity"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    state = hass.states.get("climate.kitchen")
    assert state is not None
    return dict(state.attributes)


async def test_mold_guard_reaches_the_bus_and_the_card_attributes(
    hass: HomeAssistant,
) -> None:
    events = async_capture_events(hass, EVENT_VENT_ADVICE)
    entry = await _setup(hass, window_open=True)
    attrs = await _wet_the_walls(hass)

    assert (attrs["vent_action"], attrs["vent_reason"]) == ("close", "mold_guard"), (
        f"expected the mould guard, got {attrs['vent_action']}/{attrs['vent_reason']} "
        f"(surface {attrs['surface_rh']} vs ceiling {attrs['rh_max_safe']}, "
        f"mean {attrs['surface_rh_mean']}, band {attrs['comfort_low']}-"
        f"{attrs['comfort_high']}, edge {attrs['cool_sp_active']})"
    )
    assert attrs["vent_level"] == "warn"
    # The two time scales the advice rests on, as published.
    assert attrs["surface_rh"] > attrs["rh_max_safe"]  # acute: over the ceiling
    assert attrs["surface_rh_mean"] < 75.0  # slow: rule 1 legitimately silent

    guard = [e for e in events if e.data["reason"] == "mold_guard"]
    assert guard, f"the advice never left the tick (events: {[e.data for e in events]})"
    payload = guard[-1].data
    assert payload["action"] == "close"
    assert payload["entry_id"] == entry.entry_id
    assert payload["zone"] == "Kitchen"


async def test_the_same_wet_walls_behind_a_shut_window_are_not_a_mold_guard(
    hass: HomeAssistant,
) -> None:
    """Control: identical air, closed window. The guard is about the OPEN
    window cooling the surfaces down — with it shut there is nothing to close,
    and the axis must fall back to its ordinary advice instead of going
    silent."""
    await _setup(hass, window_open=False)
    attrs = await _wet_the_walls(hass)

    assert attrs["vent_reason"] != "mold_guard"
    # ...and the axis is demonstrably alive in this very scenario.
    assert attrs["surface_rh"] > attrs["rh_max_safe"]
