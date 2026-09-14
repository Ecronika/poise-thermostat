# Verifikation des externen Reviews zu v0.189.1-alpha (2026-08-14)

**Gegenstand:** Drittes externes Code-Review (Folge-Review zu den am 2026-08-10/11 verifizierten Reviews), diesmal über den GitHub-Tag `v0.189.1-alpha` = Commit `d0425726`, verglichen mit Tag `0.188.0-alpha` = `bd9b673`.
**Methode:** 37 Einzelbehauptungen in 11 Themenclustern parallel gegen Code und Tag-Diff geprüft (18 Prüf-Agenten, jede Behauptung mit Datei:Zeile-Beleg); jedes Verdikt ≠ WAHR zusätzlich adversarial gegengeprüft (Auftrag: Erstverdikt widerlegen). GitHub-seitige Behauptungen (Commits, CI, Release-Flags) direkt gegen die GitHub-API verifiziert. Diffs zwischen den Tags durchgehend mit `--ignore-cr-at-eol` (die Web-Uploads tragen CRLF-Rauschen).

**Gesamtergebnis: 30 × WAHR · 7 × TEILWEISE · 0 × FALSCH.** Das Review ist das bislang präziseste der drei — aber es enthält erneut eine Passage mit erfundener Provenienz (Abschnitt 4), und zwei zentrale Schlussfolgerungen sind unsauber (Abschnitte 6–7).

---

## 1. Verifikationsgrundlage: der geprüfte GitHub-Stand

