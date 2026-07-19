"""Phase 0 — Fault-Injection: Legacy-Klimaband-Domäne (Refactoring-Plan
``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md``, Befund 11 /
Punkt 11b "Legacy-Klimaband-Domäne", Zeilentabelle 2523–2555 / 2638–2650;
Negativ-Test für F-HUMSHADOW aus Phase 10).

Friert das HEUTIGE Verhalten der EINEN breiten Fehlergrenze um den
Klimaband-Block ein (``coordinator.py``, try 2529–2650):

* Wirft ``humidity_decide`` (Aufruf Z. 2543), degradiert der LIVE
  Dry-Mode-Nudge still: ``_hum_action`` bleibt auf dem Default "idle"
  (Z. 2528), ``mode_arbitration`` (Z. 2745–2749) liefert nie "dry", der
  Mode-Nudge-Write (Z. 2942–2964) sendet kein ``set_hvac_mode('dry')``.
* AR-32 warn-once (Z. 2638–2650): der ERSTE Fehler erzeugt genau eine
  WARNING ("climate-band/humidity block failed"); jeder weitere Tick mit
  demselben Fehler nur noch DEBUG ("Poise climate-band shadow failed") —
  Latch ``_hum_shadow_warned`` (Init Z. 518), wird nie zurückgesetzt.
* Die gesamte ``climate_diag``-Assembly (Z. 2609–2637) degradiert GEMEINSAM:
  bei einem Humidity-Fehler bleibt das Dict leer und KEINER seiner Keys
  erreicht ``coord.data`` (Spread in ``_tick_data`` Z. 3685) — die
  Humidity-Felder ebenso wie die nachgelagerten Free-Running-/Fan-/PMV-
  Shadow-Felder (Befund 11b: beobachtbare gemeinsame Degradation).
* Der Tick selbst bleibt erfolgreich ("must never break the tick").

Phase 10 (F-HUMSHADOW) entkoppelt Humidity von den reinen Klima-Shadows;
bis dahin fixiert diese Datei das Vorher-Verhalten. Glue, CI-only.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from unittest.mock import patch

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
    CONF_OUTDOOR_SENSOR,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_TRM_SENSOR,
    DOMAIN,
)

_COORD_LOGGER = "custom_components.poise.coordinator"
_WARN_TEXT = "climate-band/humidity block failed"
_DEBUG_TEXT = "climate-band shadow failed"

# Every key the climate_diag-Assembly (coordinator.py 2609–2637) produces.
# On a humidity failure they must ALL be absent from coord.data together —
# the Live-Humidity fields AND the shadow fields share the one boundary.
_HUMIDITY_KEYS = ("humidity_action", "dry_active", "humidity_reason")
_SHADOW_KEYS = (
    "cool_sp_eff",
    "cool_sp_active",
    "rh_high_used",
    "fr_active",
    "fan_circ_shadow",
    "fan_velocity_ms",
    "pmv",
    "ppd",
)
_CLIMATE_DIAG_KEYS = _HUMIDITY_KEYS + _SHADOW_KEYS

# Mirrors test_dry_actuation: room in the dead-band (22 C), RH 70 % over the
# Cat II ceiling (60 %) -> humidity_decide normally returns action "dry".
_SENSORS = {
    "sensor.room_temp": ("22", {"device_class": "temperature"}),
    "sensor.rh": ("70", {"device_class": "humidity"}),
    "sensor.outdoor": ("18", {"device_class": "temperature"}),
    "sensor.trm": ("20", {"device_class": "temperature"}),
}

_ROOM_DATA: dict[str, Any] = {
    CONF_NAME: "Zone",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: "climate.ac",
    CONF_HUMIDITY_SENSOR: "sensor.rh",
    CONF_OUTDOOR_SENSOR: "sensor.outdoor",
    CONF_TRM_SENSOR: "sensor.trm",
    CONF_CATEGORY: "II",
    CONF_COMFORT_BASE: 21.0,
    CONF_CLIMATE_MODE: "auto",
    CONF_COMFORT_WEIGHT: 70,
    CONF_SETBACK_DELTA: 3.0,
    CONF_OPTIMAL_START: True,
    CONF_OPERATIVE_INPUT: False,
    CONF_CONTROLS_BOILER: False,
}


class _FakeClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _set_states(hass: HomeAssistant) -> None:
    for eid, (state, attrs) in _SENSORS.items():
        hass.states.async_set(eid, state, attrs)
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["cool", "heat", "dry", "off"],
            "temperature": 24.0,
            "current_temperature": 22.0,
            "target_temperature_step": 0.5,
            "min_temp": 16,
            "max_temp": 32,
        },
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=_ROOM_DATA, title="Zone"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _warn_count(caplog: Any) -> int:
    return sum(
        1
        for r in caplog.records
        if r.levelno == logging.WARNING and _WARN_TEXT in r.getMessage()
    )


def _debug_count(caplog: Any) -> int:
    return sum(
        1
        for r in caplog.records
        if r.levelno == logging.DEBUG and _DEBUG_TEXT in r.getMessage()
    )


async def test_healthy_baseline_dry_nudge_and_diag_fields(
    hass: HomeAssistant,
) -> None:
    """Sanity anchor for the fault test: with a WORKING humidity_decide this
    exact zone nudges into dry and publishes every climate_diag key — so the
    degradation asserted below is attributable to the injected fault alone."""
    async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    _set_states(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    dry = [c for c in set_mode if c.data.get("hvac_mode") == "dry"]
    assert dry, "expected the healthy setup tick to nudge set_hvac_mode('dry')"
    data = coord.data or {}
    assert data.get("available") is True
    assert data.get("humidity_action") == "dry"
    for key in _CLIMATE_DIAG_KEYS:
        assert key in data, f"healthy tick must publish climate_diag key {key!r}"


async def test_humidity_decide_failure_degrades_domain_warn_once(
    hass: HomeAssistant, caplog: Any
) -> None:
    """Befund 11b: a raising ``humidity_decide`` (a) suppresses the dry nudge
    silently, (b) warns exactly ONCE across ticks (AR-32), (c) drops the WHOLE
    climate_diag key set from coord.data together, (d) never breaks the tick."""
    caplog.set_level(logging.DEBUG, logger=_COORD_LOGGER)
    async_mock_service(hass, "climate", "set_temperature")
    set_mode_setup = async_mock_service(hass, "climate", "set_hvac_mode")
    _set_states(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    # healthy setup tick: the zone provably WOULD dry (anchor for (a))
    assert any(c.data.get("hvac_mode") == "dry" for c in set_mode_setup)
    assert (coord.data or {}).get("humidity_action") == "dry"
    assert _warn_count(caplog) == 0

    # deterministic, forward-moving tick clock (convention; seeded past the
    # real monotonic so the setup tick's stamps stay in the past)
    clock = _FakeClock(time.monotonic() + 60.0)
    coord._clock = clock

    # re-arm the recorders AFTER setup: platform forwarding re-registered the
    # real climate handlers, which would clobber the pre-setup mocks for the
    # post-setup ticks (harness finding 2026-07-02, test_frost_rescue_disabled).
    async_mock_service(hass, "climate", "set_temperature")
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")

    with patch(
        "custom_components.poise.coordinator.humidity_decide",
        side_effect=RuntimeError("injected humidity_decide failure"),
    ):
        # ---- tick 1: first failure -------------------------------------
        clock.t += 60.0
        await coord.async_refresh()
        await hass.async_block_till_done()

        # (a) no dry nudge: _hum_action fell back to "idle" (line 2528)
        dry = [c for c in set_mode if c.data.get("hvac_mode") == "dry"]
        assert not dry, "a failing humidity block must not nudge into dry"
        # (b) exactly one WARNING on the first failure (AR-32)
        assert _warn_count(caplog) == 1
        assert coord._hum_shadow_warned is True
        # (c) the WHOLE climate_diag domain is gone from coord.data together
        data = coord.data or {}
        for key in _CLIMATE_DIAG_KEYS:
            assert key not in data, (
                f"climate_diag key {key!r} must degrade with the domain"
            )
        # (d) the tick itself still succeeds
        assert coord.last_update_success is True
        assert data.get("available") is True

        # ---- tick 2: same failure again --------------------------------
        clock.t += 60.0
        await coord.async_refresh()
        await hass.async_block_till_done()

        # (b) warn-once: NO further WARNING; the repeat goes to DEBUG
        assert _warn_count(caplog) == 1
        assert _debug_count(caplog) >= 1
        # (a) still no dry nudge across both failing ticks
        dry = [c for c in set_mode if c.data.get("hvac_mode") == "dry"]
        assert not dry
        # (c)+(d) unchanged degradation, tick still green
        data = coord.data or {}
        for key in _CLIMATE_DIAG_KEYS:
            assert key not in data
        assert coord.last_update_success is True
        assert data.get("available") is True
