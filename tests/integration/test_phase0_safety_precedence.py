"""Phase 0 (Refactoring-Plan coordinator, 2026-07-18): Safety-Präzedenz tabellarisch.

Plan point (docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md, Verhaltens-
Testnetz): "Safety-Präzedenz tabellarisch: Fenster > Frost > Sensorausfall/frozen
> Override > Komfort (Blöcke 2494–2522, 3241–3269)". This module freezes TODAY's
behaviour of the enabled full-tick path over recorded HA service calls; the
disabled-zone frost rescue (3241–3326) is already pinned by
``test_frost_rescue_disabled.py``.

Coordinator anchor points (line numbers verified against coordinator.py v0.179):

* 2494–2506  ``resolve_write_target`` call — window / override / comfort →
  (target, mode) plus the unconditional norm envelope. Pure logic in
  ``control/tick_resolve.py::resolve_write_target`` (window first at 93–94,
  override band-clamp 95–98, comfort fallthrough 99–100; M2 "device cap is
  clamped up to the health floor" at 109).
* 2511–2522  frozen-sensor degrade: a stale room reading replaces the resolved
  target (even a manual override's) with ``frozen_safe_target`` = health floor,
  mode forced to ``heat`` on a heat-capable device.
* 1866        the ``frozen`` flag itself: ``is_frozen(self._sensor_age(...),
  SENSOR_FREEZE_AFTER_S)`` — **wall-clock** based (``dt_util.utcnow()`` vs the
  state's ``last_changed``, see ``_sensor_age`` 1364–1374), NOT the injectable
  monotonic ``coord._clock``. A FakeClock therefore cannot age the sensor;
  the repo-proven pattern (tests/integration/test_coverage_paths.py::
  test_frozen_sensor_writes_health_floor) patches
  ``custom_components.poise.coordinator.is_frozen`` instead — the narrowest
  possible injection, used here for the frozen cases only.
* 1380–1403  window contact read (any configured contact "on" = open),
  combined via ``effective_window_open`` (2126–2129).
* 1412–1418  ``_device_max`` from the actuator's ``max_temp`` attribute (the
  misreported-below-floor input for the M2 case).
* 2942–2964  mode-nudge write; 3164–3190 setpoint write (the recorded
  ``climate.set_temperature`` service calls asserted below).
* 3051–3062  adoption safety gates (window/frozen suppress device-side
  adoption), which is why an unchanged device setpoint never turns into a
  phantom hold during these ticks.

Each parametrised case pits exactly two levels of the precedence ladder against
each other and asserts what actually went onto the wire (recorded service
calls) plus the tick-data verdict:

1. window_beats_warm_override   — open window vs. active warm manual hold: the
   frost/health floor (7.0) is written, never the override value; the hold
   itself survives (precedence, not cancellation).
2. health_floor_beats_device_max — a device misreporting ``max_temp`` BELOW the
   frost floor: the floor still wins (M2 — the SAFETY device cap is clamped up
   to the HEALTH floor when heating), so 7.0 is written, never 6.0/5.0.
3. frozen_beats_override        — stale room sensor vs. active warm hold: the
   write degrades to the health floor in ``heat``; the hold survives.
4. override_beats_comfort       — no safety active: the manual value is written
   verbatim (band allows it), not the comfort heat setpoint.
5. comfort_base_case            — nothing active: the comfort heat setpoint is
   written (== this tick's published ``heat_sp``).

Config mirrors the proven ROOM_DATA family (no outdoor/TRM/humidity sensors →
``mold_min`` is None, so the health floor == FROST_FLOOR_C == 7.0; no
comfort_start/end → all-day comfort window, so the schedule/setback can never
make the expected values depend on the wall-clock time the suite runs at).
Room = 19.0 °C keeps every case in clear heat demand (published ``heat_sp`` is
~23 °C here: operative→air conversion against the virtual MRT with the 5 °C
fallback outdoor raises it above the 21 °C base — asserted dynamically, with
explicit discriminating-precondition checks so a drift makes the test speak).
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest
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
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_SENSOR,
    DOMAIN,
    FROST_FLOOR_C,
)

ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.trv",
    CONF_WINDOW_SENSOR: "binary_sensor.window",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: False,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}

ROOM_C = 19.0  # clear heat demand in every case (see module docstring)


@dataclass(frozen=True)
class Case:
    """One precedence duel: which two levels compete, what must hit the wire."""

    override: float | None = None  # active manual hold before the tick
    window: bool = False  # open the contact before the tick
    frozen: bool = False  # patch is_frozen -> True around the tick
    device_max: float = 30.0  # actuator max_temp attribute
    device_sp: float = 20.0  # actuator's reported setpoint (stable, so
    #   the adoption detector never fires — stable_prev/echo, lines 3015–3062)
    expect_temp: float | str = 0.0  # exact written value, or "heat_sp" (dynamic)
    expect_mode: str = "heat"  # this tick's published data["mode"]
    forbid_temps: tuple[float, ...] = field(default_factory=tuple)
    override_survives: bool = False  # safety must not CANCEL the hold


CASES = [
    pytest.param(
        Case(
            override=24.0,
            window=True,
            expect_temp=FROST_FLOOR_C,
            expect_mode="off",
            forbid_temps=(24.0,),
            override_survives=True,
        ),
        id="window_beats_warm_override",
    ),
    pytest.param(
        Case(
            device_max=6.0,  # misreported BELOW the 7.0 health floor (M2)
            device_sp=5.0,  # the device also sits below the floor
            expect_temp=FROST_FLOOR_C,
            expect_mode="heat",
            forbid_temps=(6.0, 5.0),
        ),
        id="health_floor_beats_device_max",
    ),
    pytest.param(
        Case(
            override=25.0,
            frozen=True,
            expect_temp=FROST_FLOOR_C,
            expect_mode="heat",
            forbid_temps=(25.0,),
            override_survives=True,
        ),
        id="frozen_beats_override",
    ),
    pytest.param(
        Case(
            override=25.0,
            expect_temp=25.0,
            expect_mode="manual",
            forbid_temps=(FROST_FLOOR_C,),
        ),
        id="override_beats_comfort",
    ),
    pytest.param(
        Case(expect_temp="heat_sp", expect_mode="heat"),
        id="comfort_base_case",
    ),
]


def _set_states(
    hass: HomeAssistant,
    *,
    device_sp: float,
    device_max: float,
    window: str = "off",
) -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(ROOM_C),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("binary_sensor.window", window, {"device_class": "window"})
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": device_sp,
            "current_temperature": ROOM_C,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": device_max,
        },
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("case", CASES)
async def test_safety_precedence_table(hass: HomeAssistant, case: Case) -> None:
    """One full _run_once tick per duel; asserts the recorded actuator write."""
    _set_states(hass, device_sp=case.device_sp, device_max=case.device_max)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    # Re-arm the recorders AFTER setup: platform forwarding re-registers the real
    # climate handlers, which would clobber a pre-setup mock (harness finding
    # 2026-07-02, see test_frost_rescue_disabled.py).
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")

    if case.override is not None:
        coord.set_override(case.override, reason="ui_setpoint")
    if case.window:
        hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})

    frozen_ctx = (
        patch("custom_components.poise.coordinator.is_frozen", return_value=True)
        if case.frozen
        else nullcontext()
    )
    with frozen_ctx:
        await coord.async_refresh()
        await hass.async_block_till_done()

    assert coord.last_update_success is True
    data: dict[str, Any] = coord.data or {}

    # Tick-data verdict of the resolution (coordinator 2494–2522).
    assert data.get("mode") == case.expect_mode
    if case.window:
        assert data.get("window_open") is True
    if case.frozen:
        assert data.get("sensor_frozen") is True

    # What actually went onto the wire (setpoint write, 3164–3190).
    temps = [
        c.data["temperature"]
        for c in set_temp
        if c.data.get("entity_id") == "climate.trv"
    ]
    assert temps, (
        f"no setpoint write recorded this tick: mode={data.get('mode')} "
        f"target={data.get('target_temperature')}"
    )

    if case.expect_temp == "heat_sp":
        expected = data["heat_sp"]
        # discriminating precondition: the comfort value must not coincide with
        # the floor, else this base case would be vacuous.
        assert expected > FROST_FLOOR_C
        assert expected > ROOM_C  # heat demand -> the heat edge is the target
    else:
        expected = case.expect_temp
    assert temps[-1] == pytest.approx(expected)
    assert data.get("target_temperature") == pytest.approx(expected)

    for bad in case.forbid_temps:
        assert bad not in temps, (
            f"losing precedence level {bad} reached the wire: {temps}"
        )
    if case.expect_temp == 25.0 and not case.frozen:
        # discriminating precondition for override_beats_comfort: the manual
        # value must differ from (and exceed) the comfort heat edge, else the
        # duel would be vacuous; equality would mean the band clamped it.
        assert data["heat_sp"] < 25.0
        assert data["heat_sp"] not in temps

    # Safety takes PRECEDENCE over a hold, it does not cancel it: once the
    # window closes / the sensor thaws, the hold resumes (coordinator keeps
    # ``_override``; the end-hold path at ~2904/2912 is gated on NOT window
    # and NOT frozen).
    if case.override_survives:
        assert coord._override == case.override