Das Review wurde gegen `github.com/Ecronika/poise-thermostat` geschrieben. Das GitHub-Repo wird per Web-Upload gepflegt („Add files via upload"-Commits) und teilt keine SHAs mit dem lokalen Repo. Inhaltsvergleich des Tag-Commits `d0425726` mit dem lokalen Stand (`a1ceeaf`/`dbfd928`):

- **Code identisch** (custom_components, card, tests, CI) — modulo CRLF und dem lokalen ADR-0036-Nachtrag vom 2026-08-14, der nach dem Tag entstand.
- **GitHub trägt drei Upload-Altlasten**, die lokal nicht (mehr) existieren:
  1. `custom_components/poise/diagnostics.py` — das alte Modul, lokal ersetzt durch das `diagnostics/`-Package, das laut eigenem Docstring das gleichnamige Modul absichtlich shadowed. Auf GitHub toter Code (das Package gewinnt beim Import), funktional harmlos, aber verwirrend.
  2. `docs/adr/ADR-0062-Fehlergrenzen-Diagnose-Segmente.md` — veraltete, falsch nummerierte Kopie des lokalen ADR-0065; auf GitHub existieren beide Nummern (ADR-0062 doppelt belegt: Fehlergrenzen und Schimmelschutz).
  3. `tests/harness/__init__.py` (leer) — lokal nicht vorhanden.
- Interne Docs (docs/reviews, docs/Konzepte, Design-/Research-Dokumente) sind auf GitHub bewusst nicht enthalten.

**Konsequenz:** Beim nächsten Upload die drei Altlasten entfernen. Die Verifikation konnte gegen den lokalen Working Tree laufen; Provenienz-Fragen wurden gegen den echten Tag-Diff `bd9b673 → d0425726` geprüft.

## 2. Meta- und Provenienz-Behauptungen — alle wahr

Anders als die Vorgänger-Reviews (erfundener Commit `3275c366`) hat dieser Reviewer den echten GitHub-Stand gesehen:

| Behauptung | Verdikt | Beleg |
|---|---|---|
| Tag `v0.189.1-alpha` auf Commit `d0425726` | **WAHR** | Tag per `git fetch` verifiziert |
| „Zwischen beiden Ständen liegen 16 Commits" | **WAHR** | `git rev-list --count bd9b673..d0425726` = 16 |
| „CI-Lauf für genau diesen Tag-Commit vollständig grün" | **WAHR** | GitHub Check-Runs API: alle Checks `success` (Glue HA-min py3.12/py3.13, HA-latest py3.13, Quality, Card, hassfest/HACS) |
| „drei HA-Integrationstest-Ziele … zusätzlich config_flow.py separat auf 100 %" | **WAHR** | ci.yml:52-61 Matrix mit exakt 3 Einträgen; ci.yml:87-91 Coverage-Gate. Nuance: das Gate ist ein Step in den Glue-Jobs (läuft in allen 3 Matrix-Läufen), kein eigener Job |
| „GitHub markiert v0.189.1-alpha jetzt korrekt als Prerelease" | **WAHR** | Releases-API: `prerelease: true` (v0.189.0-alpha davor: `false` — der implizite Vorwurf früherer Release-Fehler stimmt also auch) |

## 3. „Wichtigste Veränderungen" — NaN/Inf und Instrumentierung: alles wahr

| # | Behauptung | Verdikt |
|---|---|---|
| V1 | InputReader sanitisiert jetzt auch current_temperature, min_temp, max_temp | **WAHR** |
| V2 | Hub verwirft nicht-finite Leistungs- und Konfigurationswerte | **WAHR** |
| V3 | Load-Shedding behandelt NaN/Inf fail-safe | **WAHR** |
| V4 | Forecast geprüft; snap_to_step kann den Tick nicht mehr per OverflowError abschießen | **WAHR** |
| V5 | Konkrete Regressionstests ergänzt (HA-State-Grenzen, Aktor-NaN, Load-Shedding) | **WAHR** |
| V7 | 5 neue default-off LTS-Sensoren (mpc_setpoint, tpi_valve_percent, pi_setpoint, pi_offset, ref_offset) | **WAHR** |

Belege (Auswahl): `ha/input_reader.py:140` `parse_finite(attrs.get("current_temperature"))`, `:148-149` `finite_attr_num` für min/max_temp (alt: nacktes `float(...)`, NaN passierte als float-Instanz); `hub_coordinator.py:89-100` `_cfg_finite`/`_cfg_finite_opt`; `control/hub_aggregate.py:300-301` — nicht-finite `available_power` sheddet **nichts** (alt: NaN fiel durch `>= 0` durch und sheddete **alle** sheddbaren Zonen); `control/tick_resolve.py:202` totales `snap_to_step` (alt: `round(inf)` → realer OverflowError; bei NaN wäre es ein ValueError gewesen — der Tick-Absturz war in beiden Fällen real); `control/tick_pipeline.py` `math.isfinite(target)` als finaler Guard vor dem Write. Regressionstests: `test_phase4_input_reader.py::test_reads_reject_non_finite_values`, `test_hub_aggregate.py::test_load_shedding_ignores_non_finite_available_power`, `test_optimal_start.py::test_forecast_samples_drop_non_finite_temperatures`, `test_tick_resolve.py::test_snap_to_step_passes_non_finite_through` u. a. — alle im Range neu.

Auch die Provenienz stimmt hier durchgehend: Alle genannten Guards und Tests sind per Tag-Diff nachweislich im Range 0.188 → 0.189.1 entstanden.

## 4. „Hub-Sicherheit deutlich gereift" — Zustand wahr, Provenienz erfunden

Der Absatz beschreibt drei Mechanismen (V6a eingefrorener Raumsensor hält den Kessel nicht mehr unbegrenzt, plausibler Frost bleibt geschützt; V6b Frost-Override prüft `controls_boiler`; V6c ausgeschlossene Frostzonen separat erfasst). **Alle drei Verdikte: TEILWEISE** — mit identischer Begründung:

- **Der beschriebene Code existiert und funktioniert wie behauptet:** `control/hub_aggregate.py:93-94` (`heating = bool(...) and not frozen`), `:58-59` (`if frozen: return 0.0`), `:101-104` (`frost_active` nur im Plausibilitätsband `_FROST_PLAUSIBLE_MIN_C = -20.0` … Floor+Margin), `:166-169` (`frost_active and r.controls_boiler`), `:174-176` (`frost_excluded`-Tuple), `hub_coordinator.py:442-458` (Repair-Issue `frost_zone_not_controlling_boiler`).
- **Aber nichts davon ist in diesem Release entstanden.** `git show bd9b673` zeigt sämtliche Blöcke **wortgleich** bereits in 0.188.0-alpha (inklusive der Kommentare „a comfort heat-call on a dead sensor no longer pins it on forever" und „ADR-0039 correction #3"). Ein Grep über alle geänderten Zeilen des gesamten Tag-Diffs nach `frost|frozen|stale|controls_boiler` liefert **null Treffer**. Die realen +70/+18 Zeilen in den beiden Hub-Dateien sind ausschließlich die Finite-Guards aus Abschnitt 3.

Das ist das aus beiden Vorreviews bekannte Muster: korrekte Zustandsbeschreibung, dem falschen Release zugeschrieben. Für die Release-Bewertung heißt das: Die echte Delta-Leistung von 0.189.1 ist NaN/Inf-Robustheit + CI-Matrix + Instrumentierung — nicht Hub-Logik. Die Anhebung auf 7,8/10 stützt sich teilweise auf nicht existierenden Fortschritt (das Niveau selbst ist deswegen nicht falsch, nur die Begründung).

## 5. Plan-Tabelle Zeile für Zeile

| Zeile | Review-Aussage (Kern) | Verdikt |
|---|---|---|
| P0 | Tag 0.189.1, aber manifest/const/Card/pyproject = 0.189.0, README-Badge = 0.188.0 | **WAHR** (und schlimmer, s. u.) |
| 1 | blocking=False weiter Vertrag; success = nur Dispatch | **WAHR** (Nuance s. Abschnitt 7) |
| 2 | NaN/Inf erledigt | **WAHR** |
| 3 | Card-History-Sync nicht zurückgebaut | **WAHR** (`history.ts:33-34`, `poise-card.ts:131`; Card im Range unverändert) |
| 4 | CI-Struktur richtig; „latest" = pytest-hacc-Neuestes = HA 2026.2.3, nicht HA-Stable | **WAHR** (requirements-test-latest.txt:6-11 dokumentiert exakt das; Datei selbst existierte schon in 0.188, neu ist nur die CI-Verdrahtung) |
| 5 | Viele neue gezielte Tests, kein Property-/State-Machine-Ansatz | **WAHR** (10 neue Testfunktionen ~290 Zeilen im Range; kein hypothesis/stateful im Repo) |
| 6 | TickOrchestrator „whole per-tick program", Backref „transitional" | **WAHR** (`tick_orchestrator.py:1`, `:63`, `:389` — wörtlich) |
| 7 | Patch-Surface richtet Produktionsstruktur an Fault-Injection-Patchpoints aus | **WAHR** (`coordinator.py:84-96` „PATCH SURFACE (binding, do not 'clean up')", 15 noqa:F401-Imports; Call-Time-Auflösung `tick_orchestrator.py:25-31`) |
| 8 | _ATTRS unverändert riesig | **WAHR** (143 Einträge, climate.py im Range byteidentisch) |
| 9 | comfort_base/Kategorie landen initial in entry.data | **WAHR** (`config_flow.py:1003-1007`, Gegenstück `__init__.py:264-282`) |
| 10 | adopt_external_setpoint/mode nicht hot-applied, Kommentar sagt es ausdrücklich | **WAHR** (`coordinator.py:252-256`, `runtime/config.py:323-326`) |
| 11 | One-Shot-Guard-Discovery, guards_resolved vor Registry-Abfrage, Heuristiken bleiben | **WAHR** (`ha/input_reader.py:215-219` — dokumentierte Absicht gegen Retry-Stürme; `devices/model_fixes.py`, `devices/capability.py`) |
| 12 | Interner Step korrekt, Entity statisch 7/30/0.5 | **WAHR** (`climate.py:229-231` mit `FROST_FLOOR_C=7.0`/`DEVICE_MAX_C=30.0`; Snapping nutzt realen Aktor-Step) |
| 13 | Boiler-Actions Freitext, nur Syntax-Validierung | **WAHR** (`config_flow.py:485-486` TextSelector, `:943-953` nur `parse_service_action`, kein has_service-/Existenz-Check) |
| 14 | Einsteigerprofile offen | **TEILWEISE** (s. u.) |
| 15 | Zentrale „Was regelt Poise wirklich?"-Ansicht fehlt | **TEILWEISE** (s. u.) |
| 16 | docs-supported-devices todo | **WAHR** (`quality_scale.yaml:111-113`) |
| 17 | Troubleshooting/Use-Cases/Examples/known-limitations/data-update alle todo | **WAHR** (alle fünf Keys explizit `status: todo`) |
| 18 | imperial_not_supported-Abweisung | **WAHR** (`config_flow.py:986-987` und `:1062-1063`) |
| 19 | heat_cool-only-Aktoren abgewiesen | **WAHR** (`config_flow.py:925-940`; Ort ist der Config-Flow, nicht capability.py) |
| 20 | Eigene Komfortfenster inkl. nummerierter Zusatzfenster, keine Schedule-Entity | **WAHR** (`const.py:92-98` ADR-0070 `comfort_start_N`, UI-Max 8; kein schedule-EntitySelector im Repo) |
| 21 | Keine nativen Trigger/Conditions | **WAHR** (kein device_trigger/condition-Modul, auch nicht im Tag-Baum) |
| 22 | Shadow-first weiter korrekt umgesetzt | **WAHR** (MPC/TPI/PI observe-only; Setpoint-Write speist sich ausschließlich aus resolve_write_target; einzige — vorbestehende, dokumentierte — Ausnahme R13: tpi_duty speist heat_demand für die Kessel-Bedarfssumme) |

**Zu P0 — schlimmer als beschrieben:** Alle fünf Einzelangaben stimmen. Zusätzlich zeigt der Tag-Diff: Alle fünf Versionsdateien sind zwischen `0.188.0-alpha` und `v0.189.1-alpha` **byteidentisch** — schon der 0.188.0-alpha-Tag enthielt Dateien mit 0.189.0 und das 0.188.0-Badge. Es sind also bereits zwei Releases in Folge falsch etikettiert; v0.189.1 fügte nur die dritte Abweichung (Tag-Name) hinzu.

**Zu 14 (TEILWEISE):** Kern stimmt — es gibt kein Tuning-Preset, das die vielen Einzelparameter per Profilwahl vorbelegt. Aber „offen" ohne Einschränkung unterschlägt vorhandene Profil-Mechanismen: das Raumtyp-Profil (ADR-0054, wirkt auf met/clo des PMV-Schattens), die EN-16798-Kategorie I–III, das bewusst schlanke Onboarding (ADR-0008) — und vor allem das **ADR-0052-Dynamikprofil** (`control/dynamics.py:25-90`), das pi_kp/pi_ki/offset_max/MPC-Horizont/Regulationsperiode/Kompressor-Defaults bündelt; diese Einzelparameter sind im Flow gar nicht exponiert. Für die Reglerabstimmung existiert also wortwörtlich „Profil statt vieler Einzelparameter".

**Zu 15 (TEILWEISE):** Als subjektive Bewertung vertretbar — eine konsolidierte „welcher Pfad aktuiert gerade"-Ansicht gibt es nicht, und die Information ist über 143 Attribute, 19 default-deaktivierte Sensoren und mehrere Card-Pills verteilt. „Fehlt" untertreibt aber das Vorhandene: Die Card beantwortet die Grundfrage bereits per default-aktiver Shadow-Pill mit Würde-Werten („TPI …% / PI …° / MPC …°"), Hold-Pill und Preset-/Preheat-/Clamp-/Guard-Chips.

## 6. Beobachtung N1 (Release-Guard) — Diagnose wahr, „technisch unmöglich" überzeichnet

**N1a (WAHR):** Der CI-Guard (`ci.yml:121-130`) vergleicht exakt drei Quellen — card/package.json ↔ manifest.json ↔ const.py — und ist Altbestand aus 0.188. pyproject.toml und README-Badge prüft nichts; deshalb konnte das Badge zwei Releases lang auf 0.188.0 stehen, ohne dass CI rot wurde.

**N1b (TEILWEISE):** Ein Tag-Check ist machbar — `on: push` ist ungefiltert und feuert auch auf Tag-Refs; ein konditionaler Step (`if: startsWith(github.ref, 'refs/tags/')`) könnte `GITHUB_REF_NAME` normalisiert gegen manifest.json vergleichen und hätte v0.189.1-alpha rot markiert. **Aber „damit wäre dieser Fehler künftig technisch unmöglich" ist falsch:** Der Check läuft erst, **nachdem** Tag und Release öffentlich existieren; ein roter Run löscht weder Tag noch Release, HACS liefert Releases unabhängig vom CI-Status aus (hacs.json hat weder version- noch zip_release-Key), und im Web-Upload-Workflow muss der rote Haken erst bemerkt werden. Auch `on: release` feuert erst nach Veröffentlichung. Das ist **Detektion, keine Verhinderung**. Wirklich verhindern würde die Fehlerklasse nur ein Release-Workflow, der Tag und Release **aus** der manifest.json-Version erzeugt (z. B. `workflow_dispatch`: Version aus manifest lesen, Konsistenz aller fünf Quellen prüfen, dann Tag + Release per API anlegen) — dann existiert kein handgetippter Tag-Name mehr, der abweichen kann.

## 7. Empfehlung „Aktor-Convergence" (dreistufiges Modell) — Stufe 2 nicht umsetzbar, Stufe 1+3 richtig

Die Zustandsbeschreibung (Zeile 1) ist exakt: `actuator_executor.py:24` „**blocking=False is the contract**", `:30` „must never switch to ``blocking=True``"; `runtime/zone_runtime.py:207-209` definiert success als „dispatched without a synchronous exception … never device-side confirmation".

Zur Empfehlung `dispatch_accepted → service_completed → state_converged`:

- **Stufe 1 existiert** bereits — das heutige success-Flag ist genau dispatch_accepted.
- **Stufe 2 (service_completed) ist unter dem eigenen Vertrag prinzipiell unbeobachtbar:** HA-Core erzeugt bei `blocking=False` den Handler-Task intern und gibt **kein Task-Handle** zurück (`core.py`: `async_create_task_internal` + `return None`); Handler-Exceptions werden in `_run_service_call_catch_exceptions` geschluckt. Erreichbar wäre die Mittelstufe nur per Vertragsbruch (`blocking=True`, ausdrücklich verboten und begründet) — und sie wird von Stufe 3 praktisch subsumiert.
- **Stufe 3 (state_converged + Repair-Issue) ist valide und mit Bordmitteln umsetzbar.** Die Bausteine existieren alle: per-Tick-Readback (`input_reader.py:545 read_actuator`), automatische Re-Assertion (`tick_resolve.py:151-155` should_write vergleicht gegen den realen Device-Sollwert), Context-basierte Echo-Erkennung (`external_override.py` own_write_ctx_ids/rebaseline_own_echo), ein funktionierendes Konvergenz-mit-Timeout-Vorbild im eigenen Code (`fan_first.py:27` FAN_ECHO_TIMEOUT_S mit await_echo/echo_timeout-Reasons) und das Repair-Plumbing (`ha/health_reporter.py:89-153`). Die echte Lücke: **Keine bestehende Repair-ID deckt Nicht-Konvergenz ab** (actuator_unavailable, sensor_frozen, valve_stuck, heating_failure — nichts davon meldet „Write kommt wiederholt nicht an"). Randbedingungen für die Umsetzung: ADR-0052-§4-Regulation-Throttle (`tick_pipeline.py:1085-1097`) und die adopt_external_setpoint-Logik müssen respektiert werden, damit Re-Asserts weder thrashen noch als User-Änderung fehlgedeutet werden.

Die Empfehlung sollte also auf **„Stufe 1 + Stufe 3"** eingedampft werden. Inhaltlich ist das nahezu deckungsgleich mit dem geplanten C-Scope (P2-Härtung: Sub-Schwellen-Divergenz + Cooling-Pendant) und präzisiert ihn sinnvoll.

## 8. Beobachtung N2 (Quality-Scale-Drift) — wahr, und noch einen Satz weiter

`quality_scale.yaml:92-100` sagt „14 of the 18 diagnostic sensors … ship entity_registry_enabled_default False". Eigene Zählung gegen sensor.py: aktuell **23** Sensoren, davon **19** default-deaktiviert (enabled bleiben nur operative_temperature, confidence, learning_phase, override_expires_at). 14/18 war für 0.188 korrekt; korrekt wäre jetzt 19/23. **Zusätzlich** (vom Review nicht bemerkt): Derselbe Kommentar behauptet „tpi_*/pi_* are climate attributes, not entities" — seit den fünf LTS-Sensoren sind tpi_valve_percent, pi_setpoint und pi_offset Entitäten. Der Reviewer-Vorschlag (Stückzahlen automatisiert verifizieren oder weglassen) ist berechtigt.

## 9. Bewertung der vorgeschlagenen Reihenfolge

1. **Release-Pipeline absichern** — richtig, aber als Verhinderung (Release-Workflow erzeugt Tag aus manifest.json + prüft alle fünf Versionsquellen inkl. pyproject/README), nicht nur als Tag-Guard (Detektion). Kleiner G-Phasen-Baustein.
2. **Aktor-Convergence** — richtig als wichtigstes Reliability-Thema, aber als Stufe-1+3-Modell (Abschnitt 7); deckt sich mit Phase C und schärft deren Scope.
3. **HA-Testmatrix aktuell halten** — richtig; die Unterscheidung „ha-min vs. ha-newest-harness" beschreibt exakt den heutigen Zustand (requirements-test-latest.txt dokumentiert die Harness-Grenze selbst). Ein echter Aktuelle-HA-Lauf hängt am pytest-hacc-Release-Stand (plus Python ≥ 3.14 für HA > 2026.2).
4. **Architektur konsolidieren** (Orchestrator-Zerlegung, Patch-Surface → DI, State-Vertrag ausdünnen) — deckt sich mit D + F; für D liegt die Vorentscheidung D.9 mit dem Attribut-Bericht vom 2026-08-12 bereit.
5. **Erst danach Features** — deckungsgleich mit unserem Plan.

Die Gesamtanhebung auf 7,8/10 ist im Ergebnis plausibel, in der Begründung aber zu großzügig: Der als Release-Fortschritt gewertete Hub-Sicherheits-Block (Abschnitt 4) ist Bestand aus 0.188.

## 10. Konsequenzen

1. **Sofort (Repo-Hygiene GitHub):** Beim nächsten Upload `diagnostics.py`, `ADR-0062-Fehlergrenzen`-Duplikat und `tests/harness/__init__.py` entfernen; README-Badge auf die reale Version heben.
2. **Kurzfristig (klein):** quality_scale.yaml-Kommentar korrigieren (19/23; tpi_*/pi_*-Satz streichen) — oder Stückzahlen ganz entfernen. Versions-Guard in CI um pyproject.toml, README-Badge und (konditional) Tag-Namen erweitern — als Detektion klar deklariert.
3. **Mittelfristig:** Release-Workflow (workflow_dispatch → Tag/Release aus manifest.json) als eigentliche Verhinderung; Aufnahme in Phase G. Write-Convergence als präzisierter C-Scope (Stufe 1+3, Repair-ID für Nicht-Konvergenz, Throttle-/Adoption-verträglich).
4. **Unverändert gültig:** Reihenfolge D → C → F → G des bestehenden Plans; das Review liefert keinen Grund zur Umplanung, sondern bestätigt sie.

---

## Nachtrag 2026-08-15 — Review-Zeile 4 (HA-Testmatrix) erledigt: echter Aktuelle-HA-Gate

Der Reviewer hatte recht: „latest" war ein Etikett, kein Zustand. Zum Prüfzeitpunkt (Abschnitt 5, Zeile 4) hing das Ziel an der Harness-Grenze — pytest-hacc-Releases endeten bei HA 2026.2.3. **Diese Grenze ist gefallen:** `pytest-homeassistant-custom-component 0.13.356` pinnt `homeassistant==2026.8.2`, also die aktuelle HA-Stable (PyPI, 2026-08-15), und verlangt Python ≥ 3.14 (HA selbst: ≥ 3.14.2).

Umgesetzt und lokal verifiziert (Python 3.14.5 via `uv` in WSL, HA 2026.8.2 + `home-assistant-frontend==20260729.7`):

* **`requirements-test-latest.txt`**: Pin 0.13.316 → **0.13.356** (HA 2026.2.3 → **2026.8.2**), Frontend-Wheel 20260128.6 → 20260729.7.
* **`ci.yml`**: Der latest-Job läuft jetzt auf **Python 3.14**; die MIN-Ziele bleiben 3.12/3.13 (HA 2025.1.4 unterstützt 3.14 nicht). Der Quality-Job (ruff, mypy strict, Pure-Core) wurde um **3.14** erweitert — ein Aktuelle-HA-Gate ist nur ehrlich, wenn Lint, Typen und Kern auf dem Interpreter laufen, den aktuelle HA verlangt.
* **Kein API-Drift:** Die volle Glue-Suite (390 Tests) läuft gegen HA 2026.8.2 unverändert grün; ruff/mypy/Pure-Core (1336 Tests, 98,7 % Coverage) ebenfalls auf 3.14. Zwischen 2026.2 und 2026.8 war für diese Integration also nichts zu portieren. (Einziger beobachteter Wegfall: `homeassistant.__version__` existiert nicht mehr — Poise nutzt es nicht, nur ein Hilfsskript stolperte darüber.)
* **Neu — `harness-freshness`-Job (die eigentliche Lehre):** Ein gepinnter „latest"-Stand kann nicht bemerken, dass die Welt weiterzieht; genau daran ist der Vorzustand gescheitert. Ein wöchentlicher (und manuell auslösbarer) Job vergleicht den Pin gegen PyPI und wird rot, sobald eine neuere Harness existiert — inklusive der HA-Version beider Stände in der Fehlermeldung. Er hängt bewusst **nicht** am `gate`-Job und läuft nicht auf push/PR: Ein neues HA-Release darf niemals einen fremden PR rot färben, es soll als roter geplanter Lauf „bump the pin" erscheinen. Beide Richtungen sind lokal getestet — gegen den heutigen Pin grün, gegen den alten 0.13.316-Stand meldet er exakt die vom Review beanstandete Situation.

Damit ist Zeile 4 der Plan-Tabelle von 🟡 auf ✅ zu setzen; die Unterscheidung „ha-min vs. ha-newest-harness" ist gegenstandslos geworden, weil die neueste Harness jetzt die aktuelle Stable ist.

---

*Rohdaten der Verifikation: Workflow-Ergebnis mit allen 37 Einzelverdikten inkl. Datei:Zeile-Evidenz und adversarialen Gegenprüfungen (Session ffc24afc, Task wnypjt4a6). Vorgänger-Berichte: `2026-08-10-externes-code-review-verifikation.md` (Plan A–G), `2026-08-11-externes-review-gesamtverifikation.md`.*
