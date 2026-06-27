# ADR-0020: Performance-Budget & Skalierung

**Status:** In Arbeit (60 %) · **Datum:** 2026-06-18 · **Bezug:** E28 · **Verifizierung:** Code-Review RoomMind/BT/ThermoSmart/Vesta/Versatile (Thema M)

## Kontext
Der MPC-Pfad (ADR-0001) ist die teuerste Komponente und läuft je Zone. Offen: Tick-Budget, Caching, Skalierungsstrategie.

## Entscheidungstreiber
Reaktionsschnell ohne CPU-Last; lineare Skalierung mit Zonenzahl; keine doppelte Berechnung teurer Größen; HA-Event-Loop nicht blockieren.

## Befund am Code (Belege)
- **Intervalle:** RoomMind **30 s** (`UPDATE_INTERVAL=30`, aggressiv), ThermoSmart/Versatile **300 s**, Vesta **60 s/Entity**, **BT eventgetrieben** (`local_push`).
- **MPC-Kosten:** RoomMind rechnet MPC **pro Raum jeden Tick** (greedy Vorwärtssim, Horizont 24 Blöcke × Aktionen × Lookahead ≈ ~430 `predict()`-Calls/Raum/Tick, **linear**, **kein** Zyklus-Gate auf dem Optimizer). BT-Grid-Search coarse→fine ≈ ~22–24 Evals, Horizont 6×5 min, aber nur eventgetrieben.
- **Caching:** RoomMind cacht den **Solar-GHI-Skalar einmal pro Zyklus global** („compute solar once per cycle") — **aber** die per-Raum-Solar-*Serie* wird je Raum/Tick neu gerechnet (kein Caching). I/O zyklus-gedrosselt (`HISTORY_WRITE_CYCLES=6`, `THERMAL_SAVE_CYCLES=30`, `VALVE_PROTECTION_CHECK_CYCLES=120`), `EKF_UPDATE_MIN_DT=3 min`. Executor für teure Recorder-Reads.
- **Skalierung:** **kein** hartes Zonen-Limit in irgendeinem Repo; Kosten überall implizit linear.

## Entscheidung
1. **Grundintervall 60 s** (Vesta-Niveau; RoomMinds 30 s ist unnötig aggressiv) **plus eventgetriebene Sofort-Reaktion** (`local_push` wie BT) für Sensor-/Override-/Fenster-Events — kombiniert mit dem atomaren Tick + Coalescing aus ADR-0006.
2. **Teure globale Größen einmal pro Tick cachen** und an alle Zonen weiterreichen — RoomMinds „Solar once per cycle"-Muster, **erweitert auf die Solar-/Forecast-*Serie*** (die RoomMind noch je Raum neu rechnet). Wetter-Forecast einmal pro Tick ziehen, nicht je Zone.
3. **Greedy/linearer Solver** (ADR-0001), kein exponentieller Suchraum; BT-coarse→fine als adaptive Auflösung. MPC nur scharf bei konfidentem Modell (ADR-0009-Gate), darunter billiges Bang-Bang.
4. **I/O-/Persistenz-Zyklenzähler** (RoomMind-Muster) + Re-Entrancy-Guard (ADR-0006); **blockierende I/O strikt in Executor**.
5. **Performance-Budget dokumentieren und testen:** Ziel-Rechenzeit pro Tick und Referenz-Zonenzahl (z. B. ≤ X ms für N Zonen) als nicht-flaky Benchmark im Harness (ADR-0011); bei Überschreitung Zonen-Staffelung (nicht alle Zonen im selben Tick voll rechnen) statt hartem Limit.

## Begründung
Eventgetrieben + moderates Grundintervall liefert Reaktionsschnelligkeit ohne RoomMinds 30-s-Dauerlast; konsequentes Caching teurer Serien behebt die einzige belegte RoomMind-Ineffizienz; greedy-Solver + Konfidenz-Gate halten die Per-Zone-Kosten klein. Ein dokumentiertes Budget macht Skalierung messbar statt implizit.

## Konsequenzen
**Positiv:** schnelle Reaktion bei niedriger Dauerlast; lineare, messbare Skalierung; kein Event-Loop-Blocking.
**Negativ/Kosten:** Caching der Serien + Zonen-Staffelung erhöhen die Implementierungskomplexität; das Budget muss als Benchmark gepflegt werden.

## Compliance
Allgemeine Performance-Muster; eigenständig umgesetzt.

## Verknüpfungen
Setzt ADR-0006 (Tick/Events) und ADR-0001/0009 (Solver/Gate) voraus. Budget-Benchmark gehört zu ADR-0011. Caching berührt ADR-0010 (Solar-Serie).
