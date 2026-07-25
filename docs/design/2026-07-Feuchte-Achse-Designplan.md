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

### B.0 Bestandsbefund: Die Card zeigt heute die Wirkung, nicht die Ursache

Der orange Strich auf dem Dial ist **kein Schimmel-Risiko-Indikator**, sondern eine **Temperatur** — eine Regelschranke:

```
mold.py: mold_min_air_temperature(t_out, rh, t_air_ref, f_rsi=0.7, limit=0.80)
  → corridor.py    Bound(mold_min, "mold")        [untere Schranke]
  → dual_setpoint  heat_sp = max(heat_sp, mold_min)
  → coordinator    Attribut "mould_floor"
  → poise-card.ts  oranger Radial-Strich + Zahl auf dem Dial (ADR-0057)
```

Erklärt wird er an vier Stellen, von denen keine erklärt, **warum** er sich bewegt:

| Ort | Text | Leistung |
| --- | --- | --- |
| Dial-Tooltip (`localize.ts`) | „Schimmelgrenze 19,4°" | ein Label |
| Config-Flow (`de.json`) | „Raumfeuchte (aktiviert Schimmelschutz)" | *dass* der Sensor etwas freischaltet |
| Repair-Issue `mould_protection_inactive` | vier Sätze, die beste Erklärung im System | erscheint **nur bei Sensorausfall** |
| README | „surface-humidity model (DIN 4108-2)" | für Entwickler, nicht für Bewohner |

**Zwei Lücken im Bestand:**

1. **Ursache und Wirkung sind nicht unterscheidbar.** Der Tick wandert nach oben, der Raum wird härter geheizt — die auslösende Größe (Oberflächenfeuchte) wird nirgends angezeigt.
2. **`mold_capped` wird berechnet, aber nie veröffentlicht.** Der Wert entsteht in `tick_pipeline.py` über `mold_min_air_temperature_detail`, liegt im Return-Dict des Coordinators, steht aber **nicht** in der `_ATTRS`-Allowlist von `climate.py` und kommt in `card/src/` nicht vor. Genau die Lage „der Sollwert kann dich nicht mehr schützen" ist heute unsichtbar.

**Daraus folgt die Rollenteilung des Entwurfs** — zwei Zahlen, zwei Dimensionen, zwei Aufgaben:

| Größe | Einheit | Rolle | heute | nachher |
| --- | --- | --- | --- | --- |
| `mould_floor` | °C | die **Schranke** — *was* geregelt wird | Tick auf dem Dial | **unverändert** |
| `surface_rh` | % | Momentanwert | nur intern | Attribut, Diagnose |
| `surface_rh_mean` | % | der **Anlass** — *warum* die Schranke steigt | existiert nicht | Auslöser Regel 1 |
| `mold_capped` | bool | Schutz reicht nicht mehr | unsichtbar | Eskalation auf `alert` |

Der Gewinn ist damit nicht in erster Linie der neue Rat, sondern dass der **bestehende** Tick erstmals eine Begründung bekommt. Das ist genau die Linie von ADR-0057 §4: der Tick zeigt, *was* die Regelung tut — der neue Wert, *warum*.

### B.1 Neues pures Modul `comfort/ventilation.py`

Eine reine Funktion, Muster exakt wie `humidity_decide` (Dataclass rein, Dataclass raus, Latch als Parameter):

