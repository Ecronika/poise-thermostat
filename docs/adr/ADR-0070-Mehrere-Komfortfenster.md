# ADR-0070: Mehrere Komfortfenster pro Tag (n-Fenster-Datenmodell, n+1-Options-UI)

**Status:** Implementiert (v0.187.0) · **Wirkung:** Live-A · **Datum:** 2026-08-09 · **Bezug:** [Recherche 2026-08 Komfortfenster/Anwesenheits-Boost](../research/2026-08-Komfortfenster-Anwesenheitsboost.md) §4 Option A + §5 Maintainer-Entscheidungen (Anlass), ADR-0025 (Schedule + Optimal-Start — der Kern, der hier mehrtermin-fähig wird), ADR-0058 N2 (Presence-Verhalten — die spontane Ergänzung zum planbaren Fenster), ADR-0008 (Options-Sektionen), ADR-0060 (Vorschlags-Schiene — künftiger Schreiber des Datenmodells)

> **Warum ein eigener ADR:** Die Recherche belegt Mehrfach-Zeitfenster als Markt-Grunderwartung (P1: Homematic IP 6 Phasen/Tag, KNX-RTR-Profile, HA-Scheduler-Threads), und der Maintainer hat vier Zuschnittsfragen entschieden (§5). Der ADR fixiert Key-Konvention, UI-Muster und Merge-Semantik, damit ADR-0060-Vorschläge später direkt in dasselbe Datenmodell schreiben können.

## Kontext

Poise kannte genau ein tägliches Komfortfenster (`comfort_start`/`comfort_end`, ADR-0025); außerhalb senkt `setback_delta` die Basis, Optimal-Start heizt auf den einen Fensterstart vor. Ein Bad braucht typischerweise Morgen- UND Abendblock (Recherche P1); der Rest des Tages darf absinken. Das pure Modul `comfort/schedule.py` war bereits mehrfensterfähig gebaut (`ComfortSchedule.windows: tuple[ComfortWindow, ...]`, `_normalize` merged/wrapped, `minutes_to_comfort = min(...)` über alle Fenster) — es fehlten Parser, UI und Dokumentation.

## Entscheidung

