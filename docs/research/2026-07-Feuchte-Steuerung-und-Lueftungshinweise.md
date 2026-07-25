# Recherche: Feuchte-Steuerung & Lüftungs-Hinweise im HA-Ökosystem

**Datum:** 2026-07-25 · **Typ:** Recherche-Notiz (kein ADR, keine Entscheidung) · **Anlass:** Bewertung eines Laien-Artikels zur „gesunden" absoluten Luftfeuchtigkeit ([cardiopraxis.de](https://www.cardiopraxis.de/corona-praevention-raumluftqualitaet/)) → Frage, was Poise auf der **Feuchte-Achse** heute kann, was der Wettbewerb kann und was Nutzer verlangen. · **Bezug:** ADR-0010, ADR-0041, ADR-0048, ADR-0049, ADR-0050

---

## 1. Bestandsaufnahme Poise (Code-Befund)

| Baustein | Datei | Was es tut | Grenze |
| --- | --- | --- | --- |
| Entfeuchtungs-Entscheidung | `comfort/humidity.py` | Dry-Guard `rh_low`=40 % (oberste Präzedenz) → cool-first → `dry` im Totband bei RH ≥ Kategorie-Decke (Cat I/II/III = 50/60/70 %) **oder** ≥ 12 g/kg; asymmetrische Hysterese; relative Decke belegungs-gegatet, absolute nie | nur **abwärts**; kein Trocken-Kriterium außer dem Blocker |
| Psychrometrie | `estimation/psychrometrics.py` | Magnus (Alduchov-Eskridge), `saturation_pressure`, `vapour_pressure`, `dewpoint`, `temperature_at_saturation`, `humidity_ratio` → **g/kg** | kein g/m³, keine Enthalpie, keine Außenluft-Rechnung |
| Schimmelschutz | `comfort/mold.py` | `f_Rsi`=0,7 (DIN 4108-2 Bestand), Oberflächen-RH-Limit 80 %, invertiert auf Mindest-Lufttemperatur, bei 24 °C gedeckelt + `was_capped`-Flag | wirkt über **Temperatur**, nie über Feuchteabfuhr |
| Ampel | `card/src/monitoring.ts` | `humidityVerdict` mit 4 Grenzen `[30, 40, 60, 65]` % RH; CO₂ UBA/EN; card-seitig, null Recorder-Last | rein **relativ**; kennt weder g/m³ noch Außenluft |
| Fenster | ADR-0041 | Sensor oder Slope-Detektor → Absenkung auf Frost/Schimmel-Boden, Lernen pausiert | rein **reaktiv**; kein Hinweis „jetzt lüften", kein „jetzt schließen" |
| Nicht-Ziele | ADR-0048 | keine Befeuchtung, kein CO₂-/Lüftungs-**Management**, keine RLT-Hygiene; Leitprinzip *Monitoring vs. Control* mit ausdrücklich erlaubtem **Nudge** („CO₂ hoch — Fenster öffnen") | Hinweis-Pfad ist erlaubt, aber nie gebaut worden |

**Bereits vorhanden, aber ungenutzt:** `abs_humidity_gkg` wird je Tick berechnet (Coordinator → `humidity_ratio(room, rh)`) und ist schon **veröffentlichtes Climate-Attribut** (`climate.py`) sowie Trace-Feld. Die Card zeigt es nicht an. Der Wert existiert also — es fehlt nur die Auswertung.

**Ebenfalls vorhanden:** eine konfigurierte **Weather-Entität** (`ha/forecast_provider.py`, für Optimal Start) und ein Außentemperatur-Sensor (`CONF_OUTDOOR_SENSOR`). HA-Weather-Entitäten führen ein `humidity`-Attribut → **die Außenfeuchte ist ohne neue Hardware-Anforderung verfügbar**. Ein eigener Außen-Feuchtesensor existiert im Config-Flow bisher nicht (`CONF_HUMIDITY_SENSOR` ist der Innensensor).

### 1.1 Zwei Zahlenbefunde aus dem Bestand

**(a) Der 12-g/kg-Backstop ist ein Warmraum-Kriterium und schützt im Winter nichts.**
12 g/kg entspricht bei 20 °C p_v ≈ 1918 Pa → **≈ 82 % RH bzw. ≈ 14,2 g/m³**. Die Cat-II-Decke (60 % RH) bindet also weit vorher. Die Kreuzung liegt bei **≈ 25 °C**: erst darüber ist der absolute Backstop die zuerst greifende Grenze (der ADR-0050-Beispielfall 30 °C/50 % ≈ 13,3 g/kg ist genau das). Für Winter-Schimmel leistet er nichts — dort arbeitet allein `mold.py` über die Mindest-Lufttemperatur. Das ist korrekt so, sollte aber nirgends anders gelesen werden können.

**(b) Der Dry-Guard trifft die physiologische Untergrenze — aber nur zufällig bei genau 20 °C.**
40 % RH bei 20 °C ≈ **7,0 g/m³** (≈ 5,9 g/kg) — exakt die Größenordnung, ab der die Literatur (Shaman/Kohn, Kudo/Iwasaki) trockenheitsbedingte Schleimhaut-Effekte beschreibt. Die Schwelle driftet aber mit der Temperatur:

| Raumtemperatur | 40 % RH entspricht | Bewertung |
| --- | --- | --- |
| 18 °C | **6,1 g/m³** | zu trocken, Ampel meldet nichts |
| 20 °C | 7,0 g/m³ | Grenzfall |
| 22 °C | 7,8 g/m³ | ok |
| 24 °C | 8,7 g/m³ | ok |

Dasselbe Argument, das ADR-0050 auf der **oberen** Seite zum absoluten Backstop geführt hat, gilt symmetrisch unten — dort ist es bisher nicht gezogen worden. Umgekehrt gilt: ein kühler Raum mit 18 °C/45 % RH ist auf der Ampel **grün**, obwohl er mit 6,9 g/m³ absolut trockener ist als ein Raum mit 24 °C/35 % RH (7,6 g/m³), der **gelb** leuchtet. Die RH-Ampel bewertet die Winterlage falsch herum.

---

## 2. Wettbewerbslandschaft

Das Feld zerfällt sauber in vier Schichten. Bemerkenswert: **niemand koppelt Schicht A/C an einen Heizungsregler.**

### A. Psychrometrie-Lieferanten (nur Sensoren, keine Steuerung)

| Projekt | Liefert | Anmerkung |
| --- | --- | --- |
| [Thermal Comfort (dolezsa)](https://github.com/dolezsa/thermal_comfort) | absolute Feuchte **g/m³**, Taupunkt, Frostpunkt, feuchte Enthalpie, Humidex/Heat Index, „thermal perception" | De-facto-Standard im Ökosystem; jede zweite Lüftungs-Automation setzt darauf auf |
| [juliusknorr/absolute_humidity](https://github.com/juliusknorr/homeassistant_absolute_humidity) | g/m³ + Taupunkt + **Fenster-Empfehlung**, automatische Paarung Temperatur↔Feuchte über Namenskonvention | Zustände „ok to open" / „too wet" / „too warm" / „opening recommended"; Regel: Außen-Taupunkt ≥ 5 K unter innen |
| [TheRealWaldo/ha-optimal-humidity](https://github.com/TheRealWaldo/ha-optimal-humidity) | `optimal_humidity`, `critical_humidity`, `mold_warning`, `dewpoint`, `humidex`, spezifische Feuchte | Braucht einen **Sensor am kältesten Punkt** — genau die Eingangsgröße, die Poise über `f_Rsi` schätzt statt zu messen |
| [HA-Core Mold Indicator](https://www.home-assistant.io/integrations/mold_indicator/) | Oberflächen-RH am kalibrierten kritischen Punkt, > 70 % = Warnung | **Manuelle Kalibrierung** ist die Standard-Beschwerde; Poises `f_Rsi`-Ansatz ist hier fachlich sauberer |
| [ha-dewpoint](https://github.com/alf-scotland/ha-dewpoint) | Taupunkt ohne externe Referenz | minimal |

### B. Feuchte-Aktuierung (bereits in ADR-0050 belegt, hier nur Delta)

`generic_hygrostat` (Core, Goldstandard-Bang-Bang mit `min_cycle_duration` + Stale-Sensor-Not-Aus), `humidifier`-Domäne, `dual_smart_thermostat` (DRY > HEAT > COOL), VTherm (Humidity-PR abgelehnt), SmartIR (display-only). **Unverändert gültig:** die einzige Feuchte-Fähigkeit im Thermostat-Feld ist Entfeuchtung; Befeuchtung ist überall eine eigene Domäne.

### C. Lüftungs-Hinweise / Ampeln (Blueprints — das aktivste Segment)

| Lösung | Logik | Schwächen |
| --- | --- | --- |
| [Open Window Recommendation (adamcornforth)](https://github.com/adamcornforth/ha-open-window-blueprint) | Magnus → absolute Feuchte innen/außen, Empfehlung bei Δ ≥ **3 g/m³**, Edge-Trigger über `input_boolean`, Push | kein TTS; kein Temperatur-/Heizkosten-Kriterium; Helper-Krücke für Zustandshaltung |
| [🪟 Ventilation Recommendation v0.4.x](https://community.home-assistant.io/t/blueprint-ventilation-recommendation-v0-3-0-smart-ventilation-alerts-via-push-alexa-ha-ui-beta/989969) | Δ absolute Feuchte → Push / Alexa / persistente Notification | reine Benachrichtigung, kein Regelbezug |
| [🌬️ GSW Smart Ventilation Suite](https://community.home-assistant.io/t/gsw-smart-ventilation-suite-absolute-humidity-dew-point-logic/995338) | Psychrometrie inkl. **Enthalpie**, CO₂-bewusst, saisonale Bias, Hersteller-Profile, „smart pause" | ambitioniertester Vertreter; YAML-Blueprint-Grenzen (kein Lernen, kein Modell) |
| [Smart Ventilation based on Absolute Humidity](https://community.home-assistant.io/t/smart-ventilation-based-on-absolute-humidity/986783) | Fenster auf/zu per Δ AH | — |

### D. Lüftungs-Aktuierung

| Lösung | Art |
| --- | --- |
| [Ventilation Assistant (derabbink)](https://github.com/derabbink/ha_hacs_ventilation_assistant) | **Der nächste architektonische Nachbar:** virtuelles Gerät aus Innen-/Außensensoren + Fensterkontakten; rechnet absolute Feuchte und **projizierte Innen-RH nach dem Lüften**; 4-Zustands-Rat `KEEP_CLOSED`/`OPEN`/`KEEP_OPEN`/`CLOSE` je Achse (Temperatur/Feuchte/CO₂) mit wählbarer Priorität — **ausdrücklich nur Empfehlung, keine Aktuierung** |
| [🚿 Bathroom Humidity Exhaust Fan](https://community.home-assistant.io/t/bathroom-humidity-exhaust-fan/509992) | meistgenutzte Feuchte-Automation überhaupt (~860+ Antworten); löste das Saison-Problem über **Derivative/Trend** statt fixer Schwelle |
| [Baseline-Differenz-Blueprint](https://community.home-assistant.io/t/turn-a-fan-on-and-off-based-on-the-difference-between-a-humidity-sensor-and-a-baseline/255999) | Lüfter nach Differenz Raum ↔ Referenzraum | |
| KWL/dezentral | [Zehnder ComfoConnect](https://www.home-assistant.io/integrations/comfoconnect/) (Core: `fan` + Sensoren; Bypass/Boost nur in der [Custom-Variante](https://github.com/michaelarnauts/home-assistant-comfoconnect)), Helios/Vallox/Pluggit über **Modbus**, [hass-lunos](https://github.com/rsnodgrass/hass-lunos), [Ambientika](https://www.ambientika.eu/en/c/decentralized-ventilation-with-home-assistant-integration-perfect-integration-into-your-smart-home/), [FaLs22 Taupunktlüftung](https://github.com/DoctorExitus/ha-fals22) | Alle exponieren HA-`fan`-Entitäten — d. h. ein Lüftungs-Aktor ist im Ökosystem **standardisiert vorhanden**, Poise müsste keine Hardware „besitzen" |

### Lücke im Feld

1. Kein Projekt koppelt die Lüftungs-Empfehlung an ein **gelerntes thermisches Modell** — niemand sagt, *wie lange* zu lüften ist oder *was es kostet*.
2. Kein Projekt verbindet die Feuchte-Empfehlung mit einem **bauphysikalischen Schimmelmodell** (Oberflächen-RH); Mold Indicator und die Lüftungs-Blueprints leben nebeneinander her.
3. Die Ampel-/Empfehlungs-Projekte kennen **keine Heizungs-Rückkopplung** (Fenster auf → Absenkung); die Thermostate kennen **keine Feuchte-Empfehlung**. Poise hat als einziges Projekt beide Seiten bereits im Haus.

---

## 3. Nutzerwünsche (Belege)

1. **„Relative Feuchte führt im Winter in die Irre"** — der wiederkehrende Aha-Moment: 5 °C/85 % Außenluft ergibt bei 21 °C nur ~28 % RH. Genau deshalb sind alle ernsthaften Lüftungs-Blueprints auf **absolute** Feuchte umgestiegen. Poise misst und bewertet in der Card bis heute nur relativ.
2. **„Nur melden, wenn etwas nicht stimmt"** — read-only-Hinweise werden gegenüber Auto-Lüftung ausdrücklich bevorzugt (bereits in ADR-0048 belegt: Auto-Lüftung „ging nach hinten los").
3. **Statische RH-Schwellen versagen über die Jahreszeiten** — der zentrale Konstruktionsfehler, den die Bad-Lüfter-Blueprints über Trend-/Baseline-Erkennung umgehen mussten.
4. **1000 ppm CO₂ ist die De-facto-Lüftungslinie** (UBA), 800 ppm präventiv — in ADR-0049 bereits umgesetzt, aber ohne Handlungshinweis.
5. **Kein Projekt beantwortet „wie lange?"** — die „Fenster wieder schließen"-Erinnerung ist in mehreren Blueprints ein explizit beworbenes Feature, immer als fester Timer oder simple Rückschwell-Bedingung, nie modellbasiert.
6. **Überkühlung / Kosten beim Jagen einer RH-Zahl** — ADR-0050s #1-Nutzerklage; das Lüften-Analogon (Wärmeverlust) ist unquantifiziert.
7. **Feuchte auf der Thermostat-Card** ist ein jahrelanger Core-Wunsch ([frontend #4740](https://github.com/home-assistant/frontend/issues/4740)) — Poise erfüllt ihn seit v0.103.0.
8. **Ökosystem-Reibung bei der Einheit:** `device_class: humidity` akzeptiert **kein g/m³** — [core #127619](https://github.com/home-assistant/core/issues/127619) wurde als *closed / not planned* geschlossen. Absolute Feuchte muss daher als Sensor **ohne** `device_class` (nur `unit_of_measurement`) veröffentlicht werden.

---

## 4. Bewertung & Empfehlung für Poise

Alles Folgende bleibt innerhalb von ADR-0048: *anzeigen und hinweisen darf Poise alles, steuern nur, was seine Aktoren bewegen.*

### Empfohlen

**(1) Absolute Feuchte sichtbar machen + Trocken-Untergrenze in der Ampel** — kleinster Aufwand, größte fachliche Korrektur.
`abs_humidity_gkg` existiert bereits als Attribut; ergänzend ein g/m³-Zwilling (ökosystem-kompatibel, ohne `device_class`). `humidityVerdict` um eine **absolute Untergrenze** erweitern, damit Winter-Trockenheit physikalisch bewertet wird statt über eine RH-Zahl. Belastbare Schwelle: **≈ 7 g/m³ (≈ 6 g/kg)** gelb, darunter rot — literaturgestützt (Shaman/Kohn 2009, Kudo/Iwasaki 2019) und deckungsgleich mit dem bestehenden Dry-Guard bei Auslegungstemperatur. **Nicht** die im Anlassartikel genannten 9 g/m³ (nicht validiert) und ausdrücklich **nicht** dessen Obergrenze von 12 g/m³ — die widerspricht dem eigenen Schimmelmodell: bei 12 g/m³ Raumluft liegt jede Oberfläche unter ~17,6 °C über der 80-%-Keimgrenze, und DIN 4108-2 legt als Referenz-Innenklima 20 °C/50 % ≈ 8,7 g/m³ zugrunde. Die Obergrenze gehört weiter zu `mold.py`, nicht zu einer festen g/m³-Zahl.

**(2) Lüftungs-Empfehlung als Ampel + optionale Notification** — der eigentliche Differenzierer.
Δ absolute Feuchte innen ↔ außen (Außenwert aus der ohnehin konfigurierten Weather-Entität, optional überschreibbarer Sensor), Schwelle ~3 g/m³ wie im Feld etabliert. Was **nur Poise** ergänzen kann und was im gesamten Wettbewerb fehlt:
- Kopplung an `mold.py`: „lüften, weil die Oberflächen-RH steigt" statt an einer Komfortzahl;
- Kopplung an das gelernte τ und die HDH-/`savings_*`-Maschinerie: **wie lange** lüften und **was kostet es** (kWh/€);
- Kopplung an ADR-0041: der Fenster-Event schließt die Schleife („Ziel erreicht — schließen"), statt eines festen Timers;
- Gegenrichtung, im Feld nirgends abgebildet: bei bereits zu trockener Luft ist Lüften im Winter **kontraproduktiv** — Poise kennt beide Seiten und kann als einziges davon **abraten**.

Das ist ein Hinweis-Feature, kein Regelpfad — aber es braucht einen eigenen ADR, weil ADR-0048 §2 die Grenze zwischen erlaubtem Nudge und verbotener Lüftungssteuerung bisher nur allgemein zieht.

### Nicht empfohlen

- **Aktive Befeuchtung** — ADR-0048 §3 bleibt richtig; `humidifier` ist eine eigene HA-Domäne, HA-Architektur und alle Peers ziehen dieselbe Grenze. Hinweis („zu trocken") ja, Aktuierung nein.
- **KWL-/Abluft-Aktuierung** — technisch trivial (alle Systeme sind `fan`-Entitäten), aber Poise besäße damit eine lufttechnische Anlage im Sinne von VDI 6022, ohne deren Hygienepflichten abbilden zu können. ADR-0048 §1 bleibt richtig.
- **CO₂-getriebene Steuerung** — unverändert monitor-only; der Handlungshinweis aus (2) deckt den Nutzerwunsch ab, ohne den Regelanspruch.

### Offene Frage für die Entscheidung

Ob die absolute Feuchte **selbst gerechnet** oder aus einem vorhandenen Thermal-Comfort-Sensor **konsumiert** wird. Poise rechnet sie ohnehin schon (`humidity_ratio`), aber Thermal Comfort ist im Ökosystem so verbreitet, dass ein optionaler Passthrough (analog zum CO₂-Sensor in ADR-0049) Doppelmessung vermeidet.

---

## Quellen

**Literatur zur Wirkung:** [Shaman & Kohn, PNAS 2009](https://www.pnas.org/doi/10.1073/pnas.0806852106) (absolute Feuchte erklärt Influenza-Saisonalität besser als relative) · [Kudo/Iwasaki, PNAS 2019](https://pubmed.ncbi.nlm.nih.gov/31085641/) (trockene Luft → gestörte mukoziliäre Clearance, Tiermodell) · [PLOS One 2022, Systematic Review HVAC-Feuchte](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0275654) (heterogene Evidenz, keine Zahlenempfehlung) · [Deutsches Ärzteblatt zur Saisonalität](https://www.aerzteblatt.de/archiv/215317/Respiratorische-Virusinfektionen-Mechanismen-der-saisonalen-Ausbreitung).
**Anlassartikel:** [cardiopraxis.de](https://www.cardiopraxis.de/corona-praevention-raumluftqualitaet/) — Praxis-Content ohne Quellenangabe; Mechanismus tragfähig, die Zahlen 9/12 g/m³ sind nicht belegt (Obergrenze bauphysikalisch riskant).
**Wettbewerb & Nutzerwünsche:** verlinkt in §2/§3.