```
ventilation_advise(
    w_in, w_out,                  # absolute Feuchte innen/außen [g/m³]
    t_in, t_out,                  # für Wärmekosten + Plausibilität
    surface_rh_mean,              # GEMITTELTE Oberflächen-RH — der Anlass (§11.1c)
    mold_floor_binding,           # klemmt der Schimmelboden gerade den Sollwert?
    mold_capped,                  # aus mold.py — harte Eskalation
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
| 1 | `surface_rh_mean ≥ Limit − Marge` | `open` | `mold_risk` | **nie** gegatet (Gebäudeschutz) |
| 2 | `w_in ≤ abs_floor` **und** `w_out < w_in` | `discourage` | `too_dry` | nie gegatet |
| 3 | `w_in − w_out ≥ Δ_ein` **und** `w_in` über dem Zielband | `open` | `moisture_out` | belegungs-gegatet (Komfort) |
| 4 | `co2 ≥ Schwelle` (nur falls Sensor vorhanden) | `open` | `co2` | belegungs-gegatet |
| 5 | `window_open` **und** Anlass entfallen (`w_in − w_out < Δ_aus`) **oder** Raum am Schimmel-/Frostboden | `close` | `target_reached` / `thermal_floor` | nie gegatet |
| 6 | sonst | `idle` | `no_gain` | — |

**Regel 1 löst am Mittelwert aus, nicht am Momentanwert** (Begründung §11.1c): ein Duschstoß bewegt das gleitende Mittel kaum, eine dauerhaft zu feuchte Wand schon. Die **Dringlichkeit** eskaliert getrennt davon: `level = warn`, wenn nur das Mittel die Grenze reißt; `level = alert`, wenn zusätzlich `mold_floor_binding` (der Schimmelboden kostet gerade Heizenergie) oder `mold_capped` (der Boden kann nicht mehr schützen) gilt.

**Konsistenz-Notiz:** Regel 1 und Regel 2 können sich physikalisch nicht widersprechen — Schimmelrisiko setzt Feuchte voraus, die ein trockener Raum nicht hat. Das ist eine Invariante, die sich als Property-Test festschreiben lässt.

**Konsumvorschrift (Randbedingung aus ADR-0041):** Bei offenem Fenster wird der Schimmelboden für die ersten **30 Minuten** der Episode (`WINDOW_MOULD_SUPPRESS_S = 1800`) aus dem **Schreibpfad** unterdrückt, damit der Raum nicht gegen das Lüften auf 24 °C heizt — die **Diagnose behält den echten Wert** (`mould_floor`). `ventilation_advise` muss deshalb den **Diagnosewert** lesen, nie den geschriebenen: sonst verschwände der Schimmel-Anlass genau in dem Moment, in dem gelüftet wird, und Regel 5 („schließen") feuerte 30 Minuten lang falsch. Gehört als Kommentar an die Aufrufstelle und als Test in die Glue-Schicht.

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
| Den Rat selbst anzeigen (HA-Benachrichtigung) | ✅ | s. B.5 — der von ADR-0048 §2 ausdrücklich erlaubte Nudge |
| Push / TTS / Alexa selbst versenden | ❌ (Entwurfsentscheidung) | s. B.5 — Empfänger- und Zeitmodell, das Poise nicht besitzen will |

### B.5 Benachrichtigung — im richtigen Kanal, ohne Empfängermodell

**Ausgangspunkt:** Poise redet bereits direkt mit dem Nutzer — es erzeugt Repair-Issues **und löscht sie wieder** (`coordinator.py`, `hub_coordinator.py`, `__init__.py`) und feuert bereits ein Bus-Event (`poise_override_ended`). „Poise besitzt keine Zustellstrecke" wäre also kein Argument. Die Frage ist der **Kanal**, nicht das Ob.

Der Entwurf sieht **drei** Ausgänge vor, die alle billig sind und keiner davon ein Empfänger- oder Zeitmodell mitbringt:

| Ausgang | Zweck |
| --- | --- |
| **`persistent_notification`, selbstlöschend** (opt-in, je Zone abschaltbar) | der eingebaute, sichtbare Kanal — erscheint in der HA-Glocke, ohne dass der Nutzer etwas baut |
| **Bus-Event** `poise_ventilation_advice` (Muster: `poise_override_ended`) | erstklassiger Trigger für eigene Automationen |
| **Diagnose-Entität** (State-Token, s. §11.2) | Trigger-Ziel für Blueprints und den Entity-Picker |

**Warum `persistent_notification` der richtige Kanal ist** — er räumt genau die Kostenliste leer, die gegen eine Push-Strecke spricht:

| Kostenpunkt einer Push-Strecke | mit `persistent_notification` |
| --- | --- |
| Empfängermodell (Poise ist pro **Zone** modelliert, `notify`-Ziele sind pro **Person**) | entfällt — die Notification hängt an der Instanz |
| Ruhezeiten („Fenster öffnen" um 3 Uhr) | entfällt — sie klingelt nicht, sie erscheint |
| Wiederholungs-/Eskalationspolitik | entfällt — dieselbe `notification_id` wird **ersetzt**, nie dupliziert |
| stille Ausfälle (`notify.mobile_app_*` ändert die ID nach Handy-Neuinstallation) | entfällt — kein Zielobjekt, das verschwinden kann |
| Testbarkeit | die Entscheidung bleibt pur; nur die Emission sitzt am Rand |

**Das Alleinstellungsmerkmal ist das Zurückziehen.** Die Schließ-Empfehlung ist keine zweite Benachrichtigung, sondern das **Ersetzen bzw. Löschen der ersten** unter derselben `notification_id` — dasselbe Muster, das Poise mit `async_create_issue` / `async_delete_issue` schon fährt. Die Blueprints im Feld können das nur über Helper-Booleans und Timer nachstellen (siehe die `input_boolean`-Krücke bei [adamcornforth](https://github.com/adamcornforth/ha-open-window-blueprint)).

**Bewusst nicht gebaut:** `notify`-Ziel-Konfiguration, Ruhezeiten, Wiederholungs-/Eskalationslogik, Quittierung/Snooze. Wer Push, TTS oder Alexa will, hängt drei Zeilen an Event oder Entität — und benutzt dafür die Blueprints, die diesen Kanal bereits gut können. Poise liefert, was dort fehlt: die **Begründung**.

**Ebenfalls bewusst nicht:** den Rat als **Repair-Issue** führen. Repairs sind für System-/Konfigurationsprobleme gedacht, die der Nutzer beheben soll; ein wiederkehrender Lüftungshinweis würde die Repair-Liste verwässern und den Nutzer trainieren, Repairs zu ignorieren.

**Unterdrückung bleibt innen.** Anwesenheit (ADR-0058), Belegung, Fensterzustand und Anlass-Gültigkeit entscheiden **in `ventilation_advise`**, ob überhaupt ein Rat entsteht — nicht im Kanal. Damit muss keine nachgelagerte Automation Zustandslogik nachbauen, die Poise ohnehin hat.

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
| `surface_rh` | float | `mold.py` (existiert bereits als Rechnung) | Momentanwert, Diagnose |
| `surface_rh_mean` | float | §11.1c, persistiert | **der Anlass** von Regel 1 |
| `mold_capped` | bool | **existiert bereits, wird nur nicht veröffentlicht** (§B.0) | Eskalation auf `alert`; schließt nebenbei eine Bestandslücke |
| `vent_action` | `idle\|open\|close\|discourage` | B.1 | Rat |
| `vent_reason` | Token | B.1 | Begründung (i18n) |
| `vent_delta_gm3` | float \| null | B.1 | die Zahl hinter dem Rat |
| `vent_cost_kwh` / `vent_cost_eur` | float \| null | B.4 | Schätzung, als solche ausgewiesen |

Card-seitig: die **Feuchte-Lampe** bekommt den g/m³-Wert in Titel/`aria-label`; der Lüftungs-Rat wird ein **Chip** (Muster `override_clamped`), keine Lampe — er trägt Text, keine Messgröße.

Außerhalb der Card (B.5): eine **Diagnose-Entität** mit `vent_action` als State-Token — bewusst **ohne** die schnell wechselnden Felder (`vent_delta_gm3`, Kosten) als eigene Attribute, die bleiben an der Climate-Entität. Dazu das Bus-Event `poise_ventilation_advice` mit `{zone, action, reason, delta_gm3}` und die selbstlöschende `persistent_notification` unter einer stabilen, zonenbezogenen `notification_id`.

---

## 6. Schichten und Refactor-Berührung

| Ort | Änderungsart | Berührt den Coordinator-Umbau? |
| --- | --- | --- |
| `estimation/psychrometrics.py` | +1 reine Funktion | nein |
| `comfort/humidity.py` | nur ein Kommentar an der 12-g/kg-Konstante | nein |
| `comfort/ventilation.py` | **neu**, rein | nein |
| `estimation/running_mean.py` | **wiederverwendet** — dieselbe exponentielle Mittelung wie für `T_rm`, angewandt auf die Oberflächen-RH; keine Änderung am Modul | nein, aber der Mittelwert braucht **Persistenz** (bestehender Pfad: `storage.py` / `persistence/codec.py`) |
| `diagnostics/shadows.py` → `compose_climate_band` | +Parameter, +Dict-Schlüssel | **die einzige Naht** — bereits eine reine Funktion |
| `coordinator.py` | ausschließlich **Argument-Konstruktion** innerhalb des bestehenden einen `try` | minimal, additiv, keine neue Stage, kein neuer Fehlerbereich |
| `climate.py` | Attribut-Allowlist erweitern | nein |
| Emissions-Rand (B.5): `persistent_notification`, Bus-Event, Diagnose-Entität | **der einzige seiteneffektbehaftete Teil** — reine Funktion rein, Zustellung raus, keine Logik | nein, aber am besten *nach* dem Umbau verdrahten |
| `runtime/config.py`, `const.py` | 1 optionales Sensor-Feld, optionale Schwellen, Notification-Opt-in | nein |
| `trace/schema.py` | optionale Felder | nein |
| `card/src/monitoring.ts`, `poise-card.ts`, `card-config.ts` | Verdict-Erweiterung + Chip + Config | nein |

**Der Punkt für dein Refactoring:** die gesamte Fachlichkeit ist ohne den Coordinator schreib- und testbar. Was auch immer aus `_stage_climate_band` wird — die neuen Werte reisen als Argumente in dieselbe pure Komposition, in der `humidity_action` und `abs_humidity_gkg` heute schon entstehen. Wenn der Umbau die Stage neu schneidet, wandert die Argument-Konstruktion mit; es gibt nichts zu migrieren.

---

## 7. Abgrenzung zu ADR-0048

Der Entwurf bewegt sich innerhalb des Leitprinzips, berührt aber dessen Formulierung an einer Stelle und braucht deshalb **einen eigenen ADR**:

- ADR-0048 §2 verbietet CO₂-getriebene Lüftungs-**Steuerung** und erlaubt den Hinweis ausdrücklich („CO₂ hoch — Fenster öffnen"). Regel 4 der Tabelle in B.2 ist genau dieser erlaubte Nudge — die Grenze ist aber bisher nur allgemein gezogen und sollte für einen strukturierten, begründeten Rat präzisiert werden. Dass der Nudge **sichtbar** wird (B.5), ist Teil desselben Satzes: ein Hinweis, den niemand sieht, ist kein Hinweis.
- Es entsteht **kein** Kommando: keine `fan`-Entität, kein `humidifier`, kein Service-Call an ein Gerät. Der `assignment_planner` baut weiterhin ausschließlich `Axis.THERMAL`. `Axis.VENTILATION` bleibt tot und darf es bleiben — der Rat ist ein *Zustand* (Attribut, Entität, Event) plus eine HA-interne Anzeige, keine Achse. Der einzige Service-Call geht an `persistent_notification`, also an die HA-Oberfläche, nicht an Hardware.
- Die Nicht-Ziele bleiben unangetastet: keine aktive Befeuchtung (§3), keine RLT-Hygiene (§1), kein Lüftungs-Bemessungsanspruch (§2).

### 7.1 ADR-Auswirkungen im Überblick

**Ungültig wird keine bestehende Entscheidung.** Geschuldet sind Nachträge:

| ADR | betroffen | Art |
| --- | --- | --- |
| **0049** (Monitoring-Ampel) | ja, **inhaltlich** | §5 legt `[30, 40, 60, 65]` **% RH** fest; die untere Seite wird auf g/m³ umgestellt (A.2/A.3) → echter Nachtrag, kein Beiwerk |
| **0048** (Nicht-Ziele) | ja, Präzisierung | §2 zieht die Grenze Nudge ↔ Lüftungssteuerung nur allgemein; ein strukturierter, sichtbarer Rat gehört ausformuliert (§7) |
| **0057** (Card-Layout) | ja, Erweiterung | „Schimmel-Tick display-only" bleibt gültig; ein neuer Chip kommt in die `resolveChips`-Tokenliste |
| **0016** (Entity-/Card-Vertrag) | ja, Erweiterung | neue Attribute + eine Diagnose-Entität — der reguläre Weg |
| **0012** (Redaction) | ja, mechanisch | optionaler Außen-Feuchtesensor gehört in `REDACT_KEYS` |
| **0050** (Dry-Pfad) | nein | Regelpfad unberührt; die 12-g/kg-Klarstellung (A.4) ist ein Kommentar |
| **0041** (Fenster) | nein, aber Randbedingung | die 30-Minuten-Unterdrückung — Konsumvorschrift in B.2, keine Änderung |
| **0030** (Anti-Garbage-In) | nein | stützt die „selbst rechnen"-Entscheidung (§11.1a) |
| **0026 / 0033** (Shadow-first) | nein | trivial erfüllt — es wird nie aktuiert |

### 7.2 Bestandsbefund: das Schimmelmodell hat keinen ADR

Beim Abgleich der Verweise: `mold.py` nennt „charter G4, ADR-0010", `estimation/psychrometrics.py` „ADR-0010 mould/psychrometrics", ADR-0048 und ADR-0050 zitieren „ADR-0010 (Schimmel/Taupunkt)" — **ADR-0010 ist aber „Solar-Buchhaltung"**. Kein ADR im Verzeichnis behandelt `f_Rsi`, DIN 4108-2 oder EN ISO 13788 als *Entscheidung*; die einzigen Treffer (ADR-0011, ADR-0014, ADR-0048) sind Test- bzw. Abgrenzungskontexte. Das referenzierte „charter G4" liegt nicht im Repo.

Damit ist die **härteste Sicherheitsschranke des Systems die einzige undokumentierte**, und vier Stellen zeigen auf die falsche Nummer. Das macht nichts ungültig und blockiert diesen Entwurf nicht — es sollte nur nicht mit ihm mitwachsen.

**Vorschlag:** ein **eigener, rückwirkend dokumentierender ADR** für den Schimmelboden (Vorbild: ADR-0048 hat die Nicht-Ziele nachträglich festgeschrieben), nicht ein Kontext-Abschnitt in ADR-0062. Sonst stünde die Bestandsentscheidung in einem Dokument, das eine Erweiterung beschreibt — und der nächste Leser sucht sie wieder an der falschen Stelle. Die Korrektur der vier Verweise gehört in denselben Zug.

---

## 8. Fehlerverhalten und Degradation

| Ausfall | Verhalten |
| --- | --- |
| kein Innen-Feuchtesensor | beide Features still inaktiv (wie heute) |
| keine Raumtemperatur | absolute Feuchte fällt aus → untere Ampel-Seite degradiert auf RH `[30, 40]` |
| keine Außenfeuchte | Feature B still inaktiv; Feature A unberührt |
| kein CO₂-Sensor | Regel 4 entfällt, Rest unverändert |
| Ausnahme in der Komposition | fällt mit dem bestehenden `climate_diag`-Block zusammen — **wichtig:** anders als beim Dry-Nudge ist der Fallback hier folgenlos, weil nichts aktuiert wird |
| Ausnahme beim Zustellen (B.5) | darf den Tick nie berühren: der Rat bleibt als Zustand gültig, nur die Anzeige fehlt. Eine hängengebliebene Notification wird beim nächsten Zustandswechsel unter derselben `notification_id` ersetzt oder gelöscht — sie kann nicht dauerhaft falsch stehenbleiben |
| Integration wird entladen / Zone entfernt | offene Notifications derselben `notification_id` werden aufgeräumt, analog zum bestehenden `async_delete_issue`-Pfad |

Die Anzeige zeigt im Zweifel **nichts** statt etwas Falschem — dieselbe Linie wie die stillen Fallbacks in `monitoring.ts`.

---

## 9. Testbarkeit (Entwurfsanforderung, nicht Testplan)

- Alles Fachliche ist rein → Unit-Tests ohne HA, wie `test_humidity.py` / `test_psychrometrics.py`.
- **Property:** das Trockenheits-Verdict ist monoton in `w` (mehr Feuchte darf nie schlechter bewerten).
- **Invariante:** `mold_risk` und `too_dry` schließen sich aus (B.2).
- **Guard-Test** im Geist von `tests/test_non_goals.py`: weder das Trockenheits- noch das Lüftungs-Verdict darf in `humidity_decide`, `dual_setpoint` oder den Constraint-Solver gelangen; `ventilation_advise` erzeugt nie ein Kommando an ein Gerät.
- **Purheits-Grenze bei B.5:** `ventilation_advise` entscheidet, der Rand stellt zu. Der Rand enthält keine Fachlogik — kein Schwellenvergleich, keine Unterdrückung, keine Zeitlogik. Prüfbar als Test „gleicher Zustand → keine zweite Notification, Zustandswechsel → Ersetzen bzw. Löschen".
- **Umrechnungs-Referenz:** g/m³ ↔ g/kg ↔ RH an bekannten Stützstellen (20 °C/40 % = 7,0 g/m³ = 5,9 g/kg).
- **Alarmfestigkeit als Test:** ein einzelner Feuchtestoß (Duschen, Kochen) darf Regel 1 **nicht** auslösen; eine anhaltend zu feuchte Wand schon; nach dem Lüften fällt das Mittel von selbst unter die Grenze zurück und zieht den Rat zurück. Drei Zeitreihen-Tests gegen die reine Mittelungsfunktion, ohne HA.

---

## 10. Sinnvolle Reihenfolge (grob, jederzeit unterbrechbar)

Jede Stufe ist für sich auslieferbar und wertvoll:

1. **A** — absolute Feuchte veröffentlichen und die untere Ampel-Seite darauf umstellen. Null Regelrisiko, korrigiert einen echten Bewertungsfehler, braucht keinen neuen Sensor.
2. **B ohne Kosten** — Lüftungs-Rat aus Δ absoluter Feuchte + Schimmelanlass + Trockenheits-Veto. Der eigentliche Differenzierer. Braucht als einzige Vorarbeit das **persistierte Oberflächen-RH-Mittel** (§11.1c) — sinnvollerweise schon in Stufe 1 mitgeschrieben, damit α an echten Daten kalibriert werden kann, bevor Regel 1 scharf geschaltet wird.
3. **B mit Kosten und Fenster-Rückkopplung** — Wärmekosten-Schätzung und ereignisgetriebene Schließ-Empfehlung. Setzt voraus, dass die Slope-/Aufheizraten-Werte nach dem Refactoring stabil erreichbar sind.

Stufe 1 ist bewusst so geschnitten, dass sie **während** des Coordinator-Umbaus machbar wäre: sie braucht genau einen zusätzlichen berechneten Wert an einer Stelle, an der bereits einer entsteht.

---

## 11. Entscheidungsstand

### 11.1 Entschieden

Alle vier ursprünglich offenen Punkte sind entschieden.

**(0) Ausgabekanal des Lüftungs-Rats (war: „Diagnose-Entität oder nur Attribut?").**
Entschieden für **alle drei Ausgänge**: selbstlöschende `persistent_notification` (opt-in) + Bus-Event + Diagnose-Entität mit State-Token — Begründung und Abgrenzung in B.5. Die ursprüngliche Fassung dieses Entwurfs sah **keine** eigene Benachrichtigung vor; das war auf die Push-/`notify`-Variante gemünzt und als Pauschalaussage falsch, weil Poise mit Repair-Issues und `poise_override_ended` bereits eigene Nutzerkommunikation betreibt. Verworfen bleibt ausschließlich die **Push-/TTS-Strecke** mit Empfänger-, Ruhezeit- und Wiederholungsmodell.

**(a) Absolute Feuchte: eigene Rechnung, kein Passthrough.**
Kein Config-Feld für einen fremden [Thermal-Comfort](https://github.com/dolezsa/thermal_comfort)-Sensor. Ausschlaggebend ist der Bestand: der 12-g/kg-Backstop ist ein **Live-Control-Input** und darf nach ADR-0030 nie an einem fremden Sensor hängen. Ein Passthrough könnte deshalb nur die *Anzeige* bedienen — Ergebnis wären zwei Quellen für eine Größe. Der verbleibende Nachteil ist kosmetisch: andere Sättigungskoeffizienten ergeben ~1 % Abweichung zu einem parallel installierten Thermal-Comfort-Sensor. Wird dokumentiert, nicht gelöst.

**(b) Δ-Schwelle fest bei 3,0 g/m³.**
**Korrektur gegenüber der ersten Fassung dieses Entwurfs:** dort stand die Vermutung, die Schwelle müsse bei kalter Außenluft steigen, weil der Wärmeverlust wächst. Nachgerechnet ist es umgekehrt — kalte Luft ist so trocken, dass Δw schneller wächst als ΔT:

| Lage | Δw | ΔT | Wärme pro m³ | **pro entferntem Gramm** |
| --- | --- | --- | --- | --- |
| 20 °C/46 % innen, −5 °C/90 % außen | 4,9 g/m³ | 25 K | 8,3 Wh | **1,7 Wh/g** |
| 20 °C/52 % innen, 10 °C/80 % außen | 1,5 g/m³ | 10 K | 3,3 Wh | **2,2 Wh/g** |

(ρ·c_p ≈ 1,2 kJ/(m³·K), ohne Wärmerückgewinnung.) Winterlüften ist pro Gramm **billiger**. Eine winterliche Verschärfung würde Poise ausgerechnet dort schlechter machen, wofür es gedacht ist. Das eigentliche Winterproblem ist nicht der Preis, sondern das Überschießen in die Trockenheit — und das erledigt Regel 2. Saubere Trennung: **Δ** beantwortet *wirkt es?*, das **Veto** *wollen wir das?*, die **Kostenschätzung** *was kostet es?*. Eine enthalpiebasierte Bewertung (Weg der GSW-Suite) wäre ein eigenes Feature, keine Schwellenkorrektur.

**(c) Schimmel-Anlass: gemittelte Oberflächen-RH als Auslöser, Konsequenz als Eskalation.**

Die Frage war ursprünglich als „wie viel Reserve vor der 80-%-Grenze?" gestellt. Der Wettbewerbsvergleich hat sie umformuliert: es geht nicht um die **Höhe** der Schwelle, sondern um den **Zeitraum**.

*Wie es andere lösen.* Die Smart-Home-Welt delegiert: der [HA-Core Mold Indicator](https://www.home-assistant.io/integrations/mold_indicator/) liefert nur eine Prozentzahl ohne jeden Auslöser, [ha-optimal-humidity](https://github.com/TheRealWaldo/ha-optimal-humidity) einen Momentanwert-Boolean, [Homematic IP](https://homematic-ip.com/de/produkt/temperatur-und-luftfeuchtigkeitssensor-innen) lässt den Nutzer konfigurieren, *ob und wann* er die Warnung überhaupt bekommen will — Zeitfenster statt Modell. Die Bauphysik hat das Problem dagegen gelöst, indem sie die Momentanschwelle aufgegeben hat: das **VTT-/Viitanen-Modell** ([Hukka & Viitanen 1999](https://research.tuni.fi/buildingphysics/finnish-mould-growth-model/), erweitert Ojanen 2010) führt einen Schimmelindex 0–6, der über der Grenze wächst und **in Trockenperioden wieder abfällt**; die **Sedlbauer-Isoplethen/LIM** ([Fraunhofer IBP](https://publica.fraunhofer.de/bitstreams/011d55af-cc14-4319-b95a-a6ceab618caa/download)) verlangen eine Verweildauer oberhalb einer temperatur- und substratabhängigen Kurve. Der kommerzielle Kompromiss ist [Airthings' Schimmelindikator](https://help.airthings.com/en/articles/4419641-wave-what-is-the-mold-risk-indicator-wave-mini-only): Temperatur + Feuchte + Zeit über ein **rollierendes 48-h-Fenster**.

*Der Befund im eigenen Haus.* **EN ISO 13788 — die Norm, auf die `mold.py` sich beruft — definiert die 80 % selbst auf Monatsmittelwerten** (`f_Rsi,min` je Monat, der kritische Monat entscheidet). Einen Momentanwert kennt die Norm nicht. Für den **Regelboden** ist Poises tickweise Auswertung dennoch richtig — Sicherheit darf nicht mitteln, konservativ klemmen kostet nur Wärme. Für einen **Hinweis** ist sie normfremd, und genau daraus entsteht die Alarmmüdigkeit.

*Entscheidung.* Regel 1 löst am **exponentiell gewichteten gleitenden Mittel der Oberflächen-RH** aus. Der Baustein liegt bereits im Repo: `estimation/running_mean.py` macht genau diese Mittelung für `T_rm` nach EN 16798-1, inklusive Persistenz — er wird wiederverwendet, nicht geändert. Die feste Reserve schrumpft auf eine **technische Marge** (~5 Prozentpunkte für Sensorrauschen und `f_Rsi`-Unsicherheit), sie ist kein Steuerungshebel mehr. Die **Dringlichkeit** trägt den ökonomischen Teil des ursprünglichen Vorschlags: `warn` beim Reißen des Mittels, `alert`, wenn zusätzlich der Schimmelboden gerade Heizenergie kostet (`mold_floor_binding`) oder `was_capped` greift.

*Verworfen: der volle VTT-Index.* Er ist material- und substratabhängig (Ojanen 2010 unterscheidet Fichte, Beton, Porenbeton, Mineralwolle, EPS …). Poise kennt die Wandoberfläche nicht und kann sie nicht erfragen, ohne eine Konfigurationsfrage zu stellen, die kaum jemand richtig beantwortet — ein Index mit falscher Materialklasse ist schlechter als ein ehrliches gleitendes Mittel.

*Nebeneffekt, der zum Rest passt:* das Mittel liefert die **Entwarnung** gleich mit. Es fällt nach dem Lüften von selbst zurück, womit das Zurückziehen der Notification (B.5) ein Zustandswechsel wird statt eines Timers.

### 11.2 Verbleibend offen

**Die Zeitkonstante α des Oberflächen-RH-Mittels.** 48 h (Airthings-Linie) ist erklärbar und reagiert schnell; mehrere Tage liegt näher an den Keimungsdauern der Isoplethen-Modelle und ist alarmfester. Das ist die einzige verbliebene Zahl, die sich nicht am Schreibtisch entscheiden lässt — sie braucht Live-Daten, sobald die Oberflächen-RH mitgeschrieben wird. Bis dahin gilt als Arbeitswert die Airthings-Linie (~48 h), weil sie die konservativere Wahl in Richtung *zu früh* statt *zu spät* ist.

---

## 12. Nicht Teil dieses Entwurfs

Aktive Befeuchtung · KWL-/Abluft-/Fenster-Aktuierung · CO₂-**Regelung** · Lüftungsbemessung · VDI-6022-Hygiene · eine Push-/`notify`-Zustellstrecke mit Empfänger-, Ruhezeit- und Wiederholungsmodell (der HA-interne Hinweiskanal dagegen **ist** Teil des Entwurfs, s. B.5). Für alles davon bleibt ADR-0048 die Antwort: Poise zeigt es an oder weist darauf hin — bewegen darf es nur, was seine eigenen Aktoren bewegen können.
