# Qualitätsbewertung nach ISO/IEC 9126 + Clean Code — Poise v0.191.0

**Stand:** 2026-08-19, Branch `main` (Commit `489db712`) + uncommittete Working-Tree-Änderungen (23 Dateien, +135/−117).
**Hinweis:** Die Zerlegung von `ha/tick_orchestrator.py` (Plan Rev. 8) ist auf dem Branch `refactor/tick-orchestrator` bereits umgesetzt, aber **nicht in main** — die Wartbarkeitsbewertung gilt für main.

**Vermessungsbasis:** 28.449 LOC Produktivcode (127 Module, 784 Funktionen, 224 Klassen) · 41.990 LOC Testcode (1.689 Testfunktionen, Ratio 1,48:1) · 72 ADRs · 0 externe Laufzeit-Abhängigkeiten.
**Eigene Verifikation:** Pure-Core-Suite **1.362 Tests grün** in ~11 s (Python 3.13.14, `.venv-dev`), Coverage **99 %** (Gate 85 %). Glue-Suite (384 Tests) läuft nur in CI/WSL (`fcntl`-Import ab HA 2025.10). 0 `skip`/`xfail` in 210 Testdateien.

---

## Gesamtübersicht

| ISO/IEC 9126-Merkmal | Note | Kurzurteil |
|---|:---:|---|
| Funktionalität | **9/10** | Großer, aber kohärent regierter Umfang; normbasiert; ehrliche Active/Shadow-Trennung; 1 dokumentierter Trace-Bug |
| Zuverlässigkeit | **9/10** | Degradationskaskaden, Watchdogs, saubere Recovery; Selbstdeklaration „Alpha“, Winter-Feldvalidierung offen |
| Benutzbarkeit | **6,5/10** | Starke Laufzeit-Führung (28 Repair-Issues), aber Setup-Pfad fast ohne Inline-Hilfen, README-Sprachmix, Doku-Lücken |
| Effizienz | **8/10** | Vorbildliche asyncio-Disziplin, alles gedeckelt; ein realer Befund: Recorder-Last durch 150 climate-Attribute |
| Wartbarkeit (main) | **7/10** | Fachschichten exzellent; die technische Schuld konzentriert sich auf `tick_orchestrator.py` (auf Branch bereits gelöst) |
| Übertragbarkeit | **9/10** | Null Dependencies, Zwei-Ziel-HA-Matrix mit Drift-Guards, generische Geräteerkennung; Celsius-only |
| **Clean Code (quer)** | **8,5/10** | Namensgebung, Kommentare, Konstanten-Disziplin herausragend; Parameterlisten und eine Dreifach-Redundanz schwach |

---

## 1. Funktionalität — 9/10

*Submerkmale: Angemessenheit 9 · Richtigkeit 9 · Interoperabilität 9 · Security 9*

**Positiv:**
- **Kohärenter Umfang trotz Größe:** Regelung (Dual-Setpoint, MPC/TPI als Shadow, Optimal Start/Stop), Komfort (EN 16798-1, PMV/PPD nach ISO 7730, Schimmelschutz DIN 4108-2), EKF-Schätzung, Multi-Zone-Hub, Diagnose/Trace — zusammengehalten durch **einen** expliziten Präzedenz-Solver (`contracts.py:26`: SAFETY < HEALTH < COMFORT < EFFICIENCY < LEARNING < OPERATION; alle Klemmungen über `resolve_constraints()`).
- **Ehrlicher Scope:** README trennt Active/Shadow/Roadmap; `tests/test_non_goals.py` verriegelt Nicht-Ziele testseitig. MPC schreibt nicht, bevor die ADR-0055-Regelgütemetrik es freigibt.
- **Richtigkeit abgesichert:** 99 % Pure-Core-Coverage, Golden-Replay-Determinismus (ADR-0014), 33 Hypothesis-Properties auf den Pipeline-Enden, `RuleBasedStateMachine` über die Setpoint-Adoption („every historical bug in this area was a SEQUENCE bug“).
- **Security sauber:** 0 gefährliche Konstrukte (eval/exec/subprocess/pickle), 0 Secrets, 0 Netzwerkzugriffe, `requirements: []`. Config-Flow vollständig deklarativ validiert plus semantische Prüfungen (heat_cool_only, sensor_on_actuator, actuator_in_use mit Zonennennung). Diagnostics redigiert 28 Entity-ID-Keys.
- **Interoperabilität:** quality_scale.yaml 34 done / 11 exempt (je begründet) / 10 todo — die todos sind ausschließlich Doku/Kosmetik.

