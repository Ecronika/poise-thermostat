# Adversarialer Review: Home-Assistant-Lifecycle der Poise-Integration

**Datum:** 2026-07-09 · **Scope:** `manifest.json`, `custom_components/poise/__init__.py` (`async_setup`, `async_setup_entry`, `async_migrate_entry`, `async_unload_entry`, `async_remove_entry` und alle direkt erreichten Nachbarn: `coordinator.py`-Lifecycle-Methoden, `hub_coordinator.py`, `migration.py`, `config_flow.py`, `config_reconcile.py`, `storage.py`, `control/lifecycle.py`, `control/hub_aggregate.py`, `frontend/__init__.py`) sowie README/ADRs/`quality_scale.yaml` und die Test-Suite als Abgleichsquellen.

**Methode:** 9 unabhängige adversariale Prüf-Dimensionen (Raum-Setup, Hub-Setup, Migration, Unload, Remove, Doku-vs-Code, Testlücken, HA-API-Annahmen, Projektgrenzen-Sweep) → Deduplizierung → adversariale Verifikation jedes Findings durch zwei unabhängige Skeptiker mit getrennten Linsen (HA-Core-Realität, verifiziert gegen den HA-2025.1-Quelltext; Code-Erreichbarkeit) → Vollständigkeits-Kritik gegen die geforderte Checkliste. Kommentare, README und ADRs wurden nicht als Wahrheit akzeptiert, sondern gegen den ausgeführten Code geprüft.

**Statistik:** 56 Roh-Findings → 45 nach Dedup → **44 bestätigt/plausibel überlebt**, 3 aktiv widerlegt (§6), 7 explizite Entwarnungen (§7). Schweregrade sind die **nach** der adversarialen Verifikation korrigierten Werte; wo die Verifikation vom Erst-Reviewer abwich, ist der Ursprungswert vermerkt.

---

## Executive Summary

Der HA-Lifecycle der Integration ist insgesamt überdurchschnittlich sorgfältig gebaut (korrekte
`runtime_data`-Reihenfolge, echter `ConfigEntryNotReady`-Guard, durchdachtes Boiler-Hand-over-Design,
Hub-Singleton erzwungen, pure/Glue-Trennung eingehalten — siehe Entwarnungen in §7). Der Review fand
**keinen Befund der Klasse „kritisch“**, aber **6 Befunde der Klasse „hoch“**, die alle demselben
KI-typischen Muster folgen: *ein plausibel kommentiertes Gate, das in genau einem Nachbarpfad nicht
greift* — die Asymmetrie zwischen zwei fast gleichen Zweigen ist das wiederkehrende Defektbild.

**Die wichtigsten Befunde:**

1. **AR-01 (hoch, sicherer Fehler):** Wird der System-Hub per Reconfigure auf einen *anderen*
   Boiler-Aktor umgezogen, erkennt die Relinquish-Logik das nicht (`still_actuating` prüft nur
   „parsen beide Actions“, nicht „gleiches Ziel“) — der **alte Boiler bleibt dauerhaft AN**, niemand
   schaltet ihn je wieder aus.
2. **AR-02 (hoch):** Beim Hub-Unload lebt der Tick-Timer bis *nach* `async_unload_entry` weiter
   (HA-Core-Semantik von `entry.async_on_unload`, gegen HA 2025.1-Quelltext verifiziert), und
   `async_fire_boiler_off` aktualisiert `self._boiler` nicht — ein in das Unload-Fenster fallender
   Keepalive kann den Boiler **nach dem Hand-over-OFF wieder einschalten**.
3. **AR-03 (hoch):** Der Raum-Zweig von `async_unload_entry` unterscheidet — anders als der
   Hub-Zweig direkt darüber — nicht zwischen Reload und **Entry-Disable**: kein Park, kein
   Sensor-Quellen-Restore. Ein bei Disable offenes Ventil heizt unreguliert weiter; ein Klimagerät
   bleibt im letzten Modus (auch `cool`); die README-Zusage „unconditional safety floors“ gilt nur
   für den Switch-Disable-Pfad.
4. **AR-04 (hoch, sicherer Fehler):** `climate_mode` hat zwei konkurrierende Eigentümer (Store via
   Climate-Entity vs. Options-Formular). Jeder Options-Save — auch wenn nur der Energiepreis geändert
   wird — setzt einen live gepinnten `heat_only`/`cool_only`-Modus still auf den stale Formularwert
   zurück (typisch `auto`) → ungewolltes Kühlen/Heizen möglich.
5. **AR-05 (hoch):** Die Frostschutzkette reißt an der Zone→Hub-Grenze: eine `unavailable-safe`
   degradierte Zone parkt ihren TRV lokal auf `heat@7 °C`, verschwindet aber vollständig aus der
   Boiler-Aggregation — bei einer hydronischen Zone ist der lokale Safe-State ohne feuernden Kessel
   wirkungslos. ADR-0039 dokumentiert die Kessel-Seite als bewussten Trade-off; es fehlen aber das
   hubseitige Repair-Issue, eine ehrliche Doku des „fail toward warmth“-Anspruchs und jeder Test
   über diese Grenze.
6. **AR-06 (hoch, Testlücke):** Der gesamte Hub-Lifecycle (Timer-Registrierung, Timer-Tod beim
   Unload, exklusives BINARY_SENSOR-Forwarding, Reload-ohne-OFF über echtes HA) läuft in keinem Test
   über den echten Zeit-/Unload-Pfad — alle Hub-Tests rufen `async_refresh()`/`_actuate()` direkt.

**Querschnittsmuster** (Details in §5): Kommentare, die Gates behaupten, die der Code nicht hat
(AR-15 „only switch a boiler Poise actually commanded“, AR-21 „no learning loss“, AR-17 vs. F27,
AR-32 „SHADOW … no writes“ über live wirksamem Code, AR-37/AR-38 stale Docstrings); doppelte
Ownership options↔Store (AR-04, AR-13, AR-16); Disable≠Delete≠Reload-Asymmetrien (AR-03, AR-15,
AR-25); vakante bzw. sich selbst bestätigende Tests (AR-07).

**Sofort umsetzbare Gegenmaßnahmen** (Reihenfolge = Nutzen):
`still_actuating` um Ziel-Vergleich erweitern + Timer-Unsub vor dem OFF ziehen (AR-01/AR-02);
Disable-Pfad des Raum-Zweigs parken lassen (AR-03); `climate_mode` einem einzigen Eigentümer geben
(AR-04); `unavailable_safe`-Zonen mit `controls_boiler` hubseitig als Repair-Issue surfacen (AR-05);
die in §8 gelieferten Tests einchecken (AR-06/07/19/22/29/41).

---

## Risiko-Matrix (sortiert nach Realbetriebsschaden)

Sortierung strikt nach möglichem Schaden im Realbetrieb, nicht nach Code-Stil. Innerhalb einer Schadensklasse nach korrigiertem Schweregrad.

### ungewolltes Heizen

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-01 | **hoch** | sicherer Fehler | Hub-Reconfigure auf anderen Boiler-Aktor lässt den alten Boiler dauerhaft AN: Relinquish-Erkennung prüft nur 'verdrahtet', nicht 'gleicher Aktor' | `__init__.py:192` |
| AR-02 | **hoch** | begründeter Verdacht | Hub-Unload-Race: Tick-Timer lebt während des Boiler-OFF-Handovers weiter und kann den Boiler nach dem OFF wieder einschalten — dauerhaft AN nach Disable/Reconfigure | `__init__.py:202` |
| AR-03 | **hoch** | begründeter Verdacht | Raum-Unload bei Entry-Disable parkt den Aktor nicht — Ventil/Klimagerät verharrt dauerhaft auf letztem Poise-Kommando, ohne Frost-Rescue | `__init__.py:208` |
| AR-07 | **mittel** | sicherer Fehler | Vakanter Test: test_remove_hub_swallows_off_failure erreicht den Fehlerpfad nie (nur OFF-Action gewired → F12-Gate überspringt den Call) — Boiler-OFF-Fehlerbehandlung bei Hub-Remove faktisch ungetestet | `tests/integration/test_glue_coverage4.py:131` |
| AR-08 | **mittel** | begründeter Verdacht | Hub verliert bei HA-Stop/Restart sämtlichen Boiler-Takt-Zustand: kein Stop-Handler, keine Persistenz, Keepalive kein Dead-Man-Netz, Reconcile misinterpretiert Script-Entities, Min-Off nach Restart verletzbar | `hub_coordinator.py:256` |
| AR-09 | **mittel** | sicherer Fehler | _STRUCTURAL_CARRY reanimiert vom Nutzer gelöschte Anlagen-Felder (declared_power, compressor_group, design_flow_temp), sobald ein System-Hub existiert — Kommentar behauptet das Gegenteil | `config_reconcile.py:72` |
| AR-10 | **mittel** | begründeter Verdacht | resolve_park_command klemmt den Setback-Setpoint nicht an device min_temp — set_temperature kann still scheitern und das Gerät bleibt in 'heat' auf dem alten Komfort-Setpoint | `control/lifecycle.py:96` |
| AR-11 | **mittel** | begründeter Verdacht | Raum-Remove aktuiert auch bei nie erfolgreichem Setup: Park + Select-Restore feuern auf ein Gerät, das Poise nie kommandiert hat | `__init__.py:288` |
| AR-12 | **mittel** | begründeter Verdacht | Room-Reconfigure auf anderen Aktor: alter TRV bleibt auf 'external'-Sensorquelle mit eingefrorenem Feed und wird nicht geparkt — F3/F6-Cleanup existiert nur im Delete-Pfad | `config_flow.py:789` |
| AR-13 | **mittel** | begründeter Verdacht | Raum-Remove-Park entscheidet heats_for_zone anhand des stale Config-climate_mode statt des store-eigenen Live-Modus — dritte Stelle der doppelten Ownership, im Delete-Pfad | `__init__.py:284` |
| AR-14 | **mittel** | fehlender Kontext | Hub-Variante des Zombie-Findings ungedeckt: der aktorisch wirksame Tick-Timer wird VOR dem Plattform-Forwarding registriert — wirft das Forwarding, kann ein SETUP_ERROR-Hub den Boiler dauerhaft weiterschalten | `__init__.py:97` |
| AR-25 | **niedrig** | begründeter Verdacht | Fehlgeschlagener Plattform-Unload beim Hub-Disable: OFF-Handover und Issue-Cleanup übersprungen, Timer läuft weiter — disabled Hub aktuiert den Boiler bis zum Neustart | `__init__.py:183` |

### ungewolltes Kühlen

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-04 | **hoch** | sicherer Fehler | async_apply_options überschreibt den live per Klima-Entität gesetzten climate_mode (heat_only/cool_only) bei jedem Options-Submit mit dem stale Formularwert — doppelte Ownership Store vs. Options | `coordinator.py:622` |

### Frost-/Mould-Schutz versagt

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-05 | **hoch** | begründeter Verdacht | Hub verwirft unavailable-safe-Zonen komplett: lokaler Frostschutz parkt TRV auf heat@7°C, aber der geteilte Boiler feuert nicht — Frostschutzkette reißt an der Zone→Hub-Grenze | `hub_coordinator.py:144` |
| AR-15 | **mittel** | begründeter Verdacht | _remove_hub_entry feuert Boiler-OFF rein verdrahtungsbasiert — Kommentar 'only switch a boiler Poise actually commanded' ist eine Fehlbehauptung (verdrahtet != kommandiert) | `__init__.py:242` |

### Batterie-/Zigbee-Schreibsturm

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-06 | **hoch** | Testlücke | Testlücke Hub-Lifecycle: Timer-Registrierung, Timer-Abbestellung beim Unload und 'nur BINARY_SENSOR wird geforwarded' — kein Test feuert je den Zeitgeber | `tests/integration/test_setup_and_cycle.py:136` |
| AR-26 | **niedrig** | Verbesserungsvorschlag | Kein Setup-Guard gegen einen zweiten System-Entry: bei zwei Hub-Entries (Storage-Restore/Backup-Merge) entstünden zwei konkurrierende Boiler-Schreiber mit kämpfenden Keepalives | `__init__.py:80` |

### falscher Komfortzustand

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-16 | **mittel** | begründeter Verdacht | Frischer V2-Entry: Required-Options-Felder ohne Default (optimal_start, comfort_weight, climate_mode) — erster Options-Save flippt Coordinator-Defaults still (optimal_start True→False, comfort_weight 70→0) | `config_flow.py:482` |
| AR-17 | **mittel** | sicherer Fehler | _execute_park: blocking=False macht Ausführungsfehler des finalen, nie wiederholten Kommandos unsichtbar (Widerspruch zu F27) und racet set_temperature gegen set_hvac_mode | `__init__.py:317` |
| AR-18 | **mittel** | sicherer Fehler | _restore_trv_internal flippt JEDES Select mit 'internal'-Option — breiter als der eigene Klassifikator is_external_sensor_select und ohne Idempotenz-/Ownership-Check | `__init__.py:351` |
| AR-19 | **mittel** | Testlücke | Testlücke Migration: version>2-Refusal (MIGRATION_ERROR), V1-Hub-Entry end-to-end, Idempotenz, options-gewinnt-Konflikt e2e, occupancy-String in data und Reconfigure-Roundtrip nach Migration sind nirgends abgedeckt | `__init__.py:158` |
| AR-27 | **niedrig** | fehlender Kontext | Migrations-Merge 'options gewinnt': ob damit ein neuerer V1-data-Wert verdeckt werden kann, hängt vom nicht mehr rekonstruierbaren V1-Verhalten ab | `migration.py:84` |

### verlorenes Lernmodell

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-20 | **mittel** | begründeter Verdacht | async_bootstrap: Catch-all über dem Store-Load macht aus jedem transienten I/O-Fehler ein 'starting fresh' — gelerntes Modell wird vom periodischen Save überschrieben; Teil-Restore kann enabled=False/override verlieren | `coordinator.py:564` |
| AR-21 | **mittel** | sicherer Fehler | Kommentar '(no learning loss)' ist falsch: Save-Fehler beim Unload wird geschluckt, bis zu 30 Ticks Lernen still verloren und das persistence_failed-Issue direkt danach gelöscht | `coordinator.py:1055` |
| AR-22 | **mittel** | Testlücke | Testlücke: Unload mit Save-Fehler — das definierte Swallow-Verhalten von async_persist_and_cleanup ist von keinem Test abgesichert | `coordinator.py:1053` |
| AR-28 | **niedrig** | sicherer Fehler | async_persist_and_cleanup nimmt self._lock nicht — finaler Save kann einen halb-aktualisierten Mid-Tick-Modellzustand persistieren | `coordinator.py:1051` |

### falsche UI-Anzeige

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-29 | **niedrig** | begründeter Verdacht | _remove_hub_entry: except (HomeAssistantError, ValueError) fängt vol.Invalid aus der synchronen Service-Schema-Validierung nicht — Löschung des Frost-Repair-Issues wird übersprungen | `__init__.py:247` |
| AR-30 | **niedrig** | sicherer Fehler | ADR-0038 Entscheidung 6 ('System-Onboarding erscheint nur bei ≥2 Zonen oder konfigurierter geteilter Ressource') ist nicht umgesetzt — das System-Menü erscheint immer | `config_flow.py:698` |
| AR-31 | **niedrig** | Verbesserungsvorschlag | quality_scale.yaml enthält veraltete Selbstauskunft: 'via_device ... still pending' ist längst implementiert, Testzahl (74 statt 98) stimmt nicht mehr | `quality_scale.yaml:64` |

### Shadow-Code schreibt live

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-23 | **mittel** | fehlender Kontext | State-Listener, Stop-Flush und Update-Listener werden vor dem Plattform-Forwarding registriert: wirft das Forwarding unerwartet, kann (HA-versionsabhängig) ein Zombie-Koordinator ohne Entities weiter aktorisch regeln | `__init__.py:142` |
| AR-32 | **niedrig** | sicherer Fehler | Als 'SHADOW (diagnostic only, no writes)' kommentierter Block erzeugt die live wirksame Stellgröße _hum_action (dry-Mode-Nudge) — Fehler darin werden nur auf DEBUG verschluckt | `coordinator.py:1611` |

### kein Realbetriebsschaden

| ID | Schweregrad | Klassifikation | Finding | Fundstelle |
|----|-------------|----------------|---------|------------|
| AR-24 | **mittel** | begründeter Verdacht | Blocking-Boiler-OFF-Calls in Unload-/Remove-Pfaden ohne das 10-s-Timeout des normalen Aktuationspfads — hängender Boiler-Service blockiert Unload/Remove unbegrenzt und vergrößert das Timer-Race-Fenster | `hub_coordinator.py:336` |
| AR-33 | **niedrig** | begründeter Verdacht | Setup-Guard erkennt registry-deaktivierte Pflicht-Entities nicht: ewiger ConfigEntryNotReady-Retry mit irreführender Meldung, kein Repair-Issue | `__init__.py:117` |
| AR-34 | **niedrig** | begründeter Verdacht | Korrupter/unvollständiger Raum-Entry crasht mit KeyError/ValueError in Guard und Koordinator-Konstruktor → dauerhafter SETUP_ERROR ('Unknown error') statt kontrolliertem Fehlerpfad | `__init__.py:118` |
| AR-35 | **niedrig** | begründeter Verdacht | Boiler-Reconcile stempelt last_switch_mono=now auch beim Adoptieren von real=OFF — nach jedem Neustart/Reload blockiert min_off (Default 300 s, bis 3600 s) das erste Einschalten, auch für den Frost-Override; F8-Kommentar begründet nur den ON-Fall | `hub_coordinator.py:265` |
| AR-36 | **niedrig** | Verbesserungsvorschlag | async_migrate_entry: version>2-Guard ist in unterstütztem HA toter Code (Core übernimmt den Refusal); Migration setzt minor_version nie — bei künftigem Minor-Bump/Downgrade läuft die Migration bei jedem Start erneut | `__init__.py:158` |
| AR-37 | **niedrig** | sicherer Fehler | Stale Modul-Docstring in binary_sensor.py: 'Poise does not switch any boiler in this stage' und 'across all zones' widersprechen dem ausgeführten Code (S2-Aktuation implementiert; Aggregation ist controls_boiler-only) | `binary_sensor.py:4` |
| AR-38 | **niedrig** | sicherer Fehler | safety/sensor_watchdog.py-Moduldocstring behauptet, der Frozen-Sensor-Pfad verändere den Regelausgang nicht ('without altering the control output') — der Coordinator ersetzt bei frozen Ziel UND Modus | `safety/sensor_watchdog.py:6` |
| AR-39 | **niedrig** | sicherer Fehler | ADR-0038 beschreibt eine nicht existierende Architektur: In-Memory-Registry hass.data[DOMAIN]['hub'] (Push) und ResourceRelease-Rückkanal — Code macht Pull über entry.runtime_data, ResourceRelease ist toter Contract | `contracts.py:164` |
| AR-40 | **niedrig** | sicherer Fehler | ADR-0007 verspricht Debounce-Persistenz ('schreibt nur bei echter Änderung', async_call_later, BT-Muster) und eine _check_entities_ready-Warteschleife — Code hat Counter-Throttle alle 30 Ticks und nur einen Existenz-Check | `coordinator.py:1028` |
| AR-41 | **niedrig** | Testlücke | Testlücke Setup-Guard: die Variante 'Temperatursensor fehlt, Aktuator existiert' und der Degraded-Pfad 'Sensor existiert-aber-unavailable → Setup lädt' sind ungetestet | `tests/integration/test_setup_and_cycle.py:100` |
| AR-42 | **niedrig** | Testlücke | Testlücke Remove-Fehlerpfade Raum: Aktor fehlt/unavailable und werfender Park-Service-Call ungetestet — Store-/Trace-Cleanup nach geschlucktem Park-Fehler unbelegt | `__init__.py:330` |
| AR-43 | **niedrig** | Testlücke | Testlücke strukturell: ohne installiertes HA wird das gesamte Lifecycle-Glue-Verzeichnis zur Collection-Zeit still übersprungen — lokal läuft kein einziger aktorischer Lifecycle-Pfad | `tests/integration/conftest.py:30` |
| AR-44 | **niedrig** | sicherer Fehler | Trace-Cleanup löscht nur '<entry_id>.jsonl' — die Rotationsgeneration '.jsonl.1' des Recorders bleibt als Leiche liegen; suppress(Exception) um Store-Remove verschluckt auch Programmierfehler | `__init__.py:298` |

---

## Detail-Findings

### AR-01 · hoch · sicherer Fehler

**Hub-Reconfigure auf anderen Boiler-Aktor lässt den alten Boiler dauerhaft AN: Relinquish-Erkennung prüft nur 'verdrahtet', nicht 'gleicher Aktor'**

- **Fundstelle:** `custom_components/poise/__init__.py:192` — `async_unload_entry (Hub-Zweig)`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** Single-Writer-/Hand-over-Garantie des Hubs (ADR-0038 Entscheidung 2, F4/F12): der Hub gibt einen Aktor ab, ohne ihn in einen sicheren Endzustand zu bringen
- **Codebeleg:** __init__.py:192-202: `still_actuating = (parse_service_action(entry.data.get(CONF_BOILER_ON_ACTION)) is not None and parse_service_action(entry.data.get(CONF_BOILER_OFF_ACTION)) is not None)` ... `if resolve_hub_unload_off(was_actuating=hub.actuation_active, disabled=..., still_actuating=still_actuating): await hub.async_fire_boiler_off()`

**Befund:** Dimension: docs-vs-code. Der F4/F12-Kommentar (__init__.py:188-191) verspricht 'hand the boiler back cleanly — fire OFF ... or the reconfigured data no longer wires ON+OFF actuation'. HAs async_update_reload_and_abort (config_flow.py:761-763) schreibt aber ZUERST die neuen Daten und lädt DANN neu — async_unload_entry sieht bereits die NEUEN Action-Strings. Zeigen die neuen Actions auf einen ANDEREN Aktor (switch.boiler_neu statt switch.boiler_alt), parsen beide weiterhin → still_actuating=True → resolve_hub_unload_off (control/lifecycle.py:101-111) liefert False → kein OFF über hub._action_off (das noch die ALTE Action hält, hub_coordinator.py:107-108). Der neue Hub reconciled und keepalived danach nur den NEUEN Aktor (hub_coordinator.py:256-259, 330-343). Niemand schaltet den alten Boiler je wieder aus.

**Mögliches Fehlverhalten im Realbetrieb:** Ein physisch laufender Boiler, den Poise selbst eingeschaltet hat, bleibt nach einem Reconfigure des Aktuator-Ziels unbegrenzt AN — unbeaufsichtigtes Heizen; wenn die Zonenventile schließen, exakt das Überdruck-Szenario, vor dem ADR-0039 selbst warnt. Grenzt an 'kritisch'; 'hoch', weil der Trigger eine seltene Admin-Aktion ist und ADR-0039 kesselseitige Sicherheitsfunktionen voraussetzt.

**Minimaler Reproduktionsfall / Testidee:** 1) System-Hub mit boiler_on_action='switch.boiler_alt/switch.turn_on' und boiler_off_action='switch.boiler_alt/switch.turn_off'; Zone mit controls_boiler heizen lassen, bis der Hub ON gefeuert hat. 2) Hub-Reconfigure: beide Actions auf 'switch.boiler_neu/...' ändern, speichern. 3) Unload läuft mit neuen Daten: still_actuating=True → kein OFF auf switch.boiler_alt. 4) switch.boiler_alt bleibt dauerhaft 'on'.

**Zur Absicherung nötig:** Keiner — update-then-reload ist HA-Core-Verhalten von async_update_reload_and_abort. Fix: still_actuating zusätzlich auf identisches entity_id-Ziel des alten hub._action_off prüfen (oder OFF über die ALTEN Actions feuern, wenn sich das Ziel ändert).

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Widerlegung fehlgeschlagen — alle Glieder der Kette sind im Code belegt. (1) __init__.py:192-196 leitet still_actuating rein aus der Parsbarkeit der NEUEN Action-Strings ab (parse_service_action, hub_aggregate.py:199-216, ignoriert das entity_id-Ziel); kein Vergleich mit dem alten hub._action_off. (2) resolve_hub_unload_off (lifecycle.py:111: `was_actuating and (disabled or not still_actuating)`) liefert bei Reconfigure auf anderen Aktor False → async_fire_boiler_off (__init__.py:202) wird nicht aufgerufen, obwohl hub._action_off die alte Actio […]
- **bestätigt** (Konfidenz 0.9): Bestätigt nach aktiver Widerlegungssuche. Kette: (1) Hub-Reconfigure config_flow.py:761-763 nutzt async_update_reload_and_abort — entry.data ist beim Unload bereits NEU; das Repo setzt diese Reihenfolge selbst voraus (F14-Kommentar __init__.py:42-46). (2) __init__.py:192-196 berechnet still_actuating aus den NEUEN Actions; zeigen beide auf einen anderen Aktor, parsen sie weiter → still_actuating=True → lifecycle.py:111 'return was_actuating and (disabled or not still_actuating)' = False → kein OFF über das alte hub._action_off (hub_coordinator. […]

---

### AR-02 · hoch · begründeter Verdacht

**Hub-Unload-Race: Tick-Timer lebt während des Boiler-OFF-Handovers weiter und kann den Boiler nach dem OFF wieder einschalten — dauerhaft AN nach Disable/Reconfigure**

- **Fundstelle:** `custom_components/poise/__init__.py:202` — `async_unload_entry (Hub-Zweig) / PoiseHubCoordinator.async_fire_boiler_off`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** safety vs comfort / Lifecycle-Grenze: der Safety-Handover (OFF) ist nicht gegen den weiterlaufenden Komfort-Regelpfad (Tick/Keepalive) serialisiert
- **Codebeleg:** __init__.py:97-101: `entry.async_on_unload(async_track_time_interval(hass, _hub_tick, timedelta(seconds=TICK_INTERVAL_S)))` — __init__.py:197-202: `if resolve_hub_unload_off(...): await hub.async_fire_boiler_off()` — hub_coordinator.py:330-343: async_fire_boiler_off ruft nur services.async_call(off, blocking=True) und aktualisiert self._boiler NICHT

**Befund:** Unabhängig gefunden von 2 Reviewern (Dimensionen: unload, ha-api; letzterer verifizierte HA-Core config_entries.py 2025.1.0, ConfigEntry.async_unload Z.855-863). Per entry.async_on_unload registrierte Callbacks (Hub-Timer, Coordinator-async_shutdown) werden erst NACH erfolgreichem Rücklauf von async_unload_entry in _async_process_on_unload ausgeführt, und nur bei result=True. Während async_unload_entry (Fenster: async_unload_platforms + blockierender OFF-Call ohne Timeout) kann noch ein _hub_tick → hub.async_refresh() → _actuate() laufen — oder ein bereits in-flight befindlicher Tick awaitet gerade in _actuate/_call. async_fire_boiler_off setzt self._boiler NICHT auf off, der State glaubt weiter on=True; step_boiler (hub_aggregate.py:380-396) re-asserted dann per Keepalive (DEFAULT_BOILER_KEEPALIVE_S=300, const.py:150) 'on' — landet dieser Call NACH dem manuellen OFF, ist der Boiler wieder AN. Danach cancelt der Core den Timer: niemand schaltet je wieder aus. Der Remove-Pfad heilt sich teilweise selbst (zweites OFF in _remove_hub_entry läuft nach Timer-Cancel), der Disable-Pfad nicht. Positiv geprüft: Entscheidungsmatrix sonst korrekt (plain reload → kein OFF + Reconcile; Reconfigure ohne Actions → OFF mit alter Config; hub.actuation_active ist statisch aus entry.data, Docstring stimmt).

**Mögliches Fehlverhalten im Realbetrieb:** Nach Disable oder Reconfigure-Handover des Hubs bleibt der Boiler mit gewisser Wahrscheinlichkeit (Keepalive fällig im Unload-Fenster bzw. Tick in-flight) dauerhaft eingeschaltet, ohne dass Poise ihn je wieder ausschaltet — ungewolltes, unkontrolliertes Heizen bis zum manuellen Eingriff; der Nutzer glaubt, die Steuerung sauber abgegeben zu haben.

**Minimaler Reproduktionsfall / Testidee:** Hub mit ON/OFF-Actions und aktiver Zonen-Anforderung, Boiler AN. Boiler-OFF-Service künstlich 2-5 s verzögern (langsamer Zigbee/Cloud-Schalter). Hub-Entry in der UI deaktivieren, während der 60-s-Tick in das Unload-Fenster fällt und (now - last_keepalive_mono) >= 300: OFF wird gesendet, der parallel laufende _hub_tick sendet danach ON und committet BoilerState(on=True); anschließend cancelt _async_process_on_unload den Timer. Boiler bleibt an, Entry ist NOT_LOADED.

**Zur Absicherung nötig:** Keiner — Core-Verhalten aus config_entries.py 2025.1.0 verifiziert. Fix-Richtung: im Unload-Zweig VOR async_unload_platforms/async_fire_boiler_off den Timer-Unsub selbst halten und explizit canceln bzw. ein Teardown-Flag setzen und self._boiler=BoilerState(on=False, ...) nach dem OFF übernehmen.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85): Alle HA-Core-Annahmen gegen 2025.1.0-Quellcode verifiziert (Repo-Minimum laut hacs.json: 2025.1.0): (1) config_entries.py Z.855-863 — _async_process_on_unload läuft erst NACH erfolgreichem async_unload_entry; Timer-Unsub (__init__.py:97-101) und der automatische Coordinator-Shutdown (update_coordinator.py:132-133, config_entry.async_on_unload(self.async_shutdown)) feuern also strikt nach dem OFF in __init__.py:202; die Entry bleibt währenddessen LOADED (kein UNLOAD_IN_PROGRESS-State in 2025.1.0). […]
- **bestätigt** (Konfidenz 0.88): Race bestätigt nach Prüfung von custom_components/poise/__init__.py (Timer Z.97-101, OFF-Handover Z.197-202), hub_coordinator.py (async_fire_boiler_off Z.330-343 ohne State-Update/Lock, _actuate/_call Z.233-296, _collect_requests Z.136-176), control/hub_aggregate.py (step_boiler Keepalive-Re-Assert Z.380-396), const.py (TICK_INTERVAL_S=60 Z.11, DEFAULT_BOILER_KEEPALIVE_S=300 Z.150) sowie HA-Core 2025.1.0 (heruntergeladen): config_entries.py Z.855-861 führt _async_process_on_unload (Timer-Cancel + coordinator.async_shutdown) erst NACH erfolgreic […]

---

### AR-03 · hoch · begründeter Verdacht

**Raum-Unload bei Entry-Disable parkt den Aktor nicht — Ventil/Klimagerät verharrt dauerhaft auf letztem Poise-Kommando, ohne Frost-Rescue**

- **Fundstelle:** `custom_components/poise/__init__.py:208` — `async_unload_entry (Raum-Zweig)`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** lokale Raumzone vs System-Hub: der Hub gibt bei disable die geteilte Ressource ab (OFF + cleanup_issues), der Raum-Pfad lässt den exklusiv gesteuerten Aktor live auf letztem Setpoint stehen
- **Codebeleg:** __init__.py:208-214: `unloaded = await hass.config_entries.async_unload_platforms(entry, [CLIMATE, SENSOR, SWITCH])\nif unloaded:\n    # final save + repair-issue/notification cleanup (no learning loss)\n    await entry.runtime_data.async_persist_and_cleanup()`

**Befund:** Dimension: unload. Der Raum-Zweig unterscheidet — anders als der Hub-Zweig direkt darüber (__init__.py:199 disabled=entry.disabled_by is not None, Z.204 Issue-Cleanup bei disable) — nicht zwischen plain reload und disable. Bei disable wird nur persistiert; der komplette Park-Mechanismus (resolve_park_command, lifecycle.py:69-98; _remove_room_entry, __init__.py:254-299 inkl. Ventil→0 %, TRV-Sensorquelle→internal) läuft ausschließlich bei Delete. Ein bei disable auf 100 % stehendes Ventil (number.*) oder ein Klimagerät im letzten Poise-Modus/-Setpoint (auch cool) bleibt unbeaufsichtigt stehen. Zusätzlich entfällt mit dem Entry die unconditional Frost-/Mould-Rescue, die der Tick für per Switch deaktivierte Zonen noch leistet (coordinator.py:1938-1975) — die README-Zusage gilt nur für Switch-Disable, nicht für Entry-Disable. Genau die Schadensbilder, die resolve_park_command laut Docstring (lifecycle.py:79-88: 'a valve without a controller must not stay open', 'no unattended full-heat, no frost/mould risk') verhindern soll, treten bei disable ein. entry.disabled_by steht im Unload zur Unterscheidung bereit und wird im Raum-Pfad nicht genutzt.

**Mögliches Fehlverhalten im Realbetrieb:** Deterministisch bei jedem Entry-Disable: offenes Ventil → unreguliertes Dauerheizen; Klimagerät im Kühlmodus → dauerhaft ungewolltes Kühlen; Aktor im Zustand 'off' → Raum ohne jeden Frost-/Schimmelschutz über den Winter. Kein Poise-Code läuft mehr, der das korrigiert.

**Minimaler Reproduktionsfall / Testidee:** Raum-Entry mit Ventil-Aktuator (number.*) in Heizphase (Ventil 80-100 %) über Einstellungen → Poise → Entry deaktivieren. async_unload_entry Z.208-214 persistiert nur; kein Park-Call, kein disabled_by-Check. Ventil bleibt offen; kein Tick, keine Rescue mehr.

