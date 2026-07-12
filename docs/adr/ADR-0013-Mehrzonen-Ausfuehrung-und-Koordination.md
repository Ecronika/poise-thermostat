# ADR-0013: Mehrzonen-Ausführung & Ressourcen-Koordination

**Status:** In Arbeit (70 %) · **Wirkung:** teilw. · **Datum:** 2026-06-18 · **Bezug:** E5, E20, K8, K12 · **Verifizierung:** Code-Review RoomMind/Versatile (Thema J)

## Kontext
Mehrere Zonen fordern je Leistung/Vorlauf an; Kessel und Leistungsbudget sind global (K12). Offen: Ausführungsreihenfolge und Auflösungsalgorithmus.

## Entscheidungstreiber
Konsistente Entscheidungen auf demselben Zustand; Fairness; Schutz geteilter Geräte; Vermeidung von Budgetüberschreitung/Vorlauf-Pendeln.

## Befund am Code (Belege)
- **RoomMind = Zwei-Phasen:** `_async_update_data` läuft `for area: room_state = await _async_process_room(...)` (mit `except → skipping`-Isolation), danach **ein** zentraler `_async_control_master_devices(room_states, …)`. Jede Zone führt ihren `MPCController.async_evaluate` aus.
- **Geteilte Ressource:** `heat_source_orchestrator.evaluate_heat_sources` (feste Rollen TRV=primary/AC=secondary, „both" bei `delta_t ≥ large_gap+Hysterese`, Sekundärleistung skaliert); `compressor_group_manager` (Min-Off blockiert Start, `check_must_stay_active` hält das **letzte** aktive Member bis Min-Run, Master spiegelt, `monotonic()`); `resolve_master_action` Default **frost-sicher heating_priority**.
- **Versatile Leistungsbudget:** `feature_central_power_manager.calculate_shedding` — `available = current_max_power − current_power`; VTherms **nach kleinstem Temperaturabstand sortiert**, bei Überlast die nächsten am Ziel zuerst abgeworfen, bei Überschuss umgekehrt freigegeben; **Reservierungs-Dict** gegen Stale-Sensor-Race + Debounce `MIN_DTEMP_SECS=20`. Kessel: `feature_central_boiler_manager` = Schwellen-Aggregator mit Aktivierungs-Delay + Re-Check, **keine** Fairness.
- **Befund-Lücke:** **kein** echtes **Vorlauftemperatur-Budget** in irgendeinem Repo — kein Referenzcode.

## Entscheidung
1. **Zwei-Phasen-Tick:** (1) Zonen rechnen **isoliert** (`try/except` je Zone) und liefern `ControlRequest`/Zustand; (2) ein **zentraler Koordinator** löst geteilte Ressourcen auf und gibt je Zone eine **gedeckelte Freigabe** zurück (Strukturplan-Ebene 5). Keine Direktansteuerung der geteilten Ressource durch Einzelzonen.
2. **Leistungsbudget = Versatile-Smallest-Gap-Shedding** (`available = max − current`, nach kleinstem Komfortabstand greedy ab-/zuschalten = „Komfort-Priorität"-Fairness) **inkl. Reservierungs-Dict + Debounce** gegen Stale-Sensor-Race.
3. **Verdichterschutz = RoomMind** (Min-Run/Off auf Member- **und** Master-Ebene, `monotonic()`, letztes Member hält Min-Run).
4. **Kessel-/Vorlaufauflösung:** `resolve_master_action` Default **frost-sicher heating_priority** + Schwelle-mit-Re-Check (Versatile). Für die **Vorlauftemperatur** (kein Feld-Vorbild) eigener Ansatz: **höchste geforderte Vorlauftemperatur gewinnt, gedeckelt**, mit Hysterese gegen Pendeln — als **neuartig markiert** und im Harness (ADR-0011) zu validieren.

## Begründung
RoomMinds Zwei-Phasen-Skelett + Verdichterschutz und Versatiles budget-genaues, fairnessbewusstes Shedding sind die am Code belegten Bestlösungen; ihre Kombination deckt Leistungs- **und** Geräteschutz ab. Die Vorlauf-Auflösung muss mangels Vorbild selbst entworfen werden — bewusst konservativ (höchste Anforderung gewinnt) und testpflichtig.

## Konsequenzen
**Positiv:** konsistente Entscheidungen, faire Priorisierung nach Komfortabstand, kein Verdichter-Kurztakten, kein Race auf Stale-Sensoren.
**Negativ/Kosten:** der Vorlauf-Allokator ist Eigenentwicklung ohne Referenz (höheres Validierungsrisiko); Zwei-Phasen-Struktur erfordert sauberen Zwischenzustand (`room_states`).

## Compliance
Algorithmen eigenständig nachimplementiert; generisch (Rollen/Geräte als Parameter).

## Verknüpfungen
Konkretisiert Strukturplan-Ebene 5 und K8/K12. Liefert die gedeckelten Freigaben an die Arbitrierung (Strukturplan-Ebene 7). Nutzt monotone Zeit aus ADR-0006.

## Umsetzungsstand Vorlauf-Allokator (S5, v0.47.0)
Der als neuartig/harness-pflichtig markierte Vorlauf-Allokator ist gebaut: `hub_aggregate.resolve_flow_temperature` (höchste geforderte Vorlauftemperatur der heizenden Zonen gewinnt, auf `max_flow` gedeckelt, Hysterese gegen Pendeln) + `FlowDecision`. **Harness-validiert** (`run_flow_allocator`, ADR-0011): über 120 verrauschte Ticks ≤3 Stellbewegungen (kein Pendeln), folgt dem Max, deckelt, folgt echten Stufen. Pro-Zone-Config `design_flow_temp`, System-Config `max_flow_temp`/`flow_hysteresis`; Hub exponiert `flow_target`/`flow_requested` als **Shadow** (kein Generator-Schreiben — Aktuierung wäre eine spätere opt-in Stufe wie der Kessel). 315 Tests.
