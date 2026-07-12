# ADR-0011: Simulations-Harness & Test-Pyramide

**Status:** Implementiert · **Wirkung:** Harness · **Datum:** 2026-06-18 · **Bezug:** E22, E23 · **Verifizierung:** Code-Review RoomMind `analytics_simulator.py`/`tests/`, BT `tests/test_mpc.py`, Versatile `tests/` (Thema G)

## Kontext
Physik und MPC sind ohne Hardware nur über Simulation verifizierbar (G1/G25). Offen: Aufbau des Test-/Simulationsfundaments.

## Entscheidungstreiber
Verifizierbarkeit der Regelung ohne Hardware; Schutz gegen die K-Bugklassen (Regression); schnelle, deterministische Tests; keine „Attrappen-Tests".

## Befund am Code (Belege)
- **RoomMind `analytics_simulator.py` = Forward-Replay-Harness, der denselben `MPCOptimizer` und dasselbe `RCModel` wie die Produktion nutzt** (`from .mpc_optimizer import MPCOptimizer`, `from .thermal_model import RCModel, ThermalEKF`; Strategien `_simulate_mpc`/`_simulate_bangbang`/`_simulate_window_open`). **Schlüsselprinzip:** Test-Sim und realer Regler teilen den Codepfad.
- **RoomMind `tests/control/test_thermal_model.py` (~2076 Z.):** speist synthetische Reihen aus **bekanntem Wahr-RC-Modell** ein und prüft Konvergenz gegen Ground Truth (`test_ekf_learns_alpha_from_idle` → `abs(α−2.0)<1.5`); Invarianten: `test_ekf_psd_preserved`, `test_ekf_parameter_bounds`, `test_ekf_anomaly_soft_reject`, `test_ekf_prediction_std_decreases`, `serialization_roundtrip`. `conftest.py` mit leichtgewichtigem MagicMock-hass (schnell, deterministisch).
- **Versatile `tests/`:** vollwertige HA-Integrationstests — `pytest_homeassistant_custom_component`, `enable_custom_integrations`, `pytest_socket`-Netzsperre, reiche Mock-Entities (MockClimate/Number/Switch/Sensor). jmcollin78s Testruf bestätigt.
- **BT `tests/test_mpc.py`:** deterministische Unit-Tests gegen `compute_mpc(...)` + **inline-Plant-Modell** (`test_heating_sequence_simulation`: `current += gain·(valve/100)·step; current −= loss·step`, `assert abs(final_error)<1.1`).

## Entscheidung
**Fünfteiliges Testfundament:**
1. **Physik-Unit-Tests gegen Referenz** (RoomMind-Muster): bekanntes Wahr-RC-Modell als Generator, EKF/Modell muss Parameter mit Toleranz zurücklernen; reine MagicMock-hass — schnell. Zusätzlich Norm-Rechenbeispiele (EN 16798 / DIN 4108-2) als Fixtures (G1/E24).
2. **Property-/Invarianten-Tests** (RoomMind+BT): PSD/Symmetrie über alle Schritte, Parameter-Bounds, Monotonie (mehr Strafe → weniger Stellgröße; `prediction_std` sinkt mit Daten), Outlier-Robustheit, **„Untergrenze nie verletzt"**, **„Solar nicht doppelt verbucht"** (ADR-0010).
3. **Replay-/Forward-Sim-Harness, der denselben Optimierer/dasselbe Modell wie die Produktion teilt** (RoomMind `analytics_simulator` als Vorbild): gespeicherte reale Trajektorien einspielen, Stellausgabe gegen Golden-Output prüfen → Regressionsbasis für die K-Bugklassen.
4. **HA-Integrationstests** (Versatile-Muster): `pytest-homeassistant-custom-component` + Mock-Entities + Socket-Sperre für End-to-End (Config-Flow, Restore, Override).
5. **CI-Gates:** Coverage-Schwelle, Pflicht-Property-Tests, Golden-File-Regression, Plant-Sim-Stabilitätswächter (Overshoot/Settling, nicht-flaky), zusätzlich ruff/black/mypy-strict (ADR-Folge zu Coding-Standards).