**Zur Absicherung nötig:** Keine ADR/Doku gefunden, die 'Disable = Pause, Aktor unangetastet' als bewusste Entscheidung festlegt. Falls beabsichtigt, gehört das dokumentiert; sonst: bei entry.disabled_by is not None denselben Park wie in _remove_room_entry fahren (ohne Store-/Trace-Löschung).

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.88): Widerlegung gescheitert; alle Kernbehauptungen belegt. (1) __init__.py:208-214: Raum-Unload ruft nur async_persist_and_cleanup() (coordinator.py:1051-1070: Save, Issue-Delete, Notification-Dismiss — kein Aktor-Service-Call); kein disabled_by-Check, während der Hub-Zweig ihn in Z.199/204 nutzt und bei Disable Boiler-OFF feuert. […]
- **bestätigt** (Konfidenz 0.92): Bestätigt nach aktiver Widerlegungsprüfung. (1) Zitat/Zeilen korrekt: __init__.py:208-214 (Raum-Zweig async_unload_entry) macht nur Platform-Unload + async_persist_and_cleanup(); diese Methode (coordinator.py:1051-1070) persistiert und räumt Issues/Notifications — kein Aktor-Zugriff, kein disabled_by-Check. […]

---

### AR-04 · hoch · sicherer Fehler

**async_apply_options überschreibt den live per Klima-Entität gesetzten climate_mode (heat_only/cool_only) bei jedem Options-Submit mit dem stale Formularwert — doppelte Ownership Store vs. Options**

- **Fundstelle:** `custom_components/poise/coordinator.py:622` — `PoiseCoordinator.async_apply_options`
- **Schadensklasse:** ungewolltes Kühlen
- **Verletzte Projektgrenze:** options vs data/Runtime-State: hot-applybares Options-Feld überschreibt store-persistierten Laufzeit-Nutzerintent; wechselnde Präzedenz je nach Ereignis (Options-Save vs Neustart)
- **Codebeleg:** coordinator.py:622: `self._climate_mode = data.get(CONF_CLIMATE_MODE, "auto")` (data = {**entry.data, **entry.options}) — kollidiert mit climate.py:259: `self.coordinator.set_climate_mode(climate_mode_for_hvac(hvac_mode.value))` (persistiert via _save_payload coordinator.py:1023, restauriert in async_bootstrap coordinator.py:559-561)

**Befund:** Unabhängig gefunden von 3 Reviewern (Dimensionen: room-setup, migration, boundaries). _climate_mode hat zwei konkurrierende Eigentümer ohne Abgleich: (a) Live-User-Intent über die Climate-Entity (climate.py:254-259 → set_climate_mode, coordinator.py:461-463), Store-persistiert (Z.1023) und in async_bootstrap restauriert (Z.559-561); (b) das Options-Formular (CONF_CLIMATE_MODE ist vol.Required im 'comfort'-Abschnitt, config_flow.py:117/449-455). Der Update-Listener (__init__.py:37-47) ruft bei JEDEM Options-Save async_apply_options, und Z.622 setzt den Wert bedingungslos aus {**entry.data, **entry.options}. Das Options-Formular füllt sich zudem nur aus dem Config-Merge vor (config_flow.py:826), NICHT aus dem Live-Zustand — der per Entität gewählte Modus ist dort unsichtbar, und als Required-Feld wird er zwingend mitgeschrieben. Ergebnis: Jeder Options-Submit — auch wenn nur ein völlig anderes Feld (z.B. Energiepreis) geändert wird — setzt den gepinnten Modus auf den veralteten Formularwert zurück; der nächste periodische Save (alle 30 Ticks, coordinator.py:1026-1032) persistiert den Revert endgültig. Nach einem Reload gewinnt dagegen wieder der Store-Wert — die beiden Quellen flip-floppen je nach Ereignispfad. Boundary-Violation: options vs data/Store — ein hot-applybares Tuning-Feld überschreibt einen store-persistierten Live-Nutzerzustand; zwei Wahrheitsquellen mit wechselnder Präzedenz. Fix-Richtung: climate_mode als Store-owned behandeln und in async_apply_options nur übernehmen, wenn sich der Options-Wert tatsächlich geändert hat, oder CONF_CLIMATE_MODE aus dem Options-Flow entfernen.

**Mögliches Fehlverhalten im Realbetrieb:** Bei reversiblem Aktor (Klimagerät): Nutzer pinnt HVAC=heat (heat_only, z.B. Kinderzimmer soll nie kühlen), editiert später einen beliebigen Tuning-Wert → Modus fällt auf 'auto' zurück → an einem heißen Tag kühlt die adaptive Kühlung die Zone (nur durch das Outdoor-Lockout cool_min_outdoor teilgedämpft). Spiegelbildlich kann cool_only→auto ungewolltes Heizen reaktivieren. Zusätzlich stiller, dauerhafter Verlust des Nutzer-Intents und sichtbar springende hvac_mode-Anzeige (climate.py:215-224).

**Minimaler Reproduktionsfall / Testidee:** 1) Raum-Zone mit reversiblem climate-Aktor anlegen (Options-Default climate_mode='auto'). 2) An der Poise-Climate-Entity HVAC-Mode 'heat' wählen → coordinator._climate_mode='heat_only', wird persistiert. 3) Optionen öffnen, NUR z.B. den Energiepreis ändern, speichern (Formular zeigt climate_mode='auto' vor). 4) _async_options_updated → structural_unchanged=True → async_apply_options setzt Z.622 _climate_mode='auto'. 5) Nächster Tick: decide_mode darf wieder 'cool'; hvac_mode springt sichtbar von heat auf auto zurück. 6) Alternativ HA neu starten → jetzt gewinnt wieder der Store-Wert — inkonsistente Präzedenz.

**Zur Absicherung nötig:** Keiner — Schreib-/Lesepfade vollständig im Repo belegt (climate.py:259, coordinator.py:461-463/559-561/622/1023, __init__.py:37-47, config_flow.py:449/826). Kein Test deckt async_apply_options ab (siehe eigenes Testlücken-Finding).

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Widerlegungsversuch fehlgeschlagen — alle Pfade am Code belegt. (1) Live-Intent: climate.py:254-259 → set_climate_mode; coordinator.py:461-463 setzt _climate_mode + _dirty. (2) Persistenz/Restore: _save_payload coordinator.py:1023, _maybe_save Z.1026-1032 (bei _dirty sofort), Restore in async_bootstrap Z.559-561. (3) Zweiter Eigentümer: config_flow.py:449-455 vol.Required(CONF_CLIMATE_MODE) im comfort-Abschnitt (Z.116); Prefill Z.826 nur aus {**entry.data, **entry.options} — Live-Zustand unsichtbar, Required-Feld wird zwingend mitgesendet. […]
- **bestätigt** (Konfidenz 0.93): Alle Code-Zitate und Zeilennummern verifiziert und korrekt. Fehlerpfad im Realbetrieb erreichbar, kein Guard widerlegt das Finding: (1) coordinator.py:622 setzt _climate_mode bedingungslos aus {**entry.data, **entry.options} (Z.588); (2) der vermeintliche Guard structural_unchanged (coordinator.py:1072-1079) vergleicht nur entry.data und lässt Options-only-Saves explizit durch (__init__.py:46-47); (3) set_climate_mode (coordinator.py:461-463, aufgerufen von climate.py:259) schreibt nie nach entry.options zurück — async_update_entry existiert nu […]

---

### AR-05 · hoch *(Erst-Einstufung: kritisch)* · begründeter Verdacht

**Hub verwirft unavailable-safe-Zonen komplett: lokaler Frostschutz parkt TRV auf heat@7°C, aber der geteilte Boiler feuert nicht — Frostschutzkette reißt an der Zone→Hub-Grenze**

- **Fundstelle:** `custom_components/poise/hub_coordinator.py:144` — `PoiseHubCoordinator._collect_requests`
- **Schadensklasse:** Frost-/Mould-Schutz versagt
- **Verletzte Projektgrenze:** safety vs comfort + lokale Raumzone vs System-Hub: lokale Zone fail-toward-warmth, Hub fail-toward-cold; Doku behauptet erhaltenen Frostschutz nur für den anderen Degradationspfad
- **Codebeleg:** hub_coordinator.py:143-144: `if not isinstance(data, dict) or not data.get("available"): continue` — vs. coordinator.py:1250-1252: `await self._write_unavailable_safe_state(); return {"available": False, "unavailable_safe": True}` — vs. hub_aggregate.py:70-72 (V9-Doku): "Frost safety is preserved: a last-plausible cold reading still trips frost_active"

**Befund:** Unabhängig gefunden von 2 Reviewern (Dimensionen: hub-setup, boundaries). Es gibt zwei Sensor-Degradationspfade der Zone, nur einer ist hubseitig frostsicher: (1) sensor_frozen (Wert stale, aber vorhanden): Zone publiziert vollen Snapshot mit available:True und Temperatur; zone_request_from_data (hub_aggregate.py:73-84) leitet frost_active aus der letzten plausiblen Temperatur ab — Frost-Override feuert den Boiler. Genau das beschreibt die V9-Doku. (2) Sensor-Entity unavailable (air is None, coordinator.py:1226): Nach 30 min (UNAVAILABLE_SAFE_AFTER_S=1800.0, const.py:39) publiziert die Zone nur {"available": False, "unavailable_safe": True} — OHNE mono_ts, OHNE Temperatur, OHNE heating — und schreibt den Aktor lokal auf heat@FROST_FLOOR_C=7.0 (coordinator.py:1185-1214, lifecycle.py:46-52, 'fail toward warmth'). Der Hub verwirft diese Zone in Zeile 144 vollständig; zusätzlich würde das fehlende mono_ts in Z.159 fail-closed droppen. Sie taucht weder in aggregate_boiler_demand noch in frost_excluded auf; das N-2-Repair-Issue (hub_aggregate.py:153-155, hub_coordinator.py:302-323) erfasst nur Zonen, die IN requests sind bzw. ohne controls_boiler. Bei einer hydronischen controls_boiler-Zone ist der lokale Safe-State ohne feuernden Kessel wirkungslos: offener TRV, kaltes Wasser. Zonenseite failt Richtung Wärme, Hubseite failt Richtung Kälte — inkonsistent; die Doku deckt nur Pfad (1) ab. Boundary-Violation: safety vs comfort + lokale Raumzone vs System-Hub — der lokale Safe-State setzt stillschweigend voraus, dass die Wärmequelle verfügbar ist, aber der Snapshot-Vertrag transportiert den Sicherheitsbedarf einer degradierten Zone nicht; Doku-vs-Code: hub_aggregate.py:70-72 behauptet erhaltenen Frostschutz bei Sensorverlust, der Code liefert das nur für den sensor_frozen-Pfad. Testlücke: test_hub_tier0.py und tests/integration/test_hub_glue_coverage.py testen frost_active/frost_excluded nur für available:True-Zonen.

**Mögliches Fehlverhalten im Realbetrieb:** Winter-Szenario: einzige (oder einzige kalte) controls_boiler-Zone (z.B. Garage/Werkstatt), Batterie des Raumsensors stirbt. Nach 30 min parkt die Zone den TRV auf heat@7°C, der Hub sieht 0 Requests → demand=False → Boiler bleibt AUS. Der Raum unterschreitet den Frost-Floor, während die Integration lokal 'Frostschutz aktiv' signalisiert. Kein hubseitiges Repair-Issue für die verlorene Boiler-Abdeckung.

**Minimaler Reproduktionsfall / Testidee:** 1 Hub-Entry mit ON/OFF-Actions + 1 Room-Entry (controls_boiler=True, Klima-TRV). Zone heizt normal. Raumsensor-Entity auf 'unavailable' setzen und >30 min halten. Beobachten: Zone schreibt heat/7.0 auf den TRV (unavailable_safe), Hub-Tick liefert zone_count=0, boiler_demand=False, frost_override=False, frost_excluded=[]; Boiler wird nicht gefeuert. Vergleich: derselbe Sensor mit eingefrorenem (stale) Wert 6°C → frost_override=True, Boiler feuert.

**Zur Absicherung nötig:** Ist als Systemannahme dokumentiert, dass der Kessel eine eigene interne Frostschutzfunktion hat, oder dass unavailable-safe nur für selbstheizende Aktoren (Elektro-Klimageräte) gedacht ist? Falls ja, wäre es 'nur' eine Doku-/Repair-Issue-Lücke; falls nein, ein Safety-Designfehler. Fix-Richtung: unavailable_safe-Zone mit controls_boiler als Heat-Call werten oder mindestens als eigenes Repair-Issue surfacen.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.88) (Schweregrad korrigiert → mittel): Mechanik vollständig code-bestätigt: coordinator.py:1251 publiziert im unavailable-safe-Fall nur {"available": False, "unavailable_safe": True} (ohne mono_ts/Temperatur; Kommentar 1100-1102 hält den Dict absichtlich minimal), hub_coordinator.py:144 verwirft die Zone daher komplett; sie erscheint weder in aggregate_boiler_demand noch in frost_excluded (hub_aggregate.py:153-155 erfasst nur Zonen IN requests), und _update_frost_issues (hub_coordinator.py:302-323) erzeugt kein Issue dafür. […]
- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → hoch): Bestätigt nach Code-Lektüre; Widerlegung nicht möglich. Alle zitierten Stellen stimmen: hub_coordinator.py:144 verwirft jede Zone mit available!=True; der unavailable-safe-Snapshot ist exakt {"available": False, "unavailable_safe": True} (coordinator.py:1250-1251) ohne mono_ts/Temperatur/heating (Vollsnapshot mit available:True/mono_ts/current_temperature nur im Normalpfad, coordinator.py:2330/2342/2343); Fallback-Drop über fehlendes mono_ts in hub_coordinator.py:159 ebenfalls korrekt. […]

---

### AR-06 · hoch · Testlücke

**Testlücke Hub-Lifecycle: Timer-Registrierung, Timer-Abbestellung beim Unload und 'nur BINARY_SENSOR wird geforwarded' — kein Test feuert je den Zeitgeber**

- **Fundstelle:** `tests/integration/test_setup_and_cycle.py:136` — `test_system_hub_setup_creates_binary_sensor`
- **Schadensklasse:** Batterie-/Zigbee-Schreibsturm
- **Verletzte Projektgrenze:** lokale Raumzone vs System-Hub: der Hub-eigene Lifecycle (unabhängiger Timer, reduziertes Plattform-Forwarding) ist genau die Grenze, die kein Test zieht; F2-Kommentar behauptet dauerhaftes Aggregieren, das nie über den echten Zeitpfad verifiziert wird
- **Codebeleg:** __init__.py:97-101: `entry.async_on_unload(async_track_time_interval(hass, _hub_tick, timedelta(seconds=TICK_INTERVAL_S)))` — von keinem Test via async_fire_time_changed getrieben

**Befund:** Dimension: test-gap. test_system_hub_setup_creates_binary_sensor (tests/integration/test_setup_and_cycle.py:136-152) prüft nur LOADED und 'binary_sensor' IN domains — nicht domains == {'binary_sensor'} (das Nicht-Forwarden von CLIMATE/SENSOR/SWITCH für den Hub bleibt unbelegt). Der F2-Kommentar in __init__.py:86-87 behauptet, der unabhängige Timer halte die Boiler-Aktuation auch bei deaktivierter Diagnostic-Entity am Leben — Grep über tests/ zeigt: kein Test verwendet async_fire_time_changed oder async_track_time_interval; alle Hub-Tests (test_review_v083_fixes.py:142, test_hub_glue_coverage.py:103-109) rufen hub.runtime_data.async_refresh() bzw. hub._actuate() DIREKT auf. Ungetestet: (1) dass der Timer registriert ist und _hub_tick → async_refresh treibt, (2) dass entry.async_on_unload ihn beim Unload cancelt. Auch der Hub-Unload-Glue-Pfad 'plain reload feuert KEIN Boiler-OFF' (__init__.py:197-202) existiert nur als pure Test (tests/test_lifecycle_pure.py:134-137), nie über hass.config_entries.async_reload eines aktuierenden Hubs.

**Mögliches Fehlverhalten im Realbetrieb:** Eine Regression, die den Timer außerhalb von entry.async_on_unload registriert (oder das Remover-Handle verliert), erzeugt einen Zombie-Timer: Nach Unload/Reload ticken zwei Hub-Coordinators parallel und feuern konkurrierende Boiler-ON/OFF-Keepalives (60-s-Schreibsturm auf den Boiler-Switch, Boiler kann von einem toten Entry weitergeheizt werden). Umgekehrt würde ein versehentlich entferntes Timer-Setup den Hub bei deaktivierter Diagnostic-Entity komplett einfrieren (Boiler bleibt im letzten Zustand) — beides fiele heute keinem Test auf.

**Minimaler Reproduktionsfall / Testidee:**

```python
# tests/integration/test_setup_and_cycle.py
from datetime import timedelta
from unittest.mock import patch
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from custom_components.poise.const import TICK_INTERVAL_S

async def test_hub_timer_ticks_and_dies_on_unload(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="poise_system", title="Poise System",
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_COUNT_THRESHOLD: 1},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hub = entry.runtime_data

    # (1) Forwarding ist exakt BINARY_SENSOR
    reg = er.async_get(hass)
    domains = {e.domain for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    assert domains == {"binary_sensor"}

    # (2) der unabhängige Timer treibt den Hub-Tick (F2)
    with patch.object(type(hub), "async_refresh", autospec=True) as refresh:
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=TICK_INTERVAL_S + 1))
        await hass.async_block_till_done()
        assert refresh.await_count >= 1

    # (3) nach Unload feuert der Timer nicht mehr (kein Boiler-Zombie)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    with patch.object(type(hub), "async_refresh", autospec=True) as refresh2:
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3 * TICK_INTERVAL_S))
        await hass.async_block_till_done()
        assert refresh2.await_count == 0
```

**Zur Absicherung nötig:** Keiner — TICK_INTERVAL_S ist in const.py verfügbar, async_fire_time_changed ist Teil von pytest-homeassistant-custom-component (bereits in requirements-test.txt).

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Widerlegung fehlgeschlagen — alle Kernbehauptungen verifiziert. (1) Grep über tests/ nach async_fire_time_changed|async_track_time_interval: null Treffer; alle Hub-Tests treiben den Tick direkt (test_review_v083_fixes.py:142/149/344/352 via hub.runtime_data.async_refresh(), test_hub_glue_coverage.py:103/107/130 via hub._actuate()). (2) tests/integration/test_setup_and_cycle.py:152 prüft nur 'assert "binary_sensor" in domains' — das exklusive Forwarding (__init__.py:102-104 forwarded nur [Platform.BINARY_SENSOR]) bleibt unbelegt. […]
- **bestätigt** (Konfidenz 0.9): Testlücke bestätigt, alle Kernbehauptungen halten aktiver Widerlegung stand. (1) Code-Quote exakt: __init__.py:97-101 registriert den Hub-Timer via entry.async_on_unload(async_track_time_interval(...)); F2-Kommentar Z.86-87, Unload-Glue Z.197-202. (2) Grep über tests/ nach async_fire_time_changed|async_track_time_interval: null Treffer — kein Test treibt je den Zeitpfad. […]

---

### AR-07 · mittel *(Erst-Einstufung: hoch)* · sicherer Fehler

**Vakanter Test: test_remove_hub_swallows_off_failure erreicht den Fehlerpfad nie (nur OFF-Action gewired → F12-Gate überspringt den Call) — Boiler-OFF-Fehlerbehandlung bei Hub-Remove faktisch ungetestet**

- **Fundstelle:** `tests/integration/test_glue_coverage4.py:131` — `test_remove_hub_swallows_off_failure`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** Safety-Pfad (Boiler-Rückgabe) vs Komfort: der einzige Test des Safety-Fehlerpfads bestätigt nur sein eigenes Mock-Setup; Kommentar behauptet Verhalten, das der Code (enge except-Tuple) nicht hat
- **Codebeleg:** tests/integration/test_glue_coverage4.py:131-146: `data={CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM, CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off"}` — nur OFF gewired; __init__.py:242: `if on is not None and off is not None:` überspringt den Call komplett

**Befund:** Dimension: test-gap. Der Test registriert einen werfenden switch.turn_off-Handler und behauptet im Kommentar 'OFF call raises → best-effort, swallowed'. Er konfiguriert den Hub aber NUR mit CONF_BOILER_OFF_ACTION. __init__.py:242 gated den OFF-Call auf beide Actions (F12-Gate) — mit fehlender ON-Action wird hass.services.async_call nie ausgeführt, der _boom-Handler nie aufgerufen, und der Test hat keine einzige Assertion: er ist grün, egal was der Fehlerpfad tut. Doppelt brisant: Der reale Fehlerpfad __init__.py:247 fängt nur `except (HomeAssistantError, ValueError)`. Der im Test verwendete RuntimeError würde bei blocking=True NICHT gefangen — _remove_hub_entry bräche VOR `ir.async_delete_issue(...)` (Z.251) ab. Wäre der Test korrekt verdrahtet (beide Actions), würde er FEHLSCHLAGEN und genau diese Lücke aufdecken. Der Docstring __init__.py:229 ('an execution error is observed not swallowed, F27') beschreibt zudem ein anderes Verhalten als der Code (loggen + weiterlaufen). Siehe verwandtes Finding zur zu engen except-Tuple (vol.Invalid).

**Mögliches Fehlverhalten im Realbetrieb:** Wirft die Boiler-Integration beim Deinstallieren des Hubs eine Nicht-HomeAssistantError-Exception (RuntimeError/TimeoutError aus hängendem Zigbee/Modbus-Stack), bleibt der Boiler im letzten Zustand (potenziell AN) UND das Frost-Repair-Issue 'frost_zone_not_controlling_boiler' überlebt die Deinstallation, weil die Cleanup-Zeile nie erreicht wird. Kein Test bemerkt eine Regression — der bestehende Test bestätigt nur ein Mock-Setup, das den Code gar nicht durchläuft.

**Minimaler Reproduktionsfall / Testidee:**

```python
# tests/integration/test_glue_coverage4.py — Ersatz für den vakanten Test
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

async def test_remove_hub_swallows_off_failure_and_clears_issue(hass: HomeAssistant) -> None:
    calls: list[ServiceCall] = []
    async def _boom(call: ServiceCall) -> None:
        calls.append(call)
        raise HomeAssistantError("boiler stuck")
    hass.services.async_register("switch", "turn_off", _boom)
    async_mock_service(hass, "switch", "turn_on")
    hub = MockConfigEntry(
        domain=DOMAIN, unique_id="poise_system", title="Poise System",
        data={
            CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
            CONF_BOILER_ON_ACTION: "switch.boiler/switch.turn_on",   # BEIDE Actions,
            CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",  # sonst greift das F12-Gate
        },
    )
    hub.add_to_hass(hass)
    ir.async_create_issue(hass, DOMAIN, "frost_zone_not_controlling_boiler",
        is_fixable=False, severity=ir.IssueSeverity.WARNING,
        translation_key="frost_zone_not_boiler")

    await async_remove_entry(hass, hub)  # darf nicht raisen

    assert len(calls) == 1  # der Fehlerpfad wurde wirklich betreten
    # F16: trotz OFF-Fehler wird das Repair-Issue entsorgt
    assert (DOMAIN, "frost_zone_not_controlling_boiler") not in ir.async_get(hass).issues

# Zweite Variante mit RuntimeError statt HomeAssistantError: deckt die zu enge
# except-Tuple in __init__.py:247 auf (schlägt aktuell fehl → Code-Fix nötig).
```

**Zur Absicherung nötig:** Bestätigung, ob F27 ('observed not swallowed') bewusst nur Logging meint oder ob Nicht-HA-Exceptions absichtlich propagieren sollen; HA fängt Exceptions aus async_remove_entry in config_entries generisch, aber dann entfällt die Issue-Bereinigung.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92) (Schweregrad korrigiert → mittel): Kern bestätigt: test_remove_hub_swallows_off_failure (tests/integration/test_glue_coverage4.py:131-146) ist beweisbar vakant. Er wired nur CONF_BOILER_OFF_ACTION (Z.139-141), hat keine Assertion, und das F12-Gate in custom_components/poise/__init__.py:242 ("if on is not None and off is not None:") überspringt den Service-Call, weil parse_service_action(None) None liefert (control/hub_aggregate.py:205-206). […]
- **bestätigt** (Konfidenz 0.92) (Schweregrad korrigiert → mittel): Bestätigt mit direktem Beleg. (1) Der Test tests/integration/test_glue_coverage4.py:131-146 konfiguriert nur CONF_BOILER_OFF_ACTION (Z.141), keine ON-Action, und enthält keine einzige Assertion. (2) Das F12-Gate __init__.py:242 (`if on is not None and off is not None:`) überspringt den Service-Call, da parse_service_action(None) None liefert (hub_aggregate.py:205-206) — der werfende _boom-Handler wird nie aufgerufen; der Test ist vakant/grün, egal was der Fehlerpfad tut. […]

---

### AR-08 · mittel · begründeter Verdacht

**Hub verliert bei HA-Stop/Restart sämtlichen Boiler-Takt-Zustand: kein Stop-Handler, keine Persistenz, Keepalive kein Dead-Man-Netz, Reconcile misinterpretiert Script-Entities, Min-Off nach Restart verletzbar**

- **Fundstelle:** `custom_components/poise/hub_coordinator.py:256` — `PoiseHubCoordinator._actuate / hub_aggregate.reconcile_boiler_on`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** measured vs estimated: reconcile adoptiert den Entity-State des Action-Ziels als gemessenen Boiler-Ist-Zustand, auch wenn diese Entity (Script) den Boiler gar nicht misst; ADR-0006/0007-Grenze (restart-persistente Timer) nur zonenseitig eingehalten; F7-Stop-Flush-Muster asymmetrisch nur für Raum-Entries
- **Codebeleg:** hub_coordinator.py:256-259: `ent = self._action_on.data.get("entity_id"); st = self.hass.states.get(ent); real = reconcile_boiler_on(st.state if st is not None else None)` — hub_aggregate.py:507-509: `if state is None or state in ("unknown", "unavailable"): return None; return state != "off"` — hub_aggregate.py:317: Default last_switch_mono=-1.0e9 ('allow an immediate first switch')

**Befund:** Unabhängig gefunden von 2 Reviewern (Dimensionen: unload, docs-vs-code). Vier zusammenhängende Defekte an derselben Stelle: (1) Nur der Raum-Pfad registriert EVENT_HOMEASSISTANT_STOP (__init__.py:133-139); der Hub-Zweig registriert nichts, BoilerState wird nirgends persistiert — bei HA-Stop bleibt der Boiler physisch AN (ADR-0039 sagt zum Stop-Verhalten nichts). (2) Das Keepalive (Re-Assert alle 300 s) ist reiner Sender-Resend gegen verlorene Service-Calls und schützt während HA-Downtime nur, wenn der EMPFÄNGER ein eigenes Timeout hat — diese Installationsvoraussetzung ist nirgends dokumentiert; das Netz entfällt komplett bei keepalive_s=0 (hub_aggregate.py:382, konfigurierbar). (3) Die V2b-Boot-Reconcile adoptiert den Ist-Zustand ausschließlich über den Entity-State des ersten Action-Spec-Segments (parse_service_action, hub_aggregate.py:211); ist das Ziel eine script.*/automation.*-Entity, ist deren State 'off' (Script läuft nicht) und reconcile_boiler_on liefert False: der Hub glaubt fälschlich 'Boiler aus', obwohl er physisch AN ist — ohne Demand entsteht kein Übergang, gerettet nur durch das Keepalive-OFF, das bei keepalive_s=0 fehlt. (4) Bis der Boiler-Aktor lesbar ist (reconcile liefert None bei unavailable), läuft die demand-getriebene ON/OFF-Maschine bewusst weiter (F29) mit Default last_switch_mono=-1.0e9 — gate_min_cycle sofort offen, mit activation_delay=0 (const.py:149) feuert der erste Tick mit Demand sofort ON, auch wenn der Boiler Sekunden vor dem Restart OFF geschaltet wurde: Min-Off verletzt, Kurztakt. Doku-Widerspruch: ADR-0039 Punkt 4 verkauft Min-On/Min-Off/Keep-Alive als Takt-/Pumpenschutz, clock.py:4-5 verspricht 'Wall-clock anchors for restart-persistent timers' — raumseitig für multi_lifecycle umgesetzt (coordinator.py:526-532), hubseitig überlebt kein einziger Timer den Restart.

**Mögliches Fehlverhalten im Realbetrieb:** Boiler-Kurztakt über einen HA-Restart hinweg (Min-Off-Bruch), wenn Zonensensorik (WiFi) vor dem Boiler-Schalter (Zigbee) verfügbar wird; Boiler läuft während HA-Ausfall (Crash, SD-Karten-Tod, langes Update) unbegrenzt weiter, falls der Empfänger kein eigenes Timeout hat; nach Neustart mit Script-basierter ON-Action plus keepalive_s=0 schaltet Poise einen physisch laufenden Boiler auch aktiv nie ab (falsche Off-Adoption).

**Minimaler Reproduktionsfall / Testidee:** (a) Hub mit Aktuation, min_off=300 s; Hub schaltet Boiler OFF; HA innerhalb <300 s neu starten; Boiler-Schalter (Zigbee) braucht 2-3 min bis verfügbar, Raumsensoren sofort da mit Heizbedarf → erster Hub-Tick: _reconciled=False, BoilerState default, demand=True, activation_delay=0 → call='on' sofort → Min-Off verletzt. (b) Boiler über Poise AN, HA hart stoppen: kein OFF, keine Keepalives — Empfänger ohne Timeout bleibt AN. (c) ON/OFF-Action als script.boiler_on/script.turn_on, keepalive_s=0, HA neu starten während Boiler physisch AN und Demand unter Schwelle: reconcile_boiler_on('off')→False, 'off' adoptiert, nie ein OFF-Call.

**Zur Absicherung nötig:** Produktentscheidung, ob ein empfängerseitiges Watchdog-Timeout dokumentierte Voraussetzung für den Aktuationsmodus ist (README/Docs erwähnen es nicht); ob reconcile auf Nicht-Switch-Entities (script/automation/scene) explizit None liefern sollte statt state!='off'. Fix-Optionen: BoilerState mit Wall-Clock-Anker persistieren (wie multi_lifecycle) oder demand-ON bis zum ersten erfolgreichen Reconcile gaten bzw. last_switch_mono beim ersten Tick auf 'now' stempeln.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9): Alle vier Teilbefunde code-verifiziert, keine falsche HA-Annahme gefunden. (1) Hub-Zweig in __init__.py:80-105 registriert keinen EVENT_HOMEASSISTANT_STOP-Handler (nur Raum-Pfad, Z.133-139) und hub_coordinator.py enthält keinerlei PoiseStore/Persistenz — BoilerState ist rein in-memory; die HA-Annahme "async_unload_entry läuft nicht bei Stop" ist korrekt (vom Code selbst in Z.131-133 dokumentiert), der F4-Unload-OFF greift bei Stop also nicht. […]
- **bestätigt** (Konfidenz 0.85): Alle vier Teilbefunde code-verifiziert, Widerlegung fehlgeschlagen. (1) EVENT_HOMEASSISTANT_STOP nur im Raum-Zweig (__init__.py:133-137); Hub-Zweig (__init__.py:80-105) registriert keinen Stop-Handler, storage.py persistiert keinerlei Hub-/BoilerState. (2) Keepalive ist reiner Sender-Resend (hub_aggregate.py:381-396), per Config-Flow auf 0 setzbar (config_flow.py:350-357, NumberSelector min=0); README:41 und ADR-0039 Punkt 4 verkaufen Keep-Alive/Min-Cycle als Schutz, ein empfängerseitiges Watchdog-Timeout wird nirgends dokumentiert (Grep docs/  […]

---

### AR-09 · mittel · sicherer Fehler

**_STRUCTURAL_CARRY reanimiert vom Nutzer gelöschte Anlagen-Felder (declared_power, compressor_group, design_flow_temp), sobald ein System-Hub existiert — Kommentar behauptet das Gegenteil**

- **Fundstelle:** `custom_components/poise/config_reconcile.py:72` — `reconcile_reconfigure`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** lokale Raumzone vs System-Hub: nicht löschbare Anlagen-Verdrahtung hält eine Zone in der Hub-Aggregation; Kommentar widerspricht ausgeführtem Code
- **Codebeleg:** config_reconcile.py:68-74: `if k not in user_input and k in _STRUCTURAL_CARRY` — Kommentar Z.17-20: "When the form hides them, their absence from user_input means 'not shown', not 'cleared'"

**Befund:** Dimension: migration. Der Code kann 'nicht angezeigt' und 'geleert' nicht unterscheiden: Er trägt JEDEN _STRUCTURAL_CARRY-Key aus old_data zurück, der nicht in user_input steht. Sobald ein Hub existiert, rendert die Reconfigure-Form die anlagen-Sektion (config_flow.py:217-255) mit vol.Optional(CONF_COMPRESSOR_GROUP), vol.Optional(CONF_DECLARED_POWER) und vol.Optional(CONF_FLOW_TEMP). Leert der Nutzer ein solches optionales Feld, lässt das HA-Frontend den Key im Submit weg (Standardverhalten optionaler Felder) → `k not in user_input` → der alte Wert wird wieder in data geschrieben. Ein einmal gesetztes declared_power/compressor_group/flow_temp ist über die UI nicht mehr entfernbar. Nur CONF_CONTROLS_BOILER (Required mit Default) und CONF_SOURCE_POLICY (Dropdown) sind nicht betroffen.

**Mögliches Fehlverhalten im Realbetrieb:** declared_power fließt gewichtet in die Boiler-Bedarfsaggregation (hub_coordinator.py:161-168; hub_aggregate.py:136) und den Lastabwurf (hub_aggregate.py:283-295) ein; compressor_group in die Verdichtergruppen-Logik (hub_aggregate.py:307-308). Ein Nutzer, der z.B. einen stillgelegten Heizkörper aus der Boiler-Gewichtung nimmt, indem er declared_power löscht, bekommt den Wert still zurück — die Zone zählt weiter für Boiler-EIN-Entscheidungen; der Boiler kann auf Bedarf einer nicht mehr angeschlossenen Zone feuern.

**Minimaler Reproduktionsfall / Testidee:** 1) System-Hub-Entry anlegen. 2) Raum-Entry reconfigurieren, in der anlagen-Sektion declared_power=1500 setzen. 3) Erneut reconfigurieren, declared_power leeren, speichern. 4) entry.data enthält weiterhin declared_power=1500; der Hub aggregiert die Zone weiter gewichtet.

