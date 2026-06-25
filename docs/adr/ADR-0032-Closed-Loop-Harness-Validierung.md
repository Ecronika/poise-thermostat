# ADR-0032: Closed-Loop-Validierung des prädiktiven Kerns im Harness

**Status:** akzeptiert · **Datum:** 2026-06-20 · **Bezug:** ADR-0011 („Harness vor Hardware"), ADR-0001 (MPC), ADR-0002/0024 (EKF), ADR-0009 (Gate), ADR-0025 (Optimal-Start) · **Verifizierung:** `tests/harness/closed_loop.py` + `tests/test_closed_loop.py`

## Kontext
MPC, Gate-Überblendung und Optimal-Start waren in Einzelteilen unit-getestet, aber **nie als geschlossener Lern→Identifizieren→Vorhersagen→Regeln-Kreis** gelaufen. Im realen System schaltet sich das erst in der kalten Saison scharf (EKF braucht echte Heizzyklen) — ein Live-Test im Sommer ist unmöglich. Größtes latentes Projektrisiko.

## Entscheidung
Den prädiktiven Kern als **Closed-Loop gegen die bekannte RC-Plant** (`tests/harness/plant.py`, Wahrheit: τ≈6,67 h, β_h=3,0) validieren — die Plant *simuliert* die Saison.
1. `run_identification`: Heiz-Square-Wave regt beide Modi an; jeder Tick speist den **Produktions-EKF** (`predict`/`update`).
2. `run_mpc_optimizer`: nach Identifikation regelt der **Produktions-`optimize_power`** die Plant.
3. `ekf_to_state` + `MpcController.evaluate`: voller gegateter Pfad (Konfidenz-Blend).

## Befund (gemessen, nicht behauptet)
- **EKF lernt die Plant exakt:** identified bei Schritt 179, `tau_hours=6.67` (Wahrheit 6,67), `beta_h=2.98` (Wahrheit 3,0), `temperature_std=0.127`, Konfidenz 0,91.
- **MPC konvergiert ohne Pendeln:** Endwert 20,96 °C, Letztes-Drittel-Mittel 21,00, Range 0,088, **kein Überschwingen** (max 21,05 < Band 24).
- **Optimal-Start plausibel:** Vorlauf 19→21 °C @8 °C = 102 min; `start_now` korrekt bei Deadline 30 min, wartet bei 600 min.
- **Gate korrekt:** kalt(18 °C)→power 1,0/heat/„w=1.00", warm(25 °C)→power 0/idle — keine Klippe, MPC bei Identifikation voll gewichtet.
- **Nebeneffekt:** `mpc.py`/`gate.py`/`mpc_controller.py` jetzt 100 % Coverage.

## Konsequenzen
**Positiv:** der Winter-Pfad ist *jetzt* validiert — M4-Scharfschalten wird risikoarm; Regressionsschutz für MPC/Gate/Optimal-Start. **Negativ/Offen:** (a) Plant ist rauschfrei & parametertreu zum EKF-Default — reale Räume weichen ab; der Harness prüft *Korrektheit der Regelkette*, nicht reale Parametergüte. (b) Optimal-**Stop** (ADR-0003) ist hier **nicht** im Kreis geprüft. (c) MPC bleibt im Coordinator **bewusst ungewerdrahtet** bis zum Live-Winter-Test — der Harness ist die Vorstufe, nicht der Ersatz.
