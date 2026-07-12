# ADR-0038: Mehrzonen-Hub & Zwei-Phasen-Tick

**Status:** Implementiert (S0–S2 live; S3/S4 Load-Shedding/Verdichtergruppen als Diagnose/Shadow — zonenseitige Durchsetzung folgt, Review 2026-07-08 F25) · **Wirkung:** teilw. · **Datum:** 2026-06-22 · **Bezug:** ADR-0013 (Mehrzonen-Entscheidung), ADR-0035 (Constraint-Solver), ADR-0026/0033 (Schatten-Prinzip), ADR-0006 (monotone Zeit), ADR-0005 (Datenverträge/Schichtgrenzen), ADR-0011 (Harness) · **Verifizierung:** Community-Meinungsbild + `Designskizze_ADR-0013_Mehrzonen-Solver.md`; Harness-Validierung ab S0

## Kontext
Poise ist heute strikt **eine Zone = ein ConfigEntry = ein unabhängiger `PoiseCoordinator`** (60-s-Tick). Geteilte Ressourcen — gemeinsamer Kessel, elektrisches Leistungsbudget, geteilte Außeneinheit/Verdichter, Vorlauftemperatur — lassen sich so nicht koordinieren. ADR-0013 hat die *Entscheidung* (Zwei-Phasen, Smallest-Gap-Shedding, Verdichterschutz, Vorlauf-Allokator) getroffen; dieser ADR legt die **ausführende Architektur** fest, ohne die tragenden Invarianten zu brechen: Single-Writer je Aktor, Schatten-Prinzip, präzedenz-expliziter Solver. Das Community-Meinungsbild verschärft zwei Randbedingungen: der reale Schmerz ist **Heizquellen-Synchronisation**, und **Komplexität ist ein Adoptions-Killer** → Mehrzonen muss optional/unsichtbar bleiben.

## Entscheidungstreiber
Konsistente Entscheidungen auf demselben Zustand; Zonen-Autonomie + Ausfallisolierung; Single-Writer auch für geteilte Aktoren; Null-Konfig und Abwärtskompatibilität bei einer Zone.

