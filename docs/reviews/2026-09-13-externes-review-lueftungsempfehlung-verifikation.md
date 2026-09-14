# Verifikation 2026-09-13: externes Review der Lüftungsempfehlung

> **Fortsetzung:** Die Nachprüfung desselben Reviewers zu v0.194.2 und ihre Verifikation stehen in [2026-09-13 (Nachprüfung)](2026-09-13-externes-review-lueftungsempfehlung-nachpruefung.md). Sie bestätigt die N4-Korrekturen **und** die Verwerfung aus §7 dieses Dokuments.

**Gegenstand:** externer Bericht zur Bewertung von `comfort/ventilation.py` · **Methode:** jede Aussage gegen Code, ADR-0066 (samt N1–N3) und eigene Psychrometrie-Rechnung geprüft · **Ergebnis:** ein echter, undokumentierter Defekt bestätigt; fünf weitere Befunde tragfähig; drei Punkte sind im ADR bereits als offene Inkremente beschrieben und keine Entdeckung; **ein Befund (12) nach der Umsetzung widerlegt** — Korrektur unten

## 1. Gesamturteil

Das Review ist fachlich gut und in der Hauptsache **richtig**. Sein stärkster Befund — die Außenfeuchte wird aus einer Ersatz-Außentemperatur gerechnet — ist im Code bestätigt, in keinem ADR behandelt und erzeugt nachweislich ein falsches **„öffnen"**. Das allein rechtfertigt den Bericht.

Schwächer ist es dort, wo es Entscheidungen als Versäumnis darstellt, die ADR-0066 ausdrücklich trifft und begründet (CO₂-Inertheit, τ = 48 h als Kalibrierziel, das Fähigkeits-Gate). Diese drei Punkte stehen wörtlich im ADR, teils mit Anlass und Marktbeleg; ein Review, das sie als Neuigkeit präsentiert, hat die Begründung nicht gelesen. Sie bleiben als Aufgaben richtig — nur eben als bekannte.

Die Empfehlung „Grundarchitektur beibehalten, nicht neu bauen" teile ich. Die vorgeschlagene Reihenfolge ändere ich (§5).

## 2. Befund für Befund

| # | Aussage des Reviews | Prüfung |
|---|---|---|
| 1 | Außenfeuchte aus `t_out_eff` (T_rm / 5 °C-Fallback) | **bestätigt — echter Defekt, §3** |
| 2 | `room_c=room` statt operativ, obwohl `room_decide` vorhanden | **bestätigt** (`shadows.py` bekommt beide, gibt die Lufttemperatur weiter) |
| 3 | 8,7 g/m³ driftet mit der Raumtemperatur | **bestätigt, Zahlen nachgerechnet** (s. u.) |
| 4 | 7,0 / 5,0 g/m³ driften ebenso | **bestätigt** (7,0 g/m³ = 40,6 % bei 20 °C, 28,8 % bei 26 °C) |
| 5 | g/kg statt g/m³ wäre physikalisch sauberer | **bestätigt, Wirkung aber klein** (§4) |
| 6 | `too_dry` bei offenem Fenster sollte `close` sein | **bestätigt**, Regel 2 liefert immer `discourage` |
| 7 | globales `no_data` blockiert Regeln, die Außenfeuchte nicht brauchen | **bestätigt — Widerspruch im Code selbst** (§3.2) |
| 8 | Schließen nach Anlass statt generisch über `delta` | **bestätigt, teilweise** — `cooled_off` macht es für 3t bereits richtig, der Rest nicht |
| 9 | `fan_capable` = „irgendwelche `fan_modes`" | **bestätigt als Code, aber im ADR begründet** (§4) |
| 10 | CO₂-Regel wirkungslos, `co2=None` | **bestätigt — und im Code als solches kommentiert**, kein Fund |
| 11 | τ = 48 h zu träge für einen Hinweis | **bestätigt — und im ADR offener Kalibrierpunkt**, kein Fund |
| 12 | `mold_risk` nutzt festes 80 % statt `rh_max_safe` | ~~bestätigt~~ → **widerlegt, §7** — gebaut, getestet, verworfen |
| 13 | DIN 4108-2:2026-05 ersetzt 2013-02 | **bestätigt** |
| 14 | 2 K / 1 K beim Freikühlen beibehalten | **zugestimmt** |

**Nachgerechnet (Magnus-Formel), die Tabelle des Reviews trifft zu:**

| Raumtemperatur | 18 | 20 | 22 | 24 | 26 | 28 °C |
|---|---|---|---|---|---|---|
| rF bei 8,7 g/m³ | 56,8 | 50,5 | 44,9 | 40,1 | 35,8 | 32,1 % |

## 3. Der eine echte Defekt

### 3.1 Außenfeuchte aus einer Temperatur, die es nicht gibt

`control/pipeline_prepare.py`:

```python
t_out_eff = (
    t_out if t_out is not None
    else (t_rm if t_rm is not None else _FALLBACK_OUTDOOR_C)   # = 5.0
)
```

`diagnostics/shadows.py`:

