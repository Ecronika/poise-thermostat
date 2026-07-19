"""Phase 3 — Coordinator <-> Persistenz-Codec-Wiring (Refactoring-Plan Phase 3).

Die FORMAT-Pins leben in der puren Suite (``tests/test_phase3_codec.py``), die
Restore-VERHALTENS-Pins in ``tests/integration/test_phase0_partial_recovery.py``
— letztere sind der eigentliche Pin und müssen nach der Umstellung von
``_save_payload``/``async_bootstrap`` auf ``persistence.codec`` unverändert
grün bleiben. Dieses Modul ergänzt nur das WIRING:

* (a) ``encode == save``: nach einem echten Tick ist ``_save_payload()``
  wertgleich zu dem, was ``codec.encode`` aus einer UNABHÄNGIG (Feld für Feld
  im Test) aus denselben Live-Attributen gebauten ``PersistedZoneState``
  erzeugt — und ein Store-Flush landet exakt dieses Payload (Key-Menge UND
  -Reihenfolge = ``codec.PAYLOAD_KEYS``).
* (b) Store-Seed-Roundtrip über ZWEI Setups: ein von Setup 1 geschriebener
  Store (echter Unload-Save) wird von Setup 2 über den echten Bootstrap-Pfad
  (``codec.decode`` + Domain-Hooks) restauriert; der persistierte Payload ist
  ein v1-Payload im Sinne des Codec-Gates.
* (c) Recovery-Log-Semantik der Modell-Korruption (verhaltensäquivalent zum
  Vor-Refactoring-Monolithen): ein struktureller Wurf mitten im Modell-Tail
  erzeugt EXAKT EINEN "failed to restore learned model; starting fresh"-
  Record — ERROR-Level MIT ``exc_info`` (Original-Exception-Klasse +
  Traceback) — und die vor dem Wurf geparsten Modelle (hier: das gelernte
  EKF) bleiben restauriert (Präfix-Semantik, Befund 10).

Konstruktions-Detail wie in ``test_phase0_partial_recovery.py``: vor dem
Reload wird ``enabled=False`` gesetzt, damit der Setup-Tick des zweiten Laufs
den Aktuations-Block überspringt und weder Baselines noch Hold-State neu
stempelt — die restaurierten Werte sind direkt gegen den Stand von Setup 1
assertierbar.
"""

from __future__ import annotations

import time
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
from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from custom_components.poise.persistence import codec
from custom_components.poise.storage import STORAGE_VERSION

ENTRY_ID = "p3wiring"


def _base() -> dict[str, Any]:
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
    }


def _set_states(hass: HomeAssistant, *, room: float = 19.0, sp: float = 18.0) -> None:
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


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
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


def _snapshot_from_attributes(coord: Any) -> codec.PersistedZoneState:
    """Der UNABHÄNGIGE Attribut->Feld-Abgleich: baut die Codec-Eingabe Feld
    für Feld aus den heutigen ``self._*``-Attributen nach (deckt Vertauschungen
    im ``_save_payload``-Wiring auf, z. B. regq<->hdh)."""
    return codec.PersistedZoneState(
        ekf=coord._ekf,
        trm_tracker=coord._trm_tracker,
        seasonless=coord._seasonless,
        window_auto=coord._window_auto,
        multi_lifecycle=coord._multi_lifecycle,
        ref_offset=coord._ref_offset,
        tau_settle=coord._tau_settle,
        outcome_stats=coord._outcome_stats,
        regq=coord._regq,
        hdh=coord._hdh,
        dry_active=coord._dry_active,
        enabled=coord._enabled,
        preset=coord._preset,
        climate_mode=coord._climate_mode,
        window_bypass=coord._window_bypass,
        has_actuated=coord._has_actuated,
        override=coord._override,
        mode_override=coord._mode_override,
        override_set_wall=coord._override_set_wall,
        override_requested=coord._override_requested,
        override_policy=coord._override_policy,
        override_expires_at=coord._override_expires_at,
        override_expiry_is_switchpoint=coord._override_expiry_is_switchpoint,
        boost_expires_at=coord._boost_expires_at,
        boost_prev_preset=coord._boost_prev_preset,
        override_stats=coord._override_stats,
        override_reason=coord._override_reason,
        last_written_sp=coord._last_written_sp,
        prev_device_sp=coord._prev_device_sp,
        last_commanded_hvac=coord._last_commanded_hvac,
        prev_device_mode=coord._prev_device_mode,
    )