1. **Key-Konvention (flach, options-nativ):** Fenster 1 bleibt `comfort_start`/`comfort_end` (unverändert, keine Migration). Weitere Fenster heißen `comfort_start_N`/`comfort_end_N` mit N ≥ 2. Der Parser (`ZoneTuning.from_merged`) sammelt numerisch sortiert, toleriert Lücken in N und ignoriert halbe oder unparsbare Paare — das Datenmodell ist **praktisch unbegrenzt** (§5.1: Voraussetzung für ADR-0060-Vorschläge, die Fenster direkt eintragen).
2. **UI: n+1-Muster mit Kappe 8** (`COMFORT_WINDOWS_UI_MAX`). Der Options-Dialog baut die Schedule-Sektion bei jedem Öffnen aus der aktuellen Config: alle *konfigurierten* Fenster plus genau **ein** leeres nächstes Paar — nie mehrere leere Fenster auf Vorrat (§5.1). Beide Zeiten eines Fensters leeren entfernt es; beim Speichern werden Extra-Paare **lückenlos ab 2 renummeriert** (der Options-Submit ersetzt die gespeicherten Options vollständig, entfallene Keys verschwinden ohne explizites Löschen). Validierung je Paar: beide Zeiten oder keine (Fehler `comfort_window_pair`, wie beim Basis-Paar). Die Kappe ist reine UI-Ergonomie — der Parser liest auch N > 8 (von Hand oder künftig per ADR-0060 gesetzt).
3. **Merge-Semantik: Überlappungen werden zusammengeführt** (bestehende `_normalize`-Semantik, jetzt Vertrag): überlappende oder berührende Same-Day-Fenster verschmelzen zu einem; ein über Mitternacht laufendes Fenster (start > end) bleibt als Wrap-Fenster erhalten. Kein Abweisen — ein „falsch" überlappendes Fenster ist nie gefährlich, nur redundant.
4. **Optimal-Start gilt für ALLE Fenster** (§5.2): Die Vorheiz-Planung konsumiert ausschließlich `minutes_to_comfort`, das bereits das Minimum über alle Fensterstarts ist — jeder Fensterstart ist damit automatisch ein Vorheiz-Termin, ohne dass `plan_preheat` sich ändert. Gleiches erbt Optimal-Stop (`minutes_to_setback` = Minimum bis zum nächsten Fensterende).
5. **Setback zwischen den Fenstern:** Zwischen zwei Fenstern gilt dieselbe `setback_delta`-Absenkung wie nachts — es gibt genau eine Absenktiefe (bewusst; mehrstufige Profile à la Homematic „Absenkung1/2" sind Nicht-Ziel dieses Inkrements).
6. **Presence bleibt orthogonal** (ADR-0058 N2): Belegung verlängert Komfort **innerhalb** eines Fensters (ROOM_ECO erst nach `absence_after_min` Leere), triggert aber keinen Komfort außerhalb. Spontane Nutzung außerhalb aller Fenster deckt der Boost/Override ab — oder ein weiteres Fenster.

## Verworfene Alternativen

- **Liste/JSON-Objekt als ein Options-Key:** wäre im HA-Options-Flow nur als Text-Feld editierbar (kein TimeSelector je Fenster) und bräche das flatten/nest-Muster der Sektionen (ADR-0008).
- **Fixe 3 leere Fenster im Formular:** von der Maintainer-Entscheidung §5.1 explizit ausgeschlossen (Formular-Lärm für den Normalfall „ein Fenster").
- **Wochentags-Profile (Mo–Fr/Sa–So):** Markterwartung (Homematic/KNX), aber bewusst vertagt — das n-Fenster-Modell ist die Voraussetzung, nicht der Ersatz; ein Wochentags-Schnitt wäre ein eigener ADR auf demselben Datenmodell.
- **Abweisen statt Mergen bei Überlappung:** Merge ist verlustfrei-konservativ und erspart dem Nutzer eine Fehlerschleife im Formular.

## Umsetzung (v0.187.0)

- **Pure:** `comfort/schedule.py` unverändert (war bereits n-fähig — die Merge-/Wrap-/min()-Semantik dieses ADRs ist dort seit ADR-0025 Code). Parser: `runtime/config.py::ZoneTuning.from_merged` sammelt Basis-Paar + `comfort_start_N/_end_N` (Regex, numerisch sortiert, lücken-/halbpaar-tolerant) → `ComfortSchedule.from_windows`. `const.py`: `COMFORT_WINDOWS_UI_MAX = 8`.
- **Flow:** `config_flow.py` — `_extra_window_ns` (konfigurierte N), `_schedule_window_fields` (n+1-Feldliste), `_options_sections(current)` (dynamische Sektionskarte), `_renumber_windows` (Per-Paar-Validierung + lückenlose Kompaktierung beim Save); `_options_schema(hass, current)` rendert die Fenster-Paare als `TimeSelector`; die Reconfigure-`tuning`-Menge ist dynamisch, damit nummerierte Fenster als Tuning reconciled werden.
- **i18n:** `strings.json`/`en.json`/`de.json` — Labels `comfort_start_2..8`/`comfort_end_2..8` + `data_description` am ersten Extra-Fenster (n+1-Verhalten, Entfernen durch Leeren, Merge, Optimal-Start-für-alle).
- **Tests:** `test_phase2_config_parser.py` — Mehrfenster-Sammlung (inkl. Nummernlücke, `minutes_to_comfort` über Fenstergrenzen) + Ignoranz halber/ungültiger Paare; Schedule-Merge/Wrap waren durch die bestehende pure Suite gepinnt.

## Konsequenzen

Morgen- und Abendblock sind einzeln planbar und beide Optimal-Start-vorheizbar; die ADR-0060-Vorschlags-Schiene hat ein Datenmodell, in das sie unbegrenzt viele gelernte Fenster schreiben kann, ohne UI-Umbau. Die UI bleibt im Normalfall (ein Fenster) exakt so schlank wie zuvor — das zweite Fenster erscheint erst als Angebot, wenn das erste konfiguriert ist. Grenze ehrlich benannt: Es gibt weiterhin nur EINE Absenktiefe und keine Wochentags-Differenzierung; beides bleibt bewusst offen.
