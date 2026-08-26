"""P1.5 — Lifecycle-Restore (Glue, CI-only): state-bestätigter Restore-Helper,
Coordinator-Handoff-Port mit Reakquisitions-Sperre, Reconfigure-Flow,
Teardown-Gate und der Apply-only-Repair-Kind ``trv_calibration``.

Plan: docs/Konzepte/2026-08-20_Plan_Nutzerwunsch-P1-Kalibrierung_P2-Wochenplan.md,
Task P1.5 (+ §0.5 Punkt 1, §0.6 Punkte 1–2, §0.6a Punkte 1–2). Kernfälle:

* Der zweifach parametrisierte **Reconfigure-Race-Test** (§0.6 Punkt 1 +
  §0.6a Punkt 1): Handoff-Port erfolgreich -> erzwungener Refresh des ALTEN
  Coordinators vor jedem Entry-Update -> kein ``cal_write``, Ownership bleibt
  leer (die Sperre hielt); der Final Save nach dem Unload persistiert keine
  Ownership (F27-Regression).
* Restore-Helper: State-Bestätigung (Write + stale Rückles -> FAILED),
  already_at_target-Kurzschluss ohne Write, gone/unreadable-Mapping,
  werfender blocking-Call -> FAILED.
* Reconfigure-Flow: FAILED -> Formularfehler + Entry unverändert + Ownership
  bleibt; zweiter Versuch mit Geräte-Echo -> RESTORED -> Flow läuft durch;
  GONE -> WARN + durchlaufen; kein Aktorwechsel -> kein Restore; ungeladene
  Entry -> Store-Pfad (§0.5 Punkt 1).
* Teardown: eigenes Gate VOR ``has_actuated`` (Restore auch ohne Aktuierung);
  FAILED behält die Store-Keys + loggt unmissverständlich; RESTORED räumt.
* Repair-Kind: Bedingung (fähig + Option aus -> Issue; Option an -> keins;
  Ext-Temp reserviert -> keins), Apply schreibt die Option über den
  Options-Pfad und stempelt KEINEN Cooldown, kein Dismiss-Step.

Harness-Muster: tests/integration/test_p1_calibration_stage.py (Registry-TRV
mit Kalibrier-Number, Fake-Clock, Store-Seed) und test_config_flow.py
(Reconfigure-Submits).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise import _park_room_actuator
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
from custom_components.poise.ha.actuator_lifecycle import (
    CalibrationRestoreResult,
    restore_trv_calibration,
)
from custom_components.poise.repairs import (
    CalibrationOptInFixFlow,
    async_create_fix_flow,
)
from custom_components.poise.storage import STORAGE_VERSION

TRV = "climate.trv"
NEW_TRV = "climate.new"
CAL = "number.trv_local_temperature_calibration"
EXT = "number.trv_external_temperature"
ENTRY_ID = "p15cal001"
CAL_ATTRS = {"min": -5.0, "max": 5.0, "step": 0.5}


class _FakeClock:
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
    """Registry-TRV-Gerät mit Kalibrier-Number (Muster test_phase4/P1.4)."""
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
        hass.states.async_set(CAL, cal, CAL_ATTRS)
    if ext:
        hass.states.async_set(EXT, "21", {"device_class": "temperature"})


def _seed_store(hass_storage: dict[str, Any], data: dict[str, Any]) -> None:
    hass_storage[f"{DOMAIN}_{ENTRY_ID}_ekf"] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": f"{DOMAIN}_{ENTRY_ID}_ekf",
        "data": data,
    }


def _store_data(hass_storage: dict[str, Any]) -> dict[str, Any]:
    return hass_storage[f"{DOMAIN}_{ENTRY_ID}_ekf"]["data"]


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


def _reset_cal(coord: Any) -> None:
    act = coord.runtime.actuator
    act.cal_baseline = None
    act.cal_entity = None
    act.last_cal_value = None
    act.last_cal_write_ts = None
    act.last_cal_dispatch_wall_ts = None
    act.last_cal_restore_ts = None
    coord.runtime.diagnostics.cal_diverged = False
    coord.runtime.diagnostics.cal_handoff_pending = False


def _cal_writes(calls: list[Any]) -> list[Any]:
    return [c for c in calls if c.data.get("entity_id") == CAL]


def _issue(hass: HomeAssistant, key: str) -> Any:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}_{ENTRY_ID}")


RECONF_SUBMIT: dict[str, Any] = {
    CONF_NAME: "Test Room",
    CONF_TEMP_SENSOR: "sensor.room_temp",
    CONF_ACTUATOR: NEW_TRV,
    "sensors": {},
}


# =============================================================================
# Der Reconfigure-Race-Test (§0.6 Punkt 1 + §0.6a Punkt 1) — Reviewer-Fokus #1
# =============================================================================


@pytest.mark.parametrize("with_baseline", [True, False], ids=["baseline", "none"])
async def test_race_no_reacquisition_between_handoff_and_entry_update(
    hass: HomeAssistant, hass_storage: dict[str, Any], with_baseline: bool
) -> None:
    """Nach erfolgreichem Handoff-Port und VOR jedem Entry-Update erzwingt der
    Test einen Tick des alten Coordinators: kein ``cal_write``-Dispatch, die
    Ownership bleibt leer — die Reakquisitions-Sperre (``_trv_calibration =
    False`` unter dem Lock) hielt. Parametrisiert (i) Baseline vorhanden und
    (ii) ``cal_baseline=None`` bei aktivierter Option (§0.6a Punkt 1: auch der
    Early-Return muss sperren). Danach Unload: der Final Save darf keine
    Ownership persistieren (F27-Regression)."""
    _register_trv_device(hass)
    _set_states(hass, room=20.5, trv_temp=22.0, cal="0.0")
    entry = await _setup(hass)
    coord = entry.runtime_data
    coord.runtime.clock = _FakeClock(1000.0)
    _reset_cal(coord)
    if with_baseline:
        # Bestehende Ownership; das Gerät MELDET die Baseline bereits
        # (already_at_target) -> der Port bestätigt ohne Dispatch.
        coord.runtime.actuator.cal_baseline = 0.0
        coord.runtime.actuator.cal_entity = CAL
    set_value = async_mock_service(hass, "number", "set_value")

    result = await coord.async_prepare_actuator_handoff()

    assert result is CalibrationRestoreResult.RESTORED
    assert coord._trv_calibration is False  # die Sperre, in beiden Fällen
    assert coord.runtime.actuator.cal_baseline is None
    assert coord.runtime.actuator.cal_entity is None

    # Der erzwungene Tick des ALTEN Coordinators (Listener/Refresh im
    # F27-Umfeld): Raum 20.5 / TRV 22.0 wäre ein sofortiger Erst-Write,
    # stünde der Kalibrierpfad noch offen.
    await coord.async_refresh()
    await hass.async_block_till_done()

    assert _cal_writes(set_value) == []  # kein cal_write
    assert coord.runtime.actuator.cal_baseline is None  # Ownership leer
    assert coord.runtime.actuator.cal_entity is None

    # F27-Regression: der Final Save beim Unload trägt keine Ownership.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    stored = _store_data(hass_storage)
    assert stored.get("cal_baseline") is None
    assert stored.get("cal_entity") is None


async def test_handoff_port_baseline_without_entity_is_gone(
    hass: HomeAssistant,
) -> None:
    """Korrupte Store-Form (Baseline ohne Entity — der Commit stempelt beide
    zusammen): der Port behandelt sie wie Segment H als strukturell GONE —
    Ownership geräumt, Pfad gesperrt, kein Dispatch-Versuch."""
    _register_trv_device(hass)
    _set_states(hass, cal="0.0")
    entry = await _setup(hass)
    coord = entry.runtime_data
    _reset_cal(coord)
    coord.runtime.actuator.cal_baseline = -1.0  # Entity fehlt

    result = await coord.async_prepare_actuator_handoff()

    assert result is CalibrationRestoreResult.GONE
    assert coord.runtime.actuator.cal_baseline is None
    assert coord._trv_calibration is False


async def test_handoff_port_failed_keeps_ownership_and_gate(
    hass: HomeAssistant,
) -> None:
    """FAILED (Number unavailable): Ownership und ``_trv_calibration`` bleiben
    unangetastet — fail-closed, der Flow entscheidet über den Formularfehler."""
    _register_trv_device(hass)
    _set_states(hass, cal="0.0")
    entry = await _setup(hass)
    coord = entry.runtime_data
    _reset_cal(coord)
    coord.runtime.actuator.cal_baseline = 0.0
    coord.runtime.actuator.cal_entity = CAL
    hass.states.async_set(CAL, "unavailable", CAL_ATTRS)

    result = await coord.async_prepare_actuator_handoff()

    assert result is CalibrationRestoreResult.FAILED
    assert coord.runtime.actuator.cal_baseline == 0.0  # Ownership bleibt
    assert coord.runtime.actuator.cal_entity == CAL
    assert coord._trv_calibration is True  # keine Sperre auf FAILED


# =============================================================================
# Restore-Helper — state-bestätigte Semantik
# =============================================================================


async def test_restore_already_at_target_short_circuits_without_write(
    hass: HomeAssistant,
) -> None:
    """Gerät meldet den (gesnappten) Zielwert bereits -> RESTORED ohne
    Dispatch — der Pfad, über den ein zweiter Versuch nach einem langsamen
    Gerät durchläuft."""
    hass.states.async_set(CAL, "1.0", CAL_ATTRS)
    set_value = async_mock_service(hass, "number", "set_value")

    result = await restore_trv_calibration(hass, entity_id=CAL, baseline=1.0)

    assert result is CalibrationRestoreResult.RESTORED
    assert set_value == []  # kein Write


async def test_restore_write_with_stale_readback_fails_conservatively(
    hass: HomeAssistant,
) -> None:
    """Write dispatcht, aber der frische Rückles zeigt das Ziel nicht (das
    Gerät ist langsam) -> FAILED, kein Polling."""
    hass.states.async_set(CAL, "-1.5", CAL_ATTRS)
    set_value = async_mock_service(hass, "number", "set_value")  # State bleibt

    result = await restore_trv_calibration(hass, entity_id=CAL, baseline=0.0)

    assert result is CalibrationRestoreResult.FAILED
    assert len(set_value) == 1
    assert set_value[0].data["value"] == 0.0  # der gesnappte restore_target


async def test_restore_write_confirmed_by_fresh_readback(
    hass: HomeAssistant,
) -> None:
    """Der Service-Handler aktualisiert den State (Geräte-Echo) -> der
    frische Rückles bestätigt -> RESTORED. Baseline 0.8 snapped auf 1.0."""

    async def _handler(call: ServiceCall) -> None:
        hass.states.async_set(
            call.data["entity_id"], str(call.data["value"]), CAL_ATTRS
        )

    hass.services.async_register("number", "set_value", _handler)
    hass.states.async_set(CAL, "-1.5", CAL_ATTRS)

    result = await restore_trv_calibration(hass, entity_id=CAL, baseline=0.8)

    assert result is CalibrationRestoreResult.RESTORED
    assert hass.states.get(CAL).state == "1.0"  # rasterfest, nie pauschal 0.0


async def test_restore_gone_and_unreadable_mapping(hass: HomeAssistant) -> None:
    """Entity strukturell weg (kein Registry-Eintrag UND kein State) -> GONE;
    vorhanden aber unavailable -> FAILED (unreadable, fail-closed)."""
    assert (
        await restore_trv_calibration(hass, entity_id="number.gone", baseline=0.0)
        is CalibrationRestoreResult.GONE
    )
    hass.states.async_set(CAL, "unavailable", CAL_ATTRS)
    assert (
        await restore_trv_calibration(hass, entity_id=CAL, baseline=0.0)
        is CalibrationRestoreResult.FAILED
    )


async def test_restore_hung_service_times_out_failed_ownership_kept(
    hass: HomeAssistant,
) -> None:
    """AR-24 (P1.5b Important): ein hängender number-Handler wird durch
    ``asyncio.timeout`` begrenzt -> FAILED über dieselbe fail-closed-Grenze
    (Ownership bleibt, ``_trv_calibration`` bleibt scharf) statt den Tick-Lock
    des Ports oder den Reconfigure-Flow einzufrieren. Über den Port gefahren,
    damit genau die Exponierung getestet wird, die der Timeout schützt."""

    _register_trv_device(hass)
    _set_states(hass, cal="-1.5")
    entry = await _setup(hass)
    coord = entry.runtime_data
    _reset_cal(coord)
    coord.runtime.actuator.cal_baseline = 0.0
    coord.runtime.actuator.cal_entity = CAL

    async def _hang(call: ServiceCall) -> None:
        await asyncio.Event().wait()  # hängt, bis die Timeout-Cancellation kommt

    # Erst NACH dem Setup registriert, damit nur der blockende (und damit
    # cancellbare) Port-Write den hängenden Handler trifft.
    hass.services.async_register("number", "set_value", _hang)

    with patch(
        "custom_components.poise.ha.actuator_lifecycle._CALIBRATION_RESTORE_TIMEOUT_S",
        0.05,
    ):
        result = await coord.async_prepare_actuator_handoff()

    assert result is CalibrationRestoreResult.FAILED
    assert coord.runtime.actuator.cal_baseline == 0.0  # Ownership bleibt
    assert coord.runtime.actuator.cal_entity == CAL
    assert coord._trv_calibration is True  # keine Sperre auf FAILED


async def test_restore_blocking_dispatch_error_fails(hass: HomeAssistant) -> None:
    """Der blocking Call macht Service-Fehler synchron sichtbar (F15): kein
    registrierter Service -> Exception -> FAILED statt Absturz."""
    hass.states.async_set(CAL, "-1.5", CAL_ATTRS)

    result = await restore_trv_calibration(hass, entity_id=CAL, baseline=0.0)

    assert result is CalibrationRestoreResult.FAILED


# =============================================================================
# Reconfigure-Flow — Formularfehler, Retry, GONE, kein Wechsel, Store-Pfad
# =============================================================================


async def test_reconfigure_failed_then_retry_at_target_succeeds(
    hass: HomeAssistant,
) -> None:
    """FAILED -> Formularfehler ``calibration_restore_failed``, Entry
    unverändert, Ownership bleibt; zweiter Versuch mit inzwischen gemeldetem
    Ziel -> already_at_target -> RESTORED -> Flow läuft durch."""
    _register_trv_device(hass)
    _set_states(hass, cal="0.0")
    hass.states.async_set(NEW_TRV, "heat", {"hvac_modes": ["heat", "off"]})
    entry = await _setup(hass)
    coord = entry.runtime_data
    _reset_cal(coord)
    coord.runtime.actuator.cal_baseline = 0.0
    coord.runtime.actuator.cal_entity = CAL
    hass.states.async_set(CAL, "unavailable", CAL_ATTRS)
    async_mock_service(hass, "number", "set_value")

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], RECONF_SUBMIT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "calibration_restore_failed"}
    assert entry.data[CONF_ACTUATOR] == TRV  # async_update_entry NICHT gerufen
    assert coord.runtime.actuator.cal_baseline == 0.0  # Ownership bleibt

    # Zweiter Versuch: das Gerät ist aufgewacht und meldet die Baseline.
    hass.states.async_set(CAL, "0.0", CAL_ATTRS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], RECONF_SUBMIT
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ACTUATOR] == NEW_TRV


async def test_reconfigure_gone_warns_and_continues(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """GONE (Entity strukturell weg): WARN mit gesnapshotteter Entity +
    Baseline (§0.6a Punkt 2 — der Port hat sie schon gelöscht), der Flow
    läuft durch — wer den Aktor tauscht, weil das Altgerät verschwunden ist,
    darf nicht blockiert werden."""
    _register_trv_device(hass)
    _set_states(hass, cal="0.0")
    hass.states.async_set(NEW_TRV, "heat", {"hvac_modes": ["heat", "off"]})
    entry = await _setup(hass)
    coord = entry.runtime_data
    _reset_cal(coord)
    coord.runtime.actuator.cal_baseline = -1.5
    coord.runtime.actuator.cal_entity = "number.vanished_calibration"

    with caplog.at_level(logging.WARNING):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], RECONF_SUBMIT
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ACTUATOR] == NEW_TRV
    assert "number.vanished_calibration" in caplog.text
    assert "-1.5" in caplog.text


async def test_reconfigure_without_actuator_change_skips_restore(
    hass: HomeAssistant,
) -> None:
    """Kein Aktorwechsel -> weder Handoff-Port noch Restore-Helper laufen."""
    _register_trv_device(hass)
    _set_states(hass, cal="0.0")
    entry = await _setup(hass)
    coord = entry.runtime_data
    _reset_cal(coord)
    coord.runtime.actuator.cal_baseline = 0.0
    coord.runtime.actuator.cal_entity = CAL

    port = AsyncMock()
    with (
        patch(
            "custom_components.poise.coordinator.PoiseCoordinator."
            "async_prepare_actuator_handoff",
            new=port,
        ),
        patch(
            "custom_components.poise.ha.actuator_lifecycle.restore_trv_calibration",
            new=AsyncMock(),
        ) as helper,
    ):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**RECONF_SUBMIT, CONF_ACTUATOR: TRV}
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    port.assert_not_awaited()
    helper.assert_not_awaited()
    assert coord.runtime.actuator.cal_baseline == 0.0  # unangetastet


async def test_reconfigure_unloaded_entry_uses_store_truth(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Ungeladene Entry: der Store ist die Wahrheit (§0.5 Punkt 1) — Restore
    über den Helper, bei RESTORED werden die zwei Ownership-Keys im Store
    geräumt."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(TRV, "heat", {"hvac_modes": ["heat", "off"]})
    hass.states.async_set(NEW_TRV, "heat", {"hvac_modes": ["heat", "off"]})
    hass.states.async_set(CAL, "0.5", CAL_ATTRS)  # already_at_target
    _seed_store(hass_storage, {"cal_baseline": 0.5, "cal_entity": CAL})
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TRV,
        entry_id=ENTRY_ID,
        data=_base(),
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], RECONF_SUBMIT
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ACTUATOR] == NEW_TRV
    stored = _store_data(hass_storage)
    assert stored.get("cal_baseline") is None
    assert stored.get("cal_entity") is None


async def test_reconfigure_unloaded_corrupt_store_shape_is_gone(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ungeladene Entry mit Baseline OHNE Entity (korrupte Store-Form):
    strukturell GONE -> WARN + durchlaufen, die Keys werden geräumt."""
    async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(TRV, "heat", {"hvac_modes": ["heat", "off"]})
    hass.states.async_set(NEW_TRV, "heat", {"hvac_modes": ["heat", "off"]})
    _seed_store(hass_storage, {"cal_baseline": -1.0})
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TRV,
        entry_id=ENTRY_ID,
        data=_base(),
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.poise.async_setup_entry", return_value=True),
        caplog.at_level(logging.WARNING),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], RECONF_SUBMIT
        )
        await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert _store_data(hass_storage)["cal_baseline"] is None
    assert "-1.0" in caplog.text


