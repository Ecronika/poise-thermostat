# Raumtyp-Parameterprofile — Empfehlungssätze für übliche Wohnräume (2026-08-09)

**Zweck:** Wie das Badezimmer-Set (Recherche 2026-08, umgesetzt am Bad) je Raumtyp ein begründetes Abweichungs-Set von den Poise-Defaults. Grundlage: EN 16798-1 Anhang B (Kategoriebänder, wie im Code: Heizen I 21–23 / II 20–24 / III 19–25; Kühlen I 23,5–25,5 / II 23–26 / III 22–27), UBA-/Energieberatungs-Praxiswerte, ISO 7730/8996 (met/clo → `ROOM_PROFILES`), plus die Poise-Mechanik selbst (Klemmen, Fenster-Semantik). Defaults aus `const.py`/`runtime/config.py` v0.187.0.

## Mechanik-Regeln, die die Empfehlungen formen (Code-verifiziert)

1. **EN-Klemme im belegten Fenster:** Innerhalb eines Komfortfensters klemmt `HEATING_LOWER[category]` die Heizkante — eine Basis unter der Kategorie-Untergrenze (I 21 / II 20 / III 19) ist dort **nicht erreichbar**. Wer ein 18-°C-Schlafzimmer will, bekommt mit Cat III real 19,0; tiefer geht nur außerhalb des Fensters (Setback, gehalten von Frost-/Schimmel-Floors).
2. **Kein Fenster = ganztägig Komfort.** Für Dauer-Niedrig-Räume (Gästezimmer, Flur) ist das gewollt: niedrige Basis ganztags statt Fenster+Setback.
3. **ROOM_ECO wirkt nur im Fenster** (ADR-0058 N2): Raum ≥ `absence_after_min` leer → flache `eco_delta`-Absenkung (2 K), Decke `cool_hard_cap`; Rückkehr stellt sofort wieder her. Ohne Fenster (Gästezimmer) ist ROOM_ECO dadurch **ganztags** aktiv — der Raum regelt sich über den Belegungssensor selbst.
4. **PIR-Falle bei reglosen Personen:** Ein PIR verliert Schläfer und Filmgucker → ROOM_ECO senkt mitten in der Nutzung ab. In Schlaf-/Wohnzimmer Occupancy nur mit mmWave/Wasp-in-Box konfigurieren — **oder gar keinen Sensor** (fail-safe = anwesend). Fürs Kinderzimmer gilt dasselbe verschärft.
5. **Mehrfenster (ADR-0070, v0.187):** Zweiteilige Nutzung (Esszimmer, Küche, Bad) bekommt zwei Fenster statt eines langen; Optimal-Start heizt auf jeden Fensterstart vor. Übernacht-Fenster (Schlafzimmer 21–07) sind als Wrap unterstützt.
6. **`actuator_dynamics` bleibt überall `auto`** (Automatik klassifiziert korrekt, Bad-Befund 2026-08-09); `optimal_start` bleibt an (ohne Fenster wirkungslos, schadet nicht).

## Empfehlungstabelle

Spalten = Poise-Optionen; erste Zeile = Auslieferungs-Default. „an\*" = nur sinnvoll, wenn die Zone einen Lüfter/eine AC hat (Tier-3-Wirkung); der Tier-2-PMV-Offset wirkt auch ohne. Komfortfenster sind Startpunkte — an den Haushalt anpassen.

| Raum | Komfort-Basis (°C) | Komfort-Gewicht | EN-Kategorie | Komfortfenster | Absenkung (K) | Adaptive Kühlkante | Raumprofil | Aktive Behaglichkeit | Lüftungs-Rat | Abwesenheit (min) |
|---|---|---|---|---|---|---|---|---|---|---|
| **(Default)** | 21,0 | 70 % | II | — (ganztags) | 3,0 | auto | office | aus | aus | 30 |
| **Wohnzimmer** | 21,5 | 85 % | II | 15:00–23:00 | 3,0 | auto | living | an\* | aus | 45 |
| **Esszimmer** | 21,0 | 70 % | II | 07:00–09:00 + 18:00–21:00 | 3,5 | auto | office | aus | aus | 30 |
| **Küche** | 19,0 | 50 % | III | 06:30–09:00 + 17:00–21:00 | 3,0 | auto | kitchen | aus | **an** | 30 |
| **Schlafzimmer** | 19,0 | 40 % | III | 21:00–07:00 (übernacht) | 3,0 | auto (mit AC: off + Cat II) | bedroom | an\* | **an** | — (kein PIR!) |
| **Kinderzimmer (Kleinkind)** | 21,0 | 90 % | I | 07:00–21:00 | 2,5 | auto | living | aus | **an** | — (kein PIR!) |
| **Kinderzimmer (Schulkind)** | 21,0 | 80 % | II | 06:30–21:30 | 3,0 | auto | living | aus | **an** | — (kein PIR!) |
| **Gästezimmer** | 20,0 | 40 % | III | — (ganztags, Eco regelt) | — (wirkungslos) | auto | bedroom | aus | aus | 60 |
| **Arbeitszimmer / Homeoffice** | 21,0 | 70 % | II | 08:00–17:30 | 4,0 | auto | office | an\* | aus | 30 |
| **Flur / Diele** | 19,0 | 20 % | III | — (ganztags) | — | auto | office | aus | aus | 30 |
| **Badezimmer** *(Referenz, umgesetzt)* | 24,0 | 100 % | II | 05:00–22:00 *(Alternative: 05:30–09 + 17–22)* | 4,0 | **off** | bathroom | **an** | **an** | 30 |

