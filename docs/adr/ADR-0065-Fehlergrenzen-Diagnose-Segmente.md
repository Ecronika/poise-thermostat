# ADR-0065: Fehlergrenzen — eine Grenze je Segment statt zwei Sammel-Domänen

> **Nummern-Korrektur 2026-07-26:** ursprünglich als ADR-0062 angelegt und damit in Kollision mit dem bereits vergebenen ADR-0062 (Schimmelschutz). Umbenannt zu **0065**; Inhalt unverändert. Verweise „ADR-0062" im Refactoring-Plan (docs/Konzepte) und in `test_phase10_shadow_segments.py` meinen DIESEN ADR und wurden mitkorrigiert.

**Status:** Implementiert (v0.179.0) · **Wirkung:** Live-A · **Datum:** 2026-07-25 · **Bezug:** ADR-0026 (Schatten-Schätzer-Politik), ADR-0033 (MPC-Shadow), ADR-0036 (TPI-Direktventil), ADR-0037 (PI-Kompensator), ADR-0043 (prädiktive Verschattung), ADR-0046 §8/§9 (Verdichterschutz, Lifecycle-Fold), ADR-0050 (Feuchte/Dry), ADR-0051 (Hitzetag-Kühlband), ADR-0012 (Diagnose/Repair) · **Grundlage:** Refactoring-Bericht coordinator.py (Befunde 1–3, 11), Phase-0-Fault-Injection-Tests

## Kontext

Der Coordinator hatte zwei breite `except Exception`-Grenzen, die historisch gewachsen waren und jeweils eine ganze Kette zusammenfassten:

**Shadow-Domäne (`finalize_tick`).** Peak-Prognose → MPC-Shadow → TPI → PI (+Integrator-Fortschreibung) → Kompressor-Lifecycle-Fold → Thermal-Arbitration → `shadow_objs`-Assembly lagen unter EINEM `try`. Der Kommentar daneben deklarierte den Block als „diagnostics must never break control" — tatsächlich hingen aber **drei live wirksame Dinge** darin:

1. **`tpi_duty`** ist nicht bloß Diagnose: `heat_demand` ist per R13 die Live-Duty, solange sie existiert. Fiel die *Verschattungs*-Prognose aus (erster Schritt der Kette), degradierte `heat_demand` auf das binäre `float(heating)` — der Kessel-Hub bekam eine gröbere Anforderung, ausgelöst von einem völlig unbeteiligten Shadow.
2. **Der Lifecycle-Fold** (`_lifecycle.observe`) speist den Verdichter-Guard des FOLGEticks (ADR-0046 §8, live). Ein Shadow-Fehler übersprang den Fold, der Guard urteilte im nächsten Tick gegen einen veralteten Laufzustand.
3. **`_pi.acc`** (Integrator) fror still ein — ein Regler-Zustand, der von einem Diagnosefehler angehalten wurde.

**Klimaband-Domäne (`_stage_climate_band`).** Die LIVE Humidity-/Dry-Entscheidung (ADR-0050 S2c, treibt den Dry-Mode-Nudge) und die reinen Free-Running-/Fan-/PMV-Shadows plus die `climate_diag`-Assembly lagen ebenfalls unter EINEM `try`. Ein Fehler in `humidity_decide` nahm nicht nur den Nudge mit, sondern löschte **alle 11 Klimaband-Keys** aus `coordinator.data` — der Nutzer sah eine leere Karte statt einer benannten Störung.

Beide Grenzen waren als Phase-0-Verhalten exakt eingefroren (`test_phase0_fault_shadow_domain`, `test_phase0_fault_climate_domain`), damit das Coordinator-Refactoring sie nicht versehentlich verschiebt.

## Entscheidung

**Eine Fehlergrenze je Segment.** Die Reihenfolge der Auswertung bleibt unverändert; nur die Fehlerausbreitung wird auf das jeweilige Segment beschränkt.

**Shadow-Domäne → sechs unabhängige Segmente** (`_shadow_cover`, `_shadow_mpc`, `_shadow_tpi`, `_shadow_pi`, `_shadow_lifecycle`, `_shadow_arbitration`). Jedes liefert sein eigenes `shadow_objs`-Fragment auf den neutralen Seed; die fünf Fragmente sind eine **Partition** der 19 Keys (pure getestet). Damit:

- **F-TPI** — `tpi_duty` (und `heat_demand`) überlebt jeden fremden Shadow-Fehler.
- **F-LIFECYCLE** — der Fold läuft in jedem Tick; der Verdichter-Guard urteilt nie gegen einen veralteten Zustand.
- **F-PIACC** — der Integrator wird nur noch von einem Fehler der PI-Auswertung selbst angehalten.

Die **einzige** verbleibende Kopplung ist eine echte Datenabhängigkeit, keine Fehlerdomäne: die Thermal-Arbitration konsumiert die `DeviceRuntime` des frisch gefalteten Lifecycles, wird also übersprungen, wenn der **Fold selbst** scheitert — nie wegen eines anderen Shadows. Die beiden `compressor_gate_*`-Keys gehören ausschließlich dem Lifecycle-Segment; sie fehlen genau dann, wenn der Fold ausfällt.

