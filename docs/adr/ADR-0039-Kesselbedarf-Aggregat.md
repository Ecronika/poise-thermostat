# ADR-0039: Kesselbedarf-Aggregat (Heizquellen-Synchronisation)

**Status:** Implementiert · **Datum:** 2026-06-22 · **Bezug:** ADR-0038 (Hub/Zwei-Phasen), ADR-0013, ADR-0026/0033 (Schatten-/Stufen-Disziplin), ADR-0006 (monotone Zeit/Entprellung), ADR-0012 (Repair/Sicherheit), ADR-0011 (Harness) · **Verifizierung:** Harness (Kessel-Laufzeit-Reduktion, Frost-Override, Anti-Takt) + Live-Shadow; Community-Beleg `Meinungsbild_Mehrzonen-Koordination.md`

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
- **#2 Frost-Sicherheit über ALLE Zonen:** `frost_override = any(frost_active for alle requests)` — eine frostgefährdete Zone feuert den geteilten Kessel auch dann, wenn sie (fehlkonfiguriert) nicht opt-in ist.
- **#3 Tote Drähte geschlossen:** `declared_power` (neues Raum-Feld) und `compressor_group` werden in den `ZoneRequest` durchgereicht → Lastabwurf (S3) und Verdichtergruppen (S4) rechnen end-to-end.
- **#4 Schimmel/Health geschützt:** `ZoneRequest.health_active` (aus Mould-Bindeursache); `resolve_load_shedding` wirft frost- **und** health-aktive Zonen nie ab. Vor zonenseitiger Durchsetzung muss der Shed-Cap unterhalb HEALTH komponieren.
- **#5/#6/#7 dokumentiert:** Verdichter erbt im Schatten die Boiler-Timer (eigene Min-Off vor Aktuierung nötig); der Zwei-Phasen-Tick ist asynchron (~60 s alte Zonen-Snapshots); `heat_demand` stammt aus dem tpi_duty-Schatten.

## Korrektur #2 (v0.46.0) — Frost war ein Schein-Fix
Der v0.45.0-„Fix" (`frost_override` über alle Zonen) war **kosmetisch**: das Eingangssignal `frost_active` wurde aus `"frost" in binding_lower_cause` abgeleitet, der Coordinator publiziert als Ursache aber **nur** `"mold"`/`"en16798"`, nie `"frost"` (der Frost-Floor ist die unterste Schranke und bindet die untere Ursache nie). `frost_active` war damit strukturell **immer False** → Frost-Override feuerte nie (latentes Einfrier-Risiko, das behoben *aussah*). **Echter Fix:** `frost_active` wird jetzt **physikalisch** aus der Raumtemperatur abgeleitet (`current_temperature <= FROST_FLOOR_C + 0,5 K`), und `zone_request_from_data` wurde in das **pure, 100 %-getestete** `hub_aggregate`-Modul verschoben (schließt die ungetestete-Ableitung-Lücke aus #1). Neuer End-to-End-Test: kalter Nicht-opt-in-Raum → `boiler_demand=True`.