**Zur Absicherung nötig:** Bestätigung des HA-Frontend-Verhaltens, dass geleerte vol.Optional-Number/Text-Felder aus user_input entfernt werden (dokumentiertes Standardverhalten; genau darauf baut die Sensor-Sektion desselben Files laut Kommentar Z.18-20 auf). Der Kommentar-Code-Widerspruch ist unabhängig davon belegt. Fix-Richtung: Carry nur anwenden, wenn die anlagen-Sektion NICHT gerendert wurde (hub_exists an reconcile_reconfigure durchreichen).

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): BESTÄTIGT mit Severity-Downgrade auf niedrig. Beweiskette: (1) config_reconcile.py:68-74 trägt jeden _STRUCTURAL_CARRY-Key aus old_data zurück, der nicht in user_input steht; die Funktion (Z.47-52) erhält kein hub_exists und kann 'nicht angezeigt' nicht von 'geleert' unterscheiden — der Kommentar Z.16-20 ('When the form hides them...') widerspricht dem ausgeführten Code. […]
- **bestätigt** (Konfidenz 0.85): Bestätigt nach Widerlegungsversuch. Beleg: config_reconcile.py:68-74 trägt jeden _STRUCTURAL_CARRY-Key aus old_data zurück, sobald er in user_input fehlt — ohne zu wissen, ob die anlagen-Sektion gerendert wurde. config_flow.py:217-255 rendert bei existierendem Hub genau diese Keys als vol.Optional (COMPRESSOR_GROUP TextSelector, DECLARED_POWER/FLOW_TEMP NumberSelector-BOX, SOURCE_POLICY Select); der Aufruf config_flow.py:786-788 reicht hub_exists nicht durch, flatten_sections (config_sections.py:30-34) fügt keine Keys ein — kein Guard existiert […]

---

### AR-10 · mittel · begründeter Verdacht

**resolve_park_command klemmt den Setback-Setpoint nicht an device min_temp — set_temperature kann still scheitern und das Gerät bleibt in 'heat' auf dem alten Komfort-Setpoint**

- **Fundstelle:** `custom_components/poise/control/lifecycle.py:96` — `resolve_park_command`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** safety vs comfort: der F1-Pfad (safe state) hat die min_temp-Klemmung, der strukturell gleiche F3-Pfad (park) nicht — Inkonsistenz zwischen zwei Safety-Endzustands-Resolvern derselben Datei
- **Codebeleg:** lifecycle.py:96: `sp = floor if setback_setpoint is None else max(floor, setback_setpoint)` — kein device_min; Kontrast resolve_safe_state lifecycle.py:47: `target = floor if device_min is None else max(floor, device_min)`

**Befund:** Dimension: remove. resolve_safe_state bekommt device_min und klemmt explizit ('clamped up to the device min_temp so a high-min AC does not thrash', lifecycle.py:41-47). resolve_park_command bekommt device_min gar nicht; der Aufrufer (__init__.py:277-287) reicht nur comfort_base-setback_delta durch. Per Config-Flow ist comfort_base>=16.0 und setback_delta<=8.0 (config_flow.py:283-284, 475-476) → Setback bis 8.0 °C, geklemmt nur an FROST_FLOOR_C=7.0. HA-Core-Climate validiert set_temperature gegen min/max_temp und wirft ServiceValidationError; ein reversibles Klimagerät/eine Wärmepumpe mit min_temp 16-17 °C lehnt 8-15 °C ab. Da _execute_park blocking=False sendet, landet der Fehler nur als Hintergrund-Task-Log: set_hvac_mode('heat') greift, der Setpoint-Write nicht.

**Mögliches Fehlverhalten im Realbetrieb:** Gerät steht nach dem Löschen dauerhaft und unbeaufsichtigt in 'heat' auf seinem VORHERIGEN Setpoint (z.B. dem letzten Poise-Komfort-Setpoint 21 °C) statt auf Setback — ungewolltes Heizen ohne Regler, Energieverschwendung; im Sommer heizt ein reversibles Gerät gegen die Kühllast an.

**Minimaler Reproduktionsfall / Testidee:** Raum-Entry mit reversiblem climate-Gerät (min_temp=16), comfort_base=16, setback_delta=8 (beides im Flow erlaubt). Entry löschen: Plan = ('climate','heat',8.0). set_hvac_mode('heat') OK; set_temperature(8.0) → ServiceValidationError im Hintergrund-Task, unbeobachtet. Gerät heizt weiter auf altem Setpoint.

**Zur Absicherung nötig:** min_temp ist im Aufrufer verfügbar (st.attributes.get('min_temp')) — analog zu resolve_safe_state durchreichen und max(floor, setback, device_min) bilden.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9): Widerlegung fehlgeschlagen — alle tragenden Behauptungen halten der Prüfung stand. (1) Code: resolve_park_command (lifecycle.py:69-76) hat keinen device_min-Parameter; Z. 96 klemmt nur an floor=FROST_FLOOR_C=7.0. Der strukturgleiche F1-Resolver resolve_safe_state klemmt an device_min (lifecycle.py:47, Doku Z. 34-37 'high-min AC'), und dessen Aufrufer liest min_temp explizit (coordinator.py:1189: device_min=_num_attr(act, "min_temp")). Der Park-Aufrufer __init__.py:277-287 liest min_temp nicht, obwohl st (Z. 271) vorliegt. […]
- **bestätigt** (Konfidenz 0.9): Widerlegungsversuch gescheitert; alle Behauptungen am Code und an HA-Core 2025.1 verifiziert. (1) Zitat exakt: custom_components/poise/control/lifecycle.py:96 klemmt nur an floor (`max(floor, setback_setpoint)`), Signatur (Z.69-76) hat keinen device_min-Parameter; resolve_safe_state klemmt dagegen an device_min (lifecycle.py:47, Docstring Z.34-36). […]

---

### AR-11 · mittel · begründeter Verdacht

**Raum-Remove aktuiert auch bei nie erfolgreichem Setup: Park + Select-Restore feuern auf ein Gerät, das Poise nie kommandiert hat**

- **Fundstelle:** `custom_components/poise/__init__.py:288` — `_remove_room_entry`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** diagnostic-only vs live: ein Entry, der nur je 'konfiguriert', nie 'kontrollierend' war, wirkt beim Löschen aktorisch; Asymmetrie zum gated Hub-Unload (resolve_hub_unload_off)
- **Codebeleg:** __init__.py:288-289: `await _execute_park(hass, actuator, plan)\nawait _restore_trv_internal(hass, actuator)` — kein Check, ob der Entry je geladen war / Poise je geschrieben hat

**Befund:** Dimension: remove. async_remove_entry wird auch für Entries gerufen, die nie erfolgreich geladen wurden (ConfigEntryNotReady-Retry-Schleife wegen fehlendem Temp-Sensor, __init__.py:117-122). Der Remove-Pfad arbeitet bewusst nur auf entry.data (korrekt, da runtime_data weg ist), prüft aber dadurch auch nicht, ob Poise das Gerät je kontrolliert hat. Ein falsch ausgewählter Aktor (z.B. das Klimagerät eines anderen Raums) bekommt beim Löschen des nie funktionsfähigen Entries set_hvac_mode('heat') + Setback-Setpoint plus den Select-Flip auf 'internal' aufgezwungen. Das ist die Raum-Variante desselben 'verdrahtet != kommandiert'-Problems wie beim Hub-Remove: der Hub-Unload-Pfad hat dafür ein Gate (was_actuating), Raum-Remove hat keines. Positiv geprüft: alle Schritte funktionieren technisch ohne runtime_data (states, registry, PoiseStore, Trace-Pfad nur aus entry_id).

**Mögliches Fehlverhalten im Realbetrieb:** Umkonfiguration eines fremden/nie kontrollierten Geräts beim Aufräumen fehlgeschlagener Entries: erzwungenes 'heat'@Setback (ungewolltes Heizen im Sommer bzw. Überschreiben einer bewussten Off-Stellung) und verstellte Sensor-Source.

**Minimaler Reproduktionsfall / Testidee:** Raum-Entry mit korrektem Aktor, aber nicht existentem Temp-Sensor anlegen → Setup bleibt in Retry, Poise schreibt nie. Entry im Retry-Zustand löschen → set_hvac_mode('heat') + set_temperature(setback) + select_option('internal') werden trotzdem abgesetzt.

**Zur Absicherung nötig:** Marker 'Poise hat diesen Aktor je beschrieben' (persistiert im PoiseStore oder entry-Flag) als Gate für Park/Restore; alternativ mindestens entry.state/disabled_by-Heuristik, sofern im Remove-Kontext verfügbar.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.8) (Schweregrad korrigiert → niedrig): Nicht widerlegbar — alle Kernbehauptungen halten der Prüfung stand. (1) Kein Gate: __init__.py:269-289 prüft nur, ob der Aktor-String gesetzt ist und ein State existiert; _execute_park (Z.288) und _restore_trv_internal (Z.289) feuern bedingungslos, ohne runtime_data und ohne jeden "Poise hat je geschrieben"-Marker (Grep: ein solcher Marker existiert nur als hub.actuation_active für den Hub-Unload, hub_coordinator.py:326). […]
- **bestätigt** (Konfidenz 0.85): Bestätigt nach aktivem Widerlegungsversuch. (1) Code-Zitat stimmt: __init__.py:288-289 feuern _execute_park + _restore_trv_internal; einziger Guard ist "isinstance(actuator, str) and actuator" (Z.270) — kein Gate auf "Entry je geladen" oder "Poise hat je geschrieben". (2) Erreichbarkeit HA-seitig belegt: HA-Core ConfigEntries.async_remove ruft nach dem Unload BEDINGUNGSLOS component.async_remove_entry (config_entries.py:1439-1441, 708-712); für SETUP_RETRY macht entry.async_unload nur cancel_retry+NOT_LOADED ohne Integrationsaufruf (Z.657-660). […]

---

### AR-12 · mittel · begründeter Verdacht

**Room-Reconfigure auf anderen Aktor: alter TRV bleibt auf 'external'-Sensorquelle mit eingefrorenem Feed und wird nicht geparkt — F3/F6-Cleanup existiert nur im Delete-Pfad**

- **Fundstelle:** `custom_components/poise/config_flow.py:789` — `async_step_reconfigure`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** Lifecycle-Grenze der lokalen Raumzone: Teardown-Sicherheit (F3/F6) greift nur bei Delete, nicht beim strukturellen Reconfigure; measured-vs-estimated: fremdes Gerät regelt weiter gegen einen als 'measured' deklarierten, tatsächlich toten Feed
- **Codebeleg:** config_flow.py:789-791: `return self.async_update_reload_and_abort(entry, unique_id=self.unique_id, data=new_data, options=new_options)`

**Befund:** Dimension: docs-vs-code. Im Betrieb flippt der Coordinator die TRV-Sensorquelle aktiv auf 'external' und füttert die Raumtemperatur (coordinator.py:1900-1910). Der Rück-Flip auf 'internal' plus Aktor-Parken läuft ausschließlich in async_remove_entry/_remove_room_entry (__init__.py:254-299, _restore_trv_internal :334-361) — mit der Begründung F6: 'so a deleted zone no longer regulates against a frozen external feed'. Der Reconfigure-Pfad tauscht den Aktor per unique_id-Wechsel (config_flow.py:779-791) und macht KEINERLEI Cleanup am Altaktor: async_unload_entry (Raum-Zweig) persistiert nur. Der alte TRV behält 'external' als Quelle und den letzten gefütterten Messwert — derselbe Gefahrenzustand, den F6 für Delete explizit schließt. README:80 dokumentiert den Restore nur für Deletion.

**Mögliches Fehlverhalten im Realbetrieb:** Der ausgetauschte TRV regelt autonom gegen einen eingefrorenen externen Messwert: friert der Feed z.B. bei 18 °C ein, heizt der TRV mit letztem Poise-Setpoint dauerhaft voll nach (reale Raumtemperatur deutlich über Ziel), alternativ dauerhaft falscher Komfortzustand. Betroffen bei Hardware-Tausch/Umverdrahtung einer Zone.

**Minimaler Reproduktionsfall / Testidee:** 1) Zone mit Sonoff-TRVZB-artigem TRV, Poise setzt Select auf 'external' und schreibt die externe Temperatur. 2) Reconfigure: Actuator auf ein anderes climate-Entity ändern. 3) Entry reload — alter TRV: Sensorquelle bleibt 'external', letzter Feed friert ein; kein Park, kein Restore.

**Zur Absicherung nötig:** Verhalten des konkreten TRV bei stale external feed (manche Firmware fällt selbst auf intern zurück — beim TRVZB nicht dokumentiert). Fix: beim Reconfigure mit Aktor-Wechsel den Delete-Cleanup (_execute_park + _restore_trv_internal) für den ALTEN Aktor ausführen.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.86): Widerlegung fehlgeschlagen; Finding nach Code-Lektüre bestätigt. Belege: (1) HA-Annahme korrekt: async_update_reload_and_abort (config_flow.py:789-791) löst nur Unload+Setup aus; async_remove_entry läuft in HA-Core ausschließlich beim Entry-Delete — das Repo bestätigt das selbst (__init__.py:42-44 "a reconfigure changes entry.data and reloads the entry"). (2) _execute_park/_restore_trv_internal werden nur aus _remove_room_entry aufgerufen (__init__.py:288-289), erreichbar allein über async_remove_entry (:217-223). […]
- **bestätigt** (Konfidenz 0.85): Bestätigt nach aktiven Widerlegungsversuchen. (1) Reconfigure erlaubt Aktor-Wechsel: config_flow.py:182 (CONF_ACTUATOR im Schema), :777-785 re-validiert explizit einen geänderten Aktor, :789-791 endet in async_update_reload_and_abort — Zitat des Findings korrekt. (2) Kein Cleanup im Reload-Pfad: async_unload_entry Raum-Zweig (__init__.py:208-214) ruft nur async_persist_and_cleanup (coordinator.py:1051-1070 = Save + Issue-/Notification-Cleanup, kein Aktor-I/O). […]

---

### AR-13 · mittel · begründeter Verdacht

**Raum-Remove-Park entscheidet heats_for_zone anhand des stale Config-climate_mode statt des store-eigenen Live-Modus — dritte Stelle der doppelten Ownership, im Delete-Pfad**

- **Fundstelle:** `custom_components/poise/__init__.py:284` — `_remove_room_entry`
- **Schadensklasse:** ungewolltes Heizen
- **Codebeleg:** heats_for_zone="heat" in modes
    and str(cfg.get(CONF_CLIMATE_MODE, "auto")) != "cool_only",

**Befund:** Der live wirksame climate_mode ist Store-Eigentum, nicht Options-Eigentum: climate.py:259 ruft coordinator.set_climate_mode() (coordinator.py:461-463, setzt _dirty), der Wert wird im Store persistiert (coordinator.py:1023 '"climate_mode": self._climate_mode') und beim Bootstrap restauriert (coordinator.py:559-561). entry.options/entry.data werden dabei nie aktualisiert. _remove_room_entry liest aber ausschließlich cfg = {**entry.data, **entry.options} (__init__.py:268) und trifft damit die Park-Entscheidung (heat@setback vs. off) auf dem stale Formularwert. Besonders bitter: derselbe Codeblock lädt den PoiseStore drei Zeilen später zum Löschen (__init__.py:294-295) — die Wahrheit wäre verfügbar, wird aber ungelesen weggeworfen. Das überlebende Clobber-Finding betrifft nur async_apply_options; diese Delete-Pfad-Stelle ist davon nicht abgedeckt.

**Mögliches Fehlverhalten im Realbetrieb:** Nutzer stellt eine reversible Klimaanlage live per Klima-Entität auf cool_only (soll nie heizen) und löscht später den Entry: die Config sagt noch 'auto', heats_for_zone wird True, resolve_park_command parkt das Gerät dauerhaft in 'heat' auf comfort_base-setback_delta — unbeaufsichtigtes Heizen nach der Deinstallation, genau das, was der Park-Docstring ('a cool-only ... device with no heating duty -> off') verhindern will. Umgekehrt (Options sagen cool_only, live heat_only) wird ein heizverantwortliches Gerät auf 'off' geparkt.

**Minimaler Reproduktionsfall / Testidee:** 1) Raum-Entry mit reversiblem climate-Aktuator anlegen (climate_mode in Options = 'auto'). 2) In der Poise-Klima-Entität HVACMode.COOL wählen -> set_climate_mode('cool_only') landet nur im Store. 3) Entry löschen. 4) Beobachten: set_hvac_mode('heat') + set_temperature(setback) statt 'off'.

**Zur Absicherung nötig:** Keiner — die Ownership-Kette (climate.py:259 -> coordinator.py:461-463 -> Store 1023/559-561, Options unberührt) ist vollständig im Code belegt; nur die Schadenshöhe hängt davon ab, ob der Nutzer den Modus live divergieren ließ.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Aktiver Widerlegungsversuch gescheitert — alle Glieder der Kette stimmen. (1) Live-Modus ist Store-Eigentum: climate.py:254-259 ruft coordinator.set_climate_mode(climate_mode_for_hvac(...)); hvac_modes.py:51 mappt "cool"->"cool_only"; coordinator.py:461-463 setzt _climate_mode+_dirty; _save_payload persistiert "climate_mode" (coordinator.py:1023) via _maybe_save (1026-1032) und final beim Unload via async_persist_and_cleanup (1051-1054, __init__.py:213) — da HA vor async_remove_entry immer unloaded, steht der Live-Modus beim Delete garantiert i […]

---

### AR-14 · mittel · fehlender Kontext

**Hub-Variante des Zombie-Findings ungedeckt: der aktorisch wirksame Tick-Timer wird VOR dem Plattform-Forwarding registriert — wirft das Forwarding, kann ein SETUP_ERROR-Hub den Boiler dauerhaft weiterschalten**

- **Fundstelle:** `custom_components/poise/__init__.py:97` — `async_setup_entry`
- **Schadensklasse:** ungewolltes Heizen
- **Codebeleg:** entry.async_on_unload(
    async_track_time_interval(
        hass, _hub_tick, timedelta(seconds=TICK_INTERVAL_S)
    )
)
await hass.config_entries.async_forward_entry_setups(
    entry, [Platform.BINARY_SENSOR]
)

**Befund:** __init__.py:97-101 registriert den unabhängigen Tick-Timer per entry.async_on_unload, erst danach (Zeile 102-104) läuft das BINARY_SENSOR-Forwarding. Wirft das Forwarding unerwartet (Plattform-Importfehler, Registry-Fehler), endet der Entry in SETUP_ERROR; on_unload-Callbacks werden von HA-Core bei einer Setup-Exception (HA-versionsabhängig) nicht abgearbeitet — async_unload_entry läuft für einen nie geladenen Entry ebenfalls nicht. Der Timer feuert dann weiter _hub_tick -> hub.async_refresh() -> _async_update_data -> self._actuate (hub_coordinator.py:361-362) und schaltet den Boiler real, obwohl die UI den Hub als fehlgeschlagen zeigt. Das überlebende Zombie-Finding ('State-Listener, Stop-Flush und Update-Listener werden vor dem Plattform-Forwarding registriert') benennt ausschließlich die Raum-Registrierungen (Zeilen 129-141); die Hub-Seite ist schärfer, weil hier nicht nur Listener, sondern der einzige aktorische Treiber des Boilers (F2-Timer) verwaist — und weder Unload-OFF-Handover (Zeile 197-202) noch cleanup_issues je erreichbar sind.

**Mögliches Fehlverhalten im Realbetrieb:** Nach einem einmaligen Forwarding-Fehler beim Hub-Setup existiert ein unsichtbarer, nicht entladbarer Boiler-Schreiber: Keepalive/ON/OFF laufen im 60-s-Takt weiter, bis HA neu gestartet wird. Ein 'defekter' Hub, den der Nutzer für tot hält, heizt den Boiler weiter oder hält ihn per Keepalive an.

**Minimaler Reproduktionsfall / Testidee:** Hub-Entry mit ON/OFF-Actions anlegen; async_forward_entry_setups für BINARY_SENSOR eine Exception werfen lassen (z. B. Monkeypatch der Plattform). Entry-Status SETUP_ERROR prüfen, dann TICK_INTERVAL_S abwarten und beobachten, dass die Boiler-Service-Calls weiter abgesetzt werden.

**Zur Absicherung nötig:** HA-Core-Verhalten der Ziel-Version: ob ConfigEntry._async_process_on_unload bei einer Exception in async_setup_entry (Status SETUP_ERROR) die on_unload-Callbacks abräumt. In den gängigen Core-Versionen laufen sie nur beim regulären Unload — das würde das Finding bestätigen.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85): Bestätigt für HA 2025.1–2025.12 (das deklarierte Support-Fenster, hacs.json: "2025.1.0"); ab HA 2026.1 durch Core-Fix entschärft. Kette verifiziert: (1) __init__.py:97-101 registriert den Tick-Timer per entry.async_on_unload VOR dem BINARY_SENSOR-Forwarding (102-104); (2) in den Core-Tags 2025.1.0/2025.6.0/2025.10.0/2025.12.0 ruft der generische except-Zweig (asyncio.CancelledError, SystemExit, Exception) in ConfigEntry.__async_setup_with_context KEIN _async_process_on_unload auf — nur ConfigEntryError/AuthFailed/NotReady tun das; erst 2026.1.0 […]

---

### AR-15 · mittel *(Erst-Einstufung: hoch)* · begründeter Verdacht

**_remove_hub_entry feuert Boiler-OFF rein verdrahtungsbasiert — Kommentar 'only switch a boiler Poise actually commanded' ist eine Fehlbehauptung (verdrahtet != kommandiert)**

- **Fundstelle:** `custom_components/poise/__init__.py:242` — `_remove_hub_entry`
- **Schadensklasse:** Frost-/Mould-Schutz versagt
- **Verletzte Projektgrenze:** diagnostic-only vs live + System-Hub-Grenze: Remove aktuiert ein Fremdsystem-Gerät ohne Nachweis, dass Poise im aktuellen Kontroll-Epoch je kommandiert hat; Kommentar behauptet ein Gate, das der Code nicht hat
- **Codebeleg:** __init__.py:240-242: `# F12: only switch a boiler Poise actually commanded (BOTH actions wired) — a shadow-only hub must never turn off a boiler a foreign automation runs.\nif on is not None and off is not None:` — vgl. Unload-Gate __init__.py:197-201 resolve_hub_unload_off(was_actuating=hub.actuation_active, ...)

**Befund:** Dimension: remove. Der Unload-Pfad kapselt die Entscheidung in resolve_hub_unload_off ('fire OFF only at a genuine relinquish', lifecycle.py:101-111); der Remove-Pfad prüft nur, ob beide Actions in entry.data parsen. 'Wired' heißt nicht 'commanded': (a) Delete eines DEAKTIVIERTEN Hubs — beim Disable wurde der OFF bereits als Hand-over gefeuert; in der Zwischenzeit kann der Nutzer/eine fremde Automation den Boiler manuell AN geschaltet haben; das spätere Aufräum-Löschen des disabled Entries feuert einen zweiten OFF lange nach dem Relinquish. (b) Delete eines nie erfolgreich geladenen Hubs (Setup-Retry) — Poise hat nie aktuiert, feuert aber OFF. Der Kommentar setzt 'actually commanded' mit 'BOTH actions wired' gleich — genau die Gleichsetzung, die der F12-Fix für den Unload-Pfad vermeiden sollte. Hintergrund: der Remove-Pfad KANN hub.actuation_active nicht abfragen, weil HA runtime_data nach erfolgreichem Unload löscht — die Duplikation ist notwendig, aber das Gate fehlt ersatzlos statt persistent abgebildet zu werden.

**Mögliches Fehlverhalten im Realbetrieb:** Ausschalten eines Boilers mitten im Winter, den ein anderer Controller/der Nutzer bewusst AN hat — bei manuellem Boiler-Betrieb ohne Re-Assert bleibt die Heizung aus (Auskühlung/Frost). Der Schaden ist einmalig, aber unsichtbar (kein Hinweis in der UI, nur ein blocking Call im Hintergrund des Delete-Dialogs).

**Minimaler Reproduktionsfall / Testidee:** Hub mit ON+OFF-Actions einrichten, Entry deaktivieren (OFF feuert korrekt beim Disable, test_hub_disable_fires_off_and_clears_issue belegt das). Danach Boiler manuell einschalten. Wochen später den deaktivierten Poise-Hub-Entry löschen → _remove_hub_entry feuert erneut OFF (on/off parsen weiterhin aus entry.data).

**Zur Absicherung nötig:** Designentscheid: Soll Delete eines bereits relinquishten (disabled/nie geladenen) Hubs nochmals OFF feuern? Falls nein, müsste ein 'Poise hat aktuiert'-Marker persistiert werden (entry.data-Flag beim ersten ON oder hass.data), da runtime_data beim Remove weg ist.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.82) (Schweregrad korrigiert → mittel): KERN BESTÄTIGT, RHETORIK TEILS FALSCH, SEVERITY GESENKT. (1) Bestätigt: _remove_hub_entry (__init__.py:238-247) gated den Boiler-OFF nur mit `if on is not None and off is not None` — kein entry.disabled_by-Check, kein Relinquish-Nachweis. Disable feuert den OFF bereits über das Unload-Gate (__init__.py:197-202, disabled=entry.disabled_by is not None; Test tests/integration/test_lifecycle_review.py:180 `assert len(turn_off)==1`). […]
- **bestätigt** (Konfidenz 0.78) (Schweregrad korrigiert → mittel): Kernverhalten bestätigt, zentrale Rationale teilweise widerlegt, Severity herabgestuft. BESTÄTIGT: Zitat/Zeile exakt (custom_components/poise/__init__.py:238-242 — on/off parsen rein aus entry.data, Gate ist nur `if on is not None and off is not None:`; kein Check auf entry.disabled_by oder Ladezustand im gesamten _remove_hub_entry, Z.226-251). […]

---

### AR-16 · mittel · begründeter Verdacht

**Frischer V2-Entry: Required-Options-Felder ohne Default (optimal_start, comfort_weight, climate_mode) — erster Options-Save flippt Coordinator-Defaults still (optimal_start True→False, comfort_weight 70→0)**

- **Fundstelle:** `custom_components/poise/config_flow.py:482` — `_options_schema / PoiseOptionsFlow.async_step_init`
- **Schadensklasse:** falscher Komfortzustand
- **Verletzte Projektgrenze:** options vs data: der Setup-Flow legt Tuning-Keys in data an, die restlichen Tuning-Defaults existieren nur implizit im Coordinator — der Options-Flow kennt sie nicht
- **Codebeleg:** config_flow.py:482: `vol.Required(CONF_OPTIMAL_START): selector.BooleanSelector()` — ebenso CONF_CLIMATE_MODE (Z.449), CONF_COMFORT_WEIGHT (Z.456, Slider min=0), CONF_SETBACK_DELTA (Z.473): vol.Required OHNE Default

**Befund:** Dimension: migration. Der Setup-Flow schreibt nur name/temp_sensor/actuator + accuracy-Sektion in data (config_flow.py:271-319, async_step_room:705-727). Ein frischer V2-Entry hat weder in data noch in options: climate_mode, comfort_weight, setback_delta, optimal_start. nest_by_section lässt fehlende Felder explizit weg, 'damit der Schema-Default greift' (config_sections.py:44-52) — aber die genannten Options-Schema-Felder sind vol.Required OHNE Default. Ein Required-Toggle ohne suggested value rendert AUS, ein Required-Slider ohne Wert rendert am Minimum (0). Die Coordinator-Defaults sind aber optimal_start=True (coordinator.py:424) und comfort_weight=70 (const.py:68). Der erste Options-Save eines frischen Entries schreibt daher optimal_start=False und comfort_weight=0 — divergent zu den bis dahin wirksamen Defaults. Kontrast: adaptive_cool (Z.491) und dynamics (Z.592) haben korrekt Schema-Defaults.

**Mögliches Fehlverhalten im Realbetrieb:** Nutzer öffnet den Options-Flow nur, um z.B. den Energiepreis einzutragen, und speichert. Ab da: Optimal-Start/-Stop deaktiviert (kein Vorheizen zum Komfortfenster, kein Coasting) und Komfortgewicht 0 statt 70 (Priorität 0.0, coordinator.py:629-631) — spürbar falsches Komfortverhalten ohne jede Fehlermeldung; der Nutzer hat diese Felder nie bewusst angefasst.

**Minimaler Reproduktionsfall / Testidee:** 1) Neuen Raum-Entry über async_step_room anlegen. 2) Options-Flow öffnen: schedule-Sektion zeigt optimal_start-Toggle AUS, comfort-Sektion den comfort_weight-Slider bei 0. 3) Speichern. 4) async_apply_options: _optimal_start=False (coordinator.py:641), _priority=0.0 (629-631).

**Zur Absicherung nötig:** Frontend-Rendering von vol.Required-Feldern ohne Default und ohne suggested value (Toggle=aus ist sicher; Slider=min sehr wahrscheinlich; Required-NumberBox setback_delta blockiert vermutlich den Submit). Fix-Richtung: DEFAULT_COMFORT_WEIGHT/True/'auto' als Schema-Defaults der Options-Felder setzen — analog zu adaptive_cool und dynamics.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9): BESTÄTIGT nach aktivem Widerlegungsversuch — der Kernmechanismus ist end-to-end gegen echten HA-Quellcode belegt, nicht nur plausibel. Repo-Seite: Frischer Entry entsteht mit VERSION=2 (config_flow.py:683, Migration läuft nie); _setup_schema (config_flow.py:271-319) + async_step_room (705-727) schreiben nur name/temp_sensor/actuator + accuracy (comfort_base=21, category="II" via Optional-Defaults) in data; options={}. […]
- **bestätigt** (Konfidenz 0.85): BESTÄTIGT nach aktivem Widerlegungsversuch — kein Guard gefunden, der den Pfad verhindert.

Verifizierte Kette:
1) Frischer V2-Entry hat die vier Keys nirgends: _setup_schema (config_flow.py:271-319) schreibt nur name/temp_sensor/actuator + accuracy-Sektion (comfort_base/category via Optional-Defaults); async_step_room (700-727) legt alles in data ab, options bleibt leer. […]

---

### AR-17 · mittel · sicherer Fehler

**_execute_park: blocking=False macht Ausführungsfehler des finalen, nie wiederholten Kommandos unsichtbar (Widerspruch zu F27) und racet set_temperature gegen set_hvac_mode**

- **Fundstelle:** `custom_components/poise/__init__.py:317` — `_execute_park`
- **Schadensklasse:** falscher Komfortzustand
- **Verletzte Projektgrenze:** Widerspruch zur eigenen F27-Regel im Hub-Pfad (blocking=True bei Teardown-Writes); 'best-effort'-Kommentar suggeriert beobachtetes Logging, das für Ausführungsfehler nicht existiert
- **Codebeleg:** __init__.py:308-331: `await hass.services.async_call("climate", "set_hvac_mode", {...}, blocking=False)` ... `await hass.services.async_call("climate", "set_temperature", {...}, blocking=False)` ... `except Exception:  # noqa: BLE001 - park on delete is best-effort`

**Befund:** Dimension: remove. Mit blocking=False laufen synchron nur Service-Lookup (ServiceNotFound) und Schema-Validierung; die eigentliche Ausführung (Entity unavailable, ServiceValidationError aus min/max-Check, Geräte-I/O-Fehler) läuft in einem create_task und wird von HA generisch weggeloggt — das except am Ende fängt sie nie. Im Hub-Pfad wird für exakt dieselbe Teardown-Situation blocking=True mit der Begründung 'so an execution error is observed not swallowed (F27)' benutzt (__init__.py:228-229, 244-246). Der Raum-Park ist der schärfere Fall: der LETZTE Write ohne Retry-Tick (im Laufbetrieb ist blocking=False ok, weil der nächste Tick nachzieht — hier zieht nichts nach). Zusätzlich werden set_hvac_mode und set_temperature als zwei unabhängige Tasks gequeued; HA serialisiert Entity-Service-Calls pro Entity nicht — set_temperature kann das Gerät erreichen, während der Modewechsel noch in-flight ist; Integrationen, die den Setpoint an den aktiven Modus binden, verlieren den Setback-Setpoint.

**Mögliches Fehlverhalten im Realbetrieb:** Ein fehlgeschlagener Park (Setpoint verworfen, Mode nicht übernommen) ist final und für den Nutzer unsichtbar — Endzustand des Geräts undefiniert (alter Setpoint in heat, oder Mode/Setpoint inkonsistent), ohne dass das Poise-Log darauf hinweist.