**Negativ:**
- **Bestätigter, bewusst nicht gepatchter Bug:** `trace/schema.py:223` liest `frozen`, der Produzent (`tick_orchestrator.py:3453`) schreibt `sensor_frozen` → `TraceRecord.frozen` ist permanent `False`. Nur Offline-Replay betroffen (kein Regelungsrisiko), aber `tests/test_phase8_trace.py:46` zementiert den Defekt.
- **Telemetrie-Asymmetrie:** `cooling_failure` hat ein Trace-Feld, das Heizausfall-Verdikt nicht (`schema.py:127-129`).
- ADR-0022 (Datenschutz) steht bei 75 % — Export-Anonymisierung und Timestamp-Quantisierung im Trace offen.
- `pipeline.py:127` (Referenz-Pipeline, nicht im Live-Pfad): `except Exception: continue` schluckt still ohne Log.

## 2. Zuverlässigkeit — 9/10

*Submerkmale: Reife 8 · Fehlertoleranz 9,5 · Wiederherstellbarkeit 9,5*

**Positiv:**
- **Degradationskaskade bei Sensorausfall** (`tick_orchestrator.py:637-692`): 30 min letzten Zustand halten + eine WARNING, danach Safe-State auf Gesundheitsboden („fails toward warmth“, `frozen_safe_target = max(frost_floor, mold_min)`), Adoptions-Baseline wird gelöscht, damit der eigene Safe-Write bei Rückkehr nicht als User-Hold missgelesen wird.
- **Drei Watchdogs:** Sensor-Freeze/Implausibilität (`sensor_watchdog.py`, 100 % Coverage), Heiz-/Kühlausfall latched mit Uhr-Härtung gegen DST-Rücksprung (`heating_failure.py:62-66`), Schreibkonvergenz mit adversarial gehärteten Evidenzregeln (`write_convergence.py`).
- **Fehler werden gezählt und eskaliert, nie stumm verschluckt:** Tick-Exceptions immer re-raised + Issue nach 3 Fehlschlägen; Persistenz-Issue nach 5; Konvergenz-Issue. 51 breite Except-Handler — aber jeder mit `noqa: BLE001` + Doktrin-Begründung. NaN/Inf stirbt konsequent an der Systemgrenze (u. a. `tick_resolve.py:357`: „so NaN/Inf can never reach the actuator“).
- **Recovery vorbildlich:** I/O-Fehler → `ConfigEntryNotReady` (Modell wird nie durch transienten Ladefehler überschrieben), nur echte Korruption → fresh; partielle Sektionsrecovery im Codec; `dirty` nur bei erfolgreichem Save gelöscht; drei Flush-Punkte inkl. `EVENT_HOMEASSISTANT_STOP`; Wallclock-verankerte Override-Holds überleben Neustarts.
- **0 TODO/FIXME/HACK in 28 kLOC**, 0 skip/xfail in 210 Testdateien.

**Negativ:**
- Selbstdeklaration **Alpha**; M3 hardware-parked, MPC-Live-Freigabe wartet auf Wintervalidierung — die Lernpfade sind harness-, aber noch nicht saisonfeldbewährt.
- Kein dedizierter Overheat-Mechanismus (nur Gerätemax-Cap + Norm-Cap im Solver) — spiegelbildlich zum Frost-Rescue-Pfad wäre mehr Symmetrie denkbar.

## 3. Benutzbarkeit — 6,5/10

*Submerkmale: Verständlichkeit 6 · Erlernbarkeit 6 · Bedienbarkeit 7 · Attraktivität 7*

