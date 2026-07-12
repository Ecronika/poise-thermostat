# ADR-0061: Kühlkante — fest bei Anwesenheit, adaptiv nur free-running

**Status:** Implementiert (v0.165.0) · **Datum:** 2026-07-12 · **Bezug:** ADR-0023 (Dual-Setpoint + adaptive Kante §1), ADR-0051 (Hitzetag-Kühlband), ADR-0058 (Presence/Occupancy), ADR-0027 (Norm-Grenzen), ADR-0050 (Feuchte/Dry) · **Grundlage:** EN 16798-1 (adaptives Modell nur ohne mechanische Kühlung), ASHRAE 55, ASR A3.5, Live-Befund Büro Technik 2026-07-12 + Nutzererwartungs-/Norm-Recherche

## Kontext

Poise hob die Kühlkante bislang **immer** adaptiv an (`adaptive_cool_edge`, ADR-0023 §1 live), sobald das Gerät kühlfähig ist und das Laufmittel im adaptiven Gültigkeitsbereich liegt — gedeckelt am ASR-Cap (`cool_hard_cap`, Default 26). Live-Befund Büro Technik: Raum operativ ~26 °C, Kante adaptiv auf ~26 gehoben → Raum genau an der Decke → kein Kühlbefehl; im so entstehenden Totband kippte die Feuchte-Logik (Cat I, RH > 50 %) auf **dry** statt zu kühlen. Nutzer erwarten „kühlt, wenn ich anwesend bin und es warm ist" (~24–25 °C Büro-Sweetspot).

**Norm-Befund (verifiziert):** Das adaptive EN-16798-Komfortmodell gilt **ausschließlich für Gebäude *ohne* mechanische Kühlung** (Fensterlüftung, Nutzer regelt Kleidung/Fenster selbst); ASHRAE 55 zieht dieselbe Grenze. Sobald eine Split-AC **aktiv kühlt**, ist der Raum „mechanisch gekühlt" → es gilt das **feste PMV-Kategorieband** (Cat I Kühlen 23,5–25,5). Der Codebase dokumentiert das bereits (`en16798.py`: „the adaptive band … applies only to free-running buildings; when actively heating/cooling these fixed category ranges govern"; `free_running.py`: die *volle* Anhebung ist bewusst nur Shadow). Die mildere Live-Anhebung `adaptive_cool_edge` wandte das adaptive Modell aber auch auf einen **anwesenden, aktiv gekühlten** Raum an — ein Widerspruch zur Norm und zur Erwartung.

**Regler-Befund:** `comfort_weight` steuert nur die ±1,5 K Totband-Verbreiterung; die adaptive Anhebung überschrieb sie danach (Kante immer ~Cap). Der Komfort/Energie-Regler war fürs Kühlen faktisch wirkungslos.

## Entscheidung

Die adaptive (free-running) Kühlkanten-Anhebung greift **nur, wenn die Zone nicht besetzt ist** (`occupied=False`, ADR-0058). Eine **besetzte, aktiv konditionierte** Zone nutzt das **feste EN-Kategorieband** (Kühlkante ≈ `comfort_base + 2 K`, geklemmt ins Cat-Band, mit `comfort_weight`). Eine **unbesetzte** Zone darf free-running Richtung ASR-Cap driften (Energie sparen; komponiert mit der ADR-0058-Eco-Aufweitung).

- **Ein-Zeilen-Gate** in `comfort/dual_setpoint.py::decide`: `if adaptive_cool and not occupied:` statt `if adaptive_cool:`. Rein — die Parameter `occupied`, `priority`, `adaptive_cap`, `adaptive_cool` fließen bereits durch den Coordinator (kein Glue).
- Das Gate **entmaskiert** den `comfort_weight`-Regler auf der Kühlkante (er bewegt die feste Kante jetzt sichtbar innerhalb des Cat-Bandes).
- **Kein neuer Config-Wert.** `adaptive_cool` bleibt Default `auto` (= aktiv bei kühlfähigem Gerät); die Semantik ist nun „adaptiv **wenn free-running/unbesetzt**". `cool_hard_cap` (26 = ASR-Bürogrenze) wird zum *Abwesenheits*-Cap.

**Wirkung Büro Technik (Cat I, comfort_base 23, cool_weight 70):** anwesend → Kühlkante ~25,3–25,5 → Raum ~26 > Kante → **kühlt** (statt dry im aufgeweiteten Totband). Leer → driftet Richtung 26 (ASR) + adaptiv → Energie gespart. Der Regler bewegt jetzt den Kühl-Einsatzpunkt.

## Begründung

Die Änderung ist zugleich **norm-korrekt** (adaptives Modell nur free-running), **erwartungskonform** (kühlt bei Anwesenheit ab dem festen Bandrand ~25) und **energiesparend, wo es zählt** (Drift nur im leeren Raum). Sie nutzt die vorhandene Presence-Infrastruktur (ADR-0058) statt eines neuen Modus — Occupancy ist der norm-relevante Proxy für „mechanisch konditioniert vs. free-running". Fehlt eine Presence-Konfiguration, gilt `occupied=True` (Default) → festes Band → responsives Kühlen; die Abwesenheits-Drift ist die Opt-in-Energieoption.

## Konsequenzen

**Positiv:** kühlt bei Anwesenheit norm-korrekt ab ~Bandrand; `comfort_weight` wirkt wieder; energiesparende Drift bleibt (unbesetzt); kein neuer Knopf; reine, gut testbare Logik. **Negativ/Migration:** Verhaltensänderung für kühlfähige Zonen ohne Presence — sie kühlten bisher erst ~ASR-Cap (26), jetzt ab dem festen Cat-Bandrand (~25). Wer bewusst wärmer + adaptiv laufen will, hebt `comfort_base` an (norm-saubere Art, das Band zu verschieben) oder konfiguriert Presence (dann driftet der leere Raum). Release-Note nötig (tado-„wtf"-Lehre). Die volle free-running-Widening (`free_running_widen`) bleibt Shadow (ADR-0023 §1 unverändert).

## Verifizierung

- `comfort/dual_setpoint.py` pure: `test_adaptive_cool_edge_gated_on_occupancy` — besetzt + adaptive → festes Band (kühlt); unbesetzt → Anhebung (idle). /tmp-Gate (ruff/format/py_compile) grün; volle pure- + Integrations-Suite CI-verifiziert.
- `test_cool_raise.py` (ADR-0051 Hitzetag) pinnt `adaptive_cool="off"` → unberührt; `test_adaptive_cool.py` prüft den Tri-State-Resolver → unberührt.

## Verknüpfungen

Verfeinert ADR-0023 §1 (adaptive Kante jetzt occupancy-gegatet, Norm-Anwendbarkeit geschärft) und nutzt ADR-0058 (`occupied`). Berührt ADR-0051 (Hitzetag-Raise, weiterhin bei aktiver Kühlung) und ADR-0050 (weniger unnötiges Dry, weil der besetzte Raum eher kühlt statt im Totband zu entfeuchten) nicht funktional, verbessert deren Zusammenspiel aber. Norm-Klemmen (ADR-0027) bleiben unumgehbar.