**Minimaler Reproduktionsfall / Testidee:** Raum-Entry mit trägem TRV (Z2M mit langsamer Bestätigung) löschen; set_temperature-Task startet vor Abschluss des set_hvac_mode-Roundtrips. Alternativ Ausführungsfehler provozieren (Entity unavailable) — das 'Poise: actuator park on removal failed'-Log erscheint nie, nur HAs generisches Task-Log.

**Zur Absicherung nötig:** blocking=True (plus asyncio.timeout wie im Hub-_call) für beide Calls; set_temperature erst nach Rückkehr von set_hvac_mode absenden.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): Kernmechanismus am HA-Core-Quelltext bestätigt: Bei blocking=False startet ServiceRegistry.async_call die Ausführung als Hintergrund-Task (core.py:2311-2317) und _run_service_call_catch_exceptions verschluckt jede Ausführungs-Exception mit generischem Log "Error executing service" (core.py:2344-2345); synchron zum Aufrufer gelangen nur ServiceNotFound (core.py:2263) und Schema-vol.Invalid (core.py:2282-2292). […]
- **bestätigt** (Konfidenz 0.85): BESTÄTIGT nach Quellenprüfung von Repo UND Home-Assistant-Core. (1) Code-Zitat/Zeile stimmen: /home/user/poise-thermostat/custom_components/poise/__init__.py:308-331 — try-Block mit drei async_call(..., blocking=False) (Z. 314, 321, 328) und `except Exception: ... "Poise: actuator park on removal failed"` (Z. 330-331). […]

---

### AR-18 · mittel · sicherer Fehler

**_restore_trv_internal flippt JEDES Select mit 'internal'-Option — breiter als der eigene Klassifikator is_external_sensor_select und ohne Idempotenz-/Ownership-Check**

- **Fundstelle:** `custom_components/poise/__init__.py:351` — `_restore_trv_internal`
- **Schadensklasse:** falscher Komfortzustand
- **Verletzte Projektgrenze:** Schreibt Gerätezustand, den Poise nie besessen hat (wired != commanded auf Select-Ebene); ignoriert die eigene Klassifikator-Grenze in devices/model_fixes.py
- **Codebeleg:** __init__.py:351-357: `if "internal" in options:\n    await hass.services.async_call("select", "select_option", {..., "option": "internal"}, blocking=False)` — Kontrast devices/model_fixes.py:63: `return "external" in opts and "internal" in opts`

**Befund:** Dimension: remove. Der Laufzeitpfad identifiziert das Sensor-Source-Select streng über is_external_sensor_select (Optionen müssen 'internal' UND 'external' enthalten, model_fixes.py:55-63, benutzt in coordinator.py:711-716) und schreibt nur, wenn der State nicht schon 'external' ist (coordinator.py:1900-1912). Der Remove-Pfad benutzt diese Klassifikation nicht: er iteriert ALLE Selects des Geräts und feuert auf jedes, dessen Optionsliste irgendein 'internal' enthält — auch ein Select, das der Coordinator nie als Sensor-Source klassifiziert hätte. Außerdem ohne Idempotenz-Check (schreibt auch, wenn schon 'internal' steht) und ohne Ownership-Check: auch wenn Poise das Select nie auf 'external' gestellt hat (CONF_TRV_EXTERNAL_TEMP nicht konfiguriert → der Runtime-Switch lief nie), wird beim Löschen 'internal' erzwungen und überschreibt eine bewusste Nutzer-/Fremdautomations-Einstellung.

**Mögliches Fehlverhalten im Realbetrieb:** Falsches Select am Gerät kann beliebige Geräteeinstellungen verstellen; ein vom Nutzer extern verdrahtetes Sensor-Setup (ohne Poise-Feed) wird beim Löschen zurück auf internal gezwungen → Gerät regelt danach auf dem (oft schlechteren) internen Fühler; unnötige Zigbee-Writes an Batteriegeräte bei bereits korrektem Zustand.

**Minimaler Reproduktionsfall / Testidee:** TRV-Gerät mit zwei Selects: select.trv_sensor (['internal','external'], vom Nutzer via eigener Automation auf 'external') und einem weiteren Select mit 'internal' in den Optionen. Raum-Entry OHNE CONF_TRV_EXTERNAL_TEMP löschen → beide Selects werden auf 'internal' geschrieben, obwohl Poise keines je angefasst hat.

**Zur Absicherung nötig:** is_external_sensor_select wiederverwenden, nur schreiben wenn state=='external', und idealerweise nur, wenn der Coordinator das Select je auf 'external' geschaltet hat (Marker in Store/entry).

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9) (Schweregrad korrigiert → niedrig): Alle drei Kernbehauptungen am Code belegt, keine falsche HA-Annahme gefunden. (1) Über-breites Matching: __init__.py:351 prüft nur `if "internal" in options:` und feuert in der Schleife (Z.346-357) auf JEDES Select des Geräts; der eigene Klassifikator devices/model_fixes.py:63 verlangt `"external" in opts and "internal" in opts`, und der Coordinator (coordinator.py:711-716) nutzt ihn strikt und wählt nur das erste Match. […]
- **bestätigt** (Konfidenz 0.85): Bestätigt nach Code-Lektüre. (1) Zitat korrekt: __init__.py:346-357 iteriert alle Selects des Geräts und feuert bei `if "internal" in options:` select_option='internal' — ohne is_external_sensor_select (model_fixes.py:63 verlangt 'external' UND 'internal'; per Grep nur in coordinator.py:713 benutzt, nicht im Remove-Pfad). (2) Kein Idempotenz-Check: Kontrast coordinator.py:1902 (`sel.state not in ("external", "unavailable")`); der Remove-Pfad schreibt auch bei bereits 'internal'. […]

---

### AR-19 · mittel · Testlücke

**Testlücke Migration: version>2-Refusal (MIGRATION_ERROR), V1-Hub-Entry end-to-end, Idempotenz, options-gewinnt-Konflikt e2e, occupancy-String in data und Reconfigure-Roundtrip nach Migration sind nirgends abgedeckt**

- **Fundstelle:** `custom_components/poise/__init__.py:158` — `async_migrate_entry / tests/test_migration.py / tests/integration/test_migration_glue.py`
- **Schadensklasse:** falscher Komfortzustand
- **Verletzte Projektgrenze:** options vs data: genau die Eigentumsgrenze, die die Migration zieht, ist für den Hub-Entry und den Refusal-Fall nur per Docstring/pure-Funktion behauptet, nie über den echten HA-Migrationspfad belegt
- **Codebeleg:** __init__.py:158-159: `if entry.version > 2:\n        return False` — grep über tests/ nach 'MIGRATION_ERROR|version=3|version > 2' liefert null Treffer

**Befund:** Unabhängig gefunden von 2 Reviewern (Dimensionen: migration, test-gap). Vorhanden: Unit-Tests für Split, options-gewinnt (nur der Gewinner asserted, tests/test_migration.py:37-41), Multi-Entity-Normalisierung, System-pass-through (nur pure function, Z.62-66), structural-data-owned (F20), as_entity_list; ein Glue-Test für genau EINEN V1-Raum-Entry (test_migration_glue.py:82-110, dort real gut abgedeckt). NICHT getestet: (1) Downgrade-Refusal __init__.py:158-159 — der Docstring ('A future (>2) schema is refused, not downgraded') ist reine Behauptung ohne Testbeleg. (2) V1-HUB-Entry durch die Glue-Schicht: dass async_migrate_entry für einen Hub nur die Version bumpt, entry.data byte-identisch lässt UND der Hub danach lädt. (3) Migrations-Idempotenz migrate_room_entry(migrate_room_entry(...)) — relevant wegen des fehlenden version==1-Guards (siehe minor_version-Finding). (4) options-gewinnt-Konflikt end-to-end. (5) V1-Entry mit CONF_OCCUPANCY_SENSOR als String in DATA (Unit-Test legt ihn nur in options, tests/test_migration.py:46-49). (6) Reconfigure-Roundtrip NACH Migration, insbesondere Löschen von anlagen-Feldern (würde das _STRUCTURAL_CARRY-Resurrect-Finding fangen). Nebenbefund ohne Widerspruch: der Coordinator liest alle drei Multi-Entity-Keys einheitlich über as_entity_list (coordinator.py:339-343, 353, 608-609).

**Mögliches Fehlverhalten im Realbetrieb:** Regressiert der Refusal-Zweig (z.B. 'vereinfacht' zu `if entry.version >= 2: return True`), würde ein Downgrade-Szenario (HA-Backup mit V3-Entry, ältere Poise-Version) die V3-Daten durch den V2-Splitter jagen: der Entry lädt mit Defaults oder falscher Sensor-Verdrahtung statt sauber mit MIGRATION_ERROR zu stoppen. Ein regressierter Hub-Pfad (Split fälschlich auch für system-Entries) würde Boiler-Actions aus data reißen und den Hub stumm auf shadow-only degradieren.

**Minimaler Reproduktionsfall / Testidee:**

```python
# tests/integration/test_migration_glue.py — zwei Ergänzungen
from homeassistant.config_entries import ConfigEntryState
from custom_components.poise.const import (
    CONF_BOILER_COUNT_THRESHOLD, CONF_BOILER_OFF_ACTION, CONF_BOILER_ON_ACTION,
    CONF_ENTRY_TYPE, ENTRY_TYPE_SYSTEM,
)

async def test_future_schema_is_refused_not_downgraded(hass: HomeAssistant) -> None:
    snapshot = _v1_data()
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.ac", data=snapshot, version=3, title="Future"
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert entry.version == 3          # kein Downgrade
    assert dict(entry.data) == snapshot  # Daten unangetastet

async def test_v1_hub_entry_bumps_version_content_untouched(hass: HomeAssistant) -> None:
    data = {
        CONF_ENTRY_TYPE: ENTRY_TYPE_SYSTEM,
        CONF_BOILER_COUNT_THRESHOLD: 1,
        CONF_BOILER_ON_ACTION: "switch.boiler/switch.turn_on",
        CONF_BOILER_OFF_ACTION: "switch.boiler/switch.turn_off",
    }
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    hub = MockConfigEntry(
        domain=DOMAIN, unique_id="poise_system", data=dict(data), version=1,
        title="Poise System",
    )
    hub.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub.entry_id)
    await hass.async_block_till_done()
    assert hub.version == 2
    assert dict(hub.data) == data      # Hub-pass-through: Boiler-Actions bleiben in data
    assert dict(hub.options) == {}
    assert hub.runtime_data.actuation_active  # Hub aktuiert nach Migration weiter

# Weitere Ergänzungen: (b) Unit-Test assert migrate_room_entry(*migrate_room_entry(d, o)) == migrate_room_entry(d, o);
# (c) Glue-Test V1-data mit occupancy_sensor='binary_sensor.pir' → assert entry.options[occupancy_sensor]==['binary_sensor.pir'].
```

**Zur Absicherung nötig:** Keiner — MockConfigEntry akzeptiert version=, HA setzt bei return False den Zustand MIGRATION_ERROR.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): Kern bestätigt, Umfang und Impact deutlich übertrieben. BESTÄTIGT: (1) Der Refusal-Zweig __init__.py:158-159 ('if entry.version > 2: return False') ist testfrei — Grep über tests/ nach 'MIGRATION_ERROR|version=3|version > 2' liefert null Treffer; einziges explizites version= in allen Tests ist test_migration_glue.py:92 (version=1). […]
- **bestätigt** (Konfidenz 0.85): KERN BESTÄTIGT, BÜNDEL TEILWEISE ÜBERZEICHNET. (A) Refusal-Gap bestätigt: __init__.py:158-159 enthält exakt `if entry.version > 2: return False`; Grep über tests/ nach MIGRATION_ERROR|version=3|version > 2 liefert null Treffer (einziger version=-Treffer: test_migration_glue.py:92, version=1). Entscheidend: Der Guard ist auf ALLEN unterstützten HA-Releases load-bearing — HA 2025.1 (CI: requirements-test.txt:9 pinnt pytest-homeassistant-custom-component==0.13.195, "verified against our 2025.1 APIs"; hacs.json-Floor 2025.1.0) bis 2026.1 haben KEIN […]

---

### AR-20 · mittel *(Erst-Einstufung: hoch)* · begründeter Verdacht

**async_bootstrap: Catch-all über dem Store-Load macht aus jedem transienten I/O-Fehler ein 'starting fresh' — gelerntes Modell wird vom periodischen Save überschrieben; Teil-Restore kann enabled=False/override verlieren**

- **Fundstelle:** `custom_components/poise/coordinator.py:564` — `PoiseCoordinator.async_bootstrap`
- **Schadensklasse:** verlorenes Lernmodell
- **Verletzte Projektgrenze:** safety vs comfort / Persistenzgrenze: 'korrupt → fresh' (richtig) und 'transient → retry' (fehlt) werden in einem Catch-all zusammengeworfen; Restore von Nutzer-Intent und Modell teilen sich einen Fehlerdomänen-Block
- **Codebeleg:** coordinator.py:564-565: `except Exception:  # noqa: BLE001 - corrupt state must not block setup\n    _LOGGER.exception("Poise: failed to restore learned model; starting fresh")`

**Befund:** Dimension: room-setup. Der try-Block Z.517-561 umfasst sowohl `await self._store.load()` als auch alle from_dict-Restores UND die Wiederherstellung des Nutzer-Intents (Z.543-561: window_bypass, preset, enabled, override, override_set_wall, climate_mode). Der Kommentar behauptet 'corrupt state must not block setup' — der Code fängt aber genauso transiente Fehler (OSError/HomeAssistantError aus Store.async_load, z.B. Disk kurz read-only, NFS-Hänger). Statt ConfigEntryNotReady (Retry, Modell bleibt auf Platte erhalten) startet die Zone 'fresh'; spätestens _maybe_save nach 30 Ticks (Z.1026-1032) bzw. der Stop-Flush überschreibt die intakte Store-Datei mit dem leeren Modell — irreversibler Verlust. Zweiter Effekt: schlägt ein SPÄTER from_dict im selben try fehl (z.B. korruptes 'multi_lifecycle'-Subdict, Z.530), bricht der Block ab, BEVOR Z.548 `self._enabled = bool(data.get("enabled", True))` läuft — der Konstruktor-Default self._enabled=True (Z.313) bleibt stehen.

**Mögliches Fehlverhalten im Realbetrieb:** (a) Verlorenes Lernmodell (EKF, trm, seasonless, outcome_stats …) bei einem einzigen transienten Load-Fehler beim HA-Start — genau der Zustand, den F7/ADR-0007 schützen soll. (b) Eine per HVAC=off ausgeschaltete Zone (enabled=False persistiert, Z.1020) kommt nach einem teilkorrupten Store-Restore ENABLED zurück und heizt/kühlt wieder — ungewollte Aktorik als Sekundärschaden.

**Minimaler Reproduktionsfall / Testidee:** (a) HA stoppen, .storage/poise_<entry_id>_ekf auf chmod 000 setzen, HA starten → Log 'failed to restore learned model; starting fresh'; Rechte wiederherstellen; ≤30 min später überschreibt _maybe_save die Datei mit dem frischen Modell. (b) Zone per HVAC off ausschalten, HA stoppen, im Store nur das 'multi_lifecycle'-Dict durch nicht parsebaren Inhalt ersetzen (falsche Typen, sodass _lifecycle.from_dict wirft), HA starten → ekf wird restauriert, ab Z.530 Exception → enabled bleibt True → Zone regelt wieder.

**Zur Absicherung nötig:** Exakte Fehlerklassen von homeassistant.helpers.storage.Store.async_load in der Ziel-HA-Version (JSONDecodeError wird in HomeAssistantError gewrappt; OSError-Verhalten) — ändert nur, WELCHE transienten Fehler betroffen sind, nicht den Mechanismus.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → mittel): Mechanismus vollständig bestätigt, Severity auf mittel herabgestuft. (1) HA-Annahme korrekt (verifiziert am HA-Core 2025.1.0, der in hacs.json gepinnten Version): util/json.py::load_json wrappt OSError in HomeAssistantError; helpers/storage.py::_async_load_data behandelt nur JSONDecodeError-verursachte Fehler selbst (Umbenennung nach .corrupt.<ts> + return None) und re-raised alles andere ("raise"). […]
- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → mittel): Widerlegung versucht, gescheitert — beide Mechanismen sind auf Code-Ebene nachweisbar. (1) Zitat exakt: coordinator.py:564-565; try-Block Z.516-563 umfasst store.load() (Z.517), alle from_dict-Restores UND Nutzer-Intent (Z.543-561, enabled auf Z.548). (2) Transient→fresh bestätigt gegen HA 2025.1.4-Quelltext (Ziel-Version per requirements-test.txt): util/json.py Z.80-82 wrappt OSError in HomeAssistantError; helpers/storage.py Z.334-386 behandelt NUR JSONDecodeError intern (.corrupt-Rename + Repair-Issue + return None) und re-raist alles andere  […]

---

### AR-21 · mittel · sicherer Fehler

**Kommentar '(no learning loss)' ist falsch: Save-Fehler beim Unload wird geschluckt, bis zu 30 Ticks Lernen still verloren und das persistence_failed-Issue direkt danach gelöscht**

- **Fundstelle:** `custom_components/poise/coordinator.py:1055` — `PoiseCoordinator.async_persist_and_cleanup`
- **Schadensklasse:** verlorenes Lernmodell
- **Verletzte Projektgrenze:** Kommentar vs. Code: '(no learning loss)' gilt nur im Erfolgszweig
- **Codebeleg:** coordinator.py:1053-1059: `except Exception:  # noqa: BLE001\n    _LOGGER.exception("Poise: final save on unload failed")\nfor issue_id in list(self._active_issues):\n    ir.async_delete_issue(self.hass, DOMAIN, issue_id)` — löscht auch persistence_failed_{entry_id} — __init__.py:212: '# final save + repair-issue/notification cleanup (no learning loss)'

**Befund:** Dimension: unload. Ein Save-Fehler (voller Datenträger, kaputter Store) wirft keine Exception aus async_unload_entry — er wird breit gefangen und nur geloggt. Positiv: kein FAILED_UNLOAD. Negativ: der Kommentar am Aufrufer (__init__.py:212) behauptet ein Verhalten, das der Fehlerzweig nicht hat — beim Reload lädt der neue Coordinator den letzten periodischen Stand, bis zu EKF_SAVE_EVERY_TICKS=30 Ticks (~30 min, const.py:129) Lernen plus pending User-Intent (Override/Preset/enabled, Teil von _save_payload Z.1018-1023) sind still weg. Verschärfend: die F24-Eskalation (_note_save_result, Z.1038-1049) wird nicht bedient, und die Schleife direkt nach dem Fehlschlag löscht ein ggf. bestehendes persistence_failed-Repair-Issue — der neue Coordinator startet mit _save_failures=0 und braucht erneut 5 Fehlschläge, bis der Nutzer wieder etwas sieht. Ergänzend: schlägt bereits async_unload_platforms fehl (unloaded=False), wird gar nicht persistiert; da HA bei result=False die on_unload-Callbacks nicht ausführt, bleibt immerhin der Stop-Flush-Listener aktiv.

**Mögliches Fehlverhalten im Realbetrieb:** Bei Store-Fehlern zum Unload-Zeitpunkt (Reload nach Reconfigure, Disable) geht bis zu ~30 min Lernfortschritt und gesetzter User-Intent verloren, ausschließlich mit einer Logzeile als Spur; das Warn-Issue wird sogar aktiv entfernt. Der Kommentar dokumentiert das Gegenteil.

**Minimaler Reproduktionsfall / Testidee:** Store-Pfad readonly machen / Datenträger füllen, Override setzen, Raum-Entry reloaden: 'Poise: final save on unload failed' im Log, Unload meldet True, neuer Coordinator startet mit altem Modellstand ohne Override; kein Repair-Issue sichtbar.

**Zur Absicherung nötig:** Entscheidung, ob der Fehlerzweig das persistence_failed-Issue stehen lassen bzw. neu setzen soll (bei Reload sinnvoll, bei Delete egal); Kommentar in __init__.py:212 korrigieren.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Alle Kernbehauptungen durch Code-Lektüre belegt, Widerlegungsversuche gescheitert. (1) coordinator.py:1053-1056 fängt den finalen Save-Fehler breit und loggt nur; _note_save_result (Z.1038-1049, F24-Eskalation) wird — anders als in _maybe_save Z.1032-1036 — nicht aufgerufen. (2) Z.1057-1059 löscht danach bedingungslos alle _active_issues aus der Registry; _issue() (Z.739-740) trägt persistence_failed_{entry_id} dort ein, das Issue wird also direkt nach dem Fehlschlag entfernt. […]
- **bestätigt** (Konfidenz 0.9): Bestätigt nach aktivem Widerlegungsversuch. Belege: (1) Code-Zitat exakt — coordinator.py:1053-1059 fängt jede Exception des finalen Save, loggt nur und löscht anschließend ALLE _active_issues inkl. persistence_failed_{entry_id}; __init__.py:212 enthält wörtlich '(no learning loss)'. (2) Kein Guard: PoiseStore.save (storage.py:33-34) ist ein dünner Wrapper um Store.async_save, I/O-Fehler propagieren; async_persist_and_cleanup wird bei jedem erfolgreichen Room-Unload aufgerufen (__init__.py:211-213). […]

---

### AR-22 · mittel · Testlücke

**Testlücke: Unload mit Save-Fehler — das definierte Swallow-Verhalten von async_persist_and_cleanup ist von keinem Test abgesichert**

- **Fundstelle:** `custom_components/poise/coordinator.py:1053` — `async_persist_and_cleanup`
- **Schadensklasse:** verlorenes Lernmodell
- **Verletzte Projektgrenze:** safety vs comfort: der finale Persist ist die einzige Verlust-Schranke fürs Lernmodell beim Unload; sein Fehlerverhalten existiert nur als unbelegter Code-Pfad
- **Codebeleg:** coordinator.py:1053-1056: `try:\n    await self._store.save(self._save_payload())\nexcept Exception:  # noqa: BLE001\n    _LOGGER.exception("Poise: final save on unload failed")`

**Befund:** Dimension: test-gap. Das Verhalten IST im Code definiert: __init__.py:211-214 ruft nach erfolgreichem Platform-Unload async_persist_and_cleanup(), und coordinator.py:1053-1056 schluckt jede Save-Exception, sodass der Unload True zurückgibt. Grep über tests/ nach 'async_persist_and_cleanup|async_save' liefert null Treffer — kein Test simuliert einen werfenden Store (Disk voll, OSError, JSON-Serialisierungsfehler) beim Unload. Der einzige Unload-Test (test_setup_and_cycle.py:95-97) prüft nur den Happy Path (NOT_LOADED). Auch der HA-Stop-Flush (async_flush_on_stop, coordinator.py:1081) wird in test_lifecycle_review.py:186-200 nur im Erfolgsfall getestet. Das Persistence-Failure-Repair-Issue (coordinator.py:1045-1049) hängt nur am periodischen Save-Pfad, nicht am finalen — auch das ist unbelegt.

**Mögliches Fehlverhalten im Realbetrieb:** Regressiert das breite except (z.B. Refactoring auf `except HomeAssistantError`), propagiert ein Save-Fehler aus async_unload_entry: der Entry landet in FAILED_UNLOAD, jede Options-Änderung/Reconfigure (die einen Reload braucht) ist blockiert, bis HA neu startet. Im heutigen (definierten) Verhalten geht der finale Lernstands-Flush stumm verloren — nur ein Log, kein Issue. Beides unterscheidet kein Test.

**Minimaler Reproduktionsfall / Testidee:**

```python
# tests/integration/test_setup_and_cycle.py
from unittest.mock import patch

async def test_unload_survives_final_save_failure(hass: HomeAssistant) -> None:
    """Ein werfender Store beim finalen Save darf den Unload nicht scheitern lassen."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_room_and_actuator(hass, room=19.5, sp=18.0)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "custom_components.poise.storage.PoiseStore.save",
        side_effect=OSError("disk full"),
    ):
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED  # kein FAILED_UNLOAD
    # optional: caplog-Assert auf 'final save on unload failed', damit der
    # Fehler wenigstens diagnostizierbar bleibt (definiertes Verhalten festnageln).
```

**Zur Absicherung nötig:** Produktentscheidung, ob ein fehlgeschlagener finaler Save ein Repair-Issue verdient (heute: nur Log; das persistence_failed-Issue coordinator.py:1045 greift nur im periodischen Pfad) — der Test sollte das gewollte Verhalten festschreiben.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92) (Schweregrad korrigiert → niedrig): Testlücke bestätigt. (1) Swallow-Verhalten existiert: coordinator.py:1053-1056 fängt jede Exception aus self._store.save() im finalen Unload-Save und loggt nur. (2) Aufrufpfad stimmt: __init__.py:211-213 ruft async_persist_and_cleanup() nach erfolgreichem async_unload_platforms; die HA-Annahme des Findings ist korrekt — eine propagierende Exception aus async_unload_entry setzt den Entry auf FAILED_UNLOAD, der bis HA-Neustart nicht reload-fähig ist (Options-/Reconfigure-Flow blockiert). […]
- **bestätigt** (Konfidenz 0.92): Alle Behauptungen am Code verifiziert: (1) Code-Zitat exakt korrekt — coordinator.py:1053-1056 schluckt jede Exception des finalen store.save mit bloßem Log; (2) __init__.py:211-213 ruft async_persist_and_cleanup() nach erfolgreichem Platform-Unload, der Swallow ist die einzige Schranke vor FAILED_UNLOAD; (3) Testlücke real: Grep über tests/ nach async_persist_and_cleanup = 0 Treffer, kein Test patcht PoiseStore.save mit side_effect (einziger side_effect im Testbaum ist unrelated, test_glue_coverage4.py:157); (4) einziger Unload-Test test_setup […]

---

### AR-23 · mittel · fehlender Kontext

**State-Listener, Stop-Flush und Update-Listener werden vor dem Plattform-Forwarding registriert: wirft das Forwarding unerwartet, kann (HA-versionsabhängig) ein Zombie-Koordinator ohne Entities weiter aktorisch regeln**

- **Fundstelle:** `custom_components/poise/__init__.py:142` — `async_setup_entry`
- **Schadensklasse:** Shadow-Code schreibt live
- **Verletzte Projektgrenze:** Lifecycle-Grenze: aktorisch wirksame Listener werden vor dem Punkt registriert, ab dem das Setup nicht mehr scheitern kann; bei Fehlschlag existiert Regel-Code ohne UI-Repräsentation
- **Codebeleg:** __init__.py:127-144: `entry.runtime_data = coordinator; coordinator.attach_listeners(entry); entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, ...)); entry.async_on_unload(entry.add_update_listener(...)); await hass.config_entries.async_forward_entry_setups(entry, [CLIMATE, SENSOR, SWITCH])`

**Befund:** Dimension: room-setup. Zwischen runtime_data-Zuweisung (Z.127) und Forwarding (Z.142) werden alle Listener scharf geschaltet. attach_listeners (coordinator.py:658-679) triggert bei jeder State-Änderung von Raumsensor/Fenster/Aktor async_request_refresh → _async_update_data → _run_once, das den Aktor SCHREIBT. Wirft async_forward_entry_setups eine unerwartete Exception (z.B. ImportError/SyntaxError eines Plattform-Moduls über integration.async_get_platform — normale Plattform-Setup-Fehler werden von EntityPlatform geschluckt), landet der Entry in SETUP_ERROR. HA-Core ruft _async_process_on_unload sicher bei ConfigEntryNotReady/ConfigEntryError/AuthFailed auf; ob der generische Exception-Zweig die on_unload-Callbacks ebenfalls aufräumt, ist versionsabhängig — tut er es nicht, bleiben State-Listener und Koordinator aktiv: eine Integration im Fehlerzustand ohne einzige Entity regelt den Heizungsaktor weiter, unsichtbar für den Nutzer.

**Mögliches Fehlverhalten im Realbetrieb:** Falls der Cleanup im generischen Fehlerzweig fehlt: unsichtbar weiterlaufende Aktorik (Setpoint-/Mode-Writes) bei einem Entry, der in der UI als fehlgeschlagen angezeigt wird — Kontrolle ohne Sichtbarkeit und ohne Abschaltmöglichkeit außer Entry-Disable. Robustheitsmaßnahme unabhängig von der HA-Version: Listener erst NACH erfolgreichem Forwarding registrieren (die 60-s-Tick-Latenz bis dahin ist unkritisch).

**Minimaler Reproduktionsfall / Testidee:** Nur mit HA-Testumgebung final belegbar: sensor.py mit einem Import versehen, der beim Plattform-Load wirft; Entry laden; prüfen, ob nach SETUP_ERROR ein State-Change des Raumsensors weiterhin Aktor-Service-Calls auslöst (Service-Call-Mock zählt Writes).

**Zur Absicherung nötig:** Exakte Ziel-HA-Version und deren ConfigEntry.async_setup: ruft der generische except-Exception-Zweig _async_process_on_unload auf (und wann wird runtime_data gelöscht)? Zudem: welche Fehlerklassen propagieren real aus async_forward_entry_setups.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9): Bestätigt durch Code-Lektüre von Repo UND HA-Core-Quellcode an gepinnten Tags. (1) Reihenfolge wie behauptet: __init__.py Z.127 runtime_data, Z.129 attach_listeners, Z.135-141 STOP-/Update-Listener, Z.142-144 async_forward_entry_setups. (2) Aktorik-Pfad real: coordinator.py Z.658-679 async_track_state_change_event auf Sensor/Fenster/Aktor -> async_request_refresh -> _run_once (Z.1218) mit Service-Writes (Z.1831/1904/1927/1960); ohne Entities kein 60s-Tick, aber jede State-Änderung schreibt. […]
- **bestätigt** (Konfidenz 0.88): Bestätigt per Quelltext-Prüfung von HA-Core über den gesamten Support-Bereich. (1) Zitat/Zeilen korrekt: __init__.py Z.127 runtime_data, Z.129 attach_listeners, Z.135-141 STOP-/Update-Listener, Z.142-144 Forwarding. (2) Kette real: attach_listeners (coordinator.py:646-679) -> async_request_refresh (Z.675); HA-DataUpdateCoordinator führt angeforderte Refreshes OHNE Entity-Listener aus (nur der Intervall-Tick ist listener-gated); _async_update_data -> _run_once schreibt den Aktor (coordinator.py:1831-1971, actuator_mod.write/services.async_call); […]

---

### AR-24 · mittel · begründeter Verdacht

**Blocking-Boiler-OFF-Calls in Unload-/Remove-Pfaden ohne das 10-s-Timeout des normalen Aktuationspfads — hängender Boiler-Service blockiert Unload/Remove unbegrenzt und vergrößert das Timer-Race-Fenster**

- **Fundstelle:** `custom_components/poise/hub_coordinator.py:336` — `PoiseHubCoordinator.async_fire_boiler_off / __init__._remove_hub_entry`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** safety vs comfort: der Safety-Hand-over-Pfad ist weniger robust abgesichert als der reguläre Regelpfad; Inkonsistenz zum eigenen N-1-Review-Standard im selben Modul
- **Codebeleg:** hub_coordinator.py:336-341 und __init__.py:244-246: `await hass.services.async_call(off.domain, off.service, dict(off.data), blocking=True)` — kein asyncio.timeout, im Gegensatz zu _call (hub_coordinator.py:77, 239: `async with asyncio.timeout(_BOILER_CALL_TIMEOUT_S)` — 'a hung boiler service must not stall the hub (N-1)')

**Befund:** Unabhängig gefunden von 2 Reviewern (Dimensionen: unload, ha-api; sekundär miterwähnt in 2 weiteren Findings der remove-Dimension). Die N-1-Begründung im selben Modul führt für den normalen Tick ein 10-s-Timeout ein; die beiden Teardown-OFFs — async_fire_boiler_off (Unload-Handover) und der Removal-OFF in __init__.py:244-246 — rufen blocking=True OHNE Timeout. hass.services.async_call(blocking=True) awaitet den Handler unbegrenzt (core.py 2025.1.0:2795). Ein hängender Handler blockiert async_unload_entry bzw. async_remove_entry unbegrenzt; beide halten das setup_lock des Entries — Disable/Reload/Löschen in der UI hängt, HA-Shutdown verzögert sich, und wegen der on_unload-Semantik feuert währenddessen der Hub-Timer weiter (verlängert das Race-Fenster aus dem Hub-Unload-Race-Finding). Die im Code selbst dokumentierte Gefährdungsannahme (N-1: Boiler-Integration kann hängen) wird in genau den Pfaden nicht angewendet, die bei Problemen mit dieser Integration am wahrscheinlichsten ausgelöst werden (Nutzer deaktiviert/entfernt den Hub, WEIL der Boiler-Stack klemmt).

**Mögliches Fehlverhalten im Realbetrieb:** Reload/Disable/Delete des Hubs kann unbegrenzt hängen (UI-Operation kehrt nie zurück, Entry verschwindet nicht); kein direkter Aktorik-Schaden, aber Teardown-Robustheit verletzt und Race-Fenster vergrößert.

**Minimaler Reproduktionsfall / Testidee:** Boiler-OFF-Service durch eine hängende Integration ersetzen (Handler mit await asyncio.Event().wait()), Hub deaktivieren oder löschen: async_unload_entry/async_remove_entry kehrt nie zurück, Timer-Ticks laufen weiter.

