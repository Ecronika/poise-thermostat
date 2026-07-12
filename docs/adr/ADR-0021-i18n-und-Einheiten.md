# ADR-0021: i18n-Struktur & Einheiten

**Status:** In Arbeit (70 %) · **Wirkung:** teilw. · **Datum:** 2026-06-18 · **Bezug:** E29 · **Verifizierung:** Code-Review ThermoSmart/Versatile/BT/RoomMind/Vesta (Thema N)

## Kontext
Mehrsprachigkeit erhöht die Reichweite (ThermoSmart: 24 Sprachen). Offen: Quellstruktur, Abdeckung, Sprachpflege, Einheiten.

## Entscheidungstreiber
Eine Übersetzungsquelle; vollständige Abdeckung (Flow, Entities, Services, Repairs); wartbare Sprachpflege; korrekte Einheiten-Lokalisierung.

## Befund am Code (Belege)
- **Sprachzahl:** ThermoSmart **24**, Versatile **10**, BT **10**, RoomMind **2** (de/en), Vesta **2** (en/it).
- **Quelle/Abdeckung:** alle haben `strings.json` an der Basis. **Versatile am vollständigsten** (`config`, `entity` inkl. `state_attributes`, `services`, `exceptions`, `selector`, `options`); **BT zusätzlich `issues` (Repair-Issues) + `device_automation`**. ThermoSmart deckt config + entity über 24 Sprachen.
- **Einheiten:** RoomMind liest die HA-Einheit korrekt aus (`hass.config.units.temperature_unit`), hardcodet **kein** °C; Zahl-/Datumsformat dem Frontend überlassen.

## Entscheidung
1. **`strings.json` als alleinige Quelle**, mit voller Abdeckung aus Versatile + BT zusammen: **config-flow + options + entity (inkl. `state_attributes`) + services + exceptions + issues (Repair) + selector + device_automation**. Das verknüpft direkt ADR-0012 (jeder Repair-`translation_key` braucht einen Eintrag).
2. **Übersetzungen nicht von Hand pflegen**, sondern aus `strings.json` generieren (Crowd/Tooling) — ThermoSmarts 24-Sprachen-Stand ist nur so haltbar.
3. **Start mit en + de** (eigene Basissprachen), Ausbau über Crowd-Übersetzung; jede neue Sprache muss alle Bereiche abdecken (CI-Vollständigkeitscheck gegen `strings.json`-Keys).
4. **Einheiten immer aus `hass.config.units` lesen** (RoomMind-Muster), nie °C hartcodieren; `native_unit_of_measurement` je Sensor korrekt deklarieren; Zahlen-/Datumsformat dem HA-Frontend überlassen.

## Begründung
Eine einzige Quelle + Tooling ist die einzige skalierbare Sprachpflege (ThermoSmart-Beleg). Die Abdeckung muss Repairs/Services einschließen, weil sonst genau der BT-Bug (Repair ohne Übersetzung) entsteht. Einheiten aus `hass.config.units` ist die einzige locale-korrekte Variante.

## Konsequenzen
**Positiv:** lokalisiertes Erlebnis inkl. Repairs/Services; wartbare Sprachskalierung; korrekte °C/°F-Behandlung.
**Negativ/Kosten:** Tooling-/Crowd-Prozess nötig; CI-Vollständigkeitscheck pflegen; jede neue UI-Zeichenkette muss in `strings.json` gepflegt werden.

## Compliance
Standard-HA-i18n; eigenständig umgesetzt.

## Verknüpfungen
Repair-Übersetzungen verknüpft mit ADR-0012; Entity-Attribut-Namen mit ADR-0016; Vollständigkeitscheck = CI-Gate aus ADR-0011.