**Positiv:**
- **Laufzeit-Nutzerführung stark:** 28 übersetzte Repair-Issues (Ursache + Folge + Abhilfe, z. B. `sensor_at_heat_source`), fixabler Repair-Flow mit apply/dismiss und 30-Tage-Cooldown, redigierte Diagnostics, eigene Lovelace-Karte mit visuellem Editor und Versionsdrift-Warnung.
- **Schlanker Einstieg:** nur Raumsensor + Aktor Pflicht, Rest Defaults; Genauigkeits-Section einklappbar; kaum Freitext (65 NumberSelector, 35 EntitySelector, nur 5 TextSelector).
- **Übersetzungen perfekt synchron:** 290 Schlüssel in strings.json = en.json = de.json, 0 Differenzen; deutsche Texte sind echte Fachübersetzungen.
- Feldgenaue Fehler mit Kontext (`actuator_in_use` nennt die konkrete Zone; °F-Installationen werden früh abgewiesen).

**Negativ:**
- **Die größte Lücke: Inline-Hilfen im Setup-Pfad.** `room`-Schritt 2/10 Felder mit `data_description`, `system`-Schritt **0/13** (inkl. zweier Freitext-Service-Felder!), reconfigure 1/17 — während der Options-Flow 29/51 erklärt. Genau dort, wo Neunutzer Hilfe brauchen, fehlt sie.
- **Options-Flow = ein Formular mit 51 Feldern** in 7 Sections — kein progressives Disclosure.
- **README mischt Deutsch und Englisch** im selben Dokument (Kapitel „Manuelle Eingriffe“ deutsch, Rest englisch; deutsche Zeilen in der englischen Optionstabelle). `docs/` (98 Dateien) komplett deutsch — als interne Doku exzellent, für internationale HACS-Nutzer eine Barriere.
- 6 offene Doku-Regeln des Quality Scale (troubleshooting, examples, use-cases, known-limitations, supported-devices, data-update), keine `icons.json`, nur 2 Sprachen (ADR-0021 bei 70 %).

## 4. Effizienz — 8/10

*Submerkmale: Zeitverhalten 9 · Verbrauchsverhalten 7*

**Positiv:**
- **asyncio-Disziplin vorbildlich:** kein `time.sleep`, kein blocking I/O im Loop; Datei-I/O nur über Executor; Trace-Schreiben tick-entkoppelt (ADR-0063, „SYNCHRONOUS by contract“-Enqueue + Hintergrund-Drain); Forecast mit warmem Cache, Single-Flight, 10-s-Timeout nur beim Kaltstart; alle Effekt-Writes `blocking=False`.
- **Selbstvermessung eingebaut:** 50-ms-Tick-Budget mit EWMA/Max/over_count, exponiert als Sensor `tick_duration_ms`. 60-s-Tick gegen Alternativen begründet (ADR-0020); Event-Zusatzreaktion mit Attribut-Churn-Filter.
- **Alle wachsenden Strukturen gedeckelt** (deque maxlen=16, Trace-Queue 512 + 20-MiB-Rotation, override/feedback-Stats je 50). Persistenz gedrosselt: 1 Save/30 Ticks + sofort bei Nutzerabsicht.
- Rechenlast trivial: MPC greedy 132 predict-Calls/Zone/Tick, handgeschriebene 6×6-EKF-Mathematik — reine stdlib, unkritisch.

**Negativ:**
- **Der eine substanzielle Befund — Recorder-Last:** `climate.py` liefert **150 `extra_state_attributes`** pro Tick, kombiniert mit `coordinator.py:170 always_update=True` → bei 8 Zonen ~70.000 State-Writes/Tag mit 150-Schlüssel-Attributsatz, auch ohne Änderung. Keine `recorder:`-Exclude-Empfehlung in der Doku. (19/23 Sensoren sind immerhin default-disabled.)
- Karten-JS (58 KB) wird via `add_extra_js_url` auf jedem Dashboard für jeden Nutzer geladen, auch ohne Kartennutzung (bewusst gewählt, dokumentiert).

## 5. Wartbarkeit — 7/10 (main)

