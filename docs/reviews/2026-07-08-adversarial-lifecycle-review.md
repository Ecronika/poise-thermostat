# Adversariales Lifecycle-Review — HA-Integration Poise

**Datum:** 2026-07-08 · **Scope:** `manifest.json`, `custom_components/poise/__init__.py`
(`async_setup`, `async_setup_entry`, `async_unload_entry`, `async_remove_entry`,
`async_migrate_entry`) und alle direkt erreichten Nachbarmodule
(`coordinator.py`, `hub_coordinator.py`, `migration.py`, `storage.py`,
`config_flow.py`, `config_reconcile.py`, `actuator.py`, `binary_sensor.py`,
`frontend/__init__.py`) · **Referenz-HA:** 2024.12.5 (Framework-Annahmen gegen
den installierten HA-Core-Quellcode geprüft; empirische Befunde mit
`pytest-homeassistant-custom-component` unter Python 3.12 reproduziert)

**Methode:** (1) lokale Prüfung des Lifecycle-Codes, (2) gezieltes Lesen des
umliegenden Codes (Eingaben, Aufrufstellen, Seiteneffekte, Persistenz,
Aktorwirkung), (3) Findings mit Schweregrad. Acht adversariale Review-Linsen
(Setup-Raum, Setup-Hub, Migration, Unload/Persistenz, Remove/Safety,
Shadow-Grenzen, Doku-vs-Code, Testlücken); jede tragende Behauptung wurde gegen
den tatsächlichen Code bzw. den HA-Core-Quellcode verifiziert, die zwei
wichtigsten zusätzlich empirisch per Integrationstest. Kommentare, README und
ADRs wurden grundsätzlich **nicht** als Wahrheit akzeptiert.

**Schweregrade:** kritisch / hoch / mittel / niedrig ·
**Kennzeichnung:** sicherer Fehler / begründeter Verdacht / fehlender Kontext /
Testlücke / Verbesserungsvorschlag

---

## 1 Findings

### F1 · hoch · sicherer Fehler — Unavailable-Safe-State schreibt Setpoint ohne Modus-Wechsel; `hvac_mode` wird im Aktuator-Pfad verworfen

- **Betroffen:** `coordinator.py:1114-1162` (`_write_unavailable_safe_state`), `actuator.py:24-29` (`service_call_for`)
- **Grenzverletzung:** *heat-only vs reversible cooling* (KI-typisch: `ActuatorCommand` hat ein `hvac_mode`-Feld, der Pfad verlässt sich darauf — aber `service_call_for` emittiert für `SETPOINT` nur `{entity_id, temperature}`)
- **Begründung:** Nach 30 min Sensorausfall schreibt der Safe-State-Pfad ein
  `ActuatorCommand(..., hvac_mode="heat")` — `service_call_for` verwirft das
  Feld jedoch stillschweigend. Beide Nachbarpfade haben den nötigen separaten
  `set_hvac_mode`-Nudge (Normaltick `coordinator.py:1770 ff.`, Frost-Rescue
  `coordinator.py:1899 ff.`), **nur dieser Pfad nicht** — obwohl sein Docstring
  behauptet, er „spiegele" den Frozen-Sensor-Safe-State. Zusätzlich: (a) der
  Idempotenz-Check `already` (Z. 1135-1138) verlangt `act.state == "heat"` und
  kann für Geräte in `cool`/`auto`/`off` nie wahr werden → **Rewrite jeden
  60-s-Tick**; (b) `self._last_written_mode = "heat"` (Z. 1152) wird gesetzt,
  ohne dass der Modus je kommandiert wurde → nach Sensor-Rückkehr rechnet der
  Mode-Nudge (`mode_changed = final_mode != self._last_written_mode`, Z. 1792)
  mit einem falschen Ausgangszustand.
