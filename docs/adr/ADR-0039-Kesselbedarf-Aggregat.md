# ADR-0039: Kesselbedarf-Aggregat (Heizquellen-Synchronisation)

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-22 · **Bezug:** ADR-0038 (Hub/Zwei-Phasen), ADR-0013, ADR-0026/0033 (Schatten-/Stufen-Disziplin), ADR-0006 (monotone Zeit/Entprellung), ADR-0012 (Repair/Sicherheit), ADR-0011 (Harness) · **Verifizierung:** Harness (Kessel-Laufzeit-Reduktion, Frost-Override, Anti-Takt) + Live-Shadow; Community-Beleg `Meinungsbild_Mehrzonen-Koordination.md`

## Kontext
Meinungsbild-Befund Nr. 1: bei mehreren Zonen an **einem** gemeinsamen Erzeuger (Kessel/Brenner) läuft dieser quasi durchgehend, weil der Raumbedarf unsynchron ist. Die Community löst das überwiegend als **Eigenbau** (Template-Sensor `any-TRV-heating` → Relais/virtueller Sollwert). Versatile-Issue #234 zeigt den **feld-akzeptierten Zuschnitt**: ein `binary_sensor` „Kessel soll an" + Pro-Zone-Flag, das eigentliche Schalten optional als Nutzer-Automation. Dieser Zuschnitt bedient **beide** im Meinungsbild belegten Lager — die „gib mir nur das Signal"-Eigenbauer (samt Hardware-Failsafe) **und** die „mach es für mich"-Nutzer.

## Entscheidungstreiber
Den meistgenannten realen Bedarf treffen (Erzeuger seltener laufen lassen); Frost-Sicherheit zuerst; kein Verdichter-/Pumpen-Kurztakten; Vertrauen/Failsafe (deaktivierbarer Schreibpfad); Generizität.

## Entscheidung
1. **Aggregat im Hub** (ADR-0038, Phase 2): zählt Zonen mit `controls_boiler && heating` **gerätegenau** (heizende Ventile, nicht Zonen) und summiert die gewichtete Last (`declared_power` × Anforderung).
2. **Schwelle:** `demand = (Anzahl ≥ count_threshold) ODER (gewichtete Last ≥ power_threshold)`.
3. **Frost-sicher:** ist eine boiler-Zone in `frost_active`, erzwingt das `demand = on` **unabhängig** von der Schwelle.
4. **Entprellung/Schutz:** Aktivierungs-**Delay** (Ventilöffnungszeit — verhindert Pumpenlauf gegen geschlossene Ventile), **Min-On/Min-Off** und **Keep-Alive**-Resend, alle über `monotonic()` (ADR-0006).
5. **Pro-Zone-Flag `controls_boiler`** (Default **AUS** → opt-in) + optional `declared_power` für die gewichtete Schwelle.
6. **Aktion** im Format `entity_id/service_id[/attr:value]` (wie VT); Ein- und Aus-Aktion getrennt konfigurierbar; der Hub ist alleiniger Schreiber dieses Aktors.
7. **Stufenfreigabe:** *Stufe 1 (Shadow)* exponiert nur `binary_sensor.poise_boiler_demand` + Diagnose (`active_zones`, `weighted_demand`, `would_switch`) und **schreibt nichts** — der Nutzer kann sofort die eigene Automation darauf bauen. *Stufe 2 (opt-in, evidenz-gegated)* ruft die konfigurierte Aktion selbst.
8. **Failsafe:** der Schreibpfad (Stufe 2) bleibt jederzeit deaktivierbar; der Shadow-`binary_sensor` bleibt als **unterstützter Eigenbau-Modus** dokumentiert.

