# Verifikation 2026-09-13 (Nachprüfung): externe Zweitbegutachtung von v0.194.2

**Gegenstand:** Nachprüfung des Reviewers zu Release v0.194.2 (`aca691c4`), nachdem die [erste Verifikation](2026-09-13-externes-review-lueftungsempfehlung-verifikation.md) und ADR-0066 N4 die dort gefundenen Defekte behoben hatten · **Methode:** jede Aussage gegen Code, Nachrechnung und ADR-0066 (N1–N4) geprüft · **Ergebnis:** drei neue Befunde bestätigt, einer davon mit unvollständigem Lösungsvorschlag; eine Beobachtung schärfer als vom Reviewer formuliert; zwei Befunde in v0.194.3 (N5) umgesetzt, einer bewusst vertagt

## 1. Gesamturteil

Die Nachprüfung bestätigt N4.1, N4.2 und die `too_dry`-Korrektur und hält nach erneuter Prüfung auch die **Verwerfung** aus N4.4 (`mold_risk` nicht an `rh_max_safe` koppeln) für richtig. Das deckt sich mit der ersten Verifikation, einschließlich deren eigener Korrektur.

Die drei neuen Befunde sind echt. Zwei davon standen als „offen" bereits in N4, aber ohne erkennbare Schwere — die Nachprüfung liefert die Zahlen, die sie einordnen. Der dritte, die RH-Untergrenze für das Trockenheits-Veto, ist neu.

## 2. Befund für Befund

| # | Aussage der Nachprüfung | Prüfung |
|---|---|---|
| 1 | `room_c=room` statt `room_decide` bei `heat_out` | **bestätigt — §3.1**, Lösungsvorschlag aber unvollständig |
| 2 | 48-h-EWMA hält `mold_risk`/`open` 10–20 h über den Schließ-Anlass hinaus | **bestätigt, nachgerechnet — §3.2**; Umsetzung vertagt, mit Grund |
| 3 | 8,7 g/m³ als alleinige Eintrittsschwelle | **bestätigt — §3.3**, umgesetzt (N5.2) |
| 4 | Trockenheits-Veto braucht eine RH-Achse | **bestätigt**, umgesetzt (N5.2), Schwellenwert 35 statt 40 — §3.3 |
| 5 | `heat_out` bekommt weiter `t_out_eff`, praktisch aber folgenlos | **bestätigt und verschärft — §4**: es ist beweisbar folgenlos, nicht nur praktisch |
| 6 | `target_reached` ursachenspezifisch trennen | **bestätigt**, gehört zu Befund 2 — zusammen umzusetzen |
| 7 | CO₂ 1000 ppm, 3,0/1,5 g/m³, 2 K/1 K, 80 %, 2 pp beibehalten | **zugestimmt**, keine Änderung |
| 8 | DIN 4108-2:2026-05 ersetzt 2013-02 | **bestätigt** (stand schon in der ersten Verifikation) |

## 3. Die drei neuen Befunde

### 3.1 Zwei Temperaturbegriffe in einer Regel — und ein halb richtiger Vorschlag

Bestätigt und schärfer als beschrieben: **dieselbe Funktion** vergleicht `eff_cool` an jeder anderen Stelle gegen `room_decide` (`in_deadband=heat_sp <= room_decide <= eff_cool`), nur Regel 3t bekam `room_c=room`. Das ist keine Auslegungsfrage, sondern eine Inkonsistenz innerhalb einer Komposition.

Der Vorschlag, `room_c` durch `room_decide` zu **ersetzen**, ist jedoch nur halb richtig. Regel 3t benutzt den Wert für zwei verschiedene physikalische Fragen:

```
and room_c > cool_edge_c              # „zu warm?"          -> operativ
and t_out_c <= room_c - (2,0 / 1,0 K) # „bringt Öffnen was?" -> Luft gegen Luft
```

Der Wärmeübergang durch ein offenes Fenster ist ein **Luftaustausch**. Eine pauschale Ersetzung macht den Gewinn-Test operativ-gegen-Luft und schreibt der Außenluft den gesamten Strahlungsüberschuss gut — im Beispiel des Reviewers 1,5 K von 2,0 K Einschaltschwelle. Umgesetzt wurde deshalb ein **Paar** von Eingängen (N5.1), und die Spiegelseite ist als eigener Testfall festgehalten.

### 3.2 Der EWMA-Konflikt — bestätigt, aber nicht als Dreizeiler umsetzbar

