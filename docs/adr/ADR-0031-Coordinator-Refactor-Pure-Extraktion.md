# ADR-0031: `_run_once`-Refactor — pure Extraktion statt UseCase-Klassen

**Status:** akzeptiert · **Datum:** 2026-06-20 · **Bezug:** ADR-0005/0011 (pure-Core/dünne-Glue), externe Review #3, Charta G25/G27 · **Verifizierung:** Test-Gate, Verhaltens-Identität (Diagnostik-Dict unverändert)

## Kontext
`_run_once` war auf **335 Zeilen** gewachsen und enthielt ungetestete **Entscheidungs**-Logik (Quellenauswahl der Schatten-Schätzer, finale Sollwert-/Modus-/Norm-Auflösung) — genau die Glue, die zuletzt von der OneDrive-Trunkierung getroffen wurde. Die externe Review schlug „UseCase-Klassen" (`SensorReadUseCase` …) vor.

## Entscheidung
Refactor **im Projektstil**: die Entscheidungslogik in **pure, getestete Funktionen** ziehen (wie schon `plan_preheat`), **keine** schwergewichtigen UseCase-Klassen — die widersprächen der bewussten „pure-Core + dünne HA-Glue"-Architektur (ADR-0005/0011).
1. **Pure `control/tick_resolve.py`** (100 % Coverage): `select_t_rm` / `select_q_solar` / `select_mrt` (Schatten-Quellenauswahl, Vorrang Sensor→intern→Fallback) + `resolve_write_target` (Fenster/Override/Komfort → Ziel+Modus, dann Norm-Clamp/ASR-Deckel + device_max; `WriteTarget`-Dataclass).
2. **Glue-Methode `_emit_health_issues()`** bündelt die ~55 Zeilen Repair-Issue-Checks (Aktor/Frozen/Geräte-Guards/Batterie/Heizquelle) und liefert die Status-Flags zurück.
3. `_run_once` ruft nur noch: **335 → 266 Zeilen**; die Diagnostik-Dict-Assemblierung (≈58 Z.) bleibt bewusst inline (reine Abbildung lokaler Werte, keine Logik).

## Begründung
Die zuvor ungetestete, verzweigte Kern-Entscheidungslogik ist jetzt unit-getestet (jeder Branch), ohne HA-Runtime. Verhalten unverändert (Diagnostik-Dict byte-identisch; manuell gegen Dangling-Refs geprüft, da Coordinator von mypy-`ignore_errors`/Tests nicht auf Namensfehler abgedeckt ist). Leichtgewichtig statt OOP-Schwergewicht hält den Kern testbar und zukunftssicher für weitere Schätzer.

## Konsequenzen
**Positiv:** kritische Tick-Logik testbar + kürzeres `_run_once`; kleinere Glue-Fläche (geringere Trunkierungsgefahr); `clamp_to_norm`/Solar-Imports aus dem Coordinator entfernt. **Negativ/Offen:** Diagnostik-Dict bleibt groß (bewusst — Plumbing); weitere Extraktionen (Operativ-Modus-Entscheidung, Forecast-Vorbereitung) möglich, aber abnehmender Grenznutzen. Gate v0.21.0: 211 Tests, cov 98,1 %, mypy 47 Dateien.
