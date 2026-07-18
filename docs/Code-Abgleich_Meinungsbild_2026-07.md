# Code-Abgleich: IST-Zustand Poise vs. Anforderungen aus dem Meinungsbild (Stand 2026-07-17, v0.174.0)

**Zweck:** Ehrlicher Abgleich des realen Code-Zustands von Poise gegen die Anforderungen und Wettbewerber-Fehlerklassen aus dem [`Meinungsbild_Wettbewerber_Nutzerfeedback_2026-07.md`](Meinungsbild_Wettbewerber_Nutzerfeedback_2026-07.md). Der Bericht listet auf, was **nachweislich gelöst** ist (mit Code-Beleg), was **teilweise** gelöst ist und welche **Restrisiken/Probleme** noch offen sind — jeweils mit Code-Stellen und konkreten Verbesserungsvorschlägen.

**Methodik:** Vier unabhängige Read-only-Code-Audits entlang der 12 Meinungsbild-Achsen (A1/A2 Kalibrierung+Ventil, A3/A4 Lernen+Optimal-Start, A5/A6/A9/A10 Fenster+Override+Komfort+Feuchte, A7/A11/A12 Hub+Onboarding+Robustheit) über `custom_components/poise/` (~16 000 Zeilen), `card/` und `tests/` (996 Testfunktionen; CI-Coverage-Gates 85 % pure / 95 % Glue, `.github/workflows/ci.yml:41,74`). Bewertungsskala: **GELÖST** (Code + Test belegt) · **TEILWEISE** (Lücke benannt) · **OFFEN** (nicht implementiert). „Shadow by design" (prädiktiver Kern rechnet, schreibt nicht — ADR-0026/0033) wird nicht als Mangel gewertet, wohl aber fehlende Vorbereitung auf den Live-Flip.

---

## 1. Management-Summary

**Gesamturteil:** Poise ist gegen die Mehrheit der im Meinungsbild dokumentierten Wettbewerber-Fehlerklassen nachweislich und getestet gebaut. Die reifsten Achsen sind **Override-Lebenszyklus**, **Write-Throttle/Funkbudget**, **Persistenz/Restart** und die **Fenster-Reaktion** (Restore-Klasse per Architektur eliminiert). Die ehrlichen Lücken konzentrieren sich auf vier Punkte mit hoher Priorität:

1. **TRVZB-Adaptive-Mode (FW 1.4.4) ist komplett unerkannt** — die im Meinungsbild als Risiko Nr. 1 benannte Interferenz zweier Regler auf einem Ventil hat weder Erkennung noch Repair-Issue noch Test (OFFEN).
2. **Diagnostics-Redaktion lässt `presence_home`/`occupancy_sensor` ungeschwärzt** — die einzige Stelle, an der Poise eine kritisierte Wettbewerber-Fehlerklasse (RoomMind: Personen-IDs im Dump) **selbst reproduziert**. Fix ist zweizeilig.
3. **Die „Kessel-aus"-Lernkorruptions-Klasse (VTherm #1428) ist nur halb geschlossen:** Poise *erkennt* Heizausfall, hält ihn aber **nicht vom EKF-Lernen fern**.
4. **Setpoint-Adoption ist nicht fenster-gegated:** ein TRV-eigener 7-°C-Frost-Drop kann als Phantom-„manual"-Hold adoptiert werden (Raum friert nicht — Band-Klemme greift — aber der Hold ist falsch).

Dazu kommen vorbereitende Lücken vor dem TPI-Live-Flip (Ventil-Kennlinie, Kalibrier-Bereichslimits, Gate-Regressionstest) und ein Doku/Code-Drift (README verspricht `savings_*`-Attribute, die nicht publiziert werden).

**Status je Meinungsbild-Achse:**

| Achse | Status | Kurzbefund |
|---|---|---|
| A1 Kalibrierung/ext. Sensor | **GELÖST**, Kalibrier-Pfad-Fallback OFFEN | external-temperature-Push live mit Keep-alive + Vetting; PI-Kompensator + Referenzrahmen-Offset bewusst Shadow |
| A2 Ventilsteuerung/TPI | **Shadow wie designt**, Live-Flip-Vorbereitung TEILWEISE | Gate strukturell sauber; Kennlinie/min-opening/Read-back/Adaptive-Mode-Guard fehlen |
| A3 Lernen | **GELÖST** bis auf Kessel-aus-Rückkopplung | Echo-, Festfahr-, Maskierungs-, Persistenz-Klassen getestet geschlossen |
| A4 Optimal Start/Absenkung | **GELÖST**, FBH-Kopplung TEILWEISE | Exponential-Inversion + Forecast + identified-Gate; Dynamikprofil fließt nicht in Preheat/Setback |
| A5 Fenster | **GELÖST**, 2 Testlücken | Restore-Klasse architektonisch eliminiert; AC-Kühl-Gate ungetestet |
| A6 Overrides | **GELÖST** | reifste Achse; VTherm-#1900-Klasse strukturell ausgeschlossen |
| A7 Mehrzonen/Kessel | **GELÖST** | „quorum of one" strukturell ausgeschlossen; symmetrischer Keep-alive |
| A8 MPC/Prädiktion | **Shadow wie designt** | Transparenz (mpc_*-Diagnose, Shadow-Pill) vorhanden |
| A9 Komfortband/Presets | **GELÖST** | Norm-Klemmen unumgehbar via Präzedenz-Solver |
| A10 Feuchte/Kühlen | **GELÖST**, Dry-Latch-Persistenz TEILWEISE | Taupunkt-Guard, 60/55-Hysterese, ADR-0061 live |
| A11 UI/Onboarding | **GELÖST**, 1 Transparenzlücke | 2 Pflichtfragen; Adopt-Ablehnungsgründe nur im DEBUG-Log |
| A12 Zuverlässigkeit | **GELÖST**, Diagnostics-Redaktion TEILWEISE | Write-Throttle & Restart-Robustheit am gründlichsten abgedeckte Klassen |

