# Poise Setpoint Thermostat — Tiefgreifendes Code-Review v0.110.0

**Gegenstand:** `custom_components/poise` (v0.110.0, Alpha), Lovelace-Card (`card/`), Testsuite, ADRs, CI
**Datum:** 2026-07-02
**Methodik:** Mehrstufige Analyse mit 13 unabhängigen Tiefenlektüren/Bug-Jagden über alle Subsysteme, vollständige Ausführung der Testsuite, anschließende manuelle Verifikation aller kritischen Befunde direkt am Code (Datei:Zeile). Befunde, die nicht einzeln nachgeprüft wurden, sind als *plausibel* gekennzeichnet.

---

## 1. Executive Summary

Poise ist **für eine Alpha ein ungewöhnlich reifes, diszipliniert gebautes Projekt** — deutlich über dem Niveau typischer HACS-Thermostat-Integrationen:

- **Kennzahlen:** ~17.400 Zeilen Python (davon ~9.500 in der Integration), 54 ADRs mit code-verifizierten Statusangaben, 571/571 Tests grün (532 Pure-Core + 39 HA-Integration, lokal reproduziert), Coverage 98,8 % (Pure Core) / 86,3 % (HA-Glue), `mypy --strict`, ruff, hassfest + HACS-Validation in CI, Card 23/23 Tests, Bundle byte-identisch zum Rebuild, Versionskonsistenz 0.110.0 über Card/Manifest/const (einzige Drift: `pyproject.toml` steht auf 0.106.0).
- **Fachliche Substanz ist echt:** EN-16798-1-Bänder, Running-Mean (Gl. B.1, α=0,8), Alduchov-Eskridge-Psychrometrie, DIN-4108-2/EN-ISO-13788-Schimmelfloor (f_Rsi=0,7, 80 % Oberflächen-RH), ISO-7726-Operativtemperatur, 1R1C-EKF mit analytischer ZOH-Diskretisierung, Joseph-Form-Update und Moden-Gating — die Formeln wurden stichprobenartig nachgerechnet und sind korrekt.
- **Sicherheits-Grundgerüst ist durchdacht:** Präzedenz-expliziter Constraint-Solver (SAFETY > HEALTH > COMFORT), fail-closed Hub-Staleness, Write-Deadband/Step-Snapping (Zigbee-Batterieschonung), Repair-Issues, redigierte Diagnostics, Shadow-first-Rollout (MPC/TPI/PI rechnen live, schreiben nicht).

**Aber:** Die Analyse hat **10 selbst verifizierte Defekte** gefunden, davon mehrere mit realer Sicherheits- oder Produktwirkung. Die drei gravierendsten:

1. **Die Heiz-zentrische Sicherheitssemantik invertiert bei Kühlgeräten** — Fenster-offen/eingefrorener Sensor schreibt den Frost-Floor (≈7 °C) als Setpoint in ein Gerät, das absichtlich im `cool`-Modus gehalten wird → eine Split-Klimaanlage kühlt bei offenem Fenster mit Volllast statt zu stoppen.
2. **Der Kessel-Aktuationspfad ist nicht restart-/fehlerfest** — fehlgeschlagene ON-Calls werden als Erfolg verbucht, `BoilerState` wird weder persistiert noch beim Start/Unload mit der Realität abgeglichen, Default-Keepalive = 0 deaktiviert die Selbstheilung → Heizausfall im Winter bzw. dauerlaufender Kessel sind real möglich.
3. **Nachtabsenkung, Eco und Away sind faktisch defekt** — der EN-Kategorieband-Clamp hebt jede abgesenkte Basis auf die Kategorie-Untergrenze an (Cat II: 20 °C). Aus „Setback 3 K" wird real 1 K, bei Cat I 0 K. Das zentrale Energiespar-Versprechen der Integration ist damit in v0.110.0 weitgehend wirkungslos.

**Gesamturteil:** Architektur, Testkultur und Norm-Fundament rechtfertigen das Selbstbild „normbasiert und selbstlernend". Für den produktiven Einsatz auf **Heiz-Hardware (TRVs) ohne Kessel-Aktuierung** ist Poise heute mit Einschränkungen nutzbar; für **Kühlgeräte und die Kessel-Schaltung ist v0.110.0 nicht vertrauenswürdig**, und der Energiespar-Anspruch erfordert den Setback-Fix. Alle drei Punkte sind mit überschaubarem Aufwand behebbar (siehe §9 und Roadmap).

---

## 2. Architektur-Bewertung

### 2.1 Stärken