async def test_reconfigure_unloaded_entry_failed_keeps_store(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Ungeladene Entry, Number unavailable -> FAILED: Formularfehler, Entry
    unverändert, die Store-Keys bleiben stehen."""
    hass.states.async_set(TRV, "heat", {"hvac_modes": ["heat", "off"]})
    hass.states.async_set(NEW_TRV, "heat", {"hvac_modes": ["heat", "off"]})
    hass.states.async_set(CAL, "unavailable", CAL_ATTRS)
    _seed_store(hass_storage, {"cal_baseline": 0.5, "cal_entity": CAL})
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TRV,
        entry_id=ENTRY_ID,
        data=_base(),
        title="Test Room",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.poise.async_setup_entry", return_value=True):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], RECONF_SUBMIT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "calibration_restore_failed"}
    assert entry.data[CONF_ACTUATOR] == TRV
    assert _store_data(hass_storage)["cal_baseline"] == 0.5
    assert _store_data(hass_storage)["cal_entity"] == CAL


# =============================================================================
# Teardown — eigenes Gate VOR has_actuated (Entfernen UND Deaktivieren)
# =============================================================================


def _teardown_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TRV,
        entry_id=ENTRY_ID,
        data=_base(),
        title="Test Room",
    )
    entry.add_to_hass(hass)
    return entry


async def test_teardown_restores_even_without_has_actuated(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Das Kalibrier-Gate steht VOR dem ``has_actuated``-Return: Baseline
    vorhanden + ``has_actuated=False`` -> Restore läuft trotzdem (und räumt
    die Keys), der Park unterbleibt weiterhin."""
    hass.states.async_set(CAL, "0.0", CAL_ATTRS)  # already_at_target
    _seed_store(
        hass_storage,
        {"cal_baseline": 0.0, "cal_entity": CAL, "has_actuated": False},
    )
    entry = _teardown_entry(hass)
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "number", "set_value")

    await _park_room_actuator(hass, entry, live_mode=False)

    stored = _store_data(hass_storage)
    assert stored["cal_baseline"] is None  # RESTORED -> Keys geräumt
    assert stored["cal_entity"] is None
    assert set_mode == []  # AR-11: nie aktuiert -> kein Park