## Begründungen je Raum (Kurzform)

- **Wohnzimmer:** 21,5 trifft die Behaglichkeitsmitte des Cat-II-Bands (20–24); `living`-Profil rechnet den Sofa-clo-Zuschlag (+0,21) ein, damit PMV nicht fälschlich „zu kühl" meldet. 45-min-Abwesenheit puffert reglose Fernsehabende bei PIR; besser mmWave. Abendfenster — Haushalte mit Vormittagsnutzung: 07:00–23:00.
- **Esszimmer:** Paradefall für zwei Fenster (Frühstück + Abendessen); dazwischen Setback. Kein eigenes Ess-Profil — `office` (met 1,2, kein Decken-clo) ist die ehrlichste Näherung.
- **Küche:** Geräte- und Kochwärme heizen mit → Basis 19 an der Cat-III-Untergrenze, mehr wäre Ko-Heizen gegen den Herd. `kitchen`-Profil (met 1,8) bewertet stehende Arbeit korrekt. **Lüftungs-Rat an** — Kochfeuchte ist neben der Dusche der zweite Feuchteherd der Wohnung.
- **Schlafzimmer:** Die UBA-17-°C-Praxis ist im belegten Fenster durch die EN-Klemme nicht abbildbar — Cat III liefert real 19,0 als Nachtkante (Basis 19, niedriges Gewicht weitet zusätzlich). Übernacht-Fenster 21–07 (Wrap); tagsüber Setback → ~16 (Floors halten). **Keinen PIR als Occupancy** — er verliert Schläfer und würde nachts absenken; ohne Sensor gilt fail-safe „anwesend". Lüftungs-Rat an (RH-Anstieg über Nacht, Morgenlüft-Hinweis). Mit Schlafzimmer-AC: adaptive Kante aus + Cat II, damit die Kühlkante nachts nicht über 26 wandert.
- **Kinderzimmer:** EN 16798-1 nennt Cat I ausdrücklich für sehr junge/empfindliche Personen → Kleinkind Cat I (Untergrenze 21, enges Band, Gewicht 90); ab Schulalter genügt Cat II. Flache Absenkung 2,5 K: nachts ist der Raum belegt, ~18,5 ist schlafgerecht (Säuglingsempfehlungen liegen eher kühl). `living` als Kompromiss zwischen Bodenspiel (hoch met) und Schlaf. Kein PIR (schlafendes Kind = Eco-Falle); Lüftungs-Rat an (dichte nächtliche Belegung).
- **Gästezimmer:** Der Selbstregel-Trick aus Mechanik-Regel 3: kein Fenster + Occupancy-Sensor + 60 min → dauerhaft 20 als Basis, bei Leere sinkt ROOM_ECO auf ~18 (Cat-Klemme entfällt, Floors halten), ein Gast hebt sofort wieder. Für Besuch zusätzlich Boost/Comfort-Preset. Setback-Wert ist ohne Fenster wirkungslos.
- **Arbeitszimmer:** Praktisch der Default-Zuschnitt (das `office`-Profil IST die Auslegungsannahme). Fenster = Arbeitszeit, kräftige Absenkung 4 K (abends/nachts nie genutzt). Mit Klimagerät (wie „Büro Technik"): Aktive Behaglichkeit an — Fan-first + Kanten-Gutschrift wirken hier am stärksten. Wochentags-Differenzierung (Wochenende ohne Fenster) gibt es noch nicht — bewusste ADR-0070-Grenze.
- **Flur:** Verkehrsfläche, kein Aufenthaltsraum — niedrigstes Gewicht (weites Band, minimale Eingriffe), Basis 19 = die Systemuntergrenze im belegten Zustand (eine 18er-Basis würde von der Cat-III-Klemme ohnehin auf 19 gehoben — Regel 1). Nur sinnvoll als eigene Zone, wenn der Flur eine eigene Wärmequelle hat.
- **Badezimmer:** Referenz — das beschlossene Set aus der Recherche 2026-08 (Basis 24/Gewicht 100/Cat II/adaptive off/Fenster 05–22/Absenkung 4/bathroom-Profil/Aktive Behaglichkeit + Lüftungs-Rat an). Seit v0.187 ist die Zweifenster-Variante (Morgen + Abend) möglich, wenn die Mittagsabsenkung gewünscht ist — bei Fernwärme-Handtuchheizkörper (slow_hydronic) heizt Optimal-Start beide Starts zuverlässig vor.

## Nicht abgedeckt / bewusste Grenzen

Wochentags-/Wochenendprofile (ADR-0070-Grenze), Ferien-/Urlaubsmodus (heute: Away-Preset bzw. Haus-Gate), Hobbyraum/Keller (Schimmel-Floor dominiert dort — eigene Betrachtung bei Bedarf), Werte unterhalb der EN-Untergrenzen im belegten Fenster (by design nicht möglich).
