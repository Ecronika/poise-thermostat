# ADR-0069: „Aktive Behaglichkeit" — Stufe-A-Spezifikation (Bedienelement, Name, Verhaltensumfang)

**Status:** Vorgeschlagen · **Wirkung:** n.a. · **Datum:** 2026-08-07 · **Bezug:** [Recherche 2026-07 Behaglichkeitsmodus](../research/2026-07-Behaglichkeitsmodus.md) §7 Stufe A / §8 Fragen 1, 6, 8 (Anlass; dieser ADR beantwortet die Spezifikationsfragen), ADR-0054 (Stufe 2 PMV-Offset — der thermische Kern), ADR-0068 (Lüfter als erste Kühlstufe — der Luftbewegungs-Kern), ADR-0053 (Leerlauf-Umwälzung), ADR-0055 N1 (Tier-Gates), ADR-0042 (Preset-Semantik — Abgrenzung), ADR-0061 (`adaptive_cool` — das Bedienelement-Vorbild), ADR-0067 (Feedback-Kanal — das Lernsignal)

> **Warum ein eigener ADR:** Die Recherche benennt drei offene Spezifikationsfragen, ohne die Stufe A nicht baubar ist: Regelgröße (§8.1 — beantwortet durch ADR-0054 + N1-Gates), Bedienelement (§7A: Preset vs. Zonen-Toggle) und Name (§8.8: „Komfortregime" und COMFORT sind besetzt). Dieser ADR entscheidet die beiden letzten und definiert den Verhaltensumfang; er schreibt keinen Code vor, der nicht bereits per ADR-0054/0068/0053 sanktioniert ist.

## Kontext

Alle Stufe-A-Bausteine existieren als Shadow (PMV/PPD seit v0.125, Fan-CE seit v0.128, Umwälzung ADR-0053, PMV-Offset-Vorbereitung ADR-0054 Stufe 2) und seit N1 existiert das passende Abnahmekriterium je Baustein (Tier 2/3). Was fehlt, ist die Nutzersicht: *ein* Schalter, der aus „Poise bewertet Behaglichkeit" ein „Poise stellt Behaglichkeit her" macht — ohne die drei bestehenden Bedienelemente (comfort_weight-Slider, COMFORT-Preset, Kategorie) zu verwässern (§7A: „drei überlappende Bedienelemente müssen entwirrt werden").

## Entscheidung

1. **Name: „Aktive Behaglichkeit"** (Options-Key `active_comfort`, EN „Active comfort"). Untechnisch, beschreibt das Verhalten (Behaglichkeit aktiv herstellen statt nur bewerten), kollidiert weder mit „Komfortregime" (ADR-0023, adaptiv ↔ Festband) noch mit dem COMFORT-Preset (ADR-0042, temporäres Komfortprofil) noch mit `comfort_weight` (Ökonomie-Gewicht).
2. **Bedienelement: Zonen-Options-Toggle** (`active_comfort`, Default aus), **kein Preset.** Begründung: Das Verhalten ist eine *stehende Zonen-Fähigkeit* (Scharfschaltung der Shadows), kein temporärer Nutzer-Intent — Presets sind per ADR-0042 Kategorie/Offset-Profile mit Auto-Rückkehr; ein Preset, das den Regel*mechanismus* wechselt, bräche diese Semantik, und ein Offset-0-Preset wäre deckungsgleich mit COMFORT (die Redundanzfalle aus §7A). Vorbild ist `adaptive_cool` (ADR-0061): ein Toggle, der an einem Seam die Schreibquelle tauscht. **Entwirrung:** `comfort_weight` bleibt das Spar-Gewicht, Presets bleiben Nutzer-Intent, `active_comfort` ist der Mechanismus-Schalter — drei orthogonale Achsen, in den Options getrennt beschriftet.
3. **Verhaltensumfang bei aktivem Toggle** (jeder Baustein hinter seinem eigenen Tier-Gate, ADR-0055 N1 — der Toggle *erlaubt*, die Gates *geben frei*):
   - **Kühlfall-Sequenz nach ADR-0068:** Lüfterstufe zuerst (Tier 3 — wirkt sofort nach Opt-in), Kühlkanten-Gutschrift (Tier 2 — erst mit `meets_comfort_quality`), dann Verdichter.
   - **PMV-invertierter ±1-K-Offset** (ADR-0054 Stufe 2, solver-geklemmt; Tier 2): schwüle Luft → etwas tiefer kühlen, trockene Winterluft → weniger heizen. Nur bei `pmv_valid` (ADR-0054 V3).
   - **Leerlauf-Umwälzung** (ADR-0053; Tier 3) mit deren Presence-/Opt-in-Regeln.
   - Alle Norm-Klemmen (EN-Band, ASR-Deckel, Frost-/Schimmel-Floors) bleiben unumgehbar (ADR-0027/0035/0042) — der Modus verschiebt nie mehr, als die Hülle erlaubt.
4. **Degradationsleiter (§8.6):** Minimum ist T + RH. Ohne RH oder außerhalb der ISO-7730-Domäne → `pmv_valid` False → PMV-Offset ruht (die Sequenz-/Umwälzungsteile können weiterlaufen); ohne Presence-Signal → alle erhöhten Lüfterstufen aus (ADR-0068-Guard), Offset darf weiter; ohne beides verhält sich die Zone exakt wie heute. Jede Ruhe-Ursache erscheint als Diagnose-Reason, nie still.
5. **Feedback als Lernsignal obendrauf** (§8.1-Endzustand): Der ADR-0067-Kanal bleibt die Korrekturschleife — Feedback verschiebt (vorschlagsbasiert) das clo-Modell und damit den PMV, nie direkt den Sollwert. Keine neue Mechanik in diesem ADR.
6. **Card:** Die bestehende Behaglichkeits-Ampel zeigt bei aktivem Toggle zusätzlich die aktive Maßnahme (Fan-Stufe/Offset) — reine Anzeige, Umfang beim nächsten Card-Build.

**Non-Goals:** kein Befeuchter (Stufe-C-Entscheidung, s. ADR-0046/0048-Nachträge 2026-08-07), keine Mehrgeräte-Orchestrierung (Stufe B, eigenes Konzeptdokument), kein PMV als direkte Regelgröße (ADR-0054-Kern unangetastet), kein neues Preset.

## Begründung

Der Toggle-Zuschnitt folgt dem stärksten belegten Nutzerwunsch (Set-and-forget, §3) in der Form, die Poises Architektur bereits kennt: `adaptive_cool` hat vorgemacht, dass ein Mechanismus-Toggle am Seam verständlich, testbar und rückbaubar ist. Die Tier-Struktur macht den Modus ehrlich ausrollbar: Tier-3-Teile wirken sofort nach dem Einschalten (der Nutzer *sieht* eine Wirkung), Tier-2-Teile kommen nach, sobald die Zone ihr Komfort-Abnahmekriterium erfüllt — genau die „Vertrauen vor Bequemlichkeit"-Reihenfolge, die die ADR-Reihe 0059/0060/0067 etabliert hat.

## Konsequenzen

**Positiv:** eine Nutzerentscheidung statt drei; klarer Evolutionspfad A → C ohne Umbenennung; jede Teilfreigabe einzeln beobachtbar und rückrollbar. **Negativ/Kosten:** Options-/i18n-/Doku-Erweiterung; die Erklärlast „warum wirkt Teil X noch nicht" wandert in Diagnose-Reasons (bewusst, statt still); der Name muss konsequent durchgezogen werden (Card, README, Optionen). **Offen bis zur Umsetzung:** exakte Options-Sektion, Reason-Katalog, Card-Umfang.

## Verifizierung (Plan)

Pure test-first je Baustein-Freigabe (Toggle aus → exakt heutiges Verhalten, byte-gleiche Writes; Toggle an + Gate zu → Shadow + Reason; Toggle an + Gate offen → Maßnahme aktiv); Degradationsleiter tabellengetestet; Integration CI: Options-Roundtrip + Entity-Defaults-Vertrag. Feld: PPD-/HDH-Vorher-Nachher je freigeschaltetem Tier-2-Baustein.

## Verknüpfungen

Konsumiert ADR-0054 (Stufe 2), ADR-0068 (Sequenz + Guards), ADR-0053 (Umwälzung), ADR-0055 N1 (Gates), ADR-0067 (Lernsignal). Abgegrenzt von ADR-0042 (Presets) und ADR-0023 (Komfortregime). Stufe B/C: separate Entscheidungen (Konzept „Stufe-B-Aufwand" bzw. ADR-0046/0048-Nachträge).
