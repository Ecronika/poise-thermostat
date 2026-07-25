# Designplan: Erweiterung der Feuchte-Achse (Trockenheits-Bewertung + Lüftungs-Empfehlung)

**Datum:** 2026-07-25 · **Typ:** Entwurf (Design), **kein** Implementierungsplan, **keine** getroffene Entscheidung · **Grundlage:** [Recherche-Notiz vom 2026-07-25](../research/2026-07-Feuchte-Steuerung-und-Lueftungshinweise.md) · **Bezug:** ADR-0010, ADR-0016, ADR-0035, ADR-0041, ADR-0045, ADR-0048, ADR-0049, ADR-0050, ADR-0058

> **Randbedingung:** Der Coordinator wird gerade refaktoriert. Dieser Plan beschreibt deshalb **Verantwortlichkeiten, Datenverträge und Schichtgrenzen** — keine Aufrufreihenfolge, keine Stage-Zuschnitte, keine Tick-Verdrahtung. Alle fachliche Logik landet in **puren Modulen**; die einzige Naht zum Coordinator ist die Argument-Konstruktion einer bereits existierenden puren Komposition. Der Entwurf gilt damit unabhängig davon, wie der Tick am Ende geschnitten ist.

---

## 1. Was der Entwurf leisten soll

| # | Ziel | Charakter |
| --- | --- | --- |
| **A** | Trockenheit wird **physikalisch** bewertet (absolute Feuchte) statt über eine RH-Zahl, die mit der Raumtemperatur wegdriftet | Anzeige, kein Regeleingriff |
| **B** | Poise sagt, **wann Lüften etwas bringt** — und wann es schadet — begründet aus Schimmelmodell, Feuchtedifferenz und Wärmekosten | Hinweis, kein Aktor |

Beides bleibt strikt auf der Anzeige-/Hinweis-Seite des ADR-0048-Leitprinzips *Monitoring vs. Control*. Der Regelpfad (`humidity_decide` → `mode_arbitration` → Dry-Nudge) wird **nicht angefasst**.

## 2. Entwurfsprinzipien

1. **Pure zuerst, Naht zuletzt.** Jede neue Entscheidung ist eine reine Funktion über Zahlen — testbar ohne HA, ohne Coordinator, ohne Tick.
2. **Additiv, nie verändernd.** Keine bestehende Signatur ändert sich; keine bestehende Schwelle verschiebt sich. Neue Funktionen stehen **neben** `humidity_decide`, nicht darin.
3. **Anzeige darf nie regeln.** Ein Trockenheits- oder Lüftungs-Verdict ist niemals Eingang von `humidity_decide`, `dual_setpoint` oder dem Constraint-Solver. Das wird per Guard-Test festgeschrieben (Muster: `tests/test_non_goals.py`).
4. **Bauphysik schlägt Komfort, Komfort ist belegungs-gegatet.** Dieselbe Trennung wie in ADR-0050 v0.179.0: Komfort-Kriterien gelten bei Belegung, Gebäudeschutz-Kriterien immer.
5. **Nichts versprechen, was nicht messbar ist.** Insbesondere: Poise kennt **keine Luftwechselrate** und kann deshalb *nicht* sagen, wie lange gelüftet werden muss, um eine Feuchtemenge abzuführen. Was Poise messen kann (Abkühl-Steigung bei offenem Fenster, Aufheizrate, Preis), darf gesagt werden — mehr nicht.

---

## 3. Feature A — Absolute Feuchte als bewertete Größe

### A.1 Physik-Schicht

`estimation/psychrometrics.py` erhält **eine** reine Funktion neben `humidity_ratio`:

```
absolute_humidity(t_c, rh_percent) -> float   # g/m³
    = vapour_pressure(t_c, rh_percent) / (R_v · T_K) · 1000,  R_v = 461.5 J/(kg·K)
```

