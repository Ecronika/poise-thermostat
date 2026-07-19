"""Phase 0 — Persistenz-Partial-Recovery (Refactoring-Plan Befund 10).

Friert das HEUTIGE Verhalten der Restore-Reihenfolge in
``PoiseCoordinator.async_bootstrap`` ein, wie in
``docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md`` (Befund 10 und
Phase-0-Checkliste "Partial-Recovery-Test") gefordert:

    "Die Restore-Reihenfolge ist dokumentierte Absicht (Partial Recovery).
    Z. 896-897: user-relevanter State ZUERST und je einzeln defensiv."

Relevante ``coordinator.py``-Stellen (Zeilennummern Stand Plan-Datum):

* 889-894  — Store-I/O-Fehler => ``ConfigEntryNotReady`` (hier NICHT getestet;
             das ist AR-20-Transienz, nicht Korruption).
* 898-1033 — Restore der billigen User-Intent-Keys (enabled / preset /
             override / mode_override / override_reason) und der
             B5-Adoption-Baselines (last_written_sp / prev_device_sp /
             last_commanded_hvac / prev_device_mode) VOR dem Modell-Parsing.
* 1036     — ``ThermalEKF.from_dict(data["ekf"])``: das schwere Parsing.
* 1062-1063 — Legacy-Zweig: ein Store OHNE ``"ekf"``-Key wird als "bare EKF
             dict" interpretiert (Plan: ``persistence/migrations.py``).
* 1064-1065 — EINE breite Fehlergrenze um den gesamten Restore-Block: ein
             Wurf im Modell-Parsing loggt "failed to restore learned model;
             starting fresh" und laesst die bereits restaurierten User-Keys
             stehen — Setup schlaegt NICHT fehl.

Abgedeckte Ist-Verhalten:

1. ``{"ekf": {"x": "garbage"}}`` — ``ThermalEKF.from_dict`` faengt das selbst
   ab (M8: ``float("g")`` -> ``ValueError`` -> frisches Modell, KEIN Wurf).
   User-Intent + Baselines restauriert, EKF frisch, Tick laeuft.
2. ``{"ekf": ["not", "a", "dict"]}`` — ``from_dict`` WIRFT (``AttributeError``:
   eine Liste hat kein ``.get``), die breite Grenze Z. 1064 faengt; die vor
   Z. 1036 restaurierten User-Keys bleiben erhalten, Setup laeuft durch.
3. Komplett leerer Store (``async_load() -> None``) — frischer Start mit
   Defaults, kein ``ConfigEntryNotReady``.
4. Bonus: Store-Dict OHNE ``"ekf"``-Key ({}) — heutiger Legacy-Zweig
   Z. 1062-1063 (``from_dict({})`` -> ``KeyError`` intern -> frisch); die
   User-Keys werden auf diesem Pfad NICHT restauriert (Gate ``"ekf" in data``).

Konstruktions-Detail: Die Seeds setzen ``enabled=False``. Damit ueberspringt
der Setup-Tick den Aktuations-Block (``if self._enabled and not _off_held:``,
Z. 2827) und stempelt weder ``_prev_device_sp``/``_prev_device_mode`` noch
``_last_written_sp`` neu — die restaurierten Baselines sind nach dem Setup
direkt assertierbar (in ``test_adopt_baseline_restore.py`` geht das nicht,
weil der enabled-Tick sie legitim ueberschreibt). ``mode_override="heat"``
statt ``"off"``, damit der M3-Off-Hold-Resume (Z. 2814-2822) nicht greift.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
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
    DOMAIN,
)
from custom_components.poise.control.override import OverrideMode
from custom_components.poise.storage import STORAGE_VERSION

ENTRY_ID = "p0partial"

# Die user-relevanten Keys, wie ein frueherer Lauf sie hinterlassen haette
# (Phase-0-Auftrag: enabled=False, preset, override=21.5, mode_override,
# override_reason, plus die vier B5-Baselines).
USER_KEYS: dict[str, Any] = {
    "enabled": False,
    "preset": "eco",
    "override": 21.5,
    "mode_override": "heat",
    "override_reason": "device_adopt_setpoint",
    "last_written_sp": 20.0,
    "prev_device_sp": 20.5,
    "last_commanded_hvac": "heat",
    "prev_device_mode": "heat",
}


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
        CONF_OPTIMAL_START: False,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        **extra,
    }


def _set_trv(hass: HomeAssistant, *, setpoint: float, room: float = 20.0) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": setpoint,
            "current_temperature": room,
            "target_temperature_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )


def _seed_store(hass_storage: dict[str, Any], data: dict[str, Any]) -> None:
    """Seed den per-Entry-Store, wie ein frueherer HA-Lauf ihn hinterliesse."""
    hass_storage[f"{DOMAIN}_{ENTRY_ID}_ekf"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}_{ENTRY_ID}_ekf",
        "data": data,
    }


async def _setup(hass: HomeAssistant):
    # Recorder VOR dem Setup: der Setup-Tick darf keine unbehandelten
    # climate-Calls sehen (Muster test_adopt_baseline_restore.py).
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="climate.trv",
        entry_id=ENTRY_ID,
        data=_base(),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _assert_user_intent_restored(coord: Any) -> None:
    """Die billigen Keys aus Z. 898-1033 haben den korrupten EKF ueberlebt."""
    assert coord._enabled is False
    assert coord._preset is OverrideMode.ECO
    assert coord._override == 21.5
    assert coord._mode_override == "heat"
    assert coord._override_reason == "device_adopt_setpoint"
    # B5-Adoption-Baselines (Z. 936-947); bewusst nicht Hold-gegated.
    assert coord._last_written_sp == 20.0
    assert coord._prev_device_sp == 20.5
    assert coord._last_commanded_hvac == "heat"
    assert coord._prev_device_mode == "heat"


async def _assert_tick_runs(coord: Any, hass: HomeAssistant) -> None:
    """Setup-Tick war erfolgreich und ein weiterer expliziter Tick laeuft."""
    assert coord.last_update_success is True
    assert isinstance(coord.data, dict)
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert coord.last_update_success is True


async def test_corrupt_ekf_values_keep_user_intent(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Fall 1: ``{"ekf": {"x": "garbage"}}`` — ``ThermalEKF.from_dict`` faengt
    den Wertefehler selbst (M8) und liefert ein frisches Modell, ohne dass die
    breite Grenze Z. 1064 anspringt. User-Intent und Baselines sind restauriert,
    das Setup laeuft (kein ``ConfigEntryNotReady``), der Tick tickt."""
    _seed_store(hass_storage, {"ekf": {"x": "garbage"}, **USER_KEYS})
    _set_trv(hass, setpoint=20.5)

    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    coord = entry.runtime_data

    _assert_user_intent_restored(coord)
    # frisches Modell: kein Restlauf des korrupten Zustands. Der Setup-Tick
    # kann noch nicht gelernt haben (_learn ueberspringt den ersten Tick,
    # weil _last_mono None ist) — 0 ist also stabil assertierbar.
    assert coord._ekf.n_updates == 0
    await _assert_tick_runs(coord, hass)


