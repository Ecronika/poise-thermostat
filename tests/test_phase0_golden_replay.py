"""Phase 0, Testebene A: exakte Golden-Replay-Tests (pure, KEIN HA-Import).

Plan-Referenz: docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md,
Abschnitt "Phase 0 - Verhalten einfrieren":

- Testebene A "Exakte Golden-Tests (pure)": festes Szenario + Fixed Clock
  (ManualClock in tests/harness/replay.simulate) -> exakt reproduzierbare
  Trace-Folge.
- Checklistenpunkt "Golden Traces sichern (ADR-0011) + Referenz-Traces
  einchecken (tests/golden/); Normalisierungs-Helfer fuer Ebene B".

Eingefroren wird hier die *pure* Referenz-Pipeline (pipeline.run_tick ->
controller.BangBangController -> arbitration.resolve gegen die RCPlant),
byte-identisch gegen tests/golden/scenario_baseline.jsonl. Der volle
Koordinator-Tick (coordinator.py `_run_once` Z. 1988-3827) ist per Plan NICHT
byte-identisch einfrierbar (monotone Zeit, Wall-Clock, `tick_ms`,
Forecast-Timing) und wird stattdessen von Ebene B (semantischer
Trace-Vergleich; Vorarbeit: normalize_semantic in tests/harness/golden.py)
und Ebene C (Integrationstests) abgedeckt.

Fixture-Regeneration (NUR wenn eine Verhaltensaenderung bewusst gewollt ist,
z. B. ein dokumentierter Phase-10-BEHAVIOR-FIX; aus der Projektwurzel, Bash):

    ".venv-ha/Scripts/python.exe" -c "import pathlib; \
from tests.harness.golden import run_reference_scenario, serialize_trace; \
pathlib.Path('tests/golden/scenario_baseline.jsonl').write_bytes(\
serialize_trace(run_reference_scenario()).encode('utf-8'))"

Der Binaer-Write haelt die \n-Zeilenenden auch unter Windows byte-stabil;
die Fixture darf deshalb nie durch einen Editor mit CRLF-Konvertierung
laufen.

Ausfuehren (pure, ohne asyncio_mode-Option). Achtung: in der lokalen
.venv-ha injizieren die HA-Testplugins (pytest-homeassistant-custom-component
+ pytest-socket) eine autouse event_loop-Fixture, deren socketpair-Fallback
unter Windows von pytest-socket blockiert wird — das trifft ALLE puren Tests
(z. B. auch tests/test_harness.py), nicht nur dieses Modul. Lokal deshalb
beide Plugins abschalten; im CI-Pure-Job (requirements-dev, ohne HA) sind sie
gar nicht installiert:

    ".venv-ha/Scripts/python.exe" -m pytest tests/test_phase0_golden_replay.py \
-q -p no:cacheprovider -p no:homeassistant -p no:socket
"""

from __future__ import annotations

from pathlib import Path

from tests.harness.golden import (
    normalize_semantic,
    parse_jsonl,
    reference_scenario,
    run_reference_scenario,
    serialize_trace,
    trace_to_records,
)

_GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "scenario_baseline.jsonl"


def test_replay_is_byte_identical_to_golden_fixture() -> None:
    """Frischer Lauf der puren Pipeline == eingecheckte Fixture, Byte fuer Byte.

    Pure Pipeline + ManualClock + gepinnte Parameter => voll deterministisch;
    jede Abweichung ist eine echte Verhaltensaenderung der Referenz-Pipeline
    (oder eine kaputte Fixture, z. B. durch CRLF-Konvertierung).
    """
    fresh = serialize_trace(run_reference_scenario()).encode("utf-8")
    golden = _GOLDEN_PATH.read_bytes()
    assert golden == fresh, (
        "Golden-Trace weicht ab - Verhaltensaenderung der puren Pipeline "
        "oder veraenderte Fixture (Regeneration nur bewusst, siehe "
        "Modul-Docstring)."
    )
    # Sanity: ein Record pro Simulationsschritt.
    assert len(golden.splitlines()) == reference_scenario().steps


def test_normalize_semantic_agrees_between_fixture_and_fresh_run() -> None:
    """Selbsttest des Ebene-B-Normalisierers gegen beide Seiten.

    normalize_semantic(Fixture) == normalize_semantic(frischer Lauf), das
    Zeitfeld ``t`` ist entfernt, die Semantikfelder bleiben erhalten.
    """
    fixture_records = parse_jsonl(_GOLDEN_PATH.read_text(encoding="utf-8"))
    fresh_records = trace_to_records(run_reference_scenario())
    norm_fixture = normalize_semantic(fixture_records)
    norm_fresh = normalize_semantic(fresh_records)
    assert norm_fixture == norm_fresh
    assert norm_fixture, "Fixture darf nicht leer sein"
    for record in norm_fixture:
        assert "t" not in record  # Zeitfeld normalisiert weg
        assert "air" in record and "setpoint" in record  # Semantik bleibt


def test_normalize_semantic_strips_runtime_fields_only() -> None:
    """Normalisierer entfernt genau die Zeit-/Laufzeitfelder aus dem Plan.

    Ebene B (Plan): ``mono_ts``, Wall-Timestamps, ``tick_ms*``,
    ``tick_over_budget`` werden normalisiert; Semantikfelder (mode, target,
    heat_sp, ...) bleiben unangetastet.
    """
    raw: list[dict[str, object]] = [
        {
            "t": 60.0,
            "mono": 60.0,
            "mono_ts": 12345.6,
            "ts": "2026-07-18T12:00:00+00:00",
            "wall_ts": 1789000000.0,
            "tick_ms": 12,
            "tick_ms_budget": 500,
            "tick_over_budget": False,
            "mode": "heat",
            "target": 21.0,
            "heat_sp": 21.0,
            "tpi_duty": None,
        }
    ]
    (normalized,) = normalize_semantic(raw)
    assert normalized == {
        "mode": "heat",
        "target": 21.0,
        "heat_sp": 21.0,
        "tpi_duty": None,
    }


def test_reference_simulation_is_deterministic_in_process() -> None:
    """Zwei Laeufe im selben Prozess sind identisch (Traces UND Bytes)."""
    first = run_reference_scenario()
    second = run_reference_scenario()
    assert first == second
    assert serialize_trace(first) == serialize_trace(second)
