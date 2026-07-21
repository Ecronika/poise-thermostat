"""Phase 5B — Executor-Sequenzen + ``commit_execution`` (Befunde 6+9+11).

Plan: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md, Abschnitt 6
Phase 5B. Die fuenf ``run_*``-Sequenz-Methoden des ``ActuatorExecutor``
besitzen die heutigen Try-Grenzen (Grenz-Logging ueber den INJIZIERTEN
Coordinator-Logger: Text, Level ERROR, Kanal
``custom_components.poise.coordinator``, Traceback — 5A-Lektion: der Kanal
ist Verhalten) und liefern ein GEORDNETES ``ExecutionReport``;
``coord.commit_execution(report, post_actions, now=...)`` faltet strikt in
Call-Reihenfolge ueber die heutigen ``self._*``-Attribute (Uebergangsheim;
wandert mit ``ZoneRuntime`` in Phase 6).

Hier exerziert: alle fuenf Sequenzen inkl. Abbruch-/Skip-Faellen (Recorder +
werfende Dispatches nach dem Phase-0-Injektionsmuster: fehlender Service ->
synchroner ``ServiceNotFound``; Setpoint-Pfad via ``patch.object(actuator_mod,
"write")``) sowie die Commit-Tabelle Attempt/Success je Effekt-Typ, die
Fold-Ordnung und der EndHold-Teardown OHNE Bus-Fire (Event via
``CommitResult.events``, Feuern bleibt Adapter-Sache). Die Coordinator-Sites
selbst laufen bis zur Site-Umstellung unveraendert — die Phase-0-Pins
(attempt_success, frost_rescue_matrix, effect_sequences, event_order,
persistence_checkpoint) bleiben davon unberuehrt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
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
    DOMAIN,
)
from custom_components.poise.contracts import ActuatorCommand, ActuatorPath
from custom_components.poise.control.lifecycle import SafeStatePlan
from custom_components.poise.ha.actuator_executor import ActuatorExecutor
from custom_components.poise.runtime.tick_result import (
    EffectExecution,
    EndHold,
    ExecutionReport,
    ExternalTemperaturePlan,
    OverrideEnded,
    PostExecutionAction,
)

TRV = "climate.trv"
SELECT = "select.trv_sensor_mode"
EXT = "number.trv_external_temperature"
ZONE = "Wohnzimmer"

# Produktionsverdrahtung gespiegelt (5A-Muster): der Coordinator injiziert
# sein Modul-``_LOGGER``, damit jeder Grenz-Record den Baseline-Kanal traegt.
_COORD_LOGGER = logging.getLogger("custom_components.poise.coordinator")
_CHANNEL = "custom_components.poise.coordinator"


def _executor(hass: HomeAssistant) -> ActuatorExecutor:
    return ActuatorExecutor(hass, logger=_COORD_LOGGER)


def _error_records(
    caplog: pytest.LogCaptureFixture, message: str
) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == message]


def _assert_boundary_record(
    caplog: pytest.LogCaptureFixture, message: str, *, count: int = 1
) -> None:
    """Text, Level ERROR, Coordinator-Kanal und Traceback — alle vier Aspekte
    des Log-Records sind eingefrorenes Verhalten (LEITPRINZIP)."""
    records = _error_records(caplog, message)
    assert len(records) == count, f"{message!r}: {len(records)} records"
    for r in records:
        assert r.name == _CHANNEL
        assert r.levelno == logging.ERROR
        assert r.exc_info is not None, "boundary logs via .exception -> traceback"


# =============================================================================
# Site 1 — run_mode_nudge (eine Grenze, V2-tagged)
# =============================================================================


async def test_mode_nudge_success_reports_and_tags(hass: HomeAssistant) -> None:
    """Erfolg: exakte Dispatch-Form (via 5A-Primitive) mit selbst erzeugtem
    Context; Report traegt attempted/success/context_id/commanded_mode und
    reicht das dispatch-zeitige M2-Flag unveraendert durch."""
    calls = async_mock_service(hass, "climate", "set_hvac_mode")
    report = await _executor(hass).run_mode_nudge(TRV, "heat", mode_changed=True)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert dict(calls[0].data) == {"entity_id": TRV, "hvac_mode": "heat"}
    (execution,) = report.executions
    assert execution.effect_id == "mode_nudge"
    assert execution.attempted is True
    assert execution.success is True
    assert execution.context_id == calls[0].context.id  # der EIGENE Context
    assert execution.commanded_mode == "heat"
    assert execution.mode_changed is True
    assert execution.pre_write_value is None
    assert execution.commanded_value is None


async def test_mode_nudge_failure_keeps_attempt_state_and_logs(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Fehlender Service -> synchroner Wurf INNERHALB der Grenze: success
    False, aber der Context wurde VOR dem Dispatch erzeugt (Attempt-State,
    Phase-0-Muster) und der Log-Record ist heutiger Text/Level/Kanal/TB."""
    assert not hass.services.has_service("climate", "set_hvac_mode")
    report = await _executor(hass).run_mode_nudge(TRV, "cool", mode_changed=False)

    (execution,) = report.executions
    assert execution.attempted is True
    assert execution.success is False
    assert execution.context_id is not None  # attempt state trotz Wurf
    assert execution.mode_changed is False
    _assert_boundary_record(caplog, f"Poise: set_hvac_mode(cool) failed for {TRV}")