Begründung der zweiten Einheit: intern rechnet Poise in **g/kg** (Mischungsverhältnis, EN 16798-1 / ASHRAE-55-Einheit — bleibt der Regelgröße vorbehalten). Das gesamte HA-Ökosystem und die Wirkungsliteratur sprechen dagegen **g/m³**. Beide Werte werden veröffentlicht; bewertet wird in g/m³.

**Einheiten-Nebenbedingung:** `device_class: humidity` akzeptiert kein g/m³ ([core #127619](https://github.com/home-assistant/core/issues/127619), *closed / not planned*). Der Wert wird als Attribut bzw. — falls je als Entität — mit `unit_of_measurement` **ohne** `device_class` geführt.

### A.2 Bewertungs-Schicht

Die Bewertung gehört auf die **Card** (ADR-0049 §2: null Recorder-Last, Verdict im Frontend aus dem Live-State). `monitoring.ts` bekommt keine zweite Ampel, sondern eine **geteilte Zuständigkeit innerhalb der bestehenden Feuchte-Lampe**:

| Seite | Wer entscheidet | Begründung |
| --- | --- | --- |
| **trockene Seite** (unten) | **absolute** Feuchte in g/m³ | Austrocknung der Schleimhaut ist ein absoluter Effekt; RH driftet mit der Raumtemperatur |
| **feuchte Seite** (oben) | **relative** Feuchte, unverändert `[60, 65]` | Schimmel ist ein Oberflächen-**RH**-Phänomen; hier ist relativ die physikalisch richtige Größe |

Fällt die absolute Feuchte aus (keine Temperatur), degradiert die untere Seite still auf die heutigen RH-Grenzen `[30, 40]` — Verhalten wie bisher.

**Verworfene Alternative:** „schlechteres von beiden gewinnt" (`worse-of`, wie `caVerdict` es über seine Teilmetriken macht). Verworfen, weil es die obere Seite ohne fachlichen Grund verschärft und eine zweite, redundante Feuchte-Obergrenze etabliert, die der 12-g/kg-Backstop und `mold.py` bereits besser abdecken.

### A.3 Schwellenwerte

Vorschlag `DEFAULT_ABS_HUMIDITY_FLOORS = [5.0, 7.0]` g/m³ (`[alertLo, warnLo]`), konfigurierbar wie alle Ampel-Schwellen.

Die Wahl ist bewusst **keine neue Zusage**, sondern die temperaturrobuste Umschreibung der heutigen RH-Grenzen bei Auslegungstemperatur:

| Schwelle | entspricht bei 20 °C | heutige RH-Grenze |
| --- | --- | --- |
| 7,0 g/m³ (gelb) | 40,6 % RH | 40 % |
| 5,0 g/m³ (rot) | 29,0 % RH | 30 % |

Der Effekt ist die Korrektur der Temperaturdrift:

| Raumtemperatur | 7,0 g/m³ entspricht | Wirkung gegenüber heute |
| --- | --- | --- |
| 18 °C | 45,7 % RH | **strenger** — der kühle, trockene Raum wird endlich erkannt |
| 20 °C | 40,6 % RH | unverändert |
| 24 °C | 32,2 % RH | **lockerer** — der warme Raum wird nicht mehr grundlos gelb |

Literaturlage: der Gradient ist belegt ([Shaman & Kohn 2009](https://www.pnas.org/doi/10.1073/pnas.0806852106), [Kudo/Iwasaki 2019](https://pubmed.ncbi.nlm.nih.gov/31085641/)), eine harte Schwelle ist es **nicht**. Deshalb gelb/rot als Hinweis, keine Handlungspflicht, keine Aktuierung. Die im Anlassartikel genannten 9 g/m³ werden **nicht** übernommen (nicht validiert), die dortige Obergrenze von 12 g/m³ ausdrücklich **nicht** (widerspricht `mold.py`: bei 12 g/m³ Raumluft überschreitet jede Oberfläche unter ~17,6 °C die 80-%-Keimgrenze).

### A.4 Was sich ausdrücklich **nicht** ändert

- `humidity_decide` — Signatur, Schwellen, Dry-Guard, Latch: unverändert.
- Der 12-g/kg-Backstop bleibt, wo er ist. Klarzustellen ist nur seine Rolle: er entspricht bei 20 °C ≈ 82 % RH und bindet erst **ab ≈ 25 °C** vor der Kategorie-RH-Decke — er ist ein **Warmraum-Schwülekriterium**, kein Winter-Schimmelschutz. Das leistet allein `mold.py`. Gehört als Kommentar an die Konstante, nicht als Verhaltensänderung.
- Keine neue Regelgröße, kein neuer Aktor, kein neuer Schreibpfad.

---

## 4. Feature B — Lüftungs-Empfehlung

### B.1 Neues pures Modul `comfort/ventilation.py`

Eine reine Funktion, Muster exakt wie `humidity_decide` (Dataclass rein, Dataclass raus, Latch als Parameter):

```
ventilation_advise(
    w_in, w_out,                  # absolute Feuchte innen/außen [g/m³]
    t_in, t_out,                  # für Wärmekosten + Plausibilität
    surface_rh, mold_capped,      # aus mold.py — Bauphysik-Anlass
    co2,                          # optional, nur als Anlass
    window_open,                  # aus ADR-0041 (gelesen, nie geschrieben)
    occupied,                     # ADR-0058
    prev_advice_active,           # Hysterese-Latch
    cfg,
) -> VentilationAdvice(action, reason, level, detail)
```

`action ∈ {idle, open, close, discourage}` · `level ∈ {ok, warn, alert}` (für die Card) · `reason` als stabiler Token für i18n und Diagnose.

### B.2 Entscheidungstabelle (Präzedenz von oben nach unten)

| # | Bedingung | `action` | `reason` | Gate |
| --- | --- | --- | --- | --- |
| 1 | `mold_capped` **oder** `surface_rh ≥ Limit − Reserve` | `open` | `mold_risk` | **nie** gegatet (Gebäudeschutz) |
| 2 | `w_in ≤ abs_floor` **und** `w_out < w_in` | `discourage` | `too_dry` | nie gegatet |
| 3 | `w_in − w_out ≥ Δ_ein` **und** `w_in` über dem Zielband | `open` | `moisture_out` | belegungs-gegatet (Komfort) |
| 4 | `co2 ≥ Schwelle` (nur falls Sensor vorhanden) | `open` | `co2` | belegungs-gegatet |
| 5 | `window_open` **und** Anlass entfallen (`w_in − w_out < Δ_aus`) **oder** Raum am Schimmel-/Frostboden | `close` | `target_reached` / `thermal_floor` | nie gegatet |
| 6 | sonst | `idle` | `no_gain` | — |

**Konsistenz-Notiz:** Regel 1 und Regel 2 können sich physikalisch nicht widersprechen — Schimmelrisiko setzt Feuchte voraus, die ein trockener Raum nicht hat. Das ist eine Invariante, die sich als Property-Test festschreiben lässt.

**Hysterese:** `Δ_ein = 3,0 g/m³` (die im Feld etablierte Schwelle, u. a. [adamcornforth](https://github.com/adamcornforth/ha-open-window-blueprint)), `Δ_aus = 1,5 g/m³`, gehalten über `prev_advice_active` — dasselbe asymmetrische Muster wie `humidity_decide`, aus demselben Grund (kein Chatter am Schwellenrand).

**Belegungs-Gate:** exakt die ADR-0050-Trennung. Komfort-Anlässe (Schwüle, CO₂) nur bei Belegung — ein leeres Haus braucht keinen Lüftungs-Hinweis. Gebäudeschutz (Schimmel) und die Schließ-Empfehlung immer.

### B.3 Außenfeuchte — Bezugsleiter

Nach der bestehenden Degradations-Ladder (gemessen → abgeleitet → geschätzt → Default):

| Stufe | Quelle | Anmerkung |
| --- | --- | --- |
| 1 | optionaler Außen-Feuchtesensor (neues Config-Feld) | genaueste Quelle, für Nutzer mit eigener Wetterstation |
| 2 | `humidity`-Attribut der **bereits konfigurierten** Weather-Entität | kostet den Nutzer nichts — die Entität existiert für Optimal Start ohnehin |
| 3 | keine Quelle | Feature **still inaktiv** (graceful), wie das Feuchte-Feature ohne Innensensor |

Damit ist das Feature für den Bestand ohne jede Zusatzhardware nutzbar — ein wesentlicher Unterschied zu den Blueprints, die zwei Sensorpaare voraussetzen.

### B.4 Was Poise sagen darf — und was nicht

| Aussage | zulässig? | Warum |
| --- | --- | --- |
| „Lüften bringt jetzt etwas" (Δ absolute Feuchte) | ✅ | direkt aus Messwerten |
| „Lüften ist jetzt kontraproduktiv, Raum ist zu trocken" | ✅ | Gegenrichtung, die im gesamten Wettbewerb fehlt |
| „Fenster wieder schließen" | ✅ | Anlass entfallen oder thermischer Boden erreicht — ereignisgetrieben statt Timer |
| „Das kostet ca. X kWh / Y €" | ✅ mit Vorbehalt | aus **gemessener** Abkühl-Steigung (ADR-0041-Slope-Detektor), gelernter Aufheizrate und dem Preis-Helfer aus `control/hdh_savings.report_price_eur_kwh`; als Schätzung ausgewiesen |
| „Lüfte N Minuten, dann ist die Feuchte weg" | ❌ | erfordert die **Luftwechselrate** — Poise misst sie nicht und darf sie nicht behaupten |
| Lüfter/KWL schalten | ❌ | ADR-0048 §1/§2 — Poise besitzt keine lufttechnische Anlage (VDI 6022) |
| Push-Benachrichtigung selbst versenden | ❌ (Entwurfsentscheidung) | s. B.5 |

### B.5 Benachrichtigungen — bewusst **nicht** in Poise

Der Entwurf sieht **keinen** Notify-Pfad vor. Der Rat wird als Attribut (und optional als recorder-exkludierbare Diagnose-Entität, ADR-0049 §7 hat das Muster bereits entworfen) veröffentlicht; Push, TTS, Alexa und Timing baut sich der Nutzer mit einer dreizeiligen Automation oder einem der vorhandenen Blueprints darauf.

Gründe: Poise besäße sonst eine Zustellstrecke inklusive Ruhezeiten, Wiederholungslogik und Empfängerverwaltung — ein eigenes Produkt. Das dokumentierte Nutzer-Sentiment („nur melden, wenn etwas nicht stimmt", Auto-Lüftung „ging nach hinten los", ADR-0048) verlangt den *Zustand*, nicht den Kanal. Und die Blueprints, die den Kanal können, fehlen genau an der Stelle, an der Poise stark ist: der Begründung.

### B.6 Fenster-Rückkopplung (ADR-0041)

Das Fenster-Signal wird **gelesen**, nie geschrieben. Es schließt die Hinweis-Schleife:

- Fenster geht auf, während `action == open` → Rat gilt als befolgt, Latch hält, Anzeige wechselt auf „lüftet".
- Anlass entfällt oder der Raum erreicht den Schimmel-/Frost-Boden → `action = close`.
- Der bestehende Regelpfad (Absenkung auf den Boden, Lernen pausiert) bleibt vollständig unberührt.

Damit ersetzt ein **Ereignis** den festen Timer, den alle Blueprints benutzen müssen.

---

## 5. Datenvertrag (neue Felder)

Alle Werte sind Diagnose-Attribute im Sinne von ADR-0016 — langsam veränderlich, keine Recorder-Last-Treiber.

| Attribut | Typ | Quelle | Zweck |
| --- | --- | --- | --- |
| `abs_humidity_gkg` | float | **existiert bereits** | Regel-Einheit, unverändert |
| `abs_humidity_gm3` | float | A.1 | Ökosystem-Einheit, Card-Bewertung |
| `abs_humidity_out_gm3` | float \| null | B.3 | Außenluft-Vergleich |
| `vent_action` | `idle\|open\|close\|discourage` | B.1 | Rat |
| `vent_reason` | Token | B.1 | Begründung (i18n) |
| `vent_delta_gm3` | float \| null | B.1 | die Zahl hinter dem Rat |
| `vent_cost_kwh` / `vent_cost_eur` | float \| null | B.4 | Schätzung, als solche ausgewiesen |

Card-seitig: die **Feuchte-Lampe** bekommt den g/m³-Wert in Titel/`aria-label`; der Lüftungs-Rat wird ein **Chip** (Muster `override_clamped`), keine Lampe — er trägt Text, keine Messgröße.

---

## 6. Schichten und Refactor-Berührung

| Ort | Änderungsart | Berührt den Coordinator-Umbau? |
| --- | --- | --- |
| `estimation/psychrometrics.py` | +1 reine Funktion | nein |
| `comfort/humidity.py` | nur ein Kommentar an der 12-g/kg-Konstante | nein |
| `comfort/ventilation.py` | **neu**, rein | nein |
| `diagnostics/shadows.py` → `compose_climate_band` | +Parameter, +Dict-Schlüssel | **die einzige Naht** — bereits eine reine Funktion |
| `coordinator.py` | ausschließlich **Argument-Konstruktion** innerhalb des bestehenden einen `try` | minimal, additiv, keine neue Stage, kein neuer Fehlerbereich |
| `climate.py` | Attribut-Allowlist erweitern | nein |
| `runtime/config.py`, `const.py` | 1 optionales Sensor-Feld, optionale Schwellen | nein |
| `trace/schema.py` | optionale Felder | nein |
| `card/src/monitoring.ts`, `poise-card.ts`, `card-config.ts` | Verdict-Erweiterung + Chip + Config | nein |

**Der Punkt für dein Refactoring:** die gesamte Fachlichkeit ist ohne den Coordinator schreib- und testbar. Was auch immer aus `_stage_climate_band` wird — die neuen Werte reisen als Argumente in dieselbe pure Komposition, in der `humidity_action` und `abs_humidity_gkg` heute schon entstehen. Wenn der Umbau die Stage neu schneidet, wandert die Argument-Konstruktion mit; es gibt nichts zu migrieren.

---

## 7. Abgrenzung zu ADR-0048

Der Entwurf bewegt sich innerhalb des Leitprinzips, berührt aber dessen Formulierung an einer Stelle und braucht deshalb **einen eigenen ADR**:

- ADR-0048 §2 verbietet CO₂-getriebene Lüftungs-**Steuerung** und erlaubt den Hinweis ausdrücklich („CO₂ hoch — Fenster öffnen"). Regel 4 der Tabelle in B.2 ist genau dieser erlaubte Nudge — die Grenze ist aber bisher nur allgemein gezogen und sollte für einen strukturierten, begründeten Rat präzisiert werden.
- Es entsteht **kein** Kommando: keine `fan`-Entität, kein `humidifier`, kein Service-Call. Der `assignment_planner` baut weiterhin ausschließlich `Axis.THERMAL`. `Axis.VENTILATION` bleibt tot und darf es bleiben — der Rat ist ein *Attribut*, keine Achse.
- Die Nicht-Ziele bleiben unangetastet: keine aktive Befeuchtung (§3), keine RLT-Hygiene (§1), kein Lüftungs-Bemessungsanspruch (§2).

---

## 8. Fehlerverhalten und Degradation

| Ausfall | Verhalten |
| --- | --- |
| kein Innen-Feuchtesensor | beide Features still inaktiv (wie heute) |
| keine Raumtemperatur | absolute Feuchte fällt aus → untere Ampel-Seite degradiert auf RH `[30, 40]` |
| keine Außenfeuchte | Feature B still inaktiv; Feature A unberührt |
| kein CO₂-Sensor | Regel 4 entfällt, Rest unverändert |
| Ausnahme in der Komposition | fällt mit dem bestehenden `climate_diag`-Block zusammen — **wichtig:** anders als beim Dry-Nudge ist der Fallback hier folgenlos, weil nichts aktuiert wird |

Die Anzeige zeigt im Zweifel **nichts** statt etwas Falschem — dieselbe Linie wie die stillen Fallbacks in `monitoring.ts`.

---

## 9. Testbarkeit (Entwurfsanforderung, nicht Testplan)

- Alles Fachliche ist rein → Unit-Tests ohne HA, wie `test_humidity.py` / `test_psychrometrics.py`.
- **Property:** das Trockenheits-Verdict ist monoton in `w` (mehr Feuchte darf nie schlechter bewerten).
- **Invariante:** `mold_risk` und `too_dry` schließen sich aus (B.2).
- **Guard-Test** im Geist von `tests/test_non_goals.py`: weder das Trockenheits- noch das Lüftungs-Verdict darf in `humidity_decide`, `dual_setpoint` oder den Constraint-Solver gelangen; `ventilation_advise` erzeugt nie ein Kommando.
- **Umrechnungs-Referenz:** g/m³ ↔ g/kg ↔ RH an bekannten Stützstellen (20 °C/40 % = 7,0 g/m³ = 5,9 g/kg).

---

## 10. Sinnvolle Reihenfolge (grob, jederzeit unterbrechbar)

Jede Stufe ist für sich auslieferbar und wertvoll:

1. **A** — absolute Feuchte veröffentlichen und die untere Ampel-Seite darauf umstellen. Null Regelrisiko, korrigiert einen echten Bewertungsfehler, braucht keinen neuen Sensor.
2. **B ohne Kosten** — Lüftungs-Rat aus Δ absoluter Feuchte + Schimmelanlass + Trockenheits-Veto. Der eigentliche Differenzierer.
3. **B mit Kosten und Fenster-Rückkopplung** — Wärmekosten-Schätzung und ereignisgetriebene Schließ-Empfehlung. Setzt voraus, dass die Slope-/Aufheizraten-Werte nach dem Refactoring stabil erreichbar sind.

Stufe 1 ist bewusst so geschnitten, dass sie **während** des Coordinator-Umbaus machbar wäre: sie braucht genau einen zusätzlichen berechneten Wert an einer Stelle, an der bereits einer entsteht.

---

## 11. Offene Entscheidungen (nicht vorweggenommen)

1. **Eigene Rechnung oder Passthrough?** Poise rechnet die absolute Feuchte ohnehin. [Thermal Comfort](https://github.com/dolezsa/thermal_comfort) ist im Ökosystem so verbreitet, dass ein optionaler Sensor-Passthrough (Muster: CO₂-Sensor in ADR-0049) Doppelrechnung vermiede — kostet aber ein Config-Feld und eine Vertrauensfrage gegenüber fremden Werten.
2. **Diagnose-Entität für den Rat?** Attribut genügt für die Card; eine recorder-exkludierbare Entität macht den Rat für fremde Automationen und Blueprints erst brauchbar. ADR-0049 §7 hat das Muster, aber es ist dort noch offen.
3. **Δ-Schwelle fest oder temperaturabhängig?** 3 g/m³ ist Feld-Konvention. Physikalisch wäre eine Schwelle sinnvoll, die bei sehr kalter Außenluft steigt (Wärmeverlust pro abgeführtem Gramm wächst) — mehr Korrektheit gegen mehr Erklärungsbedarf.
4. **Reserve auf das Schimmel-Limit** in Regel 1: wie früh vor `SURFACE_RH_LIMIT` bzw. `was_capped` soll der Rat anspringen? Zu früh = Daueralarm im Altbau, zu spät = nutzlos.

---

## 12. Nicht Teil dieses Entwurfs

Aktive Befeuchtung · KWL-/Abluft-/Fenster-Aktuierung · CO₂-**Regelung** · Lüftungsbemessung · VDI-6022-Hygiene · eine Benachrichtigungsstrecke. Für alles davon bleibt ADR-0048 die Antwort: Poise zeigt es an oder weist darauf hin — bewegen darf es nur, was seine eigenen Aktoren bewegen können.