async def test_throwing_ekf_structure_keeps_user_intent(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fall 2: ``{"ekf": ["not", "a", "dict"]}`` — ``from_dict`` WIRFT
    (``AttributeError``, eine Liste hat kein ``.get``; von ``from_dict``s
    eigenem ``except (KeyError, TypeError, ValueError)`` NICHT gefangen).
    Die breite Grenze Z. 1064-1065 faengt, loggt "starting fresh", und die
    VOR Z. 1036 restaurierten User-Keys bleiben stehen (genau die Absicht
    aus Z. 896-897)."""
    _seed_store(hass_storage, {"ekf": ["not", "a", "dict"], **USER_KEYS})
    _set_trv(hass, setpoint=20.5)

    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    coord = entry.runtime_data

    # Beweis, dass dieser Fall wirklich den Wurf-Pfad nahm (Unterschied zu
    # Fall 1, der still intern recovert):
    assert "failed to restore learned model" in caplog.text
    _assert_user_intent_restored(coord)
    assert coord._ekf.n_updates == 0  # das frische Modell aus __init__
    await _assert_tick_runs(coord, hass)


async def test_empty_store_starts_fresh_with_defaults(
    hass: HomeAssistant,
) -> None:
    """Fall 3: gar kein Store (``async_load() -> None``) — beide Restore-Zweige
    werden uebersprungen, frischer Start mit Defaults, kein
    ``ConfigEntryNotReady``. (Kein hass_storage-Seed = leerer Store.)"""
    _set_trv(hass, setpoint=23.0)

    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    coord = entry.runtime_data

    # Defaults, keine Phantom-Restauration:
    assert coord._enabled is True
    assert coord._preset is OverrideMode.NONE
    assert coord._override is None
    assert coord._mode_override is None
    assert coord._override_reason is None
    # ... und ohne Baseline wird das 23.0-Geraet nicht als Hold gegriffen
    # (konservatives no_baseline-Verhalten, siehe test_adopt_baseline_restore).
    await _assert_tick_runs(coord, hass)
    assert coord._override is None


async def test_store_without_ekf_key_is_legacy_branch(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Bonus (Ist-Verhalten Z. 1062-1063): ein Dict-Store OHNE ``"ekf"``-Key
    wird als Legacy-"bare EKF dict" gelesen — ``from_dict({...})`` recovert
    intern zu frisch. Wichtig als Einfrier-Punkt: auf diesem Pfad werden die
    User-Intent-Keys NICHT restauriert (das Gate ist ``"ekf" in data``),
    selbst wenn sie im Payload stehen. Der Plan macht daraus eine explizite
    Migration (``persistence/migrations.py``)."""
    _seed_store(hass_storage, dict(USER_KEYS))  # kein "ekf"-Key!
    _set_trv(hass, setpoint=20.5)

    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    coord = entry.runtime_data

    # Heutiges Verhalten: alles Default — der User-Intent aus dem Seed ist
    # auf dem Legacy-Zweig unerreichbar.
    assert coord._enabled is True
    assert coord._preset is OverrideMode.NONE
    assert coord._override is None
    assert coord._mode_override is None
    assert coord._ekf.n_updates == 0
    await _assert_tick_runs(coord, hass)