*Submerkmale: Analysierbarkeit 7,5 · Änderbarkeit 6 · Stabilität 7,5 · Testbarkeit 9*

**Positiv:**
- **Analysierbarkeit durch Begründungsdichte:** 33,4 % Kommentar-/Docstring-Anteil, 100 % Moduldocstrings, **857 ADR-Referenzen in 116/127 Dateien** (per Linter erzwungen) — Kommentare erklären fast ausnahmslos das WARUM inkl. Angriffsszenarien und physikalischer Herleitungen.
- **Stabilität:** keine echten Importzyklen (Rückwärtskanten sauber hinter `TYPE_CHECKING`), 89 % frozen Dataclasses, 96 % slots, `mypy --strict` über Paket + Harness, gesundes Stable-Dependencies-Profil (const/contracts hohe Afferenz, Orchestrierung hohe Efferenz).
- **Testbarkeit herausragend:** 91/127 Module komplett HA-frei; Closed-Loop-Harness treibt Produktions-EKF/MPC gegen ein RC-Modell mit bekannter Wahrheit („without waiting for a real heating season“); getrennte Gates 85 % pur / 95 % Glue / **100 % config_flow**.
- Flache Komplexität: Median-Funktionslänge 13 Zeilen, nur 7 Funktionen über McCabe 10, nur 3 Funktionen tiefer als Verschachtelung 3.

**Negativ (konzentriert auf die HA-Adapterschicht, ~17 % des Codes):**
- **`tick_orchestrator.py` (3.487 Z.) ist das God Object:** eine Klasse, 48 Methoden, 21 davon >50 Z., 6 >100 Z. (Spitze `_stage_assemble_tick_data` 331 Z.), Fan-Out 54, **147 `self._c.`-Durchgriffe auf 63 Coordinator-Attribute** (Feature Envy; als „transitional“ deklariert). → *Auf Branch `refactor/tick-orchestrator` bereits gelöst (931 Z., 0 `self._c`, Ratchet-Gate) — Merge ausstehend; nach Merge wäre die Note hier ~8,5.*
- **Dreifach-Redundanz der Stage-Signaturen** (Shotgun Surgery): jede der 12 Stages existiert als Implementierung (`tick_pipeline.py`), Signaturkopie (`zone_runtime.py:498-816`, ~320 Z. reine Delegation) und Aufrufstelle (Orchestrator). Ein neuer Parameter = drei Änderungsorte.
- Extreme Parameterlisten: `compose_climate_band` **33** Params (`diagnostics/shadows.py:327`), `dual_setpoint.decide` 23, `plan_preheat` 18 — mildernd: alle keyword-only und strict-typisiert.
- `commit_execution` (`zone_runtime.py:185`): McCabe 33, 13-Zweig-String-Dispatch statt Polymorphie.
- Test-Patch-Surface `_CoordinatorGlobals` koppelt Produktionscode an Testmechanik.

## 6. Übertragbarkeit — 9/10

*Submerkmale: Installierbarkeit 10 · Anpassbarkeit 9 · Koexistenz 9 · Austauschbarkeit 8*

**Positiv:**
- **Null Fremdabhängigkeiten** (Import-Audit über 139 Module: nur stdlib + HA-mitgeliefertes voluptuous) → installierbar auf jeder HA-Plattform ohne Build-Toolchain; hassfest + HACS-Action in CI.
- **Zwei-Ziel-HA-Matrix** (MIN 2025.10.1/Py 3.13, LATEST 2026.8.2/Py 3.14) mit drei Drift-Guards: `min-consistency` (hacs.json ↔ README-Badge ↔ Test-Pin, per PyPI verifiziert), wöchentlicher `harness-freshness`-Cron, Collection-Guard gegen stillen 0-Test-Lauf.
- **HA-API-Risiken inventarisiert und terminiert** (Drift-Review 2026-08-15): 2026.10- und 2026.12-Brüche bereits gelöst, `via_device`-Entfernung (2027.8) terminiert offen. AST-basierter Deprecation-Test (`test_ha_deprecations.py`), weil HA Deprecations nicht als Warning meldet.
- **Geräte-generisch:** Capability-Erkennung rein attributbasiert (`devices/capability.py`), „No model names“; einzige Herstellerregel ist ein Schreib-Ausschluss (TRVZB-Firmware-Bug).
- **Koexistenz sauber:** durchgängiges Namespacing, `runtime_data` statt `hass.data`, kein Monkeypatching, Own-Write-Echo-Erkennung, aktive Erkennung fremder Regler auf demselben Gerät (Repair-Issue), vollständiges Aufräumen beim Entfernen inkl. Aktor-Parken.
- **Hot-Apply:** Options-Änderungen ohne Reload — das gelernte Gebäudemodell überlebt jede Komfort-Anpassung.

