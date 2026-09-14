# Feldbefund 2026-09-14: der Lüftungsrat kippte am Fensterkontakt

**Anlass:** Meldung des Betreibers — „Es wird empfohlen zu lüften (Feuchte), kaum dass das Fenster auf ist, soll ich es wieder schließen (Schimmelschutz) — als gäbe es keine Hysterese." · **Methode:** laufende Instanz ausgelesen (Entitätsattribute + Verlauf von Fensterkontakt und `sensor.<zone>_luftungs_empfehlung`) · **Ergebnis:** kein Hysterese-Problem, sondern eine **fehlende Rückkopplung** — der Rat war eine Funktion des Fensterkontakts · **Behoben in v0.194.4** (ADR-0066 N6)

## 1. Die Messung

Schlafzimmer, 2026-09-14 06:38, aus `climate.schlafzimmer_trv_2`:

| Größe | Wert |
|---|---|
| Lufttemperatur / rF | 22,0 °C / 62 % |
| operative Temperatur / MRT | 21,5 °C / 21,0 °C |
| absolute Feuchte innen / außen | 12,0 / 8,3 g/m³ → **Δ 3,7** (Eintritt 3,0) |
| Oberflächen-RH momentan | **79,0 %** |
| sichere Decke `rh_max_safe` | **62,8 %** |
| 48-h-Mittel `surface_rh_mean` | 67,26 % (Regel-1-Linie: 75 %) |
| `mould_engaged` / `mould_floor` / `norm_binding` | false / null / null |
| Kühlkante `cool_sp_active` | 22,0 °C |
| `abs_max_safe` | 12,2 g/m³ — 0,2 über der Raumfeuchte |

## 2. Der Verlauf

`binary_sensor.fenster_sensor_schlafzimmer_contact` gegen `sensor.schlafzimmer_trv_luftungs_empfehlung`:

| Zeit | Fenster | Rat |
|---|---|---|
| 04:03:24 | **auf** | `close` (`mold_guard`) — dieselbe Sekunde |
| 04:32:13 | zu | `open` (`moisture_out`) — dieselbe Sekunde |
| 04:33:51 | **auf** | `close` — dieselbe Sekunde |
| 04:37:37 | auf | `open` — von selbst, Fenster blieb offen |

## 3. Ursache

**(a) Der Rat war eine Funktion des Kontakts.** `mold_guard` verlangt drei Dinge: Fenster offen, `surface_needs_warmer`, Oberflächen-RH über der Decke. Die letzten beiden waren **bereits bei geschlossenem Fenster erfüllt** (79,0 % gegen 62,8 %) — der einzige fensterabhängige Term der Regel *ist* der Kontakt. Da Regel 1b über Regel 3 steht, kippte der Rat mit dem Kontakt und war per Konstruktion nicht befolgbar: schließen → „öffnen" → öffnen → „schließen". Nichts in der Regel maß, was das Lüften bewirkt hatte.

**(b) Die Selbstauflösung um 04:37 war die Punktvergleichs-Kante.** `surface_needs_warmer` vergleicht die nötige Lufttemperatur mit der Kühlkante auf 0,05 K genau. Hier sind Raumtemperatur und Kante beide exakt 22,0, und die Raumfeuchte liegt 0,2 g/m³ unter der eigenen Decke `abs_max_safe` — ein Zehntel Gramm entscheidet. **Kontrollprobe Küche**, dieselbe Minute: gleiche Lage, Fenster seit 04:30 offen, 77,0 % gegen 62,5 % — aber 11,9 statt 12,0 g/m³ innen, und sie liegt auf der anderen Seite derselben Schwelle und rät korrekt `open`.

**(c) Der Notausgang war zu.** Die Öffnen-Seite (`mold_risk`) liest ein träges 48-h-Mittel gegen ein **festes** 80-%-Limit (Marge 5 pp → Linie 75 %); mit 67,26 % feuert sie nicht. Die Schließen-Seite liest den **Momentanwert** gegen eine **dynamische** Decke von 62,8 %. Diese Asymmetrie — langsam+fest gegen schnell+dynamisch — hatte die externe Nachprüfung vom 2026-09-13 als Befund 2 benannt; im Feld erzeugt sie keinen verzögerten, sondern einen widersprüchlichen Rat.

**(d) Inhaltlich war der Schließ-Rat hier falsch.** Die Außenluft ist absolut 3,7 g/m³ trockener, es greift kein Schutzboden, und Lüften senkt genau die Größe, die die Oberflächen-RH treibt. Der Fall, für den N2 die Regel gebaut hat, sah anders aus: dort hielt ein greifender Boden die Kühlkante, und der Gewinn betrug nur 1,6 g/m³.

## 4. Behebung (v0.194.4, ADR-0066 N6)

1. **`mold_guard` tritt zurück, solange Lüften die Behandlung ist:** Außenluft mindestens um die Eintrittsschwelle der Feuchteregel trockener (3,0 g/m³) **und** kein durchgreifender Schutzboden. Die beiden Feldfälle trennen auf dieser Linie sauber — Küche 2026-08-19: 1,6 g/m³ und gebundene Kante; Schlafzimmer 2026-09-14: 3,7 g/m³ und keine Bindung —, es war keine neue Zahl nötig. Ohne Außenfeuchte gibt es kein `delta`, also auch kein Argument fürs Lüften: die N4.2-Zusage (Gebäudeschutz überlebt einen fehlenden Außensensor) bleibt unberührt.
2. **Asymmetrische Marge statt Punktvergleich:** Eintritt weiter 0,05 K unter der Kante, Loslassen erst 0,35 K darunter — dieselbe Eintritt-eng/Ausstieg-weit-Form wie bei den Feuchte- und Freikühl-Schwellen, verankert am bereits vorhandenen `prev_vent_reason`.

## 5. Nebenwirkung, bewusst in Kauf genommen

Der N3-Nachweisfall („frische Installation, nasse Wände, kein Boden durchgreifend") trug eine zweite Variable, die N3 nicht getrennt hatte: seine Außenluft war 5,1 g/m³ trockener. Unter N6 rät Poise dort zum **Lüften** statt zum Schließen. Die Aussage von N3 — der Rat darf nicht auf die Reifezeit der Dosis warten — bleibt und wird jetzt an einer schwülen Außenluft gezeigt (14 °C / 98 % = 1,7 g/m³ Gewinn), wo die offene Scheibe wirklich die Ursache und nicht die Behandlung ist.

## 6. Weiterhin offen

Die ursachenspezifischen Ausstiege über `prev_vent_reason` (statt des generischen `target_reached`) und die τ-Kalibrierung bleiben offen; N6 nimmt dem EWMA-Befund der Nachprüfung die Dringlichkeit, hebt ihn aber nicht auf.