- **„Pure Core + dünne HA-Glue" ist real, nicht nur behauptet.** `comfort/`, `control/`, `estimation/`, `multi/`, `safety/` sind vollständig HA-frei (stdlib-only, keine numpy-Abhängigkeit — bewusste ADR-0022-Entscheidung, die Installation auf RPi/HA Green trivial macht), mit injizierbarer monotoner Uhr (`clock.py`). Die 532 Pure-Core-Tests brauchen null Mocks.
- **Single-Writer-Prinzip:** Jeder Aktor-Write läuft durch `actuator.py` (`service_call_for` ist pur und testbar); `valve_closing_degree` wird wegen des TRVZB-Firmware-Bugs strukturell nie geschrieben.
- **Write-Hygiene vorbildlich:** Vergleich gegen den *realen* Geräte-Setpoint (re-assert nach externem Eingriff), `snap_to_step` gegen grobe TRV-Echos, 0,2-K-Deadband, Regulation-Throttle für selbstregelnde Geräte mit Safety-Bypass (`tick_resolve.py:116-147`, `coordinator.py:1281-1315`).
- **Persistenz/Restore durchdacht:** EKF + Lernzustände + Nutzerintention überleben Neustarts; Override-Expiry auf Wall-Clock-Basis; korrupter Store fällt kontrolliert auf frisch zurück (`thermal_ekf.from_dict` validiert Version/Shape/Finiteness).
- **Fehlerisolation dreistufig:** Shadow-Blöcke können den Tick nie töten; Aktor-I/O-Fehler werden geloggt, nicht propagiert; Hub-Boiler-Calls mit 10-s-Timeout.

### 2.2 Strukturelle Schwächen

| Befund | Beleg | Wirkung |
|---|---|---|
| **God-Method-Regression:** `_run_once` umfasst `coordinator.py:884-1685` (~800 Zeilen, ~60 Mutable-Felder) gegen den in ADR-0031 dokumentierten Zielzustand von 266 Zeilen. Die Mathematik ist extrahiert, die Orchestrierung nicht — jede neue Shadow-Funktion (ADR-0043–0053) wurde inline angeflanscht. | coordinator.py:207-335, 884-1685 | Wartbarkeit, Sequenz-Logik nur integrationsgetestet (84 % Coverage, 104 Stmts offen) |
| **Zwei Tick-Implementierungen:** `pipeline.py`/`controller.py`/`arbitration.py` sind Produktions-toter Referenzpfad (explizit dokumentiert, pipeline.py:7-12); der Harness validiert damit *nicht* den Live-Pfad. | pipeline.py, ADR-0033 §c | Drift-Risiko Referenz ↔ Produktion; Harness-Validität eingeschränkt |
| **Der eigene Contracts-Anspruch ist am wichtigsten Boundary nicht eingelöst:** Zone→Hub läuft über ein stringly-typed Dict (~90 Keys) via `getattr(entry.runtime_data, "data")`; `ThermalState`/`ControlRequest`/`ResourceRelease` (contracts.py) werden im Live-Pfad nie erzeugt. ResourceRelease (Load-Shedding-Rückkanal, ADR-0038) ist toter Vertragscode. | hub_coordinator.py:130-170, contracts.py:186-199 | Versionsdrift Zone/Hub nur über Staleness abgefangen; Shedding hat keinen Enforcement-Pfad |
| **Degradationsleiter teilweise dekorativ:** Bei Raumsensor-Ausfall bricht der Tick ab (`{"available": False}`, coordinator.py:892-901) statt degradiert weiterzuregeln; die `derived`/`default`-Arme von `ingest_temperature` sind im Produktionspfad unerreichbar. | coordinator.py:892-913, ingestion.py:58-60 | „unavailable" und „frozen" haben zwei verschiedene Sicherheitsphilosophien (§3, Befund V9) |
| **Kein Store-Migrationspfad:** STORAGE_VERSION=1 ohne `minor_version`/Migrate-Hooks — „schema-tolerant laden" heißt bei inkompatibler Änderung: stiller Lernverlust. | storage.py | Risiko für kommende Releases, ADR-0007 verspricht Migration |
| **Kein `async_remove_entry`:** `.storage/poise_<entry_id>_ekf` bleibt nach Entry-Löschung liegen; README verspricht das Gegenteil. | __init__.py, storage.py:26 | Storage-Leichen |

---

## 3. Verifizierte Defekte (selbst am Code nachgeprüft)

Sortiert nach Schwere. Jeder Befund wurde in dieser Analyse manuell an den genannten Stellen verifiziert.