**Negativ:**
- **Celsius-only** — imperiale Installationen werden abgewiesen (ehrlich, aber eine Einschränkung).
- `via_device`-Deprecation offen; zwei semi-öffentliche Frontend-APIs als Restrisiko (abgefangen, blockieren Setup nie).
- Entwickler-Portabilität: Glue-Suite unter Windows nicht lauffähig (`fcntl` ab HA 2025.10) — nur Contributor betroffen, dokumentiert.

---

## Clean-Code-Bewertung — 8,5/10

| Prinzip | Note | Beleg |
|---|:---:|---|
| Aussagekräftige Namen | **9,5** | Domänensprache (`free_running_widen`, `mold_floor`, `compressor_guard`), konsistente Präfix-/Suffix-Familien (`stage_*`, `*_fn`, `*_eff`), absichtskodierende Enums. Schwach: `self._c`/`self._g`-Sigel, Namenskollision `pipeline.py` vs. `control/tick_pipeline.py` (Root-Datei ist toter Referenzcode) |
| Kleine Funktionen | **7** | Median 13 Z., 89 % ≤ 50 Z. — aber 24 Funktionen >100 Z., konzentriert im Orchestrator (auf Branch gelöst) |
| Wenige Argumente | **5,5** | Schwächster Punkt: 33/23/18/17/15 Parameter; mildernd keyword-only + strict-typed; Parameter-Objekte (`FinalizeContext`) existieren als Vorbild, werden aber nicht flächig genutzt |
| Kommentare erklären WARUM | **9,5** | 857 ADR-Referenzen, Angriffsszenarien, physikalische Herleitungen, dokumentierte historische Bugs; 0 TODO/FIXME |
| DRY | **6,5** | Dreifache Stage-Signatur-Pflege + Finalize-Kontext 3×; HA-Entity-Boilerplate idiomatisch-unvermeidbar |
| Fehlerbehandlung | **9** | Keine stummen Fehler im Live-Pfad; jede breite Except-Klausel begründet; Eskalation über Repair-Issues (Ausnahme: `pipeline.py:127`, nicht live) |
| SOLID | **7,5** | DIP/ISP im Kern vorbildlich (injizierte Callables, Protokolle, verengte Kontexte, 89 % frozen); SRP-Verletzung in Orchestrator/Coordinator (48/53 Methoden); String-Dispatch statt Polymorphie in `commit_execution` |
| Keine Magic Numbers | **9,5** | 402 begründete Konstanten; `const.py` ist eine Herleitungstabelle („120 s = 2 ticks“); nur 154 Literale in 28 kLOC, davon 53 normkonforme ISO-7730-Koeffizienten. Kleinere Duplikate: `16.0`/`26.0` literal neben existierender Konstante |
| Tests als First-Class-Code | **9,5** | Ratio 1,48:1, Property-based + StateMachine + Golden-Replay + Governance-Tests (Non-Goals-Verriegelung, ADR-Lint, AST-Deprecation-Scan); Harness unter mypy --strict |
| Formatierung/Konsistenz | **10** | ruff check + format + mypy --strict als CI-Gates auf 3 Python-Versionen, 0 Befunde |

---

## Priorisierte Empfehlungen

