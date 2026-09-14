# Kommentar- und Dokumentations-Review (2026-08-09)

**Typ:** Vollständiger Review + Umsetzung (behavior-preserving) · **Umfang:** alle 130 Python-Module, README, quality_scale.yaml, Paket-Docstrings · **Ergebnis:** 96 Dateien geändert (+903/−772 Zeilen), ausschließlich Kommentare/Docstrings/Doku plus drei sanktionierte Mikro-Codeänderungen (s. §4.9).

## 1. Executive Summary

Die Ausgangsqualität war ungewöhnlich hoch: nahezu flächendeckende Modul-Docstrings, null TODO/FIXME/HACK-Schulden, dichte Warum-Kommentare mit ADR-Ankern, gepflegte i18n (strings/en/de strukturell identisch, 0 Waisen). Die Schwachstelle war systematisch dieselbe: **Phasendrift** — Kommentare und Docstrings, die während des Coordinator-Refactorings (Phasen 0–10) und der Feature-Wellen (ADR-0059…0069) korrekt waren und nicht nachgezogen wurden. Daraus entstanden mehrere Aussagen, die das **Gegenteil des heutigen Codes** behaupteten (Shadow-behauptet-aber-live, Proxy-APIs, die nicht mehr existieren, Kontrakt-Enumerationen mit fehlenden Mitgliedern), plus hand-gepflegte Zählwerte (Keys, Felder, Stages), die erwartungsgemäß gedriftet waren. Alle P0/P1-Befunde und die tragfähigen P2 wurden umgesetzt; Verhalten, Entity-IDs, Persistenzformat und Tests sind unverändert (beide Suiten grün).

## 2. Verwendete Standards