**Leitprinzip (RoomMind):** Test-Sim und realer Regler **müssen denselben Codepfad teilen** — sonst testet man eine Attrappe.

## Begründung
RoomMind liefert das einzige Vorbild eines produktionsidentischen Simulators **und** echter Physik-/Invariantentests; Versatile das Vorbild für HA-Integrationstests; BT die kompakte Plant-Sim-Idee. Zusammengesetzt decken sie alle Pyramidenebenen ab und machen genau die Konflikt-/Bugklassen (K1–K17) regressionsfest.

## Konsequenzen
**Positiv:** Regelung ohne Hardware verifizierbar; Bugklassen regressionsgesichert; schnelle deterministische Kern-Tests; Vertrauen in Refactorings.
**Negativ/Kosten:** Aufbau des Harness + Golden-Files ist erheblicher Initialaufwand; Golden-Files müssen bei bewussten Verhaltensänderungen gepflegt werden; Integrationstests sind langsamer (separater CI-Job).

## Compliance
Testmuster allgemeingültig; eigenständig umgesetzt. Keine realen Nutzerdaten in Fixtures (synthetische/anonymisierte Trajektorien).

## Verknüpfungen
Verifiziert ADR-0001 (Solver), ADR-0002 (EKF-Trennung), ADR-0009 (Überblendung), ADR-0010 (Solar-Invariante). Setzt ADR-0005 (testbare Schichten) und ADR-0006 (injizierbare Uhr) voraus.

## Nachtrag (2026-07-04, v0.146.0): Feld-Trace-Recorder + Real-Trajektorien-Replay

Punkt 3 (»gespeicherte reale Trajektorien einspielen, gegen Golden-Output prüfen«) war bisher nur gegen die synthetische `RCPlant` umgesetzt (`tests/harness/replay.py` = Forward-Sim, `closed_loop.py`). Ergänzt um die **Echte-Trajektorien-Seite**:

- **Pure `custom_components/poise/trace/schema.py`** — `TraceRecord` (versioniert, `TRACE_VERSION`) + `build_record`: eine Tick-Aufnahme in **replay-suffizienter** Form — EKF-Drive (`room/t_out/u_h/u_c/q_solar/q_occ`) + `mono` als dt-Quelle + Modell-Snapshot (alpha/betas/t_std/n_*/identified) + Entscheidungskontext — als eine kompakte JSONL-Zeile je Tick; `from_dict` ignoriert unbekannte Keys (vorwärtskompatibel).
- **Pure `tests/harness/trace_replay.py`** — `load_trace` + `replay_ekf`: ein frischer Schätzer wird deterministisch aus der Aufnahme nachgefahren (ADR-0014). **Golden-Regression** `tests/test_trace.py` (5 Tests): Replay reproduziert das aufgezeichnete Modell exakt (`replay_ekf(loaded).alpha == records[-1].alpha`), Serialisierung verlustfrei, Replay-Suffizienz (u_c wird konsumiert).
- **Glue `trace/recorder.py`** — best-effort Executor-Schreiber (blockiert den Loop nie), 2-Datei-Rotation bei 20 MB, OSError-safe. Der Coordinator ruft `_maybe_record_trace` am Tick-Ende; **opt-in, default off** (`CONF_TRACE_RECORDING`), reine Beobachtung (ADR-0026), kann die Regelung nie brechen; Datei `config/poise_traces/<entry_id>.jsonl`.

Zweck: Kandidat-Algorithmen (τ-Settle-Konfidenz, CA-Schwellen-Kalibrierung) gegen **echte** Feldbahnen scoren statt nur gegen die synthetische Plant; Kalender-Vorlauf, weil Traces über Wochen/Wetterlagen wachsen müssen (Phase-4-Abnahmebasis). Offen: committed Golden-Fixture aus echten Traces + Eval-/Scoring-Schicht (Folge-Increment).