**Zur Absicherung nötig:** Keiner — Inkonsistenz ist codeintern belegt. Fix: dieselbe asyncio.timeout(_BOILER_CALL_TIMEOUT_S)-Hülle in async_fire_boiler_off und _remove_hub_entry.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): Bestätigt nach aktivem Widerlegungsversuch. Code-Beleg: hub_coordinator.py:336-341 (async_fire_boiler_off) und __init__.py:244-246 (_remove_hub_entry) rufen hass.services.async_call(..., blocking=True) OHNE Timeout; der reguläre Pfad _call (hub_coordinator.py:239-242) hat `async with asyncio.timeout(_BOILER_CALL_TIMEOUT_S)` mit der N-1-Begründung in Z. 77 ("a hung boiler service must not stall the hub"). Die except-Klauseln (Z. 342 bzw. __init__.py:247) helfen gegen einen Hang nicht (keine Exception). […]
- **bestätigt** (Konfidenz 0.92): Bestätigt nach aktivem Widerlegungsversuch. Alle Zitate stimmen: hub_coordinator.py:336-341 (async_fire_boiler_off) und __init__.py:244-246 (_remove_hub_entry) rufen hass.services.async_call(blocking=True) OHNE Timeout, während der reguläre Pfad _call (hub_coordinator.py:239) mit asyncio.timeout(_BOILER_CALL_TIMEOUT_S=10.0, Zeile 77, N-1-Kommentar) abgesichert ist — async_fire_boiler_off hätte schlicht self._call(self._action_off) nutzen können. HA-Core 2025.1.0 (gepinnte Version lt. […]

---

### AR-25 · niedrig *(Erst-Einstufung: mittel)* · begründeter Verdacht

**Fehlgeschlagener Plattform-Unload beim Hub-Disable: OFF-Handover und Issue-Cleanup übersprungen, Timer läuft weiter — disabled Hub aktuiert den Boiler bis zum Neustart**

- **Fundstelle:** `custom_components/poise/__init__.py:183` — `async_unload_entry (Hub-Zweig)`
- **Schadensklasse:** ungewolltes Heizen
- **Verletzte Projektgrenze:** safety vs comfort: der Safety-Handover ist an den Erfolg eines reinen UI-/Diagnose-Plattform-Unloads gekoppelt
- **Codebeleg:** __init__.py:183-205: `unloaded_sys = await hass.config_entries.async_unload_platforms(entry, [Platform.BINARY_SENSOR])\nif unloaded_sys:\n    ...OFF-Handover + cleanup_issues...\nreturn bool(unloaded_sys)`

**Befund:** Dimension: unload. Der gesamte Handover (resolve_hub_unload_off → async_fire_boiler_off, cleanup_issues bei disabled_by) hängt am Erfolg des Binary-Sensor-Plattform-Unloads. Gibt async_unload_platforms False zurück, liefert async_unload_entry False; HA setzt FAILED_UNLOAD und führt die on_unload-Callbacks NICHT aus — der unabhängige Tick-Timer (__init__.py:97-101) feuert weiter und _async_update_data aktuiert den Boiler weiter (hub_coordinator.py:361-362), obwohl entry.disabled_by bereits gesetzt ist. Der Zustand hält bis zum HA-Neustart — und beim Neustart feuert auch niemand mehr ein OFF, weil der Handover-Pfad nie lief. Mitgeprüft, kein Finding: entry.runtime_data kann in HA-initiierten Unloads nicht fehlen (HA entlädt nur LOADED-Entries; runtime_data wird vor return True gesetzt).

**Mögliches Fehlverhalten im Realbetrieb:** Ein vom Nutzer deaktivierter Hub steuert den Boiler unsichtbar weiter (Entry als disabled angezeigt) und schaltet ihn beim späteren Neustart nie per Handover ab — der Boiler bleibt in dem Zustand, den der letzte Tick vor dem Neustart setzte.

**Minimaler Reproduktionsfall / Testidee:** Binary-Sensor-Unload zum Fehlschlag bringen (Exception im Entity-Teardown einer gepatchten HA-Umgebung), dann Hub-Entry deaktivieren: async_unload_entry → False, kein OFF, kein cleanup_issues, _hub_tick feuert weiter, Boiler folgt weiter der Demand-Aggregation.

**Zur Absicherung nötig:** Wie wahrscheinlich ein Plattform-Unload-Fehlschlag bei der eigenen Binary-Sensor-Plattform ist (aktuell kein erkennbarer Fehlerpfad in binary_sensor.py, Trigger exotisch). Robuster: Handover/cleanup auch bei unloaded_sys=False ausführen, wenn entry.disabled_by gesetzt ist.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): Mechanismus vollständig verifiziert, Widerlegung fehlgeschlagen. (1) Code: In /home/user/poise-thermostat/custom_components/poise/__init__.py:180-206 hängen OFF-Handover (resolve_hub_unload_off → hub.async_fire_boiler_off()) und cleanup_issues() komplett an `if unloaded_sys:`; der Tick-Timer ist nur via entry.async_on_unload registriert (__init__.py:97-101). […]
- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): Mechanik vollständig belegt: (1) Zitat/Zeile korrekt — custom_components/poise/__init__.py:183 `if unloaded_sys:` gateet OFF-Handover (Z.197-202) und cleanup_issues (Z.204-205); Z.206 `return bool(unloaded_sys)`. (2) HA-Semantik stimmt: HA-Core config_entries.py (dev, Z.1040-1051) ruft `_async_process_on_unload` NUR bei result=True, sonst FAILED_UNLOAD — der per `entry.async_on_unload` registrierte Tick-Timer (__init__.py:97-101) läuft bei Unload-Fehlschlag weiter; auch DataUpdateCoordinator.async_shutdown ist nur ein on_unload-Callback (update […]

---

### AR-26 · niedrig · Verbesserungsvorschlag

**Kein Setup-Guard gegen einen zweiten System-Entry: bei zwei Hub-Entries (Storage-Restore/Backup-Merge) entstünden zwei konkurrierende Boiler-Schreiber mit kämpfenden Keepalives**

- **Fundstelle:** `custom_components/poise/__init__.py:80` — `async_setup_entry`
- **Schadensklasse:** Batterie-/Zigbee-Schreibsturm
- **Verletzte Projektgrenze:** Single-Writer-Invariante des System-Hubs wird nur im Config-Flow, nicht im Lifecycle-Code durchgesetzt
- **Codebeleg:** __init__.py:80-84: `if _is_system(entry):\n    from .hub_coordinator import PoiseHubCoordinator\n    hub = PoiseHubCoordinator(hass, entry)\n    await hub.async_config_entry_first_refresh()` — kein Check auf bereits geladenen zweiten system-Entry

**Befund:** Dimension: docs-vs-code. manifest.json hat kein single_config_entry — korrekt, weil Raum-Entries mehrfach existieren müssen. Die Singleton-Garantie des Hubs lebt ausschließlich im Config-Flow (unique_id 'poise_system' + _abort_if_unique_id_configured, config_flow.py:736-737). async_setup_entry lädt aber jeden Entry mit entry_type=system anstandslos: Existieren zwei System-Entries (Backup-Merge, .storage-Edit oder aus einer Version vor der Flow-Absicherung), laufen zwei unabhängige PoiseHubCoordinator mit eigenen Timern, BoilerStates und Keepalives auf denselben Boiler-Actions — die Single-Writer-Invariante (ADR-0038 Entscheidung 2, ADR-0039: 'schließt konkurrierende Schreiber aus') wird von nichts mehr verteidigt; bei divergierenden Zuständen feuern die Keepalives alle 300 s abwechselnd ON und OFF. Nebenbefund positiv: manifest-Abhängigkeiten und hacs.json-Mindestversion (2025.1.0) decken alle benutzten APIs.

**Mögliches Fehlverhalten im Realbetrieb:** Nur außerhalb des UI-Pfads erreichbar; dann aber wechselseitig kämpfende ON/OFF-Keepalives auf dem Boiler-Schalter (Funk-Schreiblast, Boiler-Takten). Ein billiger Guard (zweiten system-Entry mit ConfigEntryError abweisen) wäre Defense-in-Depth analog zum F12-Prinzip.

**Minimaler Reproduktionsfall / Testidee:** Zweiten Entry mit data.entry_type='system' direkt in .storage/core.config_entries injizieren (oder Backup zweier Instanzen mergen), HA starten → beide Hubs setzen auf, beide aktuieren (hub_coordinator.py:361-362), keiner weiß vom anderen.

**Zur Absicherung nötig:** Ob es historische Poise-Versionen ohne den unique_id-Singleton gab (dann wären Bestandsinstallationen mit Doppel-Hub real möglich und async_migrate_entry müsste deduplizieren).

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85): Bestätigt mit einer Reachability-Korrektur nach unten. Faktenlage: (1) __init__.py:80-105 lädt jeden entry_type=system-Entry bedingungslos — eigener PoiseHubCoordinator, eigener Timer (Z. 97-101), kein Guard. (2) Die Singleton-Garantie existiert ausschließlich im Flow (config_flow.py:736-737); quality_scale.yaml:16 stützt sich explizit nur darauf. (3) Die HA-Annahme stimmt: HA Core setzt Entries mit doppelter unique_id aus .storage beide auf (nur ERROR-Log, keine Verhinderung; single_config_entry wirkt nur im Flow und ist hier unbrauchbar). […]
- **bestätigt** (Konfidenz 0.88): Bestätigt mit Belegen, Erreichbarkeit noch enger als behauptet. (1) Code-Quote korrekt: custom_components/poise/__init__.py:80-85 lädt jeden system-Entry ohne Duplikat-Check und hängt je Entry einen eigenen Timer an (Z. 97-101); kein Guard an anderer Lifecycle-Stelle (Grep über alle ENTRY_TYPE_SYSTEM-Stellen; hub_coordinator.py:140 überspringt fremde System-Entries sogar explizit — zwei Hubs ignorieren einander). (2) Singleton nur im Flow: config_flow.py:736-737 exakt wie zitiert. […]

---

### AR-27 · niedrig · fehlender Kontext

**Migrations-Merge 'options gewinnt': ob damit ein neuerer V1-data-Wert verdeckt werden kann, hängt vom nicht mehr rekonstruierbaren V1-Verhalten ab**

- **Fundstelle:** `custom_components/poise/migration.py:84` — `migrate_room_entry`
- **Schadensklasse:** falscher Komfortzustand
- **Verletzte Projektgrenze:** options vs data: Alterspräferenz per Konvention statt per Zeitstempel
- **Codebeleg:** migration.py:84: `merged: dict[str, object] = {**data, **options}` — Begründung Z.79-81: "it holds the newer, hot-tuned value"

**Befund:** Dimension: migration. Die Annahme stimmt nur, wenn unter V1 ein Options-Flow existierte UND es keinen V1-Pfad gab, der Tuning NACH einem Options-Save wieder nach data schrieb (z.B. V1-Reconfigure mit Tuning-Feldern) — dann wäre der data-Wert der neuere und ginge verloren. Entschärfend: Der Coordinator liest heute {**entry.data, **entry.options} (coordinator.py:324), options gewann also vermutlich auch unter V1 zur Laufzeit — die Migration konserviert dann den effektiv wirksamen Wert ohne Verhaltensbruch. Die Git-Historie besteht nur aus 'Add files via upload'-Squashes, der V1-Flow-Code ist nicht rekonstruierbar. Positiv geprüft: unbekannte Keys gehen nicht verloren (migration.py:89); strukturelle Keys sind data-owned (Z.85-87, Test F20).

**Mögliches Fehlverhalten im Realbetrieb:** Falls V1 einen Reconfigure-Pfad hatte, der Tuning in data voll ersetzte, übernimmt die Migration einen älteren Options-Wert als dauerhaft wirksamen (z.B. alte comfort_base) — wegen identischer Merge-Reihenfolge zur Laufzeit aber ohne beobachtbaren Sprung. Reines Konsistenz-/Erwartungsrisiko.

**Minimaler Reproduktionsfall / Testidee:** Nur mit V1-Code reproduzierbar: V1-Entry mit options={comfort_base:23.5} (alt) und data={comfort_base:20.0} (neuer); migrate_room_entry liefert options[comfort_base]==23.5 (vom Unit-Test test_options_win_over_data_on_conflict, tests/test_migration.py:37-41, als GEWOLLT festgeschrieben).

**Zur Absicherung nötig:** V1-Release-Quellcode (hatte V1 einen Options-Flow? Schrieb ein V1-Reconfigure Tuning nach data?). Ohne ihn ist nicht entscheidbar, ob 'options gewinnt' je einen tatsächlich neueren Wert verwirft.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85): Aktive Widerlegung versucht, gescheitert — alle Faktenanker verifiziert. (1) V1-Unrekonstruierbarkeit sogar stärker belegt als im Finding: alle 50 Commits (git rev-list --all) enthalten config_flow.py bereits mit VERSION = 2; der Root-Commit b51a7c5 (2026-07-07, manifest 0.153.0) enthält migration.py fertig; keine git-Tags, keine GitHub-Releases (list_releases/list_tags: leer). Ein V1-Flow-Code existiert nirgends. […]
- **bestätigt** (Konfidenz 0.85): Alle prüfbaren Behauptungen halten der Verifikation stand. (1) Zitat korrekt: migration.py:84 `merged: dict[str, object] = {**data, **options}`; Begründung "it holds the newer, hot-tuned value" steht in Z.77-78 (Finding nennt Z.79-81, off-by-2, Substanz korrekt). (2) Kernaussage "V1-Verhalten nicht rekonstruierbar" bestätigt: alle 50 Commits sind 'Add files via upload'-Squashes, der älteste Commit hat bereits VERSION=2 (config_flow.py:683) und manifest 0.153.0 mit vorhandener migration.py — kein V1-Flow-Code, keine Tags, kein Changelog im Repo; […]

---

### AR-28 · niedrig *(Erst-Einstufung: mittel)* · sicherer Fehler

**async_persist_and_cleanup nimmt self._lock nicht — finaler Save kann einen halb-aktualisierten Mid-Tick-Modellzustand persistieren**

- **Fundstelle:** `custom_components/poise/coordinator.py:1051` — `PoiseCoordinator.async_persist_and_cleanup`
- **Schadensklasse:** verlorenes Lernmodell
- **Verletzte Projektgrenze:** HA-Seiteneffekt-Reihenfolge: Persist läuft vor der Abmeldung der per async_on_unload registrierten Listener (die erst nach async_unload_entry erfolgt)
- **Codebeleg:** coordinator.py:1051-1056: `async def async_persist_and_cleanup(self) -> None:\n    try:\n        await self._store.save(self._save_payload())` — KEIN `async with self._lock`, im Gegensatz zu async_flush_on_stop (Z.1087) und _async_update_data (Z.1094)

**Befund:** Dimension: unload. async_flush_on_stop und _async_update_data serialisieren über self._lock; async_persist_and_cleanup nicht — klare Asymmetrie, der Lock existiert genau für diesen Zweck. Real erreichbar: die per entry.async_on_unload registrierten State-Change-Listener (attach_listeners, Z.677-679) und der Stop-Listener werden erst NACH Rückkehr von async_unload_entry entfernt (HA-Semantik), und ein vor Unload-Beginn gestarteter Tick kann in _run_once an einem await-Punkt stehen (Service-Calls Z.1831-1960, _maybe_save Z.1231, Forecast/Trace) und den Lock halten. _save_payload() (Z.1002-1024) liest dann EKF/TRM/outcome_stats/override mitten in einem Tick — komponentenübergreifend inkonsistenter Snapshot; Mutationen nach dem Snapshot gehen verloren. Zusatzeffekt derselben Reihenfolge-Lücke: zwischen Plattform-Unload und Unload-Rückkehr kann ein State-Change über async_request_refresh noch einen vollen Tick inkl. Aktor-Schreibzugriff auf dem gerade entladenen/disabled Entry auslösen.

**Mögliches Fehlverhalten im Realbetrieb:** Der als final gespeicherte Lernzustand kann ein inkonsistenter Mid-Tick-Schnappschuss sein (z.B. EKF fortgeschrieben, Lifecycle/Override noch alt) und Mutationen des letzten Ticks verlieren; zusätzlich möglicher später Aktor-Write auf einem Entry, das der Nutzer gerade entlädt/deaktiviert.

**Minimaler Reproduktionsfall / Testidee:** Reload/Disable eines Raum-Entries auslösen, während der 60-s-Tick in _run_once an einem await hängt (blockierender climate-Call). async_unload_entry → async_persist_and_cleanup läuft ohne Lock parallel, _save_payload() snapshottet mid-tick, store.save schreibt diesen Zustand als finalen.

**Zur Absicherung nötig:** Keiner — Fix ist mechanisch: async with self._lock um den Save wie in async_flush_on_stop.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): Bestätigt mit Beleg: coordinator.py:1051-1056 speichert in async_persist_and_cleanup ohne `async with self._lock`, während async_flush_on_stop (Z.1087) und _async_update_data (Z.1094) den Lock nehmen — die behauptete Asymmetrie ist wörtlich im Code. HA-Realitäts-Check stützt die Erreichbarkeit: (1) __init__.py:208-213 ruft den Persist innerhalb von async_unload_entry auf; HA arbeitet entry.async_on_unload-Callbacks (State-Change-Listener Z.677-679, Coordinator-Shutdown) erst NACH Rückkehr von async_unload_entry ab. […]
- **bestätigt** (Konfidenz 0.8) (Schweregrad korrigiert → niedrig): Bestätigt nach aktivem Widerlegungsversuch. (1) Zitat exakt: coordinator.py:1051-1056 speichert ohne Lock; async_flush_on_stop (Z.1087) und _async_update_data (Z.1094) nehmen `async with self._lock` (Lock: Z.312). (2) Kein Guard: __init__.py:208-214 ruft async_persist_and_cleanup direkt nach async_unload_platforms — kein async_shutdown, kein Lock, kein Warten auf den laufenden Tick; die per entry.async_on_unload registrierten Listener (coordinator.py:677-679, __init__.py:135-141) und der Coordinator-Shutdown laufen nach HA-Semantik erst NACH Rü […]

---

### AR-29 · niedrig · begründeter Verdacht

**_remove_hub_entry: except (HomeAssistantError, ValueError) fängt vol.Invalid aus der synchronen Service-Schema-Validierung nicht — Löschung des Frost-Repair-Issues wird übersprungen**

- **Fundstelle:** `custom_components/poise/__init__.py:247` — `_remove_hub_entry`
- **Schadensklasse:** falsche UI-Anzeige
- **Verletzte Projektgrenze:** diagnostic-only vs live: Fehler des Live-Aktorik-Calls verhindert den rein diagnostischen Cleanup — zwei unabhängige Teardown-Pflichten sequenziell gekoppelt
- **Codebeleg:** __init__.py:247-251: `except (HomeAssistantError, ValueError):\n    logging.getLogger(__name__).exception("Poise: boiler OFF on hub removal failed")\nir.async_delete_issue(hass, DOMAIN, "frost_zone_not_controlling_boiler")`

**Befund:** Unabhängig gefunden von 2 Reviewern (Dimensionen: remove, ha-api; letzterer verifizierte core.py 2025.1.0:2758-2768). parse_service_action übernimmt beliebige key:value-Paare als Strings (hub_aggregate.py:211-216). Bei blocking=True validiert HA die Service-Daten synchron gegen das Handler-Schema und re-raised vol.Invalid unverändert; voluptuous.Invalid erbt von voluptuous.Error(Exception) — weder HomeAssistantError noch ValueError, entkommt also dem except. Der Core fängt die Exception eine Ebene höher (ConfigEntry.async_remove: 'Error calling entry remove callback'), aber ir.async_delete_issue in Z.251 wird nie erreicht: das Frost-Issue überlebt die Deinstallation, im Widerspruch zum F16-Docstring ('clear the frost repair issue so it does not survive deinstallation', __init__.py:229). Der Hub-Tick-Pfad benutzt dagegen bewusst except Exception (_call, hub_coordinator.py:244). Verwandt: dieselbe zu enge except-Tuple lässt auch RuntimeError durch (siehe vakantes-Test-Finding).

**Mögliches Fehlverhalten im Realbetrieb:** Wenn die gespeicherte Boiler-OFF-Action Daten enthält, die das Service-Schema ablehnt (Tippfehler im Action-Spec, umgebauter Ziel-Service, handeditierter Storage), überlebt das Repair-Issue 'frost_zone_not_controlling_boiler' die Deinstallation — genau das, was F16 verhindern soll. Zusätzlich bricht der Remove-Callback mit geloggtem Core-Fehler ab.

**Minimaler Reproduktionsfall / Testidee:** Hub mit CONF_BOILER_OFF_ACTION 'switch.boiler/switch.turn_off/foo:bar' und ON-Action anlegen, Frost-Issue aktiv, Hub löschen: switch.turn_off-Schema (extra=PREVENT) wirft vol.Invalid synchron → except greift nicht → ir.async_delete_issue wird nie erreicht.

**Zur Absicherung nötig:** Wie strikt der Config-Flow die Action-Daten beim Anlegen validiert; je laxer, desto realer der Pfad. Fix: vol.Invalid mit fangen (oder breites except wie in _call/async_fire_boiler_off) und das Issue-Delete in ein finally ziehen.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9): Widerlegung fehlgeschlagen — jede Teilbehauptung hält der Quellcode-Prüfung stand. (1) Reachability: parse_service_action (custom_components/poise/control/hub_aggregate.py:212-215) übernimmt beliebige key:value-Extras; der Config-Flow prüft nur Parsebarkeit (config_flow.py:671-674), nicht Schema-Konformität — 'switch.boiler/switch.turn_off/foo:bar' passiert den Flow. […]
- **bestätigt** (Konfidenz 0.9): Bestätigt nach aktivem Widerlegungsversuch. (1) Zitat exakt: __init__.py:247 `except (HomeAssistantError, ValueError):`, ir.async_delete_issue in Z.251 liegt außerhalb des try — eine entkommende Exception überspringt es. (2) vol.Invalid entkommt: HA core 2025.1.0 (gefetcht) re-raised in ServiceRegistry.async_call `except vol.Invalid: ... raise` unverändert, synchron vor Task-Dispatch (blocking=True nicht mal nötig); voluptuous Invalid(Error(Exception)) ist weder HomeAssistantError noch ValueError. […]

---

### AR-30 · niedrig · sicherer Fehler

**ADR-0038 Entscheidung 6 ('System-Onboarding erscheint nur bei ≥2 Zonen oder konfigurierter geteilter Ressource') ist nicht umgesetzt — das System-Menü erscheint immer**

- **Fundstelle:** `custom_components/poise/config_flow.py:698` — `async_step_user`
- **Schadensklasse:** falsche UI-Anzeige
- **Verletzte Projektgrenze:** Doku-vs-Code: ADR-Entscheidungspunkt als implementiert deklariert, aber nicht kodiert
- **Codebeleg:** config_flow.py:698: `return self.async_show_menu(step_id="user", menu_options=["room", "system"])`

**Befund:** Dimension: docs-vs-code. ADR-0038 Entscheidung 6: 'Optional/unsichtbar: kein Hub-Entry bei einer Zone; das "Poise System"-Onboarding erscheint nur bei ≥2 Zonen oder konfigurierter geteilter Ressource.' Der Flow zeigt das Menü mit 'system' bedingungslos — auch bei null Zonen kann sofort ein System-Hub angelegt werden. Das README (Z.85) beschreibt das tatsächliche Codeverhalten; der ADR widerspricht — und begründet die Gating-Entscheidung explizit mit 'Komplexität ist ein Adoptions-Killer'. Positiv gegengeprüft: die Singleton-Garantie hält (unique_id 'poise_system' + _abort_if_unique_id_configured, config_flow.py:736-737).

**Mögliches Fehlverhalten im Realbetrieb:** Onboarding-/UI-Verhalten weicht von der dokumentierten Architektur-Entscheidung ab; Nutzer mit einer Zone bekommen den Mehrzonen-Hub angeboten, den der ADR bewusst verstecken wollte. Kein Regelungs-/Sicherheitsschaden.

**Minimaler Reproduktionsfall / Testidee:** Settings → Add Integration → Poise: Menü zeigt 'system' auch ohne einen einzigen Raum-Entry (async_step_user hat keine Zonen-Zählung; kein Verweis auf async_entries).

**Zur Absicherung nötig:** Entscheidung des Maintainers, ob der ADR (per Nachtrag) oder der Flow (Menü konditional auf ≥2 Raum-Entries) angepasst wird.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.93): Bestätigt nach aktiven Widerlegungsversuchen. (1) config_flow.py:695-698: async_step_user ist ein unbedingter Einzeiler `return self.async_show_menu(step_id="user", menu_options=["room", "system"])` — keine Zonen-Zählung, kein Gating; `_async_current_entries()` wird im selben File nur für Aktor-Dedup (Z.715, 780) genutzt, nicht fürs Menü. (2) Kein alternativer Onboarding-Mechanismus: Grep über die Integration findet weder Discovery-Step noch Repair-Issue, das die Hub-Anlage vorschlägt — das Menü ist der einzige Pfad. […]
- **bestätigt** (Konfidenz 0.93): Bestätigt nach aktiver Widerlegungsprüfung. (1) Zitat/Zeile exakt: config_flow.py:698, async_step_user (Z.695-698) zeigt das Menü ["room","system"] bedingungslos — keine Zonen-Zählung, kein async_entries-Verweis. (2) Kein Guard anderswo: async_step_system (Z.732-748) hat nur den Singleton-Abort (unique_id "poise_system", Z.736-737), keine Mindest-Zonen-Prüfung; das einzige Entry-Gating im Flow (Z.217-221, hub_exists) blendet nur die "anlagen"-Sektion im Raum-Formular ein — umgekehrte Richtung, kein Menü-Gating. […]

---

### AR-31 · niedrig · Verbesserungsvorschlag

**quality_scale.yaml enthält veraltete Selbstauskunft: 'via_device ... still pending' ist längst implementiert, Testzahl (74 statt 98) stimmt nicht mehr**

- **Fundstelle:** `custom_components/poise/quality_scale.yaml:64` — `rules.devices / rules.test-coverage`
- **Schadensklasse:** falsche UI-Anzeige
- **Verletzte Projektgrenze:** Doku-vs-Code: Selbstauskunft veraltet
- **Codebeleg:** quality_scale.yaml:64: `devices: done  # DeviceInfo per zone + hub; via_device hub<->zone link still pending (review M9)` ... `test-coverage: done  # HA-glue 95.1% (74 integration tests, ...)`

