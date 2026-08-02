# Recherche: clo/met-Schätzung — Kritik am Schiavon-&-Lee-Modell, Verbesserungen, Alternativen

**Datum:** 2026-08-02 · **Typ:** Recherche-Notiz (kein ADR, keine Entscheidung) · **Anlass:** Vertiefung zu [2026-07-Behaglichkeitsmodus.md](2026-07-Behaglichkeitsmodus.md) §9.2 N2 (clo/met-Konfiguration): Taugt das dynamische Bekleidungsmodell (Schiavon & Lee 2013, ASHRAE 55 „Methode 4", `clo_tout`) als Ersatz für Poises Saisonpauschale — und was gibt es an Kritik, besseren Modellen und neuen Methoden? · **Bezug:** ADR-0054 (PMV/PPD), ADR-0022 (dependency-frei), `comfort/pmv.py` (CLO_WINTER 1,0 / CLO_SUMMER 0,5 bei T_rm-Schwelle 15 °C; met fix 1,2) · **Methode:** 4 parallele Web-Recherche-Agenten (Kritik/Validierung, Modelle, Sensorik/ML, Normen/Praxis) + Vollständigkeits-Kritiker mit eigener Primärquellen-Auswertung.

---

## 0. Kernbefund in sieben Sätzen

1. Das Schiavon-&-Lee-Modell ist **empirisch schwach** (R²adj 0,19; selbst mit allen 20 erhobenen Variablen max. 0,28) und stammt ausschließlich aus **Büro-Daten von 1986–1997** — es gibt keine einzige Residential-Validierung, und ASHRAE 55 erlaubt die Methode nur „in mechanically conditioned buildings".
2. Der Winterast **clo = 1,0 unter −5 °C ist von den Autoren ausdrücklich „arbitrarily" gesetzt** (energetisch begründet); die eigene Regression liefert dort nur 0,74 clo, und nur 4,5 % der Daten liegen unter −5 °C.
3. Trotzdem ist es gegenüber Poises Zweipunkt-Pauschale eine klare Verbesserung — **der Hauptgewinn liegt in der Übergangszeit (5–15 °C)**, wo Poise heute bis zu 0,45 clo (≈ 3 K Sollwert-Äquivalent) zu hoch liegt und an der 15-°C-Schwelle einen ~3-K-Sprung erzeugt.
4. **Der 6-Uhr-Eingang ist verzichtbar**: Die Autoren wählten ihn unter drei kollinearen Statistiken (min/max/Tagesmittel, Spearman-r 0,88–0,97) ausdrücklich „arbitrarily" — Poises vorhandenes Außen-Laufmittel kann direkt als Eingang dienen; neuere Modelle (Liu 2018, Zhao 2022) nutzen ohnehin Laufmittel.
5. Die **met-Unsicherheit ist zuhause der größere Fehler als jede clo-Modellwahl** (0,7 met Schlafen bis 2,7 met Hausarbeit gegen fix 1,2) — und PMV ist für Schlafräume formal gar nicht anwendbar (0,7 met liegt unter der ISO-7730-Grenze 0,8; Bettsysteme messen 0,9–4,9 clo).
6. Der wissenschaftlich tragfähigste Ausweg ist nicht ein präziseres clo-Modell, sondern **clo/met als latente Größen zu behandeln**: Prior + gelernter Haushalts-Offset (statistisch gerechtfertigt durch den 13–17-%-Gebäude-Random-Effect des Originalpapers) bzw. Personal-Comfort-Feedback-Lernen — genau der Weg, den Ambi Climate produktisiert hatte und den kein Consumer-Thermostat über clo löst.
7. Alle publizierten Modelle schauen rückwärts — **antizipatives Anziehen nach Wettervorhersage** (gewarnte Hitze-/Frosttage) bildet keines ab; die Poise-originäre Erweiterung dafür ist die richtungssymmetrische Eingangs-Mischung `T_eff = (1−w)·T_rm + w·T_forecast` (§9), shadow-first zu validieren.

---

## 1. Was das Modell empirisch wirklich leistet

- **Datenbasis:** 6.333 von 23.475 Beobachtungen (nur Qualitätsklasse I) aus ASHRAE RP-884 + RP-921, erhoben **1986–1997**, ausschließlich Büro/Arbeitsplatz: Kalifornien (2.950), Australien (2.429), Montreal (869), Michigan (85); 88,2 % mechanisch klimatisiert. Median 0,59 clo (Sommer 0,50 / Winter 0,69).
- **Erklärte Varianz:** Modell 1 (nur t_out,6h): **R²adj = 0,19**; Modell 2 (+ Innen-Operativtemperatur): 0,22; Obergrenze mit allen 20 Variablen: 0,28. Reststreuung SD ≈ 0,22 clo ≈ **1,3 K** operative Temperatur (Faustregel ~6–7 K/clo aus dem Paper selbst).
- **Der Gebäude-Random-Effect erklärt 13–17 % der Gesamtvarianz** — fast so viel wie der gesamte Klimaeffekt. Das ist die statistische Rechtfertigung für einen lernbaren Per-Haushalt-Offset statt eines starren Weltmodells.
- **Willkürliche Äste:** clo = 1,00 unter −5 °C ist laut Paper „arbitrarily" gesetzt („supporting … 1 clo would have energy benefits"); die Regression selbst liefert bei −5 °C nur 0,74. Auch 0,46 ab 26 °C ist gekappt. Nur 15,5 % der Daten < 5 °C, 4,5 % < −5 °C — mitteleuropäische Winter liegen im datenarmen, künstlich gesetzten Bereich. Kanadische Winterdaten im Paper (Median 0,8 clo bei −7,5 °C) stützen, dass 1,0 clo selbst im Kalten eher hoch ist.
- **6-Uhr-Wert ohne Sonderstellung (Primärquellen-Fund):** min/max/Tagesmittel der Außentemperatur sind hochkollinear (Spearman 0,88–0,97, VIF > 100); Zitat: „It is not important which one is kept. We **arbitrarily** preserved the minimum air temperature (6:00 o'clock)…" → **Poises Außen-Laufmittel ist als Eingang direkt verwendbar, ein 6-Uhr-Sensorpfad ist unnötig.**

## 2. Kritik und Validierung durch Dritte

| Studie | Befund |
| --- | --- |
| Rupp, Kazanci & Toftum 2021 (Global DB I+II) | Stuhlisolation (0,10–0,30 clo) in DB II unsauber getrennt — Bias größer als die meisten Modellunterschiede; eigenes Modell ebenfalls nur R² 0,22 |
| de la Hoz-Torres et al. 2023 (NV-Hochschulen ES/PT) | ASHRAE-Modell trifft nur **32 % der Fälle innerhalb ±0,1 clo** (ANN: 50 %); Geschlechtsunterschied 0,60 vs. 0,72 clo |
| Pittana et al. (Schule IT) | 6-Uhr-Außentemperatur **nicht signifikant** (p = 0,52, R² 0,00); **Innen-Laufmittel R² 0,46–0,74** |
| Liu et al. 2018 (IC-RM) | Logistik über **Außen-Laufmittel** statt 6-Uhr-Wert, R² > 0,9 (gebinnt); Sättigung an beiden Enden |
| Zhao et al. 2022 (ländl. China, Wohnen) | **1,81 clo Winter / 0,42 Sommer** — weit über dem 1,0-Deckel; Prädiktoren t_op + 7-Tage-Laufmittel |
| Umishio et al. 2020 (2.190 jap. Haushalte) | +0,1 clo ↔ −0,3 K Wohnzimmertemperatur — **zuhause substituiert Kleidung die Heizung**; ein reines Außenmodell bildet diese Rückkopplung nicht ab |
| Cheung et al. 2019 (Kontext) | PMV trifft die Empfindung nur zu ~34 % — clo-Präzision unter ±0,1 geht im Modell-Grundfehler unter |

**Prädiktor-Widerspruch aufgelöst (Kritiker-Synthese):** Außen stark (Schiavon/Lee, De Carli) vs. innen stark (Pittana) vs. innen n.s. (Morgan & de Dear) erklärt sich über die Innentemperatur-*Varianz* der jeweiligen Gebäude. Für Poise ist die Innentemperatur zudem **endogene Stellgröße**: ein Innen-Prädiktor schließt eine positive Rückkopplung (Poise hebt t_op → Modell senkt clo → PMV sinkt → Poise hebt weiter) und interpretiert die japanische Kleidungs-statt-Heizung-Substitution falsch herum. **Regelungstechnisch sauber ist nur: Außen-Laufmittel als Basis + lernbarer Haushalts-Offset;** ein Innen-Term höchstens als träges Innen-Laufmittel mit Anti-Feedback-Guard.

**Normenstatus:** In ASHRAE 55 seit Addendum k (2013, „Methode 4"); der Normtext warnt selbst („may not be appropriate for all cultures and occupancy types") und erlaubt Anpassung für Dresscodes. **EN 16798-1 und ISO 7730 kennen kein dynamisches clo-Modell** — für das EN-basierte Poise wäre die Übernahme eine Erweiterung über die Norm hinaus. ISO 7730:2025 (4. Ausgabe, Juni 2025) behält Fanger unverändert; clo/met bleiben Verweise auf ISO 9920/8996.

## 3. Konkretes Delta zu Poise heute (BEHAVIOR FIX, kein Refactoring)

Vergleich Zweipunkt-Pauschale (`seasonal_clo`, Schwelle T_rm 15 °C) gegen die ASHRAE-Stückfunktion, Sollwert-Äquivalent mit ~6,8 K/clo:

| t_out (Laufmittel) | Poise heute | clo_tout | Δclo | ≈ ΔSollwert |
| --- | --- | --- | --- | --- |
| −5 °C | 1,00 | 1,00 | 0,00 | 0 K |
| 0 °C | 1,00 | 0,82 | 0,18 | ≈ 1,2 K |
| 10 °C | 1,00 | 0,59 | 0,41 | ≈ 2,8 K |
| 14,9 °C | 1,00 | 0,55 | 0,45 | ≈ 3,1 K |
| 15,1 °C | 0,50 | 0,55 | −0,05 | ≈ −0,3 K |
| 20 °C | 0,50 | 0,51 | −0,01 | ≈ 0 K |

Der Gewinn liegt **nicht im tiefen Winter** (identisch 1,0), sondern in der Übergangszeit; die 15-°C-Diskontinuität verschwindet. Achtung Vorzeichen: weniger clo heißt bei PMV-Führung **höherer** Sollwert — der Umstieg macht die Wohnung in der Übergangszeit rechnerisch *wärmer*. Das ist ein auszuweisender **BEHAVIOR FIX** (heute nur Diagnose-Shadow; verhaltensrelevant, sobald ADR-0054 Stufe 2 live geht) und ggf. gedämpft einzuführen.

## 4. Verbesserte Modelle (Auswahl mit Poise-Bewertung)

- **Schiavon/Lee Modell 2** (`log10 clo = 0,2134 − 0,0165·t_op − 0,0063·t_out,6`): nur +3 pp Varianz, Rückkopplungsrisiko (s.o.) — **nur mit Innen-Laufmittel** zulässig; Gewinn klein.
- **Logistik über Laufmittel** (Liu 2018 IC-RM; Zhao 2022; Form `clo = d + (a−d)/(1+exp((T−c)/b))`): konzeptionell besser (Sättigung, Laufmittel-Eingang, im Wohnen belegt), aber Koeffizienten aus China/Schulen — für Mitteleuropa nicht kalibriert.
- **Verhaltensmodell** (Haldi & Robinson 2011, ordinales Logit): wichtigste Lehre — Kleidungswechsel *innerhalb* des Tages sind selten → **ein clo-Update pro Tag genügt**, mehr ist Scheingenauigkeit.
- **met-Kopplung:** ASHRAE-Korrektur `Icl,dyn = Icl·(0,6+0,4/met)` greift erst ab met > 1,2 — **bei Poises fixem met 1,2 exakt wirkungslos**. ISO 9920 korrigiert feiner über Luft-/Gehgeschwindigkeit.
- **Sitz-/Sofa-Zuschlag** (ASHRAE 55-2023 Tab. 5-4 / ISO 9920): Bürostuhl +0,10, Chefsessel +0,15, **Sofa +0,21 clo** — im Schiavon-Lee-Modell ausdrücklich *nicht* enthalten; fürs Wohnzimmer der billigste reale Zuschlag.
- **Schlafen:** met 0,7 liegt **unter der Gültigkeitsgrenze von ISO 7730 (0,8) und ASHRAE 55 (1,0)**; Bettsysteme messen 0,9–4,9 clo, dominiert vom Bedeckungsgrad (+1 clo Bett ≈ −4,2…−6 K Neutraltemperatur). ASHRAE erklärt Schlafsituationen für mit Standardmethoden nicht bestimmbar. → **Schlafzimmer gehören aus dem PMV-Pfad heraus** (festes Nacht-Band bzw. Peeters-Algorithmus, §6).

## 5. Sensor- und ML-Alternativen

- **Kamera/IR-Vision** (Choi 2022/2023, Liu 2022, Wei 2024): 86–95 % Klassifikationsgenauigkeit — aber ausschließlich Büro-Settings (frontal sitzend, feste Distanz), Nutzenhebel klein (±0,1 clo ≈ ±0,6 K gegen ±0,15 clo Restfehler) und **RGB-Kameras im Wohnraum für ein HA-Publikum disqualifiziert**. Low-Res-IR-Arrays (Grid-EYE, MLX90640) sind privacy-tauglich, aber nur für Präsenz, nicht für clo. → nicht empfohlen.
- **Wearables:** met aus Herzrate (ISO 8996) nur mit Individual-Kalibrierung 10–15 % Fehler, im flachen Wohnbereich 0,8–1,6 met kaum trennscharf; Consumer-Uhren liefern Hauttemperatur nur relativ/nachts. Lokal machbar (Gadgetbridge → Health Connect → HA), aber nur als **optionales** Zusatz-Feature — nie Pflichtsensorik.
- **Personal Comfort Models — der tragfähige Ausweg:** Individuum direkt lernen statt Population schätzen: 73 % vs. 51 % Trefferquote (Kim et al. 2018); F1 0,78 mit ~250–300 Feedback-Punkten pro Person (Tartarini 2022); Active Learning senkt den Labelaufwand um 31 % (Tekler 2023); Bayes-Präferenzlernen mit Unimodalitäts-Constraint braucht drastisch weniger Abfragen (GPPrefElicit). **Feldvalidiert ohne Umfragen:** Multi-Armed-Bandit lernt Präferenz allein aus Sollwert-Overrides via „Nudging" (Elehwany 2026). **ComfortGPT** (ecobee-Daten, >100.000 Haushalte) sagt bevorzugte Sollwerte mit MAE 0,65 K voraus — ganz ohne clo/met. Kommerzielle Bestätigung: kein Consumer-Thermostat schätzt clo/met; Ambi Climate, Nest, ecobee lernen alle latent aus Interaktionen.

## 6. Übersehene dritte Werkklasse: residentielle adaptive Komfortmodelle

Neben „clo besser schätzen" und „Individuum lernen" existiert die etablierte Option, **clo/met ganz zu umgehen**:

- **Peeters et al. 2009** (Applied Energy 86:772–780): Komforttemperatur-Algorithmen speziell für Wohngebäude, **getrennt nach Schlafzimmer / Bad / übrige Räume**, als Funktion einer Laufmittel-Außenreferenz — explizit für Regelung/Simulation gedacht.
- **Rijal, Humphreys & Nicol 2019** (36.114 Votes, 120 japanische Wohnungen): größtes residentielles Adaptiv-Datenset (Wohn- und Schlafzimmer).

Da EN-16798-Adaptiv aus *Büro*-Feldstudien stammt und PMV im Schlafraum formal ungültig ist, sind diese Modelle der naheliegende **Fallback-/Plausibilisierungs-Pfad** — mindestens als Sanity-Bound um den PMV-Offset.

## 7. Normen- und Werkzeug-Stand (Benchmark)

- **pythermalcomfort 4.4.0** (07/2026): `clo_tout`, `clo_dynamic_ashrae/_iso`, met-Tabellen (Sleeping 0,7 / Seated 1,0 / Cooking 1,8 / House cleaning 2,7); `pmv_ppd_iso` unterstützt bereits `model="7730-2025"`. Bleibt für Poise **Testvektor-Quelle**, keine Laufzeit-Dependency (ADR-0022).
- **EnergyPlus** hat `DynamicClothingModelASHRAE55` im People-Objekt — dynamisches clo ist **Simulationsstandard, aber nirgends Regelungsstandard**: weder BMS-Produkte noch HA-Integrationen (Indoor Thermal Comfort Tool: statische clo/met-Entities) noch Consumer-Thermostate regeln mit clo-Vorhersage. Poise wäre hier first mover — mit entsprechender Beweislast.

## 8. Konsequenz für Poise (Empfehlungsskizze, keine Entscheidung)

1. **clo_tout als Prior übernehmen, aber mit Außen-Laufmittel als Eingang** (per Primärquelle unkritisch) — pure Nachimplementierung in `comfort/pmv.py`, ~4 Zeilen, Testvektoren aus pythermalcomfort. Bounds 0,4–1,2 clo, **ein Update pro Tag**, Änderung als BEHAVIOR FIX ausweisen (§3-Tabelle). Zur Extremtag-/Antizipations-Erweiterung des Eingangs s. §9.
2. **met als Raumtyp-/Zustands-Profil statt fix 1,2** (Schlafen 0,7–0,8 / Wohnen 1,0–1,2 / Küche 1,8): zuhause die größere Fehlerquelle als jede clo-Modellwahl; erst damit wird `clo_dynamic` überhaupt wirksam. Wohnzimmer-Sofa-Zuschlag +0,15…0,21 clo als Raumprofil-Detail.
3. **Schlafzimmer aus dem PMV-Pfad nehmen** (Norm-Gültigkeit!): Nacht-Band bzw. Peeters-Schlafzimmer-Algorithmus; PMV-Lampe dort als „nicht validiert" flaggen.
4. **Haushalts-Offset lernbar machen** (±0,3 clo, Zeitkonstante Tage) — statistisch durch den Gebäude-Random-Effect gerechtfertigt; Auslieferung über den ADR-0060-Vorschlags-Mechanismus („nie still"), Feedback-Kanal wäre der Stufe-C-Baustein aus der Behaglichkeitsmodus-Recherche.
5. **Ehrlichkeit beibehalten:** Auch clo_tout erklärt nur ~19 % der Varianz; ±0,2 clo ≈ ±1,2 K bleiben als Unsicherheit bestehen und gehören als Bandbreite geführt, nicht als Scheinpräzision. **Offene Datenlücke:** Es existiert kein publizierter clo-Messwert aus beheizten mitteleuropäischen Wohnungen — plausibel sind 0,7–1,0 clo Winter mit großer Haushaltsvarianz.

---

## 9. Extremtage & Forecast-Antizipation (Poise-originäre Erweiterung)

**Szenario:** 15 °C nachts / 25 °C tags, dazwischen 2–4-tägige Ausreißer-Episoden mit 35–40 °C tags bei nur ~17 °C morgens — die Bewohner sind per Wetterwarnung vorbereitet und ziehen sich *vorausschauend* dünn an. Spiegelbildlich der Kälteeinbruch: T_rm noch mild, aber am ersten angekündigten Frosttag trägt der Mensch sofort den Pullover.

### 9.1 Warum das Basisdesign (§8.1) im Sommerfall schon robust ist

- **Kurven-Sättigung:** Bei Normaltagen-Laufmittel ≈ 20 °C steht clo_tout bei 0,51; selbst volle Einpreisung des Hitzetags erreicht nur den Boden 0,46 — **max. 0,05 clo ≈ 0,3 K** Sollwert-Äquivalent. Das Laufmittel driftet während der Episode von 0,51 auf ~0,48 und zerfällt danach von selbst (α = 0,8: T_rm 20 → ~23,4 °C nach drei Hitzetagen, dann Rückfall).
- **Intraday-Hub erreicht clo nicht:** Ein Update pro Tag + Tagesstatistik-Eingang heißt: der Sprung 17 → 40 °C innerhalb des Tages berührt clo gar nicht (Haldi-&-Robinson-Kadenz, §4).
- **Arbeitsteilung:** Den Extremtag selbst beantwortet nicht clo, sondern die live laufende Maschinerie — ADR-0051 (Hitzetag-Kühlkanten-Raise Richtung outdoor − 7 K, ASR-26-Cap, 0,5 K/Tick), Taupunkt-Cap, ggf. Fan-Credit (WHO-Guard < 40 °C). Beim Kälteeinbruch: EN-Heizband + Frost-/Schimmel-Floors. Jeder clo-Restfehler ist durch den ±1-K-Offset-Deckel + Band-Klemme (ADR-0054 Stufe 2 / ADR-0035) hart begrenzt — Defense in depth.

### 9.2 Die echte Lücke: antizipatives Anziehen

Menschen kleiden sich nach der **Vorhersage**, alle publizierten Modelle schauen rückwärts (6-Uhr-Wert bzw. Laufmittel). Morgan & de Dear identifizierten Vortagserfahrung *und Wettervorhersage* als Kleidungstreiber — **kein Modell nutzt die Vorhersage als Eingang**. Der Effekt ist im Sommer klein (Sättigung, s. o.), sitzt aber in der **Übergangszeit auf dem steilen Kurventeil**: Laufmittel 5 °C → 0,64 clo, angekündigter 20-°C-Föhntag → real ~0,50 → Fehler ~0,9–1 K, an der Deckelgrenze. Beim Kälteeinbruch (T_rm 8 °C → Modell 0,61; real Pullover ~0,9) heizt das System ~1 K wärmer als nötig.

### 9.3 Richtungssymmetrische Formulierung (Eingänge mischen, nicht Ausgänge)

⚠️ **Anti-Pattern `clo = min(clo_tout(T_rm), clo_tout(T_forecast))`:** funktioniert nur in der Hitze-Richtung — im Winter wirft `min()` die Kälteeinbruch-Information exakt weg (bleibt beim milden Laufmittel-Wert). Richtig ist die Mischung der *Eingänge*:

```
T_eff = (1 − w) · T_rm + w · T_forecast_heute        (w ≈ ⅓…½, Start konservativ ⅓)
clo   = clo_tout(clamp(T_eff, −27,2 … 26 °C))
```

Ein Term, beide Richtungen, kein Gate, keine Sprungstelle (kontinuierlich/geklemmt/ratenlimitiert — der Poise-Stil aus den ADRs). Durchgerechnet (w = 0,4):

| Fall | T_rm | Forecast (Tagesmittel) | T_eff | clo | statt (nur T_rm) | Wirkung |
| --- | --- | --- | --- | --- | --- | --- |
| Hitze-Episode | 20 °C | 28 °C | 23,2 °C | 0,48 | 0,51 | Kühlziel ~0,2 K höher |
| Kälteeinbruch | 8 °C | −8 °C | 1,6 °C | 0,76 | 0,61 | Heizziel ~1 K tiefer |

**Beide Richtungen sind energie-positiv:** Sommer dünner angezogen → Neutraltemperatur höher → weniger kühlen; Winter Pullover → Neutraltemperatur tiefer → weniger heizen (die Umishio-Substitution „Kleidung statt Heizung", richtig herum genutzt). Komfort-Restrisiko (jemand hat sich *nicht* wärmer angezogen): doppelt begrenzt durch ±1-K-Deckel und die nie unterschrittene EN-Bandunterkante (Kat. II 20 °C).

### 9.4 Umsetzungsdetails

1. **Tagesmittel als Forecast-Größe, nicht Tmax** — die min/max/Mittel-Austauschbarkeit des Originalpapers gilt für *beobachtete* Tagesstatistiken; Tmax würde den Hitzefall doppelt verschieben. Quelle: vorhandener `forecast_provider` (wie Optimal Start), Update einmal morgens.
2. **Degradationsleiter:** kein Forecast → w = 0 → exakt das Basismodell (Muster „measured → derived → estimated → default").
3. **w ist Feldkalibrier-Parameter, kein Naturgesetz.** Die Forecast-Erweiterung ist Poise-originär (keine publizierte Validierung) → **Shadow-first (ADR-0026)**: `clo_shadow` mit/ohne Antizipationsterm parallel loggen, gegen die L1-Override-Statistik bzw. Komfort-Feedback vergleichen, erst dann in den Stufe-2-Offset.
4. **Lern-Maskierung:** Der gelernte Haushalts-Offset (§8.4, Zeitkonstante Tage) darf aus einer 2–4-Tage-Episode nichts lernen — Feedback/Overrides an Extremtagen fließen in die Kühl-/Heizreaktion, nicht in den clo-Offset (ADR-0055-Maskierungsmuster analog).

---

## 10. Quellen (Auswahl)

**Original & Norm:** Schiavon & Lee 2013 (doi:10.1016/j.buildenv.2012.08.024; Volltext escholarship.org/uc/item/3338m9qf) · Lee & Schiavon 2014 (doi:10.3390/en7041917) · ASHRAE 55-2010 Addendum k (2013) / 55-2023 §5.2.2.2, Tab. 5-1/5-4, App. B · ISO 7730:2025 · ISO 9920 · ISO 8996:2021 · EN 16798-1 Annex B.

**Kritik/Validierung:** Rupp/Kazanci/Toftum 2021 (doi:10.1016/j.enbuild.2021.111431) · de la Hoz-Torres 2023 (doi:10.3390/buildings13041002) · Pittana et al. (unibz BSA) · Liu 2018 (doi:10.1016/j.buildenv.2018.03.015) · Zhao 2022 (doi:10.1016/j.buildenv.2022.109014) · Umishio 2020 (doi:10.1111/ina.12708) · Tang 2020 / Jiao 2017 (Ältere) · Indraganti (Sari) · Cheung 2019 (doi:10.1016/j.buildenv.2019.01.055).

**Modelle/Schlaf:** De Carli 2007 (doi:10.1016/j.buildenv.2006.06.038) · Morgan & de Dear 2003 · Haldi & Robinson 2011 (doi:10.1007/s00484-010-0383-4) · Aparicio-Ruiz 2024 (doi:10.1007/s12273-024-1114-9) · Ngarambe 2019 · Lin & Deng 2008 (Bettsysteme) · Pan/Lin/Deng 2010 (doi:10.1016/j.buildenv.2010.02.018) · Su 2022 (China-DB).

**Sensorik/ML:** Choi 2022/2023 (doi:10.1016/j.buildenv.2022.109345, …2023.110255) · Wei 2024 (doi:10.1016/j.buildenv.2024.111277) · Lee 2016 IR (doi:10.3390/s16030341) · Liu/Foged/Moeslund 2022 (doi:10.3390/s22020619) · ISO-8996-HR-Validierungen (2019/2025) · Kim/Zhou/Schiavon 2018 (doi:10.1016/j.buildenv.2017.12.011) · Tartarini 2022 (doi:10.1111/ina.13160) · Tekler 2023 (arXiv:2309.09073) · Awalgaonkar 2019 (arXiv:1903.09094, GPPrefElicit) · Zhang 2024 (Bayes-Meta) · Park & Nagy 2020 (HVACLearn) · Elehwany 2026 (doi:10.1016/j.enbuild.2026.117030) · Chen & Ghahramani 2024 ComfortGPT (doi:10.1016/j.buildenv.2023.111085) · WiFi-CSI-Review 2025 (doi:10.1007/s12273-025-1249-3).

**Residentiell-adaptiv:** Peeters et al. 2009 (doi:10.1016/j.apenergy.2008.07.011) · Rijal/Humphreys/Nicol 2019 (doi:10.1016/j.enbuild.2019.109371) · Matsuo 2026 (doi:10.1002/2475-8876.70071).

**Werkzeuge:** pythermalcomfort 4.4.0 (pythermalcomfort.readthedocs.io; doi:10.1016/j.softx.2020.100578) · CBE Comfort Tool (comfort.cbe.berkeley.edu) · EnergyPlus People/`DynamicClothingModelASHRAE55` · HA Indoor Thermal Comfort Tool (github.com/1iverea9er/Indoor-Thermal-Comfort).
