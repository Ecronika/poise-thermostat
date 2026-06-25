# ADR-0001: MPC-Solver — greedy variable Trajektorie + Robustheitsbausteine

**Status:** akzeptiert · **Datum:** 2026-06-18 · **Bezug:** E16, E17, K2 · **Verifizierung:** V1, V3

## Kontext
Die Regelungsebene (`control/mpc`) braucht einen Optimierer, der die Stellgröße über einen Horizont plant. Drei reale Vorbilder stehen zur Wahl, deren Code in Runde 2 gelesen wurde.

## Entscheidungstreiber
Regelqualität (Fähigkeit, Aufheiz-/Drossel-Profile zu planen), Robustheit gegen Modelldrift und Störungen (Fenster, Sonne, Sensorrauschen), Rechenbudget pro Tick/Zone (E28), Verifizierbarkeit/Determinismus (G27).

## Betrachtete Optionen
1. **RoomMind — greedy Vorwärtssimulation mit variabler Trajektorie** (`control/mpc_optimizer.py`): iteriert pro 5-min-Block über Aktionen, proportionale Leistung via Closed-Form, adaptiver Horizont.
2. **Better Thermostat — Grid-Search über eine über den Horizont KONSTANTE Ventilstellung** (`utils/calibration/mpc.py`, `_evaluate_cost`): grob 10 %/fein 1 %, 6×5 min, lineare Open-Loop-Projektion `t_k = T0 + k·(a·u + net_passive)`.
3. **Echtes Receding-Horizon-QP** (kein Vorbild im Feld): global optimal, aber Solver-Abhängigkeit + Tuning-/Rechenaufwand.

## Entscheidung
**Solver-Kern = Option 1 (RoomMind-greedy mit *variabler* u-Sequenz).** Ergänzt um drei **Robustheitsbausteine aus Better Thermostat**:
- **Skalarer Kalman-Observer** für den Startzustand `T0` (glättet TRV-Sensor-Quantisierung; BT `compute_mpc` Predict/Update, `kalman_Q=0.001`, `kalman_R=0.04`).
- **Student-t-Regimewechsel → temporärer Lernraten-Boost** (BT `_detect_regime_change`: N=10, `t_stat=|mean_err|/(std/√N)`, Schwelle 2.0 → α-Boost) als billiger Drift-/Störungsschutz.
- **Asymmetrischer Overshoot-Penalty** (BT: `(1+overshoot_pen)·e²` bei Überschwingen, Faktor ~9×) zur sauberen Kodierung der Komfort-Asymmetrie.

Option 2 (Konstant-u) wird **verworfen** für die Planung, Option 3 (QP) **zurückgestellt**.

## Begründung
BTs Konstant-Ventil über 30 min kann prinzipiell **kein** „erst hoch aufheizen, dann drosseln"-Profil planen — der Kernvorteil von MPC ginge verloren (V3 belegt: lineare Open-Loop, eine Stellgröße). RoomMinds variable Trajektorie liefert genau diese Flexibilität. Ein echtes QP (Option 3) bringt bei 30-min-Horizont und der ohnehin durch Konfidenz begrenzten Modellgüte nur marginalen Gewinn gegen erheblichen Solver-/Tuning-Aufwand — Aufwand/Nutzen rechtfertigt es derzeit nicht. BTs Stärke liegt nicht im Optimierer, sondern im **Observer + Regimeschutz**; diese isoliert übernehmbaren Bausteine erhöhen die Robustheit ohne die Konstant-u-Schwäche zu erben.

## Konsequenzen
**Positiv:** flexible Stellprofile (Vorheizen/Coasting), robuste Drift-/Störungsreaktion, sauberes `T0` trotz grober TRV-Sensoren, billiger Rechenaufwand (greedy, ~Dutzende predict()-Aufrufe).
**Negativ/Kosten:** greedy ist **nicht** global optimal (akzeptiert); Penalty-Gewichte, Horizont und Blockgröße müssen getunt werden → offen als **E17** (inkl. Konfidenz→MPC-Gate-**Überblendung** statt hartem Flip, K11). Horizont-Basiswert 6×5 min = 30 min, revidierbar via E28.

## Verifizierung
V1 bestätigt die saubere Optimierer-Schnittstelle (ADR-0002), auf der dieser Solver aufsetzt. V3 bestätigt am Code, dass BTs Optimierer konstant-u ist (Grenze) und Observer/Regimeschutz die nachahmenswerten Teile sind. Tests: Replay-Harness (E22) mit Szenarien Aufheizen/Störung/Überschwingen; Property-Test „kein Überschwingen über Toleranz bei konfidentem Modell".

## Compliance
Methoden (greedy Vorwärtssim, Skalar-Kalman, t-Test-Boost, Overshoot-Asymmetrie) werden eigenständig nachimplementiert — kein Code-Copy. Generisch, gerätunabhängig.

## Verknüpfungen
Setzt ADR-0002 (reiner Optimierer) voraus. Liefert τ-Eingang an ADR-0003 (Residual als advisory Term). Offene Folge: E17 (Tuning), E19 (Solar-Pfad als Störgröße im Modell).
