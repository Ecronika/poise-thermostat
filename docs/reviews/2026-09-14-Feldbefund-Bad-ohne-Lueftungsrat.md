# Feldbefund 2026-09-14: das Bad bekommt keinen Lüftungsrat — Präsenzquelle unter der Belegungsschwelle; dazu ein Bezugsgrößen-Fehler in `mold_guard`

**Anlass:** Frage des Betreibers, warum das Badezimmer keine Lüftungsempfehlung erhält; auf Nachfrage: „wir haben das Bad heute morgen schon mehrfach benutzt, ich war eben gerade Duschen" · **Quelle:** laufende Instanz, **v0.194.3**, Entitätsattribute + Config-Entry-Diagnose + Recorder-Historie · **Stand:** Fassung 2, nach externem Review — dessen Größen-Korrektur ist übernommen und hat einen **Fehler in der Regel selbst** aufgedeckt · Alle Zeiten lokal (CEST)

## 1. Messwerte (07:41) — korrigierte Gegenüberstellung

| Größe | Wert |
|---|---|
| Luft / rF | 22,4 °C / **69,5 %** |
| absolute Feuchte innen / außen | **13,8** / 8,6 g/m³ → **Δ 5,1** (Eintritt 3,0) |
| `rh_max_safe` (schimmelsichere **Raumluft**-Obergrenze) | **63,3 %** |
| `abs_max_safe` | **12,5 g/m³** |
| Oberflächen-RH momentan | 87,9 % (rückgerechnet: t_out ≈ 9,7 °C, t_si ≈ 18,6 °C) |
| kritische **Oberflächen**-RH (`critical_rh`) | 80,0 % |
| 48-h-Mittel `surface_rh_mean` | 69,38 % (Regel-1-Linie: 75 %) |
| Fenster | zu |
| Zonen-Diagnose | **`occupied: false`**, `presence_level: "room_eco"`, **`room_absent_min: 424,7`** (7,1 h), `home_present: true` |

**Die frühere Fassung verglich 87,9 % gegen 63,3 % und sprach von „24,6 pp darüber". Das war falsch** — `rh_max_safe` ist ausdrücklich eine **Raumluft**-Obergrenze, keine Oberflächengrenze. Richtig ist dieselbe Grenze in drei Koordinaten, die einander exakt entsprechen:

| Koordinate | Ist | Grenze | Abstand |
|---|---|---|---|
| Raumluft-RH | 69,5 % | `rh_max_safe` 63,3 % | **+6,2 pp** |
| Oberflächen-RH | 87,9 % | `critical_rh` 80,0 % | **+7,9 pp** |
| absolut | 13,78 g/m³ | `abs_max_safe` 12,54 | **+1,24 g/m³** |

Der Zustand bleibt eindeutig kritisch — nur eben um 6,2 statt 24,6 Prozentpunkte. Rat: **`idle` / `no_gain`**.

## 2. Befund A — die konfigurierte Präsenzquelle bleibt trotz tatsächlicher Nutzung unter ihrer Belegungsschwelle

Die Diagnose meldet 7,1 h Abwesenheit; tatsächlich war das Bad heute früh mehrfach in Gebrauch. Beides stimmt: Poise gibt wieder, was seine Quelle liefert.

**Poise liest `binary_sensor.badezimmer_occupancy_status`** (Area-Occupancy). Letzte `on`-Phasen: **gestern 20:37–20:39 und 20:47–20:48**, seither durchgehend `off`. Die Wahrscheinlichkeit erreichte gestern Abend 85 %, **heute früh nur 51 %** — die Schaltschwelle liegt bei rund 55 %.

**Ein zweiter Indikator im selben Raum hat es gesehen:** `binary_sensor.badezimmer_belegt_indiz` (`device_class: occupancy`) war heute **05:31–06:02, 06:13–06:17 und 06:20–07:44** `on`. Die dritte Phase ist das Duschen — sie lief **zum Messzeitpunkt 07:41 noch** und endete drei Minuten danach. Während Poise also 6,9 h Abwesenheit meldete, sagte ein zweiter Belegungssensor desselben Raums **„belegt, jetzt gerade"**.

