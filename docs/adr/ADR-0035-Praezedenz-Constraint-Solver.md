# ADR-0035: Präzedenz-expliziter Constraint-Solver (ADR-0013 Stufe 1)

**Status:** Implementiert · **Datum:** 2026-06-21 · **Bezug:** ADR-0013 (Arbitrierung/Choke-Point), ADR-0023 (Dual-Setpoint), ADR-0027 (Norm-Envelope), Charta-Präzedenz (K4/K7) · **Verifizierung:** `tests/test_constraints.py` + unveränderte `test_arbitration`/`test_norm_compliance`/`test_tick_resolve` (Verhaltenserhalt)

## Kontext
Die Sollwert-Begrenzung lag an **drei** Stellen mit je *impliziter* Reihenfolge: `arbitration.resolve` (Korridor + device_max, Harness-Pfad), `resolve_write_target` (Norm-Envelope + `min(device_max)`, Live-Pfad) und `clamp_to_norm` (ASR-Cap + Frost/Schimmel-Floor). Die Charta-`Precedence` (SAFETY<HEALTH<COMFORT<EFFICIENCY…) existierte, war aber nirgends als Auflösungsregel kodiert. Bei Konflikten (z. B. Schimmel-Floor über Geräte-Max) entschied die zufällige Code-Reihenfolge, nicht die Präzedenz.

## Entscheidung
Ein **pures, HA-freies** Modul `constraints.py` als Single Source of Truth:
- `Constraint(value, cause, kind∈{FLOOR,CAP}, precedence)`; Floors komponieren zum **Maximum**, Caps zum **Minimum**.
- Bei **Inversion** (bindender Floor über bindendem Cap) gewinnt die **höhere Präzedenz** (Gleichstand → Floor, health-first). So schlägt das physische Geräte-Max (SAFETY) den Schimmel-Floor (HEALTH), und der Health-Floor schlägt den Komfort-Cap.
- `resolve_constraints(desired, constraints) → Resolution(value, binding, floor, cap)` meldet, **welche** Schranke band und mit welcher Präzedenz.
- `clamp_to_norm`, `arbitration.resolve` und `resolve_write_target` **delegieren** daran — verhaltenserhaltend (alle Alttests grün). Der Live-Pfad führt Norm-Floor (HEALTH), Norm-Cap (COMFORT) und Geräte-Max (SAFETY) jetzt durch **einen** Solver.
- Neu exponiert: `binding_precedence` (Climate-Attribut) — die Präzedenzklasse der bindenden Schranke.

## Begründung
Eine einzige, getestete Constraint-Komposition statt drei impliziter Pfade; Konflikte lösen sich physikalisch korrekt (man kann keinen Sollwert über dem Geräte-Max kommandieren). Der Nebeneffekt: genauere `norm_binding`-Diagnose (meldet jetzt `device_max`, wenn dieses statt der Norm bindet — der **Zielwert** war schon immer identisch).

## Konsequenzen
**Positiv:** ADR-0013-Choke-Point auf den vollen, präzedenz-expliziten Solver gehoben; Constraints sind erweiterbar (neue Schranken = neue `Constraint`-Einträge, keine if-Kaskaden); 100 % Cov auf allen vier Modulen. **Negativ/Offen:** (a) Korridor-Bounds in `arbitration.resolve` erhalten generische Präzedenz (FLOOR=HEALTH/CAP=COMFORT) statt cause-spezifischer — für den Zielwert irrelevant, nur bei seltenen Inversionen vereinfachend. (b) **Mehrzonen-/Ressourcen-Koordination** (Lastabwurf, gemeinsame Wärmequelle, Kompressor-Guard) aus ADR-0013 ist **bewusst aufgeschoben** — für die Einzelzonen-Installation noch nicht nutzbar; eigener ADR, wenn relevant.
