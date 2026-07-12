# ADR-0018: Versionierung, Semver & Deprecation

**Status:** In Arbeit (60 %) · **Wirkung:** teilw. · **Datum:** 2026-06-18 · **Bezug:** E25 · **Verifizierung:** Code-Review BT/Versatile/Vesta/RoomMind/ThermoSmart (Thema I)

## Kontext
Updates dürfen weder Lerndaten noch Konfiguration brechen (G25, ADR-0007). Offen: Versionsschema, Migrations- und Deprecation-Policy.

## Entscheidungstreiber
Saubere, kumulative Migration; Abwärtskompatibilität persistierter Zustände; nachvollziehbare Deprecations; eine Wahrheitsquelle für die Version.

## Befund am Code (Belege)
- **Versatile = Best-Practice-Migration:** `CONFIG_VERSION=2 + CONFIG_MINOR_VERSION=3`, `calculate_version=major*100+minor`, **kumulatives** `async_migrate_entry` (`if version <= 200/201/202`), durchgängig `.get(key, default)` + alte Keys `pop`, expliziter `# Deprecated`-Block in `const.py`, silent-migrate mit `info`-Log.
- **Better Thermostat:** `VERSION=18`, aber **nicht-kumulative** `if version == N`-Blöcke (Schwäche: v6–v17 verlassen sich auf vorhandene Keys); ein harter Pre-1.0-Deprecation-Guard (Re-Add statt Auto-Migration). Storage getrennt + **Legacy-Stores nicht gelöscht** („rollback remains possible").
- **RoomMind:** Entry trägt keine Daten (`VERSION=1`), alles im `Store` mit **read-time schema-toleranter** Migration (`room.get("comfort_temp", DEFAULT)`).
- **ThermoSmart:** `VERSION=1`, Migrations-Stub; **Versions-Inkonsistenz** manifest `1.1.1` ≠ `const.VERSION="1.0.8"` ≠ ConfigFlow.VERSION `1` (Negativbeleg).
- **Alle vier:** **kein `min_ha_version`** im manifest (gemeinsame Lücke).

## Entscheidung
1. **SemVer** für die Integration (major.minor.patch); Breaking Changes nur bei **major**-Bump, immer mit Migration.
2. **Config-Entry: getrennte `VERSION` + `MINOR_VERSION`, KUMULATIVES `async_migrate_entry`** (`if version <= N`, Versatile-Muster — **nicht** BTs `== N`), fallback-basiert (`.get(key, default)`, alte Keys `pop`), expliziter `# Deprecated`-Block, silent-migrate mit `info`-Log.
3. **Persistierte Lern-/Storage-Daten getrennt versionieren** (eigener `STORAGE_VERSION` + `_async_migrate_func` + eingebettete Per-Unit-Version, ADR-0007) — **abwärtskompatibel**: BTs „Legacy nicht löschen → Rollback möglich" **kombiniert mit** RoomMinds read-time schema-toleranter Migration.
4. **Deprecation-Policy:** ein zu entfernender Schlüssel/eine Option wird **eine Minor-Version vorher** mit Warnung markiert und per Fallback weiter gelesen, dann beim nächsten Major entfernt.
5. **manifest:** **`min_ha_version` setzen** (Lücke aller vier) + **eine** Versions-Wahrheitsquelle (ThermoSmart-Inkonsistenz manifest≠const≠Flow vermeiden — CI-Check auf Übereinstimmung).

## Begründung
Versatiles kumulatives, fallback-basiertes Schema ist am Code als robusteste Variante belegt; BTs Rollback-Sicherheit und RoomMinds Schema-Toleranz ergänzen es für die persistierten Zustände. Die zwei gemeinsamen Feldlücken (`min_ha_version`, Versionsquellen-Inkonsistenz) werden bewusst geschlossen.

## Konsequenzen
**Positiv:** kein Konfig-/Lernverlust über Updates; vorhersehbare Breaking-Changes; Rollback möglich; klare HA-Mindestversion.
**Negativ/Kosten:** kumulative Migrationskette muss bei jedem Schema-Schritt gepflegt werden; Deprecation-Fenster verlängert die Zeit, in der alte Keys mitgeschleppt werden; CI-Versionscheck nötig.

## Compliance
Standard-HA-Migrationsmechanismen; eigenständig umgesetzt.

## Verknüpfungen
Baut auf ADR-0007 (Persistenz/Migration) auf. Schützt den Card-Attribut-Vertrag aus ADR-0016. CI-Versionscheck gehört zu den Gates aus ADR-0011.