(Zeitanker: die Messwerte oben stammen aus der ersten Diagnose-Abfrage um **07:41** mit `room_absent_min` 413,6; eine zweite Abfrage um **07:52** ergab 424,7 — die Differenz von 11,1 min bestätigt beide Zeitpunkte.)

**Identifikation der konfigurierten Quelle** (die Diagnose redigiert Entity-IDs), zwei unabhängige Belege: die Abwesenheitsuhr startete um **00:48**, zwei Minuten nach dem HA-Neustart um 00:46 — genau das Verhalten von `step_room_absence` (Neustart → `present is None` → Uhr gelöscht); und sie wurde **nie zurückgesetzt**, obwohl `belegt_indiz` dreimal ansprang, was `any_present` als ODER über die konfigurierte Menge ausschließt.

**Installationsseitig behebbar:** `CONF_OCCUPANCY_SENSOR` nimmt eine Menge (`multiple=True`, device_class `occupancy`/`motion`/`presence`) und verodert sie; `belegt_indiz` trägt die passende device_class. Alternativ die Area-Occupancy-Schwelle senken.

## 3. Befund B — Gebäudeschutz hängt an einer Komfortsperre

| Regel | Bedingung, die fehlt |
|---|---|
| `moisture_out` (öffnen) | Δ 5,1 ✓, 13,8 > 8,7 ✓, 69,5 % ≥ 50 ✓ — aber **belegungs-gegatet** |
| `mold_risk` (öffnen, ungegatet) | liest das **48-h-Mittel**: 69,38 gegen 75; bei unveränderten Bedingungen ≈ 17 h, praktisch nie |
| `mold_guard` (schließen, ungegatet) | verlangt ein **offenes** Fenster |
| übrige | Trockenboden weit unterschritten; vier Regeln verlangen ein offenes Fenster; Raum 22,4 unter der Kühlkante 28,5; CO₂ inert |

Der einzige Rat, der hier „öffnen" sagen kann, hängt an einem Präsenzmodell; der einzige ungegatete Öffnen-Rat an einem Signal mit 48 h Zeitkonstante. **Ein Bad ist genau dann am nassesten, wenn niemand mehr darin steht** — und genau dann ist ein Präsenzmodell am unsichersten. Befund A ist damit keine Einzelstörung, sondern eine **strukturell wiederkehrende Schwäche gerade bei Feuchtespitzen nach der Raumnutzung**.

