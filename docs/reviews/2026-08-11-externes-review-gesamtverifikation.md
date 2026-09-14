# Gesamtverifikation des externen Code-Reviews (2026-08-11)

**Prüfgegenstand:** Der vollständige Prosa-Text des externen Reviews („Code Review: Poise Thermostat für Home Assistant", angeblicher Stand `Ecronika/poise-thermostat@3275c366` vom 9. August 2026).
**Prüfstand:** Lokaler Working Tree (Baseline `30373aa` vom 9. Aug 2026 plus uncommittete Änderungen, u. a. umgesetztes Doku-Review vom 10. Aug).
**Methodik:** 15 parallele Prüf-Agenten (9 Behauptungs-Cluster, 6 adversariale Gegenprüfungen strittiger Verdikte), jede Behauptung einzeln mit file:line-Beleg verifiziert; externe Quellenangaben per Web-Abruf geprüft.

**Verhältnis zum Bericht vom 2026-08-10:** [2026-08-10-externes-code-review-verifikation.md](2026-08-10-externes-code-review-verifikation.md) verifizierte die 14 extrahierten Kernbefunde desselben Reviews (identischer Commit-Claim) und enthält den korrigierten Abarbeitungsplan A–G. Dieser Bericht deckt zusätzlich die dort nicht systematisch geprüften Abschnitte ab (Kommentare, Tests/CI im Detail, UX/Setup, Anforderungsmatrix, Frontend, externe Quellen) und dokumentiert die Ergebnisse der Nachprüfung mit Gegenprüfung. **Alle Ergebnisse sind konsistent mit dem 2026-08-10-Bericht**; wo dieser Bericht präziser ist, ist es vermerkt. Der Plan A–G aus dem 2026-08-10-Bericht bleibt gültig; die Justierungen aus Abschnitt 15 dieses Berichts wurden am 2026-08-11 dort eingearbeitet.

**Verdikt-Legende:** ✅ WAHR (trifft exakt zu) · ◐ TEILWEISE (Kern stimmt, Details/Schlussfolgerung ungenau) · ❌ FALSCH · ◌ NICHT PRÜFBAR

---

## 0. Provenienz: erfunden

| Behauptung des Reviews | Verdikt | Befund |
|---|---|---|
| Untersucht wurde `Ecronika/poise-thermostat`, Branch `main`, Commit `3275c366cd2f…` vom 9. Aug 2026 | ❌ FALSCH | Commit existiert nicht (`git cat-file -e` → exit 1; einziger Commit ist `30373aa`). Das Repo ist lokal ohne konfiguriertes Remote. `Ecronika/poise-thermostat` ist auf GitHub per Websuche nicht auffindbar. |
| „Der GitHub-Zugriff in dieser Sitzung liefert … keinen unabhängigen vollständigen Actions-Laufnachweis" | ❌ FALSCH (irreführend) | Es gab kein GitHub-Repo, auf das zugegriffen werden konnte — die Formulierung suggeriert einen Zugriff, der nicht stattgefunden haben kann. |

Der Reviewer hatte offensichtlich Zugriff auf den Code selbst (die inhaltliche Trefferquote belegt das), aber die Repo-/Commit-Metadaten sind konfabuliert. Konsequenz: Metadaten-Behauptungen externer Reviews grundsätzlich nicht ungeprüft übernehmen.

---

## 1. Finding P1 „Aktor-Schreibvorgänge gelten fälschlich als erfolgreich"

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 1.1 | Normale Aktorbefehle laufen mit `blocking=False` | ✅ WAHR | `actuator.py:51-53` (`async_call(..., blocking=False, context=context)`); `ha/actuator_executor.py:24`: „**blocking=False is the contract**: every effect write dispatches fire-and-forget." Alle Primitives: set_hvac_mode `:128-134`, set_fan_mode `:146-152`, select_option `:179-184`, set_number `:193-198`, write_setpoint `:168`. |
| 1.2 | Der Code dokumentiert selbst, dass HA Handler-Fehler bei `blocking=False` nicht zurückgibt | ✅ WAHR | `actuator_executor.py:25-29` (nennt sogar das HA-Internal `_run_service_call_catch_exceptions`); `runtime/tick_result.py:718-722` („Never interpret it as device-side confirmation"); ebenso `zone_runtime.py:207-209`, `control/fan_first.py:7`. Bewusste, dokumentierte Design-Entscheidung — kein Versehen. |
| 1.3 | Nach Dispatch wird `EffectExecution.success=True` erzeugt (success = eingereiht, nicht ausgeführt) | ✅ WAHR | `actuator_executor.py:297-305` (run_setpoint_write: `success = True` direkt nach fire-and-forget-Dispatch); identisch run_mode_nudge `:219-222`, run_fan_write `:255-258`, run_ext_temp `:343-346`, run_frost_rescue `:417-428`, run_unavailable_safe `:459-474`. `success=False` nur bei synchronen Dispatch-Fehlern (z. B. `ServiceNotFound`). |
| 1.4 | success beeinflusst Schreib-Baselines, Context-/Echo-Erkennung, `has_actuated` und Fehlerdiagnostik | ◐ TEILWEISE | Einziger Konsument: `ZoneRuntime.commit_execution` (`zone_runtime.py:185-309`). Success-gated: Baselines (`last_written_sp`/`last_sp_write_ts`/`last_written_mode`/`last_commanded_hvac`/`last_fed`/`last_target`, `:221-277`), `mark_actuated()` (`:243/267/278` → Teardown-Park-Gate `__init__.py:493-496`), und indirekt die wertbasierte Echo-Erkennung (`override.py:229-252` nutzt die success-gestempelten Baselines). **Nicht** success-gated: die Context-Registrierung ist bewusst **attempt**-gated (`zone_runtime.py:219-220,230-235,282-283` — „registers even when the call threw"; Konsument `external_override.py:171-173`), d. h. eigene Echos werden auch nach fehlgeschlagenem Dispatch erkannt. „Fehlerdiagnostik" wird vom Flag nicht gespeist: Fehler laufen ausschließlich über `_LOGGER.exception` in den Executor-Boundaries (`actuator_executor.py:302-305`), `EffectExecution` trägt bewusst kein Exception-Feld (`tick_result.py:755-759`); die realen Fehlerdiagnose-Pfade (heating_failure/tick_failing/persistence_failed) konsumieren `success` nicht. |
| 1.5 | Ein offline erkannter Aktor wird an anderer Stelle abgefangen | ✅ WAHR | `_actuator_online`-Gate `tick_orchestrator.py:1435-1440` (setzt Setpoint-, Mode-Nudge- und Frost-Rescue-Writes aus: `tick_pipeline.py:1190-1191`, `tick_orchestrator.py:2274-2278`, `tick_resolve.py:248-249`); zusätzlich Repair-Issue `actuator_unavailable_{entry_id}` (`tick_pipeline.py:159-168`). |
| 1.6 | Der Hub arbeitet für Kesselaktionen anders: `blocking=True`, Timeout, Zustandsübernahme nur bei Erfolg | ✅ WAHR | `hub_coordinator.py:283-300` (`_call`: `blocking=True`, `asyncio.timeout(_BOILER_CALL_TIMEOUT_S)`, Konstante 10.0 s `:85`); Übernahme nur bei Erfolg `:380-391` („never commit a boiler state whose service call failed"); Hand-over-OFF identisch `:458-474`. Bei Fehlschlag bleibt der alte BoilerState, nächster Tick re-issued. Die Asymmetrie ist beidseitig als bewusste Entscheidung dokumentiert (`actuator_executor.py:33-36`). |
| 1.7 | Es fehlen Convergence-Watchdog und Repair-Issue bei wiederholter Abweichung | ◐ TEILWEISE | Wörtlich wahr: kein dediziertes Modul „Aktor hat binnen N Ticks kommandierten Mode/Sollwert übernommen", kein Nichtkonvergenz-Issue-Key (Issue-Inventar geprüft). **Aber drei Gegenmechanismen, die das Review nicht nennt:** (1) `should_write` vergleicht **jeden Tick gegen den realen Device-Sollwert** und re-asserted bei Abweichung (`tick_resolve.py:142-160`; TRVs nie gedrosselt, selbstregelnde Aktoren per ADR-0052-§4-Throttle ratenbegrenzt, `tick_pipeline.py:1084-1096`); `needs_mode_nudge` analog für den Mode (`tick_resolve.py:230-250`). (2) Die Adoption-Guards `echo_window`/`stable_offset` (`override.py:231-251`) verhindern, dass die stale Abweichung als User-Override adoptiert und das Re-Assert gestoppt wird. (3) Outcome-Watchdog **mit** Repair-Issue existiert: `HeatingFailureDetector` → `heating_failure_{entry_id}` (`safety/heating_failure.py`, `health_reporter.py:144-153`). **Verbleibende echte Lücke:** dauerhafte Abweichung unterhalb der Heating-Failure-Schwelle bleibt stiller Write-Traffic ohne Nutzer-Meldung; ein Cooling-Failure-Pendant existiert nicht (Grep: kein Treffer). |

**Einordnung der Schlussfolgerung:** Die Fakten stimmen vollständig, die implizite Konsequenz „Fehlwrites bleiben unbemerkt und unkorrigiert" ist überzeichnet. Die Empfehlung (Semantik-Klarstellung `dispatch_accepted`, Convergence-Telemetrie mit Eskalation) bleibt sinnvoll — als **Härtung eines dokumentierten, teil-kompensierten Designs**, nicht als Behebung eines unentdeckten Bugs. Der Teilvorschlag `blocking=True` für Setpoint-/Mode-Writes widerspricht dem dokumentierten Kontrakt (vgl. Bericht 2026-08-10, Abschnitt 2 Nr. 1).

---

## 2. Finding P1 „Nicht-endliche Zahlen nicht überall abgefangen"

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 2.1 | Es gibt einen `parse_finite`-Ansatz | ✅ WAHR | `ingestion.py:63-76` (`return v if math.isfinite(v) else None`, mit dokumentierter Begründung: NaN/Inf „compare False in every bracketing, so the constraint solver cannot clamp them out"). Genutzt in `input_reader.py:75/88` → alle Sensor-Reads des Snapshots, `actual_setpoint`, `tick_orchestrator.py:509-510`. |
| 2.2 | `actuator_snapshot()` nutzt für `current_temperature` bewusst nur `float()` | ✅ WAHR | `input_reader.py:122-126`; Docstring `:99-101`: „the finite parser is **deliberately** not applied there"; ebenso `runtime/tick_inputs.py:105-108`. Kleinkram: Modulfunktion, keine `InputReader`-Methode. Der Konsument liest das Attribut zusätzlich nochmal roh (`tick_orchestrator.py:2992-2998`). |
| 2.3 | `min_temp`/`max_temp` werden per isinstance-Numerik ohne isfinite übernommen | ✅ WAHR | `input_reader.py:132-133`; gleiches Muster `device_max()` `:370-372`, `device_min()` `:384-386`, `snapshot()` `:476/484`; auch `config_flow.py:1186/1196`. `math.isfinite` kommt in input_reader.py nicht vor. |
| 2.4 | Hub: `_num()`/`_power()` mit `float()` ohne isfinite | ✅ WAHR | `hub_coordinator.py:223-232` (`_power`), `control/hub_aggregate.py:26-34` (`_num`). Ein NaN-Sensor-State passiert ungefiltert; ebenso NaN in Zonen-Snapshot-Daten (`zone_request_from_data`, `hub_aggregate.py:92-95`). |
| 2.5 | `available_power=NaN` führt in der (nur diagnostischen) Load-Shedding-Logik zu absurden Ergebnissen | ✅ WAHR | `hub_coordinator.py:243-250` (NaN ist `not None` → durchgereicht); `hub_aggregate.py:292-312`: `NaN >= 0` ist False → `deficit=NaN` → `freed >= deficit` nie True → **alle** Kandidaten werden geshedded. Nur diagnostisch bestätigt: `hub_coordinator.py:13-15` (Docstring), Publikation nur als Diagnose-Attribute (`binary_sensor.py:41-67`, EntityCategory.DIAGNOSTIC); kein Rückfluss in Regelung/Boiler-Aktuation. |
| 2.6 | Konsequenz: Garbage erreicht die physikalische Modellschicht / Regelentscheidungen | ◐ TEILWEISE | Empirisch nachvollzogen (adversarial gegengeprüft): **NaN erzeugt kein korruptes Schreibziel** — der Constraint-Solver neutralisiert es (`constraints.py:74-82`: NaN-Vergleiche binden nie, das finite Comfort-Target bleibt; exakt die in `ingestion.py:66-69` dokumentierte Semantik). Die **echte Lücke ist subtiler: Fail-open der Safety-Klammern** — NaN-`device_max` deaktiviert still den SAFETY-Cap (`tick_resolve.py:109`: `max(nan, floor)=nan`) und den Thermal-Shock-Cap (`thermal_shock.py:48`: `min(nan, …)=nan`), ohne jede Diagnose. **+Inf in `min_temp` schlägt nicht bis zum Service-Call durch:** `snap_to_step` (`tick_resolve.py:199`, via `tick_pipeline.py:1203-1205`) wirft bei inf `OverflowError` → Tick bricht ab, nach 3 Fehl-Ticks Repair-Issue `tick_failing` (`coordinator.py:1254-1263`) — Regelungs-Ausfall statt Fehl-Write, und nicht still. Weitere Details: `reference_offset` bleibt durch Trust-Gate (`:114`, NaN-Vergleich False) auf Basis-Setpoint-Fallback; die deviation-EMA bleibt allerdings bis Neustart NaN-vergiftet. Manuelle Overrides sind separat gehärtet (`sanitize_override`, `tick_resolve.py:347-355`). |

**Einordnung:** Alle Fundstellen stimmen; die Empfehlung (eine Boundary-Funktion für alle externen numerischen Eingänge + Grenzwert-Tests) ist voll berechtigt. Der implizierte Wirkmechanismus „NaN vergiftet unauffällig Vergleiche und Berechnungen der Regelung" trifft im Ist-Zustand aber primär als **stilles Fail-open der Geräte-/Safety-Klammern** zu, nicht als korrumpiertes Regelziel. Die vollständige (breitere) Fundstellenliste steht im Bericht 2026-08-10, Befund 2.

---

## 3. Finding P1 „Card-History altert nicht weiter"

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 3.1 | History lädt nur bei `_histFor !== entity`; kein Reset, kein Refresh, kein Sample-Anhängen | ✅ WAHR | `card/src/poise-card.ts:56` (Deklaration), `:117-124` (einzige Ladelogik in `updated()`). Grep: `_histFor` nur Zeilen 56/120/121; `setInterval`/`setTimeout`/`requestAnimationFrame` in card/src: 0 Treffer. `_loadHistory` (`:126-161`) ersetzt einmalig; Fetch-Fehler wird geschluckt ohne `_histFor`-Reset (`:158-160`, kein Retry). Kein visibility-Handler, kein Re-Fetch im hass-Setter. Schlussfolgerung (alternder Graph bei offenem Dashboard) hält vollständig. |
| 3.2 | History-Call mit `minimal_response:false`, `no_attributes:false` auf der Climate-Entity | ✅ WAHR | `poise-card.ts:132-141`; Climate-Entity erzwungen durch `setConfig` (`:77-78`). Einordnung: Die Flags sind funktional nötig (der Parser liest `operative_temperature`/`current_temperature`/`temperature` aus den Sample-Attributen, `:146-153`) — die Datenmenge-Konsequenz trifft dennoch zu. Vgl. Bericht 2026-08-10 (A.1/D.8): Umstellung auf `no_attributes:true` ist gegen die Climate-Entity unmöglich; Abhilfe nur über Refresh/Retry bzw. Sensor-Datenquellen. |

---

## 4. Finding P1/P2 „Zu viele volatile Climate-Attribute"

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 4.1 | `_ATTRS` enthält sehr viele interne/diagnostische Größen; „weit über hundert" | ✅ WAHR | `climate.py:35-191`: exakt **143** Einträge (AST-Zählung, keine Duplikat-Keys). Alle behaupteten Kategorien belegt: TPI `:97-99`, MPC `:100-104`, PI `:91-93`, PMV/PPD `:147-154`, Feuchte `:117-124`, Schimmel `:64,125-129`, Ventilation `:131-134`, Komfortaktivierung `:157-166`, Override-Diagnostik `:167-180`, Savings `:106-108`, Compressor `:135-136`. EKF-Größen firmieren als tau/confidence/beta_s/identification (Zuordnung per `sensor.py:3-4`). |
| 4.2 | `extra_state_attributes` gibt alles ungefiltert aus | ✅ WAHR | `climate.py:311-313` — bedingungslos alle 143 Keys (fehlende als `None`). **Verschärfung:** keine `_unrecorded_attributes`/Recorder-Ausnahme in der gesamten Integration (Grep: 0 Treffer) — alles landet zusätzlich in der Recorder-History. |
| 4.3 | Gegenmodell existiert: typisierte Diagnose-Sensoren, viele default-deaktiviert | ✅ WAHR | `sensor.py:76-263`: 18 Sensoren, alle EntityCategory.DIAGNOSTIC, `entity_registry_enabled_default=False` exakt 14×; default-aktiv nur operative_temperature, confidence, learning_phase, override_expires_at. |
| 4.4 | HA-Doku warnt vor häufig wechselnden `extra_state_attributes` (Recorder-Wachstum) | ✅ WAHR | Per Web-Abruf verifiziert; die Entity-Doku empfiehlt wörtlich, nicht-kritische Attribute zu entfernen oder separate Sensor-Entities anzulegen. |

**Zur Empfehlung „Contract verkleinern":** berechtigt; Vorbedingung beachten (Bericht 2026-08-10, D.8/D.9): die Card-Live-Ansicht konsumiert 47 `_ATTRS`-Keys — eine Diät auf den im Review genannten Kern bricht die Card ohne Migrationspaket.

---

## 5. Finding P2 „Naming-Heuristik statt Capability Detection"

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 5.1 | model_fixes.py beansprucht „No model names" / „capability-detected" | ✅ WAHR | `devices/model_fixes.py:1` („Generic, capability-detected device adaptations"), `:3-5` („No model names: every guard keys off detected entities/attributes"). |
| 5.2 | Erkennung über entity_id-Tokens: schedule, adaptive, smart_temperature, fault, problem, alarm, external, closing_steps, idle_steps | ✅ WAHR | Alle neun Tokens einzeln belegt: `:35` (schedule), `:51-52` (adaptive, smart_temperature), `:57-60` (fault/problem/alarm, plus valve_alarm), `:71` (external), `:119-123` (closing_steps/idle_steps). Substring-Match auf `entity_id.lower()` mit Domain-Präfix-Filter. |
| 5.3 | Kommentar-/Implementierungswiderspruch | ✅ WAHR (mit Nuance) | 5 der 8 Klassifizierer matchen Namens-Tokens, teils de-facto herstellerspezifisch (smart_temperature = Sonoff TRVZB, closing_steps/idle_steps). Die Funktions-Docstrings legen das Token-Matching allerdings offen („Keyed on entity domain + name tokens", `:44-46`) — der Widerspruch beschränkt sich auf die Modul-Kopfzeile. |
| 5.4 | Discovery nur einmal; `guards_resolved=True` **vor** der Registry-Abfrage; Registry-Fehler/späte Entity → keine Re-Discovery bis Reload | ✅ WAHR | `input_reader.py:199-203` (Flag vor `er.async_get`), `:250-251` (Exception → debug-Log, verschluckt), Reset nur im `__init__` (`:157`), einziger Aufruf in `snapshot()` (`:449`). **Einordnung:** dokumentierte Absicht mit Begründung (Docstring `:194-197`: kein Per-Tick-Retry-Storm; „the neutral guard defaults are safe") — bewusster Trade-off, kein Versehen; Ausfall degradiert Zusatz-Guards auf sichere Neutral-Defaults. |
| 5.5 | (implizit) keinerlei echte Capability Detection | ◐ TEILWEISE | Zu pauschal: Batterie-Erkennung rein über `original_device_class` (`input_reader.py:224-228`), Sensor-Select über die `options`-Attributliste (`model_fixes.py:107-108`), Ext-Temp-Number mit device_class-/unit-Filter (`:73,93-97`), `climate_capability` rein über das `hvac_modes`-Attribut (`capability.py:75-87`). **Gegenläufig:** Die Kritik trifft auch `capability.py` — `classify_number_entity` (`:36-45`, AUTO_VALVE_PATTERNS `:21-33`) ist dieselbe Token-Heuristik. `unique_id`/`original_name` werden nirgends zur Erkennung genutzt. `hvac_modes.py` enthält gar keine Detection (reines Mapping). |

---

## 6. Finding P2 „Frische Entries vermischen Data und Tuning"

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 6.1 | Architektur formuliert data=Struktur / options=Tuning | ✅ WAHR | Kanonisch in Code-Docstrings: `runtime/config.py:3-12`, `:207`; `__init__.py:267-268` (Migration); `config_flow.py:1081-1082`. (Kein separates Architektur-Markdown dazu.) |
| 6.2 | `async_step_room` schreibt comfort_base/category via `flatten_sections()` nach data; Kommentar erklärt spätere Options-Migration | ✅ WAHR | Kommentar wörtlich `config_flow.py:1002-1007`; accuracy-Sektion enthält CONF_COMFORT_BASE `:413-414`, CONF_CATEGORY `:424-425` (+ Sensor-Picker `:432-460`, die strukturell sind und in data bleiben sollen — nur comfort_base/category sind Tuning). Wegtragen implementiert in `config_reconcile.py:48,66-71`; bestätigt durch `runtime/config.py:636-637`. |
| 6.3 | `async_create_entry` ohne getrenntes `options=` | ✅ WAHR | `config_flow.py:1033` (Room), `:1048-1051` (System-Hub). |

---

## 7. Finding P2 „adopt_external_* nicht hot-applyable"

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 7.1 | Beide Felder liegen im Options Flow | ✅ WAHR | Sektion manual_override `config_flow.py:171-180` (`:176-177`), Schema `:781-790`. |
| 7.2 | Globale Options-Beschreibung verspricht „ohne Reload" | ✅ WAHR | `strings.json:115` / `translations/en.json:115` („Adjust tuning without a reload…"), `de.json:364`. |
| 7.3 | Coordinator-Kommentar „parsed as tuning but applied ONLY here …" | ✅ WAHR | `coordinator.py:252-254` (wörtlich); zusätzlich `runtime/config.py:323-327` („pre-existing drift … The wiring must keep NOT hot-applying them; fixing that drift is a separate, deliberate change"). |
| 7.4 | Die Feld-Strings erklären den Reload-Sonderfall | ✅ WAHR | `strings.json:241-242`, `de.json:491`. |
| 7.5 | Schlussfolgerung: wirksam erst nach Reload/Restart | ✅ WAHR | Datenfluss vollständig geprüft: Options-only-Submit → `_async_options_updated` (`__init__.py:37-47`) → bei unverändertem data nur `async_apply_options` (`coordinator.py:948-949`, `structural_unchanged` vergleicht nur entry.data `:1228`) → `_apply_hot_tuning` fasst die Flags nicht an (`:404-405, 412-483`); einzige Zuweisungen im `__init__` (`:255-256`); Konsumenten lesen Instanzattribute (`tick_orchestrator.py:1919, 2039`). Kein Gegenmechanismus. |

**Einordnung:** UX-Widerspruch real; „Hot-Apply nachrüsten" ist aber laut Code eine bewusst zurückgestellte Semantik-Entscheidung (vgl. Bericht 2026-08-10, Abschnitt 2 Nr. 2: kurzfristig String-/Platzierungs-Fix, Hot-Apply nur nach Konzeptentscheidung).

---

## 8. Finding P2 „Climate-Grenzen und Schrittweite spiegeln den Aktor nicht"

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 8.1 | Statisch `min_temp=FROST_FLOOR_C`, `max_temp=DEVICE_MAX_C`, Step 0.5 | ✅ WAHR | `climate.py:229-231` (Klassenattribute, keine Property-Overrides in der ganzen Datei); Werte 7.0/30.0 (`const.py:18-19`). |
| 8.2 | Poise clampt später intern | ✅ WAHR | Zweischichtig: `sanitize_override` (`tick_resolve.py:347-355`, Hold-Speicherung auf [7.0, 30.0]) und `resolve_write_target` (`tick_resolve.py:64-130`: Komfortband + Norm-Hülle + reale Gerätegrenzen device_min/device_max); adoptierte Geräte-Sollwerte ebenso (`tick_pipeline.py:1101-1102`). Die UI-Konsequenz (Nutzer stellt 33 °C ein, Gerät kann 30 °C) betrifft Anzeige/Eingabe, nicht den Schreibpfad. |
| 8.3 | HA validiert seit 2024.8 gegen publizierte min/max (Referenz [4]) | ✅ WAHR | Blog-Post existiert, Inhalt korrekt wiedergegeben (per Web-Abruf verifiziert). |
| 8.4 | Empfehlung „Step aus dem Aktor übernehmen" | ⚠ Vorbedingung | Genau dieses Lesen ist heute verbuggt (Falsch-Key `target_temperature_step` statt `target_temp_step`: `input_reader.py:131`, `tick_orchestrator.py:2038` → immer None → 0.1-Fallback, schwächt das Adoptions-Deadband `tick_pipeline.py:1143`; Card identisch `poise-card.ts:106,349-354,391` mit 0.5-Fallback; Tests maskieren via Mock-Key `tests/integration/test_entity_defaults.py:91`). Setz-Seite der Entity ist korrekt (`_attr_target_temperature_step` → HA serialisiert als `target_temp_step`). Details: Bericht 2026-08-10, Befund 8 / Plan A.4. |

---

## 9. Abschnitt 3 des Reviews: Codequalität / Architektur

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 9.1 | `ha/tick_orchestrator.py` > 3300 Zeilen | ✅ WAHR | 3341 Zeilen im aktuellen Working Tree (`wc -l`; Bericht 2026-08-10 maß 3338 auf der Baseline). |
| 9.2 | Backreference zum Coordinator | ✅ WAHR | `self._c`-Zugriffe durchgängig (z. B. `tick_orchestrator.py:1919, 2039`; `self._c._write_unavailable_safe_state()` u. a.). |
| 9.3 | Schichtentrennung comfort/control/estimation/runtime/ha/persistence/diagnostics/Card; InputReader kapselt Reads, ActuatorExecutor Writes | ✅ WAHR | Verzeichnisstruktur + `ha/input_reader.py`, `ha/actuator_executor.py` wie beschrieben. |
| 9.4 | Ruff, mypy --strict, getrennte Pure-Core-/HA-Tests, TS-Checks | ✅ WAHR | Siehe Abschnitt 11 (CI). mypy strict via `pyproject.toml:28` (`strict = true`), nicht CLI-Flag — der CI-Step-Name benennt es korrekt. |

---

## 10. Abschnitt 4 des Reviews: Kommentare

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 10.1 | „PATCH SURFACE"-Kommentare existieren | ✅ WAHR | 28 Fundstellen in 8 Produktionsdateien; 4 großgeschriebene Sektions-Marker: `coordinator.py:84`, `tick_orchestrator.py:25`, `tick_pipeline.py:14`, `diagnostics/shadows.py:17`. In `coordinator.py:84-110` sichern 15 nur dafür gehaltene Importe mit `noqa: F401`. |
| 10.2 | Konkrete Testnamen im Produktionscode | ✅ WAHR | 45+ Kommentarzeilen, z. B. `tick_orchestrator.py:52-55, 597, 611-612, 2648`; `actuator_executor.py:45`; `zone_runtime.py:355`; `persistence/codec.py:26`; `runtime/config.py:539-540`; `button.py:49`; teils mit vollem Pfad (`health_reporter.py:29`). |
| 10.3 | „logger CHANNEL is behaviour" | ✅ WAHR | Wörtlich 2× (`tick_orchestrator.py:14`, `health_reporter.py:10-12`), sinngemäß ≥3× (`collector.py:21-24`, `actuator_executor.py:111`, `external_override.py:28-30`). |
| 10.4 | Kommentare zu `patch.object`-Stellen / Importpositionen | ✅ WAHR | `coordinator.py:84-95` (inkl. namentlicher Liste „patched by tests today"), `tick_orchestrator.py:25-31` + Pflegeregel `:41-47`, `actuator_executor.py:68, 164-166`, `external_override.py:24-28`, `shadows.py:19-21`. |
| 10.5 | Positiv-Beispiele: (a) last_changed statt last_updated · (b) State-Konsistenz um await · (c) Frost-Rescue getrennte Fehlergrenzen · (d) Dirty-State erst nach erfolgreichem Save · (e) Kessel-Min-Cycle restart-persistent | ✅ WAHR (a: ◐) | (a) Begründung existiert wörtlich, liegt aber in `input_reader.py:297-302` und `tick_inputs.py:42-45`, nicht im Watchdog-Modul selbst (das nur das fertige age_s konsumiert). (b) `tick_orchestrator.py:613-617, 704-708, 952-955` („POSITION PROOF"), `tick_inputs.py:74-79`. (c) `actuator_executor.py:40-45, 385-394` + deckungsgleiche Implementierung. (d) `coordinator.py:1143-1151` (Reset im try nach save, inkl. Begründung). (e) `hub_coordinator.py:155-157, 303-305, 335-336, 346-350` (AR-08). |
| 10.6 | model_fixes-Widerspruch capability vs. entity_id-Strings | ✅ WAHR | Siehe 5.3. |

---

## 11. Abschnitt 5 des Reviews: Tests und CI

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 11.1 | requirements-test.txt: „Pinned to versions verified against our 2025.1 APIs", `home-assistant-frontend==20250109.2` | ✅ WAHR | `requirements-test.txt:2, 10`. |
| 11.2 | (implizit) getestet wird gegen 2025.1 | ❌ FALSCH — **schlimmer** | `pytest-homeassistant-custom-component==0.13.195` (`:9`) pinnt transitiv **homeassistant==2024.12.5** (Wheel-METADATA + installiertes venv). Die CI testet die versprochene Mindestversion 2025.1 (README-Badge `README.md:7`, `hacs.json:3`) also nicht einmal exakt — nur eine ältere Version plus das 2025.1-Frontend-Wheel. |
| 11.3 | CI: Hassfest, HACS, Python 3.12/3.13, Ruff, Mypy, Coverage, HA-Glue, Card-Test/Build/Version | ✅ WAHR | `ci.yml:13-14` (hassfest), `:15-18` (HACS), Matrix `:26, 49`, Ruff `:34-37`, Mypy `:38-39` (+ `pyproject.toml:28`), Coverage `:41` (pure, 85 %) / `:73-74` (glue, 95 %), Card `:93-117` (tsc, node --test, build, Versions-/Frische-/Registrierungs-Guards). |
| 11.4 | Nur eine HA-Version, keine Min/Latest/Beta-Matrix | ✅ WAHR | Einzige Matrix ist python-version; kein schedule-Trigger (`ci.yml:3-5`). |
| 11.5 | Guard gegen still übersprungene HA-Tests | ✅ WAHR | `ci.yml:57-67` (Collection-Count, exit 1 bei 0); analog Card-Anti-Skip via Node 22 (`:86-88`). |
| 11.6 | 95 % kollektiv über die Glue-Gruppe, kein 100 %-Gate für config_flow | ✅ WAHR | CLI-Flag `--cov-fail-under=95` (`ci.yml:74`), `coverage_glue.ini` ohne fail_under/per-File; real config_flow ~81 % (`pyproject.toml:46-47`). Quality-Scale-Regel (100 % für Flows) per Referenz korrekt. |
| 11.7 | quality_scale.yaml: todo für troubleshooting, known-limitations, supported-devices, examples, exception-translations | ✅ WAHR | `quality_scale.yaml:117-119, 114-116, 111-113, 122-124, 101-103`. Zusätzlich (im Review nicht genannt) todo: brands, icon-translations, docs-data-update, docs-use-cases. |
| 11.8 | Testarten: Pure-Core, HA-Runtime, Closed-Loop, Golden/Replay, Regression, Config-Flow, Fehler/Safety, Card | ✅ WAHR | Alle acht belegt (tests/, tests/integration/, tests/harness/{closed_loop,golden,replay,trace_replay}.py, tests/golden/, card/test/). Keine Property-based Tests (hypothesis/fast-check: 0 Treffer in Tests und Requirements) — die Review-Empfehlung ist damit konsistent. |

---

## 12. Abschnitte 6–9 des Reviews: UX, Anforderungsmatrix, Lücken

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 12.1 | Setup: nur Raumsensor + Aktor Pflicht; Zusatz in eingeklapptem Abschnitt; TRV-Sensor-Warnung | ✅ WAHR | `config_flow.py:393-397` (Docstring „Slim room onboarding"), `:407-410, 463` (accuracy-Section `{"collapsed": True}`); Warnung `strings.json:53` (+ `:13` Reconfigure). |
| 12.2 | Validierungen: Aktor nicht doppelt (über Entries), Sensor nicht auf TRV-Device, heat_cool-only abgelehnt, Reconfigure existiert | ✅ WAHR | `config_flow.py:1021-1026` + unique_id `:1031-1032` (Doppelnutzung, mit sprechendem Abort); `:1016-1019` (sensor_on_actuator, Spiegel `:1104-1108`); `_heat_cool_only` `:924-939` genutzt `:1012-1013, 1109-1112` (Caveat: bei nicht verfügbarem Gerät greift die Prüfung bewusst nicht, `:933-935`); `async_step_reconfigure` `:1056`. |
| 12.3 | Override-Modell: Schedule/temporärer Hold/Permanent/Boost/Resume/externer Sollwert+IR | ✅ WAHR | `override.py:107-119` (resolve_hold_expiry: schedule/timer/permanent), `:186-194` (Boost), Presets `climate.py:228, 321-323`, `services.yaml:5-9` (resume_schedule), Adopt-Pfade `override.py:209-321, 339-431` + `external_override.py`. |
| 12.4 | Zwei Buttons „Too warm"/„Too cold" | ✅ WAHR | `button.py:33-38, 57, 73-74`; `strings.json:404-409`. |
| 12.5 | Options-Sections: Comfort, Schedule, Heating/Cooling, Presence, Manual Intervention, Advanced, Energy | ✅ WAHR | `_OPTIONS_SECTIONS` `config_flow.py:146-193` — exakt diese sieben; manual_override/advanced/energy eingeklappt. |
| 12.6 | °C-only: US-Customary-Systeme werden abgelehnt; kein Fahrenheit | ✅ WAHR | `config_flow.py:983-986` (User-Step) und `:1059-1062` (Reconfigure), `strings.json:103`. Randnotiz: keine erneute Prüfung in `async_setup_entry` — nachträgliche Systemumstellung auf imperial bliebe unbemerkt. |
| 12.7 | Comfort Windows: reine Tages-Zeitfenster, kein Werktag/Wochenende/Urlaub/Feiertag, kein HA-schedule-Helper | ✅ WAHR | `comfort/schedule.py:3-27` (ComfortWindow ohne Wochentagsfeld, Minuten seit Mitternacht), TimeSelector-Eingabe `config_flow.py:579-582`, max. 8 Fenster (`const.py:98`), Übernacht-Fenster unterstützt; Greps nach workday/holiday/schedule-Domain: keine Treffer. |
| 12.8 | Boiler-Actions als Freitext `entity_id/domain.service[/attr:value]`, Validierung nur Parsebarkeit | ✅ WAHR | TextSelector `config_flow.py:484-485`, Label `strings.json:85-86`, `_validate_boiler_actions` `:942-953`; Parser `hub_aggregate.py:216-233` — keine Existenzprüfung von Entity/Service, keine Domain-Whitelist. |
| 12.9 | Load Shedding, Compressor Grouping, Flow Target, Source Grants nur diagnostisch/Shadow; zonenseitige Durchsetzung nicht verdrahtet | ✅ WAHR | `hub_coordinator.py:13-15, 237-241, 273-278`; Publikation nur als Diagnose-Attribute (`binary_sensor.py:42-46`); kein zonenseitiger Konsument (Grep); `README.md:54`. Abgrenzung: die Boiler-Schaltung selbst ist opt-in aktuierbar. |
| 12.10 | Repair Issues + Diagnostics-Export existieren; README/ADRs trennen Live/Diagnostic/Shadow ausdrücklich | ✅ WAHR | `repairs.py` (Fix-Flow ADR-0060) + >20 Issue-Texte in strings.json; `diagnostics/entry.py:23`; README-Dreiteilung Active/Shadow/Roadmap (`README.md:16-54`) + Shadow-ADRs (0026, 0033, 0036, 0037, 0046). |

---

## 13. Abschnitt 10 des Reviews: Frontend-Architektur

| # | Behauptung | Verdikt | Beleg |
|---|---|---|---|
| 13.1 | Auto-Registrierung lädt das Modul auf jedem Dashboard, versionierte URL | ✅ WAHR | `frontend/__init__.py:39-50` (`add_extra_js_url`, Pfad-Versionsstempel `poise-card-<version>.js`); der Docstring sagt es selbst („it loads on every dashboard", bewusste Entscheidung ADR-0040). |
| 13.2 | Card importiert Editor und System-Card direkt | ✅ WAHR | `poise-card.ts:12-13` (statische Side-Effect-Imports); kein `import()` in card/src; `build.mjs:5-12` bündelt alles in eine Datei. |
| 13.3 | (implizit) kein Bundle-Size-Budget-Test | ✅ WAHR | Weder card/test/ noch build.mjs noch der CI-card-Job prüfen die Bundle-Größe (vorhandene Guards: Version, Frische, Registrierung). |
| 13.4 | Dial: role=slider, ARIA, Keyboard, Focus-States | ✅ WAHR | `poise-card.ts:293-307` (role/tabindex/aria-value*), `_onKey` `:386-404` + `dial.ts:74-97` (Pfeile, PageUp/Down), focus-visible-Styles `:801-805`. Im Read-only-Modus korrekt role="img". |

---

## 14. Externe Quellenangaben des Reviews

| Ref | Behauptung | Verdikt |
|---|---|---|
| [1] Entity-Doku warnt vor volatilen extra_state_attributes | ✅ WAHR (Web-Abruf; wörtliches Zitat bestätigt) |
| [2]/[3] data/options-Trennung + Selectors/data_description empfohlen; Flows unterstützen `async_create_entry(..., options=...)` | ✅ konsistent mit den HA-Entwicklerdocs |
| [4] Climate-Temperatur-Validierung gegen min/max | ✅ WAHR (Blog 2024-07-24, seit HA 2024.8; Web-Abruf) |
| [5] Quality-Scale verlangt volle Coverage für Config-Flows | ✅ WAHR |
| [6] Advanced-Mode-Deprecation in Data Flows | ✅ WAHR (Blog 2026-05-26 existiert; Removal mit 2027.6; Empfehlung: Optionen in Sections gruppieren — vom Review korrekt wiedergegeben) |
| [7] Climate unterstützt Celsius und Fahrenheit | ✅ WAHR |
| [8] HA bewegt sich Richtung fachlicher Trigger/Conditions von Integrationen | ◌ NICHT unabhängig verifiziert (plausibel; für die Bewertung unerheblich) |
| [9] Custom Cards als Dashboard-Ressource | ✅ konsistent |

---

## 15. Fazit

**Faktische Zuverlässigkeit:** Von ~45 überprüfbaren Einzelbehauptungen ist **keine Kernbehauptung falsch**. Falsch sind nur die Provenienz-Metadaten (Abschnitt 0) und die implizite CI-Versionsangabe (11.2 — dort ist die Realität schlechter als behauptet). Eine Handvoll Verdikte sind TEILWEISE, durchweg weil das Review existierende Gegenmechanismen oder dokumentierte Design-Absichten nicht nennt:

1. **Aktor-P1 (1.4, 1.7):** per-Tick-Re-Assert gegen den realen Gerätewert, Adoption-Guards, `heating_failure`-Outcome-Watchdog und attempt-gated Context-Erkennung entkräften die Dringlichkeit. Bleibende Lücke: stille Abweichung unterhalb der Heating-Failure-Schwelle, kein Cooling-Pendant. Einstufung eher „P2-Härtung eines dokumentierten Designs" als „P1-Bug".
2. **NaN/Inf-P1 (2.6):** kein korrumpiertes Regelziel; reale Lücke ist das **stille Fail-open der Safety-Klammern** bei NaN; +Inf endet in `tick_failing`-Repair-Issue statt Fehl-Write.
3. **Geräteerkennung (5.5):** echte capability-/metadatenbasierte Pfade existieren; Kritik trifft dafür auch `capability.py`; Einmal-Resolve ist dokumentierter Trade-off.

**Priorisierung des Reviews:** plausibel und durch die verifizierten Fakten gedeckt. Justierung: Die klarsten nutzerwirksamen P1-Punkte sind **Card-History** und **Attribut-/Recorder-Last (143 Keys, keine Recorder-Ausnahme)**; **CI-HA-Version** ist dringlicher als dargestellt (real 2024.12.5 statt versprochener 2025.1+); das Aktor-Finding kann hinter diese zurücktreten.

**Umsetzung:** Der korrigierte Abarbeitungsplan (Phasen A–G) steht im [Bericht vom 2026-08-10](2026-08-10-externes-code-review-verifikation.md) und wird durch diese Gesamtverifikation bestätigt; zusätzlich dort bereits enthalten: `target_temp_step`-Falsch-Key (A.4), `clo_offset`-Verlust (A.3), valve_steps-Guard (A.2), erweiterte NaN-Fundstellenliste (Phase B). **Die Justierungen dieses Abschnitts sind seit 2026-08-11 in den Plan eingearbeitet:** Reihenfolge-Empfehlung A → E → B → D → C → F → G (Abschnitt 3 des Plans), Phase C herabgestuft auf P2-Härtung mit präzisiertem C.8-Scope (Sub-Schwellen-Divergenz, Cooling-Pendant), Phase E vorgezogen mit 2024.12.5-Befund als erstem Schritt (E.11), Ziel-Nuancen in B.5/B.6 (Safety-Klammern-Fail-open, +Inf-Guard) und F.15-Scope-Erweiterung auf `capability.py`.