Die Arithmetik stimmt exakt: mit τ = 48 h braucht ein Mittel von 80 % nach einem Sprung auf 55 % noch 48·ln(25/20) = **10,71 h**, um unter 75 % zu fallen; von 85 % aus 48·ln(30/20) = **19,46 h**. τ ist tatsächlich 48 h (`DEFAULT_SURFACE_TAU_MIN = 48·60`), und die Präzedenz ist von zwei Tests festgenagelt (`test_mold_guard_precedence_below_rule1_and_above_the_rest`, und die N4.4-Schranke). Bei offenem Fenster, trockenerer Außenluft und Mittel ≥ 75 % lautet der Rat `open`, obwohl `mold_guard` schließen würde. Der Konflikt ist real, und der Hinweis auf die UBA-Empfehlung zum **Stoßlüften** trifft den Punkt: der Rat beschreibt derzeit einen Dauerzustand, wo die Handlung eine kurze ist.

**Nicht in v0.194.3 umgesetzt, mit Grund.** Hängt der Ausstieg am Momentanwert und der Eintritt am Mittel, kippt ein Raum genau auf der Linie im Tick-Takt zwischen `open` und `close` — und die Emissionskante (`NOTIFY_REASONS`, `advice_transition`) meldet jeden dieser Wechsel als Episodenwechsel. Das braucht dieselbe asymmetrische Hysterese wie der Rest der Datei und eine Entscheidung, ob „Anlass" und „Haltezustand" zwei Regeln oder eine Regel mit zwei Schwellen werden. Es gehört außerdem mit Befund 6 zusammen, weil `target_reached` genau der generische Ausstieg ist, den die Trennung ersetzt. Das ist ein Entwurf, kein Patch — und damit der Inhalt des nächsten Schritts, nicht dieses.

### 3.3 8,7 g/m³ — bestätigt, mit einem stärkeren Argument als der Drift-Tabelle

Nachgerechnet und bestätigt: Bei 28 °C entspricht die Eintrittsschwelle 32,1 % rF, das Trockenheits-Veto greift dort aber erst unter 7,0 g/m³ = **25,8 % rF**. Zwischen diesen beiden Werten widerspricht nichts, und darüber feuert der Öffnen-Rat aktiv — ein 28 °C warmer Raum mit 33 % rF (8,96 g/m³) bekam den Rat, wegen Feuchte zu lüften. Das Veto kann den Fehler bauartbedingt nicht fangen, weil beide Achsen absolut sind.

Das stärkste Argument ist dabei nicht die Drift, sondern die Herkunft der Zahl: **8,7 g/m³ ist ein Bemessungs-Referenzklima (DIN 4108-2, 20 °C/50 %), keine Betriebsschwelle.** Es sagt, wogegen man ein Bauteil auslegt, nicht, wann man ein Fenster öffnet.

Umgesetzt als N5.2. Beim Trockenheits-Veto weicht die Umsetzung bewusst vom oberen Ende des vorgeschlagenen Bandes ab und nimmt **35 %** statt 40 %: Regel 2 steht über Regel 3t, und eine 40-%-Linie hätte einem Sommerraum mit 26 °C/40 % (9,72 g/m³) das Freikühlen verboten. Der Grund steht im Code und in einem eigenen Testfall.

## 4. Wo die Nachprüfung zu vorsichtig ist

Zu `heat_out` und `t_out_eff` heißt es, das sei „praktisch kein Fehler". Es ist **beweisbar** keiner: Regel 3t verlangt `delta`, `delta` verlangt `w_out`, `w_out` verlangt `t_out_measured` — und wo die gesetzt ist, **ist** `t_out_eff` genau dieser Messwert, weil der Ersatzwert nur bei fehlender Messung entsteht. v0.194.3 macht diese Kette strukturell, indem die Naht `t_out_measured` direkt durchreicht (N5.3); das Verhalten ist bit-identisch, aber eine spätere Änderung am Fallback kann die Regel nicht mehr erreichen.

## 5. Umsetzung und verbleibende Reihenfolge

In **v0.194.3** (ADR-0066 N5): Befund 1 als Eingangs-Paar, Befunde 3 und 4 als relative Begleiter beider absoluter Grenzen, Befund 5 strukturell.

Danach, in dieser Reihenfolge:

1. **Befund 2 + 6 gemeinsam** — `mold_risk`: Eintritt und Haltezustand trennen, Ausstiege ursachenspezifisch über `prev_vent_reason`.
2. g/kg als interne Rechengröße.
3. Fähigkeitsmodell, das Umluft von Zuluft unterscheidet (HAs `fan_modes` kann das nicht).
4. τ-Kalibrierung an Felddaten; Kommentar zu 8,7 g/m³ gegen DIN 4108-2:2026-05 prüfen.

**Unverändert lassen:** 3,0/1,5 g/m³, 2 K/1 K, 1000 ppm, das feste 80-%-Limit in Regel 1 (N4.4), die 2-pp-Marge und die Präzedenzkette.
