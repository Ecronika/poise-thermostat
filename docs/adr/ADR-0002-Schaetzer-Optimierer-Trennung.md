# ADR-0002: Ein Schätzer (EKF) speist einen reinen Optimierer

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-18 · **Bezug:** K2, E1 · **Verifizierung:** V1

## Kontext
Beim Zusammenführen bringen RoomMind (6-State-EKF) **und** Better Thermostat (eigenes RC-Modell + skalarer Kalman) je ein eigenes Wärmemodell mit. Zwei Filter, die dieselbe Zeitkonstante τ/denselben Verlust schätzen, würden divergieren — die in der Konflikt-Analyse als **K2** beschriebene Kernkonfliktklasse („welches Modell besitzt die Wahrheit?").

## Entscheidungstreiber
Eine einzige Wahrheitsquelle für den thermischen Zustand (G3/G27), Testbarkeit, Vermeidung divergierender τ/β, klare Modulgrenze (E1/E2).

## Betrachtete Optionen
1. **Ein Zustandsschätzer (mode-gated EKF) als alleinige Quelle; Optimierer ist read-only.**
2. Zwei Modelle parallel (EKF zum Lernen, MPC-eigenes Modell zum Planen) mit Abgleich — wie es eine naive BT+RoomMind-Verschmelzung ergäbe.
3. MPC besitzt das Modell, EKF nur als Korrektur — Modell-Eigentum bei der Regelung.

## Entscheidung
**Option 1.** Genau **ein** Schätzer (`estimation/thermal_ekf`, mode-gated) ist die alleinige Quelle des Gebäudezustands. Er exponiert ein **eingefrorenes Wertobjekt** `RCModel` über `get_model() → RCModel`. Der Optimierer (ADR-0001) ist **rein/read-only** und sagt ausschließlich über das **zustandslose, seiteneffektfreie** `RCModel.predict()` voraus. `seasonless_rate` dient nur als **Prior/Cold-Start**, nie als parallel regelndes Modell.

## Begründung
V1 hat am RoomMind-Code belegt, dass genau dieses Muster **bereits Realität** ist: `MPCOptimizer(model: RCModel)` erhält das Modell als Parameter, greift nie auf EKF-Interna (`_x`, `_P`, Jacobian) zu; `ThermalEKF.get_model()` projiziert den Zustand in ein eingefrorenes `RCModel`; `predict()` mutiert nichts. Damit ist Option 1 ohne Refactoring adaptierbar, während Option 2 die K2-Divergenz erst herstellt und Option 3 die Trennung von Lernen und Planen aufweicht (G6-Risiko: Planungslast verfälscht Lernen).

## Konsequenzen
**Positiv:** nur **ein** Modell zu verifizieren, zu persistieren und zu migrieren; saubere, testbare Naht `Estimator.get_model()` + `predict()`; Lernen (mutierend) und Planen (read-only) strukturell getrennt.
**Negativ/Kosten:** Der Datenvertrag `RCModel` muss formal definiert werden (→ **E1**). RoomMinds Identifizierbarkeits-Normalisierung **`C=1`** bedeutet: nur Verhältnisse α=U/C und β=Q/C sind bestimmbar. Wollen wir physikalische C/U **getrennt** führen (z. B. für absolute Energiebilanzen im Einsparungs-Report), muss die Projektionsfunktion erweitert werden — der Optimierer bleibt davon unberührt.

## Verifizierung
V1: `mpc_optimizer.py` (Feld `model: RCModel`), `mpc_controller.py:_evaluate_mpc` (Parameter-Injektion `MPCOptimizer(model=model, …)`, `model = ModelManager.get_model()`), `thermal_model.py:get_model()` (Projektion), `RCModel.predict()` (zustandslos). Tests: Property-Test „predict() ist seiteneffektfrei"; Regressionstest „Idle-Daten verändern Heizparameter nicht" (G6).

## Compliance
Schnittstellenmuster eigenständig nachimplementiert; kein Code-Copy. `RCModel`/`predict()` generisch.

## Verknüpfungen
Fundament für ADR-0001 und ADR-0003. Erzeugt Folge-Entscheidung **E1** (RCModel- und übrige Datenverträge formalisieren). Berührt E17 (EKF-Tuning).