# =============================================================================
# Site 2 — run_setpoint_write (eine Grenze, V2-tagged, RAW auf dem Draht)
# =============================================================================


def _tick_cmd(value: float) -> ActuatorCommand:
    return ActuatorCommand(
        actuator_id=TRV,
        path=ActuatorPath.SETPOINT,
        value=value,
        hvac_mode="heat",
        reason="tick",
    )


async def test_setpoint_write_success_snapped_report_raw_wire(
    hass: HomeAssistant,
) -> None:
    """Erfolg: der ROHE Wert geht auf den Draht, der Report traegt den
    GESNAPPTEN Echo-Baseline-Wert + final_mode (Mode-String am
    Setpoint-Effekt) + pre_write_value; Context selbst erzeugt/gemeldet."""
    calls = async_mock_service(hass, "climate", "set_temperature")
    report = await _executor(hass).run_setpoint_write(
        _tick_cmd(20.3),  # bewusst kein 0.5er-Step
        pre_write_value=19.5,
        snapped_value=20.5,
        final_mode="heat",
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert dict(calls[0].data) == {"entity_id": TRV, "temperature": 20.3}  # raw
    (execution,) = report.executions
    assert execution.effect_id == "setpoint_write"
    assert execution.success is True
    assert execution.context_id == calls[0].context.id
    assert execution.pre_write_value == 19.5
    assert execution.commanded_value == 20.5  # gesnappt, NIE der Draht-Wert
    assert execution.commanded_mode == "heat"


async def test_setpoint_write_failure_attempt_state_and_log(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Injektion auf ``actuator_mod.write`` (Phase-0-Flaeche): success False,
    Attempt-Felder (pre_write_value, context_id) vollstaendig, Log-Record
    exakt wie heute; der Executor-Context ging an den Write."""
    cmd = _tick_cmd(21.0)
    with patch.object(
        actuator_mod, "write", side_effect=HomeAssistantError("injected")
    ) as mock_write:
        report = await _executor(hass).run_setpoint_write(
            cmd, pre_write_value=20.0, snapped_value=21.0, final_mode="heat"
        )

    (execution,) = report.executions
    assert execution.attempted is True
    assert execution.success is False
    assert execution.pre_write_value == 20.0
    assert execution.context_id is not None
    assert mock_write.call_args.kwargs["context"].id == execution.context_id
    _assert_boundary_record(caplog, f"Poise: actuator write failed for {TRV}")


# =============================================================================
# Site 3 — run_ext_temp (Select/Feed, sequenz-interner Settle-Skip)
# =============================================================================


async def test_ext_temp_select_success_skips_feed(hass: HomeAssistant) -> None:
    """Select-Erfolg -> Feed in DIESEM Tick uebersprungen (Geraet settlet);
    der Skip ist sequenz-intern und erscheint als attempted=False."""
    selects = async_mock_service(hass, "select", "select_option")
    feeds = async_mock_service(hass, "number", "set_value")
    plan = ExternalTemperaturePlan(select_external=True, feed_value=21.3)
    report = await _executor(hass).run_ext_temp(
        plan, select_entity_id=SELECT, number_entity_id=EXT
    )
    await hass.async_block_till_done()

    assert len(selects) == 1
    assert dict(selects[0].data) == {"entity_id": SELECT, "option": "external"}
    assert feeds == []  # settle tick: kein Feed
    select, feed = report.executions
    assert (select.effect_id, select.attempted, select.success) == (
        "ext_select",
        True,
        True,
    )
    assert (feed.effect_id, feed.attempted, feed.success) == (
        "ext_feed",
        False,
        False,
    )
    assert feed.commanded_value == 21.3


async def test_ext_temp_select_failure_still_feeds(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Select-Wurf -> Feed laeuft TROTZDEM (Befund 11 #3): Select-Log wie
    heute, Feed dispatcht mit dem gerundeten Wert."""
    assert not hass.services.has_service("select", "select_option")
    feeds = async_mock_service(hass, "number", "set_value")
    plan = ExternalTemperaturePlan(select_external=True, feed_value=20.9)
    report = await _executor(hass).run_ext_temp(
        plan, select_entity_id=SELECT, number_entity_id=EXT
    )
    await hass.async_block_till_done()

    assert len(feeds) == 1
    assert dict(feeds[0].data) == {"entity_id": EXT, "value": 20.9}
    select, feed = report.executions
    assert select.success is False
    assert (feed.attempted, feed.success) == (True, True)
    _assert_boundary_record(caplog, "Poise: sensor-select switch failed")
    assert "external-temp write failed" not in caplog.text


async def test_ext_temp_feed_only_and_feed_failure(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Kein Select geplant -> nur der Feed; ein Feed-Wurf loggt heutigen
    Text und liefert success False (best-effort)."""
    assert not hass.services.has_service("number", "set_value")
    plan = ExternalTemperaturePlan(select_external=False, feed_value=19.8)
    report = await _executor(hass).run_ext_temp(
        plan, select_entity_id=None, number_entity_id=EXT
    )

    (feed,) = report.executions
    assert (feed.effect_id, feed.attempted, feed.success) == (
        "ext_feed",
        True,
        False,
    )
    _assert_boundary_record(caplog, f"Poise: external-temp write failed for {EXT}")


async def test_ext_temp_nothing_planned_yields_empty_report(
    hass: HomeAssistant,
) -> None:
    """feed_value=None (Gate ``external_feed_due`` sagte nein) ohne Select ->
    leerer Report, null Dispatches; Select geplant ohne Entity ist ein
    Programmierfehler (ValueError)."""
    plan = ExternalTemperaturePlan(select_external=False, feed_value=None)
    report = await _executor(hass).run_ext_temp(
        plan, select_entity_id=None, number_entity_id=EXT
    )
    assert report.executions == ()

    with pytest.raises(ValueError, match="select planned without"):
        await _executor(hass).run_ext_temp(
            ExternalTemperaturePlan(select_external=True, feed_value=None),
            select_entity_id=None,
            number_entity_id=EXT,
        )


# =============================================================================
# Site 4 — run_frost_rescue (ZWEI unabhaengige Grenzen)
# =============================================================================


async def test_frost_rescue_success_order_nudge_before_write(
    hass: HomeAssistant,
) -> None:
    """Beide Erfolge: Dispatch-Reihenfolge Nudge VOR Floor-Write (Phase-0-
    Ordnungspin), Report geordnet, Floor-Payload exakt wie heute."""
    order: list[tuple[str, dict[str, Any]]] = []

    async def _rec_mode(call: ServiceCall) -> None:
        order.append(("set_hvac_mode", dict(call.data)))

    async def _rec_temp(call: ServiceCall) -> None:
        order.append(("set_temperature", dict(call.data)))

    hass.services.async_register("climate", "set_hvac_mode", _rec_mode)
    hass.services.async_register("climate", "set_temperature", _rec_temp)

    report = await _executor(hass).run_frost_rescue(TRV, 7.0, nudge=True)
    await hass.async_block_till_done()

    assert [n for n, _ in order] == ["set_hvac_mode", "set_temperature"]
    assert order[0][1] == {"entity_id": TRV, "hvac_mode": "heat"}
    assert order[1][1] == {"entity_id": TRV, "temperature": 7.0}
    nudge, write = report.executions
    assert (nudge.effect_id, nudge.success, nudge.commanded_mode) == (
        "rescue_nudge",
        True,
        "heat",
    )
    assert (write.effect_id, write.success, write.commanded_value) == (
        "rescue_write",
        True,
        7.0,
    )


async def test_frost_rescue_nudge_failure_never_skips_floor_write(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Nudge wirft -> der Floor-Write laeuft TROTZDEM (unabhaengige Grenzen,
    test_phase0_effect_sequences-Semantik); nur der Nudge-Log erscheint."""
    assert not hass.services.has_service("climate", "set_hvac_mode")
    writes = async_mock_service(hass, "climate", "set_temperature")

    report = await _executor(hass).run_frost_rescue(TRV, 7.0, nudge=True)
    await hass.async_block_till_done()

    assert len(writes) == 1, "a failed nudge must never skip the floor write"
    nudge, write = report.executions
    assert (nudge.attempted, nudge.success) == (True, False)
    assert (write.attempted, write.success) == (True, True)
    _assert_boundary_record(caplog, f"Poise: frost rescue nudge failed for {TRV}")
    assert "frost rescue write failed" not in caplog.text


async def test_frost_rescue_write_failure_independent_of_nudge(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Write wirft (Injektion), Nudge gelang: Kommando-Payload wie heute
    (reason='frost_rescue', ohne Context-Tag), nur der Write-Log erscheint."""
    nudges = async_mock_service(hass, "climate", "set_hvac_mode")
    with patch.object(
        actuator_mod, "write", side_effect=HomeAssistantError("injected")
    ) as mock_write:
        report = await _executor(hass).run_frost_rescue(TRV, 7.5, nudge=True)
    await hass.async_block_till_done()

    assert len(nudges) == 1
    cmd = mock_write.call_args.args[1]
    assert cmd.actuator_id == TRV
    assert cmd.value == 7.5
    assert cmd.hvac_mode == "heat"
    assert cmd.reason == "frost_rescue"
    assert mock_write.call_args.kwargs == {"context": None}  # untagged
    nudge, write = report.executions
    assert nudge.success is True
    assert write.success is False
    _assert_boundary_record(caplog, f"Poise: frost rescue write failed for {TRV}")
    assert "frost rescue nudge failed" not in caplog.text


async def test_frost_rescue_without_nudge_writes_only(hass: HomeAssistant) -> None:
    """Kein Nudge geplant (Geraet schon in heat) -> genau der Floor-Write."""
    writes = async_mock_service(hass, "climate", "set_temperature")
    report = await _executor(hass).run_frost_rescue(TRV, 7.0, nudge=False)
    await hass.async_block_till_done()

    assert len(writes) == 1
    (write,) = report.executions
    assert (write.effect_id, write.success) == ("rescue_write", True)


# =============================================================================
# Site 5 — run_unavailable_safe (EINE gemeinsame Grenze)
# =============================================================================


async def test_unavailable_safe_mode_failure_aborts_sequence(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Mode-Wurf bricht die Sequenz ab: KEIN Setpoint-Dispatch, Setpoint im
    Report attempted=False; EIN Log-Record mit heutigem Zonen-Text."""
    assert not hass.services.has_service("climate", "set_hvac_mode")
    writes = async_mock_service(hass, "climate", "set_temperature")
    plan = SafeStatePlan("heat", 7.0, True, True)

    report = await _executor(hass).run_unavailable_safe(
        plan, entity_id=TRV, zone_name=ZONE
    )
    await hass.async_block_till_done()

    assert writes == [], "a mode dispatch error must skip the setpoint write"
    mode, setpoint = report.executions
    assert (mode.effect_id, mode.attempted, mode.success) == (
        "safe_mode",
        True,
        False,
    )
    assert mode.commanded_mode == "heat"
    assert (setpoint.effect_id, setpoint.attempted, setpoint.success) == (
        "safe_setpoint",
        False,
        False,
    )
    _assert_boundary_record(
        caplog, f"Poise {ZONE}: unavailable-safe write failed", count=1
    )


async def test_unavailable_safe_setpoint_failure_keeps_mode_success(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Mode-Erfolg + Setpoint-Wurf: der Mode-Erfolg bleibt im Report bestehen
    (die Stempel ueberleben den spaeteren Wurf), gleicher EIN-Record-Log."""
    nudges = async_mock_service(hass, "climate", "set_hvac_mode")
    plan = SafeStatePlan("heat", 7.0, True, True)
    with patch.object(
        actuator_mod, "write", side_effect=HomeAssistantError("injected")
    ) as mock_write:
        report = await _executor(hass).run_unavailable_safe(
            plan, entity_id=TRV, zone_name=ZONE
        )
    await hass.async_block_till_done()

    assert len(nudges) == 1
    cmd = mock_write.call_args.args[1]
    assert cmd.reason == "unavailable_safe"
    assert cmd.value == 7.0
    mode, setpoint = report.executions
    assert mode.success is True
    assert (setpoint.attempted, setpoint.success) == (True, False)
    _assert_boundary_record(
        caplog, f"Poise {ZONE}: unavailable-safe write failed", count=1
    )


async def test_unavailable_safe_partial_plans(hass: HomeAssistant) -> None:
    """Nur-Mode- bzw. Nur-Setpoint-Plaene erzeugen genau den einen geplanten
    Effekt (write_mode/write_setpoint entscheiden, Off-Pfad: setpoint=None)."""
    nudges = async_mock_service(hass, "climate", "set_hvac_mode")
    writes = async_mock_service(hass, "climate", "set_temperature")
    ex = _executor(hass)

    off_report = await ex.run_unavailable_safe(
        SafeStatePlan("off", None, True, False), entity_id=TRV, zone_name=ZONE
    )
    setpoint_report = await ex.run_unavailable_safe(
        SafeStatePlan("heat", 7.0, False, True), entity_id=TRV, zone_name=ZONE
    )
    await hass.async_block_till_done()

    assert len(nudges) == 1  # nur der Off-Plan nudgte
    assert len(writes) == 1  # nur der Setpoint-Plan schrieb
    (off_mode,) = off_report.executions
    assert (off_mode.effect_id, off_mode.commanded_mode) == ("safe_mode", "off")
    (safe_sp,) = setpoint_report.executions
    assert (safe_sp.effect_id, safe_sp.commanded_value) == ("safe_setpoint", 7.0)


# =============================================================================
# commit_execution — Fold-Ordnung, Attempt/Success-Regeln, EndHold-Teardown
# =============================================================================

ROOM_DATA: dict[str, Any] = {
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
}


async def _coord(hass: HomeAssistant) -> Any:
    hass.states.async_set(
        "sensor.room_temp",
        "20.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set(
        TRV,
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
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=TRV, data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


def _exec(
    effect_id: str,
    *,
    attempted: bool = True,
    success: bool = True,
    context_id: str | None = None,
    pre_write_value: float | None = None,
    commanded_value: float | None = None,
    commanded_mode: str | None = None,
    mode_changed: bool = False,
) -> EffectExecution:
    return EffectExecution(
        effect_id=effect_id,
        attempted=attempted,
        success=success,
        context_id=context_id,
        pre_write_value=pre_write_value,
        commanded_value=commanded_value,
        commanded_mode=commanded_mode,
        mode_changed=mode_changed,
    )


async def test_commit_setpoint_write_attempt_vs_success(
    hass: HomeAssistant,
) -> None:
    """Plan-5B-Tabelle Zeilen 1+2: attempted -> pre_write_sp + Context-ID
    (auch bei Fehlschlag, Phase-0 Fall A); success -> gesnappte Baseline,
    ts, Mode, has_actuated+dirty."""
    coord = await _coord(hass)
    coord._pre_write_sp = 15.0  # sentinel
    coord._last_written_sp = 20.0
    coord._last_sp_write_ts = 1000.0
    coord._last_written_mode = None
    coord._has_actuated = False
    coord._dirty = False
    ctx_before = len(coord._own_write_ctx_ids)

    failed = ExecutionReport(
        executions=(
            _exec(
                "setpoint_write",
                success=False,
                context_id="ctx-fail",
                pre_write_value=20.0,
                commanded_value=21.5,
                commanded_mode="heat",
            ),
        )
    )
    result = coord.commit_execution(failed, now=2000.0)
    assert result.events == ()
    assert coord._pre_write_sp == 20.0  # attempt stamp
    assert list(coord._own_write_ctx_ids)[ctx_before:] == ["ctx-fail"]
    assert coord._last_written_sp == 20.0  # success stamps untouched
    assert coord._last_sp_write_ts == 1000.0
    assert coord._last_written_mode is None
    assert coord._has_actuated is False
    assert coord._dirty is False

    ok = ExecutionReport(
        executions=(
            _exec(
                "setpoint_write",
                context_id="ctx-ok",
                pre_write_value=20.0,
                commanded_value=21.5,
                commanded_mode="heat",
            ),
        )
    )
    coord.commit_execution(ok, now=2100.0)
    assert coord._last_written_sp == 21.5  # der GESNAPPTE Report-Wert
    assert coord._last_sp_write_ts == 2100.0
    assert coord._last_written_mode == "heat"
    assert coord._has_actuated is True
    assert coord._dirty is True  # _mark_actuated: erster Flip persistiert
    assert list(coord._own_write_ctx_ids)[ctx_before:] == ["ctx-fail", "ctx-ok"]


async def test_commit_mode_nudge_m2_gated_ts(hass: HomeAssistant) -> None:
    """Plan-5B-Tabelle 'Mode-Write success': last_commanded_hvac IMMER,
    last_hvac_cmd_ts NUR bei echtem Moduswechsel (M2, dispatch-zeitig
    evaluiert); Fehlschlag registriert nur die Context-ID."""
    coord = await _coord(hass)
    coord._last_commanded_hvac = "heat"
    coord._last_hvac_cmd_ts = 500.0
    ctx_before = len(coord._own_write_ctx_ids)

    # identischer Re-Nudge (mode_changed=False): ts NICHT neu armieren (B1).
    coord.commit_execution(
        ExecutionReport(
            executions=(_exec("mode_nudge", context_id="ctx-a", commanded_mode="heat"),)
        ),
        now=900.0,
    )
    assert coord._last_commanded_hvac == "heat"
    assert coord._last_hvac_cmd_ts == 500.0

    # echter Wechsel: ts = now.
    coord.commit_execution(
        ExecutionReport(
            executions=(
                _exec(
                    "mode_nudge",
                    context_id="ctx-b",
                    commanded_mode="cool",
                    mode_changed=True,
                ),
            )
        ),
        now=950.0,
    )
    assert coord._last_commanded_hvac == "cool"
    assert coord._last_hvac_cmd_ts == 950.0

    # Wurf: Attempt-State (Context-ID) ja, Stempel nein.
    coord.commit_execution(
        ExecutionReport(
            executions=(
                _exec(
                    "mode_nudge",
                    success=False,
                    context_id="ctx-c",
                    commanded_mode="heat",
                    mode_changed=True,
                ),
            )
        ),
        now=980.0,
    )
    assert coord._last_commanded_hvac == "cool"  # unveraendert
    assert coord._last_hvac_cmd_ts == 950.0
    assert list(coord._own_write_ctx_ids)[ctx_before:] == [
        "ctx-a",
        "ctx-b",
        "ctx-c",
    ]


async def test_commit_rescue_effects(hass: HomeAssistant) -> None:
    """Rescue-Nudge: ts UNCONDITIONAL (kein M2 — eigener Effekt-Typ);
    Rescue-Write: last_written_sp=None (B2) + has_actuated."""
    coord = await _coord(hass)
    coord._last_commanded_hvac = "heat"  # schon heat -> M2 wuerde NICHT stempeln
    coord._last_hvac_cmd_ts = 500.0
    coord._last_written_sp = 20.0
    coord._has_actuated = False
    coord._dirty = False

    coord.commit_execution(
        ExecutionReport(
            executions=(
                _exec("rescue_nudge", commanded_mode="heat"),
                _exec("rescue_write", commanded_value=7.0),
            )
        ),
        now=1234.0,
    )
    assert coord._last_commanded_hvac == "heat"
    assert coord._last_hvac_cmd_ts == 1234.0  # unconditional re-arm
    assert coord._last_written_sp is None  # B2, NICHT der Rescue-Wert
    assert coord._has_actuated is True
    assert coord._dirty is True


async def test_commit_ext_effects(hass: HomeAssistant) -> None:
    """Feed-Erfolg stempelt last_fed/last_fed_ts; der Select stempelt NIE
    (sequenz-interner switched-Flag); Fehlschlaege stempeln nichts."""
    coord = await _coord(hass)
    coord._last_fed = None
    coord._last_fed_ts = 0.0

    coord.commit_execution(
        ExecutionReport(
            executions=(
                _exec("ext_select"),
                _exec("ext_feed", attempted=False, success=False, commanded_value=21.3),
            )
        ),
        now=800.0,
    )
    assert coord._last_fed is None  # settle skip: nichts gestempelt
    assert coord._last_fed_ts == 0.0

    coord.commit_execution(
        ExecutionReport(executions=(_exec("ext_feed", commanded_value=21.3),)),
        now=860.0,
    )
    assert coord._last_fed == 21.3
    assert coord._last_fed_ts == 860.0


async def test_commit_safe_effects(hass: HomeAssistant) -> None:
    """Safe-State-Zeile der Tabelle: Mode-Teil stempelt written_mode UND
    commanded_hvac (K2); Setpoint-Teil last_target + last_written_sp=None
    (B2) + has_actuated; attempted=False (Abbruch) stempelt nichts."""
    coord = await _coord(hass)
    coord._last_written_mode = None
    coord._last_commanded_hvac = None
    coord._last_target = None
    coord._last_written_sp = 20.0
    coord._has_actuated = False

    coord.commit_execution(
        ExecutionReport(
            executions=(
                _exec("safe_mode", commanded_mode="heat"),
                _exec("safe_setpoint", commanded_value=7.0),
            )
        )
    )
    assert coord._last_written_mode == "heat"
    assert coord._last_commanded_hvac == "heat"
    assert coord._last_target == 7.0
    assert coord._last_written_sp is None  # B2
    assert coord._has_actuated is True

    # Abbruch-Transport (Mode-Wurf): nichts stempeln.
    coord._last_target = None
    coord._has_actuated = False
    coord.commit_execution(
        ExecutionReport(
            executions=(
                _exec("safe_mode", success=False, commanded_mode="off"),
                _exec(
                    "safe_setpoint",
                    attempted=False,
                    success=False,
                    commanded_value=7.0,
                ),
            )
        )
    )
    assert coord._last_written_mode == "heat"  # unveraendert
    assert coord._last_target is None
    assert coord._has_actuated is False


async def test_commit_folds_strictly_in_report_order(hass: HomeAssistant) -> None:
    """Befund 9: kein Gruppen-Aggregat — zwei Effekte auf derselben Baseline
    falten in Report-Reihenfolge (letzter gewinnt), Context-IDs registrieren
    in Call-Reihenfolge."""
    coord = await _coord(hass)
    ctx_before = len(coord._own_write_ctx_ids)

    coord.commit_execution(
        ExecutionReport(
            executions=(
                _exec(
                    "setpoint_write",
                    context_id="ctx-1",
                    pre_write_value=20.0,
                    commanded_value=21.5,
                    commanded_mode="heat",
                ),
                _exec("rescue_write", commanded_value=7.0),
            )
        ),
        now=3000.0,
    )
    assert coord._last_written_sp is None  # rescue_write (B2) faltete ZULETZT

    coord.commit_execution(
        ExecutionReport(
            executions=(
                _exec("rescue_write", commanded_value=7.0),
                _exec(
                    "setpoint_write",
                    context_id="ctx-2",
                    pre_write_value=20.0,
                    commanded_value=19.0,
                    commanded_mode="heat",
                ),
            )
        ),
        now=3060.0,
    )
    assert coord._last_written_sp == 19.0  # jetzt gewann der Setpoint-Write
    assert list(coord._own_write_ctx_ids)[ctx_before:] == ["ctx-1", "ctx-2"]


async def test_commit_end_hold_teardown_without_bus_fire(
    hass: HomeAssistant,
) -> None:
    """EndHold('frost_rescue', require_success=False): State-Teardown + dirty
    im Commit, das Event NUR als CommitResult-Payload — der Bus bleibt still,
    bis der Adapter feuert (Phase-0 frost_rescue_matrix/event_order-Semantik);
    ``_end_hold`` selbst feuert fuer die anderen Sites unveraendert sofort."""
    coord = await _coord(hass)
    fired = async_capture_events(hass, "poise_override_ended")

    coord._override = 22.0
    coord._mode_override = "off"
    coord._override_set_wall = 1.0
    coord._override_expires_at = 2.0
    coord._override_requested = 22.0
    coord._override_reason = "user"
    coord._override_expiry_is_switchpoint = True
    coord._dirty = False

    result = coord.commit_execution(
        ExecutionReport(executions=()),
        post_actions=(EndHold("frost_rescue"),),
    )
    await hass.async_block_till_done()

    assert result.events == (OverrideEnded("frost_rescue"),)
    assert fired == [], "the commit must NOT fire the bus event itself"
    assert coord._override is None
    assert coord._mode_override is None  # K2
    assert coord._override_set_wall is None
    assert coord._override_expires_at is None
    assert coord._override_requested is None
    assert coord._override_reason is None  # K3
    assert coord._override_expiry_is_switchpoint is False
    assert coord._dirty is True

    # Die anderen vier Sites nutzen weiter _end_hold: Teardown + SOFORTIGES
    # Feuern mit heutigem Payload (zone/entry_id/reason/entity_id).
    coord._end_hold("user_resume")
    await hass.async_block_till_done()
    assert len(fired) == 1
    payload = fired[0].data
    assert payload["reason"] == "user_resume"
    assert payload["zone"] == coord.zone_name
    assert payload["entry_id"] == coord._entry_id


@dataclass(frozen=True, slots=True)
class _UnknownAction(PostExecutionAction):
    reason: str


async def test_commit_rejects_unknown_inputs(hass: HomeAssistant) -> None:
    """Programmierfehler schlagen LAUT fehl: unbekannte Effekt-IDs und
    Post-Actions, ts-Stempel ohne now, require_success=True (Semantik erst
    spaeter definiert)."""
    coord = await _coord(hass)

    with pytest.raises(ValueError, match="unknown effect_id"):
        coord.commit_execution(
            ExecutionReport(executions=(_exec("bogus_effect"),)), now=1.0
        )
    # Alle vier ts-stempelnden Erfolge verlangen now= (mode_nudge nur beim
    # echten Wechsel — M2; der Rescue-Nudge immer).
    for needs_now in (
        _exec("mode_nudge", commanded_mode="heat", mode_changed=True),
        _exec(
            "setpoint_write",
            pre_write_value=20.0,
            commanded_value=21.5,
            commanded_mode="heat",
        ),
        _exec("ext_feed", commanded_value=1.0),
        _exec("rescue_nudge", commanded_mode="heat"),
    ):
        with pytest.raises(ValueError, match="needs now="):
            coord.commit_execution(ExecutionReport(executions=(needs_now,)))
    with pytest.raises(ValueError, match="unknown post action"):
        coord.commit_execution(
            ExecutionReport(executions=()),
            post_actions=(_UnknownAction("x"),),
        )
    with pytest.raises(NotImplementedError):
        coord.commit_execution(
            ExecutionReport(executions=()),
            post_actions=(EndHold("frost_rescue", require_success=True),),
        )