### V1 — KRITISCH: Fenster-offen/Frozen-Sensor treibt Kühlgeräte in Volllast-Kühlung
**Stellen:** `control/tick_resolve.py:79-85` (window → `target=floor`, `mode="off"`), `tick_resolve.py:200-204` (`resolve_desired_mode` hält reversibles Gerät bewusst im `cool`-Modus), `coordinator.py:1263-1267` (`needs_mode_nudge("cool","cool")` → False), `actuator.py:24-29` (SETPOINT-Pfad sendet nur `temperature`, keinen Modus).
**Mechanik:** Bei `window_open` (Sensor *oder* Slope-Detektor) wird der Frost-/Schimmelfloor (≈7 °C) als Setpoint geschrieben. Der Anti-Reversing-Valve-Schutz hält das Gerät gleichzeitig in `cool`. Der „cool-matched idle hold" (coordinator.py:1114-1128) schützt nur den `idle`-Zweig, **nicht** den Fenster-Pfad. Analog erzwingt der Frozen-Pfad (coordinator.py:1142-1147) `mode="heat"` — ein Cool-only-Gerät ohne `heat` in `hvac_modes` bekommt keinen Nudge und kühlt auf den Floor.
**Szenario:** Sommer, Split-AC kühlt auf 26 °C, Fenster wird zum Lüften geöffnet → `set_temperature(7.0)` bei aktivem `cool` → Kompressor kühlt mit Maximalleistung gegen das offene Fenster. „Fail toward warmth" invertiert bei Kühl-Hardware zu „fail toward maximal cooling".
**Fix-Skizze:** `resolve_write_target` kühlrichtungsbewusst machen: Für ein Gerät im `cool`-Modus ist der sichere Fenster-/Frozen-Hold die **obere** Bandkante (bzw. `off`, wenn unterstützt), nie der Heiz-Floor.

### V2 — KRITISCH: Kessel-Aktuationspfad ist nicht fehler- und restartfest (3 Teilbefunde)
**Stellen:** `hub_coordinator.py:259-264`, `hub_coordinator.py:113`, `__init__.py` (Unload-Zweig), `const.py:114`.
**(a) ON-Fehlschlag wird verbucht:** `_actuate` prüft nur den OFF-Call (`if not await self._call(...): return`); der Rückgabewert des ON-Calls wird verworfen und `self._boiler = step.state` committet `on=True`. Mit Default-Keepalive 0 gibt es keinen Retry, solange Bedarf ansteht → Zonen kühlen aus, der Hub meldet `boiler_on=True`. Im Frostfall heißt das: **Frost-Override aktiv, Kessel trotzdem aus.**
**(b) Kein Restart-/Unload-Reconcile:** `BoilerState()` startet nach jedem Setup mit `on=False`, wird nie persistiert, nie gegen den realen Kesselzustand abgeglichen; beim Unload/Löschen des Hub-Entries wird kein OFF gesendet, es gibt keinen `EVENT_HOMEASSISTANT_STOP`-Handler. Szenario: Kessel AN, HA-Neustart, Bedarf inzwischen weg → `off→off`, es wird **nie** OFF gesendet — der Kessel läuft unbegrenzt.
**(c) Default-Keepalive 0:** Mehrere Sicherheitskommentare im Code verweisen auf den Keepalive als Selbstheilung (`hub_aggregate.py:362-374`) — der ist per Default deaktiviert.
**Fix-Skizze:** ON-Fehlschlag wie OFF behandeln; `BoilerState` persistieren + beim Start reconcilen (Entity aus dem Action-Spec ist bekannt); OFF bei Unload und HA-Stop; Keepalive-Default ≥ 300 s, sobald Aktuierung aktiviert ist; Repair-Issue bei wiederholt fehlschlagenden Calls.

### V3 — HOCH: Setback/Eco/Away werden vom Kategorieband-Clamp neutralisiert
**Stelle:** `comfort/dual_setpoint.py:69-71` — `heat_op = _clamp(comfort_base − widen, HEATING_LOWER[cat], HEATING_UPPER[cat])`.
**Mechanik:** Der Setback-Pfad läuft ausschließlich über `comfort_base=base` (abgesenkte Basis aus `plan_preheat`). `_clamp(18, 20, 24) = 20`: Aus 3 K Setback wird 1 K (Cat II); Eco (−2 K) und Away (−4 K) landen identisch auf 20 °C; bei Cat I (Lower = 21 = Default-Basis) sind **alle** Absenkungen wirkungslos. Auch der HDH-Ersparnisreport rechnet mit der geklemmten Kante — die ausgewiesene Ersparnis ist konsistent, aber das Feature liefert sie nicht.
**Norm-Einordnung:** Die EN-16798-Auslegungsbänder gelten für die **Nutzungszeit**. Außerhalb der Belegung sind abgesenkte Sollwerte normverträglich, solange die HEALTH-Floors (Frost/Schimmel) halten. Der Clamp ist also strenger als die Norm, ohne dass die Norm es verlangt.
**Fix-Skizze:** `decide()` um ein `occupied`-Flag erweitern; außerhalb des Komfortfensters nur Frost-/Schimmelfloor als Untergrenze zulassen, Band-Clamp nur bei Belegung.