**Befund:** Dimension: docs-vs-code. Der devices-Kommentar behauptet, der via_device-Link sei 'still pending' — er ist implementiert: coordinator.py:487-496 (via_device_id, M9), gesetzt in sensor.py:246, switch.py:56 und weiteren Plattformen. Der test-coverage-Kommentar nennt 74 Integrationstests; tatsächlich sind es 98 (Zählung def test_ in tests/integration/*.py). Beide Abweichungen gehen in die harmlose Richtung (Code besser als Doku), verletzen aber die Regel, dass die Selbstauskunft dem Code entsprechen muss. Lifecycle-relevant gegengeprüft und KORREKT: config-entry-unloading, test-before-setup, unique-config-entry, parallel-updates, entity-unavailable, runtime-data, reauthentication-exempt.

**Mögliches Fehlverhalten im Realbetrieb:** Irreführende Selbstauskunft für Core-Review/HACS-Audit; keine Laufzeitwirkung.

**Minimaler Reproduktionsfall / Testidee:** Vergleich quality_scale.yaml:64 mit coordinator.py:487 und sensor.py:246; grep -c 'def test_' tests/integration/*.py → 98 ≠ 74.

**Zur Absicherung nötig:** Keiner; Kommentare aktualisieren. Die Coverage-Prozentwerte sind ohne CI-Lauf nicht verifizierbar.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.95): Beide Kernbehauptungen verifiziert. (1) quality_scale.yaml:64 behauptet "via_device hub<->zone link still pending (review M9)", aber der Link ist implementiert: coordinator.py:487-496 (Property via_device_id, Docstring nennt explizit M9, liefert (DOMAIN, entry_id) des System-Hubs) und wird in sensor.py:246, switch.py:56 und climate.py:184 als via_device=coordinator.via_device_id gesetzt; tests/integration/test_review_v083_fixes.py:283/288/309 testen den Link sogar in beide Richtungen (mit Hub genestet, ohne Hub None). […]
- **bestätigt** (Konfidenz 0.95): Bestätigt nach Code-Lektüre. (1) via_device ist implementiert, nicht "pending": coordinator.py:487-496 Property via_device_id (M9-Docstring), gesetzt in climate.py:184, sensor.py:246, switch.py:56; getestet in tests/integration/test_review_v083_fixes.py:252-309 (assert zone_dev.via_device_id == hub_dev.id). Der Kommentar in quality_scale.yaml:64 ("via_device hub<->zone link still pending") ist veraltet. […]

---

### AR-32 · niedrig *(Erst-Einstufung: mittel)* · sicherer Fehler

**Als 'SHADOW (diagnostic only, no writes)' kommentierter Block erzeugt die live wirksame Stellgröße _hum_action (dry-Mode-Nudge) — Fehler darin werden nur auf DEBUG verschluckt**

- **Fundstelle:** `custom_components/poise/coordinator.py:1611` — `PoiseCoordinator._run_once`
- **Schadensklasse:** Shadow-Code schreibt live
- **Verletzte Projektgrenze:** diagnostic-only-Block vs Live-Aktuation: Live-Stellgrößenberechnung (_hum_action, _dry_active) lebt in einem als 'no writes' deklarierten, debug-verschluckten Diagnose-Block
- **Codebeleg:** coordinator.py:1611-1612: '# ADR-0050/0051 SHADOW (diagnostic only, no writes): ...' — aber Z.1640: `_hum_action = _hum.action`; Z.1773-1777: `final_mode = mode_arbitration(base_mode=mode, humidity_action=_hum_action, dry_ok="dry" in act_modes)`; Z.1831-1835: `await self.hass.services.async_call("climate", "set_hvac_mode", {..., "hvac_mode": desired_hvac}, ...)`

**Befund:** Dimension: boundaries. Der try-Block ab coordinator.py:1615 ist als reiner Diagnose-/Shadow-Block deklariert (Kommentar 1611-1612, Except-Handler 1723-1724: 'shadow diagnostics must never break tick', nur _LOGGER.debug). Tatsächlich berechnet er mit humidity_decide (1629-1638) die Größe _hum_action und mutiert den Live-Latch self._dry_active (1639), und _hum_action steuert über mode_arbitration (1773-1777) den realen set_hvac_mode('dry')-Service-Call (1831). Das widerspricht dem Blockkommentar und verwischt die ADR-0026/0033-Grenze 'Shadow rechnet nur': ein Teil des Shadow-Blocks IST der Live-Pfad. Funktionale Konsequenz: wirft humidity_decide (oder Code davor, z.B. humidity_ratio, 1624-1628), degradiert eine LIVE-Regelachse (Entfeuchten) still auf 'idle' — dauerhaft und nur als DEBUG-Log sichtbar, während für echte Live-Pfade sonst _LOGGER.exception gilt (1837-1842, 1890-1893).

**Mögliches Fehlverhalten im Realbetrieb:** Grenzverletzung diagnostic-only vs live: Wartende dürfen laut Kommentar annehmen, der Block sei folgenlos abschaltbar/fehlertolerant — tatsächlich hängt der ADR-0050-S2c-Dry-Pfad daran. Ein persistenter Fehler in der Feuchte-Logik schaltet die Entfeuchtung unsichtbar ab (falscher Komfortzustand, Schimmelrisiko steigt indirekt); umgekehrt wird eine aktorisch wirksame Entscheidung unter einem 'no writes'-Label gepflegt und bei künftigen Änderungen als harmlos behandelt.

**Minimaler Reproduktionsfall / Testidee:** Code-Inspektion genügt: _hum_action wird ausschließlich innerhalb des als 'SHADOW (diagnostic only, no writes)' kommentierten try-Blocks gesetzt (1614/1640) und in 1773-1777 in den Live-Modus-Nudge gefaltet. Fehlerpfad: rh-Sensor liefert einen Wert, der humidity_decide werfen lässt → except 1723 (debug) → _hum_action bleibt 'idle' → dry wird nie kommandiert, ohne sichtbare Meldung.

**Zur Absicherung nötig:** ADR-0050 S2c bestätigt, dass der Dry-Nudge live sein SOLL (Zeilenkommentar 1614) — das Finding betrifft die falsche Block-Deklaration und die dadurch falsche Fehlerbehandlungsklasse (debug-Swallow) für einen Live-Regelpfad, nicht die Dry-Funktion selbst.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.86) (Schweregrad korrigiert → niedrig): Kernbeobachtung bestätigt, Impact deutlich übertrieben. FAKTEN STIMMEN: Header coordinator.py:1611-1612 sagt 'SHADOW (diagnostic only, no writes)', aber Z.1639-1640 setzen im selben try-Block den Live-Latch self._dry_active und _hum_action, die über mode_arbitration (1773-1777) den realen set_hvac_mode-Call (1831-1836) steuern; der Except-Handler 1723-1724 loggt nur DEBUG, während echte Live-Pfade _LOGGER.exception nutzen (1837-1842, 1890-1893). […]
- **bestätigt** (Konfidenz 0.8) (Schweregrad korrigiert → niedrig): Kern bestätigt, Schadensbehauptung weitgehend widerlegt, daher Severity auf niedrig korrigiert. BESTÄTIGT: Alle Zitate stimmen — coordinator.py:1611-1612 deklariert den Block als "SHADOW (diagnostic only, no writes)", aber Z.1639-1640 setzen darin den Live-Latch self._dry_active und die Live-Stellgröße _hum_action, die über mode_arbitration (Z.1773-1777) den realen set_hvac_mode("dry")-Call (Z.1831-1835) steuert; der except (Z.1723-1724) verschluckt auf DEBUG, während echte Live-Pfade _LOGGER.exception nutzen (Z.1837-1842, 1890-1893). […]

---

### AR-33 · niedrig *(Erst-Einstufung: mittel)* · begründeter Verdacht

**Setup-Guard erkennt registry-deaktivierte Pflicht-Entities nicht: ewiger ConfigEntryNotReady-Retry mit irreführender Meldung, kein Repair-Issue**

- **Fundstelle:** `custom_components/poise/__init__.py:117` — `async_setup_entry`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** Falsche Annahme über HA-Core-Verhalten: 'kein State' wird ausschließlich als 'noch nicht geladen' interpretiert; der Kommentar dokumentiert ein Verhalten, das der Code nicht leisten kann
- **Codebeleg:** __init__.py:117-122: `missing = [entry.data[k] for k in (CONF_TEMP_SENSOR, CONF_ACTUATOR) if hass.states.get(entry.data[k]) is None]\nif missing: raise ConfigEntryNotReady(f"required entity not available yet: {missing}")`

**Befund:** Dimension: room-setup. Eine im Entity-Register deaktivierte Entity (disabled_by gesetzt — üblich beim Gerätetausch oder wenn der Nutzer den TRV-eigenen Klima-Eintrag deaktiviert) hat dauerhaft KEINEN State: hass.states.get liefert für immer None. Der Kommentar Z.112-115 behauptet, der Guard decke nur den Fall 'may load after us' ab — der Code kann aber nicht zwischen 'lädt gleich noch' und 'ist permanent deaktiviert' unterscheiden. Es fehlt der Registry-Check (er.async_get(hass).async_get(entity_id).disabled_by), um in diesem Fall einen klaren, permanenten Fehler (ConfigEntryError/Repair-Issue) statt einer Endlos-Retry-Schleife zu erzeugen. Die NotReady-Meldung 'not available yet' ist dann faktisch falsch — es wird nie verfügbar.

**Mögliches Fehlverhalten im Realbetrieb:** Der Raum-Entry hängt dauerhaft in 'Wird erneut versucht' mit einer Meldung, die Besserung suggeriert; die Zone wird nie geregelt, und der Nutzer bekommt keinen Hinweis auf die eigentliche Ursache (deaktivierte Entity). Setup-Robustheit/Diagnostizierbarkeit, kein aktiver Realbetriebsschaden.

**Minimaler Reproduktionsfall / Testidee:** Raum-Entry einrichten; danach die Aktor-Climate-Entity im Entity-Register deaktivieren; HA neu starten → Entry loopt für immer in SETUP_RETRY mit 'required entity not available yet: [climate.x]'; kein Repair-Issue, kein Hinweis auf disabled_by.

**Zur Absicherung nötig:** Keiner für den Mechanismus (disabled Entities haben in HA keinen State); nur Produktentscheidung, ob deaktivierte Pflicht-Entity als permanenter Fehler oder Retry behandelt werden soll.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9) (Schweregrad korrigiert → niedrig): Mechanismus bestätigt, Severity abgestuft. Belege: (1) __init__.py:116-122 prüft nur hass.states.get(...) is None und wirft ConfigEntryNotReady("required entity not available yet") — kein disabled_by-Registry-Check (einzige er-Zugriffe: config_flow.py:174/266, __init__.py:342). (2) HA-Annahmen des Findings stimmen, gegen HA core 2025.1.0 verifiziert: entity_platform.py:895-903 bricht das Hinzufügen registry-deaktivierter Entities ab (add_to_platform_abort) → hass.states.get() liefert dauerhaft None; config_entries.py:537-545 retryt NotReady end […]
- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): Mechanismus verifiziert: custom_components/poise/__init__.py:116-122 prüft nur `hass.states.get(entry.data[k]) is None` und wirft ConfigEntryNotReady("required entity not available yet"). Eine registry-deaktivierte Entity (disabled_by gesetzt) hat in HA dauerhaft keinen State, also loopt der Entry für immer in SETUP_RETRY mit einer faktisch falschen "yet"-Meldung. […]

---

### AR-34 · niedrig *(Erst-Einstufung: mittel)* · begründeter Verdacht

**Korrupter/unvollständiger Raum-Entry crasht mit KeyError/ValueError in Guard und Koordinator-Konstruktor → dauerhafter SETUP_ERROR ('Unknown error') statt kontrolliertem Fehlerpfad**

- **Fundstelle:** `custom_components/poise/__init__.py:118` — `async_setup_entry`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** Trust-Boundary: entry.data wird als garantiert wohlgeformt behandelt, obwohl es persistierter, migrierter und extern editierbarer Zustand ist; Validierung existiert nur im Config-Flow, nicht am Setup-Eingang
- **Codebeleg:** __init__.py:118-119: `entry.data[k] for k in (CONF_TEMP_SENSOR, CONF_ACTUATOR)` — harter Key-Zugriff; ebenso coordinator.py:325 `self.zone_name: str = data[CONF_NAME]`, coordinator.py:331-332, coordinator.py:354 `Category(data.get(CONF_CATEGORY, "II"))` und diverse bare float(...)-Casts (z.B. Z.347, 356, 401-415)

**Befund:** Dimension: room-setup. Jeder Entry OHNE entry_type=='system' nimmt den Raum-Zweig (_is_system, __init__.py:33-34) — also auch ein korrupter Entry, ein von Hand editierter Store oder ein Alt-Entry, dem temp_sensor/actuator/name fehlen. Der Guard greift mit entry.data[k] hart zu (KeyError), der Konstruktor zusätzlich mit data[CONF_NAME] und ungeprüften float(...)/Category(...)-Konvertierungen (ValueError bei ungültigem Kategorie-String in options). Diese Exceptions sind KEIN ConfigEntryNotReady/ConfigEntryError: HA-Core fängt sie generisch und setzt den Entry permanent auf SETUP_ERROR mit nichtssagender Log-Zeile — kein Retry, kein actionabler Hinweis, kein Repair-Issue. Der Konstruktor läuft VOR der NotReady-Konvertierung von async_config_entry_first_refresh, wird also nie in einen Retry übersetzt.

**Mögliches Fehlverhalten im Realbetrieb:** Setup-Robustheit: ein einzelner defekter Wert im Config-Entry-Store (z.B. nach fehlgeschlagener Migration oder Handedit) macht die Zone dauerhaft unbrauchbar mit 'Unknown error occurred'; die Ursache ist nur aus dem Traceback erratbar. Kein aktiver Regelbetriebsschaden.

**Minimaler Reproduktionsfall / Testidee:** In .storage/core.config_entries beim Poise-Raum-Entry den Key 'temp_sensor' entfernen (oder in options 'category': 'IV-invalid' setzen), HA starten → KeyError in __init__.py:118 (bzw. ValueError in coordinator.py:354) → Entry-Status SETUP_ERROR, kein Retry.

**Zur Absicherung nötig:** Keiner; das HA-Core-Verhalten (generische Exception in async_setup_entry → SETUP_ERROR, kein Retry) ist stabil dokumentiert.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85) (Schweregrad korrigiert → niedrig): Mechanismus vollständig verifiziert: __init__.py:116-120 greift mit entry.data[k] hart auf CONF_TEMP_SENSOR/CONF_ACTUATOR zu (KeyError vor dem ConfigEntryNotReady-Raise Z.122); der Koordinator-Konstruktor (Z.124, vor async_config_entry_first_refresh Z.126) hat weitere harte Zugriffe: coordinator.py:325 data[CONF_NAME], 331-332 data[CONF_TEMP_SENSOR]/[CONF_ACTUATOR], 354 Category(...) mit Enum nur I/II/III (comfort/en16798.py:23-25, ValueError sonst) sowie bare float(...)-Casts (346-348, 355-357, 400-415). Kein try/except, kein Repair-Issue. […]
- **bestätigt** (Konfidenz 0.92) (Schweregrad korrigiert → niedrig): Faktisch bestätigt, aber Severity übertrieben. Alle zitierten Stellen stimmen: __init__.py:116-119 greift mit entry.data[k] hart auf CONF_TEMP_SENSOR/CONF_ACTUATOR zu (KeyError VOR dem ConfigEntryNotReady-Raise in Z.122); coordinator.py:325 `self.zone_name: str = data[CONF_NAME]`, 331-332 harte Zugriffe, 354 `Category(data.get(CONF_CATEGORY,"II"))` mit Enum {I,II,III} (en16798.py:23-25 → ValueError bei jedem anderen String), bare float()-Casts bei 346-348/355-357/400-415. […]

---

### AR-35 · niedrig · begründeter Verdacht

**Boiler-Reconcile stempelt last_switch_mono=now auch beim Adoptieren von real=OFF — nach jedem Neustart/Reload blockiert min_off (Default 300 s, bis 3600 s) das erste Einschalten, auch für den Frost-Override; F8-Kommentar begründet nur den ON-Fall**

- **Fundstelle:** `custom_components/poise/hub_coordinator.py:265` — `PoiseHubCoordinator._actuate`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** Kommentar-vs-Code: F8 begründet den Zeitstempel nur mit min-on-Schutz eines LAUFENDEN Kessels; der Code erzeugt zusätzlich eine unbegründete min-off-Sperre für den AUS-Fall
- **Codebeleg:** hub_coordinator.py:260-271: `if real is not None:\n    # F8: stamp the switch time to NOW when adopting the real boiler state at startup, so min-on protects it — ...\n    self._boiler = BoilerState(on=real, last_switch_mono=now, ...)` — hub_aggregate.py:185-187 (gate_min_cycle): `return elapsed >= min_off_s`

**Befund:** Dimension: hub-setup. Der F8-Kommentar rechtfertigt den now-Stempel ausschließlich für 'adopting the real boiler state ... so min-on protects it' (physisch laufender Kessel darf nicht sofort abgeschaltet werden — korrekt). Der Code stempelt aber symmetrisch AUCH bei real=False: BoilerState(on=False, last_switch_mono=now). Danach läuft jede ON-Anforderung durch gate_min_cycle (hub_aggregate.py:245-252), und elapsed >= min_off_s ist für 300 s (DEFAULT_BOILER_MIN_OFF_S, const.py:152) falsch — der Kessel, der womöglich seit Stunden aus ist, darf 5 Minuten nicht einschalten. Das gilt auch für frost_override-Demand, da das min-cycle-Gate NACH der Demand-Entscheidung greift. Ohne Reconcile (Boiler-Entity unlesbar) gälte der Default last_switch_mono=-1.0e9 und ON käme sofort.

**Mögliches Fehlverhalten im Realbetrieb:** Nach jedem Neustart/Reload mit lesbarem, ausgeschaltetem Boiler-Entity verzögert sich das erste Heizen um bis zu min_off (Default 5 min, konfigurierbar bis 3600 s = 1 h). Bei min_off=3600 wartet auch ein Frost-Override eine Stunde. Physisch meist unkritisch (thermische Trägheit), aber undokumentiert und für den Frost-Pfad bei großem min_off unangenehm.

**Minimaler Reproduktionsfall / Testidee:** Hub mit ON/OFF-Actions auf switch.boiler (state 'off'), min_off=600. Zonen heizen (Demand aktiv). HA neu starten. Erster Hub-Tick: reconcile → on=False, last_switch=now; step_boiler: desired=True, gate_min_cycle: elapsed=0 < 600 → kein ON. ON kommt erst nach 10 min, obwohl der Kessel schon lange aus war.

**Zur Absicherung nötig:** Ist der symmetrische now-Stempel eine bewusste Worst-Case-Annahme ('Kessel könnte gerade eben selbst abgeschaltet haben')? Falls ja, gehört das in den F8-Kommentar; falls nein, sollte der OFF-Adopt den Default -1e9 (oder now-min_off) behalten.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Alle Kernbehauptungen durch Code-Lektüre belegt: (1) hub_coordinator.py:260-271 stempelt last_switch_mono=now unverzweigt für real=True UND real=False (reconcile_boiler_on("off")→False, hub_aggregate.py:507-509); (2) gate_min_cycle hub_aggregate.py:187 `return elapsed >= min_off_s` blockiert das erste ON für min_off (Default 300 s, const.py:152; bis 3600 s per config_flow.py:376-377); (3) frost_override wird nur in demand.active gefaltet (hub_aggregate.py:159) und läuft ohne Bypass durch dasselbe Gate; (4) Reconcile-Stempel fällt auf den ersten […]
- **bestätigt** (Konfidenz 0.93): Widerlegungsversuch fehlgeschlagen — das Finding ist in allen Kernaussagen korrekt und wurde zusätzlich dynamisch bestätigt.

BELEGE (Code-Lektüre):
1. Symmetrischer Stempel: hub_coordinator.py:260-271 — `if real is not None: self._boiler = BoilerState(on=real, last_switch_mono=now, ...)`. Der Stempel gilt für real=True UND real=False; `reconcile_boiler_on` (hub_aggregate.py:507-509) liefert für state "off" explizit False (`return state != "off"`), der OFF-Adopt-Pfad ist also bei lesbarem, ausgeschaltetem Boiler-Entity immer erreichbar (kein Gu […]

---

### AR-36 · niedrig · Verbesserungsvorschlag

**async_migrate_entry: version>2-Guard ist in unterstütztem HA toter Code (Core übernimmt den Refusal); Migration setzt minor_version nie — bei künftigem Minor-Bump/Downgrade läuft die Migration bei jedem Start erneut**

- **Fundstelle:** `custom_components/poise/__init__.py:158` — `async_migrate_entry`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** Docstring behauptet eine Schutzfunktion, die der Core übernimmt; options vs data: die Re-Migration re-splittet data/options erneut — nur die (ungetestete) Idempotenz verhindert Drift
- **Codebeleg:** __init__.py:158-159: `if entry.version > 2:\n        return False` — __init__.py:163-165: `hass.config_entries.async_update_entry(entry, data=new_data, options=new_options, version=2)` — minor_version fehlt

**Befund:** Unabhängig gefunden von 2 Reviewern (Dimensionen: migration, ha-api; letzterer verifizierte config_entries.py 2025.1.0, ConfigEntry.async_migrate Z.964-966). (a) Seit HA 2024.1 prüft der Core selbst auf Future-Versionen: bei entry.version > handler.VERSION wird der Entry mit MIGRATION_ERROR abgelehnt, OHNE async_migrate_entry aufzurufen — mit min. HA 2025.1.0 (hacs.json:3) ist der Guard unerreichbar; der Docstring-Anspruch 'A future (>2) schema is refused, not downgraded' (Z.156) wird faktisch vom Core erfüllt, nicht von diesem Code. (b) Der Core-Vergleich auf minor_version ist ein Gleichheits-, kein <=-Vergleich: jeder Entry mit version==2 und minor_version!=1 (nach Downgrade von einer künftigen Poise-Version mit MINOR_VERSION=2) landet bei JEDEM Start wieder in async_migrate_entry; async_update_entry bumpt nur version=2, nie minor_version → die Migration läuft dauerhaft erneut (nach Code-Analyse idempotent — V2-Split reproduziert sich, _as_list lässt Listen durch — aber ungetestet und unbeabsichtigt) mit irreführendem Migrations-Log bei jedem Neustart. Hub-Pfad (migration.py:82-83 pass-through) verliert nichts.

**Mögliches Fehlverhalten im Realbetrieb:** Kein Realbetriebsschaden heute. Risiko erst bei künftigem MINOR_VERSION-Bump bzw. Downgrade: Schein-Migration bei jedem Start, nie konvergierende minor_version, Docstring behauptet eine Schutzfunktion, die der eigene Code nie ausführt.

**Minimaler Reproduktionsfall / Testidee:** Entry-Storage mit version=2, minor_version=2 präparieren (simulierter Downgrade), HA starten: async_migrate_entry läuft, Guard greift nicht (version==2), migrate_room_entry läuft erneut, minor_version bleibt 2 → nach jedem Neustart identisch, jeweils mit 'migrated config entry ... to schema version 2'-Log.

**Zur Absicherung nötig:** Keiner für den Ist-Zustand; für den Zukunftsfall die geplante Minor-Migrationsstrategie. Fix: async_update_entry(..., version=2, minor_version=1) und die Split-Migration hinter `if entry.version == 1:` legen.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9): GETEILTES ERGEBNIS — der actionable Kern ist bestätigt, die Kernbegründung (a) ist widerlegt. (a) WIDERLEGT: Die Behauptung, der Core lehne Future-Versionen ab, OHNE async_migrate_entry aufzurufen, ist für HA 2025.1.0 (hacs.json-Minimum) und 2026.1.0 nachweislich falsch. Die zitierten Z.964-966 sind der Gleichheits-Fast-Path (`same_major_version = self.version == handler.VERSION; if same_major_version and self.minor_version == handler.MINOR_VERSION: return True`), kein Refusal. […]
- **bestätigt** (Konfidenz 0.9): Gemischtes Ergebnis, Kern des Findings bestätigt, Begründung (a) widerlegt. (a) WIDERLEGT: Die Behauptung, der version>2-Guard sei in unterstütztem HA toter Code, ist falsch. HA Core 2025.1.0 ConfigEntry.async_migrate Z.964-966 ist nur der Up-to-date-Shortcut ('same_major_version = self.version == handler.VERSION; if same_major_version and self.minor_version == handler.MINOR_VERSION: return True'); danach ruft der Core bei JEDER Abweichung — auch entry.version > handler.VERSION — direkt component.async_migrate_entry auf (Z.983). […]

---

### AR-37 · niedrig · sicherer Fehler

**Stale Modul-Docstring in binary_sensor.py: 'Poise does not switch any boiler in this stage' und 'across all zones' widersprechen dem ausgeführten Code (S2-Aktuation implementiert; Aggregation ist controls_boiler-only)**

- **Fundstelle:** `custom_components/poise/binary_sensor.py:4` — `Modul-Docstring (PoiseBoilerDemand-Plattform)`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** diagnostic-only vs live: Die Datei deklariert die gesamte Stufe als diagnostisch, obwohl der zugrunde liegende Coordinator (opt-in) live aktuiert
- **Codebeleg:** binary_sensor.py:3-5: "It reflects the aggregated call-for-heat across all zones and is **diagnostic only** — Poise does not switch any boiler in this stage (shadow; actuation is S2, opt-in)." — dagegen hub_coordinator.py:361-362: `if self._actuation:\n    await self._actuate(demand.active, now)` — und hub_aggregate.py:133: `participating = [r for r in requests if r.controls_boiler]`

**Befund:** Dimension: hub-setup. Der Docstring beschreibt den Stand S1 (Shadow) als aktuellen Zustand ('in this stage'). Tatsächlich ist S2 ausgeliefert: Sind beide Boiler-Actions konfiguriert (hub_coordinator.py:107-109), schaltet derselbe Coordinator, dessen Daten diese Entity anzeigt, den Kessel real — inklusive Keepalive-Re-Assert alle 300 s. Zusätzlich ist 'across all zones' falsch: aggregate_boiler_demand wertet nur controls_boiler-Zonen (hub_aggregate.py:133-136). Die Entity-Eigenschaft selbst (EntityCategory.DIAGNOSTIC, Z.64) ist korrekt — falsch ist die Behauptung, Poise schalte 'in this stage' keinen Boiler.

**Mögliches Fehlverhalten im Realbetrieb:** Reviewer/Beitragende, die die Plattformdatei lesen, halten den Hub für rein passiv und übersehen, dass hinter derselben Coordinator-Instanz ein aktorischer Pfad mit blockierenden Service-Calls liegt. Keine Laufzeitwirkung.

**Minimaler Reproduktionsfall / Testidee:** Doku-vs-Code-Vergleich: binary_sensor.py:1-6 lesen, dann hub_coordinator.py:352-375 (_async_update_data ruft _actuate) und hub_aggregate.py:133. Hub mit ON/OFF-Actions konfigurieren → Boiler wird geschaltet, während der Docstring das Gegenteil behauptet.

**Zur Absicherung nötig:** Keiner — rein textuell belegbar. Fix: Docstring auf 'S1 shadow / S2 opt-in actuation via hub_coordinator' und 'controls_boiler zones' präzisieren.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Beide Docstring-Behauptungen widersprechen dem Code nachweislich. (1) "Poise does not switch any boiler in this stage": hub_coordinator.py:361-362 aktuiert real (`if self._actuation: await self._actuate(demand.active, now)`), Opt-in via beider Actions (hub_coordinator.py:107-109), Keepalive-Default 300 s (const.py:150). […]
- **bestätigt** (Konfidenz 0.85): Alle Code-Zitate exakt verifiziert: binary_sensor.py:3-5 (Docstring verbatim), hub_coordinator.py:107-109 (_actuation aus beiden geparsten Actions), hub_coordinator.py:361-362 (`if self._actuation: await self._actuate(demand.active, now)`), hub_aggregate.py:133 (`participating = [r for r in requests if r.controls_boiler]`), Keepalive 300 s (const.py:150). […]

---

### AR-38 · niedrig · sicherer Fehler

**safety/sensor_watchdog.py-Moduldocstring behauptet, der Frozen-Sensor-Pfad verändere den Regelausgang nicht ('without altering the control output') — der Coordinator ersetzt bei frozen Ziel UND Modus**

- **Fundstelle:** `custom_components/poise/safety/sensor_watchdog.py:6` — `(Moduldocstring) vs PoiseCoordinator._run_once`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** advisory/diagnostic (laut Docstring) vs live Safety-Aktuation (tatsächlicher Code): die Doku deklariert einen Live-Safety-Pfad als wirkungslos
- **Codebeleg:** sensor_watchdog.py:6-7: 'We detect it ... and react *advisorily* — raise a repair issue and pause learning — without altering the control output (no new control risk).' — vs coordinator.py:1599-1609: `if frozen: ... target = frozen_safe_target(FROST_FLOOR_C, mold_min); mode = "heat"` (bzw. mode = "off" für cool-only)

**Befund:** Dimension: boundaries. Der Modul-Header beschreibt den Watchdog als rein advisorisch (Issue + Lernpause). Tatsächlich greift der Frozen-Zustand massiv in den Regelausgang ein: coordinator.py:1599-1610 ersetzt das Komfortziel durch den Health-Floor und erzwingt heat/off; frozen bypasst außerdem den Regulation-Throttle (coordinator.py:1866) und unterdrückt das Override-Clamp-Flag (1598). Das neuere Verhalten ist in frozen_safe_target (sensor_watchdog.py:76-86) korrekt dokumentiert — der Modul-Header wurde beim C3/Ü3-Umbau nicht nachgezogen und widerspricht der eigenen Datei.

**Mögliches Fehlverhalten im Realbetrieb:** Kein Laufzeitschaden; aber der Header verharmlost einen aktiven Safety-Eingriff. Wer auf Basis des Docstrings reviewt oder erweitert (z.B. den Frozen-Schwellwert lockert), unterschätzt die Regelwirkung des Watchdogs (Sollwertersetzung + Modenzwang am Aktor).

**Minimaler Reproduktionsfall / Testidee:** Vergleich sensor_watchdog.py:1-8 mit coordinator.py:1599-1610 (Nutzung von is_frozen aus _emit_health_issues, Z.1118, und frozen_safe_target).

**Zur Absicherung nötig:** Keiner — reiner Doku/Code-Widerspruch innerhalb des Repos.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.95): Alle Zitate verifiziert. sensor_watchdog.py:5-7 behauptet, der Frozen-Pfad reagiere "advisorily ... without altering the control output (no new control risk)". Tatsächlich ersetzt coordinator.py:1599-1610 bei frozen das Ziel durch frozen_safe_target(FROST_FLOOR_C, mold_min) und erzwingt mode="heat" (bzw. "off" bei cool-only); zusätzlich bypasst frozen den Regulation-Throttle (coordinator.py:1866, "and not frozen") und unterdrückt das Override-Clamp-Flag (Z.1598). […]
- **bestätigt** (Konfidenz 0.95): Doku/Code-Widerspruch verifiziert. Moduldocstring sensor_watchdog.py:5-7 behauptet wörtlich "react *advisorily* — raise a repair issue and pause learning — without altering the control output (no new control risk)". Tatsächlich ist der Frozen-Zustand regelwirksam: coordinator.py:1118 berechnet frozen via is_frozen in _emit_health_issues, _run_once entpackt es (Z.1261-1262) und (1) ersetzt bei frozen den Sollwert durch frozen_safe_target(FROST_FLOOR_C, mold_min) und erzwingt mode="heat" bzw. […]

---

### AR-39 · niedrig · sicherer Fehler

**ADR-0038 beschreibt eine nicht existierende Architektur: In-Memory-Registry hass.data[DOMAIN]['hub'] (Push) und ResourceRelease-Rückkanal — Code macht Pull über entry.runtime_data, ResourceRelease ist toter Contract**

- **Fundstelle:** `custom_components/poise/contracts.py:164` — `ZoneRequest (Docstring) / PoiseHubCoordinator._collect_requests`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** Doku-vs-Code: ADR als 'Implementiert' markiert für eine Mechanik, die der Code nicht hat
- **Codebeleg:** contracts.py:164: "Each zone writes this at the end of Phase 1 into the shared registry; the hub resolves shared resources ... the hub replies with a :class:`ResourceRelease` cap, not a write."

**Befund:** Dimension: docs-vs-code. ADR-0038 Entscheidung 1 ('schreibt am Tick-Ende eine frozen ZoneRequest in eine In-Memory-Registry hass.data[DOMAIN]["hub"]' ... 'schreibt je Zone eine ResourceRelease zurück') und der contracts.py-Docstring behaupten ein Push-Registry-Modell. Tatsächlich: grep 'hass.data' über die gesamte Integration = 0 Treffer; die Zonen bauen nie ein ZoneRequest — der HUB pullt das rohe coordinator.data-Dict jeder Zone aus entry.runtime_data und baut die Requests selbst (hub_coordinator.py:136-176, zone_request_from_data). ResourceRelease (contracts.py:187-199) wird nirgends erzeugt oder konsumiert — auch nicht als Shadow. Der ADR-Status deklariert S0–S2 als 'live', die beschriebene Registry-/Release-Mechanik existiert in keiner Stufe.

**Mögliches Fehlverhalten im Realbetrieb:** Kein Laufzeitschaden (der Pull-Ansatz ist funktional gleichwertig und über mono_ts stale-sicher), aber Architektur-Doku und Datenvertrags-Docstring führen Reviewer/Contributor in die Irre; toter Contract-Code suggeriert einen Rückkanal, den Zonen nie lesen.

**Minimaler Reproduktionsfall / Testidee:** grep -rn 'hass.data' custom_components/poise/ → leer; grep -rn 'ResourceRelease' → nur contracts.py:167/187. Vergleich mit ADR-0038 Entscheidung 1 und contracts.py:164.

**Zur Absicherung nötig:** Keiner. Entweder ADR-0038 um einen Umsetzungs-Nachtrag ergänzen (Pull statt Registry; ResourceRelease erst ab S3/S4) oder Docstring/Contract anpassen. Nebenbefund ohne Widerspruch: frontend/__init__.py registriert wirklich nur StaticPathConfig + add_extra_js_url — konsistent mit ADR-0040/README.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.93): Bestätigt nach aktivem Widerlegungsversuch. Belege: (1) Grep 'hass\.data' über custom_components/poise/ = 0 Treffer, obwohl ADR-0038 Z.12 eine "In-Memory-Registry hass.data[DOMAIN][\"hub\"]" und Z.24 deren Unload-Bereinigung beschreibt. (2) Zonen bauen nie ein ZoneRequest: einzige produktive Konstruktion ist hub_aggregate.py:86 in zone_request_from_data, aufgerufen nur vom Hub (hub_coordinator.py:162-175), der per Pull `getattr(e, "runtime_data", None)` → `coord.data` (Z.142-143) das rohe Zonen-Dict liest — der Docstring contracts.py:164 ("Each […]
- **bestätigt** (Konfidenz 0.95): Widerlegung fehlgeschlagen; alle Kernbehauptungen verifiziert. (1) Zitat/Zeile korrekt: contracts.py:164-167 behauptet im Präsens ein Push-Registry-Modell ("Each zone writes this ... into the shared registry ... hub replies with a ResourceRelease cap"). (2) grep 'hass.data' über custom_components/poise/ = 0 Treffer — hass.data[DOMAIN]["hub"] existiert nicht. (3) Pull statt Push: hub_coordinator.py:136-176 (_collect_requests) iteriert config_entries, pullt entry.runtime_data (Z. 142) und baut ZoneRequest selbst via zone_request_from_data (Z. […]

---

### AR-40 · niedrig · sicherer Fehler

**ADR-0007 verspricht Debounce-Persistenz ('schreibt nur bei echter Änderung', async_call_later, BT-Muster) und eine _check_entities_ready-Warteschleife — Code hat Counter-Throttle alle 30 Ticks und nur einen Existenz-Check**

- **Fundstelle:** `custom_components/poise/coordinator.py:1028` — `_maybe_save`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** Doku-vs-Code: ADR-Entscheidungstext beschreibt einen anderen Mechanismus als den ausgeführten
- **Codebeleg:** coordinator.py:1028-1032: `self._save_counter += 1\nif self._save_counter >= EKF_SAVE_EVERY_TICKS or self._dirty:\n    ...\n    await self._store.save(self._save_payload())`

**Befund:** Dimension: docs-vs-code. ADR-0007 Entscheidung Punkt 4: 'Throttle = Debounce (BT-Muster: async_call_later, dirty-tracked, Flush bei HOMEASSISTANT_STOP) — schreibt nur bei echter Änderung.' Der Code implementiert stattdessen exakt das im selben ADR als schwächer klassifizierte ThermoSmart-Muster ('Count-throttled, kein Debounce'): unbedingter Save alle EKF_SAVE_EVERY_TICKS=30 Ticks (const.py:129), dirty nur als Beschleuniger. Punkt 3 verspricht zusätzlich BTs '_check_entities_ready-Loop (auf Sensoren/TRVs warten)'; der Code prüft nur die EXISTENZ der Entities (__init__.py:117-122) — ein vorhandenes, aber unavailable Entity passiert das Setup (der A2-Kommentar in __init__.py:113-115 dokumentiert das ehrlich, der ADR nicht). Positiv verifiziert: Flush bei Stop (F7), ekf_version + Korruptions-Recovery, Store-Remove beim Delete, V1→V2-Migration inkl. Hub-Passthrough.

**Mögliches Fehlverhalten im Realbetrieb:** Kein Lernverlust (Flush-on-Stop existiert), aber die dokumentierte Persistenz-Garantie 'schreibt nur bei echter Änderung' ist falsch: alle 30 min ein unbedingter Flash-Write pro Zone unabhängig von Änderung. Bei vielen Zonen dauerhafte, vermeidbare Storage-Writes; vor allem irreführende Doku für Reviewer.

**Minimaler Reproduktionsfall / Testidee:** Zone ohne jede Zustandsänderung 30 Ticks laufen lassen → _maybe_save schreibt den Store trotz identischem Payload (kein Dirty-Vergleich, kein Debounce-Timer im gesamten Coordinator; grep 'async_call_later' im Persistenz-Pfad = leer).

**Zur Absicherung nötig:** ADR-0007 ist als 'In Arbeit (75 %)' markiert — möglich, dass Debounce/Ready-Loop bewusst offener Rest sind; dann gehört der Delta-Stand in den ADR.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Docs-vs-Code-Diskrepanz zeilengenau bestätigt. (1) ADR-0007:22 verspricht "Throttle = Debounce (BT-Muster: async_call_later, dirty-tracked) — schreibt nur bei echter Änderung"; der Code (custom_components/poise/coordinator.py:1026-1032) implementiert stattdessen das im selben ADR (Z.15) als schwächer klassifizierte Count-Throttle-Muster: `if self._save_counter >= EKF_SAVE_EVERY_TICKS or self._dirty` mit EKF_SAVE_EVERY_TICKS=30 (const.py:129), dirty nur als Beschleuniger; grep async_call_later/schedule_save/Debouncer im Persistenzpfad = leer; st […]
- **bestätigt** (Konfidenz 0.9): Docs-vs-Code-Abweichung real und belegt. (1) ADR-0007 Z. 22 verspricht Debounce-Persistenz ("BT-Muster: async_call_later, dirty-tracked ... schreibt nur bei echter Änderung"); coordinator.py:1026-1032 implementiert stattdessen den Counter-Throttle `if self._save_counter >= EKF_SAVE_EVERY_TICKS or self._dirty` mit unbedingtem Store-Write alle 30 Ticks (const.py:129, Tick=60 s → ~30 min) — exakt das im selben ADR (Z. 15) als schwächer klassifizierte ThermoSmart-Muster. […]

---

### AR-41 · niedrig · Testlücke

**Testlücke Setup-Guard: die Variante 'Temperatursensor fehlt, Aktuator existiert' und der Degraded-Pfad 'Sensor existiert-aber-unavailable → Setup lädt' sind ungetestet**

- **Fundstelle:** `tests/integration/test_setup_and_cycle.py:100` — `test_setup_retry_when_actuator_missing`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** measured vs estimated: der Guard trennt 'Entity fehlt' (Retry) von 'Entity unavailable' (Degraded-Regelung); nur eine Seite einer Guard-Hälfte ist getestet
- **Codebeleg:** tests/integration/test_setup_and_cycle.py:100-111: `# only the room sensor exists; the actuator entity is not yet available\nhass.states.async_set("sensor.room_temp", "20", {"device_class": "temperature"})`

**Befund:** Dimension: test-gap. Der einzige ConfigEntryNotReady-Test setzt den Temperatursensor und lässt den Aktuator fehlen — real getestet über hass.config_entries.async_setup mit SETUP_RETRY-Assert. Für das Spiegel-Szenario (Aktuator existiert, Sensor fehlt) gibt es keinen Test. Der Guard (__init__.py:117-122) iteriert zwar über beide Keys mit demselben Ausdruck, sodass das Risiko heute gering ist; aber weil entry.data[k] ein harter Key-Zugriff ist (KeyError statt ConfigEntryNotReady bei Alt-Entry ohne Key) und der Kommentar __init__.py:113-115 verspricht, dass ein existierender-aber-unavailable Sensor den Guard passiert (Degraded-Pfad statt Retry), sind beide Randfälle unbelegt.

**Mögliches Fehlverhalten im Realbetrieb:** Eine Regression, die die Guard-Liste auf den Aktuator verengt (oder den Sensor-Key umbenennt), ließe einen Raum ohne Temperatursensor in SETUP_ERROR statt SETUP_RETRY laufen (kein automatischer Retry, Zone dauerhaft tot bis zum manuellen Reload) — der bestehende Test bliebe grün.

**Minimaler Reproduktionsfall / Testidee:**

```python
# tests/integration/test_setup_and_cycle.py
async def test_setup_retry_when_temp_sensor_missing(hass: HomeAssistant) -> None:
    """Aktuator existiert, Temperatursensor fehlt -> ConfigEntryNotReady/SETUP_RETRY."""
    hass.states.async_set(
        "climate.trv", "heat",
        {"hvac_modes": ["heat", "off"], "temperature": 18.0, "current_temperature": 19.0},
    )  # NUR der Aktuator; sensor.room_temp wird nie gesetzt
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY

async def test_setup_loads_with_unavailable_sensor(hass: HomeAssistant) -> None:
    """Kommentar __init__.py:113-115: existiert-aber-unavailable passiert den Guard."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _set_room_and_actuator(hass, room=19.5, sp=18.0)
    hass.states.async_set("sensor.room_temp", "unavailable", {})  # existiert, aber tot
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=ROOM_DATA, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED  # Degraded-Pfad, kein Retry
```

**Zur Absicherung nötig:** Keiner.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.88): Beide Testlücken real: (1) Einziger ConfigEntryNotReady/SETUP_RETRY-Test im gesamten tests/-Baum ist test_setup_and_cycle.py:100-111 und testet nur "Sensor da, Aktuator fehlt"; das Spiegel-Szenario fehlt (Grep-Beleg). (2) Kein Test setzt den Sensor VOR async_setup auf unavailable — test_review_v083_fixes.py:202/221 und test_glue_coverage2.py:106-113 flippen erst nach erfolgreichem Setup; das in __init__.py:113-115 dokumentierte Degraded-Setup-Verhalten ist unbelegt. […]
- **bestätigt** (Konfidenz 0.9): Testlücke real und Zitat korrekt. (1) Grep über tests/ nach SETUP_RETRY|ConfigEntryNotReady trifft nur test_setup_and_cycle.py:100-111 (test_setup_retry_when_actuator_missing, setzt nur sensor.room_temp, Z.103) — das Spiegel-Szenario 'Aktuator existiert, Sensor fehlt' ist nirgends getestet. (2) Der vom Kommentar __init__.py:112-115 versprochene Degraded-Pfad 'existiert-aber-unavailable passiert den Guard → Setup lädt' ist an der Setup-Boundary ungetestet: alle unavailable-Tests (test_glue_coverage2.py:101-161, test_review_v083_fixes.py:196ff.)  […]

---

### AR-42 · niedrig · Testlücke

**Testlücke Remove-Fehlerpfade Raum: Aktor fehlt/unavailable und werfender Park-Service-Call ungetestet — Store-/Trace-Cleanup nach geschlucktem Park-Fehler unbelegt**

- **Fundstelle:** `custom_components/poise/__init__.py:330` — `_execute_park / _remove_room_entry`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** pure function vs HA-Seiteneffekt: resolve_park_command ist pure getestet, aber die HA-Seiteneffekt-Kette dahinter (Service-Dispatch-Fehler → Rest-Cleanup) nur im Happy Path
- **Codebeleg:** __init__.py:330-331: `except Exception:  # noqa: BLE001 - park on delete is best-effort\n    logging.getLogger(__name__).exception("Poise: actuator park on removal failed")`

**Befund:** Dimension: test-gap. Die Raum-Remove-Happy-Paths sind real getestet (test_lifecycle_review.py:62-98: Heat-Park mit Frost-Floor-Assert, Cool-only→off, Valve→0.0, echtes async_remove_entry, echter Store-Delete-Assert). Ungetestet: (1) Aktuator-Entity existiert nicht mehr (Integration bereits entfernt) — st is None → modes=[] → ParkPlan('climate','off') → set_hvac_mode auf nicht registrierte climate-Domain wirft ServiceNotFound SYNCHRON (auch bei blocking=False), gefangen nur vom breiten except Z.330; (2) dass NACH einem geschluckten Park-Fehler _restore_trv_internal, Store-Delete (:294-295) und Trace-Delete (:296-299) trotzdem laufen. Hinweis: die Park-Calls nutzen blocking=False, Handler-Exceptions kämen ohnehin nie im try an — nur ServiceNotFound ist der real erreichbare Fehler, und genau der ist unsimuliert.

**Mögliches Fehlverhalten im Realbetrieb:** Regressiert das except (oder rutscht der Store-Cleanup hinter einen propagierenden Fehler), hinterlässt das Löschen eines Raums mit bereits entfernter TRV-Integration einen verwaisten EKF-Store und ein verwaistes Trace-File; HA schluckt die Exception aus async_remove_entry, der Nutzer sieht nichts.

**Minimaler Reproduktionsfall / Testidee:**

```python
# tests/integration/test_lifecycle_review.py
async def test_room_remove_with_gone_actuator_still_cleans_up(hass: HomeAssistant) -> None:
    """TRV-Integration schon deinstalliert: kein climate-Service registriert,
    kein Actuator-State -> Park wirft ServiceNotFound, Cleanup muss trotzdem laufen."""
    # BEWUSST kein async_mock_service und kein hass.states.async_set für climate.trv
    entry = _room_entry(hass)
    await PoiseStore(hass, entry.entry_id).save({"ekf_version": 1, "n_heating": 3})

    await async_remove_entry(hass, entry)  # darf nicht raisen

    # der Park-Fehler war best-effort — Modell + Trace sind trotzdem weg
    assert await PoiseStore(hass, entry.entry_id).load() is None

async def test_room_remove_park_service_error_does_not_block_cleanup(hass) -> None:
    async def _boom(call: ServiceCall) -> None:
        raise HomeAssistantError("TRV gateway offline")
    hass.services.async_register("climate", "set_hvac_mode", _boom)
    hass.services.async_register("climate", "set_temperature", _boom)
    hass.states.async_set("climate.trv", "heat", {"hvac_modes": ["heat"]})
    entry = _room_entry(hass)
    await PoiseStore(hass, entry.entry_id).save({"ekf_version": 1})
    await async_remove_entry(hass, entry)
    assert await PoiseStore(hass, entry.entry_id).load() is None
```

**Zur Absicherung nötig:** Keiner.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.85): Teilbestätigt mit erheblicher Einengung. BESTÄTIGT ist der Titelkern "Store-/Trace-Cleanup nach geschlucktem Park-Fehler unbelegt": kein Test in tests/ kombiniert einen Park-Fehler mit Store-/Trace-Asserts (Store-Delete-Assert nur im Happy Path, test_lifecycle_review.py:76; Trace-Delete-Assert nur in test_glue_coverage2.py:249 ohne Fehlerfall). Der erste Repro-Test des Findings wäre dafür tauglich. […]
- **widerlegt** (Konfidenz 0.82): Kernbehauptung widerlegt: Der als "unsimuliert" bezeichnete ServiceNotFound-Pfad IST getestet. tests/integration/test_glue_coverage4.py:112-117 (test_remove_zone_entry_is_noop) ruft async_remove_entry auf einem Zone-Entry mit CONF_ACTUATOR="climate.trv" (_base(), Z.52) auf, OHNE den Actuator-State zu setzen und OHNE climate-Services zu mocken. […]

---

### AR-43 · niedrig · Testlücke

**Testlücke strukturell: ohne installiertes HA wird das gesamte Lifecycle-Glue-Verzeichnis zur Collection-Zeit still übersprungen — lokal läuft kein einziger aktorischer Lifecycle-Pfad**

- **Fundstelle:** `tests/integration/conftest.py:30` — `collect_ignore_glob (Modul-Ebene)`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** pure function vs HA-Seiteneffekt: die Projektgrenze ist sauber gezogen, aber die HA-Seite der Grenze ist außerhalb von CI komplett dunkel — inklusive aller aktorischen Lifecycle-Pfade (Boiler-OFF, Aktor-Park)
- **Codebeleg:** tests/integration/conftest.py:30: `collect_ignore_glob = [] if _HA_MODERN else ["test_*.py"]`

**Befund:** Dimension: test-gap. Verifiziert: In der Sandbox ist `import homeassistant` ein ModuleNotFoundError; conftest.py:22-30 skippt daraufhin ALLE test_*.py des Verzeichnisses zur Collection-Zeit. Damit sind lokal/im HA-freien Gate strukturell ungetestet: async_setup_entry (beide Entry-Typen inkl. NotReady-Guard), async_migrate_entry, async_unload_entry (inkl. Boiler-OFF-Gating), async_remove_entry (Park/Boiler-OFF/Store-Cleanup) — die pure Suite deckt nur die Resolver ab, nicht deren Verdrahtung. WICHTIGE ENTLASTUNG: CI ist abgesichert — .github/workflows/ci.yml enthält einen expliziten Guard ('integration suite actually collected tests — no silent skip', bricht bei 0 collected Tests) plus ein 95%-Coverage-Gate über die Glue-Module. Restrisiko ist der lokale Workflow: `pytest` im Repo-Root ist grün, ohne dass eine Lifecycle-Glue-Zeile ausgeführt wurde — und Zeilen-Coverage 95% ersetzt keine Szenario-Coverage (der vakante Fehlerpfad-Test und die fehlenden Timer-/Refusal-/Save-Fehler-Szenarien koexistieren mit dem Gate).

**Mögliches Fehlverhalten im Realbetrieb:** Ein Entwickler, der lokal (ohne requirements-test.txt) ändert und testet, bekommt für jede Lifecycle-Regression grünes Licht; erst CI fängt sie — und nur, soweit die Glue-Suite das Szenario enthält (die except-Zweige __init__.py:247 und der Timer-Cancel-Pfad sind wenige Zeilen und passieren auch das Zeilen-Gate).

**Minimaler Reproduktionsfall / Testidee:**

```python
# Nachweis (im Repo-Root der Sandbox):
#   $ python -c "import homeassistant"   -> ModuleNotFoundError
#   $ pytest tests/integration --co -q   -> 'no tests collected' (collect_ignore_glob)
#   $ pytest -q                          -> grün, obwohl __init__.py nie importiert wurde
# Härtung (Vorschlag): den stillen Skip lokal sichtbar machen — statt collect_ignore_glob
# einen pytest_collection_modifyitems-Hook mit pytest.mark.skip(reason=...) verwenden,
# sodass die Tests als SKIPPED (mit Grund) erscheinen statt unsichtbar zu fehlen.
# Der CI-Guard in ci.yml bleibt unverändert.
```

**Zur Absicherung nötig:** Bewusste ADR-0005/0011-Designentscheidung (pure Core HA-frei testbar) — das Finding richtet sich nicht gegen den Split, sondern gegen die Unsichtbarkeit des Skips im lokalen Lauf.

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.9): Kern des Findings verifiziert: tests/integration/conftest.py:30 (`collect_ignore_glob = [] if _HA_MODERN else ["test_*.py"]`) skippt ohne installiertes HA das gesamte Verzeichnis still zur Collection-Zeit — nachgestellt: `import homeassistant` -> ModuleNotFoundError; `pytest tests/integration --co -q` -> 0 collected (exit 5, kein Skip-Hinweis); `pytest -q` im Root -> grün (exit 0). […]
- **bestätigt** (Konfidenz 0.93): Bestätigt nach aktiver Widerlegungsprüfung. (1) Code-Zitat exakt: tests/integration/conftest.py:30 `collect_ignore_glob = [] if _HA_MODERN else ["test_*.py"]`, Guard Zeilen 22-27. (2) Sandbox reproduziert: `import homeassistant` -> ModuleNotFoundError (Py 3.11.15); `pytest tests/integration --co -q` -> Exit 5 mit NULL Output (kein SKIPPED-Marker, völlig unsichtbar); `pytest -q` im Root -> grün (Exit 0) trotz testpaths=["tests"] (pyproject.toml:13). […]

---

### AR-44 · niedrig · sicherer Fehler

**Trace-Cleanup löscht nur '<entry_id>.jsonl' — die Rotationsgeneration '.jsonl.1' des Recorders bleibt als Leiche liegen; suppress(Exception) um Store-Remove verschluckt auch Programmierfehler**

- **Fundstelle:** `custom_components/poise/__init__.py:298` — `_remove_room_entry`
- **Schadensklasse:** kein Realbetriebsschaden
- **Verletzte Projektgrenze:** Cleanup-Pfad kennt das Rotationsschema des Schreibpfads nicht — zwei Module teilen eine implizite Dateinamens-Konvention nur zur Hälfte
- **Codebeleg:** __init__.py:298: `hass.config.path("poise_traces", f"{entry.entry_id}.jsonl")` — Recorder rotiert aber: `self._path.replace(self._path.with_name(self._path.name + ".1"))` (trace/recorder.py:35)

**Befund:** Dimension: remove. Der Schreibpfad stimmt für die Basisdatei überein (coordinator.py:329 setzt _trace_slug=entry.entry_id, coordinator.py:935-936 schreibt nach poise_traces/<entry_id>.jsonl). Der TraceRecorder erzeugt bei Erreichen des Größenlimits jedoch eine zweite Generation '<entry_id>.jsonl.1' (recorder.py:33-35, Docstring: 'two generations ... bounded at ~2x the cap'); _remove_trace_file (__init__.py:364-370) löscht nur die Basisdatei. Nach dem Löschen eines Entries mit Trace-Recording und mindestens einer Rotation bleibt die .1-Datei (bis max_bytes groß) dauerhaft liegen. Nebenbefund im selben Block: contextlib.suppress(Exception) um PoiseStore.async_remove (__init__.py:294-295) verschluckt auch TypeError/AttributeError aus künftigen Refactoring-Fehlern — ein still nie funktionierendes Store-Cleanup wäre unentdeckbar; suppress(OSError) wäre das passende Fangnetz für best-effort Datei-Cleanup.

**Mögliches Fehlverhalten im Realbetrieb:** Verwaiste Trace-Dateien (Speicher, DSGVO-relevante Raumdaten bleiben nach 'Löschen' liegen); still fehlschlagendes Store-Cleanup bliebe unsichtbar.

**Minimaler Reproduktionsfall / Testidee:** Raum-Entry mit CONF_TRACE_RECORDING=true betreiben, bis die Rotation greift (Datei >= DEFAULT_TRACE_MAX_BYTES → .jsonl.1 entsteht), dann Entry löschen: poise_traces/<entry_id>.jsonl.1 existiert weiterhin.

**Zur Absicherung nötig:** In _remove_trace_file zusätzlich path + '.1' entfernen (bzw. glob auf '<entry_id>.jsonl*').

**Adversariale Verifikation:**

- **bestätigt** (Konfidenz 0.92): Widerlegungsversuch gescheitert — alle Behauptungen halten der Code-Lektüre stand. (1) Rotation existiert: custom_components/poise/trace/recorder.py:33-35 rotiert bei st_size >= max_bytes via `self._path.replace(self._path.with_name(self._path.name + ".1"))` → erzeugt poise_traces/<entry_id>.jsonl.1. (2) Namenskonvention stimmt: coordinator.py:329 `self._trace_slug: str = entry.entry_id` (einzige Zuweisung, nie reassigned), coordinator.py:935-936 schreibt nach poise_traces/<slug>.jsonl. […]
- **bestätigt** (Konfidenz 0.93): Alle Kernbehauptungen verifiziert. (1) Zitate/Zeilen exakt: __init__.py:298 löscht nur poise_traces/<entry_id>.jsonl via _remove_trace_file (__init__.py:364-370, os.remove auf genau einen Pfad); recorder.py:35 rotiert bei stat().st_size >= max_bytes per replace(...name + ".1") zu <entry_id>.jsonl.1 (Docstring Z.4: "two generations ... bounded at ~2x the cap"). (2) Schreib-/Löschpfad-Kongruenz für die Basisdatei bestätigt (coordinator.py:329 _trace_slug=entry.entry_id; coordinator.py:935-940 mit DEFAULT_TRACE_MAX_BYTES=20 MiB, const.py:107). […]

---

## KI-typische Grenzverletzungen (Karte)

Stellen, an denen mutmaßlich „hilfreich“ vervollständigter Code eine deklarierte Projektgrenze verletzt oder ein Kommentar eine Grenze behauptet, die der Code nicht einhält:

**options vs data:**
- AR-04 (hoch): async_apply_options überschreibt den live per Klima-Entität gesetzten climate_mode (heat_only/cool_only) bei jedem Options-Submit mit dem stale Formularwert — doppelte Ownership Store vs. Options
- AR-16 (mittel): Frischer V2-Entry: Required-Options-Felder ohne Default (optimal_start, comfort_weight, climate_mode) — erster Options-Save flippt Coordinator-Defaults still (optimal_start True→False, comfort_weight 70→0)
- AR-19 (mittel): Testlücke Migration: version>2-Refusal (MIGRATION_ERROR), V1-Hub-Entry end-to-end, Idempotenz, options-gewinnt-Konflikt e2e, occupancy-String in data und Reconfigure-Roundtrip nach Migration sind nirgends abgedeckt
- AR-27 (niedrig): Migrations-Merge 'options gewinnt': ob damit ein neuerer V1-data-Wert verdeckt werden kann, hängt vom nicht mehr rekonstruierbaren V1-Verhalten ab
- AR-36 (niedrig): async_migrate_entry: version>2-Guard ist in unterstütztem HA toter Code (Core übernimmt den Refusal); Migration setzt minor_version nie — bei künftigem Minor-Bump/Downgrade läuft die Migration bei jedem Start erneut

**diagnostic only vs live:**
- AR-11 (mittel): Raum-Remove aktuiert auch bei nie erfolgreichem Setup: Park + Select-Restore feuern auf ein Gerät, das Poise nie kommandiert hat
- AR-15 (mittel): _remove_hub_entry feuert Boiler-OFF rein verdrahtungsbasiert — Kommentar 'only switch a boiler Poise actually commanded' ist eine Fehlbehauptung (verdrahtet != kommandiert)
- AR-29 (niedrig): _remove_hub_entry: except (HomeAssistantError, ValueError) fängt vol.Invalid aus der synchronen Service-Schema-Validierung nicht — Löschung des Frost-Repair-Issues wird übersprungen
- AR-32 (niedrig): Als 'SHADOW (diagnostic only, no writes)' kommentierter Block erzeugt die live wirksame Stellgröße _hum_action (dry-Mode-Nudge) — Fehler darin werden nur auf DEBUG verschluckt
- AR-37 (niedrig): Stale Modul-Docstring in binary_sensor.py: 'Poise does not switch any boiler in this stage' und 'across all zones' widersprechen dem ausgeführten Code (S2-Aktuation implementiert; Aggregation ist controls_boiler-only)
- AR-38 (niedrig): safety/sensor_watchdog.py-Moduldocstring behauptet, der Frozen-Sensor-Pfad verändere den Regelausgang nicht ('without altering the control output') — der Coordinator ersetzt bei frozen Ziel UND Modus

**pure function vs HA side effect:**
- AR-28 (niedrig): async_persist_and_cleanup nimmt self._lock nicht — finaler Save kann einen halb-aktualisierten Mid-Tick-Modellzustand persistieren
- AR-42 (niedrig): Testlücke Remove-Fehlerpfade Raum: Aktor fehlt/unavailable und werfender Park-Service-Call ungetestet — Store-/Trace-Cleanup nach geschlucktem Park-Fehler unbelegt
- AR-43 (niedrig): Testlücke strukturell: ohne installiertes HA wird das gesamte Lifecycle-Glue-Verzeichnis zur Collection-Zeit still übersprungen — lokal läuft kein einziger aktorischer Lifecycle-Pfad

**safety vs comfort:**
- AR-02 (hoch): Hub-Unload-Race: Tick-Timer lebt während des Boiler-OFF-Handovers weiter und kann den Boiler nach dem OFF wieder einschalten — dauerhaft AN nach Disable/Reconfigure
- AR-05 (hoch): Hub verwirft unavailable-safe-Zonen komplett: lokaler Frostschutz parkt TRV auf heat@7°C, aber der geteilte Boiler feuert nicht — Frostschutzkette reißt an der Zone→Hub-Grenze
- AR-07 (mittel): Vakanter Test: test_remove_hub_swallows_off_failure erreicht den Fehlerpfad nie (nur OFF-Action gewired → F12-Gate überspringt den Call) — Boiler-OFF-Fehlerbehandlung bei Hub-Remove faktisch ungetestet
- AR-10 (mittel): resolve_park_command klemmt den Setback-Setpoint nicht an device min_temp — set_temperature kann still scheitern und das Gerät bleibt in 'heat' auf dem alten Komfort-Setpoint
- AR-20 (mittel): async_bootstrap: Catch-all über dem Store-Load macht aus jedem transienten I/O-Fehler ein 'starting fresh' — gelerntes Modell wird vom periodischen Save überschrieben; Teil-Restore kann enabled=False/override verlieren
- AR-22 (mittel): Testlücke: Unload mit Save-Fehler — das definierte Swallow-Verhalten von async_persist_and_cleanup ist von keinem Test abgesichert
- AR-24 (mittel): Blocking-Boiler-OFF-Calls in Unload-/Remove-Pfaden ohne das 10-s-Timeout des normalen Aktuationspfads — hängender Boiler-Service blockiert Unload/Remove unbegrenzt und vergrößert das Timer-Race-Fenster
- AR-25 (niedrig): Fehlgeschlagener Plattform-Unload beim Hub-Disable: OFF-Handover und Issue-Cleanup übersprungen, Timer läuft weiter — disabled Hub aktuiert den Boiler bis zum Neustart

**local room zone vs system hub:**
- AR-01 (hoch): Hub-Reconfigure auf anderen Boiler-Aktor lässt den alten Boiler dauerhaft AN: Relinquish-Erkennung prüft nur 'verdrahtet', nicht 'gleicher Aktor'
- AR-03 (hoch): Raum-Unload bei Entry-Disable parkt den Aktor nicht — Ventil/Klimagerät verharrt dauerhaft auf letztem Poise-Kommando, ohne Frost-Rescue
- AR-06 (hoch): Testlücke Hub-Lifecycle: Timer-Registrierung, Timer-Abbestellung beim Unload und 'nur BINARY_SENSOR wird geforwarded' — kein Test feuert je den Zeitgeber
- AR-09 (mittel): _STRUCTURAL_CARRY reanimiert vom Nutzer gelöschte Anlagen-Felder (declared_power, compressor_group, design_flow_temp), sobald ein System-Hub existiert — Kommentar behauptet das Gegenteil
- AR-12 (mittel): Room-Reconfigure auf anderen Aktor: alter TRV bleibt auf 'external'-Sensorquelle mit eingefrorenem Feed und wird nicht geparkt — F3/F6-Cleanup existiert nur im Delete-Pfad
- AR-17 (mittel): _execute_park: blocking=False macht Ausführungsfehler des finalen, nie wiederholten Kommandos unsichtbar (Widerspruch zu F27) und racet set_temperature gegen set_hvac_mode
- AR-26 (niedrig): Kein Setup-Guard gegen einen zweiten System-Entry: bei zwei Hub-Entries (Storage-Restore/Backup-Merge) entstünden zwei konkurrierende Boiler-Schreiber mit kämpfenden Keepalives

**measured vs estimated:**
- AR-08 (mittel): Hub verliert bei HA-Stop/Restart sämtlichen Boiler-Takt-Zustand: kein Stop-Handler, keine Persistenz, Keepalive kein Dead-Man-Netz, Reconcile misinterpretiert Script-Entities, Min-Off nach Restart verletzbar
- AR-41 (niedrig): Testlücke Setup-Guard: die Variante 'Temperatursensor fehlt, Aktuator existiert' und der Degraded-Pfad 'Sensor existiert-aber-unavailable → Setup lädt' sind ungetestet

**Weitere Lifecycle-/Persistenzgrenzen:**
- AR-18 (mittel): _restore_trv_internal flippt JEDES Select mit 'internal'-Option — breiter als der eigene Klassifikator is_external_sensor_select und ohne Idempotenz-/Ownership-Check
- AR-21 (mittel): Kommentar '(no learning loss)' ist falsch: Save-Fehler beim Unload wird geschluckt, bis zu 30 Ticks Lernen still verloren und das persistence_failed-Issue direkt danach gelöscht
- AR-23 (mittel): State-Listener, Stop-Flush und Update-Listener werden vor dem Plattform-Forwarding registriert: wirft das Forwarding unerwartet, kann (HA-versionsabhängig) ein Zombie-Koordinator ohne Entities weiter aktorisch regeln
- AR-30 (niedrig): ADR-0038 Entscheidung 6 ('System-Onboarding erscheint nur bei ≥2 Zonen oder konfigurierter geteilter Ressource') ist nicht umgesetzt — das System-Menü erscheint immer
- AR-31 (niedrig): quality_scale.yaml enthält veraltete Selbstauskunft: 'via_device ... still pending' ist längst implementiert, Testzahl (74 statt 98) stimmt nicht mehr
- AR-33 (niedrig): Setup-Guard erkennt registry-deaktivierte Pflicht-Entities nicht: ewiger ConfigEntryNotReady-Retry mit irreführender Meldung, kein Repair-Issue
- AR-34 (niedrig): Korrupter/unvollständiger Raum-Entry crasht mit KeyError/ValueError in Guard und Koordinator-Konstruktor → dauerhafter SETUP_ERROR ('Unknown error') statt kontrolliertem Fehlerpfad
- AR-35 (niedrig): Boiler-Reconcile stempelt last_switch_mono=now auch beim Adoptieren von real=OFF — nach jedem Neustart/Reload blockiert min_off (Default 300 s, bis 3600 s) das erste Einschalten, auch für den Frost-Override; F8-Kommentar begründet nur den ON-Fall
- AR-39 (niedrig): ADR-0038 beschreibt eine nicht existierende Architektur: In-Memory-Registry hass.data[DOMAIN]['hub'] (Push) und ResourceRelease-Rückkanal — Code macht Pull über entry.runtime_data, ResourceRelease ist toter Contract
- AR-40 (niedrig): ADR-0007 verspricht Debounce-Persistenz ('schreibt nur bei echter Änderung', async_call_later, BT-Muster) und eine _check_entities_ready-Warteschleife — Code hat Counter-Throttle alle 30 Ticks und nur einen Existenz-Check
- AR-44 (niedrig): Trace-Cleanup löscht nur '<entry_id>.jsonl' — die Rotationsgeneration '.jsonl.1' des Recorders bleibt als Leiche liegen; suppress(Exception) um Store-Remove verschluckt auch Programmierfehler

---

## Aktiv widerlegte Verdachtsmomente

Diese Findings der ersten Runde hielten der adversarialen Verifikation **nicht** stand und sind dokumentiert, damit sie nicht in einer späteren Review-Runde erneut aufgeworfen werden:

### ✗ Park-Pfad kommandiert 'off' an heizfähige TRVs, wenn der Aktor beim Löschen unavailable/ohne State ist (modes=[] → Off-Plan) — Docstring verspricht das Gegenteil

*Erst-Einstufung: hoch — `custom_components/poise/__init__.py`*

- **widerlegt:** Der Poise-Code-Pfad existiert wie zitiert (__init__.py:271-276 → modes=[] bei st=None; heats_for_zone False in Z.283-284; lifecycle.py:98 Off-Plan; _execute_park Z.317-331 blocking=False, Fehler verschluckt), aber die tragende HA-Annahme ist falsch: (1) Ein unavailable Climate-Entity BEHÄLT hvac_modes — HA-Core 2026.1.0 helpers/entity.py __async_calculate_state baut attr aus capability_attributes VOR dem 'if available:'-Check, und ClimateEntity.capability_attributes enthält ATTR_HVAC_MODES als ersten Eintrag. […]
- **widerlegt:** Der Poise-interne Code-Pfad ist korrekt zitiert (custom_components/poise/__init__.py:271-276 ergibt modes=[] bei st=None; control/lifecycle.py:98 liefert dann ParkPlan('climate','off')), und die Testlücke existiert (tests/test_lifecycle_pure.py:75-118, tests/integration/test_lifecycle_review.py:62-98 testen nur nicht-leere Modelisten). Die Schadenskette ist aber gegen HA-Core 2025.1.0 (Minimum laut hacs.json) widerlegt: (1) Die Prämisse 'unavailable => hvac_modes fehlt' ist falsch — helpers/entity.py:1081-1090 übernimmt capability_attributes (inkl. […]

### ✗ Testlücke: async_apply_options (A10-Hot-Apply) ist vollständig ungetestet — genau der Pfad, der das climate_mode-Clobber-Finding enthält

*Erst-Einstufung: mittel — `custom_components/poise/coordinator.py`*

- **widerlegt:** Kernbehauptung widerlegt: tests/integration/test_entity_actions.py:190-216 (test_options_update_applies_tuning_without_reload) testet den A10-Hot-Apply-Pfad end-to-end über den echten HA-Update-Listener: volles Entry-Setup (Z.76 registriert den Listener via __init__.py:141), dann hass.config_entries.async_update_entry(entry, options={"comfort_base": 22.5, ...}) (Z.206-208) + async_block_till_done. […]
- **widerlegt:** Kernbehauptung widerlegt: tests/integration/test_entity_actions.py:190-216 (test_options_update_applies_tuning_without_reload) testet exakt den A10-Hot-Apply-Pfad. Der Test lädt einen Raum-Entry über das echte async_setup_entry (registriert den Listener, __init__.py:141), feuert hass.config_entries.async_update_entry(entry, options={"comfort_base": 22.5, "category": "I"}) (Z.206) und assertet: (a) entry.runtime_data is coord (kein Reload), (b) coord._comfort_base == 22.5 — nur async_apply_options (coordinator.py:589) setzt dieses Feld zur Laufzeit, der Apply lief also nachweislich, (c) EKF-Ler […]

### ✗ _async_options_updated greift entry.runtime_data ohne Guard — Options-Update während eines laufenden Unloads trifft einen sterbenden Koordinator (Debouncer-RuntimeError / Apply auf Discard-Instanz)

*Erst-Einstufung: niedrig — `custom_components/poise/__init__.py`*

- **widerlegt:** Der Kern-Fehlermodus des Findings beruht auf einer falschen HA-Annahme. (1) Kein Debouncer-RuntimeError in der Zielversion (hacs.json verlangt HA >= 2025.1.0): homeassistant/helpers/debounce.py (Tag 2025.1.0) Z. 78-80 — nach async_shutdown ist async_call ein stilles No-Op ('Debouncer call ignored as shutdown has been requested.' + return), kein Raise. Doppelt abgesichert durch update_coordinator.py:368 — _async_refresh returned sofort bei self._shutdown_requested. […]
- **widerlegt:** Beide behaupteten Fehlermechanismen sind in der Zielversion (hacs.json: HA >= 2025.1.0; Tests gepinnt auf pytest-homeassistant-custom-component==0.13.195) mit Quellcode-Beleg unmöglich. (1) Kein Debouncer-RuntimeError: homeassistant/helpers/debounce.py@2025.1.0 Z.78-80 ignoriert Aufrufe nach async_shutdown still ("Debouncer call ignored as shutdown has been requested.", return False); async_call Z.99-102 kehrt ohne Raise zurück; zusätzlich returned DataUpdateCoordinator._async_refresh bei _shutdown_requested sofort (update_coordinator.py:368). […]

---

## Entwarnungen (geprüft und für in Ordnung befunden)

### ✓ Prüfpunkt runtime_data vor/nach Forwarding — Reihenfolge in beiden Entry-Typen korrekt, alle vier Plattformen lesen runtime_data erst nach dem Setzen

Hub: runtime_data wird in __init__.py:85 gesetzt, Forwarding folgt in Zeile 102. Raum: runtime_data in Zeile 127, Forwarding in Zeile 142. Alle Konsumenten greifen ausschließlich in ihren async_setup_entry-Plattformfunktionen zu: climate.py:156, sensor.py:223, switch.py:35, binary_sensor.py:56, diagnostics.py:24. Kein Pfad liest runtime_data vor der Zuweisung; der Hub-Zonen-Scan (hub_coordinator.py:142) nutzt defensives getattr(e, 'runtime_data', None) für fremde Entries. Restrisiko der Registrierungs-Reihenfolge (Listener vor Forwarding) ist bereits als eigenes Finding gemeldet.

### ✓ Migration fasst Hub-Entries nachweislich nicht an — Docstring-Behauptung 'Hub entries keep their content unchanged' stimmt mit dem Code überein

Prüfpunkt (4) Migration-überschreibt-data/options in der System-vs-Room-Dimension (Prüfpunkt 7): async_migrate_entry (__init__.py:162) schickt zwar auch Hub-Entries durch migrate_room_entry, aber migration.py:82-83 gibt data/options für entry_type=='system' als Kopien unverändert zurück — nur die Version wird gebumpt (__init__.py:163-165). Der Docstring-Anspruch in __init__.py:155-156 ('Hub entries keep their content unchanged (only the version bumps)') ist damit korrekt. Die verbleibenden Room-Merge-Risiken (options-gewinnt-Ambiguität, Idempotenz, fehlende Tests, minor_version) sind bereits durch überlebende Findings abgedeckt.

### ✓ Kommentar-vs-Code Setup-Guard — die Behauptung, ein existierender-aber-unavailable Sensor werde vom Degraded-Pfad des Ticks (Frost-/Mould-Safe-State) aufgefangen, ist implementiert

Der Setup-Guard-Kommentar in __init__.py:112-115 ('one that exists but is unavailable/unknown passes here and is handled by the tick's degraded path (hold last state, then the frost/mould safe state)') wurde gegen den Code geprüft: coordinator.py:1233-1251 trackt _unavailable_since, loggt den Verlust (Silver-Anforderung, 1236-1242) und schreibt nach UNAVAILABLE_SAFE_AFTER_S über _write_unavailable_safe_state (1165-1216) den per pure resolve_safe_state (control/lifecycle.py:24-56) aufgelösten Frost-/Mould-Safe-State: heat@Floor (an device_min geklemmt) für heizfähige, 'off' für cool-only Geräte. Der Kommentar ist keine Fehlbehauptung. Die separate Frozen-Pfad-Docstring-Diskrepanz im sensor_watchdog ist bereits als Finding gemeldet.

### ✓ Projektgrenze pure function vs. HA-Seiteneffekt eingehalten — control/lifecycle.py und control/hub_aggregate.py sind HA-frei, alle Service-Calls liegen im Glue

Die als pure deklarierten Lifecycle-Entscheider importieren ausschließlich dataclasses (lifecycle.py:9-11); hub_aggregate.py importiert nur stdlib + const/contracts (hub_aggregate.py:10-17). Kein hass-Zugriff, keine Zeitquelle, keine Service-Calls — alle aktorischen Aufrufe liegen nachweislich im Glue (__init__.py:_execute_park 302-331, _restore_trv_internal 334-361; hub_coordinator._call 233-250, async_fire_boiler_off 330-343). Die Grenze 'Entscheidung pure, Ausführung Glue' aus dem lifecycle.py-Docstring stimmt mit dem Code überein. Inhaltliche Schwächen einzelner Entscheider (Setback-Clamp an device min_temp) sind bereits als Finding gemeldet.

### ✓ Grenzen measured/estimated und diagnostic/live am Hub-Shadow eingehalten — S3/S4 (declared_power-basiert) erzeugt nur Diagnose-Attribute, keinen Service-Call

Der einzige Ort, an dem geschätzte/deklarierte Größen (declared_power aus der Config statt gemessener Leistung, shadow-min-cycle mit geliehenen Boiler-Timern) in Entscheidungen einfließen, ist _shared_resource_shadow (hub_coordinator.py:189-231). Der Pfad enthält keinen einzigen hass.services.async_call; die Ergebnisse (shed_zones, compressor_groups, flow_target, source_grants) landen ausschließlich im Rückgabe-Dict und werden nur als Attribute des diagnostischen Binary-Sensors exportiert (binary_sensor.py:37-42). Kein anderer Code liest shed/flow/grants aktorisch (repo-weiter Grep). Die einzige Hub-Aktuation ist der Boiler-Pfad, der auf gemessenen Zonen-Snapshots und dem realen Boiler-Entity-State (reconcile) basiert. Deklarierter Kommentar 'computed, not enforced' stimmt mit dem Code überein; die bekannten Boiler-Pfad-Schwächen sind bereits als Findings gemeldet.

### ✓ Kein toter Hub-Options-Pfad — PoiseHubOptionsFlow abortet sofort (F9), konsistent mit dem frühen System-Return in _async_options_updated

Verdachtsprüfung zu Prüfpunkt (7): _async_options_updated ignoriert System-Entries komplett (__init__.py:39-40) — das wäre gefährlich, wenn der Hub editierbare Options hätte, die dann still nie angewendet würden. Tatsächlich abortet der Hub-Options-Flow sofort (config_flow.py:849-852), Hub-Einstellungen laufen ausschließlich über Reconfigure mit vollem Reload (config_flow.py:755-770, async_update_reload_and_abort), und der Hub-Coordinator liest konsistent nur entry.data (hub_coordinator.py:100). Der F9-Kommentar stimmt mit dem Code überein; es gibt keinen Hub-Options-Zustand, der verloren gehen könnte. Die Reconfigure-Schwächen des Hubs (Relinquish-Erkennung, alter Boiler bleibt AN) sind bereits als Findings gemeldet.

### ✓ Soll-Test 'fehlender Aktuator' existiert und prüft den echten SETUP_RETRY-Pfad end-to-end

Von den sechs Soll-Tests war 'fehlender Aktuator' der einzige, der weder durch ein überlebendes Finding noch durch eine Entwarnung adressiert war. Der Test existiert (tests/integration/test_setup_and_cycle.py:100-111): nur der Raumsensor wird angelegt, das Setup läuft gegen den echten Guard (__init__.py:116-122) und asserted SETUP_RETRY. Die Spiegelvariante ('Temperatursensor fehlt, Aktuator existiert') und der Degraded-Pfad sind bereits als Testlücken-Finding gemeldet; ebenso die strukturelle Einschränkung, dass diese Tests ohne installiertes HA still übersprungen werden.

---

## Konkrete Tests für die geforderten Szenarien

Die sechs geforderten Soll-Szenarien, ihr Ist-Zustand und die gelieferten Tests. Die neuen
Integrationstests liegen ausführbar in **`tests/integration/test_lifecycle_adversarial_review.py`**
(CI-only, wie alle Glue-Tests; die Sandbox überspringt das Verzeichnis mangels HA-Runtime — siehe
AR-43), der pure Idempotenz-Test in `tests/test_migration.py` (lokal grün gelaufen).

| # | Szenario | Ist-Zustand | Neuer Test |
|---|----------|-------------|------------|
| a | Setup bei fehlendem Sensor | Nur die Aktuator-Variante war getestet (`test_setup_retry_when_actuator_missing`) | `test_setup_retry_when_temp_sensor_missing` + `test_setup_loads_with_unavailable_temp_sensor` (Degraded-Pfad-Zusage des Guard-Kommentars) |
| b | Setup bei fehlendem Aktuator | ✓ vorhanden: `tests/integration/test_setup_and_cycle.py:100` prüft den echten `SETUP_RETRY`-Pfad end-to-end (Entwarnung §7) | — |
| c | Systemhub-Entry | Nur „`binary_sensor` in domains“ + LOADED; Timer nie gefeuert (AR-06) | `test_hub_timer_ticks_and_dies_on_unload`: exaktes Forwarding, Timer treibt den Tick, Timer stirbt beim Unload |
| d | Migration von alter Version | V1-Raum-Entry e2e vorhanden (`test_migration_glue.py:82`); version>2-Refusal, V1-Hub und Idempotenz fehlten (AR-19) | `test_future_schema_is_refused_not_downgraded`, `test_v1_hub_entry_bumps_version_content_untouched`, pure: `test_migration_is_idempotent` |
| e | Unload mit Save-Fehler | Ungetestet (AR-22); Verhalten war nur im Code definiert (Swallow + Log, AR-21) | `test_unload_survives_final_save_failure` — nagelt fest: Unload gelingt trotz `OSError` |
| f | Remove mit Boiler-OFF-Action | Happy-Path vorhanden (`test_glue_coverage4.py:94`); der Fehlerpfad-Test war **vakant** (AR-07: nur OFF-Action verdrahtet → F12-Gate überspringt den Call, keine Assertion) | `test_remove_hub_off_failure_swallowed_and_issue_cleared` (Fehlerpfad wirklich betreten, Issue-Cleanup trotz Fehler) + `test_remove_hub_off_runtime_error_still_clears_issue` als **strict xfail** (dokumentiert AR-29: zu enge except-Tuple; der Marker fällt mit dem Fix) |

Der vakante Alt-Test `test_remove_hub_swallows_off_failure` (tests/integration/test_glue_coverage4.py:131)
sollte nach Übernahme der neuen Tests entfernt oder auf beide Actions umverdrahtet werden — in seiner
heutigen Form bestätigt er nur sein eigenes Mock-Setup (Beweis: der Schwestertest
`test_hub_remove_silent_when_shadow_only` asserted mit identischem Setup `len(turn_off) == 0`).

Weitere Test-Skizzen (Remove-Fehlerpfade Raum, Migrations-Konfliktfälle) liegen in den jeweiligen
Findings AR-42 und AR-19.

---

## Limitierungen dieses Reviews

* Die Integrationstests konnten in dieser Sandbox nicht ausgeführt werden (Harness benötigt
  Python ≥ 3.12 + HA 2025.1; hier 3.11) — die neuen Glue-Tests sind syntaxgeprüft und eng an den
  vorhandenen, in CI laufenden Mustern gebaut, aber erst der CI-Lauf beweist sie. Der pure Test
  wurde lokal ausgeführt (grün, 9/9 in `test_migration.py`).
* HA-Core-Verhalten wurde von den Verifikations-Reviewern gegen den HA-2025.1-Quelltext geprüft
  (u. a. `config_entries.py`: `_async_process_on_unload` erst **nach** `async_unload_entry`;
  `runtime_data` wird nach erfolgreichem Unload gelöscht; `Store.async_load` re-raist
  Nicht-JSON-Fehler). Abweichende zukünftige HA-Versionen können einzelne Aussagen verschieben.
* Findings der Klassen „begründeter Verdacht“ und „fehlender Kontext“ benennen im Feld
  „Zur Absicherung nötig“, welche Information sie zu „sicherer Fehler“ oder zur Entwarnung machen
  würde — insbesondere AR-05 hängt an einer Design-Entscheidung, die ADR-0039 nur teilweise abdeckt.


---

# Nachtrag (2026-07-10): Verifikation der Umsetzung in v0.160.0

Geprüft wurde `origin/main` @ `4d738d9` (25 Commits nach dem Review-Stand `b4730e7`, Version 0.159.0 → 0.160.0).
Die Umsetzung referenziert die AR-Nummern dieses Reviews explizit im Code. **CI auf dem geprüften HEAD ist grün**
(Run vom 2026-07-10, inkl. der neuen Testdateien `test_review_ar_coverage.py`, erweiterter
`test_setup_and_cycle.py`/`test_lifecycle_review.py`/`test_migration_glue.py`/`test_config_flow.py` und
purer `test_hub_aggregate.py`-Ergänzungen). Jede Zeile unten wurde gegen den tatsächlichen Diff verifiziert,
nicht gegen Commit-Botschaften.

## Status je Finding

| ID | Status | Umsetzung (verifiziert) |
|----|--------|--------------------------|
| AR-01 | ✅ behoben + getestet | `resolve_hub_unload_off(..., target_changed=)`; Unload vergleicht altes `hub._action_on/_off`-Ziel mit den neuen entry.data-Actions und feuert bei Retarget OFF über die **alte** Action. Test: `test_hub_unload_hands_back_old_boiler_on_retarget`. |
| AR-02 | ✅ behoben | Timer-Unsub liegt am Hub (`hub._tick_unsub`) und wird im Unload-Zweig **vor** OFF/Plattform-Unload gecancelt; nach dem Hand-over-OFF wird `hub._boiler = BoilerState(on=False)` gesetzt, sodass kein Keepalive aus stale Glauben re-asserted. (Race selbst strukturell beseitigt; kein direkter Race-Test — akzeptabel.) |
| AR-03 | ✅ behoben + getestet | Raum-Unload parkt bei `entry.disabled_by is not None` über das neue `_park_room_actuator(live_mode=True)` (ohne Store-/Trace-Löschung). Tests: `test_room_disable_parks_heater`, `test_room_disable_parks_cool_only_off`. |
| AR-04 | ✅ behoben (ohne dedizierten Test) | `async_apply_options` wendet `CONF_CLIMATE_MODE` nicht mehr an (Store-owned, Kommentar dokumentiert die Entscheidung); das Feld wurde komplett aus dem Options-Formular entfernt. Kein direkter Regressionstest „Options-Save erhält gepinnten Modus" — Restlücke Test. |
| AR-05 | ✅ behoben + getestet | `frost_heat_request()` (pure): eine `unavailable_safe`-Zone mit `controls_boiler` feuert den Kessel synthetisch über den Frost-Override (bewusster mono_ts-Bypass, `declared_power=None` hält sie aus der Power-Mathematik); neues Repair-Issue `hub_frost_zone_unavailable` + Snapshot-Feld + Übersetzungen. Tests: Glue (`test_hub_fires_frost_for_unavailable_safe_zone`) + pure (`test_frost_heat_request_fires_boiler_unconditionally`). |
| AR-06 | ⚠️ auf main offen — auf diesem Branch geschlossen | main testet den Hub-Timer weiterhin nie über den echten Zeitpfad (kein `async_fire_time_changed` im Baum) und asserted Forwarding nur mit `in domains`. Der Test dieses Branches (`test_hub_timer_ticks_and_dies_on_unload`) deckt Registrierung, Tick-Antrieb, Timer-Tod beim Unload und `domains == {"binary_sensor"}` ab. |
| AR-07 | 🟡 teilweise | Der Happy-Path-Test wurde korrekt auf das neue `has_actuated`-Gate umverdrahtet und `test_hub_remove_fires_off_from_persisted_state` prüft Gate+OFF+Issue-Cleanup. **Aber:** der vakante Alt-Test `test_remove_hub_swallows_off_failure` (OFF-only, RuntimeError, keine Assertion) existiert unverändert — er ist jetzt sogar doppelt vakant (F12-Gate **und** fehlender Hub-Store-Payload). Der Remove-**Fehlerpfad** war auf main nur im Erfolgsfall getestet; die zwei Fehlerpfad-Tests dieses Branches schließen das. |
| AR-08 | ✅ behoben + getestet | Neuer `PoiseHubStore`: BoilerState wall-clock-verankert persistiert/restauriert (`boiler_state_to_payload`/`restore_boiler_state`, Rückwärts-Uhr geklemmt), `has_actuated`-Dead-Man-Flag; Persist auf Aktuierungs-Meilenstein und jeden ON/OFF-Flip; Load-/Save-Fehler best-effort. Tests: Glue (Restore+Reconcile, Load-/Save-Fehler) + pure (Payload-Roundtrip, Clamps). |
| AR-09 | ✅ behoben | `reconcile_reconfigure(..., structural_section_rendered=)`: der Carry läuft nur noch, wenn die Anlagen-Sektion NICHT gerendert wurde; der Flow übergibt `hub_exists`. |
| AR-10 | 🟡 teilweise | `resolve_park_command` klemmt jetzt an `device_min` — aber nur der Reconfigure-Pfad (`_park_replaced_actuator`) übergibt `min_temp`; **`_park_room_actuator` (Remove/Disable) übergibt kein `device_min`**, obwohl der State dort gelesen wird. Der ursprünglich gemeldete Pfad bleibt ungeklemmt. |
| AR-11 | ✅ behoben + getestet | `_has_actuated`-Latch im Zonen-Coordinator (gesetzt bei jedem erfolgreichen Aktor-Write inkl. Safe-State), persistiert/restauriert; Park/Select-Restore laufen nur noch mit `has_actuated=True`. Test: `test_room_remove_skips_park_when_never_actuated`. |
| AR-12 | ✅ behoben + getestet | `_park_replaced_actuator` im Reconfigure-Flow: alter Aktor wird geparkt + TRV-Select restauriert, Live-Modus aus `runtime_data` bevorzugt. Test: `test_reconfigure_new_actuator_parks_old`. |
| AR-13 | ✅ behoben + getestet | Park liest `climate_mode` aus dem **Store** (Live-Wert), nicht aus der Entry-Config; bestehende Remove-Tests entsprechend nachgeschärft. |
| AR-14 | ❌ offen | Der Hub-Timer wird weiterhin **vor** dem Plattform-Forwarding registriert; wirft das Forwarding, cancelt niemand `hub._tick_unsub` (HA ruft bei Setup-Fehlern weder unload noch on_unload). Restrisiko klein (HA fängt Plattform-Setup-Fehler i. d. R. selbst), aber unverändert. |
| AR-15 | ✅ behoben + getestet | Remove-OFF zusätzlich auf persistiertes `has_actuated` (PoiseHubStore) gegated; Docstring korrigiert („actually commanded" stimmt jetzt). |
| AR-16 | ✅ behoben + getestet | `comfort_weight`/`optimal_start` mit Defaults; `climate_mode` aus dem Options-Formular entfernt. Test: `test_options_first_save_keeps_optimal_start_and_weight_defaults`. |
| AR-17 | ✅ behoben + getestet | `_execute_park` durchgängig `blocking=True`, engere except-Tuple, Mode-vor-Setpoint dokumentiert. Tests: werfender Park / unavailable Aktor brechen Cleanup nicht ab. |
| AR-18 | ✅ behoben + getestet | Restore nutzt den eigenen Klassifikator `is_external_sensor_select` und skippt bereits-`internal` (idempotent). Tests inkl. Nonmatch-/Skip-Zweige. |
| AR-19 | ✅ weitgehend | Neue Tests: version>2-Refusal (direkter `async_migrate_entry`-Aufruf), Migrations-Idempotenz e2e, `minor_version`-Assert. V1-**Hub**-Entry-e2e und der options-gewinnt-Konflikt e2e fehlen weiterhin (klein). |
| AR-20 | ✅ behoben | Store-Load-Fehler → `ConfigEntryNotReady` (Retry statt „starting fresh"+Überschreiben); User-Intent (enabled/preset/override/mode) wird **vor** dem schweren Modell-Parsing defensiv restauriert. |
| AR-21 | ✅ behoben + getestet | Save-Fehler beim Unload: `persistence_failed`-Issue wird gesetzt/behalten statt gelöscht; irreführender „(no learning loss)"-Anspruch aus dem Docstring korrigiert. Test: `test_unload_save_failure_keeps_persistence_issue`. |
| AR-22 | ✅ getestet | Ebendieser Test nagelt auch fest, dass der Unload trotz `OSError` gelingt (`NOT_LOADED`). |
| AR-23 | ✅ behoben | Listener/Stop-Flush/Update-Listener werden erst **nach** erfolgreichem Plattform-Forwarding registriert. |
| AR-24 | ✅ behoben + teilgetestet | `async_fire_boiler_off` und der Remove-OFF laufen mit dem 10-s-Timeout des normalen Aktuationspfads; Swallow-Test für den Helper vorhanden. |
| AR-25 | ✅ behoben | OFF-Handover + Issue-Cleanup laufen **vor** `async_unload_platforms` — ein fehlschlagender Plattform-Unload kann sie nicht mehr überspringen. |
| AR-26 | ❌ offen | Weiterhin kein Setup-Guard gegen einen zweiten System-Entry (nur die Flow-unique_id). Wie im Review: niedrig, Storage-Restore-Randfall. |
| AR-27 | ➖ kein Handlungsbedarf | „Fehlender Kontext"-Finding (V1-Verhalten nicht rekonstruierbar); keine Code-Änderung möglich/nötig. |
| AR-28 | ✅ behoben | Finaler Save läuft unter `self._lock` (kein Mid-Tick-Snapshot mehr). |
| AR-29 | ✅ behoben + auf diesem Branch getestet | except-Tuple erweitert (`vol.Invalid`, `TimeoutError`), Issue-Löschung in `finally` (überlebt auch ungefangene Exceptions). Fehlerpfad-Tests liefert dieser Branch nach (HomeAssistantError geschluckt; RuntimeError propagiert, Issue trotzdem weg). |
| AR-30 | ✅ behoben + getestet | System-Menüpunkt erscheint erst ab ≥1 Raum-Entry (ADR-0038 Entscheidung 6 jetzt umgesetzt). Test: `test_user_menu_hides_system_until_a_room_exists`. |
| AR-31 | ✅ behoben | quality_scale.yaml: via_device als erledigt markiert, Testzahl 74→98 korrigiert. |
| AR-32 | ✅ behoben | Kommentar sagt jetzt ehrlich „mostly-diagnostic … NOT `no writes`"; Fehler im Block werden einmalig als WARNING geloggt (danach DEBUG). |
| AR-33 | ✅ behoben + getestet (2×) | Registry-disabled Pflicht-Entity → Repair-Issue + `ConfigEntryError` (SETUP_ERROR statt Endlos-Retry). |
| AR-34 | ✅ behoben | Defensive `_require()` in Guard und Coordinator-Konstruktor (`ConfigEntryError` statt KeyError), `Category`-Fallback auf „II". |
| AR-35 | ✅ behoben | Reconcile-Stempel differenziert: Belief==Real → restaurierte Dwell behalten; Real=ON → now (min-on schützt); Real=OFF → in die Vergangenheit (kein Phantom-min-off blockiert den ersten ON/Frost-Override nach Neustart). |
| AR-36 | ✅ behoben | `minor_version=1` wird mitgeschrieben (Assert im Migrationstest); der >2-Guard ist als bewusst defensiv/toter Code dokumentiert. |
| AR-37 | ✅ behoben | binary_sensor-Docstring: „controls_boiler-only", „this entity itself never writes", S2-Aktuation korrekt beschrieben. |
| AR-38 | ✅ behoben | sensor_watchdog-Docstring beschreibt jetzt die reale Degradation des Regelausgangs (Safe-State), nicht mehr „without altering the control output". |
| AR-39 | ✅ behoben | ADR-0038 Nachtrag: Pull statt Push-Registry, kein ResourceRelease-Rückkanal (Contract als reserviert markiert). |
| AR-40 | ✅ behoben | ADR-0007 Nachtrag: Counter+Dirty statt Debounce, Existenz-Guard statt `_check_entities_ready`. |
| AR-41 | ✅ getestet | `test_setup_retry_when_temp_sensor_missing` + `test_setup_loads_when_required_sensor_unavailable` auf main. |
| AR-42 | ✅ getestet | Werfender Park, unavailable Aktor, never-actuated-Skip. |
| AR-43 | ❌ offen | `conftest.py` unverändert — das Integrationsverzeichnis wird ohne HA weiterhin still (collect_ignore_glob) übersprungen statt sichtbar geskippt. Niedrig/strukturell. |
| AR-44 | ✅ behoben + getestet | `_remove_trace_file` löscht auch `<entry_id>.jsonl.1`; Store-Remove-Suppression auf `(OSError, HomeAssistantError)` verengt + geloggt. |

**Bilanz: 35 von 44 vollständig umgesetzt, 3 teilweise (AR-07, AR-10, AR-19), 4 offen (AR-06 auf main, AR-14, AR-26, AR-43), 1 ohne Handlungsbedarf (AR-27), 1 durch diesen Branch geschlossen (AR-06).**
Alle sechs Hoch-Findings sind auf main behoben; von den Hoch-Findings bleibt nur die Testlücke AR-06 offen, die dieser Branch schließt.

## Neuer Befund aus der Verifikation

**AR-45 · niedrig · begründeter Verdacht — Hub-Remove löscht den neuen `PoiseHubStore` nicht.**
`_remove_hub_entry` **liest** den Hub-Store (`has_actuated`-Gate, AR-15), ruft aber nie
`PoiseHubStore.async_remove()`. Der Store ist entry-id-unabhängig (`poise_system_hub`): Wird der Hub
gelöscht und später neu angelegt, erbt die neue Installation `has_actuated=True` und den alten
`boiler_on`-Glauben — (a) der Remove eines **nie** aktuierenden Nachfolge-Hubs feuert trotzdem OFF
(genau das Verhalten, das AR-15 verhindern sollte), (b) der erste Tick des neuen Hubs restauriert
eine fremde Dwell/Belief. Das eigene Muster (F15: `PoiseStore.async_remove()` beim Raum-Delete)
wird hier nicht angewendet. Fix: `await PoiseHubStore(hass).async_remove()` am Ende von
`_remove_hub_entry` (im `finally`). Testidee: Hub mit `has_actuated=True` löschen → Store-`load()`
liefert `None`; zweiten Hub anlegen und sofort löschen → kein `turn_off`.

## Restarbeiten (priorisiert)

1. **AR-45** (neu): Hub-Store beim Hub-Delete entfernen — kleiner Fix, verhindert vererbtes `has_actuated`.
2. **AR-10**: `device_min` auch in `_park_room_actuator` übergeben (`st.attributes["min_temp"]` liegt dort bereits vor).
3. **AR-07**: den vakanten Alt-Test `test_remove_hub_swallows_off_failure` löschen oder auf beide Actions + Hub-Store-Seed umverdrahten (die Fehlerpfad-Tests dieses Branches decken das Verhalten bereits ab).
4. **AR-04**: kleiner Regressionstest „Options-Save erhält den live gepinnten climate_mode".
5. **AR-14/AR-26/AR-43**: bewusst offen lassen oder als Low-Prio-Hygiene nachziehen (Restrisiken klein und dokumentiert).


---

# Nachtrag 2 (2026-07-10): Abgleich mit einem externen Review

Ein extern zugeliefertes Review (bezogen auf Commit `b4730e760`, den Basis-Stand dieses Reviews)
meldet drei „verbleibende kritische Abweichungen" und liefert zwei Refactoring-„Blueprints". Der
Abgleich gegen den tatsächlichen Code und den HA-Core-Lifecycle ergibt: **ein Claim ist ein
Duplikat bereits erfasster Findings (mit einem als Wörtlich-Zitat präsentierten, im Repo nicht
existierenden Code-Snippet und einem Fix-Vorschlag, der zwei Regressionen einführen würde); zwei
Claims beruhen auf falschen Annahmen über den HA-Core und sind widerlegt.** Ein berechtigter
Teilaspekt aus Claim 1 wird unten als neues Finding **AR-46** aufgenommen.

## Claim 1: „Die Kessel-Abschaltgarantie versagt" — Duplikat (AR-07/AR-15/AR-29), Kern-Teilaspekt neu (AR-46)

**Zutreffend (am Stand `b4730e7`):** `_remove_hub_entry` fing die OFF-Exception und lief weiter,
während der F27-Docstring „observed not swallowed" suggerierte. Genau das war bereits erfasst:
AR-07 (Docstring beschreibt anderes Verhalten; der einzige Fehlerpfad-Test war vakant), AR-29
(zu enge except-Tuple → Issue-Cleanup übersprungen), AR-15 (OFF rein verdrahtungsbasiert). In
v0.160.0 ist der Pfad umgebaut (Timeout, `finally`-Cleanup, `has_actuated`-Gate). Anmerkung zur
Quellentreue: das im externen Review als Code-Zitat präsentierte Snippet
(`"Poise: failed to execute boiler-off action during remove: %s"`) existiert im Repo nicht —
tatsächlich lautet die Zeile `"Poise: boiler OFF on hub removal failed"`.

**Falsch am Blueprint — nicht übernehmen:**

1. **Die Kernprämisse ist eine falsche HA-Annahme.** „Re-raise blockiert das Löschen des
   Config-Entries aktiv" stimmt nicht: HA-Core ruft `async_remove_entry` in
   `ConfigEntry.async_remove` innerhalb eines `try/except Exception` mit Log auf und **entfernt
   den Entry unabhängig vom Ausgang**. Ein `raise` verhindert die Löschung nicht — es würde nur
   (vor dem AR-29-`finally`-Umbau) das Issue-Cleanup überspringen. Ironischerweise ist das exakt
   die Fehlerklasse, die dieses Review jagt: plausibel klingender Code auf Basis einer falschen
   Lifecycle-Annahme.
2. **Der Blueprint bricht das F12-/AR-15-Gate.** Er feuert OFF, sobald NUR die OFF-Action
   konfiguriert ist — ein shadow-only Hub würde damit einen Kessel abschalten, den eine fremde
   Automation führt (genau der Fehler, den das Repo bewusst vermeidet und den v0.160.0 mit dem
   persistierten `has_actuated` weiter verschärft hat).
3. **Das Parsing ist falsch.** `off_action.split(".", 1)` zerlegt das Repo-Format
   `entity_id/domain.service` (z. B. `switch.boiler/switch.turn_off`) in `domain="switch"`,
   `service="boiler/switch.turn_off"` und verliert die `entity_id`-Daten komplett — der
   Service-Call wäre kaputt. Das Repo hat dafür `parse_service_action`.
4. Das Timeout (AR-24) fehlt — ein hängender Boiler-Stack würde die Entfernung wieder
   unbegrenzt stallen.

### AR-46 · mittel · Verbesserungsvorschlag (aus Claim 1 destilliert)

**Ein fehlgeschlagener Boiler-OFF beim Remove/Hand-over ist nur im Log sichtbar — keine
nutzer-sichtbare Warnung.** Da HA die Entfernung ohnehin nicht blockieren lässt (s. o.), ist die
richtige Härtung nicht `raise`, sondern **Sichtbarkeit**: schlägt der OFF in `_remove_hub_entry`
oder `async_fire_boiler_off` fehl (Exception oder Timeout), sollte eine
`persistent_notification` (und/oder ein nicht-entry-gebundenes Repair-Issue) erzeugt werden:
„Poise wurde entfernt, der Kessel-OFF konnte nicht bestätigt werden — Kesselzustand manuell
prüfen." Fundstelle: `custom_components/poise/__init__.py` (`_remove_hub_entry`, except-Zweig)
und `hub_coordinator.py` (`async_fire_boiler_off`). Realbetriebsschaden: ungewolltes Dauerheizen
nach Deinstallation bleibt unbemerkt, bis es jemand physisch feststellt (schmales Fenster —
OFF-Fehler exakt zum Entfernzeitpunkt, aber plausibel korreliert: beim Rückbau ist das Gateway
oft gerade offline). Testidee: Remove mit werfendem `turn_off` bei `has_actuated=True` →
`persistent_notification.async_create` wurde gerufen.

## Claim 2: „Endlose Migrationsschleife bei jedem Systemstart" — widerlegt

Die Behauptung, bei `entry.version == 2` durchlaufe die Integration „bei jedem HA-Neustart die
komplette Migrations-Pipeline" und schreibe „die JSON-Konfiguration zyklisch neu", ist eine
falsche Annahme über den HA-Core: **HA ruft `async_migrate_entry` nur auf, wenn
`(version, minor_version)` des Entries ÄLTER ist als die im Flow deklarierte Version**
(`PoiseConfigFlow.VERSION = 2, MINOR_VERSION = 1`). Bei Gleichheit wird die Funktion beim Start
gar nicht betreten — es gibt keinen zyklischen Disk-Write und keine Schleife; das galt auch schon
am Stand `b4730e7`. Der wahre Kern des Themas — fehlendes `minor_version`-Pinning als *latentes*
Jeden-Boot-Risiko bei einem künftigen Minor-Bump — war bereits **AR-36** und ist in v0.160.0
behoben (`async_update_entry(..., version=2, minor_version=1)`), zusätzlich e2e als idempotent
getestet (AR-19). Der vorgeschlagene Blueprint (`if entry.version == 2: return True` früh raus)
wäre toter Code — und er **lässt das `minor_version`-Pinning weg**: ihn zu übernehmen wäre eine
Regression gegenüber main.

## Claim 3: „Stumme Desynchronisation bei Optionen-Updates" — widerlegt

Die Behauptung, bei `structural_unchanged == False` laufe die Integration „stumm mit den alten
Parametern weiter", weil `_async_options_updated` keinen Reload auslöse, verkennt die
HA-Reconfigure-Mechanik: **strukturelle Felder sind über den Options-Flow gar nicht änderbar.**
Sie ändern sich ausschließlich über den Reconfigure-Flow, und dessen
`async_update_reload_and_abort` (config_flow.py) löst den Reload **selbst** aus — der
Update-Listener feuert dabei VOR dem Reload, und der frühe Return ist exakt die dafür nötige
F14-Behandlung: der todgeweihte Coordinator darf nicht mehr hot-appliken (die
update-then-reload-Reihenfolge wurde in diesem Review gegen den HA-2025.1-Quelltext verifiziert,
siehe AR-01/AR-04-Verifikationsprotokolle). Ein Options-only-Save lässt `entry.data` unberührt →
`structural_unchanged == True` → Hot-Apply läuft. Es existiert kein Pfad, auf dem sich
`entry.data` ändert, ohne dass ein Reload folgt (Migration läuft im Setup; `config_reconcile`
nur innerhalb des Reconfigure-Flows). Der implizit vorgeschlagene Fix — ein zusätzliches
`async_reload` im Listener — würde bei jedem Reconfigure einen **Doppel-Reload** erzeugen
(Flow-Reload + Listener-Reload): eine Verschlechterung.

## Randnotiz zum Lob-Teil des externen Reviews

Zwei der gelobten Architektureigenschaften sind sachlich falsch beschrieben: (a) „Raum-Einträge
pushen ihre Daten flussabwärts" — tatsächlich **pullt** der Hub die Zonen-Snapshots aus
`entry.runtime_data` (`_collect_requests`; die ursprünglich in ADR-0038 beschriebene
Push-Registry existiert nicht, siehe AR-39 und den ADR-Nachtrag); (b) „Schattenwerte werden
strikt isoliert" — die `_hum_action` des als „SHADOW (diagnostic only, no writes)" kommentierten
Blocks trieb den live wirksamen Dry-Mode-Nudge (AR-32, Kommentar in v0.160.0 korrigiert).

**Fazit:** Übernommen wird ausschließlich AR-46 (Sichtbarkeit eines fehlgeschlagenen
Hand-over-/Remove-OFF). Beide Blueprints sollten **nicht** umgesetzt werden — der erste führt
zwei Regressionen und eine falsche Sicherheitszusage ein, der zweite entfernt einen bereits
implementierten Fix. Die Restarbeiten-Liste aus Nachtrag 1 erweitert sich damit um: **AR-46 nach
Priorität zwischen Punkt 1 (AR-45) und Punkt 2 (AR-10) einordnen** — beide betreffen denselben
Codepfad (`_remove_hub_entry`) und lassen sich in einem Zug umsetzen.