---

## 2. Nachweislich gelöst (mit Code-Beleg)

Die folgenden Meinungsbild-Anforderungen sind im Code umgesetzt **und** durch Regressionstests abgedeckt:

| Anforderung (Fehlerklasse des Feldes) | Umsetzung | Beleg | Tests |
|---|---|---|---|
| **Funkbudget schonen** (HmIP-Duty-Cycle durch BT-Dauer-Writes) | Change-aware Write-Gate gegen den *gemeldeten* Geräte-Sollwert, Snap auf Geräte-Step, 0,2-K-Deadband; Regulation-Throttle für self-regulating Geräte; External-Feed nur bei ≥ 0,1 K Delta oder 600-s-Keep-alive | `control/tick_resolve.py:142-199`, `const.py:28,34`, `control/dynamics.py:125-141`, `coordinator.py:2914-2943, 3090-3095` | `test_tick_resolve.py` (u. a. Coarse-TRV-Rewrite-Schleife), `integration/test_regulation_throttle.py`, `test_actuator_unavailable_write_storm.py` |
| **Externer Sensor als Führungsgröße** (Kernversprechen des Feldes) | Live external-temperature-Push mit Auto-Erkennung, Sensor-Select-Management („external" re-assertieren), Keep-alive gegen stillen TRV-Fallback, Plausibilitäts-Vetting + Repair | `coordinator.py:3124-3173, 1280-1339`, `devices/model_fixes.py:42-52`, `tick_resolve.py:163-186` | `integration/test_external_feed_keepalive.py` |
| **Echo-/Eigenschreiber-Klasse** (BT „Sollwert ändert sich von selbst", RoomMind #241) | HA-Context-Tagging jedes eigenen Writes (Deque 16) + Wert/Zeit-Fallback mit Deadband-Echo, 120-s-Fenster, Drei-Werte-Regel; Baselines restart-persistent | `coordinator.py:1635-1645, 2743-2749, 3115`, `control/override.py:208-306`, `storage.py:36-45` | `test_adopt.py` (15), `test_adopt_mode.py` (13), `integration/test_adopt_baseline_restore.py` |
| **Festgefahrene-Parameter-Klasse** (RoomMind #301) | Bounds, α-Drift-Dämpfung, Joseph-Form + PSD-Enforcement, 4σ-Soft-Reject, Laufzeit- und Lade-Recovery bei gepegtem α | `estimation/thermal_ekf.py:47-50, 182-222, 240-269, 409-420` | `test_thermal_ekf.py` (Recovery-, PSD-, Bounds-, Outlier-Tests) |
| **Lern-Maskierung** (Fenster/frozen/Default-Werte) | `should_learn`-Gate + Anker-Drop nach Pause (kontaminiertes dt wird nie integriert), nur MEASURED lehrt | `safety/sensor_watchdog.py:92-99`, `coordinator.py:2123-2150` | `integration/test_learning_pause.py`, `test_sensor_unavailable_drops_anchors.py` |
| **Lernwert-Verlust-Klasse** (IHP #123/#125, HASmartThermostat #266) | Bootstrap **vor** erstem Steuertick, `ConfigEntryNotReady` bei Store-I/O-Fehler statt Frischstart, Shutdown-Flush (`EVENT_HOMEASSISTANT_STOP`), versionstoleranter Store, EKF-Migrationslogik (Zähler bleiben) | `__init__.py:196-222`, `coordinator.py:882-887, 1697-1788`, `thermal_ekf.py:376-423` | `integration/test_review_persistence.py`, `test_migration*.py`, `test_storage.py` |
| **Fenster-Restore-Klasse** (VTherm #683/#1284, BT #1195) | Architektonisch eliminiert: Fenster = Solver-Floor + `off`, kein Setpoint-Swap, kein Restore nötig; Hold-Expiry unter offenem Fenster kehrt zum Plan zurück, nie zum Manualwert | `control/tick_resolve.py:93-98` | `test_tick_resolve.py:49,305,323`, `integration/test_override_lifecycle.py:425` |
| **Fenstersensor-unavailable-Klasse** (BT PR #2126) | unavailable ≠ closed; Failsafe = Slope-Fallback + Repair-Issue; gesunder Zweitkontakt gewinnt | `coordinator.py:1362-1385, 2054-2059` | `integration/test_window_sensor_unavailable.py` (3) |
| **Override-Auto-Rückkehr** (universeller Community-Wunsch) | 3 Policies (timer/schedule/permanent), wall-clock-persistent, Band-Klemme + `override_clamped`, Preheat beendet Schedule-Holds, Boost friert Preset ein (VTherm-#1961-Guard) | `control/override.py:77-182`, `tick_resolve.py:96-98`, `coordinator.py:602-608, 816-833, 975-1002` | `test_override.py` (18), `integration/test_override_lifecycle.py` (12) |
| **Norm-Klemmen unumgehbar** | Jeder Write durch `resolve_write_target`: ASR-Cap, Frost/Schimmel-Floor, Device-Limits via Präzedenz-Solver; auch Disabled-Pfad hält den Floor | `tick_resolve.py:102-130, 354-378`, `constraints.py:64-83` | `test_constraints.py`, `test_norm_compliance.py` |
| **Schimmelschutz integriert** (dt. Kernthema, im Feld nur Sensorik) | DIN-4108-2-Oberflächenmodell (f_Rsi 0,7, 80 %-Kriterium, 24-°C-Kappe mit Signal), Frost-Floor nie unterdrückt, Proxy ohne Außensensor | `comfort/mold.py:18-61`, `coordinator.py:2433-2447, 2164-2176` | `test_mold.py`, `integration/test_review_write_floor.py:142` |
| **Feuchte/Dry mit Taupunkt-Guard** | „never cool below dewpoint + 2 K", 60/55-Hysterese, Dry ersetzt nur `idle`, heat-only unberührt | `comfort/dual_setpoint.py:126-127`, `comfort/humidity.py:23-34,104-111`, `comfort/mode_seam.py:17-28` | `test_humidity.py` (19), `integration/test_dry_actuation.py` |
| **Kühlkante ADR-0061** | Adaptives Kühl-Raise nur unbelegt, belegt fixes EN-Band, ASR-gekappt | `dual_setpoint.py:100-116`, `comfort/free_running.py:56-85` | `test_dual_setpoint.py:167`, `test_free_running.py` |
| **„Quorum of one"-Klasse** (BT #2063: ein Gerät schaltet Gruppe ab) | Strukturell ausgeschlossen: ODER-Aggregation; frozen Zone ⇒ demand=0 (kann Kessel weder pinnen noch abwürgen); symmetrischer Keep-alive (auch OFF wird re-assertiert) | `control/hub_aggregate.py:73-77, 156-159, 380-396` | `test_hub_aggregate.py` (43), `test_hub_tier0.py` |
| **Kessel-Aktuierung nur Opt-in** + Min-Zyklen | Aktuierung nur wenn beide Aktionen parsen; Min-On/Off mit 120-s-Hard-Floor; Boot-Reconcile gegen reales Gerät | `hub_coordinator.py:112-131, 293-369` | `integration/test_hub_glue_coverage.py` (inkl. Fail-Call-Rollback) |
| **Doppelsteuerungs-Klasse** (FRITZ!OS/TRV-Wochenplan vs. HA) | Mode-Nudge hält Aktor in `heat` (Re-Assert bei Fremdeingriff), interner Geräte-Zeitplan wird erkannt → Repair-Issue + Adoption-Sperre (Programm-Verstellung wird re-assertiert, nicht als Nutzer-Hold adoptiert) | `coordinator.py:2868-2916, 1223-1224, 1851-1859, 2946-2948, 3217-3229` | `integration/test_mode_adoption.py`, `test_setpoint_adoption.py` |
| **Onboarding-Komplexitäts-Klasse** (VTherm „50–60 Variablen") | 2 Pflichtfragen bis zur ersten Zone (Sensor + Aktor), Optionen in 7 Sektionen mit collapsed advanced; kein irreversibler „Typ" (Aktorpfad auto-erkannt), Aktor-Tausch mit Alt-Geräte-Park ohne Lernverlust | `config_flow.py:306-369, 862-869, 992-1063` | `integration/test_config_flow.py` |
| **Transparenz-Klasse** („warum heizt es nicht?"; stille Fallbacks) | ~120 Reason-/Diagnose-Attribute, stabiler ReasonCode-Vertrag, Card-Chips/Hold-Pill/Shadow-Pill/Lernbalken, Monitoring-Ampel; 18 Repair-Issue-Typen, de/en 207/207 Schlüssel | `climate.py:34-153`, `multi/reason.py:3-41`, `card/src/poise-card.ts:472-665`, `strings.json:345-408` | `card/test/monitoring.test.ts` u. a. |
| **Heizausfall-Erkennung** | „läuft real + ΔSoll ≥ 2 K + < 0,2 K Anstieg über 35 min", Latch, Mid-Episode-Fenster, echtes `hvac_action` statt Intent | `safety/heating_failure.py:11-100`, `coordinator.py:2625-2638` | `test_heating_failure.py` (9) |
| **Anti-Garbage-In** (Sensor an Wärmequelle) | implausible τ < 1 h nach Identifikation → Repair-Issue | `sensor_watchdog.py:44-55`, `const.py:65`, `coordinator.py:1876-1886` | `test_sensor_watchdog.py:34` |
| **Optimal Start physikbasiert** | Exponential-Inversion mit t_eq, Unerreichbarkeits-Fallback, Forecast-Außentemperatur (900-s-TTL, Ausfall ⇒ Konstant-Außen), identified-Gate, Anti-Chatter-Latches; Optimal-Stop-Coast konservativ | `control/optimal_start.py:41-127, 184-208`, `optimal_stop.py:44-96`, `coordinator.py:1440-1464` | `test_optimal_start.py`, `test_closed_loop.py` |
| **`valve_closing_degree` wird NIE geschrieben** (TRVZB-FW-Bug) | Ausschluss-Pattern wird *vor* den Valve-Patterns geprüft; kein Write-Pfad existiert | `devices/capability.py:26-27, 38`, `actuator.py:32` | `test_capability.py:21,43` |
| **Referenzrahmen-Offset (Shadow)** | EWMA ±2-K-Cap, Trust-Gate gegen sign-flipping Gerätefühler, nur im Laufbetrieb konditioniert, konservativer Restore (nie direkt nach Restart kompensieren) | `control/reference_offset.py:28-31, 58-61, 95, 112-114`, `coordinator.py:3547-3554` | `test_reference_offset.py` (10) |

---

## 3. Restrisiken und offene Probleme (priorisiert)

### P1 — vor der nächsten Heizsaison / vor dem TPI-Live-Flip

**R1 · TRVZB „Adaptive Mode" (FW 1.4.4) unerkannt — OFFEN.**
Repo-weite Suche: kein Code erkennt `smart_temperature_control`/Adaptive-Mode; alle „adaptive"-Treffer sind eigene Features. ADR-0036 kennt den Schalter nur textlich als Force-Open-Voraussetzung. Da der Sollwert-Pfad heute live schreibt, ist doppelte Regelung (TRVZB-interner PID gegen Poise-Sollwertführung) **schon jetzt** möglich und bliebe unbemerkt; ab TPI-Live-Flip wäre sie destruktiv.
**Vorschlag:** (a) `looks_like_adaptive_mode_switch()` in `devices/model_fixes.py` (Entity-Heuristik `switch.`/`select.` + „adaptive"/„smart_temperature"); (b) Repair-Issue `adaptive_mode_active` in `coordinator._emit_health_issues` analog `device_schedule` (`coordinator.py:1851-1859`); (c) beim späteren TPI-Flip eine AUS-Assertion als Vorbedingung im `resolve_write_target`-Seam; (d) ADR-0036-Nachtrag + Tests.

**R2 · Diagnostics: `presence_home`/`occupancy_sensor` unredigiert — TEILWEISE (Privacy).**
`diagnostics_data.py:14-34` (`REDACT_KEYS`) schwärzt alle Sensor-/Aktor-/System-IDs, aber **nicht** `presence_home` (person/device_tracker/group, `const.py:143`) und `occupancy_sensor`; `build_diagnostics` merged `entry.options` (Z. 59) → `person.*`-IDs erscheinen im Dump. Das ist exakt die im Meinungsbild kritisierte RoomMind-Fehlerklasse (ADR-0022 nennt Redaktion „Pflicht").
**Vorschlag:** beide Schlüssel in `REDACT_KEYS` aufnehmen + Regressionstest in `tests/test_diagnostics_data.py` („person.* erscheint nie im Dump"). Aufwand: Minuten.

**R3 · „Kessel-aus"-Klasse nur halb geschlossen (VTherm #1428) — TEILWEISE.**
`u_h` kommt korrekt vom realen `hvac_action` (`tick_resolve.py:202-212`) — aber ein TRV mit offenem Ventil meldet „heating", auch wenn der Kessel nicht liefert. Die `HeatingFailureDetector`-Erkennung (`safety/heating_failure.py:28-86`) erzeugt nur ein Repair-Issue; das Lern-Gate ist ausschließlich `should_learn(window_open, frozen)` (`coordinator.py:2123`) — **`failed` fließt nicht ein**. Der EKF lernt in einer Kessel-aus-Phase mit `u_h=1` auf flacher Kurve und drückt `beta_h` Richtung Bound (Abfederung nur über Bounds/Recovery).
**Vorschlag:** Heating-Failure in das Lern-Gate aufnehmen (bei `failed`: `u_h→0` setzen **oder** Lernen pausieren + Anker droppen, analog V5-Muster `coordinator.py:2147-2150`); bei `controls_boiler`-Zonen zusätzlich den bekannten Hub-Kesselzustand einspeisen. Closed-Loop-Regressionstest „Kessel aus, Ventil offen → beta_h bleibt brauchbar" im Harness (`tests/harness/closed_loop.py`).

**R4 · Setpoint-Adoption nicht fenster-gegated (Phantom-Hold-Klasse) — TEILWEISE.**
Die Mode-Adoption ist auf `not window_open and not frozen` gegated (`coordinator.py:2801-2807`), die Setpoint-Adoption (`coordinator.py:2997-2999`) **nicht**, und `sanitize_override` lässt 7,0 °C passieren. Senkt ein TRV per eigener Fenstererkennung auf 7 °C, *bevor* Poises Sensor/Slope anschlägt, entsteht ein falscher „manual"-Hold (geschrieben wird dank Band-Klemme `tick_resolve.py:96-98` zwar nie 7 °C — aber der Hold ist da und expiriert erst per Policy).
**Vorschlag:** Setpoint-Adoption wie die Mode-Adoption auf `not window_open` gaten **plus** Plausibilitätsfilter „`device_sp ≤ Frost-Floor + ε` ⇒ nie adoptieren" in `setpoint_adopt_reason` (`control/override.py:208-306`); Regressionstest „TRV-Frost-Drop wird nicht adoptiert".

### P2 — Qualität/Vollständigkeit (diese Saison sinnvoll)

**R5 · Ventil-Physik vor dem TPI-Live-Flip fehlt.** Kein Kennlinien-/Totband-Modell, keine min-opening-/Anti-Stiction-Logik, kein Read-back geschriebene vs. gemeldete Öffnung (ADR-0036 nennt das selbst offen). Das Shadow-Gate ist nur strukturell gesichert (kein `ActuatorPath.TPI_VALVE`-Command im Coordinator — Grep-Beleg), ohne Regressionstest.
**Vorschlag:** (a) Harness-Plant um nichtlineare kv-Kennlinie + Totband erweitern (`tests/harness/plant.py`) und TPI dagegen validieren; (b) Gate-Regressionstest „Valve-Entity vorhanden ⇒ kein `number.set_value`"; (c) `valve_opening_degree`-Read-back als Diagnose (Referenz: VTherm PR #1827 Stuck-Valve-Recovery — Poises `valve_stuck`-Issue `sensor_watchdog.py:58-67` deckt nur die closing_steps-Klasse).

**R6 · Kalibrier-Fallback-Pfad ist tot + ±2,4/±2,5-K-Klasse latent.** `control/calibration.py:15-25` clampt fix auf ±5 K; `select_path` (`capability.py:65-71`) hat keinen produktiven Aufrufer, `actuator.service_call_for(CALIBRATION)` wirft `NotImplementedError` (`actuator.py:38`). Geräte ohne external-temp-Eingang haben damit heute keine Drift-Kompensation (PI-Kompensator ADR-0037 ist bewusst Shadow).
**Vorschlag:** beim Verdrahten (ob Kalibrier-Pfad oder PI-Live-Flip) `min`/`max` der Kalibrier-Number **auslesen** statt fixem Clamp — sonst reproduziert Poise die AHC-Fehlerklasse #141/#157 (Wert außerhalb des Geräte-Bereichs). Bis dahin: Lücke in der Doku ehrlich benennen („ohne external-temp-Eingang keine Live-Kompensation").

**R7 · FBH-Klasse: Dynamikprofil fließt nicht in Setback/Optimal-Start.** `VERY_SLOW` („underfloor") wird von `classify_dynamics` (`control/dynamics.py:87-108`) **nie automatisch** erkannt (nur manueller Override), und `plan_preheat`/`heatup_minutes` kennen kein Profil — `max_lead_h` ist fix 4 h (`optimal_start.py`), die Setback-Tiefe wird nicht klassenabhängig gedämpft. Die Community-Warnung „Absenkung bei träger FBH kontraproduktiv" bleibt unadressiert.
**Vorschlag:** Profil in `plan_preheat` einspeisen (`max_lead_h` je Klasse, z. B. 8–12 h für `very_slow`), bei `very_slow` Setback-Dämpfung oder Repair-Hinweis „Absenkung bei FBH prüfen"; Options-UI für `actuator_dynamics` prominenter machen.

**R8 · Effizienz-Report unsichtbar + README-Drift.** `hdh_savings` rechnet live und persistiert (`coordinator.py:3466-3479, 3577-3579`), aber `savings_*` steht weder in `climate._ATTRS` (`climate.py:34-153`) noch als Sensor noch auf der Card — nur im Diagnostics-Dump. **README.md:45 behauptet „published as `savings_*` climate attributes" — nicht eingelöst.**
**Vorschlag:** `savings_kwh_month/eur/pct` in `_ATTRS` (+ optional Sensor, default aus) aufnehmen — oder README korrigieren. Gerade diese Zahl beantwortet die Community-Frage „lohnt sich Absenkung bei mir?" und ist ein Alleinstellungs-Feature.

**R9 · Nicht persistierte Runtime-Latches.** (a) `_dry_active` (`coordinator.py:508`) fehlt im `_save_payload` (`coordinator.py:1647-1695`) → nach Restart fällt ein Raum zwischen 55 und 60 % r. F. aus dem Dry-Modus (fail-safe Richtung „nicht trocknen", aber Verhaltenssprung — dual_smart-#553-Klasse). (b) `_window_open_since` (`coordinator.py:409`) runtime-only → 30-min-Schimmel-Suppression startet nach Restart neu.
**Vorschlag:** beide in den Save-Payload aufnehmen; Restart-Tests „mid-dry bleibt dry" / „Reload bei offenem Fenster".

**R10 · Fehlende Regressionstests für vorhandene Logik.** Konkret: (a) AC-Kaltluft-Fenster-Gate (`coordinator.py:1538-1542` — Neutralisierung existiert, aber kein Test füttert `cooling=True`; Logik liegt zudem nur in Glue); (b) Sensor-Select-Re-Assert („external_2"-Klasse, `coordinator.py:3130-3145`); (c) Restart mit offenem Fenster (nur purer Roundtrip); (d) Hub-Restart als Glue-Test (Persist→Reload→Reconcile nur pure getestet); (e) `external_feed_due`-Unit-Test.
**Vorschlag:** die fünf Tests ergänzen; für (a) das Kühl-Gate in einen puren Helper ziehen.

### P3 — mittelfristig

**R11 · Golden-Feldtrace-Korpus fehlt.** Der Trace-Recorder + deterministisches Replay existieren und sind getestet (`trace/schema.py`, `tests/harness/trace_replay.py`, `test_trace.py:160`), aber es sind **keine realen Traces committet** (kein `*.jsonl` unter `tests/`) — die Golden-Regression läuft nur synthetisch. ADR-0018 (SemVer/Deprecation) steht bei 60 %, eine formale Deprecation-Warn-Mechanik fehlt. Genau die Update-Fragilität ist im Meinungsbild ein Top-Abwanderungsgrund (BT-1.8-Welle).
**Vorschlag:** anonymisierte Feld-Traces der kommenden Saison als Golden-Korpus committen; Deprecation-Warnpfad (ADR-0018 §4) implementieren.

**R12 · Adopt-Ablehnungsgründe unsichtbar.** K3-Ablehnungen (`own_echo`, `opt_out`, `safety_window`, `schedule_active`) landen nur debounced im DEBUG-Log (`coordinator.py:3044-3051`). Nutzer-Erlebnis: „mein Dreh am TRV tat nichts" — die AHC-„stille-Fallback"-Kritik in eigener Ausprägung.
**Vorschlag:** letzten Ablehnungsgrund als Attribut (`adopt_rejected_reason`) + Card-Chip surfacen.

**R13 · Zonen-„call for heat" nicht publiziert.** Systemweit ist der Bedarf vorbildlich exponiert (`binary_sensor.py:30-47`); pro Zone existiert `heating` nur im internen Snapshot (`coordinator.py:3656`) — Automationen müssen über `hvac_action`/`tpi_duty` templaten.
**Vorschlag:** `heat_demand`/`heating` als Zonen-Attribut oder optionalen `binary_sensor` publizieren (ebusd/BSB-LAN-Anschlussfähigkeit pro Zone).

**R14 · Kleinere Punkte.** (a) Kein Nutzer-Service „Lernmodell zurücksetzen" (nur Auto-Recovery bzw. Entry-Neuanlage; `services.yaml` kennt nur `resume_schedule`). (b) Boiler-Aktionen als Freitext im Versatile-Format (`config_flow.py:387-388`) statt Action-Selector. (c) Verdichtergruppen nutzen die Boiler-Min-Zyklen mit — eigener (längerer) Min-Off fehlt (`hub_coordinator.py:138-140`, dort selbst als NOTE markiert). (d) i18n: 2 Sprachen (de/en, 207/207 Schlüssel Parität) — unter Wettbewerbsniveau (ThermoSmart 24, VTherm/BT 10). (e) Interner Geräte-Zeitplan wird nur gemeldet, nicht optional abgeschaltet. (f) `heating_failure` könnte die gemeldete Ventilöffnung als schärfere Zusatzbedingung nutzen. (g) Doku-Hinweis: `comfort/corridor.py` ist Referenz-Pipeline, nicht Live-Pfad (`pipeline.py`-Docstring) — bei Reviews leicht zu verwechseln.

---

## 4. Ehrlichkeits-Bilanz gegenüber der eigenen Dokumentation

- **README/ADR-Statusangaben stimmen weit überwiegend** mit dem Code überein (Shadow-Kennzeichnungen TPI/PI/MPC/Referenzrahmen sind korrekt; „Bootstrap vor erstem Tick", Shutdown-Flush, Opt-in-Kesselaktuierung wie dokumentiert). Der ADR-Status-Linter (`tests/test_adr_status_lint.py`) hält die Disziplin.
- **Ein nachgewiesener Drift:** README.md:45 „savings_* climate attributes" — im Code nicht publiziert (R8).
- **Ein dokumentiertes Versprechen ohne Code:** Meinungsbild §5 empfiehlt den Adaptive-Mode-Guard als „Nachtrag zu ADR-0036 empfohlen" — bislang weder ADR-Nachtrag noch Code (R1).
- Der Meinungsbild-Satz „Poise ist architektonisch genau darauf gebaut (lokal, erklärbar, abschaltbar, updatefest, funkarm)" hält dem Code-Audit stand — mit den oben benannten vier P1-Ausnahmen.

## 5. Priorisierte Maßnahmen-Kurzliste

| Prio | Maßnahme | Aufwand | Bezug |
|---|---|---|---|
| P1 | `presence_home`/`occupancy_sensor` in `REDACT_KEYS` + Test | Minuten | R2 |
| P1 | Adaptive-Mode-Guard (model_fixes-Heuristik + Repair-Issue) + ADR-0036-Nachtrag | klein | R1 |
| P1 | Heating-Failure → Lern-Gate (`u_h→0`/Pause + Anker-Drop) + Harness-Test | mittel | R3 |
| P1 | Setpoint-Adoption fenster-gaten + Frost-Plausibilitätsfilter + Test | klein | R4 |
| P2 | 5 fehlende Regressionstests (AC-Gate, external_2, Fenster-Restart, Hub-Glue-Restart, feed_due) | klein–mittel | R10 |
| P2 | `savings_*` in `_ATTRS` oder README-Korrektur | Minuten | R8 |
| P2 | Dry-Latch + `_window_open_since` persistieren | klein | R9 |
| P2 | Harness-Ventilkennlinie + TPI-Gate-Regressionstest | mittel | R5 |
| P2 | FBH: Profil → `plan_preheat`/Setback-Dämpfung | mittel | R7 |
| P2 | Kalibrier-Range aus Geräte-Number lesen (vor jedem Live-Flip des Pfads) | klein | R6 |
| P3 | Golden-Trace-Korpus, Deprecation-Mechanik, Adopt-Reason-Attribut, Zonen-heat_demand, Lern-Reset-Service, i18n-Ausbau | laufend | R11–R14 |

---

## 6. Nachtrag: Prüfung v0.177.0-alpha (2026-07-18)

**Prüfumfang:** Diff v0.174.0 → v0.177.0 (origin/main, +801/−26 Zeilen über 27 Dateien) gegen die Findings dieses Berichts; vollständiger Testlauf der Suite auf v0.177.0 (Python 3.13, `asyncio_mode=auto` wie CI): **1022 Tests, alle grün (Exit 0)**.

### Korrekt umgesetzt (Finding → Beleg in v0.177.0)

| Finding | Umsetzung | Bewertung |
|---|---|---|
| **R1** Adaptive-Mode-Guard | `looks_like_adaptive_mode_switch()` (`model_fixes.py`, switch./select. + „adaptive"/„smart_temperature"), Scan **vor** der elif-Kette (verhindert Verschlucken durch den Sensor-Select-Zweig), Repair-Issue `adaptive_mode_active` mit de/en-Übersetzung; Switch- („on") und Select-Zustände („adaptive"/„smart") werden erkannt. AUS-Assertion bewusst als TPI-Flip-Vorbedingung offen gelassen (im Code dokumentiert). Tests: `test_adaptive_mode_switch_classifier` (inkl. Negativfälle child_lock/schedule/Domain) | ✅ korrekt |
| **R2** Diagnostics-Redaktion | `presence_home` + `occupancy_sensor` in `REDACT_KEYS`; Test `test_presence_and_occupancy_ids_are_redacted` prüft zusätzlich `"person.alice" not in repr(diag)` | ✅ korrekt, vollständig |
| **R3** Kessel-aus → Lern-Gate | `should_learn(heating_failed=…)` neu; gespeist aus dem **Vortick-Latch** `_prev_heating_failed` (Verdict entsteht erst spät im Tick — sauber gelöst und begründet); Anker-Drop-Pfad greift mit. **Closed-Loop-Regressionstest** `test_learn_gate_heating_failure.py` pinnt exakt das VTherm-#1428-Szenario (u_h=1, Plant ohne Leistung → beta_h bleibt brauchbar) | ✅ korrekt; Restlatenz s. u. |
| **R4** Setpoint-Adoption | Doppelt abgesichert: Glue-Gate `not window_open and not frozen` (wie Mode-Pfad) **und** purer `implausible_frost`-Filter (`device_sp ≤ FROST_FLOOR_C` nie adoptieren, nach dem Echo-Guard geprüft — echte Komfortänderungen unberührt); neue Reason-Codes `safety_window`/`safety_frozen`/`implausible_frost`. Tests pure + Glue (`test_trv_frost_drop_is_not_adopted`) | ✅ korrekt, vollständig |
| **R5** Ventil-Physik-Vorbereitung | Harness-Plant um `valve_deadband` + `valve_curve` erweitert (Default byte-identisch linear); `test_tpi_converges_against_nonlinear_valve` (15 %-Totband, Exponent 1,6 → settelt ohne Hunting); **Gate-Regressionstest** `test_autodetected_valve_is_never_written` (nicht-vakuum: asserted zuerst, dass `_valve_entity` aufgelöst wurde) | ✅ Teil „Harness+Gate" erledigt; Read-back-Diagnose bleibt offen |
| **R6** Kalibrier-Clamp | Bewusst nur die empfohlene Interim-Lösung: „Honesty note" im Modulkopf (`calibration.py`) — nicht verdrahtet, ±5-K-Clamps als Platzhalter deklariert, Geräte-Range-Auslesen als Verdrahtungs-Voraussetzung benannt | ✅ wie vorgeschlagen (Interim) |
| **R7** FBH → Optimal Start | `DynamicsProfile.max_lead_h` (Radiator/AC 4 h, `very_slow` 12 h), durchgereicht bis `advise()`; Tests `test_r7_*` (3). Ehrlich dokumentiert, dass Auto-Detect FBH nicht erkennen kann (bleibt Nutzer-Flag) | ✅ Teilumsetzung wie designt; Setback-Dämpfung/Repair-Hinweis weiter offen |
| **R8** savings_* | In `climate._ATTRS` aufgenommen — der README-Claim stimmt jetzt | ✅ korrekt |
| **R9** Dry-Latch | `dry_active` in Save-Payload + Bootstrap-Restore + Glue-Test. `_window_open_since` bewusst **nicht** persistiert (Monotonic-Stamp; im Code begründet) — akzeptierte Abweichung, fail-safe Richtung kalt | ✅ korrekt (Teil bewusst ausgelassen) |
| **R10e** `external_feed_due`-Unit-Test | `test_r10_external_feed_due` | ✅ |
| Bonus | `cooling_intent()` als purer, getesteter Helper (Fenster-Gate des Kühl-Intents); **Doku-Ehrlichkeits-Fix** in `strings.json`: die Adoption-Beschreibung behauptete „Baseline not restored after restart" — korrigiert auf „persisted" (deckt sich mit dem Audit-Befund B5) | ✅ |

### Weiterhin offen (unverändert gegenüber Abschnitt 3)

- **R10a** Slope-Neutralisierung im Kühlbetrieb (`_was_cooling`-Glue) weiterhin ohne Test — der neue `cooling_intent`-Test deckt das benachbarte Intent-Gate ab, nicht die Fenster-Slope-Neutralisierung. **R10b** Sensor-Select-Re-Assert („external_2"), **R10c** Restart-mit-offenem-Fenster (Integration), **R10d** Hub-Glue-Restart: Tests fehlen weiter.
- **R5-Rest:** `valve_opening_degree`-Read-back-Diagnose; **R6-Rest:** Geräte-Range-Auslesen beim Verdrahten; **R7-Rest:** Setback-Dämpfung/Hinweis bei `very_slow`.
- **R11–R14** (P3) unverändert: Golden-Trace-Korpus, Deprecation-Mechanik, Adopt-Reason als Attribut (die neuen Reason-Codes existieren, landen aber weiter nur debounced im DEBUG-Log), Zonen-`heat_demand`-Publikation, Lern-Reset-Service, i18n-Ausbau.

### Rest-Risiko-Hinweise zur R3-Umsetzung (klein, dokumentierenswert)

1. **Detektor-Latenz:** Der `HeatingFailureDetector` latcht erst nach ~35 min Demand+Flat — die ersten ~35 min einer Kessel-aus-Episode lernen also weiterhin mit (begrenzte Kontamination; die EKF-Bounds/Recovery fangen das, der Harness-Test läuft konservativ mit gelatchtem Zustand).
2. `_prev_heating_failed` ist nicht persistiert — nach einem Restart mitten in einer Ausfall-Episode beginnt die 35-min-Erkennung neu. Konsistent mit dem übrigen Latch-Verhalten, aber erwähnenswert.

**Fazit v0.177.0:** Alle vier P1-Findings sind korrekt, getestet und mit sauberer Begründungs-Dokumentation umgesetzt; von den P2-Findings sind Harness-Kennlinie, TPI-Gate-Test, savings_*, Dry-Latch und `max_lead_h` erledigt, R6 wie empfohlen als Ehrlichkeitsnote interimistisch. Die Suite ist mit 1022 Tests grün. Der Fortschritt entspricht exakt der priorisierten Maßnahmenliste; Qualität der Umsetzung: hoch (pure Logik + Glue-Verdrahtung + Regressionstest je Finding, Kommentare referenzieren die Fehlerklassen).
