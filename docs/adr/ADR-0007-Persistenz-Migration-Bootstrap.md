# ADR-0007: Persistenz, Migration & Bootstrap

**Status:** akzeptiert · **Datum:** 2026-06-18 · **Bezug:** E7, E8, K15 · **Verifizierung:** Code-Review RoomMind/BT/Vesta/ThermoSmart/Versatile (Thema C)

## Kontext
Persistenzverlust bei Reload ist ein dokumentierter Hebel des eigenen Stacks; der Strukturplan verlangt koordinierten Bootstrap vor dem ersten Tick (K15). Offen: Mechanismus, Versionierung/Migration, Restore-Reihenfolge, Speicherhäufigkeit.

## Entscheidungstreiber
Kein Lernverlust bei Reload/Update; robuste Migration + Korruptionsschutz; keine Steuerung auf Leerzustand (Startup-Race); sparsames, verlustfreies Speichern.

## Befund am Code (Belege)
- **RoomMind:** zentraler `Store` (`STORAGE_VERSION=1`) + **eingebettete `ekf_version` je Lerneinheit** (`thermal_model.to_dict()` schreibt `"ekf_version": 6`; `from_dict()` macht Dimensions-Migration 5→6 **und Korruptions-Recovery**: bei gepegtem `alpha` RC-Parameter auf Default zurück, **Counter/T-State/Modi behalten** → „MPC-Gates bleiben erfüllt, Filter fällt sanft auf Bang-Bang bis Re-Learn"). Restore vor erstem Tick via `_model_loaded`-Guard; Konfidenz aus Bestand rekonstruiert. Throttle: zyklen­gezählt (`THERMAL_SAVE_CYCLES=30`).
- **Better Thermostat:** Hybrid `RestoreEntity` + dedizierter `Store` pro Entry (`StateManager`); **zwei Versionsachsen** (Config `VERSION=18` + `async_migrate_entry` Ketten-Migrationen; Store `CURRENT_VERSION=1` + `_migrate_v0_to_v1` + Korruptionsschutz „starting fresh"). **Stärkster Race-Guard:** `async_at_started` → `_check_entities_ready` (Loop bis Sensor+alle TRVs bereit) → `_restore_state` → erst dann erste Trigger; `_available=False` bis fertig. Throttle: **echtes Debounce** `schedule_save_state(15 s)`, dirty-tracked, Flush bei Unload. (Korrektur: `_MpcState` hat **35** Felder, nicht 41.)
- **Vesta:** nur `RestoreEntity` für Lernzustand (nicht versioniert), `Store` nur für Zeitpläne; Config `VERSION=7`. Kein Persistenz-Throttle.
- **ThermoSmart:** geteilter `Store`, `async_load` endet mit `_rebuild_confidence()` **vor** `async_config_entry_first_refresh()`; Migrationsfunktion faktisch Stub. Count-throttled, kein Debounce.

## Entscheidung
**Hybrid nach BT/RoomMind:**
1. **Lerndaten in dediziertem `Store`** (nicht nur RestoreEntity-Attribute wie Vesta/Versatile) — robuster, größerer Umfang, vom Entity-Lebenszyklus entkoppelt. Laufzeit-/UI-Zustand zusätzlich über `RestoreEntity`.
2. **Zwei Versionsachsen** (Config-Entry `VERSION` + `async_migrate_entry`; separate Store-/Lernschema-Version) **plus eingebettete Versions-IDs je Lerneinheit** (`ekf_version`-Muster) für Feld-/Dimensions-Migration **und Korruptions-Recovery**: Parameter zurücksetzen, **Counter behalten**, automatischer Rückfall auf Bang-Bang bis Re-Konvergenz. Das adressiert direkt den Persistenzverlust-Hebel.
3. **Restore strikt vor erstem Steuertick** + Race-Guard: BTs `_check_entities_ready`-Loop (auf Sensoren/TRVs warten) als robustestes Muster, minimal RoomMinds `_model_loaded`-Flag; Konfidenz aus Bestand rekonstruieren.
4. **Throttle = Debounce** (BT-Muster: `async_call_later`, dirty-tracked, Flush bei `HOMEASSISTANT_STOP`) — schreibt nur bei echter Änderung, kein Verlust beim Shutdown.

## Begründung
BT und RoomMind haben den reifsten Persistenz-/Recovery-Apparat; ihre Kombination deckt genau die Schwächen ab, die Vesta/ThermoSmart zeigen (kein versionierter Lern-Store, Stub-Migration). RoomMinds „Counter behalten, Parameter zurücksetzen"-Recovery ist die elegante Antwort auf korrupten Zustand ohne Lernverlust.

## Konsequenzen
**Positiv:** kein Lernverlust bei Reload; saubere Updates ohne Datenverlust; keine Fehl-Entscheidung direkt nach Neustart; verlustfreies, sparsames Speichern.
**Negativ/Kosten:** mehr Migrations-/Recovery-Code; zwei Versionsachsen erfordern Disziplin; Wartepfad (`_check_entities_ready`) verzögert den ersten Tick bewusst (akzeptiert).

## Compliance
Persistenzmuster allgemeingültig, eigenständig umgesetzt; anonymisierte Exporte separat (G28).

## Verknüpfungen
Nutzt die monotone Uhr + Wall-Clock-Anker aus ADR-0006. Persistiert die Verträge/Zustände aus ADR-0002/0005. Bootstrap-Reihenfolge ist Teil der Tick-Initialisierung (ADR-0006).
