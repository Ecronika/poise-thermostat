# ADR-0014: Determinismus & numerische Referenzfälle

**Status:** akzeptiert · **Datum:** 2026-06-18 · **Bezug:** E9, E24 · **Verifizierung:** Code-Review (kein Feld-Vorbild — Befund)

## Kontext
G27 verlangt: gleiche Eingänge → gleiche Stellentscheidung, und jede Entscheidung aus Diagnose nachvollziehbar. Offen: wie Determinismus technisch sichern und gegen welche Referenzwerte prüfen.

## Entscheidungstreiber
Reproduzierbarkeit (Debugging, Golden-File-Tests), keine versteckten Nichtdeterminismen, Verifizierbarkeit der Physik gegen Norm.

## Befund am Code
- **Kein Wettbewerber** macht Determinismus zum expliziten Designziel. RoomMind iteriert über `rooms.items()` (Insertion-Order-abhängig), nutzt aber sonst keine Zufallsquellen; die anderen ebenso ad-hoc. Versatile injiziert `self._now` nur für Tests. → Determinismus ist im Feld **implizit/ungesichert**; das ist eine Lücke, kein Vorbild.
- Physik-Referenzprüfung: nur RoomMind testet gegen ein bekanntes Wahr-RC-Modell (ADR-0011); **Normrechenbeispiele** (EN 16798/DIN 4108-2) prüft niemand.

## Entscheidung
1. **Deterministischer Tick:** gleiche Eingänge + gleicher Zustand → identischer `ActuatorCommand`. **Feste Iterationsreihenfolge** (Zonen nach **sortiertem** Schlüssel, nicht dict-Insertion-Order); **keine** versteckte RNG; wo Reihenfolge numerisch zählt (Summen über Zonen/Sensoren), deterministische Sortierung vor Reduktion.
2. **Injizierte Uhr** (ADR-0006) ist die einzige Zeitquelle — keine direkten `time.time()`-Aufrufe in der Regel-Logik; macht Ticks in Tests reproduzierbar.
3. **Float-Stabilität:** dokumentierte Rundung an Ausgabegrenzen; keine reihenfolgeabhängige Akkumulation in Kostenfunktion/EKF ohne feste Ordnung.
4. **Numerische Referenzfälle (E24):** Norm-Rechenbeispiele (EN 16798-1 Komfortband bei gegebenem T_rm; DIN 4108-2 Taupunkt/Oberflächenfeuchte; psychrometrische Enthalpie/Mischungsverhältnis) als **Golden-Fixtures** im Test (ADR-0011, Ebene 1). Jede Physikformel hat mindestens einen Referenzwert-Test (G1/G25).

## Begründung
Da das Feld Determinismus nicht sichert, ist es ein Differenzierer für Wartbarkeit und Golden-File-Regression (ADR-0011). Sortierte Iteration + injizierte Uhr + RNG-Verbot sind die minimalen, wirksamen Maßnahmen. Norm-Fixtures verankern die fachliche Tiefe prüfbar — genau der Moat, den das Feld nicht hat.

## Konsequenzen
**Positiv:** reproduzierbares Debugging; belastbare Golden-File-Regression; Physik gegen Norm abgesichert; Tests nicht-flaky.
**Negativ/Kosten:** Disziplin (sortierte Iteration, keine ad-hoc-Uhr) muss in Reviews durchgesetzt werden; Norm-Fixtures müssen einmalig sauber recherchiert/abgeleitet werden.

## Compliance
Norm-Referenzwerte stammen aus öffentlich dokumentierten Rechenbeispielen; eigenständig umgesetzt.

## Verknüpfungen
Setzt ADR-0006 (injizierte Uhr) voraus. Speist ADR-0011 (Fixtures, Golden-Files). Stützt G27.
