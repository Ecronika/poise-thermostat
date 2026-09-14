# Kommentar- und Dokumentations-Review — Delta-Pass (2026-08-19)

**Typ:** Folge-Review + Umsetzung (behavior-preserving) · **Umfang:** alle seit dem Voll-Review vom 2026-08-09 (Basis `7f1dd2fc`) geänderten Produktions- und Testdateien (Plan-A–F-Wellen: Options-Fixes, Finite-Boundaries B.5, Convergence-Watchdog/Cooling-Failure C.7/C.8, Reload-Architektur E.13, Instrumentierung, Property-Tests F.5) plus Muster-Sweep über den Bestand und Nachprüfung der §7-Altbefunde · **Ergebnis:** 23 Dateien geändert (+135/−117 Zeilen), ausschließlich Kommentare/Docstrings/Doku plus zwei sanktionierte Mikro-Codeänderungen und eine YAML-Reparatur (s. §4.7/§4.8).

## 1. Executive Summary

Die seit dem Voll-Review neu entstandenen Kommentare sind überwiegend exzellent: selbsttragende Warum-Sätze mit ADR-/Plan-Ankern, die kritischsten Aussagen (Kommando- vs. Adoptions-Baseline des Watchdogs, Evidenz-Frische, Echo-Bindung an den Context-Ring, die A.3-Carry-over-Semantik) haben die adversariale Verifikation vollständig bestanden. Die Schwachstellen konzentrierten sich auf zwei Muster: (1) **erfundene bzw. falsch attribuierte Mechanismen im HA-Lifecycle-Hotspot** — zwei P0-Kommentare beschrieben HA-Verhalten, das in den realen HA-Quellen (2025.10.1/2026.8.2, gegen beide verifiziert) nicht existiert, einer davon mit einem inerten, irreführenden Parameter im Code, gegen den der repo-eigene AST-Gate-Test sogar argumentiert; (2) **Inventar-Drift durch die 5 neuen Instrumentierungs-Sensoren** (README „18", quality_scale „14 von 18", „tpi_*/pi_* sind Attribute, keine Entities" — alles überholt). Als Beifang der Kommentar-Verifikation wurde ein echter Code-Bug gefunden (Trace-Key-Mismatch, §7.1). Beide Testsuiten, ruff, Format und mypy strict sind vor wie nach den Änderungen grün.

## 2. Verwendete Standards

- **HA Developer Docs — Style Guidelines** (Stand 2026-08 gegengeprüft): PEP 8/257 via Ruff; „Comments should be full sentences and end with a period"; Google-Style-Docstrings nur bei Bedarf; keine Typangaben in Docstrings.
- **HA Integration Quality Scale** (docs-*-Regeln Bronze–Gold, Stand 2026-08): unverändert gegenüber dem Voll-Review; keine Regeln zu Code-Kommentaren.
- **Projekt-Konventionen** (Voll-Review 2026-08-09 §2): Warum-Kommentare mit ADR-Anker; nackte Review-Codes ohne selbsttragenden Satz sind Schuld; keine hand-gepflegten Zählwerte; keine spekulativen Herkünfte. Die Plan-Codes A.x–F.x der jüngsten Wellen wurden als zulässige Anker eingestuft, **sofern** der Satz selbsttragend ist und der Code auf ein in-Repo-Dokument (docs/reviews/…) zurückverfolgbar ist — Massenentfernung wäre reiner Diff-Lärm (Leitlinie 10).
- **Verifikationsregel dieses Passes:** Jede faktische Behauptung eines seit `7f1dd2fc` neuen/geänderten Kommentars wurde gegen den Code geprüft; HA-Verhaltens-Behauptungen zusätzlich gegen die HA-Quellen der WSL-Umgebungen (2025.10.1 und 2026.8.2).

## 3. Ausgangszustand (Befundklassen des Deltas)

- **A (wertvoll, korrekt) — die große Mehrheit.** Verifiziert u. a.: die komplette write_convergence-Modul-Doku (Baseline-Entscheid, TTL, Toleranz-Floor, Escalation-UND), alle vier C.8f-Kommentare in zone_runtime, die comfort_activation-Regeln (gegen ADR-0069 §5 exakt), die B.5-Konsequenz-Beschreibungen in hub_aggregate, der `target_temp_step`-Wire-Key, die A.3-Carry-over-Doku samt repairs.py-Querbezug, alle fünf neuen Test-Modul-Docstrings (F.5-Fallen inklusive).
- **D/P0 (falsch, gefährliche Richtung), 3 Stellen:** `__init__.py` erfand einen Await-Teardown-Mechanismus als Begründung für `async_schedule_reload` (real: HA dispatcht Listener als detached Task; die belegbaren Gründe sind HAs eigene Guidance und der Retry-Cancel); `config_flow.py` begründete `reload_on_update=False` an zwei bare Duplicate-Abort-Aufrufen mit einer 2026.12-Regel, die dort nachweislich nicht greift (ohne `updates` kann der Aufruf weder updaten noch reloaden — der eigene Gate-Test `test_abort_if_unique_id_configured_never_reloads` dokumentiert exakt das); `trace/schema.py` behauptete Heating-Failure-Replay-Abdeckung „via frozen-era keys" — real erreicht weder das Heating-Verdikt den Trace noch wird der `frozen`-Key je befüllt (Code-Bug, §7.1).
- **C/D (Drift), ~10 Stellen:** README-Sensorinventar 18→23 und „tpi_*/pi_* nicht als Sensoren" (seit der Instrumentierung falsch); quality_scale-Zählung; der `self._c`-Vertrag im Orchestrator ohne die zwei neuen Health-Fassaden; health_reporter „four methods"; hub_coordinator beschrieb die Vor-B.5b-Konsequenz als aktuell; ein Reload-Beispiel nannte SETUP_RETRY, wo nur SETUP_ERROR die Begründung trägt; coordinator.structural_unchanged beschrieb den Vor-E.13-Reload-Fluss; „ADR-0033b" als nicht existente ADR-ID (2×); „September instrumentation" als Monatsanker.
- **B (redundant):** die E.13-Begründung 4× ausgeschrieben statt 1× + Verweis; EffectExecution-Docstring wiederholte den eigenen ersten Absatz; ein Inline-Kommentar in input_reader wiederholte die Docstring drei Zeilen darüber.
- **Sprache:** zwei deutsche Docstrings + ein deutscher Kommentar in test_trace.py (Projektsprache Englisch).
- **Werkzeug-Befund:** quality_scale.yaml war invalides YAML (Zeile 25, unquoted `:` im Scalar) — vorbestehend, von jedem strikten Parser (hassfest!) abgewiesen.

## 4. Durchgeführte Änderungen

1. **Lifecycle (`__init__.py`, `config_flow.py`, `coordinator.py`)** — beide P0-Begründungen durch die verifizierten ersetzt (Listener-Dispatch als Task; Schedule-Guidance + Retry-Cancel); E.13-Rationale auf einen kanonischen Ort (`_async_options_updated`-Docstring) konzentriert, Call-Sites auf Einzeiler + Verweis; `_schedule_reload_if_unloaded`-Beispiel auf SETUP_ERROR gedreht (SETUP_RETRY gewinnt nur Promptheit); Hub-Satz „no state worth preserving" korrigiert (die Boiler-Anker SIND der Grund für den Guard); `structural_unchanged` auf die Listener-Autorität umformuliert.
2. **ha/** — `self._c`-Vertragsliste um `_notify_cooling_failure`/`_notify_convergence` ergänzt (die Liste ist bindend: „nothing may rely on it growing"); health_reporter-Modul-Docstring ent-zählt und die Synchron-Checkpoint-Regel auf alle `notify_*` ausgedehnt; Stage-Docstring „Heating/cooling failure detectors"; Re-Arm-Semantik von „+" auf „BOTH thresholds" präzisiert; notify_convergence um TTL-Expiry und Disabled-Pfad ergänzt; Duplikat-Kommentar in input_reader entfernt.
3. **safety/ + runtime/** — Paket-Docstring um die zwei neuen Detektoren ergänzt; heating_failure-Modul-Docstring nennt das Cooling-Pendant; should_learn-Summenzeile modus-neutral; write_convergence: falsches „persisted baseline"-Szenario auf die reale In-Memory-Semantik korrigiert, Herkunftsmarker für die Schwellwerte (projekt-gewählt, keine Quelle — bewusst nichts erfunden); tick_inputs: „attribute-number rule"-Selbstwiderspruch aufgelöst (parse_finite, bewusst OHNE Availability-Gate); EffectExecution-Docstring dedupliziert; stale_own_echo-Attribution an die reale Ring-Check-Stelle.
4. **trace/schema.py + sensor.py** — „ADR-0033b" → „ADR-0033 flip criterion (b)" (2×); „September" → „Winter-gate instrumentation"; falsche frozen-Parenthese ersetzt durch ehrliche Lücken-Doku + KNOWN-GAP-Warnkommentar am `frozen`-Feld (Replay-Falle für jeden Trace-Nutzer, bis der Bug gefixt ist); Default-off-Rationale der Instrumentierungs-Sensoren dokumentiert (Statistik akkumuliert erst nach Aktivierung — load-bearing für die Evidenz-Kampagne).
5. **hub_coordinator.py + tick_pipeline.py** — B.5-Konsequenz auf den heutigen Stand (Guard in resolve_load_shedding existiert; die Boundary schützt jetzt die Diagnose), Vorher-Verhalten als Historie; Umbruch-Schutt reflowt.
6. **README + quality_scale.yaml** — Inventar 23 Sensoren inkl. neuem Bullet für das Default-off-Quintett; „Attribute, nicht Sensoren"-Absatz korrigiert (Headline-Werte jetzt gespiegelt); Robust-by-design um die zwei neuen Repair-Issues ergänzt; quality_scale-Kommentar ent-zählt („alle außer dem 4er-Set" statt „14 von 18") und den falschen tpi/pi-Satz ersetzt.
7. **Sanktionierte Mikro-Codeänderungen (verhaltensneutral, test-verifiziert):** (a) `reload_on_update=False` an den zwei bare `_abort_if_unique_id_configured()`-Aufrufen entfernt — der Parameter ist ohne `updates` nachweislich inert (HA-Quelle 2026.8.2, `should_reload` nur im updates-Zweig erreichbar) und der repo-eigene Gate-Test nennt genau diese Form „misleading"; kein Test pinnt den Parameter. Analog zu §4.9(b) des Voll-Reviews: Code entfernt, dessen dokumentierte Begründung falsch war. (b) pyproject: die unbelegbare „sandbox Python 3.10"-Provenienz aus dem Coverage-Kommentar gestrichen (CI läuft real 3.12–3.14) — Kommentar-only.
8. **YAML-Reparatur:** quality_scale.yaml Zeile 25 gequotet — die Datei ist jetzt erstmals parsebar (validiert). Semantik unverändert.
9. **Tests** — zwei deutsche Docstrings + Kommentar in test_trace.py übersetzt (dabei die mitübersetzte „wie heating"-Falschaussage entfernt); test_phase6b_state_move-Docstring auf `coord.runtime.clock`; „(50 names)"-Pin als Provenienz mit In-line-Fortschreibung ausgewiesen; ECHO_WINDOW_S=90 als bewusst produktionsfremder Injektionswert markiert.

## 5. Entfernte Kommentare

Wenig — das Delta war überwiegend additiv wertvoll: der input_reader-Duplikat-Kommentar, zwei redundante E.13-Ausschreibungen (durch Verweis ersetzt), die deduplizierte EffectExecution-Passage, zwei falsche Begründungsblöcke (durch korrekte, kürzere ersetzt). Die Plan-Codes A.x–F.x blieben stehen (selbsttragende Sätze, in-Repo-Anker).

## 6. Neu dokumentierte wichtige Zusammenhänge

- Die **echten** Gründe für Schedule-statt-Await im Reload-Pfad (HA-Guidance, Retry-Cancel, Task-Dispatch der Listener) — statt eines erfundenen Teardown-Mechanismus.
- Der reale Scope der 2026.12-Listener-vs-Reload-Regel (nur Aufrufe mit `updates`) am bare Duplicate-Abort.
- Der Trace-`frozen`-Key-Mismatch als markierte Replay-Falle (KNOWN GAP) statt einer falschen Abdeckungs-Behauptung.
- Default-off-Mechanik der Instrumentierungs-Sensoren (LTS akkumuliert erst ab Aktivierung → Opt-in-Kampagne).
- Watchdog-Re-Arm = UND beider Schwellen (nicht Summe); Issue-Clear auch durch Evidenz-TTL und Disabled-Pfad.
- SETUP_ERROR als der Fall, den `_schedule_reload_if_unloaded` wirklich rettet.

## 7. Nicht automatisch behobene Befunde

1. **BUG (P0, Code, Task-Chip angelegt):** `trace/schema.py` liest `frozen=_b("frozen")`, der Tick publiziert `"sensor_frozen"` → `TraceRecord.frozen` ist in jedem Live-Trace konstant False; das Heating-Failure-Verdikt (`"heating_failure"` im Datensatz) erreicht den Trace gar nicht (Cooling seit C.8 schon). Fix ändert Trace-Output → Golden-Replay-Prüfung + End-zu-End-Keytest nötig (test_trace.py testet nur build_record mit direkt gesetzten Keys und maskiert den Bug).
2. **Produktions-toter Code:** `heating_failure.failure_notification_action` — einzige Caller sind die eigenen Unit-Tests; der Live-Pfad läuft über HealthReporter. Entfernung = kleiner Code-Eingriff, nicht Doku.
3. **Bekannter Sensor-Bug (Task-Chip existiert, task_5c2e5623):** `override_expires_at`-Sensor liefert immer unknown (ISO-String vs. Epoch-Erwartung) — unabhängig doppelt bestätigt.
4. **Altbestand aus §7 des Voll-Reviews, unverändert offen:** ADR-0001 „~9×" vs. Code 8×; ADR-0051 „10–33,5 °C" vs. Code 10–30; ADR-0007-F13-Liste ohne `last_fan_cmd_ts`; ungenutzte Reste (PersistencePhase.NONE, manual_override_expired, running_mean.recent_days); Herkunft der Tuning-Konstanten; Gold-docs-Regeln (korrekt als todo geführt). **Erledigt aus §7 alt:** der clo_offset-Bug (A.3, mit Regressionstest).
5. **Kein Trace-Feld für das Heating-Failure-Verdikt** — Teil von Befund 1; Feld-Ergänzung wäre eine (kompatible) Schema-Erweiterung, keine Doku.

## 8. Validierung

| Gate | vorher (Baseline) | nachher |
| --- | --- | --- |
| ruff check | clean | clean |
| ruff format --check | 337 formatiert | 337 formatiert |
| mypy --strict (133 Dateien) | clean | clean |
| Pure-Suite (.venv-dev, Windows) | 1362 passed | 1362 passed |
| Glue-Suite HA-Min 2025.10.1 (WSL) | 395 passed | 395 passed |
| Glue-Suite HA-Latest 2026.8.2 (WSL, py3.14) | 395 passed | 395 passed |
| JSON (manifest/hacs/strings/en/de) + services.yaml | valide | valide |
| quality_scale.yaml | **invalide** (vorbestehend) | valide |
| Diff-Review | — | 23 Dateien, +135/−117; Code-Zeilen: nur §4.7(a) + §4.8 |

Betriebshinweis: Die Glue-Suite braucht die CI-Flags `-o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function` (ci.yml) — ohne sie scheitern alle Tests am `hass`-Fixture; das doppelte `-q` (pyproject-addopts + CLI) unterdrückt zudem die Summenzeile.

## 9. Gesamturteil

| Bereich | vorher (Delta-Stand) | nachher |
| --- | ---: | ---: |
| Inline-Kommentare | 8/10 | 9/10 |
| Docstrings | 8,5/10 | 9/10 |
| Architekturverständlichkeit | 9/10 | 9/10 |
| Home-Assistant-Konformität | 8/10 | 9/10 |
| README / Entwicklerdoku | 8/10 | 9/10 |
| Wartbarkeit | 8,5/10 | 9/10 |

Begründung: Das Niveau der neuen Kommentare war bereits hoch (die adversarial gehärteten C.8-Passagen gehören zum Besten im Repo); der Abzug lag fast vollständig in den zwei Lifecycle-P0s — genau die Kategorie „falsch in gefährlicher Richtung", die einen Wartungs-Entwickler zu falschen Schlüssen über HA-Verhalten verleitet hätte — und der Inventar-Drift der Instrumentierungs-Welle. Beides ist behoben; verbleibende Schulden sind die unter §7 gelisteten Code-Befunde und der unveränderte ADR-Altbestand.
