# ADR-0066: Feuchte-Achse — Trockenheits-Bewertung, Lüftungs-Empfehlung, schimmelsichere Feuchte-Obergrenze

**Status:** In Arbeit (60 %) · **Wirkung:** Live-D · **Datum:** 2026-07-26 · **Bezug:** ADR-0062 (Schimmelboden), ADR-0048 (Monitoring vs. Control), ADR-0049 (Ampel), ADR-0050 (Dry-Pfad), ADR-0041 (Fenster), ADR-0058 (Presence), ADR-0016 (Attribut-Vertrag), ADR-0012 (Redaction) · **Grundlage:** [Designplan 2026-07-25](../design/2026-07-Feuchte-Achse-Designplan.md) + [Recherche](../research/2026-07-Feuchte-Steuerung-und-Lueftungshinweise.md) + [Implementierungsplan](../design/2026-07-Feuchte-Achse-Implementierungsplan.md)

## Entscheidung

Drei additive, **nie regelnde** Fähigkeiten (alle Entwurfsentscheidungen des Designplans §12 gelten unverändert; dieser ADR fixiert sie):

1. **A — Trockenheit absolut bewerten:** `psychrometrics.absolute_humidity` (g/m³, ρ_v = p_v/(R_v·T)); Regelgröße bleibt g/kg. Untere Ampel-Grenzen `[5,0, 7,0] g/m³` (temperaturrobuste Umschreibung der heutigen 30/40 % RH bei 20 °C, Shaman/Kohn · Kudo/Iwasaki); die 9/12-g/m³-Zahlen des Anlassartikels sind abgelehnt.
2. **B — Lüftungs-Rat:** pures `comfort/ventilation.py::ventilation_advise` — Präzedenz `mold_risk` (am **~48-h-EWMA der Oberflächen-RH**, Marge 5 pp; Eskalation `alert` bei `mold_floor_binding`/`mold_capped`) > `too_dry`-Veto (≤ 7 g/m³) > `moisture_out` (Δ ≥ 3,0/1,5 g/m³ Hysterese, Raum > 8,7 g/m³ = DIN-4108-2-Referenzklima) > `co2` (≥ 1000 ppm, inert bis ADR-0049-Backend) > `close` (Anlass entfallen / thermischer Boden) > `idle`. Komfort-Regeln belegungs-gegatet, Gebäudeschutz nie (ADR-0050-Trennung). Jede Feuchte-Regel verlangt trockenere Außenluft; ohne Außenquelle still `no_data`. Außenfeuchte-Leiter: Weather-`humidity`-Attribut (Stufe 2, null Zusatzconfig); dedizierter Sensor = Inkrement 3.
3. **C — `mold.max_safe_rh`:** die Schimmelgleichung nach RH aufgelöst — die Obergrenze, die einem fremden Befeuchter fehlt; `fabric_conflict`, wenn sie unter dem Trockenheitsboden liegt (Bauteil-, kein Regelproblem). Round-Trip-invariant zur Mindest-Lufttemperatur.

**Naht:** ausschließlich `compose_climate_band` (pure Komposition); mold_min/mold_capped werden dort mit derselben puren Funktion + denselben Eingängen wie im Floors-Stage **re-berechnet** → per Konstruktion der Diagnosewert, nie der fenster-unterdrückte Schreibwert (Design B.2). Latch + EWMA persistiert (`vent_active`, `surface_rh_mean`; state/codec, additiv zum v1-Store). Neue Attribute: `abs_humidity_gm3/-_out_gm3`, `surface_rh/-_mean`, `mold_capped` (B.0-Bestandslücke geschlossen), `rh_max_safe`, `abs_max_safe`, `fabric_conflict`, `vent_action/-_reason/-_level/-_delta_gm3`.

**Abweichung vom Design (dokumentiert):** `RunningMeanTracker` (tagesbasiert) passt nicht auf ein 48-h-Signal → dt-bewusstes `ewma_step` in `ventilation.py`, gleiches Persistenzmuster, `running_mean.py` unangetastet. τ = 48 h ist **Arbeitswert/Kalibrierziel, nicht normativ** (§12.2-Warnung übernommen).

## Umsetzungsstand

**Inkrement 1 (v0.180.0):** A + C vollständig; B ohne Kosten/Emission; Naht, Attribute, Persistenz, Guard-Test (Rat erreicht nie `humidity_decide`/`dual_setpoint`/Solver/`tick_resolve`/`arbitration`), 12-g/kg-Rollen-Kommentar (Design A.4). **Offen:** Inkr. 2 Card (untere Lampen-Seite g/m³ + Vent-Chip → dann Nachträge ADR-0049 §5/0057) · Inkr. 3 Emissions-Rand (`persistent_notification` opt-in + Bus-Event + Diagnose-Entität → Nachträge 0016/0012) + Außen-RH-Sensor-Feld · Inkr. 4 Kosten (`vent_cost_*`) + τ-Kalibrierung an Felddaten.

## Konsequenzen

ADR-0048 §2 präzisiert: der sichtbare, begründete Lüftungs-Nudge ist der erlaubte Hinweis-Pfad; es entsteht kein Kommando (kein `fan`, kein `humidifier`, `Axis.VENTILATION` bleibt tot). Kein Luftwechselraten-Versprechen („N Minuten lüften" bleibt verboten). Degradation: ohne Sensoren still inaktiv, Anzeige zeigt im Zweifel nichts statt Falsches.