### V4 — HOCH: `HVACMode.OFF` hebelt Frost- und Schimmelschutz vollständig aus
**Stellen:** `coordinator.py:1242` (`if self._enabled:` umschließt **alle** Writes inkl. Mode-Nudge, frozen-safe-target und External-Temp-Feed), `climate.py:209-215`.
**Mechanik:** OFF heißt: Poise schreibt nichts mehr — es schaltet den Aktor aber auch nicht ab. Ein TRV heizt auf dem letzten Setpoint weiter (Entity zeigt `off`/`HVACAction.OFF` — irreführend), oder ein abgeschalteter Aktor bleibt im Winter ohne jeden Frost-Floor. Das README verspricht „unconditional safety floors"; im OFF-Zustand ist der Floor nicht unconditional. Zusätzlich stoppt der External-Temp-Feed — ein TRV im External-Sensor-Modus regelt gegen einen einfrierenden Wert.
**Fix-Skizze:** Beim Umschalten auf OFF einmalig einen definierten Zustand schreiben (Gerät `off` bzw. Frost-Floor-Setpoint); im OFF-Zustand den Frost-Floor weiterhin durchsetzen (mind. als Option, Default an).

### V5 — HOCH: EKF-Modellvergiftung nach Lernpausen (Stoßlüften!)
**Stellen:** `coordinator.py:684-701` (`_last_mono` wird nur in `_learn` fortgeschrieben), `coordinator.py:984-985` (Gating), `coordinator.py:986` (`_observe_seasonless` läuft ungegated).
**Mechanik:** `should_learn=False` (Fenster offen / frozen) pausiert `_learn`, friert aber `_last_mono` ein. Der erste Lernschritt nach Pausenende integriert das **gesamte** kontaminierte Intervall (nur Pausen > 1 h werden durch den `dt_h < 1.0`-Guard verworfen). Numerische Prüfung durch die Analyse: 25 min Fenster offen, 3 K Abfall → α springt von 0,089 auf 0,244 (τ: 11,2 h → 4,1 h, +174 %). **Das trifft exakt das deutsche Kernnutzungsmuster Stoßlüften** und degradiert das Lernversprechen schleichend: Optimal-Start startet danach falsch, die adaptive Fensterschwelle verstellt sich.
**Fix-Skizze:** Ein-Zeiler — beim Übergang `should_learn → False` `_last_mono = None` setzen; zusätzlich `_observe_seasonless` mitgaten.

### V6 — HOCH: Fenster-Slope-Detektor fehlalarmiert bei 0,1-K-quantisierten Sensoren
**Stellen:** `coordinator.py:722-728` (Slope aus rohen Tick-Differenzen; Ticks sind zusätzlich event-getrieben, dt bis ~10 s), `window_auto.py:27` (EMA-Gewicht 0,8 auf das **neue** Sample), `window_auto.py:23/30` (Schwelle −3,0 bzw. adaptiv min. 2,0 K/h).
**Mechanik:** Ein einzelner 0,1-K-Quantisierungsschritt in einem 60-s-Tick ergibt −6 K/h; die EMA springt auf 0,8·(−6) = −4,8 → Fehlalarm nach **einem** Sample. Ein normal auskühlender Raum (0,5 K/h) mit üblichem Zigbee-Sensor (Aqara, Sonoff SNZB, 0,1-K-Auflösung) produziert damit wiederkehrende „Fenster offen"-Fehlalarme → Heizabfall auf den Floor, EKF-Lernpausen, TRV-Thrash. Bei aktiver Kühlung (−2…−6 K/h real) entsteht ein Grenzzyklus: AC kühlt → „Fenster offen" → AC aus → Raum erwärmt sich → wieder an. In Kombination mit V1 doppelt kritisch.
**Fix-Skizze:** Slope zwischen *Sensor-Updates* statt pro Tick rechnen; N konsekutive Ticks unter Schwelle fordern; Detektion bei `hvac_action == "cooling"` unterdrücken oder das Vorzeichenmodell spiegeln.
**Zusatzbefund (verifiziert):** Ist ein Fenstersensor konfiguriert, wird der Detektor nie mehr gesteppt (`coordinator.py:711-712`), aber sein **persistierter** `open`-Zustand fließt weiter per OR in `effective_window_open` ein — ein gespeichertes `auto_open=True` hängt nach Nachrüsten eines Fenstersensors für immer (nur der Bypass-Switch hilft).