**Klimaband → zwei Grenzen.** Die LIVE-Entscheidung (`_climate_humidity`) und die reine Shadow-Komposition (`_climate_shadows`) trennen sich (**F-HUMSHADOW**). Bei einem Humidity-Fehler:

- fällt der Dry-Nudge weiterhin still auf `idle` und der `dry_active`-Latch wird **übernommen, nicht zurückgesetzt** (ein gescheiterter Entscheid ist kein Beleg dafür, dass die Entfeuchtung endete);
- läuft die Shadow-Komposition trotzdem — gegen einen neutralen `HumidityDecision`, sodass alle `climate_diag`-Keys publiziert bleiben und `humidity_reason` den Ausfall **benennt** (`"humidity block failed"`) statt zu verschwinden.

Jede Grenze hat ihren eigenen **warn-once**-Latch (AR-32): `hum_shadow_warned` für den Live-Pfad, `climate_shadow_warned` für die Shadows.

**Log-Vertrag.** Der Shadow-Record behält seinen Text (`"Poise: shadow evaluation failed"` — Nutzer filtern darauf) und trägt jetzt den Segmentnamen: `shadow evaluation failed (cover|mpc|tpi|pi|lifecycle|arbitration)`.

## Begründung

Eine breite Grenze ist genau so viel wert, wie ihr Inhalt homogen ist. Beide Domänen waren **nicht** homogen: sie mischten reine Diagnose mit Live-Zustand. Die Grenze schützte damit nicht den Regelpfad — sie riss ihn bei jedem Diagnosefehler ein Stück mit. Die Segmentierung ist die minimale Änderung, die den ursprünglichen Anspruch („Diagnose darf die Regelung nie brechen") tatsächlich einlöst, statt ihn nur zu behaupten.

Die Alternative — Live-Anteile aus den Diagnose-Blöcken herausziehen und vor die Grenze setzen — hätte die Auswertungsreihenfolge und damit K2b (Guard-Diagnose vor `observe`, ADR-0046 §9) verletzt. Die Segmentierung lässt die Reihenfolge exakt stehen.

## Konsequenzen

**Positiv:** `heat_demand`/`tpi_duty`, der Verdichter-Guard und der PI-Integrator sind gegen fremde Diagnosefehler immun; ein Humidity-Ausfall kostet nicht mehr die halbe Diagnosefläche; der Log benennt das ausgefallene Segment; `_stage_shadow_domain` fällt unter die 150-Zeilen-Grenze (die Phase-8-Ausnahme entfällt).

**Negativ/Migration:** Die Degradation ist feiner und damit weniger „auffällig" — wo früher ein Ausfall die ganze Shadow-Fläche neutralisierte, fehlen jetzt einzelne Keys. Karten/Automationen, die auf `multi_reason == "shadow_error"` als Sammel-Störungsindikator prüfen, sehen diesen Wert nur noch bei einem Lifecycle-/Arbitration-Ausfall. Der Log ist die verlässliche Quelle. Zusätzlich erscheinen die beiden `compressor_gate_*`-Keys jetzt auch dann, wenn ein anderer Shadow scheitert.

## Verifizierung

- `tests/integration/test_phase0_fault_shadow_domain.py` — von „degradiert" auf „bleibt verfügbar" gekippt: F-TPI (`tpi_duty`/`heat_demand` überleben), F-LIFECYCLE (neues `DeviceLifecycle`-Objekt trotz Fault), F-PIACC (`acc` läuft weiter), plus „nur das Cover-Segment degradiert".
- `tests/integration/test_phase10_shadow_segments.py` — parametrisiert über alle fünf übrigen Segmente: eigene Keys degradieren, alle anderen sind bit-gleich zum gesunden Tick; genau EIN Log-Record mit Segmentnamen; die Fold→Arbitration-Datenabhängigkeit explizit gepinnt.
- `tests/integration/test_phase0_fault_climate_domain.py` — Humidity-Fehler: Nudge weiterhin unterdrückt, warn-once erhalten, aber alle `climate_diag`-Keys publiziert und `humidity_reason` benannt; Gegenrichtung (Shadow-Komposition fällt aus) lässt den Live-Nudge und den Latch stehen.
- `tests/test_phase8_shadows.py` — die fünf Fragmente sind eine disjunkte Partition der 19 Keys; die beiden `compressor_gate_*` gehören exakt dem Lifecycle-Fragment.

## Verknüpfungen

Löst die im Refactoring-Plan als `F-TPI`/`F-LIFECYCLE`/`F-PIACC`/`F-HUMSHADOW` geführten Verhaltensfixes ein und beendet die dort dokumentierten „zwei LEGACY-Fehlerdomänen". Schärft ADR-0026 (Schatten-Schätzer dürfen die Regelung nicht beeinflussen — auch nicht über eine gemeinsame Fehlergrenze) und macht die Live-Wirkung von ADR-0036/0046 §8/0050 gegen Diagnosefehler robust. Offen bleibt `F-OUTFOLD` (die Outcome-/HDH-/RegQ-Folds teilen weiterhin die eine `safe_collect`-Grenze — dort ist der Inhalt homogen: alles reine Metrik).
