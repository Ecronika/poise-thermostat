# ADR-0068: Lüfter als erste Kühlstufe — dritte Rolle der `air_movement`-Achse (R2)

**Status:** Vorgeschlagen · **Wirkung:** n.a. · **Datum:** 2026-08-07, Rev. 2 (nach Maintainer-Code-Review gleichen Datums) · **Bezug:** [Recherche 2026-07 Behaglichkeitsmodus](../research/2026-07-Behaglichkeitsmodus.md) §6/§9.1 R2 (Anlass und Evidenz), ADR-0048 (Nicht-Ziele — dieser ADR ist die dort geforderte *eng geschnittene* Revision der `air_movement`-Beschränkung), ADR-0046 §2/§4 (Achsen-Definition, `device_conflict_resolver`, P6/P7), ADR-0053 (Leerlauf-Umwälzung — die zweite Rolle), ADR-0054 Stufe 3 (Fan-Credit; „idealerweise kommandiert Poise den Lüfter selbst"), ADR-0055 N1 (Tier-Gates), ADR-0035/0027 (Norm-Klemme), ADR-0022 (stdlib-only)

> **Warum ein eigener ADR:** ADR-0048s Nachtrag fixiert `air_movement` auf zwei passive Rollen (Kühlkanten-Gutschrift, Leerlauf-Umwälzung). Die Behaglichkeitsmodus-Recherche identifiziert die dritte Rolle — den Lüfter **aktiv als erste Kühlstufe** — als größten Qualitäts-pro-Aufwand-Hebel des gesamten Vorhabens (§9.1 R2) und verlangt die Revision ausdrücklich als eigenen Folge-ADR, „nie als stille Aufweichung". Dieser ADR revidiert **nur** diese eine Beschränkung; ADR-0048 §1/§2 (keine RLT-Hygiene, kein CO₂-/Lüftungsmanagement) bleiben unberührt.
>
> **Rev. 2:** Das Maintainer-Review der Erstfassung identifizierte die zentrale Lücke — `set_fan_mode` stellt nur die Lüfter*stufe*, garantiert aber keinen verdichterfreien Betrieb — sowie fünf weitere Punkte (Zustandsmaschine, Resolver-Timing, Stufenwahl, Guard-Präzision, Nacht-Quelle). Diese Fassung arbeitet alle sechs ein; der physikalische Kern bleibt unverändert.

## Kontext

Im Kühlfall ist erhöhte Luftgeschwindigkeit die mit Abstand billigste Komfort-Maßnahme: ASHRAE 55-2020 rechnet ab v > 0,2 m/s über SET einen Cooling Effect in Kelvin — 0,5 m/s ≈ 2 K, 0,8 m/s ≈ 3 K; Deckenventilatoren liefern 2–4 K für 2–30 W und sind damit **Faktor 20–50 günstiger als Kompressorkühlung**; Feldstudien zeigen bis zu ⅓ Einsparung bei 24 → 26,5 °C mit Lüftern (Recherche §6). Poise hat die Bausteine als Shadow (`comfort/fan_cooling.py` Fan-CE seit v0.128, `comfort/fan_circulation.py` ADR-0053) — und den entscheidenden Mechanismus bereits live: `idle_park()` setzt geeignete Geräte explizit auf **`hvac_mode="fan_only"`**, und die Capability-Discovery modelliert `fan_only` als `AIR_MOVEMENT/RECIRCULATE`. Was fehlt, ist die Erlaubnis und die *Sequenz*, diesen verdichterfreien Modus **vor** dem Kompressor als Kühlstufe einzusetzen.

Der Markt bestätigt die Lücke: gestufte Kühlung existiert im HA-Ökosystem nur als dual_smart-Muster ohne Komfortmodell (Recherche §4); ADR-0053 grenzt sie ausdrücklich von der Umwälzung ab.

## Entscheidungstreiber

- **Größter Hebel, kleinste Kontroverse** (Recherche §9.4): kein Verdichterbezug in der Stufe selbst, reversibel, normgestützt.
- **Kein zweiter HVAC-Steuerpfad:** Die Sequenz muss durch die bestehende Mode-Choreografie (`mode_seam`, `idle_park`, Kompressor-Guard) laufen — nicht neben ihr (Review-Kernsorge).
- **Discovery-Doktrin:** „degradiere sicher, rate nie" gilt auch für Lüfterstufen.
- **ADR-0048-Geist unangetastet:** Umluft für thermischen Komfort, keine IAQ-Funktion; `ventilation`/`humidify`-Garantien bleiben vollumfänglich.
- **Abnahme messbar:** ADR-0055 N1 (Fan-Stufe = Tier 3, Kanten-Gutschrift = Tier 2).

## Betrachtete Optionen

1. **Status quo** — Fan-CE bleibt Anzeige. Verworfen: verschenkt den dokumentiert größten Hebel.
2. **Nur `set_fan_mode(stage)` auf dem laufenden Gerät.** Verworfen (Review-Blocker): Bei einem `climate`-Gerät bestimmt `fan_mode` die Lüfterstufe, der HVAC-Modus das Kühlen — in `cool` hebt `set_fan_mode("high")` die Stufe, während der Verdichter weiterläuft. „Fan zuerst" wäre nicht garantiert, nur „Fan lauter".
3. **Kompressorfreie Cooling-Stage über `hvac_mode="fan_only"` + optionale Stufenwahl, als Zustandsmaschine im bestehenden Mode-Seam** — **gewählt** (Details § Entscheidung).
4. **Aktivierung des `air_movement_resolver`/`assignment_planner` (ADR-0046-Pipeline).** Verworfen für v1: Der von ADR-0046 §4 vorgesehene `device_conflict_resolver` existiert nicht, der `assignment_planner` hat keinen Live-Konsumenten — die Achsen-Arbitrierung jetzt zu aktivieren, eröffnete genau den zweiten, konkurrierenden Steuerpfad, den dieser ADR vermeiden muss. v1 bleibt beim gebundenen Einzelaktor; die Überführung in die Achsen-Arbitrierung ist P6/P7-Arbeit.

## Entscheidung

1. **Die Kühlstufe ist der verdichterfreie Modus, nie nur die Lüfterstufe.** Sequenz: `normal → fan_only → fan_only + definierte Stufe → cool`. Aktives Fan-first findet in v1 **ausschließlich** statt, wenn das gebundene Klimagerät einen verifizierten kompressorfreien `fan_only`-HVAC-Modus anbietet (Discovery-Capability `AIR_MOVEMENT/RECIRCULATE`); ein Gerät mit `fan_modes`, aber ohne `fan_only`, gilt **nicht** als Fan-first-fähig und degradiert auf „kein aktives Fan-first". Die tatsächliche Aktuierung ist `set_hvac_mode("fan_only")` → optional `set_fan_mode(stage)` → Verweilphase → bei Bedarf `set_hvac_mode("cool")`.
2. **Zustandsmaschine (pure, `fan_first_decision()`):** Mindestverweilzeit der Fan-Stufe (sonst kauft Tick N+1 den Moduswechsel ohne Effizienzgewinn), Exit-Kriterien mit Hysterese (Temperaturfortschritt unzureichend ODER Timeout ODER schnell steigende Raumtemperatur → direkt `cool`), Wiedereintritts-Sperre gegen Pendeln, und explizite Unterordnung unter die bestehende Choreografie: Kompressor-Guard (`min_off`/`mode_hold`) bleibt Autorität für jeden `cool`-Eintritt, `mode_seam` bleibt der einzige Ort, an dem HVAC-Modi entschieden werden — `fan_first_decision()` liefert dort nur einen Kandidaten ab, wie heute der `dry`-Nudge. Der `idle_park`-Über-Trocknungs-Park bleibt unberührtes Schutzverhalten; beide Pfade nutzen dieselbe Unterdrückungsliste (Punkt 4), damit nicht zwei Regeln denselben Lüfter bewegen.
3. **Stufenwahl nur aus verifiziertem Geräteangebot:** neuer Pure-Helper `select_fan_stage(advertised_modes, max_velocity)` — wählt aus den vom Gerät angebotenen `fan_modes` die höchste Stufe, deren geschätzte Luftgeschwindigkeit (bestehende `_FAN_SPEED_MS`-Tabelle) unter der Klemme liegt. **Unbekannte Bezeichnungen werden nie geraten** (ein Gerät mit `["1","2","3","Auto"]` erhält kein blindes `"low"`; ohne bekannte Stufe läuft `fan_only` mit der Geräte-Default-Stufe, die CE-Schätzung bleibt konservativ bei der niedrigsten bekannten Annahme). Die Climate-Discovery wird um die Inventarisierung der `fan_modes` erweitert.
4. **Sicherheits-/Komfort-Guards (alle hart, als Poise-Politik benannt):**
   - **Geschwindigkeits-Klemme (konservative Poise-Klemme, keine vollständige ASHRAE-55-Nachimplementierung):** unter 23 °C operativ max. ≈ 0,2 m/s (keine erhöhte Stufe), 23–25,5 °C die jeweils nächsthöhere Stufe nur, wenn ihre Schätzgeschwindigkeit unterhalb der konservativ interpolierten Equal-SET-Grenze bleibt, ab 25,5 °C Deckel 0,8 m/s ohne lokale Nutzerkontrolle (ASHRAE 55 Addendum d als Referenzrahmen).
   - **Hitzegrenze 35 °C Raumtemperatur — eigene konservative Poise-Politik** (WHO nennt 40 °C als Grenze, ab der Ventilatoren den Körper erwärmen können; mit vorhandener Klimaanlage ist der frühere Umstieg auf `cool` ohnehin sinnvoll): darüber kein Fan-first, direkt Kompressor.
   - **Nur bei realem Presence-Signal** (`presence_control_ready`, ADR-0069 — das fail-safe-`occupied` genügt ausdrücklich nicht); unbelegt gilt die normale Verdichterlogik.
   - **Ruhezeiten, ehrlich:** Ein `quiet_hours`-Konzept existiert im Regelpfad **nicht** (bestätigte Lücke, s. Stufe-B-Schätzung WP4). v1 leitet ersatzweise aus dem Zeitplan ab: erhöhte Stufen nur im Komfortfenster; ein echtes Ruhezeiten-Design ist Voraussetzung für mehr und als offen markiert — dieser Guard gilt nicht als gelöst.
   - **Fenster offen** (ADR-0041) und aktiver `dry`-Lauf haben Vorrang; Heizfall: kein Fan-first, nur ADR-0053-Umwälzung (ISO-7730-DR-Modell).
5. **Gutschrift nur gegen bestätigten Gerätezustand:** Die Fan-CE-Kanten-Gutschrift (Tier 2, `meets_comfort_quality`) wird erst wirksam, wenn der beobachtete Gerätezustand bestätigt, dass der Lüfter tatsächlich läuft (Echo/`hvac_action`/`fan_mode`-Readback) — nie auf Verdacht aus dem eigenen Kommando. Ein ohnehin laufender Lüfter (auch ohne Fan-first-Fähigkeit des Geräts) darf weiterhin diagnostisch und für die CE-Schätzung berücksichtigt werden.
6. **Zwei getrennte Freigaben nach ADR-0055-N1:** (a) die **Sequenz** (`fan_only`-Stage) ist Tier 3 — Opt-in + `presence_control_ready` + Guards, ohne CA-Feldsaison; (b) die **Kanten-Gutschrift** ist Tier 2 — erst hinter `meets_comfort_quality` mit Baseline-Stempelung. Bis (b) frei ist, läuft (a) allein (der Lüfter kühlt gefühlt, die Kante bleibt).
7. **Guard-Test in v1 unverändert:** Da v1 den `air_movement_resolver` **nicht** aktiviert (No-op bleibt No-op, `assignment_planner` bleibt ohne Live-Konsument), bleibt `tests/test_non_goals.py` wortgleich in Kraft. Die Fortschreibung des `air_movement`-Pins (positives Pin statt No-op-Assert) wird erst mit der P6/P7-Überführung in die Achsen-Arbitrierung fällig und ist dann Teil jener Umsetzung.

**Non-Goals:** keine IAQ-/Frischluft-/CO₂-Lüftung (ADR-0048 §1/§2 unverändert); keine fan-Domain-Geräte in v1 (dedizierte Ventilatoren = ADR-0046 P6/P7 nach Stufe B); keine Aktivierung der Multi-Aktor-Pipeline (Resolver/Planner) in v1; kein Hitzewellen-Protokoll; keine Änderung der ADR-0053-Umwälzung.

## Begründung

Die Rev.-2-Sequenz macht aus „Lüfterstufe hochsetzen" eine echte kompressorfreie Cooling-Stage — nur so ist „Fan zuerst, Kompressor später" *garantiert* statt erhofft, und nur so bleibt die Mode-Autorität dort, wo sie heute liegt (`mode_seam` + Kompressor-Guard), statt einen zweiten Steuerpfad zu eröffnen. Der v1-Zuschnitt auf den gebundenen Einzelaktor folgt derselben Logik wie der ADR-0046-„P3-lite"-Präzedenzfall: der Seam wird am Single-Pfad erprobt, bevor die generische Arbitrierung ihn übernimmt. Die Stufenwahl aus verifiziertem Angebot und die Gutschrift nur gegen bestätigten Zustand übertragen die Discovery-Doktrin („rate nie") und die Echo-Disziplin (ADR-0059) auf den neuen Pfad. Die Guards sind bewusst als *Poise-Politik* deklariert, wo sie strenger sind als die Quelle (35 °C vs. WHO 40 °C; Stufen-Klemme vs. volle Equal-SET-Kurve) — konservativ sein ist erlaubt, sich dabei auf die Norm zu berufen nicht.