```python
w_out = absolute_humidity(t_out_eff, rh_out) if t_out_eff is not None and rh_out is not None else None
```

`rh_out` ist eine **eigene, aktuelle** Quelle (ADR-0066: dedizierter Sensor vor Weather-Attribut) und kann unabhängig vom Temperaturkanal verfügbar sein. Fällt die Außentemperatur aus, wird also die **aktuelle** Außen-RH mit einem **gemittelten oder erfundenen** Temperaturwert zu einem Luftzustand verrechnet, den es nirgends gibt. Für die Heizungsregelung ist der Ersatzwert als konservative Krücke dokumentiert und vertretbar; für eine Feuchteentscheidung ist er es nicht.

**Die Fehlerrichtung ist die ungünstige.** T_rm liegt im Alltag unter der aktuellen Außentemperatur, der Fallback fast immer. Damit fällt `w_out` zu niedrig aus, `delta = w_in − w_out` zu hoch — und Regel 3 rät zum Öffnen gegen feuchtere Außenluft, also genau zum Feuchteeintrag, den die Regel verhindern soll.

**Gegenbeispiel, gerechnet:**

| | echt | mit T_rm = 10 °C | mit Fallback 5 °C |
|---|---|---|---|
| außen 18 °C / 80 % → `w_out` | 12,26 | 7,51 | 5,43 g/m³ |
| `delta` gegen Raum 22 °C / 55 % (10,65) | **−1,61** | **+3,14** | **+5,22** |
| Regel 3 (≥ 3,0) feuert? | nein | **ja** | **ja** |

Draußen ist es real **feuchter** als drinnen, und Poise rät zum Lüften. Das Vorzeichen kippt vollständig.

**Korrektur:** Für die Feuchte-Achse nur zusammengehörige, aktuelle Außenwerte verwenden. Fehlt die aktuelle Außentemperatur, ist `w_out` `None` und die Feuchteregeln schweigen — was das vorhandene `no_data` bereits vorsieht. `t_out_eff` bleibt unverändert das, was es ist: der Regelungs-Ersatzwert.

### 3.2 Der `no_data`-Riegel widerspricht dem eigenen Kommentar

```python
if w_in_gm3 is None or w_out_gm3 is None:
    return VentilationAdvice("idle", "no_data", "ok", None)
```

Dahinter steht Regel 1b (`mold_guard`), deren eigener Kommentar lautet: *„It deliberately does NOT require drier outside air: the risk driver is the surfaces cooling down, not imported vapour."* Genau diese Regel wird vom Riegel erschlagen, sobald die Außenfeuchte fehlt — ebenso `thermal_floor`, das mit Feuchte nichts zu tun hat. Der Gebäudeschutz, den ADR-0066 ausdrücklich **nie** gatet, ist also an einer Datenquelle aufgehängt, die er nicht braucht.

Das wiegt schwerer, sobald §3.1 korrigiert ist: Dann wird `w_out` häufiger `None` — und mit dem heutigen Riegel würde das Schimmel-Schließen still verschwinden. **Die beiden Punkte müssen zusammen gefixt werden**, sonst verschlimmert der erste den zweiten.

## 4. Wo das Review recht hat, aber die Wirkung kleiner ist als der Text nahelegt

**g/kg statt g/m³.** Physikalisch korrekt: Der Feuchtegrad ist bei Temperaturänderung erhalten, die Dampfdichte nicht. Ich habe das Raster innen 16–28 °C / 30–80 % gegen außen 0–30 °C / 40–100 % durchgerechnet: Ein **Vorzeichenwechsel** zwischen Δg/m³ und Δg/kg tritt nur in Extremecken auf (schlimmster Fall innen 28 °C/32 % gegen außen 10 °C/98 %: −0,51 g/m³ gegen +0,03 g/kg). An der 3,0-Schwelle ist das folgenlos; am ±1,0-Wächter des Freikühlens ist es bis zu einer halben Schwellenbreite. Die Umstellung ist richtig, aber sie ist Feinschliff und kein Defekt — und ADR-0066 §A hält für die Trockenheitsachse ohnehin fest: *„Regelgröße bleibt g/kg"*. Die Inkonsistenz besteht also hausintern.

**`fan_capable`.** Die Physik des Reviews stimmt — ein Umluftventilator ersetzt keine Außenluft. ADR-0066 §3t begründet das Gate aber: *„eine AC-/Fan-Zone bekommt den Rat nie … die Fan-Zone hat Tier 3"* (ADR-0068). Die Zone ist also nicht schutzlos, sie hat einen anderen Pfad. Der offene Punkt ist ein anderer als der behauptete: HAs `fan_modes` kann **Umluft nicht von Zuluft unterscheiden**, und ein Fähigkeitsmodell dafür existiert nicht. Das ist Entwurfsarbeit, kein Einzeiler.

## 5. Was im Review keine Entdeckung ist

Drei Punkte stehen im ADR, bevor das Review sie nennt:

* **CO₂ inert** — im Aufruf steht wörtlich `co2=None,  # ADR-0049 §1 backend not built yet -> rule 4 inert`, und ADR-0066 §B schreibt „inert bis ADR-0049-Backend".
* **τ = 48 h** — ADR-0066: „**Arbeitswert/Kalibrierziel, nicht normativ** (§12.2-Warnung übernommen)", und unter Inkrement 3: „**Offen:** … τ-Kalibrierung an Felddaten".
* **Trägheit von Regel 1** — N2 nennt als Anlass wörtlich: „Regel 1 hätte selbst feuern müssen, **ihr 48-h-EWMA ist träge**". Genau deshalb liest N3 im `mold_guard` die **aktuelle** Oberflächen-RH statt des Mittels.

Punkt 12 hielt ich aus demselben Grund für umso berechtigter: Dass `mold_risk` weiterhin gegen das feste 80 %-Limit prüft, während N3 für den Guard auf `rh_max_safe` umgestellt hat, sah nach einer **echten** Inkonsistenz in einer Richtung aus, die das Projekt selbst schon eingeschlagen hat. **Das war falsch** — die Umsetzung hat es widerlegt; §7 trägt die Korrektur nach.

## 6. Priorität (abweichend vom Review)

1. **Außenfeuchte nur aus aktuellen, zusammengehörigen Außenwerten** (§3.1) — falsche Empfehlung, still, undokumentiert.
2. **`no_data` regelindividuell** (§3.2) — zwingend zusammen mit 1, sonst verstummt der Gebäudeschutz.
3. **`too_dry` bei offenem Fenster → `close`** — drei Zeilen, eindeutig richtig.
4. ~~**`mold_risk` auf `rh_max_safe` koppeln**~~ — **zurückgezogen, §7.** Es gibt keine Lücke; die beiden Regeln stellen verschiedene Fragen.
5. **8,7 g/m³ nicht mehr als alleinige Eintrittsschwelle**, sondern mit rF kombinieren — braucht eine Entscheidung, nicht nur einen Fix.
6. **`room_c` auf die operative Temperatur** — klein, aber richtig; die Kühlkante wird operativ gedacht.
7. **Schließen nach Anlass** über das vorhandene `prev_vent_reason`.
8. g/kg intern, Fähigkeitsmodell für Umluft, τ-Kalibrierung — Feinschliff bzw. Entwurf, nach Felddaten.

Das Review setzt g/kg auf Platz 3 und die Schwellenfrage auf Platz 4. Ich drehe das: Der Riegel aus §3.2 ist dringender als jede Einheitenfrage, weil er Gebäudeschutz betrifft, und er wird durch Fix 1 **schlimmer**, nicht besser.

**Unverändert lassen:** 2 K / 1 K, die 3,0/1,5-Hysterese, 1000 ppm, die Präzedenzkette und die Trennung Gebäudeschutz / Komfort. Diese Teile sind belegt, mehrfach im Feld nachgeschärft (N1–N3) und tragen.

## 7. Korrektur nach der Umsetzung (2026-09-13, v0.194.2): Punkt 12 ist widerlegt

Die Punkte 1, 6, 7 dieser Tabelle sind umgesetzt (ADR-0066 **Nachtrag N4**, Abschnitte N4.1–N4.3). Punkt 12 wurde ebenfalls gebaut — und dabei **widerlegt**. Diese Verifikation hat ihn oben bestätigt und auf Priorität 4 gesetzt; beides ziehe ich zurück und lasse es durchgestrichen stehen, damit der Irrtum nachvollziehbar bleibt.

**Was die Umsetzung zeigte:** Koppelt man Regel 1 an die dynamische Decke, fallen vier bestehende Tests — darunter der N2-Regressionsfall. Der Live-Tick Küche (48-h-Mittel 72 %, `rh_max_safe` 69,6 %) überschreitet `69,6 − 5` sofort; Regel 1 rät `open` und sitzt über `mold_guard`. Damit wäre exakt der Fehlrat zurück, dessen Beseitigung der Anlass von N2 war.

**Warum mein Urteil falsch war:** Ich habe „beide Regeln sprechen über Schimmel" mit „beide Regeln sollten dieselbe Schranke lesen" verwechselt. Ein **niedriges** `rh_max_safe` bedeutet eine **kalte** Oberfläche, und eine kalte Oberfläche spricht fürs Schließen, nicht fürs Öffnen. Regel 1 fragt absolut („sind die Oberflächen nass"), der Guard relativ („mehr, als diese Wand verträgt"). N3 hat den relativen Eingang dorthin gebracht, wo er hingehört — ihn zusätzlich in die absolute Regel zu ziehen ist kein Gleichziehen, sondern ein Kategorienfehler.

Der feste 80 %-Wert bleibt, und `test_n4_mold_risk_keeps_the_fixed_limit_on_purpose` hält ihn samt Begründung fest, damit der Vorschlag nicht stumm wiederkehrt.

**Unverändert offen** bleiben die Punkte 3/4 (Schwellen-Drift), 2 (`room_c` operativ), 8 (Schließen nach Anlass), 5 (g/kg), 9 (Fähigkeitsmodell) und 11 (τ) — Reihenfolge wie in §6, ohne den gestrichenen Platz 4.
