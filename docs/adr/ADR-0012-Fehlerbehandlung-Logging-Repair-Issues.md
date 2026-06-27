# ADR-0012: Fehlerbehandlung, Logging & Repair-Issues

**Status:** Implementiert · **Datum:** 2026-06-18 · **Bezug:** E3, E26 · **Verifizierung:** Code-Review RoomMind/BT/ThermoSmart/Versatile (Thema H)

## Kontext
Die Charta verlangt „robust, aber nicht versteckt" (G15) und eine klare Trennung „degradieren vs. werfen" (E3). Offen: Ausnahme-Taxonomie, Nutzer-Meldungen, Logging.

## Entscheidungstreiber
Eine schlechte Zone/ein Sensor darf nie das Gesamtsystem kippen; Probleme sichtbar machen, ohne zu spammen; persistente vs. akute Probleme richtig kanalisieren; auditierbares Logging.

## Befund am Code (Belege)
- **Tick-Fehler:** ThermoSmart kapselt den ganzen Tick in `except → raise UpdateFailed(...)` (HA markiert „unavailable", retry). RoomMind/BT isolieren **pro Raum/Aktor** (`for area: try/except: _LOGGER.exception(... skipping)`, BT `asyncio.gather(return_exceptions=True)` + re-queue). Versatile = **ungeschützte Propagation** (Negativbeleg).
- **Repair-Issues:** **Better Thermostat = Goldstandard** — vier instanz-keyed Klassen via `issue_registry` (`missing_entity` fixable/Severity-gestaffelt, `degraded_mode` mit 5-min-Startup-Grace, `invalid_window_state`, `invalid_external_temperature`), Auto-Delete bei Recovery, zentrales Cleanup in `async_remove_entry`. **Lehre aus BT-Bug:** `invalid_external_temperature` wird geworfen, hat aber **keinen** `translations`-Eintrag → Repair ohne Text. RoomMind: ein Key `restart_required` (fixable, Restart-Flow). ThermoSmart/Versatile: **keine** Repair-Issues.
- **persistent_notification:** ThermoSmart Heizausfall create-once (`notification_id=…_{zone_id}`) + dismiss bei Erholung, im Observation-Mode deaktiviert. RoomMind: Außentemp-Watchdog analog.
- **Logging:** alle vier staffeln bewusst `debug`/`warning`/`error`/`exception`; „fail open" für nicht-sicherheitskritische Detektoren (Versatile Template-Eval).
- **Diagnostics:** RoomMind+BT bieten `async_get_config_entry_diagnostics` — **aber ohne `async_redact_data`** (rohe Entity-/Personen-IDs; Gap). ThermoSmart/Versatile: kein Endpoint (Versatile hat Log-Download).

## Entscheidung
1. **Zweistufige Ausnahme-Taxonomie:** *degradierbar* (Sensor stale/unplausibel → Degradationsleiter + `warning`, Tick läuft weiter) vs. *Tick-fatal* (→ `UpdateFailed`). **Äußerer `UpdateFailed`-Mantel** (ThermoSmart) **plus innere Pro-Zone-`try/except`-Isolation** (RoomMind/BT) — eine Zone killt nie den Tick.
2. **Repair-Issues für persistente Konfig-/Verfügbarkeitsprobleme** (BT-Muster: instanz-keyed, `is_fixable`-differenziert, Severity-gestaffelt, Startup-Grace, Auto-Delete bei Recovery). **Pflicht-CI-Check: jeder `translation_key` hat einen Übersetzungseintrag** (BT-Bug vermeiden).
3. **`persistent_notification` für akute, handlungsrelevante Ereignisse** (Heizausfall): create-once + dismiss-on-recovery mit stabiler `notification_id`.
4. **Logging-Konvention:** `debug`=erwartete Skips, `warning`=degradiert-aber-läuft, `error`=echter Fehler mit definierter Degradation, `exception`=unerwarteter Crash (mit Weiterlaufen, wo möglich). „Fail open" nur für nicht-sicherheitskritische Detektoren.
5. **Diagnostics-Endpoint anbieten — mit `async_redact_data`** (Entity-IDs, Personen, Koordinaten); optional Log-Download (Versatile).

## Begründung
Die Kombination nimmt das HA-konforme Degradieren (ThermoSmart-Mantel), die Ausfallisolierung (RoomMind/BT) und den reifsten Meldekanal (BT-Repairs) — und schließt die zwei belegten Lücken (fehlende Redaktion, fehlender Translation-Eintrag). Akut ≠ persistent wird sauber getrennt (Notification vs. Repair).

## Konsequenzen
**Positiv:** robustes Weiterlaufen; sichtbare, restart-feste Konfigprobleme; keine Notification-Spam; datenschutzkonforme Diagnostics.
**Negativ/Kosten:** Repair-Katalog + Übersetzungen + CI-Check sind Pflegeaufwand; zweistufige Taxonomie muss konsequent angewandt werden.

## Compliance
Allgemeine HA-Mechanismen; eigenständig umgesetzt. Redaktion erfüllt G28.

## Verknüpfungen
Stützt G15 (sichtbare Degradation) aus ADR-0006/0007. Repair-Issues ergänzen den Bootstrap-Race-Guard (ADR-0007). Logging/Tests in ADR-0011.