async def test_save_payload_equals_codec_encode_after_real_tick(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """(a) encode == save: nach echtem Setup-Tick + explizitem Tick + einer
    User-Mutation (Hold) ist ``_save_payload()`` wertgleich zum Codec-Encode
    der unabhängig nachgebauten Attribut-Snapshot, und der Flush außerhalb
    des Ticks (``async_flush_on_stop``) persistiert exakt dieses Payload."""
    _set_states(hass)
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    coord: Any = entry.runtime_data

    # ein weiterer echter Tick, damit Modelle/Baselines Live-Input gesehen haben
    await coord.async_refresh()
    await hass.async_block_till_done()

    # nicht-triviale User-Intent-/Hold-Sektion im Payload
    coord.set_override(21.5, reason="device_adopt_setpoint")
    coord.set_preset(OverrideMode.ECO)

    expected = codec.encode(_snapshot_from_attributes(coord))
    payload = coord._save_payload()
    assert payload == expected
    assert list(payload) == list(codec.PAYLOAD_KEYS)
    # der Hold-Stand ist wirklich drin (kein leerer Default-Vergleich)
    assert payload["override"] == 21.5
    assert payload["override_reason"] == "device_adopt_setpoint"
    assert payload["preset"] == "eco"

    # Flush außerhalb des Ticks: exakt dieses Payload landet im Store.
    await coord.async_flush_on_stop(None)
    stored = hass_storage[f"{DOMAIN}_{ENTRY_ID}_ekf"]["data"]
    assert stored == expected


async def test_store_seed_roundtrip_across_two_setups(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """(b) Store-Seed-Roundtrip über zwei Setups: Setup 1 hinterlässt per
    echtem Unload-Save einen v1-Store; Setup 2 restauriert ihn über den
    echten Bootstrap-Pfad (codec.decode + Domain-Hooks). User-Intent, Hold-
    Lifecycle und B5-Baselines kommen wertgleich zurück."""
    _set_states(hass)
    entry = await _setup(hass)
    coord: Any = entry.runtime_data

    # Stand von Setup 1: User-Intent + Hold; enabled=False, damit der
    # Setup-Tick von Lauf 2 nichts neu stempelt (Muster partial_recovery).
    coord.set_climate_mode("heat")
    coord.set_preset(OverrideMode.ECO)
    coord.set_override(21.5, reason="device_adopt_setpoint")
    coord.set_enabled(False)
    held_set_wall = coord._override_set_wall
    held_expires_at = coord._override_expires_at
    held_requested = coord._override_requested
    base_written_sp = coord._last_written_sp
    base_prev_sp = coord._prev_device_sp
    base_cmd_hvac = coord._last_commanded_hvac
    base_prev_mode = coord._prev_device_mode
    assert held_set_wall is not None and held_expires_at is not None

    # Zwei Setups: der Reload entlädt (echter Unload-Save) und baut neu auf.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored: Any = entry.runtime_data
    assert restored is not coord, "a genuine reload built a fresh coordinator"

    # Der von Setup 1 hinterlassene Store ist ein v1-Payload im Codec-Sinn.
    stored = hass_storage[f"{DOMAIN}_{ENTRY_ID}_ekf"]["data"]
    assert list(stored) == list(codec.PAYLOAD_KEYS)
    assert codec.decode(stored, now_wall=time.time()).kind == "v1"

    # User-Intent + Hold-Lifecycle wertgleich restauriert.
    assert restored._enabled is False
    assert restored.preset is OverrideMode.ECO
    assert restored.climate_mode == "heat"
    assert restored._override == 21.5
    assert restored._override_reason == "device_adopt_setpoint"
    assert restored._override_set_wall == held_set_wall
    assert restored._override_expires_at == held_expires_at
    assert restored._override_requested == held_requested
    # B5-Baselines: von Setup 1 gestempelt, über den Codec zurück (der
    # enabled=False-Setup-Tick überschreibt sie nicht).
    assert restored._last_written_sp == base_written_sp
    assert restored._prev_device_sp == base_prev_sp
    assert restored._last_commanded_hvac == base_cmd_hvac
    assert restored._prev_device_mode == base_prev_mode


async def test_model_corruption_logs_single_exception_record(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """(c) Recovery-Log-Semantik + Präfix-Retention bei Mid-Tail-Korruption.

    Seed: gültiges (gelerntes) ``ekf``, danach strukturell werfende ``trm``-
    UND ``outcome_stats``-Werte (``float("not-a-number")`` -> ``ValueError``).
    Verhaltensäquivalent zum alten sequenziellen Restore muss (1) das bereits
    geparste EKF restauriert bleiben (kein Lernmodell-Verlust), (2) genau EIN
    Log-Record "failed to restore learned model; starting fresh" entstehen —
    ERROR-Level MIT ``exc_info`` (``ValueError``-Klasse + Traceback), NICHT
    zwei Records für zwei "Sektionen" — und (3) der User-Intent erhalten
    bleiben; das Setup läuft durch."""
    learned = ThermalEKF()
    learned.n_updates = 7
    hass_storage[f"{DOMAIN}_{ENTRY_ID}_ekf"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}_{ENTRY_ID}_ekf",
        "data": {
            "ekf": learned.to_dict(),
            "trm": {"alpha": "not-a-number"},
            "outcome_stats": {"ts_sum": "not-a-number"},
            "enabled": False,  # der Setup-Tick stempelt nichts neu
            "preset": "eco",
            "override": 21.5,
            "override_reason": "device_adopt_setpoint",
        },
    }
    _set_states(hass)

    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    coord: Any = entry.runtime_data

    # (1) Präfix-Semantik: das VOR dem Wurf geparste EKF ist restauriert
    # (der Setup-Tick lernt noch nicht: ``_last_mono`` ist None).
    assert coord._ekf.n_updates == 7
    # (2) Log-Form des alten Monolithen: EIN Record, ERROR, mit Traceback.
    records = [
        r for r in caplog.records if "failed to restore learned model" in r.getMessage()
    ]
    assert len(records) == 1
    assert records[0].levelname == "ERROR"
    assert records[0].exc_info is not None
    assert records[0].exc_info[0] is ValueError
    # (3) User-Intent unversehrt.
    assert coord._enabled is False
    assert coord.preset is OverrideMode.ECO
    assert coord._override == 21.5
    assert coord._override_reason == "device_adopt_setpoint"
