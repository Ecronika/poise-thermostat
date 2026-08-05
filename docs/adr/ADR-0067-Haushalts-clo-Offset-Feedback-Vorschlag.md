# ADR-0067: Haushalts-clo-Offset — expliziter Komfort-Feedback-Kanal + Vorschlags-Lernen (ADR-0054 V4)

**Status:** In Arbeit (F1 umgesetzt, F2 offen) · **Wirkung:** Live-D · **Datum:** 2026-08-03 · **Bezug:** ADR-0054 Nachtrag V1–V3 (clo-Pipeline, dieser ADR ist dessen V4), ADR-0059 §5 (Grundsatz „Eingriffe sind Ausnahmen, keine Trainingssignale"), ADR-0060 (Vorschlagsmechanik L2 — Auslieferungsvehikel und Abgrenzung), ADR-0055 (Maskierungsmuster), ADR-0012 (Repair-Fix-Flow), ADR-0008 (Reconfigure-Pfad), ADR-0027/0035 (Norm-Klemme), ADR-0011 (Golden-Replay) · **Grundlage:** [Recherche 2026-08 Bekleidungsmodell](../research/2026-08-Bekleidungsmodell-clo-met.md) §1/§5/§8.4; [Recherche 2026-07 Behaglichkeitsmodus](../research/2026-07-Behaglichkeitsmodus.md) §5/§8 (Ambi-Muster, fehlender Feedback-Kanal)

> **Warum ein eigener ADR:** Der ADR-0054-Nachtrag hat V4 bewusst ausgekoppelt: Ein *lernender* Anteil an der Bekleidungsannahme berührt den Grundsatz „nie still lernen" und braucht eine Feld-Tuning-Runde — beides gehört nicht in einen Umsetzungs-Nachtrag. Dieser Entwurf ändert **nichts** am ausgelieferten V1–V3-Verhalten.

## Umsetzungsstand (2026-08-03 — F1, test-first)

**Implementiert (F1, beobachten only):** pures `control/feedback.py` — `feedback_mask_reason` (§F1-Maskenliste als First-Match: `window_open` / `override_active` / `setback_or_absent` / `sensor_frozen` / `pmv_not_valid` / `extreme_day` (> 8 K, beidseitig, degradiert ohne Forecast) / `no_pmv` / `pmv_out_of_range` (±1,0 inklusiv)) + `record_feedback` (Event-Shape ts/direction/pmv/ppd/clo_used/met_used/clo_source/phase/presence_level, in-place, cap 50 — L1-Muster), 6 pure Tests. **Kanal:** neue `button`-Plattform (`too_warm`/`too_cold` je Zone, Platform.BUTTON in Setup+Unload) + Service `poise.comfort_feedback` (`direction: warm|cold`, Target-Semantik wie `resume_schedule`), beide → `coordinator.submit_comfort_feedback` (Kontext aus dem letzten publizierten Tick + `clo_forecast_day` aus der Runtime; verworfen = Debug-Log mit Reason, akzeptiert = Fold + `dirty` für den Tick-Ende-Checkpoint ADR-0064). **Persistenz:** `UserControlState.feedback_stats` (PERSISTED_FIELDS, Bijektion via POST_RELOCATION), v1-Store-Key `feedback_stats` (additiv, by reference, Decode dict-Filter + Tail-Cap 50 — Codec-Vertrag 33→34 Keys re-frozen). **Diagnose:** Tick-Data-Key + Lift-out in `diagnostics_data` (wie `override_stats`, keine Entity-Attribute, keine Recorder-Last), Datenvertrag +1. i18n EN/DE (Buttons, Service, Selector). Suite 1195 grün, ruff check/format clean (mypy: CI). **Offen:** F2 (Vorschlags-Prädikat + Repair-Flow + Kollisionsregel — erst nach L2-Umsetzung und Golden-Replay-Tuning, §5), Anwendung `clo_offset` (§3).

## Kontext

Die clo-Pipeline steht seit V1–V3: ASHRAE-55-Prior auf `T_eff = (1−w)·T_rm + w·T_forecast`, Raumprofil-Zuschlag, ASHRAE-Dynamikkorrektur, ISO-Gültigkeits-Flag. Alles davon ist **Populationswissen** — und die Recherche beziffert dessen Grenze: Das Quellmodell erklärt nur ~19 % der clo-Varianz, während der **Gebäude-Random-Effect allein 13–17 %** erklärt, fast so viel wie der gesamte Klimaeffekt. Ein stabiler Per-Haushalt-Bias ist also statistisch real („der Haushalt, der zuhause immer Pullover trägt" vs. „der T-Shirt-Haushalt"), und für beheizte mitteleuropäische Wohnungen existiert **kein einziger publizierter Messwert** — der Prior kann dort systematisch daneben liegen. Größenordnung: ±0,2 clo ≈ ±1,2 K Neutraltemperatur.

Zwei Poise-Fakten rahmen jede Lösung: (1) Der Grundsatz aus ADR-0059 §5 ist normativ — kein Mechanismus verschiebt still eine Nutzerannahme; ADR-0060 definiert das einzige sanktionierte Vehikel (beobachten → **sichtbar vorschlagen** → bestätigen). (2) Es existiert **kein Komfort-Feedback-Kanal**: kein „zu warm/zu kalt"-Entity, kein Service (Recherche-Befund). Die L1-Statistik (ADR-0059) erfasst nur Sollwert-Overrides — und die konsumiert **bereits ADR-0060 L2** für Komfortbasis-Vorschläge.

**Das Attributionsproblem** ist damit die Kernfrage dieses ADRs: Ein wiederholter „+1 K"-Override kann eine falsche Komfortbasis *oder* eine falsche Bekleidungsannahme bedeuten. Dieselbe Beobachtung darf nicht zwei konkurrierende Vorschläge speisen — sonst schlägt Poise dem Nutzer widersprüchliche Änderungen vor oder lernt denselben Effekt doppelt.

## Entscheidungstreiber

- **Nie still** (ADR-0059 §5/ADR-0060): jede Wirkung nur über sichtbaren, ablehnbaren, normgeklemmten Vorschlag.
- **Saubere Signal-Trennung:** Overrides gehören L2 (Komfortbasis); der clo-Offset braucht ein Signal, das die Bekleidungs-Deutung trägt.
- **Wissenschaftliche Passung:** explizites Feedback ist das validierte Muster (Personal Comfort Models 73 % vs. 51 %; ~250–300 Labels; Ambi Climate als Produktpräzedenz — Recherche §5).
- **Robustheit:** Zeitkonstante Tage; 2–4-Tage-Extremepisoden dürfen nichts prägen (Maskierungsmuster ADR-0055 / Recherche §9.4).
- **Begrenztheit:** Gesamt-Offset hart ±0,3 clo (≈ ±2 K Äquivalent), Vorschlags-Schrittweite klein; Norm-Hülle (ADR-0027/0035) bleibt unumgehbar.
- **Ehrliche Wirkung:** solange PMV Diagnose ist, verbessert der Offset nur Lampe/Statistik — bewusst der risikoarme Validierungslauf des Kanals, *bevor* Stufe 2 ihn regelungswirksam macht.

## Betrachtete Optionen (mit Quelle)

1. **Stilles Online-Lernen** (Offset driftet automatisch aus Feedback/Overrides). **Verworfen:** verletzt den normativen Grundsatz ADR-0059 §5; exakt das Nest-Muster, dessen Kurskorrektur das Meinungsbild dokumentiert (ThermoCoach +12,4 % *gegen* stilles Lernen).
2. **clo-Offset aus der Override-Statistik mit Saison-Konditionierung** (Übergangszeit-Muster → clo, Ganzjahres-Muster → Komfortbasis). **Verworfen als Primärsignal:** bleibt mit L2 konfundiert (dieselbe Datenquelle, Zuordnung nur heuristisch), Signal schwach und langsam; als *Plausibilisierung* eines Feedback-Vorschlags aber nützlich (s. Entscheidung 4).
3. **Expliziter Komfort-Feedback-Kanal + Vorschlags-Lernen über die ADR-0060-Mechanik** — **gewählt.** Löst die Attribution strukturell: Overrides → Komfortbasis (L2, unverändert); explizites „zu warm/zu kalt" → Bekleidungsannahme (dieser ADR). Wissenschafts- und Produktpräzedenz (Kim 2018, Tartarini 2022, Ambi Climate; Recherche §5).

## Entscheidung

### 1. F1 — Feedback-Kanal + Statistik (beobachten, nichts wirkt)

Zwei Button-Entities je Zone (`button.<zone>_too_warm` / `_too_cold`) plus Service `poise.comfort_feedback` (`zone`, `direction: warm|cold`) als Automations-/Sprachpfad. Jedes Feedback wird als Ereignis in eine **persistierte, kontextgefilterte Feedback-Statistik** gefaltet (Muster L1, cap 50): Zeitstempel, Richtung, `pmv`/`ppd`/`clo_used`/`met_used`/`clo_source` des Ticks, Schedule-Phase, Presence-Level. **Maskierung — ein Feedback wird verworfen (nie gewertet), wenn:** Fenster offen; Override aktiv; Setback/unbelegt; Sensorik frozen; `pmv_valid == false` (Schlafraum!); Extremtag (`|T_rm − T_forecast| > 8 K` — die Antizipationslage aus Recherche §9); PMV außerhalb ±1,0 (dann ist die *Regelung*, nicht die Annahme das Problem). Rein diagnostisch sichtbar (`feedback_stats` in den Diagnosedaten).

### 2. F2 — Vorschlag (ADR-0060-Mechanik, wortgleiche Regeln)

Erkennt die Statistik ein Muster — **≥ 5 gleichgerichtete, maskierungs-saubere Feedbacks innerhalb von 30 Tagen** — erzeugt Poise ein Repair-Issue mit Fix-Flow: „5× ‚zu kalt' bei rechnerisch neutralem PMV — Bekleidungsannahme um 0,1 clo senken?" (weniger clo angenommen → wärmeres Ziel). Regeln wie ADR-0060: **Schrittweite ≤ 0,1 clo** pro Vorschlag (≈ 0,6–0,7 K); **Annahme** schreibt sichtbar die Config (`clo_offset`, Number ±0,3, Default 0, Reconfigure-Pfad); **Ablehnung** unterdrückt das Muster 30 Tage; **abschaltbar** über denselben `override_suggestions`-Toggle (ein Vorschlags-Schalter für alles — keine dritte Komfort-Stellschraube, Kritik-Befund „überlappende Bedienelemente"); Löschen der Statistik löscht wirklich.

### 3. Anwendung des Offsets (pure, eine Zeile im Prior-Pfad)

`clo_prior = clamp(predictive_clo(T_eff) + clo_offset, 0,4, 1,2)` — der Offset wirkt auf den **Prior vor** Raumprofil-Zuschlag und Dynamikkorrektur (er korrigiert die Ensemble-Schätzung des Haushalts, nicht das Raumprofil); die V1-Bounds 0,4–1,2 haben den Headroom dafür bereits reserviert (`_CLO_MIN`-Kommentar). Diagnose: `clo_source` erweitert um den Zusatz `+offset` (z. B. `rm+offset`), `clo_offset` als Attribut. **Per Zone** gelernt und gespeichert (Zonen sind eigenständige Config-Entries; ein haushaltsglobaler Wert bräuchte Hub-Koordination — bewusst verworfen, s. Konsequenzen).

### 4. Plausibilisierung & Kollisionsregel gegen L2

Ein clo-Vorschlag wird **unterdrückt**, solange für dieselbe Zone ein unbeantworteter L2-Komfortbasis-Vorschlag offen ist (und umgekehrt) — nie zwei konkurrierende Deutungen gleichzeitig. Zweitens dient die Override-Statistik als **Konsistenz-Check**: widerspricht das Override-Muster der Feedback-Richtung (Feedback „zu kalt", Overrides aber abwärts), wird kein Vorschlag erzeugt (`inconsistent_signals`, Diagnose-Reason).

### 5. Schwellen-Feld-Tuning vor Live

Die F2-Schwellen (5 / 30 Tage / 0,1 clo / Maskenliste) sind **Startwerte**. Vor der Live-Schaltung: Golden-Replay-Runde (ADR-0011) über Feld-Traces mit Ziel Falsch-Positiv-Rate ≈ 0 (kein Vorschlag aus Urlaubs-/Fenster-/Extremtag-Feedback), wie ADR-0060 §3.

**Non-Goals:** kein stilles Lernen; kein met-Lernen (Aktivität ist Kontext → Raumprofil V2, keine Präferenz); kein volles Personal-Comfort-Modell (nur ein skalarer Bias — das PCM-Feld bleibt Behaglichkeitsmodus Stufe C); keine EKF/MPC-Berührung; kein Cross-Haushalt-/Cloud-Lernen; keine Feedback-Pflicht (ohne Feedback bleibt exakt V1–V3).

## Begründung

Option 3 ist die einzige, die alle vier Rahmenbedingungen gleichzeitig erfüllt: Sie respektiert den Nie-still-Grundsatz (Vorschlag statt Drift), löst die Attribution strukturell statt heuristisch (getrennte Signalquellen), nutzt das wissenschaftlich stärkste Signal (explizites Feedback; die 250–300-Label-Erwartung aus Tartarini 2022 begründet, warum der **Prior bleibt** und der Offset nur ein kleiner, gedeckelter Zusatz ist) und liefert die im Behaglichkeitsmodus-Review als fehlend identifizierte Infrastruktur (Feedback-Kanal) in der risikoärmsten Ausbaustufe: Solange PMV Diagnose ist, kostet ein falsch angenommener Vorschlag maximal eine falsche Lampe — der Kanal validiert sich im Feld, *bevor* Stufe 2 ihn regelungswirksam macht. Der statistische Anker (Gebäude-Random-Effect 13–17 %) rechtfertigt genau die gewählte Form: einen konstanten, kleinen Per-Haushalt-Bias, keine Kurvenform-Änderung.

## Konsequenzen

**Positiv:** erster Komfort-Feedback-Kanal (wiederverwendbar für Stufe C/Behaglichkeitsmodus); Haushalts-Anpassung ohne Grundsatzbruch; Attribution sauber; Offset klein, geklemmt, sichtbar, reversibel; ohne Feedback null Verhaltensänderung.
**Negativ/Kosten:** zwei neue Entities + Service + Statistik-Persistenz + Repair-Flow; die Kollisionsregel koppelt diesen ADR an die (noch nicht gebaute) L2-Umsetzung; per-Zone-Lernen kann in Mehrzonen-Haushalten divergieren (derselbe Mensch, zwei Offsets) — bewusst akzeptiert, bis der Hub einen Haushalts-Kanal bietet (dann Folge-Nachtrag); Feedback-Teilnahme ist freiwillig → Einschwingzeit unbestimmt.
**Risiko niedrig:** kein Regelpfad berührt (bis Stufe 2), alles hinter Vorschlags-Toggle + Klemmen.

## Verifizierung (Plan)

Pure test-first: Feedback-Fold (Maskenliste vollständig — je Maske ein Verwerfen-Fall, inkl. `pmv_valid=false` und Extremtag); Vorschlags-Prädikat (≥5/30 d/Richtung; Einzel-/Urlaubs-/maskierte Feedbacks lösen nie aus); Kollisionsregel (offener L2-Vorschlag → unterdrückt, `inconsistent_signals`); Offset-Anwendung (Clamp 0,4–1,2, `clo_source`-Suffix, Zusammenspiel mit Zuschlag/Dynamikkorrektur bit-genau). Glue: Button/Service → Fold; Annahme → sichtbarer Reconfigure-Write, normbandgeklemmt; Ablehnung → 30-Tage-Unterdrückung; Toggle greift. Golden-Replay-Tuning (ADR-0011) vor Live-Schaltung von F2; F1 kann früher landen (beobachtet nur).

## Compliance

Generisch, kein Geräte-Sonderweg (G29/G30); stdlib-only (ADR-0022); Feedback-Daten bleiben lokal persistiert (Local-First — Ambi-Abschaltungs-Lehre, Recherche §5); Statistik in den Diagnosedaten redaktionspflichtig zu prüfen (ADR-0012-Redaction). Der Offset ist Bewertungs-, nie Regelgröße — ADR-0054-Kern („PMV nie direkte Regelgröße") unberührt.

## Verknüpfungen

Setzt **ADR-0054 Nachtrag V4** um (dessen ±0,3-clo-Rahmen und Extremtag-Maskierung hier ausgestaltet). Nutzt **ADR-0060** (Vorschlagsmechanik, Toggle, Schwellen-Tuning-Muster) und grenzt sich gegen dessen L2 ab (Kollisionsregel §4); **ADR-0059** (Grundsatz + L1 als Konsistenz-Check); **ADR-0012/0008** (Repair-Flow/Reconfigure); **ADR-0055** (Maskierungsmuster); **ADR-0011** (Golden-Replay). **Vorleistung für** Behaglichkeitsmodus Stufe C (Feedback-Kanal) und ADR-0054 Stufe 2 (`pmv_valid` + ehrlicherer clo → besserer Offset). **Folge-Nachtrag** bei Hub-Haushalts-Kanal (zonenübergreifender Offset).