## Entscheidung
1. **Zwei-Phasen-Tick.** *Phase 1:* jede Zone rechnet **isoliert** (`try/except`) und schreibt am Tick-Ende eine frozen **`ZoneRequest`** in eine In-Memory-Registry `hass.data[DOMAIN]["hub"]`. *Phase 2:* ein separater **`PoiseHubCoordinator`** (eigener ConfigEntry „Poise System", analog dem feld-üblichen Master-/System-Gerät) liest alle `ZoneRequest`, löst die geteilten Ressourcen **frost-sicher** auf und schreibt je Zone eine **`ResourceRelease`** zurück.
2. **Hub = alleiniger Schreiber geteilter Aktoren** (Kesselschalter, Verdichter-Master). Zonen bleiben alleinige Schreiber ihres **eigenen** Aktors. Damit gilt das Ein-Schreiber-Prinzip (ADR-0013) auch global.
3. **Der Hub aktuiert keine Zonen.** Er publiziert nur **Caps** (`ResourceRelease`), die jede Zone in ihren **eigenen** Solver (ADR-0035) als zusätzliche `Cap`-Schranke hoher Präzedenz einspeist. Keine zweite Arbitrierungslogik — dieselbe Solver-Algebra (Floor=max/Cap=min, Inversion nach Präzedenz) **eine Ebene höher**.
4. **Datenverträge** (`contracts.py`, frozen-slots): `ZoneRequest(zone_id, heating, hvac_action, heat_demand, declared_power?, flow_temp_request?, comfort_gap, frost_active, controls_boiler, source_pref?, compressor_group?, mono_ts)` und `ResourceRelease(zone_id, power_cap?, shed, source_grant?, mono_ts)`. Stale-Erkennung über `mono_ts` (ADR-0006).
5. **Schatten zuerst** (ADR-0026/0033): jede Auflösung geteilter Ressourcen rechnet erst nur mit und wird als Diagnose exponiert, bevor sie schreibt.
6. **Optional/unsichtbar:** kein Hub-Entry bei einer Zone; das „Poise System"-Onboarding erscheint nur bei ≥2 Zonen **oder** konfigurierter geteilter Ressource. Leere Registry → Zonen verhalten sich **exakt** wie heute.

## Begründung
RoomMinds Zwei-Phasen-Skelett ist die am Code belegte Bestlösung; die **Cap-statt-Direktbefehl**-Mechanik hält Poise's Single-Writer- und Schatten-Disziplin auch zonenübergreifend ein und vermeidet einen zweiten Regler. Die Registry entkoppelt die unabhängig taktenden Zonen vom Hub ohne harte Reihenfolgekopplung.

## Konsequenzen
**Positiv:** konsistente, isolierte Entscheidungen; Zonen-Autonomie + Ausfallisolierung; Single-Writer global gewahrt; Null-Konfig bei einer Zone; nur **eine** Arbitrierungs-Algebra.
**Negativ/Kosten:** Tick-Versatz — der Hub arbeitet auf einem ≤60 s alten `ZoneRequest` (für Kessel/Anti-Takt unkritisch, große Zeitkonstanten; `mono_ts` erlaubt Stale-Erkennung); neuer Zwischenzustand (Registry) muss sauber gehalten und bei Unload bereinigt werden; zusätzlicher ConfigEntry-Typ.

## Compliance
Generisch (Rollen/Geräte/Gruppen als Parameter), keine geräte-/herstellerspezifische Logik; HA-freie pure Helfer für die Auflösung (testbar), HA-Glue dünn.

## Verknüpfungen
Konkretisiert ADR-0013 (Strukturplan-Ebene 5); nutzt ADR-0035 (Solver), ADR-0006 (monotone Zeit), ADR-0005 (Verträge). Liefert gedeckelte Freigaben an die Zonen-Arbitrierung. **ADR-0039** (Kesselbedarf-Aggregat) ist der erste Konsument.

## Nachtrag/Korrektur (Ist-Stand v0.159)
Die ausgelieferte Umsetzung weicht in der **Transportmechanik** von Punkt 1/3/4 ab; die tragenden Invarianten (Single-Writer, Schatten-zuerst, eine Solver-Algebra, Stale-Erkennung über `mono_ts`) bleiben unberührt:

- **Pull statt Push-Registry.** Es gibt **keine** In-Memory-Registry `hass.data[DOMAIN]["hub"]`, in die Zonen ihre `ZoneRequest` schreiben. Der `PoiseHubCoordinator` **zieht** die Zonenzustände in `_collect_requests`: er iteriert `hass.config_entries.async_entries(DOMAIN)` und liest je Zone den zuletzt publizierten Snapshot aus `entry.runtime_data.data` (geprüft auf `available`, `last_update_success` und `mono_ts`-Alter). Die `ZoneRequest`-Objekte werden dabei hub-seitig aus dem Snapshot gebaut. Die Entkopplung der unabhängig taktenden Zonen entsteht aus diesem gepufferten `runtime_data`-Snapshot, nicht aus einer geteilten Registry.
- **Kein `ResourceRelease`-Rückkanal.** Der Hub schreibt **keine** per-Zone-`ResourceRelease` zurück. `_async_update_data` liefert ein **einfaches Diagnose-Dict** (`boiler_demand`, `active_zones`, Load-Shedding-/Verdichter-/Flow-Shadow …), das die Hub-Entitäten lesen. Die Zonen speisen aktuell **keinen** Hub-Cap in ihren Solver ein; die zonenseitige Cap-Durchsetzung aus Punkt 3 (S3/S4) ist noch offen. Der Datentyp `ResourceRelease` (`contracts.py`) ist daher **reserviert/ungenutzt** und dort so markiert.
- **Kesselaktuierung** liegt beim Hub (`if self._actuation`, opt-in); die Bedarfsaggregation zählt **nur** Zonen mit `controls_boiler` (ADR-0039). „Der Hub aktuiert keine Zonen" (Punkt 3) bleibt korrekt: er schaltet den **geteilten** Kessel, nicht die Zonen-Aktoren.
