# ADR-0027: Norm-Compliance — unkonditionale Sollwert-Grenzen (ASR A3.5)

**Status:** Implementiert · **Datum:** 2026-06-20 · **Bezug:** Charta G1/G18, K4/K7 (Konflikt-Analyse), Programmstrukturplan (`norm_compliance`), ADR-0023 (Dual-Setpoint), Phase 1 · **Verifizierung:** ASR A3.5 (Raumtemperatur); Coordinator-Code

## Kontext
Phase 1 forderte ein `norm_compliance`-Modul (ASR/GEG-Grenzen). **VDI 6022 (RLT-Hygiene) ist ausdrücklich ein Nicht-Ziel** (ADR-0048) — Poise besitzt/wartet keine lufttechnische Anlage; `norm_compliance` deckt ausschließlich Temperatur-/Komfortgrenzen (ASR A3.5, EN 16798-1 thermisch), keine Hygiene-/Lüftungsnormen. Bis v0.14.0 gab es Frost-Floor, Schimmel-Floor und Taupunkt-Cap, aber **keinen expliziten, unkonditionalen oberen Sollwert-Deckel**. Mit dem virtuellen MRT (v0.11.0, Kaltwand-Term) kann der Luft-Sollwert in extremer Kälte rechnerisch hoch getrieben werden (Richtung `device_max=30`). Charta G18 verlangt harte, durch Lernen/Defaults **nicht** übersteuerbare Grenzen; K4/K7 verlangen, dass auch der manuelle Override in den Frost/Schimmel/**Norm**-Korridor geklemmt wird.

## Entscheidung
1. **Pure `comfort/norm_compliance.py`** mit `clamp_to_norm(setpoint, *, floor, cap)` → `NormClamp(value, binding)`, `binding ∈ {norm_floor, norm_cap, None}`.
2. **Oberer Deckel = ASR A3.5: `ASR_MAX_ROOM_C = 26 °C`.** Die Lufttemperatur in Wohn-/Arbeitsräumen soll 26 °C nicht überschreiten; Poise **kommandiert nie einen Heiz-Sollwert über 26 °C**.
3. **Unterer Boden** = vom Aufrufer übergeben (`max(Frost, Schimmel-Mindesttemp)`) — die harte Gesundheitsgrenze, die Setback/Effizienz nie unterschreiten.
4. **Floor hat Vorrang vor Cap** bei Inversion (Gesundheit/Sicherheit zuerst).
5. **Verdrahtung:** finaler Clamp im Coordinator *nach* Komfort-/Override-/Fenster-Entscheidung und *vor* `device_max`. **Nicht im aktiven Kühlbetrieb** angewandt (hohe Außentemperaturen sind ein Kühlthema; der obere Wert kommt dann aus dem EN-Kühlband, nicht aus dem Heiz-Überhitzungsdeckel). Bindender Grund als Attribut `norm_binding` sichtbar.

## Begründung
ASR A3.5 ist die einschlägige, benannte Norm für die obere Raumtemperatur (Charta G1: Norm vor Heuristik). Der Clamp ist die einzige Stelle, an der die unkonditionale Grenze garantiert greift — unabhängig von MRT-, Effizienz- oder Override-Mathematik (G18). Die Aussparung im Kühlbetrieb verhindert, dass der Heiz-Überhitzungsdeckel das EN-Kühlband (Kat. III bis 27 °C) fälschlich beschneidet.

## Konsequenzen
**Positiv:** harte, sichtbare Überhitzungs-/Frost-Grenze; manueller Override wird nachweisbar in den Norm-Korridor geklemmt; Kaltwand-MRT kann den Sollwert nicht mehr unbegrenzt hochtreiben. **Negativ/Offen:** (a) GEG §61 (Einzelraumregelung) ist eine *Fähigkeits*-Anforderung, die Poise inhärent erfüllt — kein numerischer Grenzwert; (b) **KNX-Expose der Norm-Werte** (Programmstrukturplan) bleibt Phase-5-/ADR-0019-optional, hier nicht umgesetzt; (c) Cap/Floor sind feste Norm-Konstanten — bei Bedarf später konfigurierbar.

Damit ist **Phase 1 (Komfort-Moat) vollständig**.
