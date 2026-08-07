# ADR-0068: Lüfter als erste Kühlstufe — dritte Rolle der `air_movement`-Achse (R2)

**Status:** Vorgeschlagen · **Wirkung:** n.a. · **Datum:** 2026-08-07 · **Bezug:** [Recherche 2026-07 Behaglichkeitsmodus](../research/2026-07-Behaglichkeitsmodus.md) §6/§9.1 R2 (Anlass und Evidenz), ADR-0048 (Nicht-Ziele — dieser ADR ist die dort geforderte *eng geschnittene* Revision der `air_movement`-Beschränkung), ADR-0046 §2 (Achsen-Definition, P6/P7), ADR-0053 (Leerlauf-Umwälzung — die zweite Rolle; §-Begründung erkennt gestufte Kühlung als *anderen* Anwendungsfall an), ADR-0054 Stufe 3 (Fan-Credit; „idealerweise kommandiert Poise den Lüfter selbst"), ADR-0055 N1 (Risiko-Stufung: Tier-2/Tier-3-Trennung dieses Vorhabens), ADR-0035/0027 (Norm-Klemme), ADR-0022 (stdlib-only)

> **Warum ein eigener ADR:** ADR-0048s Nachtrag fixiert `air_movement` auf zwei passive Rollen (Kühlkanten-Gutschrift, Leerlauf-Umwälzung). Die Behaglichkeitsmodus-Recherche identifiziert die dritte Rolle — den Lüfter **aktiv als erste Kühlstufe** — als größten Qualitäts-pro-Aufwand-Hebel des gesamten Vorhabens (§9.1 R2) und verlangt die Revision ausdrücklich als eigenen Folge-ADR, „nie als stille Aufweichung". Dieser ADR revidiert **nur** diese eine Beschränkung; ADR-0048 §1/§2 (keine RLT-Hygiene, kein CO₂-/Lüftungsmanagement) bleiben unberührt — Luftbewegung für thermischen Komfort ist keine Frischluft-Lüftung.

## Kontext

Im Kühlfall ist erhöhte Luftgeschwindigkeit die mit Abstand billigste Komfort-Maßnahme: ASHRAE 55-2020 rechnet ab v > 0,2 m/s über SET einen Cooling Effect in Kelvin — 0,5 m/s ≈ 2 K, 0,8 m/s ≈ 3 K; Deckenventilatoren liefern 2–4 K für 2–30 W und sind damit **Faktor 20–50 günstiger als Kompressorkühlung**; Feldstudien zeigen bis zu ⅓ Einsparung bei 24 → 26,5 °C mit Lüftern (Recherche §6). Poise hat die Bausteine bereits als Shadow: `comfort/fan_cooling.py` (Fan-CE nach ASHRAE 55, `fan_ce_k`/`fan_cool_sp_shadow`, seit v0.128) und `comfort/fan_circulation.py` (ADR-0053, Umwälzung). Es fehlt allein die Erlaubnis und die Sequenz, den Lüfter **vor** dem Verdichter einzusetzen.

Der Markt bestätigt die Lücke: gestufte Kühlung existiert im HA-Ökosystem nur als dual_smart-Muster ohne Komfortmodell und ohne Koordination (Recherche §4); ADR-0053 grenzt sie ausdrücklich von der Umwälzung ab. **Vorleistung mit Spannung:** Der live `idle_park`-Pfad (`control/tick_resolve.py:334`) parkt eine `fan_only`-fähige AC heute im besetzten Totband bereits per Default in `fan_only` — als Schutz gegen Über-Trocknung, nicht als Komfortkühlung, aber ohne Presence-Gate und ohne Opt-in. Dieser ADR ordnet auch diese Vorleistung ein (§ Entscheidung 6).

## Entscheidungstreiber

- **Größter Hebel, kleinste Kontroverse** (Recherche §9.4): kein Verdichterbezug, reversibel, normgestützt.
- **Nutzerwunsch:** „gefühlte Temperatur regeln" und Set-and-forget-Orchestrierung (Recherche §3) — der Lüfter-zuerst-Pfad ist deren energetisch ehrlichste Form.
- **Norm-Leitplanken:** ASHRAE 55 (0,8-m/s-Deckel ohne Nutzerkontrolle, Belegungsbezug), ISO 7730 DR-Zugluftmodell (Heizfall), WHO-Hitzegrenzen für Ventilatoren.
- **ADR-0048-Geist unangetastet:** Umluft für thermischen Komfort, keine IAQ-/Frischluft-Funktion; die Nicht-Ziel-Garantien für `ventilation`/`humidify` bleiben vollumfänglich.
- **Abnahme messbar:** ADR-0055 N1 liefert die passende Stufung (Fan-Kommando = Tier 3, Kühlkanten-Gutschrift = Tier 2 mit PPD-Komponente).

## Betrachtete Optionen

1. **Status quo** — Fan-CE bleibt Anzeige, der Verdichter läuft, sobald die feste Kühlkante reißt. Verworfen: verschenkt den dokumentiert größten Effizienz-/Komfort-Hebel; der Nutzer sieht eine Gutschrift, die nie wirkt.
2. **Nur Kühlkanten-Gutschrift live schalten (ohne Fan-Kommando).** Verworfen als Alleinlösung: hebt die Kante nur, wenn der Lüfter *zufällig* läuft — ADR-0054 Stufe 3 benennt selbst, dass Poise den Lüfter dafür kommandieren können muss; sonst ist die Gutschrift Glückssache.
3. **Dritte Rolle „gestufte Kühlung": Fan-Kommando + Gutschrift als Sequenz vor dem Verdichter** — **gewählt** (Details § Entscheidung).
4. **Voller Luftbewegungs-Arbitrierer über fan-Domain-Geräte (ADR-0046 P6/P7 vorziehen).** Verworfen für diesen ADR: braucht Config-Flow-/Executor-/Ownership-Umbau (Stufe B); dieser ADR bleibt beim **eigenen Lüfter des gebundenen Klimageräts** (`set_fan_mode`) — P6/P7 bleiben der Pfad für dedizierte Ventilatoren.

## Entscheidung

1. **Dritte Rolle der `air_movement`-Achse:** *gestufte Kühlung* — bei Kühlbedarf in belegter Zone wird zuerst die Luftgeschwindigkeit angehoben (Lüfterstufe des gebundenen Klimageräts, `climate.set_fan_mode`), die Kühlkante um den ASHRAE-55-Cooling-Effect angehoben (`fan_cool_sp` von Shadow → wirksam), und **erst wenn die Gutschrift ausgeschöpft ist, startet der Verdichter.** Sequenz: Fan-Stufe ↑ → Kanten-Gutschrift → Kompressor.
2. **Zwei getrennte Freigaben nach ADR-0055-N1-Stufung:** (a) das **Fan-Kommando** ist Tier 3 (reversibel, verdichterfrei) — Freigabe über Opt-in + Presence + Guards, ohne CA-Feldsaison; (b) die **Kanten-Gutschrift** verschiebt das Band und ist Tier 2 — Freigabe erst hinter `meets_comfort_quality` (CA-Gate + PPD-Nicht-Verschlechterung). Bis (b) freigegeben ist, darf (a) allein laufen (Lüfter kühlt gefühlt, Kante bleibt).
3. **Sicherheits-Guards (Pflichtteil, alle hart):**
   - **Hitzegrenze:** kein Fan-zuerst bei Raumtemperatur ≥ 35 °C (konservative Untergrenze der WHO-Debatte; darüber direkt Kompressor — Ventilatorluft kann dann den Wärmeeintrag erhöhen).
   - **Geschwindigkeits-Deckel:** ohne explizite Nutzerkontrolle maximal die Lüfterstufe, die ≈ 0,8 m/s entspricht (ASHRAE 55); die bestehende konservative Stufen→v-Tabelle aus `fan_cooling.py` ist die Referenz.
   - **Nur belegt:** erhöhte Luftgeschwindigkeit nur bei Anwesenheit (ASHRAE-Belegungsbezug); unbelegt gilt die normale Verdichterlogik. Nacht-/Schlaffenster unterdrücken die höheren Stufen (Lärm; ADR-0053-Liste).
   - **Heizfall:** kein Fan-zuerst; es gilt ausschließlich die ADR-0053-Umwälzung (Zugluft/DR-Modell ISO 7730).
   - **Fenster offen** (ADR-0041) und aktiver `dry`-Lauf haben Vorrang.
4. **Opt-in, Shadow-first:** Die Sequenz erscheint zuerst als Diagnose (`fan_stage_shadow`, Erweiterung der bestehenden `fan_*`-Keys), aktuiert wird nach Zonen-Opt-in — Bedienelement und Name definiert die Stufe-A-Spezifikation (ADR-0069); dieser ADR liefert nur die Achsen-Erlaubnis + Sequenz + Guards.
5. **Guard-Test-Fortschreibung statt -Aufweichung:** `tests/test_non_goals.py` sichert heute (a) `ventilation` nie inventarisiert, (b) `humidify` nie aktuiert, (c) beide Stub-Resolver No-op. Mit Umsetzung dieses ADRs wird (c) für `air_movement` durch ein **positives Pin** ersetzt: der Resolver darf ausschließlich `recirculate`/Fan-Stufen-Kommandos für das gebundene Klimagerät erzeugen — die Garantien (a) und (b) bleiben wortgleich bestehen. Die Fortschreibung ist Teil der Umsetzung, nie ein stilles Löschen.
6. **Einordnung der `idle_park`-Vorleistung:** Der Über-Trocknungs-Park (`fan_only` im besetzten Totband) bleibt Schutzverhalten und wird von dieser Rolle **nicht** berührt; mit Umsetzung übernimmt aber die hiesige Guard-Liste (Belegung/Nacht) auch für ihn die Unterdrückungsentscheidung, damit nicht zwei Pfade mit verschiedenen Regeln denselben Lüfter bewegen.

**Non-Goals:** keine IAQ-/Frischluft-/CO₂-Lüftung (ADR-0048 §1/§2 unverändert); keine fan-Domain-Geräte in v1 (dedizierte Ventilatoren = ADR-0046 P6/P7 nach Stufe B); kein Hitzewellen-Protokoll (`use_fans_heatwaves` bleibt Referenzwerkzeug, kein Feature); keine Änderung der ADR-0053-Umwälzung.

## Begründung

Die Sequenz „Fan zuerst, Kompressor später" ist die direkte Umsetzung des §6-Befunds der Recherche: alle Maßnahmen in K-Äquivalente übersetzt, priorisiert nach K pro Watt — und der Lüfter gewinnt diese Rechnung um ein bis zwei Größenordnungen. Sie ist zugleich der einzige Punkt, an dem Poise dem De-facto-Standard (dual_smart-Blueprints, Sensibo-Schwellen) ein Komfortmodell voraushat: Die Kanten-Gutschrift ist ASHRAE-55-gerechnet, presence-gegated und normgeklemmt statt schwellen-gebastelt. Die Tier-Trennung (Kommando sofort nach Opt-in, Gutschrift hinter dem PPD-Gate) folgt der ADR-0055-N1-Logik: das reversible Fan-Kommando braucht keine Feldsaison, die Band-Verschiebung sehr wohl ein Komfort-Abnahmekriterium. Gegen Option 2 spricht ADR-0054 selbst; gegen Option 4 die Stufe-B-Kostenlage (eigenes Dokument).

## Konsequenzen

**Positiv:** größter dokumentierter Effizienz-/Komfort-Hebel wird nutzbar; ADR-0054-Stufe-3-Wunsch erfüllt; klare Achsen-Semantik (drei benannte Rollen statt implizitem Anwachsen); `idle_park`-Doppelpfad wird konsolidiert. **Negativ/Kosten:** erster nicht-thermischer Live-Schreibpfad auf das Klimagerät (`set_fan_mode` — Executor-Primitive + Echo-/Override-Regeln für Fan-Stufen nötig, klein aber neu); Guard-Test-Fortschreibung; mehr Zustands-/Diagnose-Keys; Lüfter-Lärm bleibt subjektiv (Opt-in + Nachtfenster mildern, beseitigen nicht). **Risiko:** Geräte, deren Firmware den Lüfter selbst verwaltet (viele Split-ACs im `cool`-Idle) — dort degradiert die Rolle auf No-op wie in ADR-0053 („kein Kampf gegen selbstverwaltende Geräte").

## Verifizierung (Plan)

Pure test-first: Sequenz-Entscheider (`fan_first_decision(...)` — Stufenwahl, Gutschrift, Guards, alle Grenzfälle: 35-°C-Grenze, 0,8-m/s-Deckel, unbelegt, Nacht, Heizfall, Fenster); Guard-Test-Fortschreibung (positives air_movement-Pin, `ventilation`/`humidify` wortgleich); Integration CI: `set_fan_mode`-Dispatch + Echo. Abnahme: Tier 3 sofort nach Opt-in beobachtbar, Tier 2 erst mit `meets_comfort_quality` (Baseline-Stempelung beim Flip). Feld: PPD-Verlauf und Verdichter-Laufzeit vor/nach (HDH-Schiene) als Nutzenbeleg.

## Compliance

ASHRAE 55-2020 (Elevated Air Speed, 0,8-m/s-Deckel, Belegungsbezug) methodisch nachimplementiert; ISO 7730 DR-Modell als Heizfall-Guard; WHO-2024-Hitzegrenze konservativ (35 °C); EN-16798-Kategorien bleiben die Band-Klemme (ADR-0027/0035). stdlib-only (ADR-0022); `pythermalcomfort` bleibt Testreferenz.

## Verknüpfungen

Revidiert die `air_movement`-Beschränkung aus dem ADR-0048-Nachtrag (dort Verweis-Nachtrag). Erweitert ADR-0046 §2 um die dritte Rolle (bei Umsetzung). Setzt ADR-0054 Stufe 3 um und konsumiert ADR-0055 N1 (Tier 2/3). Bedienelement/Name: ADR-0069 (Stufe-A-Spezifikation). Dedizierte Ventilatoren: ADR-0046 P6/P7 (nach Stufe-B-Entscheidung).