1. **Branch `refactor/tick-orchestrator` mergen** — löst die drei größten Wartbarkeitsbefunde (God Object, `self._c`-Durchgriffe, Methodenlängen) auf einen Schlag; Ratchet-Gate hält den Stand.
2. **Recorder-Last adressieren:** `always_update=True` prüfen, README-Abschnitt mit `recorder:`-Exclude-Empfehlung, ggf. Attributsatz der climate-Entität reduzieren/auslagern.
3. **`data_description` für den Setup-Pfad nachziehen** (room/system/reconfigure: aktuell 3 von 40 Feldern) — größter Benutzbarkeits-Hebel bei kleinem Aufwand.
4. **frozen-Trace-Key-Bug fixen** (`schema.py:223` → `sensor_frozen`, TRACE_VERSION → 3, Golden neu einfrieren, `test_phase8_trace.py:46` nachziehen) + fehlendes `heating_failure`-Trace-Feld ergänzen.
5. **README-Sprache vereinheitlichen** und die 6 offenen Doku-Regeln des Quality Scale schließen.
6. **Stage-Delegationsebene** in `zone_runtime.py:498-816` durch Parameter-Objekte ersetzen (beendet die Dreifach-Signaturpflege) — falls nicht ohnehin vom Branch miterledigt.
7. ADR-0022 abschließen (Timestamp-Quantisierung, gesalzene Zonen-ID im Trace-Export).

---

## Umsetzungsstand (Nachtrag, gleicher Tag)

Alle sieben Empfehlungen wurden am 2026-08-19 abgearbeitet (Commits `ded0311f`..`b061834d`):

1. **Merge erledigt** (`2b52f3f9`): `refactor/tick-orchestrator` → main. Der Branch enthielt über O.0–O.7 hinaus auch S.1–S.4, N1/N2 und Version 0.192.0; damit sind zusätzlich `exception-translations`, `icon-translations` und alle 6 Doku-Regeln des Quality Scale geschlossen (offen bleibt nur `brands`, braucht den externen PR). Wartbarkeit auf main jetzt ≈ **8,5** (Orchestrator 931 Z., 0 `self._c`, Ratchet-Gates).
2. **Recorder-Diät** (`9c52821d`): 136 der 150 climate-Attribute per `_unrecorded_attributes` von der DB ausgenommen (Partition total, Glue-Test-gepinnt); `always_update=True` bleibt — im Code begründet nötig (Hub-Staleness bei identischem Degraded-Payload). README-Abschnitt „Recorder / database load".
3. **Setup-Hilfen** (`88f2cdeb`): room/system/reconfigure jetzt 40/40 Felder mit `data_description`, en/de synchron (499 Keys).
4. **Trace v3** (`506e1667`): `frozen` liest `sensor_frozen`, `heating_failure`-Feld ergänzt, TRACE_VERSION 3 (v≤2-`frozen` als bedeutungslos markiert), MIN_SUPPORTED bleibt 1. TDD.
5. **README einsprachig** (`2cc555a7`): Hold-/Adoptionskapitel übersetzt, Anker/Optionslabels angepasst, Versions-Badge-Drift 0.191→0.192 mitgefixt.
6. **Delegationsebene: analysiert, bewusst belassen.** Nach dem Merge ist die Fassade plan-reviewte Architektur (Split-Plan: `zone_runtime.py` als „genau ein Konsument" der Pipeline-Module, Struktur-Gates pinnen die Partition); einziger Restfall `_stage_observe_guarded` ist als P.2 mit zwei sanktionierten Ausgängen getrackt. Ein Ad-hoc-Umbau widerspräche den Gates — Empfehlung 6 wird damit zurückgezogen.
7. **ADR-0022 implementiert** (`b061834d`): ts-Quantisierung (900-s-Buckets, `mono` exakt), gesalzener Trace-Dateiname (`salted_trace_slug`), Löschpfad räumt beide Namen; ADR auf Implementiert/Live-D, Index synchron.

Gates nach jedem Schritt lokal grün (ruff, ruff format, mypy strict 142 Dateien, pure Suite 1.641 Tests); die Glue-Suite (drei umgestellte Trace-Tests, ein neuer Recorder-Diät-Test) verifiziert CI beim nächsten Push — lokal unter Windows nicht lauffähig (`fcntl`).
