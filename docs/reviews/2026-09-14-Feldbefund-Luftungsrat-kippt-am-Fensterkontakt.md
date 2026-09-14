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

1. **`mold_guard` widerspricht der eigenen laufenden Empfehlung nicht:** Der Wächter schweigt, solange eine Lüftungs-Episode läuft, die diese Achse selbst angeordnet hat (letzter Rat `open` mit Grund `moisture_out` oder `mold_risk`) — außer ein Schutzboden greift durch. Die Episode endet an der Ausstiegs-Hysterese der Feuchteregel, `target_reached` schließt, und im Tick danach ist der Wächter wieder frei. Ein ohne Poises Zutun geöffnetes Fenster trifft ihn unverändert an; ohne Außenfeuchte gibt es keine Episode, also bleibt die N4.2-Zusage unberührt.
2. **Asymmetrische Marge statt Punktvergleich:** Eintritt weiter 0,05 K unter der Kante, Loslassen erst 0,35 K darunter — dieselbe Eintritt-eng/Ausstieg-weit-Form wie bei den Feuchte- und Freikühl-Schwellen, verankert am bereits vorhandenen `prev_vent_reason`.

## 5. Der erste Lösungsversuch war falsch — und wie er aufflog

Die erste Fassung hängte den Rücktritt an den **Trocknungsgewinn**: Außenluft mindestens um die Eintrittsschwelle der Feuchteregel (3,0 g/m³) trockener. Die beiden bekannten Feldfälle trennten sich darauf sauber — Küche 2026-08-19 mit 1,6 g/m³, Schlafzimmer heute mit 3,7 —, und es war keine neue Zahl nötig. Das sah nach der Antwort aus.

Die Integrationssuite hat sie in derselben Stunde erlegt. Das Glue-Szenario der Emissionsschiene ist ein Winterfall: 23 °C/60 % innen gegen 6 °C/85 % außen — **6,2 g/m³ Gewinn**, mehr als das Schlafzimmer. Kalte Außenluft ist absolut immer trockener, also hätte die gewinnbasierte Fassung `mold_guard` für die **gesamte Heizperiode** abgeschaltet. Der Gewinn trennt die Fälle nicht.

Was sie trennt, ist, **wessen Anweisung gerade ausgeführt wird**. Im Schlafzimmer hatte Poise das Öffnen geraten und sich selbst widersprochen; im Küchen- und im Glue-Fall stand vorher `heat_out` bzw. gar kein Öffnen-Rat. Die enge Bedingung — den eigenen, noch gültigen Öffnen-Rat nicht zurücknehmen — deckt den Befund vollständig ab und lässt beide Bestandsfälle unverändert.

Als Nebenertrag fällt damit auch die Nebenwirkung weg, die die erste Fassung auf den N3-Nachweisfall gehabt hätte.

## 6. Weiterhin offen

Die ursachenspezifischen Ausstiege über `prev_vent_reason` (statt des generischen `target_reached`) und die τ-Kalibrierung bleiben offen; N6 nimmt dem EWMA-Befund der Nachprüfung die Dringlichkeit, hebt ihn aber nicht auf. Der Wächter 5 der Regel 3t liest weiterhin bewusst das 48-h-Mittel (N2 §2) und nicht den Momentanwert — das trägt, solange `mold_guard` nur während einer laufenden Feuchte-Episode schweigt, in der Öffnen ohnehin gewollt ist.

## 7. Externes Review zu `b024be0` (2026-09-14) — geprüft

Der Reviewer hat den Stand `b024be0` begutachtet, also die **gewinnbasierte erste Fassung**, die die Integrationssuite kurz danach erlegt hat. Seine drei inhaltlichen Befunde sind alle richtig, und sein Lösungsvorschlag — den Rücktritt an die tatsächliche Feuchte-Episode über `prev_vent_reason` koppeln statt an Δ — ist genau der Weg, der hier unabhängig eingeschlagen wurde. Gegen den jetzigen Stand nachgerechnet:

| Befund | Stand `b024be0` | heutiger Stand |
|---|---|---|
| 1 — Rücktritt bei 3,0, Episode hält bis 1,5 → zweiter Flip an der Schwelle | zutreffend | **behoben**: ein gemeinsames Prädikat `moisture_reason_valid`, von Regel 1b und Regel 3 gelesen |
| 2 — Δ ≥ 3 allein ist kein „Lüften ist die Behandlung"; 8,6 g/m³ / 45 % bei Δ 3,6 endet in `idle` über offenem Fenster | zutreffend | **behoben**: der Rücktritt verlangt den **ganzen** Grund samt Innenfeuchte-Linien; sein Gegenfall liefert `close`/`mold_guard` — mit und ohne vorangegangene Episode |
| 3 — keine echte Rückkopplung, kalte Außenluft hat immer großes Δ | zutreffend, und genau daran ist die Fassung gescheitert (Glue-Szenario: 6,2 g/m³) | **entschärft**: Δ steuert den Rücktritt nicht mehr; die Episode hat einen definierten Endpunkt. Eine Messung des tatsächlichen Lüfterfolgs ist es weiterhin nicht — bleibt offen |
| Doku: `cool_edge_protected`-Vorrang gilt nicht global, `mold_risk` steht davor | zutreffend | **Text präzisiert** (Reichweite auf Regel 1b eingegrenzt) |
| 0,35 K ist ein Arbeitswert, kein physikalischer Grenzwert | zutreffend | **als Kalibrierziel gekennzeichnet**, wie τ = 48 h |
| 0,05/0,35-K-Hysterese beibehalten | — | unverändert übernommen |

Die vier von ihm benannten Testfälle sind als `test_n6b_*` ergänzt. Sein Hinweis zu den fehlenden GitHub-Statuschecks trifft eine andere Schiene: GitHub Actions veröffentlicht **Check-Runs**, keine Commit-Status, weshalb `/statuses` `total_count: 0` liefert; unabhängig davon war der Lauf auf `b024be0` tatsächlich **rot** — an genau dem Fall, den sein Befund 3 beschreibt.
