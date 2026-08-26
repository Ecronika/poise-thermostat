"""P1.4 — Kalibrier-Segmente (Glue, CI-only): Segment W (Regulations-Write),
Segment H (fail-closed Ownership-Handoff, D3) und die Resume-Quarantäne (D4).

Plan: docs/Konzepte/2026-08-20_Plan_Nutzerwunsch-P1-Kalibrierung_P2-Wochenplan.md,
Task P1.4. Die Fälle (a)–(m) des Plans, als Closed-Loop über
``coord.async_refresh()`` gefahren:

* (a) Erst-Write −1.5 stempelt Baseline/Entity/Anker,
* (b) Evidence-Gate: kein Write ohne Aktor-Report nach dem Dispatch-Anker,
* (c) konvergiert + frisch + Delta < Deadband -> kein Write,
* (d') zweistufiger Handoff mit State-Bestätigung gegen den restore_target,
* (e) Restore ohne Geräte-Echo: Redispatch 300 s gedrosselt, Ownership bleibt;
      werfender Dispatch hält die Ownership ebenfalls,
* (f) ``"gone"``: Issue + Ext-Temp läuft + Ownership bleibt (kein Dauer-Block),
* (g) Metadaten ohne step -> ``calibration_entity_unsafe``, kein Write,
* (h) 900 s ohne Konvergenz -> ``cal_diverged`` + ``calibration_unapplied``
      (nicht bei 899 s),
* (i) alter Store ohne Kalibrier-Keys -> Ownership None (Codec-Robustheit),
* (j) fail-closed: Number unavailable -> pending, Ext-Temp blockiert, kein
      Dispatch; Number zurück + Echo -> Ownership state-bestätigt gelöscht,
* (l) Restart-Quarantäne: restaurierte Baseline ohne Anker -> KEIN Write im
      ersten Tick; Akkumulation erst nach neuem Climate-Report,
* (m) clipped: Baseline 5.0 gegen max 4.5 -> Restore schreibt 4.5, Echo 4.5
      löscht die Ownership, ``calibration_restore_clipped`` diagnostiziert.

Harness-Muster: Registry-TRV-Gerät mit Kalibrier-Number
(tests/integration/test_phase4_input_reader.py), Fake-Monotonic-Clock + Feed-
Recorder nach dem Setup (test_external_feed_keepalive.py), Store-Seed
(test_phase0_partial_recovery.py).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

import custom_components.poise.actuator as actuator_mod
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
    CONF_TRV_CALIBRATION,
    CONF_TRV_EXTERNAL_TEMP,
    DOMAIN,
)
from custom_components.poise.estimation.thermal_ekf import ThermalEKF
from custom_components.poise.storage import STORAGE_VERSION

TRV = "climate.trv"
CAL = "number.trv_local_temperature_calibration"
EXT = "number.trv_external_temperature"
ENTRY_ID = "p1cal001"


class _FakeClock:
    """A monotonic clock whose value the test advances by hand."""

    def __init__(self, t: float) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _base(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: TRV,
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: False,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        CONF_TRV_CALIBRATION: True,
        **extra,
    }


def _register_trv_device(hass: HomeAssistant, *, with_ext_number: bool = False) -> None:
    """A mock TRV device owning the actuator + its calibration number.

    Mirrors ``test_phase4_input_reader._register_trv_device``: guard discovery
    is registry-based, so the calibration role is found on the actuator's own
    device on the first tick.
    """
    dev_entry = MockConfigEntry(domain="demo", title="TRV Device")
    dev_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=dev_entry.entry_id, identifiers={("demo", "trv1")}
    )
    ent_reg = er.async_get(hass)

    def _reg(domain: str, obj: str, uid: str) -> str:
        return ent_reg.async_get_or_create(
            domain,
            "demo",
            uid,
            config_entry=dev_entry,
            device_id=device.id,
            suggested_object_id=obj,
        ).entity_id

    assert _reg("climate", "trv", "act") == TRV
    assert _reg("number", "trv_local_temperature_calibration", "cal") == CAL
    if with_ext_number:
        assert _reg("number", "trv_external_temperature", "ext") == EXT


def _set_states(
    hass: HomeAssistant,
    *,
    room: float = 20.5,
    trv_temp: float = 22.0,
    cal: str | None = "0.0",
    cal_attrs: dict[str, Any] | None = None,
    ext: bool = False,
) -> None:
    hass.states.async_set(
        "sensor.room_temp", str(room), {"device_class": "temperature"}
    )
    hass.states.async_set(
        TRV,
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": trv_temp,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    if cal is not None:
        attrs = {"min": -5.0, "max": 5.0, "step": 0.5}
        if cal_attrs is not None:
            attrs = cal_attrs
        hass.states.async_set(CAL, cal, attrs)
    if ext:
        # plausible external-temperature number so F2 keeps the feed.
        hass.states.async_set(EXT, "21", {"device_class": "temperature"})


def _seed_store(hass_storage: dict[str, Any], data: dict[str, Any]) -> None:
    hass_storage[f"{DOMAIN}_{ENTRY_ID}_ekf"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}_{ENTRY_ID}_ekf",
        "data": data,
    }


async def _setup(hass: HomeAssistant, **extra: Any) -> Any:
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TRV,
        entry_id=ENTRY_ID,
        data=_base(**extra),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _tick(hass: HomeAssistant, coord: Any) -> None:
    await coord.async_refresh()
    await hass.async_block_till_done()


def _cal_writes(calls: list[Any]) -> list[Any]:
    return [c for c in calls if c.data.get("entity_id") == CAL]


def _ext_writes(calls: list[Any]) -> list[Any]:
    return [c for c in calls if c.data.get("entity_id") == EXT]


def _issue(hass: HomeAssistant, key: str) -> Any:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}_{ENTRY_ID}")


def _reset_cal(coord: Any) -> None:
    """Zero the calibration bookkeeping after setup (keepalive pattern).

    The SETUP tick already ran the whole program — on the live calibration
    path it may have dispatched a first write with the REAL clocks. The tests
    take over the fake clock afterwards, so the bookkeeping is reset to the
    fresh-start shape first, exactly like the keepalive test resets the feed
    anchors.
    """
    act = coord.runtime.actuator
    act.cal_baseline = None
    act.cal_entity = None
    act.last_cal_value = None
    act.last_cal_write_ts = None
    act.last_cal_dispatch_wall_ts = None
    act.last_cal_restore_ts = None
    coord.runtime.diagnostics.cal_diverged = False
    coord.runtime.diagnostics.cal_handoff_pending = False


# =============================================================================
# Segment W — Regulations-Write auf dem Live-Kalibrierpfad
# =============================================================================


async def test_a_first_write_stamps_baseline_entity_and_anchors(
    hass: HomeAssistant,
) -> None:
    """(a) Raum 20.5 / TRV 22.0 / reported 0.0 / step 0.5 -> Write −1.5;
    der Commit stempelt Baseline 0.0 + Entity + alle drei Anker."""
    _register_trv_device(hass)
    _set_states(hass, room=20.5, trv_temp=22.0, cal="0.0")
    entry = await _setup(hass)
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _reset_cal(coord)
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)

    writes = _cal_writes(set_value)
    assert len(writes) == 1
    assert writes[0].data["value"] == -1.5  # (20.5 − 22.0) + 0.0, rasterfest
    act = coord.runtime.actuator
    assert act.cal_baseline == 0.0  # der VORGEFUNDENE Offset (D3)
    assert act.cal_entity == CAL
    assert act.last_cal_value == -1.5
    assert act.last_cal_write_ts == 1000.0
    assert act.last_cal_dispatch_wall_ts is not None
    # Publizierte Diagnose-Attribute (Shadow-Keys).
    assert coord.data["cal_offset"] == 0.0
    assert coord.data["cal_target"] == -1.5
    assert coord.data["cal_diverged"] is False
    assert coord.data["cal_handoff_pending"] is False


async def test_b_no_write_without_actuator_report_after_dispatch(
    hass: HomeAssistant,
) -> None:
    """(b) Folge-Tick: der Climate-State ist ÄLTER als der Dispatch-Anker
    (und der Offset unbestätigt) -> Evidence-Gate hält, kein zweiter Write."""
    _register_trv_device(hass)
    _set_states(hass, room=20.5, trv_temp=22.0, cal="0.0")
    entry = await _setup(hass)
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _reset_cal(coord)
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)
    assert len(_cal_writes(set_value)) == 1

    # Intervall verstrichen, aber weder Geräte-Echo noch frischer Report:
    clock.t = 1000.0 + 400.0
    await _tick(hass, coord)
    assert len(_cal_writes(set_value)) == 1  # kein Write


async def test_c_converged_fresh_below_deadband_no_write(
    hass: HomeAssistant,
) -> None:
    """(c) Gerät zeigt den letzten Befehl, Report ist frisch, Delta unter der
    Deadband -> geplanter value=None, kein Dispatch."""
    _register_trv_device(hass)
    _set_states(hass, room=20.5, trv_temp=22.0, cal="0.0")
    entry = await _setup(hass)
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _reset_cal(coord)
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)  # Write −1.5
    assert len(_cal_writes(set_value)) == 1

    # Gerät übernimmt: Offset −1.5, current_temperature folgt (20.6) — der
    # frische Climate-Report öffnet das Evidence-Gate wieder.
    clock.t = 1000.0 + 400.0
    hass.states.async_set(CAL, "-1.5", {"min": -5.0, "max": 5.0, "step": 0.5})
    hass.states.async_set(
        TRV,
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 20.6,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    await _tick(hass, coord)
    # neu = (20.5 − 20.6) + (−1.5) = −1.6 -> snap −1.5 -> Delta 0.0 < 0.3.
    assert len(_cal_writes(set_value)) == 1  # kein zweiter Write
    assert coord.data["cal_diverged"] is False


async def test_g_meta_without_step_raises_entity_unsafe(
    hass: HomeAssistant,
) -> None:
    """(g) Kalibrier-Number ohne step-Attribut -> "unreadable" -> Issue
    ``calibration_entity_unsafe`` aktiv, kein Write."""
    _register_trv_device(hass)
    _set_states(
        hass,
        cal="0.0",
        cal_attrs={"min": -5.0, "max": 5.0},  # step fehlt
    )
    entry = await _setup(hass)
    coord = entry.runtime_data
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)

    assert _cal_writes(set_value) == []
    assert _issue(hass, "calibration_entity_unsafe") is not None
    assert coord.runtime.actuator.cal_baseline is None

    # Metadaten wieder sicher -> Issue verschwindet, Write läuft an.
    hass.states.async_set(CAL, "0.0", {"min": -5.0, "max": 5.0, "step": 0.5})
    await _tick(hass, coord)
    assert _issue(hass, "calibration_entity_unsafe") is None
    assert len(_cal_writes(set_value)) == 1


async def test_h_divergence_is_a_time_predicate_at_900s(
    hass: HomeAssistant,
) -> None:
    """(h) Das Gerät zeigt den Befehl 900 s lang nicht -> ``cal_diverged`` +
    ``calibration_unapplied`` — bei 899 s noch nicht (D4-Zeitprädikat)."""
    _register_trv_device(hass)
    _set_states(hass, room=20.5, trv_temp=22.0, cal="0.0")
    entry = await _setup(hass)
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _reset_cal(coord)
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)  # Write bei t0 = 1000.0
    assert len(_cal_writes(set_value)) == 1

    clock.t = 1000.0 + 899.0
    await _tick(hass, coord)
    assert coord.data["cal_diverged"] is False
    assert _issue(hass, "calibration_unapplied") is None

    clock.t = 1000.0 + 900.0
    await _tick(hass, coord)
    assert coord.data["cal_diverged"] is True
    assert _issue(hass, "calibration_unapplied") is not None
    assert len(_cal_writes(set_value)) == 1  # Divergenz schreibt NICHT nach

    # P1.4c (einheitliche Issue-Hygiene): Option aus -> der Pfad ist nicht
    # mehr live, Divergenz ist keine lebende Behauptung mehr — Segment W
    # emittiert den inaktiven Rand. (Das Gerät meldet hier noch 0.0 == die
    # Baseline, also bestätigt der Handoff zugleich sofort state-basiert.)
    coord._trv_calibration = False
    clock.t = 1000.0 + 960.0
    await _tick(hass, coord)
    assert _issue(hass, "calibration_unapplied") is None
    assert coord.data["cal_diverged"] is False


async def test_l_restart_quarantine_blocks_first_tick(
    hass: HomeAssistant,
) -> None:
    """(l) Baseline/Entity aus dem Store restauriert, Anker None, alter
    ``current_temperature`` -> KEIN Write im ersten Tick; der gemeldete Offset
    wird als letzter Befehl übernommen; Akkumulation erst nach einem Climate-
    Report NACH dem Resume-Anker."""
    _register_trv_device(hass)
    _set_states(hass, room=20.5, trv_temp=22.0, cal="-1.5")
    entry = await _setup(hass)
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    # Simulierter Neustart mitten in aktiver Kalibrierung: die persistierte
    # Ownership ist da, die transienten Anker sind es nicht (D4).
    _reset_cal(coord)
    coord.runtime.actuator.cal_baseline = 0.0
    coord.runtime.actuator.cal_entity = CAL
    assert coord.runtime.actuator.last_cal_value is None
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)
    assert _cal_writes(set_value) == []  # Quarantäne: kein Write
    assert coord.runtime.actuator.last_cal_value == -1.5  # reported übernommen
    assert coord.runtime.actuator.last_cal_dispatch_wall_ts is not None
    assert coord.runtime.actuator.cal_baseline == 0.0  # Ownership unberührt

    # Zweiter Tick OHNE neuen Climate-Report: der Anker ist neuer als der
    # (vor dem Setup gesetzte) Aktor-State -> weiterhin kein Write.
    clock.t = 1000.0 + 400.0
    await _tick(hass, coord)
    assert _cal_writes(set_value) == []

    # Frischer Climate-Report NACH dem Resume-Anker: Akkumulation läuft an.
    hass.states.async_set(
        TRV,
        "heat",
        {
            "hvac_modes": ["heat", "off"],
            "temperature": 21.0,
            "current_temperature": 21.5,
            "target_temp_step": 0.5,
            "min_temp": 5,
            "max_temp": 30,
        },
    )
    clock.t = 1000.0 + 800.0
    await _tick(hass, coord)
    writes = _cal_writes(set_value)
    assert len(writes) == 1
    # neu = (20.5 − 21.5) + (−1.5) = −2.5 (rasterfest).
    assert writes[0].data["value"] == -2.5


async def test_i_old_store_without_cal_keys_restores_none(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """(i) Ein v1-Store ohne Kalibrier-Keys restauriert Ownership None; einer
    MIT dem Paar restauriert es (Roundtrip über den echten Restore-Pfad)."""
    _register_trv_device(hass)
    _set_states(hass, cal=None)
    _seed_store(hass_storage, {"ekf": ThermalEKF().to_dict()})
    entry = await _setup(hass, **{CONF_TRV_CALIBRATION: False})
    coord = entry.runtime_data
    assert coord.runtime.actuator.cal_baseline is None
    assert coord.runtime.actuator.cal_entity is None


async def test_i2_store_with_cal_pair_restores_ownership(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    _register_trv_device(hass)
    _set_states(hass, cal=None)
    _seed_store(
        hass_storage,
        {"ekf": ThermalEKF().to_dict(), "cal_baseline": 0.5, "cal_entity": CAL},
    )
    entry = await _setup(hass, **{CONF_TRV_CALIBRATION: False})
    coord = entry.runtime_data
    assert coord.runtime.actuator.cal_baseline == 0.5
    assert coord.runtime.actuator.cal_entity == CAL
    # Transiente Anker restaurieren NIE (Resume-Quarantäne-Trigger, D4).
    assert coord.runtime.actuator.last_cal_value is None
    assert coord.runtime.actuator.last_cal_write_ts is None


# =============================================================================
# Segment H — fail-closed Ownership-Handoff (D3) vor dem Ext-Temp-Feed
# =============================================================================


def _seed_handoff(coord: Any, *, baseline: float = 0.0) -> None:
    """Bestehende Kalibrier-Ownership, wie ein früherer Lauf sie hinterließ."""
    coord.runtime.actuator.cal_baseline = baseline
    coord.runtime.actuator.cal_entity = CAL


async def test_d_two_stage_handoff_confirms_against_restore_target(
    hass: HomeAssistant,
) -> None:
    """(d') Ext-Temp konfiguriert, Baseline 0.0, reported −1.5: Tick 1
    dispatcht den Restore, pending, Ext-Temp übernimmt NICHT; Tick 2 meldet
    das Gerät 0.0 -> state-bestätigt gelöscht, Ext-Temp läuft."""
    _register_trv_device(hass, with_ext_number=True)
    _set_states(hass, cal="-1.5", ext=True)
    entry = await _setup(hass, **{CONF_TRV_EXTERNAL_TEMP: EXT})
    coord = entry.runtime_data
    assert coord._trv_ext_temp == EXT  # Feed von der F2-Validierung gehalten
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _seed_handoff(coord)
    coord.runtime.actuator.last_fed = None
    coord.runtime.actuator.last_fed_ts = 0.0
    set_value = async_mock_service(hass, "number", "set_value")

    # Tick 1: Restore-Dispatch auf den restore_target (Baseline rasterfest),
    # Ownership BLEIBT (Erfolg ist Dispatch, nicht Übernahme — F15).
    await _tick(hass, coord)
    cal_writes = _cal_writes(set_value)
    assert len(cal_writes) == 1
    assert cal_writes[0].data["value"] == 0.0
    assert _ext_writes(set_value) == []  # Ext-Temp-Skip während pending
    assert coord.data["cal_handoff_pending"] is True
    assert coord.runtime.actuator.cal_baseline == 0.0

    # Tick 2: das Gerät MELDET den restore_target -> Ownership gelöscht,
    # der Nachfolger-Pfad übernimmt.
    hass.states.async_set(CAL, "0.0", {"min": -5.0, "max": 5.0, "step": 0.5})
    clock.t = 1000.0 + 60.0
    await _tick(hass, coord)
    assert coord.runtime.actuator.cal_baseline is None
    assert coord.runtime.actuator.cal_entity is None
    assert coord.data["cal_handoff_pending"] is False
    assert len(_ext_writes(set_value)) == 1  # der Feed läuft jetzt
    assert len(_cal_writes(set_value)) == 1  # kein zweiter Restore


async def test_e_restore_redispatch_throttled_and_failure_keeps_ownership(
    hass: HomeAssistant,
) -> None:
    """(e) Kein Geräte-Echo: der Redispatch ist 300 s gedrosselt (die Drossel
    stempelt der cal_restore-Commit, Erfolg = Dispatch); danach genau ein
    weiterer Versuch. Ein synchron werfender Dispatch stempelt nichts und
    lässt die Ownership ebenso stehen."""
    _register_trv_device(hass, with_ext_number=True)
    _set_states(hass, cal="-1.5", ext=True)
    entry = await _setup(hass, **{CONF_TRV_EXTERNAL_TEMP: EXT})
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _seed_handoff(coord)
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)  # Dispatch 1 bei t0
    assert len(_cal_writes(set_value)) == 1
    assert coord.runtime.actuator.last_cal_restore_ts == 1000.0

    clock.t = 1000.0 + 60.0  # innerhalb der Drossel
    await _tick(hass, coord)
    assert len(_cal_writes(set_value)) == 1  # kein Redispatch
    assert coord.data["cal_handoff_pending"] is True

    clock.t = 1000.0 + 301.0  # Drossel verstrichen
    await _tick(hass, coord)
    assert len(_cal_writes(set_value)) == 2
    assert coord.runtime.actuator.cal_baseline == 0.0  # Ownership bleibt

    # Werfender Dispatch: Attempt ohne Erfolg -> KEIN Drossel-Stempel, keine
    # Ownership-Änderung (Commit stempelt nur auf success).
    before_ts = coord.runtime.actuator.last_cal_restore_ts
    clock.t = 1000.0 + 700.0
    with patch.object(
        actuator_mod, "write", side_effect=HomeAssistantError("injected")
    ):
        await _tick(hass, coord)
    assert coord.runtime.actuator.cal_baseline == 0.0
    assert coord.runtime.actuator.last_cal_restore_ts == before_ts
    assert coord.data["cal_handoff_pending"] is True


async def test_f_gone_entity_never_blocks_but_keeps_evidence(
    hass: HomeAssistant,
) -> None:
    """(f) Die gespeicherte Entity ist strukturell weg (Gerät getauscht):
    Issue ``calibration_restore_failed``, aber KEIN Dauer-Block — der
    Ext-Temp-Feed läuft, die Ownership bleibt als Beleg stehen."""
    _register_trv_device(hass, with_ext_number=True)
    _set_states(hass, cal=None, ext=True)
    entry = await _setup(hass, **{CONF_TRV_EXTERNAL_TEMP: EXT})
    coord = entry.runtime_data
    coord.runtime.actuator.cal_baseline = -1.0
    coord.runtime.actuator.cal_entity = "number.ghost_calibration"  # weg
    coord.runtime.actuator.last_fed = None
    coord.runtime.actuator.last_fed_ts = 0.0
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)

    assert _issue(hass, "calibration_restore_failed") is not None
    assert coord.data["cal_handoff_pending"] is False
    assert len(_ext_writes(set_value)) == 1  # Ext-Temp läuft
    assert _cal_writes(set_value) == []  # nichts, worauf ein Offset wirkt
    assert coord.runtime.actuator.cal_baseline == -1.0  # Beleg bleibt


async def test_j_fail_closed_unavailable_number_blocks_ext_temp(
    hass: HomeAssistant,
) -> None:
    """(j) fail-closed (D3): die Kalibrier-Number ist unavailable — der
    Offset ist evtl. physisch noch aktiv. pending=True, der Ext-Temp-Feed
    läuft NICHT, es wird nichts dispatcht; kommt die Number zurück und meldet
    den restore_target, wird die Ownership state-bestätigt gelöscht."""
    _register_trv_device(hass, with_ext_number=True)
    _set_states(hass, cal="unavailable", ext=True)
    entry = await _setup(hass, **{CONF_TRV_EXTERNAL_TEMP: EXT})
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _seed_handoff(coord)
    coord.runtime.actuator.last_fed = None
    coord.runtime.actuator.last_fed_ts = 0.0
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)
    assert set_value == []  # kein Dispatch (weder Restore noch Feed)
    assert coord.data["cal_handoff_pending"] is True
    assert _issue(hass, "calibration_restore_failed") is not None
    assert coord.runtime.actuator.cal_baseline == 0.0

    # Number zurück, Gerät meldet bereits den restore_target (Echo).
    hass.states.async_set(CAL, "0.0", {"min": -5.0, "max": 5.0, "step": 0.5})
    clock.t = 1000.0 + 60.0
    await _tick(hass, coord)
    assert coord.runtime.actuator.cal_baseline is None  # state-bestätigt
    assert coord.data["cal_handoff_pending"] is False
    assert _issue(hass, "calibration_restore_failed") is None
    assert len(_ext_writes(set_value)) == 1  # der Feed übernimmt


async def test_m_clipped_baseline_restores_best_possible(
    hass: HomeAssistant,
) -> None:
    """(m) Baseline 5.0, Entity-max inzwischen 4.5: der Restore schreibt den
    gesnappten restore_target 4.5 (bestmöglich, ``calibration_restore_clipped``
    diagnostiziert); meldet das Gerät 4.5, ist die Ownership gelöscht."""
    _register_trv_device(hass, with_ext_number=True)
    _set_states(
        hass,
        cal="3.0",
        cal_attrs={"min": -5.0, "max": 4.5, "step": 0.5},
        ext=True,
    )
    entry = await _setup(hass, **{CONF_TRV_EXTERNAL_TEMP: EXT})
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _seed_handoff(coord, baseline=5.0)
    set_value = async_mock_service(hass, "number", "set_value")

    await _tick(hass, coord)
    writes = _cal_writes(set_value)
    assert len(writes) == 1
    assert writes[0].data["value"] == 4.5  # der geclippte restore_target
    assert coord.data["cal_handoff_pending"] is True
    assert _issue(hass, "calibration_restore_clipped") is not None

    hass.states.async_set(CAL, "4.5", {"min": -5.0, "max": 4.5, "step": 0.5})
    clock.t = 1000.0 + 60.0
    await _tick(hass, coord)
    assert coord.runtime.actuator.cal_baseline is None  # gegen 4.5 bestätigt
    assert coord.data["cal_handoff_pending"] is False
    # P1.4c-Regel (einheitliche Issue-Hygiene, eine Ein-Tick-Ausnahme): der
    # BESTÄTIGENDE Tick hält den clipped-Beleg noch ("wiederhergestellt, aber
    # beschnitten"), der Folge-Tick ohne Ownership räumt ihn ab.
    assert _issue(hass, "calibration_restore_clipped") is not None
    clock.t = 1000.0 + 120.0
    await _tick(hass, coord)
    assert _issue(hass, "calibration_restore_clipped") is None


async def test_n_stale_restore_failed_clears_when_path_returns(
    hass: HomeAssistant,
) -> None:
    """Issue-Hygiene (Spec-Review P1.4b): ein während einer fail-closed-Phase
    gesetztes ``calibration_restore_failed`` darf nicht ewig stehen, wenn der
    Kalibrierpfad wieder der Live-Pfad wird (kein Handoff mehr nötig) — der
    ``live is CALIBRATION``-Early-Return emittiert den inaktiven Rand."""
    _register_trv_device(hass)
    _set_states(hass, cal="unavailable")
    entry = await _setup(hass, **{CONF_TRV_CALIBRATION: False})
    coord = entry.runtime_data
    clock = _FakeClock(1000.0)
    coord.runtime.clock = clock
    _reset_cal(coord)
    _seed_handoff(coord)  # Ownership aus einer früheren Kalibrier-Phase
    set_value = async_mock_service(hass, "number", "set_value")

    # Tick 1 (Option aus, Number unavailable): fail-closed -> Issue aktiv,
    # pending, kein Dispatch.
    await _tick(hass, coord)
    assert _issue(hass, "calibration_restore_failed") is not None
    assert coord.data["cal_handoff_pending"] is True
    assert set_value == []

    # Der Kalibrierpfad wird wieder live (Hot-Apply der Option; hier wie der
    # P1.5-Port direkt auf dem Live-Attribut) — kein Handoff mehr noetig:
    # der Early-Return raeumt das stehengebliebene Issue ab.
    coord._trv_calibration = True
    clock.t = 1000.0 + 60.0
    await _tick(hass, coord)
    assert _issue(hass, "calibration_restore_failed") is None
    assert coord.data["cal_handoff_pending"] is False
    assert coord.runtime.actuator.cal_baseline == 0.0  # Ownership unberuehrt
    # Die (weiterhin unlesbare) Number ist jetzt Sache von Segment W:
    assert _issue(hass, "calibration_entity_unsafe") is not None
    assert set_value == []  # weiterhin kein Dispatch