- **Realbetriebsschaden:** Sommer, reversibles Splitgerät im Modus `cool`,
  Batteriesensor fällt aus → nach 30 min kommandiert Poise
  `set_temperature(max(7 °C, min_temp≈16 °C))` bei unverändertem Modus `cool`
  → das Gerät **kühlt aktiv Richtung Geräteminimum**, minütlich neu bestätigt
  (Zigbee-/Batterie-Schreibsturm). Winter-Variante: TRV im Zustand `off`
  erhält nur den Setpoint, das Ventil bleibt zu → **der versprochene
  Frost-Floor greift nicht** („fail toward warmth" gebrochen).
- **Repro/Test:** Reversibles `climate`-Entity in `cool`
  (`hvac_modes=['heat','cool']`, `min_temp=16`), Temp-Sensor > 30 min
  `unavailable`, zwei Ticks: erwartet `set_hvac_mode('heat')` + genau ein
  Setpoint-Write; ist: kein Mode-Call, zwei identische Setpoint-Writes.
- **Absicherung:** keine weitere nötig — Code-Widerspruch vollständig belegt.

### F2 · hoch · sicherer Fehler — Live-Kesselsteuerung hängt am Entity-Listener einer einzigen abschaltbaren *Diagnose*-Entity

- **Betroffen:** `binary_sensor.py:53-66` (einzige Hub-Entity, `EntityCategory.DIAGNOSTIC`), `hub_coordinator.py` (Aktuierung im Tick), HA-`DataUpdateCoordinator`-Semantik
- **Grenzverletzung:** *diagnostic only vs live* — der Docstring nennt die Entity „diagnostic only", tatsächlich hält ihr Listener die **live Boiler-Aktuierung** am Leben
- **Begründung:** Der HA-`DataUpdateCoordinator` plant Refreshes nur, solange
  mindestens ein Entity-Listener registriert ist (verifiziert in
  `homeassistant/helpers/update_coordinator.py`: `_unschedule_refresh()` beim
  Entfernen des letzten Listeners). Die Hub-Plattform erzeugt genau **eine**
  Entity — als Diagnose-Entity per UI deaktivierbar. Deaktiviert ein Nutzer
  sie, läuft nach dem nächsten Reload nur noch der `first_refresh` aus dem
  Setup; danach tickt der Hub **nie wieder**: kein Keepalive, kein
  Min-Cycle, kein OFF bei wegfallender Anforderung.
- **Realbetriebsschaden:** Kessel wird vom ersten (einzigen) Tick EIN
  geschaltet und bleibt **unbegrenzt AN**, ohne dass irgendetwas in der UI
  darauf hindeutet — ungewolltes Dauerheizen.
- **Repro/Test:** Hub mit Boiler-Aktionen aufsetzen, `binary_sensor` im
  Entity-Registry deaktivieren, Entry neu laden, Demand-Wechsel simulieren →
  erwartet: Kessel folgt; ist: kein weiterer Tick nach `first_refresh`.
- **Absicherung:** keine — HA-Semantik direkt aus dem HA-Quellcode belegt.
  Fix-Richtung: eigener Tick über `entry.async_create_background_task` bzw.
  listener-unabhängige Intervallplanung, sobald Aktuierung aktiv ist.

### F3 · hoch · sicherer Fehler — Löschen eines Raum-Entries parkt den Aktuator nicht (empirisch bewiesen)

- **Betroffen:** `__init__.py:152-155` (`async_remove_entry`: early return für Nicht-System-Entries); kein kompensierender Teardown in `climate.py`/`coordinator.py`
- **Begründung:** `async_remove_entry` behandelt nur den Hub. Für Raum-Entries
  schreibt kein Teardown-Pfad (Entity-Removal, Unload, Remove) einen sicheren
  Endzustand auf den Aktuator. **Empirisch bewiesen** durch den neuen
  strict-xfail-Test `test_remove_room_entry_parks_actuator`
  (`tests/integration/test_lifecycle_adversarial.py`): beim Löschen wird kein
  `set_hvac_mode('off')`/Safe-Setpoint gesendet.
- **Realbetriebsschaden:** Ein TRV/Heiz-Switch, der beim Löschen gerade
  „heizen" kommandiert hat, **heizt unbeaufsichtigt weiter** — niemand regelt
  nach. Sondervariante: Löschen während des Safe-State parkt das TRV dauerhaft
  auf dem Frost-Floor (7 °C) → Raum bleibt kalt.
- **Repro/Test:** vorhanden (xfail, strict); nach dem Fix `xfail` entfernen.
- **Absicherung:** Produktentscheidung nötig, *welcher* Endzustand gewünscht
  ist (off vs. neutraler Komfort-Setpoint) — das Review markiert nur, dass es
  heute **keinen** gibt.

### F4 · hoch · sicherer Fehler — Hub-Disable/-Unload lässt einen eingeschalteten Kessel zurück; Boiler-OFF existiert nur im Remove-Pfad

- **Betroffen:** `__init__.py:137-141` (Hub-Unload: nur `async_unload_platforms`), `__init__.py:152-169` (OFF nur in `async_remove_entry`)
- **Begründung:** Deaktivieren des Hub-Eintrags in der UI (= Unload ohne
  Remove) oder ein fehlgeschlagener Reload (Unload ok, Setup wirft) hinterlässt
  den Kessel im letzten kommandierten Zustand — ohne Keepalive, Min-Cycle oder
  OFF. Der Docstring „switch its boiler off so it is not left running" gilt nur
  für endgültiges Löschen.
- **Realbetriebsschaden:** Kessel bleibt nach einem Disable/fehlgeschlagenen
  Reload unbegrenzt AN — ungewolltes Heizen im ganzen Haus.
- **Repro/Test:** Hub mit Boiler-ON-Zustand →
  `async_set_disabled_by(USER)` → erwartet: OFF-Action; ist: kein Call
  (Plain-Reload-Fall ist bewusst KEIN Off — siehe neuer Test
  `test_unload_hub_does_not_fire_boiler_off`; die saubere Unterscheidung ist
  `entry.disabled_by is not None` im Unload).
- **Absicherung:** keine — Codepfade vollständig gelesen
  (`hub_coordinator.py` hat weder `async_shutdown`-Override noch
  Unload-Hook mit OFF).

### F5 · hoch · sicherer Fehler — Nutzer-Intent wird bei ausgefallenem Raumsensor nie persistiert

- **Betroffen:** `coordinator.py:445-468` (Setter setzen nur `_dirty`), `coordinator.py:1188-1193` (Early-Return bei `air is None`), `coordinator.py:1927` (einzige `_maybe_save`-Stelle im Normalpfad)
- **Begründung:** `set_enabled`/`set_override`/`set_preset`/`set_climate_mode`
  persistieren nichts selbst — sie markieren `_dirty` und verlassen sich auf
  den Tick. Ist der Raumsensor `unavailable`, kehrt `_run_once` **vor**
  `_maybe_save` zurück; da bei HA-Stop kein Unload läuft (F7), geht der Intent
  beim Neustart verloren.
- **Realbetriebsschaden:** Nutzer schaltet Poise für einen Raum ab (defekter
  Sensor!), HA startet neu → Poise ist **wieder aktiv** und regelt — exakt in
  der Situation (Sensorproblem), in der der Nutzer es abgeschaltet hatte.
  Auch Override/Preset gehen verloren.
- **Repro/Test:** Sensor `unavailable`, `switch.*_enabled` aus, HA-Restart
  simulieren (Entry neu laden ohne Unload-Save bzw. Store inspizieren) →
  `enabled` im Store noch `True`.
- **Absicherung:** keine — Setzstellen und Save-Pfade vollständig belegt.
  Fix-Richtung: bei `_dirty` sofort (debounced) speichern, unabhängig vom
  Tick-Erfolg.

### F6 · hoch · begründeter Verdacht — TRV bleibt nach Unload/Remove auf Sensorquelle „external" mit eingefrorenem Messwert

- **Betroffen:** `coordinator.py:1840-1877` (Tick schaltet `select` auf `external` und füttert `number`-Entity); kein Teardown-Pfad stellt zurück
- **Begründung:** Der Tick schaltet den TRV-internen Sensor-Select auf
  `external` und schreibt die reale Raumtemperatur in die External-Temp-Number.
  Weder `async_unload_entry` noch `async_remove_entry` noch Entity-Teardown
  setzen den Select auf „internal" zurück oder beenden die Fütterung sauber.
- **Realbetriebsschaden:** Nach dem Entfernen regelt das TRV **gegen den
  letzten eingefrorenen externen Messwert**: War zuletzt 18 °C gefüttert und
  der Raum erwärmt sich, glaubt das TRV dauerhaft an 18 °C und heizt über.
  („Verdacht", weil einzelne Firmwares nach Stunden auf intern zurückfallen —
  das ist gerätespezifisch und nicht garantiert.)
- **Repro/Test:** Raum-Entry mit `select`-Sensorquelle + External-Number
  aufsetzen, Entry entfernen → erwartet: `select_option('internal')` (oder
  dokumentiertes Verhalten); ist: nichts.
- **Absicherung:** Geräteverhalten (z. B. Sonoff TRVZB Fallback-Timeout) für
  die Ziel-Hardware dokumentieren.

### F7 · mittel · sicherer Fehler — Kein Persistenz-Flush bei HA-Stop; ADR-0007 und Code-Kommentar widersprechen dem Code

- **Betroffen:** `__init__.py:147` (Kommentar „no learning loss"), `coordinator.py:1011-1019` (`_maybe_save`, zählerbasiert), gesamte Integration (kein `EVENT_HOMEASSISTANT_STOP`-Handler; grep leer)
- **Doku-Widerspruch:** ADR-0007 entscheidet wörtlich „Throttle = Debounce …
  **Flush bei `HOMEASSISTANT_STOP`** — … kein Verlust beim Shutdown". Umgesetzt
  ist ein Zähler (alle `EKF_SAVE_EVERY_TICKS=30` Ticks à 60 s) ohne Stop-Flush.
  HA ruft bei Stop **kein** `async_unload_entry` auf (verifiziert:
  `config_entries.py:1976-1986`, `_async_shutdown` → nur
  `entry.async_shutdown()`), der „final save" im Unload greift also bei jedem
  normalen Neustart nicht.
- **Realbetriebsschaden:** Bis zu ~30 min EKF-/Statistik-Lernen pro Neustart
  verloren (bei täglichen Neustarts systematischer Lern-Schwund); zusammen mit
  F5 auch Verlust von Nutzer-Intent.
- **Repro/Test:** Tick 10× laufen lassen, HA stoppen (ohne Unload) → Store
  enthält den Stand von Tick 0.
- **Absicherung:** keine — ADR-Text, Code und HA-Verhalten liegen vor.

### F8 · mittel · sicherer Fehler — Erster Hub-Tick nach HA-Start schaltet den Kessel AUS, bevor die Zonen geladen sind

- **Betroffen:** `hub_coordinator.py:132-172` (`_collect_requests` filtert Zonen ohne `runtime_data`/frischen Snapshot), `control/hub_aggregate.py:313-320` (`BoilerState.last_switch_mono = -1.0e9`, „allow an immediate first switch"), `__init__.py:77` (`first_refresh` im Hub-Setup)
- **Begründung:** Beim HA-Start ist die Setup-Reihenfolge der Entries
  unbestimmt. Läuft der Hub-`first_refresh`, bevor Zonen `runtime_data`
  publiziert haben, ist `requests == []` → Demand inaktiv. Die
  V2b-Reconciliation erkennt den physisch laufenden Kessel korrekt als AN —
  und `step_boiler` schaltet ihn mangels Demand **sofort AUS** (Min-On kann
  nicht schützen: `last_switch_mono = -1e9`). Minuten später melden die Zonen
  wieder Bedarf → EIN nach Activation-Delay.
- **Realbetriebsschaden:** Ein Zwangs-AUS/EIN-Zyklus des Kessels **bei jedem
  HA-Neustart unter Heizlast** — Verschleiß (Anti-Short-Cycle-Ziel des ADR-0039
  konterkariert) und Komfortdelle.
- **Repro/Test:** Hub-Entry allein aufsetzen (Zonen noch nicht geladen),
  Boiler-Entity „on" → erwartet: Hub wartet eine Karenz (z. B.
  `HUB_ZONE_STALE_AFTER_S`) auf Zonen-Snapshots; ist: OFF-Call im ersten Tick.
- **Absicherung:** keine — rein aus Code ableitbar.

### F9 · mittel · sicherer Fehler — System-Hub-Entry erhält den Raum-Options-Flow; gespeicherte Optionen sind wirkungslos

- **Betroffen:** `config_flow.py:669-671` (`async_get_options_flow` unkonditional), `__init__.py:39-40` (`_async_options_updated` ignoriert System-Entries), `__init__.py:73-82` (Hub-Pfad registriert keinen Update-Listener), `hub_coordinator.py:96` (liest ausschließlich `entry.data`)
- **Grenzverletzung:** *local room zone vs system hub*
- **Begründung:** Der Hub-Eintrag zeigt in der UI den „Konfigurieren"-Dialog
  mit dem **Raum**-Tuning-Schema (Komfort, Zeitplan, Presence …). Gespeicherte
  Werte landen in `entry.options`, die der Hub nirgends liest; ein Listener
  fehlt ohnehin.
- **Realbetriebsschaden:** Nutzer glaubt, Systemeinstellungen geändert zu
  haben — nichts wirkt (falsche UI/Erwartung; die echten Hub-Parameter liegen
  nur im Reconfigure-Flow).
- **Repro/Test:** Options-Flow am Hub-Entry starten → erwartet: Abort oder
  Hub-Schema; ist: Raum-Schema.
- **Absicherung:** keine.

### F10 · mittel · sicherer Fehler — Raum-Reconfigure verwirft Anlagen-Struktur-Keys stillschweigend

- **Betroffen:** `config_reconcile.py:25-46` (`reconcile_reconfigure`: `new_data = dict(user_input)`, nur *Tuning* wird nach `options` gerettet), `config_flow.py` (Reconfigure-Schema zeigt Anlagenfelder situativ)
- **Begründung:** Das Reconfigure ersetzt `data` vollständig. Gerettet wird nur
  Tuning (`tuning_keys`); **strukturelle** Keys, die das Formular gerade nicht
  anbietet (`controls_boiler`, `declared_power`, `flow_temp`, `source_policy` —
  z. B. weil aktuell kein Hub-Entry existiert), fallen ersatzlos weg.
- **Realbetriebsschaden:** Nach „Hub kurz entfernt + Raum reconfiguriert +
  Hub neu angelegt" nimmt die Zone **nicht mehr an der Kesselanforderung
  teil** (`controls_boiler` weg) — der Raum wird bei zentraler Wärmequelle
  nicht mehr versorgt; die Frost-Exklusions-Warnung (N-2) ist dann die einzige
  Spur.
- **Repro/Test:** Raum mit `controls_boiler: True` → Hub-Entry löschen →
  Raum-Reconfigure durchlaufen → `entry.data[CONF_CONTROLS_BOILER]` fehlt.
- **Absicherung:** Bestätigen, unter welchen Bedingungen `_reconfigure_schema`
  die Anlagenfelder ausblendet (`config_flow.py:215 ff.`).

### F11 · mittel · sicherer Fehler — Fehlerhafte Boiler-Action-Strings degradieren still zu Shadow-only

- **Betroffen:** `hub_coordinator.py:103-105` (`parse_service_action` → `None` → `_actuation=False`), `config_flow.py:335-336` (freies `TextSelector` ohne Validierung)
- **Begründung:** Ein Tippfehler im Versatile-Format
  (`entity_id/domain.service`) wird nirgends validiert — weder im Flow noch
  per Repair-Issue. Der Hub rechnet dann kommentarlos nur im Schatten.
- **Realbetriebsschaden:** Nutzer konfiguriert Kesselsteuerung, Poise steuert
  **nie** — Haus bleibt kalt bzw. Kessel folgt nur der alten Fremdsteuerung;
  als Diagnose existiert allein das Attribut `actuation_enabled`.
- **Repro/Test:** Hub mit `boiler_on_action: "switch.boiler"` (ohne Service) →
  Flow akzeptiert; erwartet: Formularfehler oder Repair-Issue.
- **Absicherung:** keine.

### F12 · mittel · sicherer Fehler — `async_remove_entry` feuert Boiler-OFF auch bei Shadow-only-Konfiguration

- **Betroffen:** `__init__.py:161` (parst nur die OFF-Action), `hub_coordinator.py:105` (Aktuierung verlangt **beide** Actions)
- **Grenzverletzung:** *diagnostic only vs live* — Shadow-Code schreibt live
- **Begründung:** Im Tick gilt Aktuierung nur bei ON **und** OFF parsebar.
  Der Remove-Pfad prüft das nicht: Ist nur eine OFF-Action konfiguriert
  (Hub war immer Shadow-only), schaltet das Löschen des Entries einen Kessel
  aus, den **Poise nie kommandiert hat** (z. B. eine fremde Automation führt).
- **Realbetriebsschaden:** Einmaliges, unerwartetes Kessel-AUS beim Entfernen
  der Integration — mitten im Winter potenziell erst spät bemerkt.
- **Repro/Test:** Hub nur mit OFF-Action, Entry löschen → erwartet: kein
  Service-Call (Shadow war nie aktorisch); ist: `switch.turn_off`.
- **Absicherung:** Produktentscheidung: OFF beim Remove nur, wenn
  `_actuation` je aktiv war (z. B. beide Actions parsen).

### Niedrig eingestufte Findings

| ID | Kennzeichnung | Betroffen | Kern | Realbetriebsfolge |
|---|---|---|---|---|
| F13 | begründeter Verdacht (Doku-Nuance) | `__init__.py:89-97` | Guard-Kommentar verspricht „Fail with retry … not silently available=False" — Entities im Zustand `unavailable`/`unknown` passieren den Guard aber, und genau dann ist das Verhalten das „stille" `available=False`. Empirisch geprüft: **kein** Garbage-Write, Entity sauber `unavailable` → nur Kommentar/Verhalten inkonsistent. | falsche Erwartung beim Debuggen |
| F14 | begründeter Verdacht | `__init__.py:37-40`, `config_flow.py:758` | `update_listener` feuert bei **jeder** `async_update_entry` (HA-verifiziert) — beim Reconfigure läuft `async_apply_options` einmal mit neuen Options auf dem *alten* Coordinator, bevor der Reload greift. Transient, aber unnötige Doppel-Anwendung. | kurzzeitig inkonsistente Regler-Konfig |
| F15 | sicherer Fehler (Doku-Widerspruch) | `__init__.py:152-155`, `storage.py:26`, README:80 | README: Löschen „removes … stored learned model" — tatsächlich wird `poise_<entry_id>_ekf` (und Trace-Dateien) **nie** gelöscht (`Store.async_remove` fehlt in `async_remove_entry`). | Waisen-Dateien in `.storage`; README falsch |
| F16 | sicherer Fehler | `hub_coordinator.py:289-310`, `__init__.py:137-141` | Frost-Repair-Issue (`frost_zone_not_controlling_boiler`) wird nur beim *Bedingungswechsel im Tick* gelöscht; Hub-Unload/-Remove räumen es nie ab — die Issue-Registry ist persistent → Warnung überlebt die Deinstallation dauerhaft. | UI-Müll in „Reparaturen" |
| F17 | begründeter Verdacht | `coordinator.py` (`_active_issues` instanzlokal) | Nach Crash/Setup-Retry kennt die neue Coordinator-Instanz alte Issues nicht; Cleanup beim Unload löscht nur die eigenen. Selbstheilend, sobald ein Tick die Bedingung neu bewertet — Restfall: dauerhaft fehlschlagendes Setup. | veraltete Repair-Issues |
| F18 | Verbesserungsvorschlag | `manifest.json:4` | `after_dependencies: ["recorder"]` — kein Code nutzt den Recorder (grep leer). Toter Ordnungs-Hint, suggeriert Historien-Nutzung. | keiner (Doku-Hygiene) |
| F19 | sicherer Fehler | `diagnostics.py:24` | Diagnostics übergeben nur `entry.data` — nach der V2-Migration liegt das gesamte Tuning in `options` und fehlt im Diagnose-Dump; für Hub-Entries ist der Typ-Annotation-Cast (`PoiseCoordinator`) zudem falsch (funktioniert nur zufällig duck-typed). | Support-Dumps unvollständig |
| F20 | fehlender Kontext | `migration.py:80` | Migrations-Merge `{**data, **options}` lässt `options` auch für **strukturelle** Keys gewinnen (dokumentierte Absicht: „options … newer"). Ein verwaister V1-Options-Wert (z. B. alter `temp_sensor`) würde den aktuellen `data`-Wert dauerhaft ersetzen. Ob V1-Options strukturelle Keys enthalten konnten, ist aus dem Repo nicht belegbar. | potenziell falscher Sensor nach Migration |
| F21 | Verbesserungsvorschlag | `migration.py:78` | Hub-Erkennung per `entry_type is not None` statt `== ENTRY_TYPE_SYSTEM` (Rest des Codes prüft auf Gleichheit). Heute äquivalent; bricht, sobald je ein Raum-`entry_type` eingeführt wird. | Migration würde Räume überspringen |
| F22 | sicherer Fehler (Doku) | `config_flow.py:667`, ADR-0018 | Kein `MINOR_VERSION`, kein Migrations-Info-Log — das in ADR-0018 dokumentierte Versionierungsmuster ist nicht umgesetzt. | erschwerte Diagnose bei Migrationen |
| F23 | Verbesserungsvorschlag | `estimation/thermal_ekf.py:377-384` | EKF-`from_dict` verwirft bei `ekf_version`-Wechsel das gesamte Modell (inkl. Counter). Als Korruptions-Recovery dokumentiert (M8/ADR-0007) und bewusst — aber jeder künftige EKF-Versionsbump kostet alle Nutzer das komplette Lernmodell; Feld-Migration fehlt. | verlorenes Lernmodell bei Upgrade |
| F24 | Verbesserungsvorschlag | `coordinator.py:1016-1026` | Save-Fehler werden an beiden Stellen (periodisch + final) nur geloggt; ein dauerhaft defekter Storage degradiert unsichtbar zu Null-Persistenz. Repair-Issue nach N Fehlversuchen fehlt. | still verlorenes Lernmodell |
| F25 | begründeter Verdacht (Doku) | ADR-0038 (Status „Implementiert"), `hub_coordinator.py:12-13` | Code deklariert S3/S4 (Load-Shedding, Verdichtergruppen) selbst als „computed as diagnostics; zone-side enforcement is a later stage" — der ADR-Status „Implementiert" überzeichnet den Stand. | falsches Bild für Reviewer |
| F26 | sicherer Fehler (klein) | `binary_sensor.py:27-41` | `_ATTRS` exponiert `frost_zone`/`frost_excluded` nicht, obwohl der Hub sie liefert (ADR-0039-Diagnosen unvollständig an der Entity). | Diagnose-Lücke in der UI |
| F27 | begründeter Verdacht (präzisiert) | `__init__.py:164-169` | Boiler-OFF beim Remove mit `blocking=False`: `ServiceNotFound` wird synchron gefangen (empirisch getestet, Log vorhanden) — **Ausführungs**fehler des Service bleiben aber unbeobachtet; kein Retry beim letzten Schaltvorgang überhaupt. | OFF kann still scheitern |
| F28 | Testlücke | `__init__.py:143-149` | `async_unload_platforms == False` → weder Persist noch Cleanup; Verhalten ungetestet. | undefinierter Zustand nach Unload-Fehler |

---

## 2 Entkräftete Hypothesen (geprüft, kein Finding)

- **`entry.data[k]`-KeyError im Guard:** Config-Flow und Reconfigure erzwingen
  `temp_sensor` + `actuator` in `data` — nicht erreichbar.
- **Zombie-Tick nach Unload:** `DataUpdateCoordinator` entplant den Timer beim
  letzten Listener; Poise-eigene State-Listener laufen über
  `entry.async_on_unload` (`coordinator.py:662`). ✔
- **runtime_data-Reihenfolge:** vor `forward_entry_setups` gesetzt, korrekt. ✔
- **`unavailable`-Sensor beim Setup:** empirisch kein Aktuator-Write, Entity
  sauber `unavailable` (nur Kommentar-Nuance F13). ✔
- **Migration:** idempotent; Downgrade-Schutz (`version > 2 → False`) korrekt
  und jetzt getestet; Hub-Boiler-Actions liegen konsistent in `data` (keine
  Options-Drift im Remove-Pfad). ✔
- **Reconfigure ohne Reload:** beide Reconfigure-Zweige nutzen
  `async_update_reload_and_abort`. ✔
- **A10-Hot-Apply:** alle 24 Options-Formularfelder werden in
  `async_apply_options` gelesen — Kommentaranspruch hält. ✔
- **Karte/`async_setup`:** `add_extra_js_url` + versionierter Static-Path,
  keine Lovelace-Storage-Writes, Fehler blockiert Setup nicht (ADR-0040-
  konform); Websocket-Registrierung einmal pro Start. ✔
- **Shadow-Reinheit:** `multi/shadow.py`, `control/{pi,tpi,mpc}_shadow.py`,
  `trace/` enthalten keinerlei `async_call`/State-Writes (grep leer). ✔
- **CI-Silent-Skip:** CI hat einen Collection-Guard, der 0 gesammelte
  Integrationstests hart fehlschlagen lässt. ✔

---

## 3 Risiko-Matrix (sortiert nach Realbetriebsschaden)

| Schadensklasse | Finding | Schwere | Eintritt (typischer Betrieb) | Kennzeichnung |
|---|---|---|---|---|
| **Ungewolltes Kühlen** | F1 (Safe-State ohne Mode-Nudge, reversibles Gerät) | hoch | mittel — Sensorausfall ≥ 30 min im Kühlbetrieb | sicherer Fehler |
| **Ungewolltes Heizen** | F2 (Hub-Tick stirbt mit deaktivierter Diagnose-Entity) | hoch | niedrig–mittel — Diagnose-Entities werden real deaktiviert | sicherer Fehler |
| **Ungewolltes Heizen** | F3 (Raum-Löschung parkt Aktuator nicht) | hoch | mittel — jede Entry-Löschung bei aktivem Heizbefehl | sicherer Fehler (empirisch) |
| **Ungewolltes Heizen** | F4 (Hub-Disable lässt Kessel AN) | hoch | niedrig–mittel — Disable/Reload-Fehlschlag | sicherer Fehler |
| **Ungewolltes Heizen** | F5 (Disable-Intent bei Sensorausfall nicht persistiert) | hoch | mittel — genau der Sensorausfall provoziert das Disable | sicherer Fehler |
| **Ungewolltes Heizen / falscher Komfort** | F6 (TRV bleibt auf „external" mit eingefrorenem Wert) | hoch | mittel — jede Löschung/Deaktivierung bei TRV-external-Setup | begründeter Verdacht |
| **Frost-/Mould-Schutz versagt** | F1-Variante (TRV `off`: Floor-Setpoint ohne Mode → Ventil bleibt zu) | hoch | niedrig–mittel | sicherer Fehler |
| **Frost-/Mould-Schutz versagt (indirekt)** | F10 (`controls_boiler` beim Reconfigure verloren → Zone ohne Wärmequelle) | mittel | niedrig | sicherer Fehler |
| **Batterie-/Zigbee-Schreibsturm** | F1 (`already`-Check greift nie → Rewrite je 60 s) | hoch (Teilwirkung) | mittel | sicherer Fehler |
| **Kessel-Verschleiß (sonstiges)** | F8 (Zwangs-AUS/EIN je HA-Neustart) | mittel | hoch — jeder Neustart unter Heizlast | sicherer Fehler |
| **Falscher Komfortzustand** | F11 (Tippfehler ⇒ still Shadow-only) | mittel | mittel — freies Textformat | sicherer Fehler |
| **Shadow-Code schreibt live** | F12 (Remove-OFF trotz Shadow-only) | mittel | niedrig | sicherer Fehler |
| **Verlorenes Lernmodell** | F7 (kein Stop-Flush; ≤ 30 min/Neustart), F23/F24 (Versionsbump/Storage-Defekt) | mittel | hoch (F7) / niedrig | sicherer Fehler / Vorschlag |
| **Falsche UI-Anzeige** | F9 (Raum-Options-Flow am Hub), F16 (Zombie-Repair-Issue), F19 (Diagnostics ohne Options), F26 (fehlende Attribute) | mittel/niedrig | mittel | sicherer Fehler |
| **Doku-/Erwartungsbruch** | F15 (README-Löschversprechen), F25 (ADR-0038-Status), F22 (ADR-0018), F13 (Guard-Kommentar), F18 (recorder) | niedrig | — | Doku-Widersprüche |

**Priorisierung:** F1 und F2 zuerst (aktive Fehlkühlung bzw. unbeaufsichtigter
Dauer-Kessel mit unsichtbarer Ursache), dann F3–F6 (Teardown-/Persistenz-
Sicherheit), dann F7/F8 (systematischer Verschleiß/Lernverlust je Neustart).

---

## 4 KI-typische Grenzverletzungen (Markierung)

| Grenze | Stelle | Befund |
|---|---|---|
| diagnostic only vs live | `binary_sensor.py` (F2) | „diagnostic only"-Entity trägt de facto die Live-Aktuierung (Listener-Kopplung) |
| diagnostic only vs live | `__init__.py:161` (F12) | Remove-Pfad schreibt live, obwohl der Hub Shadow-only konfiguriert ist |
| pure function vs HA side effect | `actuator.py` vs `coordinator.py:1142` (F1) | Pfad verlässt sich auf ein Feld (`hvac_mode`), das die pure Übersetzung verwirft — Seiteneffekt-Vertrag stillschweigend verletzt |
| options vs data | `config_flow.py:670` + `hub_coordinator.py:96` (F9) | Options-Flow schreibt in einen Store, den der Hub nie liest |
| options vs data | `diagnostics.py:24` (F19) | Migration verschob Tuning nach `options`, Lesestelle blieb auf `data` |
| safety vs comfort | `coordinator.py:1114-1162` (F1, F5) | Safe-State-/Intent-Pfade sind gerade in den Degraded-Zweigen unvollständig |
| heat-only vs reversible cooling | F1 | Safe-State implizit heat-only gedacht; reversibles Gerät kühlt |
| local room zone vs system hub | F9, F21, `__init__.py` Unload-Asymmetrie (F4/F16) | Hub-Pfade sind gegenüber Raum-Pfaden systematisch dünner (kein Listener, kein Cleanup, kein Guard) |
| measured vs estimated | — | kein Verstoß gefunden (Shadow-Module nachweislich rein) |

---

## 5 Tests

**Neu in diesem Branch** (`tests/integration/test_lifecycle_adversarial.py`,
alle grün auf HA 2024.12.5 / Python 3.12; 9 passed + 1 strict-xfail):

| Gefordertes Szenario | Test |
|---|---|
| Setup, fehlender Temp-Sensor | `test_setup_retry_when_temp_sensor_missing` (+ `..._both_required_entities_missing`) |
| Setup, fehlender Aktuator | vorhanden: `test_setup_retry_when_actuator_missing` (test_setup_and_cycle.py) |
| Systemhub-Entry | vorhanden: `test_system_hub_setup_creates_binary_sensor`; neu ergänzt um Unload-/Remove-Verhalten |
| Migration von alter Version | vorhanden: `test_v1_entry_migrates_and_runs_list_presence`; neu: `test_future_schema_version_refused_not_downgraded` |
| Unload mit Save-Fehler | `test_unload_survives_save_failure` (+ Positivfall `test_unload_persists_learned_state`) |
| Remove mit Boiler-Off-Action | `test_remove_hub_fires_boiler_off_action`, `..._without_off_action_is_silent_noop`, `..._service_error_does_not_block_removal`, `test_unload_hub_does_not_fire_boiler_off` |
| Raum-Remove-Endzustand | `test_remove_room_entry_parks_actuator` (**strict xfail** — dokumentiert F3; nach Fix xfail entfernen) |

**Empfohlene Folge-Tests** (decken die neuen Findings ab): F1 (reversibles
Gerät + Sensorausfall → Mode-Nudge + Idempotenz), F2 (deaktivierte Hub-Entity →
Tick läuft weiter), F5 (Disable bei `unavailable` + Restart → Intent erhalten),
F8 (Hub-Erststart mit physisch laufendem Kessel → kein Sofort-AUS), F10
(Reconfigure erhält Anlagen-Keys), F9 (Options-Flow am Hub abgewiesen),
F16 (Issue-Cleanup beim Hub-Unload), F28 (Unload-Plattform-Fehler),
Migrations-Idempotenz (Doppellauf von `migrate_room_entry`).

---

## 6 Verifikation der Umsetzung (Nachtrag 2026-07-09, Stand `origin/main` v0.158.0)

Alle 12 Mittel-/Hoch-Findings sind auf `main` umgesetzt und verifiziert (Code-
Review des Diffs + beide Testsuiten grün auf HA 2024.12.5/Python 3.12; die
Entscheidungslogik liegt neu HA-frei in `control/lifecycle.py`):

| Finding | Umsetzung | Status |
|---|---|---|
| F1 | `resolve_safe_state` (pure): Mode-Nudge und Setpoint unabhängig + je idempotent; `_last_written_mode` nur nach echtem Nudge | ✔ behoben |
| F2 | Hub-Tick über eigenen `async_track_time_interval`-Timer (`entry.async_on_unload`); `update_interval=None` → Entity-Listener irrelevant, kein Doppel-Tick | ✔ behoben |
| F3 | `resolve_park_command`: Ventil→0 %, Heizgerät→`heat`@Setback (Floor-geklemmt), Cool-only→`off` in `_remove_room_entry` | ✔ behoben (wie empfohlen) |
| F4/F12 | `resolve_hub_unload_off(was_actuating, disabled, still_actuating)`: OFF nur bei Disable oder Aktuierungs-Entzug durch Reconfigure; Remove-OFF nur wenn ON+OFF verdrahtet | ✔ behoben (inkl. Übergangsfall) |
| F5 | `_run_once` flusht `_dirty` auch im Unavailable-Early-Return | ✔ behoben |
| F6 | `_restore_trv_internal`: Select→`internal` beim Remove | ✔ behoben (siehe Rest-Nit unten) |
| F7 | `async_flush_on_stop` an `EVENT_HOMEASSISTANT_STOP` (über `entry.async_on_unload`) | ✔ behoben |
| F8 | Reconciliation stempelt `last_switch_mono=now` → Min-On schützt den laufenden Kessel vor dem Erst-Tick-OFF | ✔ behoben (Restlücke F29 in v0.159.0 geschlossen) |
| F9 | `PoiseHubOptionsFlow` → sofortiger Abort `hub_no_options` | ✔ behoben |
| F10 | `_STRUCTURAL_CARRY` in `reconcile_reconfigure` trägt Anlagen-Keys zurück nach `data` | ✔ behoben |
| F11 | `_validate_boiler_actions` in Hub-Create + -Reconfigure (`invalid_boiler_action`) | ✔ behoben |

Niedrig-Findings: F13 ✔ (Kommentar präzisiert) · F15 ✔ (`PoiseStore.async_remove`
+ Trace-Datei-Löschung; README stimmt jetzt) · F16 ✔ (`cleanup_issues` bei
Disable + `async_delete_issue` bei Remove) · F17 ✔ (Issue-Re-Adoption im
Bootstrap) · F18 ✔ (`recorder` aus `after_dependencies` entfernt) · F19 ✔
(Diagnostics mergen `options`, Hub duck-typed) · F20 ✔ (strukturelle Keys sind
im Merge data-owned) · F21 ✔ (`== ENTRY_TYPE_SYSTEM`; `CONF_ENTRY_TYPE` jetzt
strukturell) · F22 ✔ (`MINOR_VERSION=1` + Migrations-Log) · F23 ✔ (besser als
vorgeschlagen: Versionsbump behält Zustand+Counter, setzt nur RC-Parameter auf
Priors mit re-geweiteter Kovarianz) · F24 ✔ (Repair-Issue `persistence_failed`
nach 5 Fehlversuchen) · F25 ✔ (ADR-0038-Status differenziert) · F26 ✔
(`frost_zone`/`frost_excluded` exponiert) · F27 ✔ (Remove-OFF `blocking=True`,
enger Except-Scope) · F14 ✔ (`structural_unchanged`-Guard im Update-Listener).

**Neue Findings aus der Verifikation:**

### F29 · mittel · sicherer Fehler — Erst-Tick-Keepalive re-asserted den *angenommenen* AUS-Zustand, wenn die Boiler-Entity beim Start (noch) nicht lesbar ist

- **Betroffen:** `control/hub_aggregate.py` (`BoilerState.last_keepalive_mono = 0.0`,
  Keepalive-Zweig in `step_boiler`), `hub_coordinator.py:_actuate` (Keepalive
  läuft auch vor erfolgreicher Reconciliation)
- **Begründung:** Der F8-Fix stempelt die Uhren nur im **reconcilierten** Pfad.
  Liefert `reconcile_boiler_on` beim ersten Tick `None` (Boiler-Entity beim
  HA-Boot noch `unavailable`/nicht angelegt — bei Zigbee-/Netzwerk-Schaltern
  üblich), läuft `step_boiler` mit dem frischen Default-State: `on=False`,
  `last_keepalive_mono=0.0`. Gegen die reale Prozess-Monotonic-Uhr ist
  `now − 0.0 ≥ keepalive_s (300)` praktisch immer wahr → der Keepalive
  re-asserted sofort den **angenommenen** AUS-Zustand.
- **Realbetriebsschaden:** Ein physisch laufender Kessel wird bei jedem
  HA-Neustart ausgeschaltet, wenn seine Entity später lädt als der erste
  Hub-Tick — dieselbe Neustart-Zyklus-Klasse wie F8, über den Keepalive- statt
  den Demand-Pfad.
- **Empirischer Beleg:** `test_hub_disable_fires_off_and_clears_issue` (main)
  zählte 2 statt 1 OFF-Calls, sobald der Keepalive-Pfad real feuerte; nach
  Setzen eines lesbaren `switch.boiler`-States (Reconcile greift, F8-Stempel)
  deterministisch 1.
- **Fix-Richtung:** Keepalive erst nach erfolgreicher Reconciliation zulassen
  (`if not self._reconciled: skip keepalive`) oder `last_keepalive_mono` beim
  Koordinator-Start auf `now` initialisieren. Vor der Reconciliation gibt es
  keinen „bekannten" Zustand, den ein Keepalive heilen könnte.
- **✔ Behoben in v0.159.0:** `step_boiler(..., allow_keepalive=...)` gated den
  Re-Assert auf `self._reconciled` (`hub_aggregate.py:336 ff.`,
  `hub_coordinator.py:277 ff.`); Demand-Übergänge bleiben aktiv. Vier neue
  Pure-Tests (`tests/test_hub_keepalive_gate.py`) decken gated/reconciled/
  Default-Kompatibilität/Demand-trotz-Gate ab. Empirisch verifiziert: der
  vormals flaky Test besteht auf unverändertem main jetzt 3× isoliert (F30
  damit an der Wurzel erledigt). Rest-Nit (niedrig): Bei einer dauerhaft
  unlesbaren Boiler-Entity (`reconcile_boiler_on` → immer `None`) bleibt der
  Keepalive-Selbstheiler permanent deaktiviert, obwohl nach Poises erstem
  *eigenen* erfolgreichen Schaltbefehl der Zustand selbst-autorisiert bekannt
  wäre — `_reconciled` (oder ein `_state_known`) könnte dann gesetzt werden.

### F30 · niedrig · Testlücke/Flaky — `test_hub_disable_fires_off_and_clears_issue` war umgebungsabhängig

- Zwei Läufe der identischen Suite auf unverändertem `main` lieferten
  unterschiedliche Ergebnisse (grün bzw. `assert 2 == 1`), weil das Feuern des
  F29-Keepalives von der Monotonic-Umgebung abhängt. Auf diesem Branch test-
  seitig deterministisch gemacht (lesbarer Boiler-State vor Setup); **seit dem
  F29-Produktfix in v0.159.0 auch auf unverändertem main deterministisch grün
  (3× isoliert verifiziert) — erledigt.**
- Gleiche Falle für alle künftigen Hub-Tests, die Service-Calls zählen:
  ohne lesbaren Boiler-State zählt man den Erst-Tick-Keepalive mit.

**Verbleibende Nits (niedrig, kein Realbetriebsschaden):**

1. `_restore_trv_internal` flippt *jedes* `select` des Geräts mit einer
   `internal`-Option — die Tick-Seite nutzt das engere
   `is_external_sensor_select`-Matching; ein fremdes Select mit zufälliger
   „internal"-Option würde mit umgestellt.
2. `_remove_hub_entry`/`async_fire_boiler_off` rufen `blocking=True` ohne
   Timeout — die Tick-Seite kapselt denselben Call in `asyncio.timeout(10)`
   (N-1); ein hängender Boiler-Service könnte Remove/Unload stallen.
3. F8-Restfall: Läuft der Kessel und liefern die Zonen länger als `min_on_s`
   keine Snapshots, folgt das OFF danach trotzdem (dann aber als legitime
   „kein Bedarf"-Entscheidung).
4. F28 (Unload-Plattform-Fehlschlag) bleibt als Testlücke offen.

## 7 Benötigter zusätzlicher Kontext

- **F6:** Verhalten der Ziel-TRV-Firmware bei ausbleibender External-Temp
  (Fallback-Timeout ja/nein) — bestimmt, ob F6 hoch bleibt oder auf mittel fällt.
- **F10:** Bedingungen, unter denen das Reconfigure-Formular Anlagenfelder
  ausblendet (`config_flow.py:215 ff.`).
- **F20:** Historie der V1-Options (konnten strukturelle Keys enthalten?) —
  entscheidet, ob der Merge-Vorrang ein realer Migrationsrisikofall ist.
- **F25:** Beabsichtigter Geltungsbereich des ADR-0038-Status „Implementiert"
  (Architektur vs. Stufen S3/S4).