Kein Nebeneffekt von N4–N6: die Belegungssperre steht seit Inkrement 1 (ADR-0050), die Regel-1-Linie seit dem Designplan. Präzedenz für die Lösung steht im selben ADR: **N1 hat `heat_out` bewusst nicht belegungs-gegatet** („Nachtauskühlung ist im leeren Raum am wertvollsten").

## 4. Befund C (neu, aus der Review-Korrektur) — `mold_guard` vergleicht zwei verschiedene Größen

Die Größenverwechslung meines Reports steht **auch im Code**. `comfort/ventilation.py`, Regel 1b:

```python
and surface_rh_pct > rh_max_safe_pct
```

links eine **Oberflächen**-RH, rechts eine **Raumluft**-Obergrenze. Die Dimension stimmt auf beiden Seiten — relative Feuchte ist dimensionslos —, der **Bezug** nicht: es sind zwei relative Feuchten mit **unterschiedlicher Bezugstemperatur**, also zwei nicht direkt vergleichbare Koordinaten derselben Wasserdampfmenge. Der Quotient ist `p_sat(T_Raum)/p_sat(T_si)` und liegt im Feld bei **1,20–1,27**; die Regel spricht damit systematisch zu früh an — effektiv ab Raum-RH > `rh_max_safe`/1,2 statt ab `rh_max_safe`.

Nachgerechnet an drei realen Ticks (t_out jeweils aus den publizierten Werten zurückgerechnet, die Nachrechnung reproduziert `surface_rh` und `rh_max_safe` auf 0,1 genau):

Die letzte Spalte betrifft **nur den RH-Vergleich** der Regel, nicht die vollständige Regel: `mold_guard` verlangt zusätzlich ein offenes Fenster und `surface_needs_warmer`. Im Bad ist das Fenster zu, dort kann die Regel also ohnehin nicht auslösen — der fehlerhafte Teilvergleich ist trotzdem wahr. In Schlafzimmer und Küche hat die **vollständige** Regel historisch tatsächlich ausgelöst.

| Fall | Raum vs `rh_max_safe` | Oberfläche vs `critical_rh` | w_in vs `abs_max_safe` | kanonisch kritisch? | RH-Vergleich im Code erfüllt? |
|---|---|---|---|---|---|
| Bad, 14.09. 07:41 | 69,5 vs 63,3 → **+6,2** | 87,9 vs 80,0 → **+7,9** | **+1,24** | **ja** | ja — hier deckungsgleich |
| Schlafzimmer, 14.09. 06:38 | 62,0 vs 62,8 → **−0,8** | 79,0 vs 80,0 → **−1,0** | **−0,15** | **nein** | ja — **zu Unrecht** (Regel hat ausgelöst) |
| Küche, 19.08. (Anlass von N2) | 66,0 vs 68,6 → **−2,6** | 77,0 vs 80,0 → **−3,0** | **−0,53** | **nein** | ja — **zu Unrecht** (Regel hat ausgelöst) |

Die drei kanonischen Formen stimmen exakt überein — es ist **eine** Grenze in drei Koordinatensystemen, nicht drei Bedingungen. Der Code-Vergleich ist eine vierte, bezugsgrößeninkonsistente Variante und die einzige, die auch dort auslöst, wo die Grenze nicht überschritten ist.

**Tragweite.** Das Schlafzimmer, dessen `close`-Rat den ganzen N6-Vorgang ausgelöst hat, lag **1,0 pp unter** seiner Schimmelgrenze. Und der **Küchenfall vom 19.08., der Anlass von N2**, lag 3,0 pp darunter — unter der kanonischen Bedingung hätte `mold_guard` dort nie gefeuert. Der thermische Teil von N2 (Wächter 5, `cool_edge_protected`/`surface_needs_warmer`) ist davon **nicht** betroffen; er verhindert den ursprünglichen `heat_out`-Fehlrat weiterhin. Betroffen ist nur der aktive Schließ-Rat.

**Minimaler Korrekturpfad — eine Zeile, ohne neue Schnittstelle:**

```python
-        and surface_rh_pct > rh_max_safe_pct
+        and rh_pct > rh_max_safe_pct
```

`rh_max_safe_pct` **ist** die sichere Raumluft-RH, und `rh_pct` (die Raumfeuchte) liegt seit N5 ohnehin in der Signatur von `ventilation_advise` — die kanonische Form braucht also weder einen neuen Parameter noch eine neue Größe an der Naht. Die physikalisch explizitere Variante `surface_rh_pct > critical_rh_pct` wäre gleichwertig, müsste aber `critical_rh` erst bis in die pure Funktion transportieren.

**Bewusst nicht umgesetzt.** Die Korrektur würde `mold_guard` aus seinem eigenen Gründungsfall entfernen und ist damit eine Entscheidung über N2/N3, kein Patch. Sie gehört vor die Umsetzung von Befund B, weil der vorgeschlagene Schutzzweig dieselbe Grenze benutzt.

## 5. Vorschlag (offen) — in der Fassung des Reviewers

Statt eines konkurrierenden Regelzweigs: **zwei Eintritte in dieselbe Feuchte-Episode**, die N6 bereits modelliert.

1. **Eintritt `moisture_out`** — wie heute: belegungs-gegatet, 8,7 g/m³ + 50 % rF, Δ ≥ 3,0.
2. **Eintritt `moisture_protect`** — ungegatet: `rh_room > rh_max_safe` **und** Δ ≥ 3,0 g/m³ **und** die thermische Schutzkante bindet nicht durchgreifend.
3. **Halten** — am eigenen Grund: `prev_vent_reason == "moisture_protect"` (nicht am globalen `prev_advice_active`), mit der vorhandenen 1,5-g/m³-Ausschwelle.
4. **Ausstieg** — Schutzgrenze wieder unterschritten **oder** Δ < 1,5. Bei offenem Fenster muss daraus ein **expliziter `close`** werden, kein Durchfallen nach `idle`/`no_gain`: der Rat, der das Fenster geöffnet hat, muss es auch wieder schließen.
5. `mold_guard` tritt genau so lange zurück, wie einer der beiden Gründe gültig ist — also über `moisture_reason_valid` erweitert, nicht daneben; fällt der Grund weg oder bindet die Schutzkante, übernimmt er im selben Tick.

Ob die Schutzgrenze selbst eine kleine Hysterese von 0,5–1 pp braucht (sonst kann ein Raum bei 63,4 → 63,2 % gegen eine Grenze von 63,3 % an der Kante pendeln), bleibt **Kalibrierfrage**; der tragende Punkt ist der ursachenspezifische `close`. Damit hängt dieser Befund unmittelbar an der offenen `prev_vent_reason`-Bereinigung.

**Die offene Frage aus Fassung 1 ist beantwortet:** `w_in > abs_max_safe` ist **keine** zweite unabhängige Auslösung, sondern dieselbe Grenze in anderen Koordinaten. `w_in − abs_max_safe` bleibt als **Schweregrad** wertvoll („der Raum trägt 1,24 g/m³ mehr Wasserdampf, als die Bauteilsituation zulässt") und gehört in die Anzeige, nicht in die Bool-Entscheidung.

Eigener Grund-Token, damit die Karte `moisture_protect` (Bauteilschutz, auch ohne Anwesenheit) von `moisture_out` (Komfort) unterscheiden kann — das erleichtert später auch die ursachenspezifischen Ausstiege.

## 6. Modellpunkt für ADR-0066

Die Trennung, die der Reviewer vorschlägt, sollte explizit in den ADR: **Langzeit-/Dosisrisiko** — der fortlaufende VTT-Mould-Index mit seinem 48-h-Akutbackstop für Dauernässe — entscheidet über **Heizen/Schutzboden**; **akute Überschreitung + realer Außentrocknungsgewinn** entscheidet über die **Lüftungsempfehlung**.

Die beiden „48 h" im System sind dabei auseinanderzuhalten: der **Backstop** des Dosismodells (ADR-0071, Dauernässe) und die **Zeitkonstante τ des EWMA `surface_rh_mean`** (ADR-0066, Regel 1) sind verschiedene Mechanismen, die zufällig dieselbe Zahl tragen. Ein Lüftungsrat kostet nichts und ist reversibel, ein Schutzboden kostet Geld und übergeht den Nutzerwunsch — dieselbe Trennlinie, die N3 schon zwischen Rat und Handlung gezogen hat.

## 7. Offene Punkte, die dieser Befund berührt

* **Substrat/`f_Rsi` als sichtbarer Kalibrierpunkt:** aktiv ist `sensitive` bei `f_Rsi = 0,7`; `mould_risk` hat für Bäder bereits `medium resistant` vorgesehen, aber nicht verdrahtet. Bevor `rh_max_safe` ein ungegateter Schutz-Trigger wird, sollte diese Annahme als Kalibrierpunkt benannt sein — sie verschiebt die Grenze in beide Richtungen.
* **`prev_advice_active` als globaler Hysterese-Anker** statt ursachenspezifisch: bekannte Schuld, kein Fehlrat.
* Trennung von Eintritt und Halten bei `mold_risk`; ursachenspezifische Ausstiege statt `target_reached`.