async def test_teardown_failed_keeps_keys_and_logs_unmistakably(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """FAILED beim endgültigen Entfernen: es gibt keinen weiteren Versuch —
    die Keys bleiben als Beleg, der Log nennt Entity UND Baseline-Wert."""
    hass.states.async_set(CAL, "unavailable", CAL_ATTRS)
    _seed_store(
        hass_storage,
        {"cal_baseline": -1.5, "cal_entity": CAL, "has_actuated": False},
    )
    entry = _teardown_entry(hass)

    with caplog.at_level(logging.WARNING):
        await _park_room_actuator(hass, entry, live_mode=False)

    stored = _store_data(hass_storage)
    assert stored["cal_baseline"] == -1.5  # Keys bleiben
    assert stored["cal_entity"] == CAL
    assert CAL in caplog.text
    assert "-1.5" in caplog.text


@pytest.mark.parametrize(
    "seed",
    [
        {"cal_baseline": -1.0, "has_actuated": False},
        # P1.5b Minor 2: nicht-numerische Baseline — dieselbe GONE-Regel
        # (resolve_restore), damit die Store-Bereinigung trotzdem läuft.
        {"cal_baseline": "kaputt", "cal_entity": CAL, "has_actuated": False},
    ],
    ids=["entity_missing", "baseline_not_numeric"],
)
async def test_teardown_corrupt_store_shape_clears_as_gone(
    hass: HomeAssistant, hass_storage: dict[str, Any], seed: dict[str, Any]
) -> None:
    """Korrupte Store-Form (Baseline ohne Entity, oder nicht-numerische
    Baseline): GONE -> die Keys werden geräumt statt einen Restore auf nichts
    zu versuchen."""
    hass.states.async_set(CAL, "0.0", CAL_ATTRS)
    _seed_store(hass_storage, dict(seed))
    entry = _teardown_entry(hass)

    await _park_room_actuator(hass, entry, live_mode=False)

    assert _store_data(hass_storage)["cal_baseline"] is None
    assert _store_data(hass_storage)["cal_entity"] is None


async def test_teardown_disable_path_restores_before_park(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Auch der Disable-Pfad (``live_mode=True``) räumt eine bestätigte
    Ownership; mit ``has_actuated=True`` läuft danach der normale Park."""
    hass.states.async_set(TRV, "heat", {"hvac_modes": ["heat", "off"], "min_temp": 5})
    hass.states.async_set(CAL, "0.0", CAL_ATTRS)
    _seed_store(
        hass_storage,
        {
            "cal_baseline": 0.0,
            "cal_entity": CAL,
            "has_actuated": True,
            "climate_mode": "auto",
        },
    )
    entry = _teardown_entry(hass)
    set_mode = async_mock_service(hass, "climate", "set_hvac_mode")
    async_mock_service(hass, "climate", "set_temperature")

    await _park_room_actuator(hass, entry, live_mode=True)

    assert _store_data(hass_storage)["cal_baseline"] is None
    assert len(set_mode) == 1  # der Park lief (heat-fähiges Gerät)


# =============================================================================
# Repair-Kind ``trv_calibration`` — Bedingung + Apply-only-Flow
# =============================================================================


async def test_repair_condition_capable_and_option_off_raises_issue(
    hass: HomeAssistant,
) -> None:
    """Fähiges TRV (Kalibrier-Number + wörtliches ``heat``) + Option AUS ->
    fixable Issue ``calibration_available`` mit Kind ``trv_calibration``."""
    _register_trv_device(hass)
    _set_states(hass)
    await _setup(hass, **{CONF_TRV_CALIBRATION: False})

    issue = _issue(hass, "calibration_available")
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.data == {"entry_id": ENTRY_ID, "kind": "trv_calibration"}


async def test_repair_condition_option_on_no_issue(hass: HomeAssistant) -> None:
    _register_trv_device(hass)
    _set_states(hass)
    async_mock_service(hass, "number", "set_value")
    await _setup(hass, **{CONF_TRV_CALIBRATION: True})

    assert _issue(hass, "calibration_available") is None


async def test_repair_condition_ext_temp_reserved_no_issue(
    hass: HomeAssistant,
) -> None:
    """Ein strukturell vorhandener Ext-Temp-Eingang verdrängt die
    Kalibrierung (D6) — keine Suggestion, obwohl die Number existiert."""
    _register_trv_device(hass, with_ext_number=True)
    _set_states(hass, ext=True)
    async_mock_service(hass, "number", "set_value")
    await _setup(hass, **{CONF_TRV_CALIBRATION: False, CONF_TRV_EXTERNAL_TEMP: EXT})

    assert _issue(hass, "calibration_available") is None


async def test_repair_apply_sets_option_without_cooldown_and_no_dismiss(
    hass: HomeAssistant,
) -> None:
    """Apply schreibt ``trv_calibration=True`` über den Options-Pfad
    (``async_update_entry`` -> Hot-Apply), stempelt KEINEN Cooldown und der
    Flow besitzt keinen ``async_step_dismiss`` — Ablehnung ist HAs
    eingebautes Issue-Ignorieren."""
    _register_trv_device(hass)
    _set_states(hass)
    entry = await _setup(hass, **{CONF_TRV_CALIBRATION: False})
    coord = entry.runtime_data
    async_mock_service(hass, "number", "set_value")

    flow = await async_create_fix_flow(
        hass,
        f"calibration_available_{ENTRY_ID}",
        {"entry_id": ENTRY_ID, "kind": "trv_calibration"},
    )
    assert isinstance(flow, CalibrationOptInFixFlow)
    assert not hasattr(flow, "async_step_dismiss")  # Ablehnung = HA-Ignore
    flow.hass = hass
    flow.flow_id = "test-flow"
    flow.handler = DOMAIN

    result = await flow.async_step_init(None)
    assert result["type"] is FlowResultType.FORM

    result = await flow.async_step_init({})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TRV_CALIBRATION] is True
    assert coord._trv_calibration is True  # über den Listener hot-applied
    # Kein Learning-Cooldown gestempelt (weder L2- noch clo-Slot).
    assert coord.runtime.user.suggestion_rejected_key is None
    assert coord.runtime.user.clo_suggestion_rejected_key is None
