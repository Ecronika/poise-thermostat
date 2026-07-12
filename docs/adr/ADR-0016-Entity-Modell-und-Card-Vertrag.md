# ADR-0016: Entity-Modell & Karten-Vertrag

**Status:** Implementiert · **Wirkung:** Live-D · **Datum:** 2026-06-18 · **Bezug:** E13, E14 · **Verifizierung:** Code-Review ThermoSmart/RoomMind/Vesta (Thema L)

## Kontext
Offen: welche HA-Entities das System exponiert und wie die Bedienkarte ihre Werte bezieht (sauberer Card/Integration-Vertrag).

## Entscheidungstreiber
Card liest aus stabiler, öffentlicher Schnittstelle (nicht aus privaten Coordinator-Feldern); Konfidenz dashboardfähig; Diagnose-Entities sauber kategorisiert; Reload-feste IDs.

## Befund am Code (Belege)
- **ThermoSmart = reichster Exposer (Prämisse „nur Attribute" widerlegt):** `climate.extra_state_attributes` liefert genau `weather_correction`, `boost_delta`, `forecast_suppression`, `learning_confidence`, `preheat_time`, `observation_mode` — **plus** `sensor.py` mit **15** Sensoren inkl. echtem `ThermoSmartConfidenceSensor` (`%`) und ENUM-`StatusSensor`. Echtes `DeviceInfo` je Zone (`entry_type="service"`).
- **RoomMind:** nur **2** Sensoren/Raum (Target, Mode), **keine Konfidenz-Entity** (Konfidenz nur im Diagnostics-Dump); **kein `device_info`** (flache Entities). Gap.
- **Vesta:** **11** Sensoren/Raum + eigenes Sidebar-Panel; `unique_id` aus gespeichertem `entry_id` („survives climate reload").
- **Niemand** nutzt `EntityCategory.DIAGNOSTIC` (ThermoSmart approximiert via `entity_registry_enabled_default=False`).

## Entscheidung
1. **Primäre `climate`-Entity je Zone** mit `extra_state_attributes` als **Card-Vertrag**: `weather_correction`, `boost_delta`, `forecast_suppression`, `learning_confidence`, `preheat_time`, `observation_mode` (+ die normspezifischen: `operative_temp`, `t_rm`, `comfort_band_low/high`, `binding_limit`, `binding_limit_cause`).
2. **Konfidenz als echte `sensor`-Entity** (nicht nur Diagnostics-Dump wie RoomMind) — dashboard-/automationsfähig.
3. **Lern-/Interna-Sensoren mit `entity_category = EntityCategory.DIAGNOSTIC`** taggen (Lücke aller drei) statt nur disabled-by-default.
4. **Ein `DeviceInfo` je Zone**, alle Entities daran gehängt (RoomMinds flaches No-Device-Modell vermeiden).
5. **`unique_id` aus gespeichertem `entry_id`** (Vesta-Lehre — überlebt Reload).
6. **Card liest EINE Quelle = climate-Attribute**; Standalone-Sensoren sind Automations-/History-Fläche → **saubere Card/Integration-Trennung**, kein Zugriff auf private `coordinator`-Felder. Das schließt direkt den offenen Hebel des eigenen SS-Card-Projekts (Blueprint muss Komfortwerte als Entity/Attribut exponieren).

## Begründung
ThermoSmarts Attribut-Vertrag ist das beste Card-Muster (stabile, öffentliche Fläche); seine fehlende Diagnostic-Kategorie, RoomMinds fehlende Konfidenz-Entity/`device_info` und die reload-feste ID (Vesta) sind die zu schließenden Lücken. Die Trennung „Card = climate-Attribute, Sensoren = History" verhindert die brüchige Kopplung an Interna.

## Konsequenzen
**Positiv:** dashboardfähige Konfidenz; saubere Geräte-Gruppierung; reload-feste Entities; Card unabhängig von internen Refactorings; Diagnose-Entities ausgeblendet, aber verfügbar.
**Negativ/Kosten:** mehr Entities (Diagnostic-Kategorie hält die UI dennoch aufgeräumt); der Attribut-Vertrag muss versioniert/stabil gehalten werden (Breaking-Change-Disziplin, ADR-0018).

## Compliance
Standard-HA-Entity-Muster; eigenständig umgesetzt; generisch.

## Verknüpfungen
Konsumiert Diagnose-Felder aus ADR-0007/0009/0013 (binding_limit_cause, confidence). Attribut-Vertrag unterliegt der Versionspolitik ADR-0018. Card-Trennung stützt ADR-0005 (keine privaten Felder über Grenzen).