### V7 — HOCH: Reconfigure-Flow hat drei reale Defekte
**Stellen:** `config_flow.py:429-432, 443-445, 448`, `coordinator.py:434-436`.
**(a) Optionale Felder sind unlöschbar:** `async_update_reload_and_abort(data_updates=user_input)` **merged**; entfernte Keys (Fenstersensor, Wetter, Boiler-Actions!) bleiben in `entry.data`. Konsequenz beim Hub: Wer die Kessel-Actions leert, um laut Doku auf „shadow-only" zurückzugehen, schaltet den Kessel real weiter.
**(b) Options beschatten Data:** Das Reconfigure-Formular prefillt und schreibt nur `entry.data`, der Coordinator liest `{**data, **options}` — nach dem ersten Options-Save sind Reconfigure-Änderungen an überlappenden Feldern (category, comfort_base, …) wirkungslos, das Formular zeigt veraltete Werte.
**(c) `climate_mode` wird vom Store zurückgedreht:** Reload nach Reconfigure persistiert erst den alten In-Memory-Wert und `async_bootstrap` (coordinator.py:434-436) restauriert ihn über den frisch konfigurierten `CONF_CLIMATE_MODE` — das Feld hat nach Reload nie Effekt.
**Fix-Skizze:** Reconfigure auf Vollersatz (`data=user_input`) umstellen; überlappende Keys aus dem Options-Flow beim Reconfigure mitschreiben oder Options leeren; `climate_mode` beim Reload aus `entry.data` priorisieren.

### V8 — MITTEL: Wetter-Forecast-Call ohne Timeout unter dem Tick-Lock
**Stelle:** `coordinator.py:668-674` — `weather.get_forecasts` mit `blocking=True, return_response=True`, ohne `asyncio.timeout`, aufgerufen innerhalb von `_run_once` unter `self._lock` (Kontrast: Hub-Boiler-Call hat 10-s-Timeout).
**Wirkung:** Eine hängende Weather-Integration friert den kompletten Zonen-Tick ein (kein Setpoint, kein Frost-Update, keine Failure-Erkennung); der Hub droppt die Zone nur via Staleness.
**Fix:** `async with asyncio.timeout(10):` analog zum Hub.

### V9 — MITTEL: Frozen-Sensor-Pfad pinnt den Kesselbedarf; „unavailable" hat keinen Safe-State
**Stellen:** `coordinator.py:1142-1147` (frozen erzwingt `mode="heat"`), `coordinator.py:1215` (`heating = enabled ∧ ¬window ∧ mode=="heat"` → True), Hub `count_threshold` Default 1; `coordinator.py:892-901` (unavailable → Tick-Abbruch ohne Setpoint-Korrektur).
**Wirkung:** (a) Eine Zone mit eingefrorenem Sensor meldet dem Hub dauerhaft Wärmebedarf → gemeinsamer Kessel läuft/taktet unbegrenzt gegen geschlossene Ventile. (b) Bei `unavailable` hält der Aktor den letzten Setpoint unbegrenzt (stirbt der Sensor während Boost, bleibt Boost); im External-Sensor-Modus regelt das TRV gegen den letzten gefütterten Wert. Zwei Philosophien für denselben Fehlertyp, beide ohne Zeitlimit.
**Fix-Skizze:** `sensor_frozen`/Degradationsflags in den ZoneRequest aufnehmen und im Aggregat ausschließen; `unavailable` nach N Minuten auf denselben Safe-State wie `frozen` degradieren.