- **HA Developer Docs — Style Guidelines:** PEP 8 + PEP 257 via ruff; „Comments should be full sentences and end with a period"; Docstrings knapp, Google-Style nur bei Bedarf; keine Typangaben in Docstrings (gehören in Annotations); Datei beginnt mit Modul-Docstring.
- **HA Integration Quality Scale** (Bronze–Platinum, docs-* Regeln): das Repo führt die Selbstbewertung in `quality_scale.yaml`; sie wurde faktisch nachgezogen.
- **Projekt-eigene Konvention** (ADR-0000, Phase-9-Kommentar-Cleanup des Refactorings): Warum-Kommentare mit ADR-Verweis sind der Standardmechanismus; nackte Review-Codes (K3, AR-02, P1-4b, R13, V9 …) und Refactoring-Phasen-Narration („since phase 10", „was:", „moved verbatim") gelten als Schuld, Invarianten bleiben in Gegenwartsform.
- **Abgeleitete Review-Regeln:** Kommentar erklärt WARUM; falsche Kommentare > fehlende Kommentare; keine hand-gepflegten Zählwerte (§16-Prinzip: Gründe/Invarianten statt Zahlen); keine spekulativen Herkunftsangaben.

## 3. Ausgangszustand (Befundklassen)

- **A (wertvoll, korrekt) — die große Mehrheit.** Beispiele, die unangetastet blieben: die Positionsbeweise und Await-Fenster-Argumente im Orchestrator, die Hold-Gating-Kommentare im Codec, die Adoption-Guard-Reihenfolgen, die Magnus-/ISO-7730-/EN-16798-Herleitungen.
- **C/D (historisch → teils falsch), der Kernbefund:** ~25 Stellen, an denen Refactoring- oder Feature-Phasen als Zukunft/Gegenwart beschrieben wurden, obwohl sie abgeschlossen bzw. überholt sind. Gravierendste Fälle (P0): `multi/lifecycle.py` („gates nothing live" — der Verdichterschutz unterdrückt real den Mode-Nudge, ADR-0046 §8 Nachtrag), `runtime/__init__.py` („nothing in coordinator.py imports these modules yet"), `zone_runtime.py`/`coordinator.py` (Property-Proxy-/`_clock`-/`_dirty`-API, die Schritt 2/3 entfernt hat), `tick_orchestrator.py` („trace I/O counts into tick_ms" + „until F-TRACEIO" nach geliefertem F-TRACEIO; „F-SAFESEQ/F-CONTEXT until phase 10" für weiterhin offene Fixes), `feedback.py` („F2 … feeds nothing" — F2 ist verdrahtet), `actuator.py`/`hvac_modes.py`/`controller.py`/`arbitration.py` (Phase-0-Scope-Behauptungen), Suggestion-Emission dreimal als „opt-in, default off" (seit ADR-0060 §3 default ON).
- **D (Zähl-/Enumerationsdrift):** Codec „39 keys" (real 42, test-gepinnt), Restore-Kette ohne `comfort_activation`/`vent_active`/`surface_rh_mean`, „four value baselines" (real 6), `FinalizeContext` „50 names" (real 53), „26 stages"/„19 keys"/„~115-line literal", Executor „five sequences" ohne `run_fan_write`, Context-Matrix ohne den getaggten Fan-Write, `effect_id`-Vokabular ohne `fan_write`, blocking=True-Inventare ohne die Hub-Boiler-Actions, tick_pipeline-Kommentare, die auf entfernte Blöcke zeigen („shadow block below", „computed once above"), tote Bezeichner (`_own_ctx()`, `own_context_ids`).
- **B/P2 (Review-Code-/Historien-Schuld):** ~70 nackte Codes (K2/K3, R6–R13, V1–V10, M2–M8, F4–F23, AR-*, P1/P2-*, „Finding 1", Datums-Archäologie) außerhalb des bereits bereinigten Phase-9-Scopes; dazu „charter Gx"/„Programmstrukturplan"-Referenzen auf nicht im Repo existierende Dokumente und zwei falsche ADR-Zuordnungen (`Maturity`→ADR-0009 statt ADR-0028; `running_mean`→ADR-0010; `capability.py` zitierte ADR-0015, dessen §1 von ADR-0036 revidiert ist).
- **F (fehlende Warum-Doku, punktuell):** Einheiten/Herkunft einzelner Konstanten (EKF-Bounds/Q, Guard-Ordnungs-Konsequenzen, 1/12-Monatsannahme der Savings, `guards_resolved`-vor-try-Semantik, Drop-Warnung once-per-instance im Trace-Recorder).
- **README/quality_scale:** Zahlen/Defaults durchgehend korrekt, aber Inventardrift: 17 statt 18 Sensoren, Button-Plattform und `poise.comfort_feedback` fehlten, zwei faktisch falsche Aussagen (Adopt-Reasons „keine Entity-Attribute"; Schedule-Entität „konfiguriert" statt auto-erkannt), Datei endete mitten im Wort; quality_scale beschrieb eine Ein-Service-Integration und führte ein bereits erfülltes `entity-disabled-by-default` als todo.

## 4. Durchgeführte Änderungen (je Bereich)

1. **runtime/ + persistence/** — Paket-/Modul-Docstrings auf Ist-Architektur (ZoneRuntime-Ownership, keine Proxys); Codec: Key-Zählung durch Test-Pin-Verweis ersetzt, Restore-Kette vervollständigt, `DiagnosticsSection`-Interleaving korrigiert, Monotonic-Ausschlussliste um `last_fan_cmd_ts` ergänzt; `state.py`-Summenzeilen (6 Baselines, Humidity-/Diagnostics-Persistenzsets) und Clock-Domänen (wall vs. monotonic) präzisiert; `tick_result.py`: `fan_write` ins `effect_id`-Vokabular, `PersistencePhase.NONE` als unbenutzt markiert, Zähler und tote `self._*`-Namen entfernt.
2. **coordinator.py / hub_coordinator.py / __init__.py / climate.py** — tote Proxy-/`_clock`-/`_dirty`-Referenzen ersetzt; `always_update=True`-Begründung korrigiert (degradierter Payload ist tick-identisch); Suggestion-Emission auf „default on / Opt-out" gedreht; Modul-Docstring verweist auf den Orchestrator; Hub: Purity-Überverkauf korrigiert, `_shared_resource_shadow` als zustandsbehaftet ausgewiesen; `async_setup`-Docstring nennt jetzt beide Services; Unload-Kommentar spiegelt die ehrliche Save-Fehler-Semantik; `PoiseClimate` bekam die fehlende Klassen-Docstring (Single-Setpoint-Entscheid, bewusst kein `TARGET_TEMPERATURE_RANGE`).
3. **ha/** — Executor: sechs Sequenzen, Drei-Site-Context-Matrix, `own_write_ctx_ids`, blocking=True-Inventar inkl. Hub; ForecastProvider: „ONE blocking call of the integration" → „only in the TICK path"; Orchestrator: F-TRACEIO-/F-SAVEPOINT-Invarianten in Gegenwartsform, offene F-SAFESEQ/F-CONTEXT als offen markiert, Reorder-Beweise auf heutige Feldnamen, Zähler entfernt; HealthReporter/Presenter/ha-__init__ ent-narrativiert.
4. **diagnostics/ + trace/** — Patch-Surface-Liste auf die real dispatchten drei Namen korrigiert (MPC/TPI/PI-Kernels sind KEINE Patch-Fläche — vorher ein Test-Fehlleiter); Besitzer-Namen (`TickOrchestrator._*` statt „the coordinator"); F-HUMSHADOW-Fehlermodell aktualisiert; Recorder: Drop-Warnung once-per-instance und Flush-Grenze (bereits übergebener Batch) dokumentiert.
5. **control/** — P0: „norm envelope"-Klemm-Behauptung an zwei Stellen auf die reale Safe-Envelope `[FROST_FLOOR_C, DEVICE_MAX_C]` korrigiert (die Norm-Hülle bindet das Schreibziel, nicht den Hold); tick_pipeline-Verweise auf verlagerte Blöcke; Fan-first-`mode_changed`-Konsequenz (ADR-0069 U5) dokumentiert; tick_resolve: 16 Review-Codes raus, `fan_only` in beide Enumerationen; override.py: `permanent`-Widerspruch, tote Wrapper als Pure-Suite-Einstieg + `manual_override_expired` als ADR-0042-Referenz ohne Live-Caller markiert; mpc 8x-Faktor, TPI-Ratio-Mathematik, doppelte Docstring entfernt; optimal_stop als Coast-Advisory + unverdrahtetes `residual_fraction` ausgewiesen, Margin-Richtung und fehlender q_occ-Term (konservative Richtung) dokumentiert; hdh 1/12-Annahme, RegulationQuality-Seed-Gate, outcome_scoring-Kennlinie.
6. **comfort/ + estimation/** — free_running-Scope gesplittet (widen=Shadow, `adaptive_cool_edge`=live); dual_setpoint-Duplikat ohne ADR-0061-Gate entfernt; norm_compliance als Referenzformulierung (kein Live-Caller); en16798: Formel statt „Eq. B.x", Band-Attribution ehrlich (nur Kat.-II-Paar quellen-verankert); seasonless-Physiknote korrigiert (Bias statt „loss term small"); fünf „charter Gx"-Danglinge und drei ADR-Fehlzuordnungen ersetzt; thermal_ekf: 12 Codes raus, Einheiten/Skalenkommentare für Bounds/Q/Anomalie-Gate, 0.3/0.7-Konfidenzvertrag; psychrometrics-ASHRAE-Stand nachgezogen; PMV: Kategorie-Intervalle `<=`, clo-Klemme dokumentarisch, dynamische-clo-Gültigkeit.
7. **Plattformen/const/config_flow** — Review-Codes und geschlossene Tuning-Runden-Narration raus; Einheiten (20 MiB, Power-Threshold-Einheitskonsistenz auch in hub_aggregate); Button-Kommentar auf ADR-0067 F2 korrigiert; repairs-Docstring (Options-Pfad statt „Reconfigure"); accuracy-Section-Lifecycle am `flatten_sections`-Aufruf dokumentiert.
8. **README / quality_scale / Paket-Docstrings** — 18 Sensoren inkl. `vent_advice`; Buttons + `poise.comfort_feedback`; „Aktive Behaglichkeit" (Opt-in, Tier-Gates) als Active-Bullet; Adopt-Reasons als Climate-Attribute; `schedule_active`-Auto-Discovery; `stable_offset`-Semantik + `stable_prev`-Zeile; 8-h-Cap der Schedule-Policy; Config-Tabelle um 9 fehlende Optionen ergänzt; Card-Option `abs_humidity_floors`; abgeschnittenes Datei-Ende repariert; quality_scale: beide Services, `entity-disabled-by-default` präzise auf done, Coverage-Hardcodes entfernt; sechs leere Paket-`__init__.py` mit Ein-Satz-Docstrings (HA-Konvention).

9. **Sanktionierte Mikro-Codeänderungen (alle test-verifiziert, verhaltensneutral):** (a) `const.DEFAULT_TARGET_C` entfernt — referenzlos (kein Code-, Test- oder Doc-Treffer); (b) `runtime/input_registry.py`: `TypeAlias`+`noqa: UP040` → `type`-Statement, da die dokumentierte Begründung („pure CI gate runs on 3.10") laut pyproject/CI (3.12/3.13) falsch war; (c) `pipeline.py`: unveränderte `_ = clock`-Zeile, nur Kommentar ersetzt.

## 5. Entfernte Kommentare

- ~70 nackte Review-/Finding-Codes außerhalb des Phase-9-Scopes (Sätze blieben, wo sie selbsttragend sind).
- Refactoring-Phasen-Narration („moved VERBATIM", „since phase 10", „(plan phase 1/3)", Micro-Reorder-Äquivalenzbeweis in diagnostics/trace.py, Baseline-Vergleiche in runtime/config.py).
- Verbatim-Duplikate von Methoden-Docstrings an Call-Sites (external_override 3×, humidity-Rolle, config_reconcile, PARALLEL_UPDATES-Begründung in Read-only-Plattformen).
- Incident-/Feldstudien-Anekdoten, deren Regel bereits im ADR steht (suggestion.py, const.py-Tuning-Runde, competitor-Audit-Prosa in diagnostics_data/pi/mpc).

## 6. Neu dokumentierte wichtige Zusammenhänge

- Der Verdichterschutz ist **live** (multi/lifecycle, tick_pipeline: Policy hier, Block-Entscheid im Orchestrator).
- Adoption klemmt in die **Safe-Envelope**, die Norm-Hülle bindet erst das Schreibziel (tick_pipeline + override.py).
- Drei getaggte Context-Sites (inkl. Fan-Write) und das vollständige blocking=True-Inventar — die Echo-Erkennungs-Grundlage.
- Patch-Surface exakt: nur `predict_peak_operative`/`shading_target_position`/`_lifecycle` laufen über Coordinator-Globals.
- `fan_write` als Nicht-Aktuierung im Commit-Vokabular; `guards_resolved`-vor-try (kein Retry-Sturm); Trace-Drop-Warnung once-per-instance; HDH-1/12-Annahme; RegulationQuality-Seed nur durch Warmup inert; Coast-down ohne q_occ → stop_now nie zu früh; Fail-toward-warmth-Präzedenz in arbitration.
- EN-16798-Bänder: ehrliche Quellen-Attribution (nur Kat.-II-Paar verankert, Rest Projekt-Extrapolation).

## 7. Nicht automatisch behobene Befunde

1. **BUG (P0, Code):** Der über den Fix-Flow gelernte `clo_offset` (repairs.py → `entry.options`) wird beim nächsten Options-Submit verworfen — `PoiseOptionsFlow.async_step_init` ersetzt `entity.options` vollständig durch die Sektions-Keys; `CONF_CLO_OFFSET` kommt in config_flow.py nicht vor. (Reconfigure-Pfad ist safe.) → separater Task-Chip angelegt; Fix + Regressionstest nötig.
2. **Herkunft unklar (P2):** Tuning-Konstanten ohne belegbare Quelle: `tpi._PROPORTIONAL_RATIO = 50`, `pi.k_ext = 1/25` (Wert), `cover_shading`-Defaults (deploy 1.5, pos_scale 40, …), `window_auto` (factor 1.8, floor 2, cap 12, max_slope 120), `outcome_scoring`-Kennlinien-Steigungen, `heating_failure` 35 min. Einheiten sind jetzt dokumentiert; die Herkunft (empirisch? Vendor? ADR-Absatz?) ist aus dem Repo nicht rekonstruierbar und wurde bewusst NICHT erfunden.
3. **ADR↔Code-Inkonsistenzen (P2, ADR-Seite):** ADR-0001 nennt den BT-Faktor „~9×", der Code implementiert exakt 8×; ADR-0051 zitiert für das EN-Adaptivband „gültig 10–33,5 °C" (das ist die ASHRAE-55-Spanne; Code: 10–30 per EN Annex B); ADR-0007 F13-Monotonic-Liste kennt `last_fan_cmd_ts` noch nicht.
4. **Möglicher Code-Smell (unklar, nicht angefasst):** `diagnostics/shadows.py` bindet `binding = "mold" if mold_min and …` — ein Floor von exakt 0.0 klassifiziert als `en16798`, auch wenn er über `heat_sp` läge. Ob 0.0 ein bewusstes Sentinel ist, ist nicht dokumentiert; kein Kommentar erfunden.
5. **Ungenutzte Reste (Entscheidung nötig):** `PersistencePhase.NONE` (jetzt als unbenutzt markiert), `override.manual_override_expired`/`manual_revert_h` (nur Test-Caller; als Referenz markiert), `running_mean.recent_days` (persistiert, von der Rekursion nie gelesen), `pmv._CLO_T_MIN`-Klemme (dokumentarisch). Entfernen wäre je ein kleiner Behavior-/Format-Eingriff.
6. **Test-Lücken zu dokumentierten Regeln (Hinweis):** die „6-8 K health rule"-Kennlinie (thermal_shock) und die 1/12-Savings-Annahme sind kommentiert, aber nicht als eigene Regel getestet; die README-Adoptionstabelle hat keinen Tabelle↔`SUPPRESSED_ADOPT_REASONS`-Sync-Test (das Enum-Register selbst ist gepinnt).
7. **README-Doku-Lücken (Gold-Regeln, unverändert todo):** docs-data-update, docs-supported-devices, docs-known-limitations, docs-troubleshooting, docs-use-cases, docs-examples — in quality_scale.yaml korrekt als todo geführt.
8. **Test-Docstring-Drift (nicht angefasst, Testdateien außerhalb des Änderungs-Scopes):** z. B. `tests/integration/test_phase6b_state_move.py:150` („coord._clock = fake") beschreibt den Swap, der im Body über `coord.runtime.clock` läuft; `tests/test_phase1_tick_result.py` trägt noch ein „(50 names…)"-Kommentar bei 53 gepinnten Feldern.

## 8. Validierung

| Gate | vorher (Baseline) | nachher |
| --- | --- | --- |
| ruff check | clean | clean |
| ruff format --check | 328 formatiert | 328 formatiert |
| mypy --strict (132 Dateien) | clean | clean |
| Pure-Suite | 1288 passed, Cov 98,71 % | 1288 passed, Cov 98,71 % |
| Integration (HA-Runtime, py3.13, pytest-homeassistant-custom-component) | — | 367 passed |
| JSON (manifest/hacs/strings/en/de) | valide | valide |
| Diff-Review | — | 96 Dateien, +903/−772; Code-Zeilen-Scan: nur die drei sanktionierten Änderungen |

Diff-Basis: lokales `git init` + Baseline-Commit (die Arbeitskopie war kein Git-Repo; `.git` kann gefahrlos gelöscht werden, `git blame`/Historie stand für §17 nicht zur Verfügung).

## 9. Gesamturteil

| Bereich | vorher | nachher |
| --- | ---: | ---: |
| Inline-Kommentare | 7/10 | 9/10 |
| Docstrings | 7/10 | 9/10 |
| Architekturverständlichkeit | 9/10 | 9/10 |
| Home-Assistant-Konformität | 8/10 | 9/10 |
| README / Entwicklerdoku | 7/10 | 8,5/10 |
| Wartbarkeit | 7/10 | 9/10 |

Begründung: Struktur und ADR-Kultur waren bereits exzellent (daher 9/10 Architektur unverändert); der Abzug „vorher" lag fast vollständig in der Phasendrift — einzelne Kommentare waren nicht nur redundant, sondern **falsch in gefährlicher Richtung** (Shadow-behauptet-aber-live, falsche Patch-Flächen, falsche Klemm-Hüllen). Nach der Bereinigung entspricht die Kommentarlage dem eigenen Phase-9-Standard repo-weit; verbleibende Lücken sind die unter §7 gelisteten Herkunftsfragen und die offenen Gold-Doku-Regeln.