## Konsequenzen

**Positiv:** größter dokumentierter Effizienz-/Komfort-Hebel wird nutzbar; ADR-0054-Stufe-3-Wunsch erfüllt; klare Achsen-Semantik; Guard-Test bleibt in v1 unangetastet; die Zustandsmaschine ist pure und einzeln testbar. **Negativ/Kosten:** die Sequenz ist ein echtes Stück Mode-Choreografie (Verweilzeiten, Hysterese, Guard-Interaktion — mehr als „eine kleine Primitive", Review-Punkt 2); Discovery-Erweiterung um `fan_modes`; `set_fan_mode`-Executor-Primitive + Echo-Regeln für Stufen; Ruhezeiten-Lücke bleibt offen markiert. **Risiko:** Geräte, deren Firmware den Lüfter selbst verwaltet — dort degradiert die Rolle auf No-op („kein Kampf gegen selbstverwaltende Geräte", ADR-0053).

## Verifizierung (Plan)

Pure test-first: `fan_first_decision()` (Eintritt nur mit `fan_only`-Capability + Presence + Klemmen; Verweilzeit; Exit-Hysterese/Timeout/Schnellanstieg; Guard-Unterordnung `min_off`/`mode_hold`; Wiedereintritts-Sperre), `select_fan_stage()` (bekannte/unbekannte Stufen-Strings, Klemmen-Bänder, „nie raten"), Gutschrift-Freigabe nur bei bestätigtem Lauf. Integration CI: Sequenz-Dispatch durch den `mode_seam` (`fan_only` → dwell → `cool`), Echo-Verhalten, Toggle aus → byte-gleiche Writes. Guard-Test: unverändert grün in v1. Feld: PPD-Verlauf + Verdichter-Laufzeit vor/nach (HDH-Schiene).

## Compliance

ASHRAE 55-2020 inkl. Addendum d als Referenzrahmen der Geschwindigkeits-Klemme (bewusst konservative Poise-Interpolation, keine Nachimplementierung der vollen Equal-SET-Kurve — so benannt); ISO 7730 DR-Modell als Heizfall-Guard; WHO-2024-Hitzeempfehlung (40 °C) als Quelle, 35 °C als eigene konservative Politik deklariert; EN-16798-Kategorien bleiben die Band-Klemme (ADR-0027/0035). stdlib-only (ADR-0022); `pythermalcomfort` bleibt Testreferenz.

## Verknüpfungen

Revidiert die `air_movement`-Beschränkung aus dem ADR-0048-Nachtrag (dort Verweis-Nachtrag). Nutzt den `idle_park`-`fan_only`-Mechanismus und den `mode_seam` als einzige Mode-Autorität. Setzt ADR-0054 Stufe 3 um und konsumiert ADR-0055 N1 (Tier 2/3) sowie ADR-0069 (`presence_control_ready`, Bedienelement). Achsen-Arbitrierung + Guard-Test-Fortschreibung: ADR-0046 P6/P7 (nach Stufe-B-Entscheidung).
