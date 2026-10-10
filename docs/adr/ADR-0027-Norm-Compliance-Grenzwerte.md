# ADR-0027: Norm-Compliance — unkonditionale Sollwert-Grenzen (ASR A3.5)

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-20, Nachtrag N1 2026-10-10 (korrigiert v0.196.1) · **Bezug:** Charta G1/G18, K4/K7 (Konflikt-Analyse), Programmstrukturplan (`norm_compliance`), ADR-0023 (Dual-Setpoint), Phase 1 · **Verifizierung:** ASR A3.5 (Raumtemperatur); Coordinator-Code

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

## Nachtrag N1 (2026-10-10, v0.196.0): Geltungsbereich der ASR A3.5 richtiggestellt

**Befund (Norm-Review 2026-10-10):** §2 und die Begründung nennen die ASR A3.5 „die einschlägige Norm" für die obere Raumtemperatur in „Wohn-/Arbeitsräumen". Das ist zweifach ungenau: Die ASR A3.5 konkretisiert die Arbeitsstättenverordnung und gilt **nur für Arbeitsstätten**, nicht für Wohnungen; und 26 °C ist dort die **Schwelle für Maßnahmen gegen sommerliche Hitze** („soll nicht überschreiten", gestaffelt bei 26/30/35 °C), kein Höchstwert für einen Heizsollwert.

**Entscheidung:** Der Deckel `ASR_MAX_ROOM_C = 26 °C` bleibt unverändert — als **Plausibilitäts- und Sicherheitsgrenze** für den Heiz-Luftsollwert (G18), die in Wohnräumen wie in Büros sinnvoll ist. **Korrektur (Review 2026-10-10, v0.196.1):** Er liegt *operativ* über allen EN-Heizobergrenzen, auch der Wohnzeile 25 °C aus ADR-0023 N1 — er wirkt aber auf den **Luft**-Sollwert. Bei kalter Hülle liegt der Luftwert über dem operativen Ziel (virtuelles MRT, ADR-0017 N1; bei −5 °C außen gilt `L = (op + 0,2) / 0,96`): 25 °C operativ brauchen dort 26,25 °C Luft, der Deckel bindet und erreicht werden nur ≈ 24,8 °C operativ. Das ist gewollt — der Deckel ist eine Sicherheitsgrenze, kein Komfortziel —, betrifft nur Wohnzonen mit Komfortwert nahe 25 °C bei Frost und wird als `norm_binding = norm_cap` sichtbar. Seine Begründung ist G18 (harte, nicht übersteuerbare Grenze gegen MRT-/Override-Mathematik), die ASR A3.5 ist die Herkunft des Zahlenwerts, nicht seine Rechtsgrundlage.

**Bewusstes Nicht-Ziel:** die Mindest-Lufttemperaturen der ASR A3.5 (z. B. 20 °C bei sitzender, leichter Tätigkeit). Sie gelten nur gewerblich; Poise prüft sie nicht. Wer Poise in einer Arbeitsstätte einsetzt, wählt Kategorie und Basis entsprechend.