## Begründung
Trifft exakt den meistgenannten Bedarf; der `binary_sensor`+Flag-Zuschnitt ist feld-validiert (VT #234); shadow-first respektiert das Vertrauens-/Failsafe-Thema; gerätegenaue Zählung wie VT. Dass der **Hub** (nicht die Zonen) den Kessel schreibt, schließt konkurrierende Schreiber aus (Single-Writer, ADR-0038).

## Konsequenzen
**Positiv:** reduziert Erzeuger-Laufzeit/Takten (im Harness messbar — der Kernnutzen wird belegbar, was das Feld nicht zeigt); bedient DIY **und** Komplett-Automatik aus **einem** Signal; frost-sicher; kein Race (Hub Single-Writer).
**Negativ/Kosten:** Nutzer muss `controls_boiler` je Zone setzen (opt-in, aber Onboarding-Aufwand); Delay/Keep-Alive korrekt zu parametrieren; reale Wirkung erst nach Live-Shadow-Beleg zusichern.
**Sicherheitshinweis:** Kessel mit geschlossenen Ventilen einschalten kann Überdruck erzeugen — daher Aktivierungs-Delay (Ventilöffnung abwarten) und der Hinweis, dass kesselseitige Sicherheitsfunktionen vorhanden sein müssen (Repair-Issue bei implausibler Konfiguration, ADR-0012).

## Compliance
Generisch (Schwellen/Delays/Aktion als Parameter), keine herstellerspezifische Kessel-Logik; das Aggregat ist eine **pure, testbare Funktion**.

## Verknüpfungen
Erster Konsument von **ADR-0038**; folgt der Stufen-Disziplin von **ADR-0033** (Shadow→Live); nutzt **ADR-0006** (Entprellung); Repair-Sicherheit nach **ADR-0012**. Harness-Plan in `Designskizze_ADR-0013_Mehrzonen-Solver.md` (Abschnitt 11).

## Review-Nachträge (v0.45.0)
Aus dem Code-Review der Mehrzonen-Stufen behoben:
- **#1 Tick-übergreifende Orchestrierung jetzt pure + getestet:** Aktivierungs-Latch, Min-On/Min-Off und Keep-Alive liegen in `hub_aggregate.step_boiler` (`BoilerState`/`BoilerStep`) bzw. `step_min_cycle`; der Coordinator führt nur noch den zurückgegebenen Service-Call aus. Die hardware-schützende Logik ist damit unit-getestet statt 0 %-abgedeckt.
- **#2 Frost-Sicherheit über ALLE Zonen:** `frost_override = any(frost_active for alle requests)` — eine frostgefährdete Zone feuert den geteilten Kessel auch dann, wenn sie (fehlkonfiguriert) nicht opt-in ist. **→ abgelöst durch Korrektur #3 (v0.93.0); war zudem inkonsistent mit Entscheidung Punkt 3 (»boiler-Zone«).**
- **#3 Tote Drähte geschlossen:** `declared_power` (neues Raum-Feld) und `compressor_group` werden in den `ZoneRequest` durchgereicht → Lastabwurf (S3) und Verdichtergruppen (S4) rechnen end-to-end.
- **#4 Schimmel/Health geschützt:** `ZoneRequest.health_active` (aus Mould-Bindeursache); `resolve_load_shedding` wirft frost- **und** health-aktive Zonen nie ab. Vor zonenseitiger Durchsetzung muss der Shed-Cap unterhalb HEALTH komponieren.
- **#5/#6/#7 dokumentiert:** Verdichter erbt im Schatten die Boiler-Timer (eigene Min-Off vor Aktuierung nötig); der Zwei-Phasen-Tick ist asynchron (~60 s alte Zonen-Snapshots); `heat_demand` stammt aus dem tpi_duty-Schatten.

## Korrektur #2 (v0.46.0) — Frost war ein Schein-Fix
Der v0.45.0-„Fix" (`frost_override` über alle Zonen) war **kosmetisch**: das Eingangssignal `frost_active` wurde aus `"frost" in binding_lower_cause` abgeleitet, der Coordinator publiziert als Ursache aber **nur** `"mold"`/`"en16798"`, nie `"frost"` (der Frost-Floor ist die unterste Schranke und bindet die untere Ursache nie). `frost_active` war damit strukturell **immer False** → Frost-Override feuerte nie (latentes Einfrier-Risiko, das behoben *aussah*). **Echter Fix:** `frost_active` wird jetzt **physikalisch** aus der Raumtemperatur abgeleitet (`current_temperature <= FROST_FLOOR_C + 0,5 K`), und `zone_request_from_data` wurde in das **pure, 100 %-getestete** `hub_aggregate`-Modul verschoben (schließt die ungetestete-Ableitung-Lücke aus #1). Neuer End-to-End-Test: kalter Nicht-opt-in-Raum → `boiler_demand=True`.

## Korrektur #3 (v0.93.0) — Frost-Override wieder gegated (review #2 abgelöst)
review #2 (v0.45.0) hatte den Frost-Override bewusst auf **alle** Zonen verbreitert (`frost_override = any(frost_active …)`), explizit auch auf nicht-opt-in Zonen. Das war die **falsche** Voreinstellung: es weicht von der **Entscheidung** dieses ADR ab (Punkt 3 sagt »ist eine **boiler**-Zone in frost_active«) und steht konträr zum gesamten Feld. Externes Review (P1/2.1) + Wettbewerber- und Nutzer-Recherche (2026-06-28) belegen das.

**Befund:**
- **Wettbewerber einstimmig gegated.** Von sechs geprüften Integrationen haben nur **Versatile Thermostat** und **RoomMind** überhaupt einen geteilten Erzeuger — und beide feuern ihn **nur** aus opt-in/heizfähigen Zonen über echten Heizbedarf (`hvac_action==heating`), **nie** aus einem Frost-Failsafe. VTherm zählt nur VTherms mit Pro-Zone-Flag `is_used_by_central_boiler` (eine nicht-markierte Zone feuert den Kessel nie, egal wie kalt) und warnt ausdrücklich vor „blindem" Kesselfeuern (Druckrisiko bei geschlossenen Ventilen). RoomMind gated auf `can_heat` (nicht `cool_only`) + Mitgliedschaft + Geräte-Typ-Match (`room_contributes_to_group`). „Jede frierende Zone feuert den geteilten Kessel" hat **kein** Wettbewerber.
- **Nutzer-Konsens gegated.** Stärkstes Signal: ein defekter/fehlender Sensor soll **aus**fallen, nicht heizen (HA-core #63419: Thermostat klammert sich an Stale-Wert und heizt einen Raum auf ~30 °C; plus verbreitete Outlier-Filterung gegen −50/−127-Spitzen) — direkter Beleg für den Plausibilitäts-Floor. Die Frost-als-Failsafe-Fraktion existiert, verortet echten Frostschutz aber an **Hardware/TRV-Frostmodus/Frostwächter** (outage-fest), nicht an einer Multi-Zonen-Integration, die einen geteilten Kessel übersteuert.
- **Konsistenz mit der eigenen Designskizze.** `Designskizze_ADR-0013_Mehrzonen-Solver.md` hatte Frost ursprünglich auf **boiler-Zonen** (`controls_boiler`, opt-in) gegated; review #2 war die Abweichung. Diese Korrektur stellt die ursprüngliche Absicht wieder her.

**Entscheidung (v0.93.0):** Frost feuert den geteilten Kessel nur noch für eine Zone, die ihn auch **steuert** **und** einen **plausiblen** Messwert liefert:
- `frost_override = any(r.frost_active and r.controls_boiler …)`; die auslösende Zone wird als `BoilerDemand.frost_zone_id` + Hub-Diagnose `frost_zone` ausgewiesen.
- **Plausibilitäts-Floor** in `zone_request_from_data`: `frost_active` nur für `_FROST_PLAUSIBLE_MIN_C (−20 °C) ≤ room ≤ FROST_FLOOR_C + 0,5 K` — ein Sensordefekt (z. B. −50 °C) zählt nicht mehr als Frost und kann den Kessel nicht mehr dauerhaft anpinnen.
- End-to-End-Test umgestellt: eine **boiler-steuernde** Zone mit plausibel kaltem Wert → `boiler_demand=True`; eine nicht-steuernde / kühl-only / defekte Zone → kein Override.

**Bewusst akzeptierter Trade-off:** Eine kesselbeheizte Zone, die der Nutzer **nicht** als `controls_boiler` markiert hat, bekommt keinen Frost-Failsafe mehr über den geteilten Kessel. Das ist ein **Konfigurationsfehler** und gehört über Config-Validierung / Repair-Issue sichtbar gemacht — nicht dadurch „repariert", dass jeder kalte Sensor im Haus den geteilten Kessel feuert. Frost bleibt **innerhalb** der gegateten Menge harte Präzedenz (Frost > Komfort > Effizienz); echter Rohrfrostschutz liegt nach Feldkonsens am Gerät (TRV-Frostmodus, vgl. Büro-Setup mit auf Frostschutz geparkter TRV) und der Schreibpfad bleibt schatten-first/deaktivierbar.

**Belege:** VTherm `feature_central_boiler_manager.py` / `is_used_by_central_boiler` + `documentation/en/feature-central-boiler.md`; RoomMind `compressor_group_manager.py` / `room_contributes_to_group`; HA-core Issue [#63419](https://github.com/home-assistant/core/issues/63419); Forum „Multi-zone boiler — 2 years of learnings"; lokal `Designskizze_ADR-0013_Mehrzonen-Solver.md`, `Meinungsbild_Mehrzonen-Koordination.md`.

## Nachtrag #4 (v0.130.0) — Frozen-Zone pinnt den Kessel nicht mehr (Review V9)
Analog zu Korrektur #3 (defekter/unplausibler Sensor) darf auch eine Zone mit **eingefrorenem** (stale) Sensor den geteilten Kessel nicht dauerhaft anpinnen: eine heizfähige Frozen-Zone degradiert lokal auf den Frost-Floor und meldete darum `heating=True` **unbegrenzt** (der Sensor aktualisiert nie „bin jetzt warm"). Fix in `zone_request_from_data`: das ohnehin publizierte `sensor_frozen` zwingt `heating`/`heat_demand` der Zone auf False/0 → ihr **Komfort**-Heizruf zählt nicht mehr in `aggregate_boiler_demand` (weder count noch power). **Frostschutz bleibt** erhalten, weil `frost_active` unabhängig aus der letzten plausiblen Temperatur abgeleitet wird: eine im Frostband eingefrorene boiler-Zone feuert den Kessel weiter über `frost_override` (fail-toward-warmth), eine bei Komfort-Temp eingefrorene fällt heraus. Neues Degradationsflag `frozen` am `ZoneRequest`-Contract (Charter G15). Der residuale Fall (Raum friert erst NACH dem Sensortod) ist inhärent an einen toten Sensor gebunden und über das bestehende `sensor_frozen`-Repair-Issue sichtbar; echter Rohrfrostschutz liegt weiter am Gerät. 2 Tests (`test_hub_aggregate`).

## Nachtrag #5 — Min-Dwell-Floor 120 s (bewusst festgelegt)
`min_on`/`min_off` werden im Hub **nach oben** auf `BOILER_MIN_DWELL_FLOOR_S = 120 s` geklemmt (`hub_coordinator`): ein zu kurz konfigurierter Wert kann Kessel/Verdichter nie kurztakten. **Bewusste Entscheidung — nicht „wegoptimieren"** (nicht in einem späteren Review streichen); `keep-alive = 0` bleibt ein gültiges „Aus", `activation_delay` wird nicht geklemmt.