### V10 — MITTEL: Manueller Override wird still ins Komfortband geklemmt
**Stelle:** `tick_resolve.py:83` — `min(max(override, heat_sp), cool_sp)`.
**Wirkung:** Nutzer stellt 17 °C ein (bewusst sparsam), geschrieben werden 20+ °C; die Climate-UI akzeptiert den Wunschwert, das Gerät bekommt einen anderen — ohne jedes Feedback (kein `override_clamped`-Attribut). Zusammen mit V3 existiert **kein** Weg zu einer bewussten Tiefabsenkung außer OFF (das wiederum V4 auslöst). Normativ wäre nur die Frost-/Schimmel-Klemme geboten; die Bandklemme ist eine Produktentscheidung, die dem Erwartungsmodell „Thermostat" widerspricht und als Defekt wahrgenommen wird.
**Fix-Skizze:** Override nur gegen HEALTH-Floors klemmen (oder Option „Norm-Modus streng/locker"); mindestens `override_clamped` als Attribut + Card-Hinweis.

### Weitere selbst verifizierte Punkte (niedriger)

- **`pyproject.toml` Version 0.106.0** vs. 0.110.0 überall sonst; der CI-Versions-Guard prüft pyproject nicht (ci.yml:104-113).
- **Doppelte Zeitverbuchung in Diagnose-Pfaden:** `_tick_min = TICK_INTERVAL_S/60` und `dt_h=TICK_INTERVAL_S/3600` werden pro `_run_once` verbucht, obwohl Ticks zusätzlich event-getrieben laufen (Debounce ~10 s) — Outcome-Scoring-Minuten und PI-Shadow-Integrator laufen bis ~6× zu schnell (`coordinator.py:1556, 1459`). Nur Diagnose/Shadow, aber genau diese Werte sollen die Live-Flip-Evidenz liefern.
- **`_resolve_device_guards` ist one-shot** (coordinator.py:536): Nach dem ersten Tick gepaarte TRV-Entities (Valve, ext-Temp, Batterie) bleiben bis zum HA-Neustart unerkannt.

### Plausible Befunde aus der Agenten-Analyse (nicht einzeln nachgeprüft)

Übereinstimmend von mehreren unabhängigen Lesern gemeldet, mit Datei:Zeile belegt, aber in dieser Runde nicht manuell verifiziert — als Backlog-Kandidaten dokumentiert:

- **Optimal-Start/-Stop ohne Latch** → Preheat-/Coast-Chattering, wenn das reale Aufheizen vom Modell abweicht (`optimal_start.py:165/197`).
- **`identified`-Gate prüft keine Parameter-Kovarianzen** — nur Beobachtungszähler + Temperatur-Std; bei trägen Gebäuden (τ 30–50 h) gilt das Modell nach ~80 min als „identifiziert", obwohl α unkonvergiert ist (`thermal_ekf.py:322-328`).
- **Seasonless-Prior mit ~4× Quantisierungsbias** bei 0,1-K-Sensoren (Selektionsfilter `rate > 0` auf Tick-Differenzen, `coordinator.py:743`, `seasonless_rate.py:72-74`).
- **Heating-Failure-Fehlalarme bei Fußbodenheizung** (fixe 35 min/0,2 K, nicht ans Dynamikprofil gekoppelt, `safety/heating_failure.py`).
- **Schimmelfloor entfällt still bei RH-Sensor-Ausfall** (kein Repair-Issue, `coordinator.py:993`).
- **Kleine Floor-Anhebungen können dauerhaft im Write-Deadband verschluckt werden** (`tick_resolve.py:134` + 0,5-K-Step-Snapping).
- **Running-Mean: mehrtägige Lücken kollabieren zu einem Rekursionsschritt** (`running_mean.py:66`); T_rm tagelang verzerrt nach Ausfällen.
- **DST-Sprünge verschieben Optimal-Start um ±60 min** (lokale Minutenrechnung, `coordinator.py:624`); naive Forecast-Zeitstempel werden als UTC interpretiert (`optimal_start.py:217`).
- **Unload-Race:** State-Listener lebt während `async_persist_and_cleanup` weiter; ein später Tick kann Notifications/Issues nach dem Cleanup neu erzeugen (`__init__.py`/coordinator).
- **Über-Eis-Sättigung fehlt in der Psychrometrie** (unter 0 °C ~10 % Fehler der Oberflächen-RH — Schimmelkriterium an Frostflächen unkonservativ, `psychrometrics.py`).
- **Load-Shedding rechnet freigesetzte Leistung mit voller `declared_power`** statt moduliertem Anteil; W/kW-Einheiten unvalidiert (`hub_aggregate.py:284`).
- **EN-16798-Detailabweichungen:** Cat-I-Kühlband 23–25 statt 23,5–25,5; untere adaptive Grenze wird bis T_rm=30 statt 25 °C angewendet ohne `extrapolated`-Flag (`en16798.py:43-79`).
- **Card:** +/−-Buttons clampen nicht auf min/max (ServiceValidationError-Toast), History lädt genau einmal (Wandtablet zeigt veraltete 24 h), °C hart codiert, Ampel-Level nur über Farbe (WCAG 1.4.1), Editor deckt Monitoring-Optionen nicht ab.
- **hassfest/HACS-Actions auf `@master`/`@main` gepinnt** — widerspricht der eigenen Pinning-Disziplin (ci.yml:14/16).
- **ADR-Register-Drift:** README-Tabelle vs. ADR-Header vs. Code bei ADR-0044/0050 inkonsistent; die seit v0.107.0 **live** geschaltete Dry-Aktuierung fehlt in der README-„Active"-Liste — Nutzer können nicht mehr allein aus dem README ablesen, was real schaltet.

---

## 4. Subsystem-Kurzbewertungen

| Subsystem | Reife | Kernbefund |
|---|---|---|
| **Laufzeit-Kern** (coordinator, storage, clock) | ★★★★☆ | Fail-closed-Disziplin und Persistenz stark; God-Method-Regression, Degradationsleiter für den Raumsensor nicht ausgeführt |
| **HA-Oberfläche** (climate, sensor, config_flow, i18n) | ★★★★☆ | Entity-Konventionen vorbildlich (has_entity_name, entity_category, PARALLEL_UPDATES, Repair-Issues, ehrliches quality_scale.yaml); 23-Felder-Monoform, Reconfigure-Defekte (V7), ~65 Climate-Attribute = Recorder-Last |
| **Regelung** (control/) | ★★★★☆ | Shadow-Disziplin und pure Zustandsmaschinen exzellent; Anti-Windup nur Akku-Klemme, keine Hysterese im MPC-Controller-Seam, kein Preheat/Coast-Latch, toter Code (TpiLearner, calibration, residual_fraction) |
| **Komfort** (comfort/) | ★★★★☆ | Normkern korrekt (nachgerechnet); Setback-Clamp (V3), Referenzrahmen-Mischungen Luft/operativ in Shadow-Pfaden, f_Rsi nicht konfigurierbar |
| **Schätzung** (estimation/) | ★★★★☆ | EKF-Mathematik korrekt (Jacobian per Finite-Differenzen bestätigt); Lernpausen-Poisoning (V5), identified-Gate zu optimistisch, Seasonless-Quantisierungsbias |
| **Multizonen + Sicherheit** | ★★★☆☆ | Aggregat/Staleness/Frost-Plausibilität stark; Kessel-Aktuierung (V2) ist der am wenigsten neustartfeste Teil mit physischer Wirkung — genau der falsche Ort dafür |
| **Lovelace-Card** | ★★★★☆ | Pure-Math-Module + Lit, 42 KB/14 KB gzip, A11y-Dial, Auto-Registrierung mit Versionsstempel = Klassenbester unter HACS-Karten; Editor unvollständig, History einmalig, nur de/en, kein °F |
| **Tests/CI/Doku** | ★★★★★ | 571/571 grün, zwei Coverage-Gates, Collection-Guard, Non-Goals als Tests, Live-Bugs als datierte Regressionstests; Lücken: Plant ohne Rauschen/Quantisierung, keine Golden Files (ADR-0011 zu großzügig „implementiert"), ADR-Status-Drift |

---

## 5. Norm-Konformität (Ist-Stand)

| Norm/Regel | Status in v0.110.0 |
|---|---|
| **EN 16798-1** (Kategorien, adaptives Modell) | Bänder & Gl. B.1/B.2 korrekt implementiert und referenzgetestet; adaptives Band nur Shadow (bewusst, README-ehrlich). Abweichungen: Cat-I-Kühlband 0,5 K, untere Adaptivgrenze über T_rm=25 hinaus, Feuchtegrenzen (60/40 fix) nicht kategoriegebunden, kein absolutes 12-g/kg-Kriterium, keine Anhang-C-Langzeitbewertung |
| **DIN 4108-2 / EN ISO 13788** (Schimmel) | f_Rsi=0,7-Inversion und 80-%-Kriterium korrekt; 24-°C-Kappung transparent (`mold_capped`). Lücken: f_Rsi fix (Altbau!), Über-Eis-Sättigung fehlt, Floor entfällt still ohne RH-Sensor, Outdoor-Fallback 5 °C ist Fiktion ohne Außensensor |
| **ISO 7730 / EN ISO 7726** (PMV/PPD, operativ) | Operative Temperatur nach ISO-7726-Gewichtung korrekt; PMV/PPD, Zugluft (DR), Strahlungsasymmetrie, Fußbodentemperatur fehlen vollständig; Luftgeschwindigkeit fix 0,1 m/s |
| **ASR A3.5** (Arbeitsstätten) | 26-°C-Heizsollwert-Cap unbedingt umgesetzt und getestet (inkl. Cooling-Aussparung); die ASR-Stufenlogik (+26/+30/+35 mit Maßnahmenpflichten) existiert nur rudimentär als Opt-in-Hard-Cap |
| **EN 15500-1 / EN ISO 52120-1** (Regelgüte, GA-Klassen) | Keine CA-Metrik, keine Klassendeklaration. Funktional liegen Klasse-A-Bausteine vor (Einzelraumregelung mit Bedarfsführung, Optimal Start/Stop), aber solange MPC/TPI Shadow sind, ist die wirksame Regelgüte die des Setpoint-Durchgriffs — ein Klassifizierungsanspruch wäre heute nicht belegbar |
| **GEG §63** (raumweise Regelung) | Poise *ist* eine selbsttätig wirkende Einrichtung zur raumweisen Regelung — grundsätzlich anschlussfähig; keine Doku, die diese Einordnung/Grenzen (Software auf HA, keine bauaufsichtliche Eignung) erklärt |

---

## 6. Reale Nutzbarkeit im Smart Home

**Für wen es heute funktioniert:** Heizzentrierte Haushalte mit TRVs (Zigbee/Z-Wave, insbes. Sonoff TRVZB), freistehendem Raumsensor, optional Feuchte-/Außensensor. Setup-Aufwand ist niedrig (2 Pflicht-Entities, Rest Default), die Degradation ohne optionale Sensoren ist definiert, die Batterieschonung (Deadband/Snapping/Throttle) ist besser als bei praktisch allen naiven Setpoint-Automationen. Repair-Issues mit Handlungsanweisungen (en/de) sind vorbildlich.

**Was Nutzer heute überrascht (Erwartungsbrüche):**
1. Manuelle Sollwerte springen zurück (Band-Klemme V10 + 2-h-Auto-Revert) — normgetreu, aber ohne UI-Erklärung wirkt es defekt.
2. Nachtabsenkung tut fast nichts (V3) — das UI-Feld „Setback 3 K" verspricht etwas, das der Solver kassiert.
3. OFF schaltet nichts ab (V4).
4. Ohne Außensensor rechnen Schimmelfloor/EKF/Optimal-Start mit einer 5-°C-Konstante — ohne Hinweis.
5. Fenster-Fehlalarme bei üblichen 0,1-K-Sensoren (V6) äußern sich als unerklärliche Heizaussetzer.

**Rote Linien heute:** Kühlgeräte (V1+V6) und Kessel-Aktuierung (V2). Beides sollte bis zum Fix nur beobachtend betrieben werden (der Diagnose-Default des Hubs ist korrekt gewählt).

**Hardware-Abdeckung:** Der generische Setpoint-Pfad deckt jede `climate`-Entity ab; die Premium-Features (Direktventil, External-Temp, running_state) sind TRVZB-lastig. Capability-Discovery aus advertised Modes (statt Hardcoding) ist zukunftsfähig, auch Richtung Matter-TRVs (Eve, Tado X), deren externe Sensor-Kopplung limitiert ist — genau dort ist der External-Temp-Feed/PI-Kompensator-Ansatz wertvoll.

## 7. Reale Nutzbarkeit im Smart Office

- **Fachlich anschlussfähig:** ASR-A3.5-Cap, EN-Kategorien, CO₂-Ampel (Monitoring-only, saubere Abgrenzung nach ADR-0048) und die geplante Klasse-A-Funktionalität (Optimal Start/Stop, bedarfsgeführte Erzeugerkoordination) treffen Office-Anforderungen.
- **Operativ fehlt:** Bulk-/Template-Onboarding (jede Zone ist ein manueller Flow — bei 20 Räumen inakzeptabel), Belegungs-/Kalenderkopplung (Wochenprofile existieren nur als tägliches Komfortfenster), Regelgüte-/Compliance-Reporting (EN-Anhang-C-Statistik, CA-Metrik) und eine Antwort auf die Recorder-Last: ~65 sich minütlich ändernde Climate-Attribute × 15 Sensoren × N Zonen skaliert schlecht; `always_update=True` verschärft das.
- **Die Heating-Failure-Fehlalarm-Charakteristik bei trägen Systemen** (FBH ist im Office-Neubau Standard) erzeugt Alarm-Fatigue.

## 8. Testlage

Der Testlauf dieser Analyse: **571/571 bestanden** (532 Pure-Core in 1,9 s; 39 HA-Integrationstests gegen echte `pytest-homeassistant-custom-component`-Runtime), Coverage-Gates beide grün (98,79 % / 86,28 %), drei Läufe deterministisch, Card 23/23. Stolperfalle: das nackte `pytest tests/` liefert 39 Setup-ERRORS, weil `asyncio_mode=auto` nur in CI-Optionen gesetzt ist — DX-Fix lohnt.
Wesentliche Lücken: Die RC-Plant ist rauschfrei (keine Sensor-Quantisierung, keine Aktor-Totzeit, keine 2. Masse) — genau die Bedingungen, unter denen V5/V6 entstehen, werden closed-loop nicht getestet; die in ADR-0011 versprochenen Golden-File-Replays realer Trajektorien existieren nicht; der Live-Pfad (`_run_once`) hängt allein an den Integrationstests.

## 9. Sofortmaßnahmen (P0, vor jedem weiteren Feature)

1. **V1** Kühlrichtungsbewusste Fenster-/Frozen-Reaktion (Sicherheit).
2. **V2** Kessel-Robustheit: ON-Fehlschlag, BoilerState-Persistenz/Reconcile, Unload/Stop-OFF, Keepalive-Default (Sicherheit).
3. **V4** OFF-Semantik: definierter Abschaltzustand + Frost-Floor bei OFF (Sicherheit).
4. **V3** Setback vom Kategorieband entkoppeln (Kernversprechen Energie).
5. **V5** Lernpausen-Terminierung (Ein-Zeiler; Kernversprechen Lernen).
6. **V6** Fenster-Detektor härten (Fehlalarme; Voraussetzung für Vertrauen).
7. **V7** Reconfigure-Fixes (a–c) — insbesondere (a), weil Kessel-Actions sonst nicht deaktivierbar sind.
8. **V8** Forecast-Timeout (drei Zeilen).
9. `pyproject`-Version in den CI-Guard aufnehmen; README-„Active"-Liste um Dry-Aktuierung ergänzen; ADR-Status 0044/0050 konsolidieren.

Alle P0-Punkte sind lokalisiert, klein und mit der vorhandenen Testinfrastruktur absicherbar. Die strategische Weiterentwicklung ist in `docs/roadmap/ROADMAP-STRATEGIE.md` ausgearbeitet.
