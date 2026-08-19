# ADR-0066: Feuchte-Achse — Trockenheits-Bewertung, Lüftungs-Empfehlung, schimmelsichere Feuchte-Obergrenze

**Status:** In Arbeit (90 %) · **Wirkung:** Live-D · **Datum:** 2026-07-26 · **Bezug:** ADR-0062 (Schimmelboden), ADR-0048 (Monitoring vs. Control), ADR-0049 (Ampel), ADR-0050 (Dry-Pfad), ADR-0041 (Fenster), ADR-0058 (Presence), ADR-0016 (Attribut-Vertrag), ADR-0012 (Redaction) · **Grundlage:** [Designplan 2026-07-25](../design/2026-07-Feuchte-Achse-Designplan.md) + [Recherche](../research/2026-07-Feuchte-Steuerung-und-Lueftungshinweise.md) + [Implementierungsplan](../design/2026-07-Feuchte-Achse-Implementierungsplan.md)

## Entscheidung

Drei additive, **nie regelnde** Fähigkeiten (alle Entwurfsentscheidungen des Designplans §12 gelten unverändert; dieser ADR fixiert sie):

1. **A — Trockenheit absolut bewerten:** `psychrometrics.absolute_humidity` (g/m³, ρ_v = p_v/(R_v·T)); Regelgröße bleibt g/kg. Untere Ampel-Grenzen `[5,0, 7,0] g/m³` (temperaturrobuste Umschreibung der heutigen 30/40 % RH bei 20 °C, Shaman/Kohn · Kudo/Iwasaki); die 9/12-g/m³-Zahlen des Anlassartikels sind abgelehnt.
2. **B — Lüftungs-Rat:** pures `comfort/ventilation.py::ventilation_advise` — Präzedenz `mold_risk` (am **~48-h-EWMA der Oberflächen-RH**, Marge 5 pp; Eskalation `alert` bei `mold_floor_binding`/`mold_capped`) > `too_dry`-Veto (≤ 7 g/m³) > `moisture_out` (Δ ≥ 3,0/1,5 g/m³ Hysterese, Raum > 8,7 g/m³ = DIN-4108-2-Referenzklima) > `co2` (≥ 1000 ppm, inert bis ADR-0049-Backend) > `close` (Anlass entfallen / thermischer Boden) > `idle`. Komfort-Regeln belegungs-gegatet, Gebäudeschutz nie (ADR-0050-Trennung). Jede Feuchte-Regel verlangt trockenere Außenluft; ohne Außenquelle still `no_data`. Außenfeuchte-Leiter: Weather-`humidity`-Attribut (Stufe 2, null Zusatzconfig); dedizierter Sensor = Inkrement 3.
3. **C — `mold.max_safe_rh`:** die Schimmelgleichung nach RH aufgelöst — die Obergrenze, die einem fremden Befeuchter fehlt; `fabric_conflict`, wenn sie unter dem Trockenheitsboden liegt (Bauteil-, kein Regelproblem). Round-Trip-invariant zur Mindest-Lufttemperatur.

**Naht:** ausschließlich `compose_climate_band` (pure Komposition); mold_min/mold_capped werden dort mit derselben puren Funktion + denselben Eingängen wie im Floors-Stage **re-berechnet** → per Konstruktion der Diagnosewert, nie der fenster-unterdrückte Schreibwert (Design B.2). Latch + EWMA persistiert (`vent_active`, `surface_rh_mean`; state/codec, additiv zum v1-Store). Neue Attribute: `abs_humidity_gm3/-_out_gm3`, `surface_rh/-_mean`, `mold_capped` (B.0-Bestandslücke geschlossen), `rh_max_safe`, `abs_max_safe`, `fabric_conflict`, `vent_action/-_reason/-_level/-_delta_gm3`.

**Abweichung vom Design (dokumentiert):** `RunningMeanTracker` (tagesbasiert) passt nicht auf ein 48-h-Signal → dt-bewusstes `ewma_step` in `ventilation.py`, gleiches Persistenzmuster, `running_mean.py` unangetastet. τ = 48 h ist **Arbeitswert/Kalibrierziel, nicht normativ** (§12.2-Warnung übernommen).

## Umsetzungsstand

**Inkrement 1 (v0.180.0):** A + C vollständig; B ohne Kosten/Emission; Naht, Attribute, Persistenz, Guard-Test (Rat erreicht nie `humidity_decide`/`dual_setpoint`/Solver/`tick_resolve`/`arbitration`), 12-g/kg-Rollen-Kommentar (Design A.4). Live-verifiziert (Home-Deploy, Bad-Zone: Werte-Kreuzprobe + korrekter `mold_risk`-Alert).

**Inkrement 2 (v0.181.0):** Card — Feuchte-Lampe geteilt: Trocken-Seite auf `abs_humidity_gm3` gegen `[5,0, 7,0] g/m³` (`abs_humidity_floors` YAML-konfigurierbar), stiller RH-Fallback ohne Absolutwert; g/m³ in `title`/`aria-label`; **Lüftungs-Rat-Chip** (abgeleitet aus `vent_action == "open"` — v0.181.1-Fix, `vent_advice_active` ist kein Entity-Attribut; Grund-i18n de/en, alert-Rand bei `vent_level=alert`), mit dem `humidity`-Element gegated. Trace v2 um die Achse ergänzt (defaulted, kein Versions-Bump): `abs_humidity_gm3/-_out_gm3`, `surface_rh_mean`, `vent_action/-_reason`. Nachträge ADR-0049 §5 + ADR-0057 geschrieben.

**Inkrement 3 (v0.182.0):** B.5 Emissions-Rand — pure `advice_transition` (Kante auf dem ACTION-Token: Event bei jeder Änderung, Notification nur für die „open"-Episode; Kaltstart still nach `idle`, re-announced eine laufende Episode nach Neustart) + Glue-Zustellung im Orchestrator (eigene Fehlergrenze, bricht nie den Tick): Bus-Event `poise_ventilation_advice` `{zone, entry_id, action, reason, delta_gm3}` + selbstlöschende `persistent_notification` (opt-in `vent_notify`, stabile ID `poise_vent_<entry_id>`, englischer Text — Notifications haben keine i18n-Schiene, der stabile Token reist im Event). Diagnose-Entität `sensor.<zone>_vent_advice` (ENUM idle/open/close/discourage, diagnostic, default-disabled; bewusst OHNE die schnellen Δ-/Kosten-Attribute, Design §6). Außen-RH-Leiter **Stufe 1**: dediziertes Sensor-Feld `outdoor_humidity_sensor` (Setup + Reconfigure, device_class humidity) schlägt das Weather-Attribut; REDACT_KEYS erweitert. Transientes `vent_last_action` (nicht persistiert, POST_RELOCATION). **Offen:** Inkr. 4 Kosten (`vent_cost_*`) + τ-Kalibrierung an Felddaten.

## Konsequenzen

ADR-0048 §2 präzisiert: der sichtbare, begründete Lüftungs-Nudge ist der erlaubte Hinweis-Pfad; es entsteht kein Kommando (kein `fan`, kein `humidifier`, `Axis.VENTILATION` bleibt tot). Kein Luftwechselraten-Versprechen („N Minuten lüften" bleibt verboten). Degradation: ohne Sensoren still inaktiv, Anzeige zeigt im Zweifel nichts statt Falsches.

## Nachtrag N1 (2026-08-10, v0.188.0): Regel 3t — Freikühl-Lüften (`heat_out`)

**Anlass (Maintainer-Feldbedarf):** Im Sommer heizen sich Zonen passiv auf; wer weder kühlen noch Luft bewegen kann, hat nur das Fenster — der Rat existierte aber nur für Feuchte/CO₂. Die Tabelle B.2 erhält eine thermische Schwester-Regel **3t** mit vier Wächtern, damit sie nie falsch rät:

1. **Fähigkeits-Gate:** nur Zonen ohne `cool` UND ohne Lüfterstufen (aus den beworbenen Geräte-Flächen `hvac_modes`/`fan_modes` an der Shadow-Naht) — eine AC-/Fan-Zone bekommt den Rat nie (Fenster offen + Verdichter wäre kontraproduktiv; die Fan-Zone hat Tier 3).
2. **Thermischer Gewinn mit asymmetrischer Hysterese:** Raum über der effektiven Kühlkante UND außen ≥ `heat_out_dt_on_k` (2,0 K) kühler öffnet; die Episode hält (`prev_heat_out`-Anker, transient in `HumidityRuntime.vent_reason`) bis der Vorsprung unter `heat_out_dt_off_k` (1,0 K) fällt oder der Raum die Kante erreicht — dann rät `cooled_off` zum Schließen. Restart mitten in der Episode re-appliziert einmalig die Eintrittsschwelle (bewusst nicht persistiert).
3. **Feuchte-Wächter:** Außenluft darf höchstens `heat_out_humid_guard_gm3` (1,0 g/m³) feuchter sein als innen — kein Tausch Wärme gegen Schwüle; sonst still `no_gain`.
4. **Nicht belegungs-gebunden** (bewusster Unterschied zu Regel 3/4): Nachtauskühlung ist im leeren Raum am wertvollsten; Notification bleibt Opt-in, das `poise_ventilation_advice`-Event feuert wie bei jeder Ratänderung (Andockpunkt für Fensterantriebe/Rollos — Aktuierung bleibt außerhalb, ADR-0048).

**Präzedenz:** Schimmel (1) und Trockenheits-Veto (2) und Winter-`thermal_floor` (5a) stehen über 3t; ein noch gültiger Feuchte-/CO₂-Grund hält das Fenster offen, bevor `cooled_off` schließt (3t-close sitzt NACH 3/4). Vokabular +2 (`heat_out`, `cooled_off`); Card-Chip „Lüften (draußen kühler)". Pure Tests: 5 neue Fälle (Gate, Hysterese/Close, Schwüle-Veto, Präzedenzen) in `tests/test_feuchte_achse.py`.

## Nachtrag N2 (2026-08-19, v0.192.0): Schimmel-Wächter für Regel 3t + vorgezogener Schließ-Rat `mold_guard` — umgesetzt

**Anlass (Live-Fund Küche, 2026-08-19):** Fenster offen (Sensor), T_rm auf 17,1 °C gefallen, Schimmel-Boden 22,1 °C bindet Sollwert UND effektive Kühlkante (`norm_binding = norm_floor`, Anzeige-Band kollabiert auf einen Punkt). Regel 3t nutzte die **gebundene** Kante als „zu warm"-Referenz und riet `heat_out` — also den Raum per Fenster exakt auf den Schimmel-Boden herunterzulüften — während die Oberflächen-RH (77 %) die sichere Grenze (`rh_max_safe` 69,6 %) bereits überschritt. Die N1-Präzedenz „Schimmel (1) > 3t" wirkt nur auf die *Rat-Auswahl* (Regel 1 hätte selbst feuern müssen, ihr 48-h-EWMA ist träge); sie verhindert nicht, dass 3t mit einer schutz-gebundenen Kante argumentiert. Regel 5a schließt erst, wenn die *Luft* den Boden erreicht — zu spät, wenn die *Wände* schon drüber sind. Die Außenluft war absolut trockener (12,2 vs. 13,8 g/m³): der Treiber des Risikos ist die Auskühlung der Oberflächen durch das offene Fenster, nicht eingetragener Wasserdampf.

**Entscheidungen:**

1. **3t-Wächter Nr. 5 (Schutz-Bindung):** `heat_out` rät nie, wenn die effektive Kühlkante von einem Schutz-Boden gebunden ist (`mold_floor_binding`/`norm_floor`) ODER die geglättete Oberflächen-RH innerhalb einer Marge (2 pp) an `rh_max_safe` liegt. Begründung: Eine schutz-gebundene Kante ist kein Komfortziel — auf sie herunterzulüften arbeitet dem Schutz entgegen.
2. **Neuer Schließ-Rat `close`/`mold_guard` (level `warn`):** Fenster offen ∧ Boden gebunden ∧ Oberflächen-RH über der sicheren Grenze → aktiver Rat „Fenster schließen (Schimmelschutz)" — VOR Erreichen des Luft-Bodens (Vorziehung gegenüber 5a). Nicht belegungs-gebunden (Gebäudeschutz). Kanäle wie gehabt: Chip, `poise_ventilation_advice`, Opt-in-Notification.
3. **Präzedenz:** `mold_guard` sitzt zwischen Regel 1 (mold_risk-open, gewinnt bei trockener Außenluft und akutem EWMA-Alarm) und 5a; Vokabular +1 (`mold_guard`), Card-i18n en/de.

**Marktbeleg:** BT/VTherm kennen nur Fenster-*Erkennung* (Heizstopp), keine Empfehlungen; ecobee alarmiert bei offenem Fenster, Honeywell drosselt Feuchte per „Window Protection"; in der DACH-HA-Community sind Innen/Außen-g/m³-Vergleich und außentemperaturabhängige „Fenster schließen"-Reminder etablierte Erwartung (simon42/heise, Blueprint-Nachfrage). Ein regelbasierter, begründeter Schließ-Rat ist im HA-Thermostat-Feld Alleinstellung.

**Wirkung.** Geänderter Rat in der Bindungs-Lage (close statt open); Regelung/Writes unverändert (Rat bleibt Anzeige/Event, ADR-0048).

**Umsetzung (v0.192.0)** — drei Präzisierungen gegenüber dem Text oben, alle im [Plan](../Konzepte/2026-08-19_Plan_ADR-0049-N1_und_ADR-0066-N2.md) begründet:

1. **Wächter 5 misst die Kante, nicht die Bindung des Schreibwerts.** `cool_edge_protected := mold_min >= eff_cool - 0,05 K` an der Naht (`diagnostics/shadows.py`). `mold_floor_binding`/`norm_floor` sagen nur, dass der Boden den **Sollwert** hob — der Winter-Normalfall (Boden 22,1 · Kante 25,0), in dem Freikühl-Lüften völlig harmlos ist. Die 0,05 K sind eine halbe Anzeige-Stufe: die Kante reist auf dem 0,1-Raster, der Boden ist stetig.
2. **Zwei Feuchte-Signale, bewusst verschieden.** Wächter 5 nimmt die **geglättete** Oberflächen-RH (Marge 2 pp, `mold_guard_margin_pp`), der Rat `mold_guard` den **Momentanwert** — der 48-h-EWMA war ja gerade zu träge; ihn hier noch einmal zu befragen wäre derselbe Fehler.
3. **Präzedenz-Platz:** direkt nach Regel 1, also **vor** dem Trockenheits-Veto. `mold_guard` ist Gebäudeschutz und rät schließen; `too_dry` rät nur ab.

Kanäle wie gehabt heißt alle drei: der Chip erscheint jetzt auch für diesen **einen** Schließ-Rat (pure `ventChip` in `monitoring.ts`; die harmlosen Entwarnungen bleiben stumm), und die Emissionskante kennt den Grund — Schlüssel ist `(action, reason)` für Gründe mit eigener Episode (`NOTIFY_REASONS`), sodass `target_reached → mold_guard` meldet, `target_reached → cooled_off` aber still bleibt; ohne die neuen Argumente ist `advice_transition` bit-identisch zu vorher. Transientes `vent_last_reason` als zweite Hälfte der Kante. Nachweise: 7 neue pure Fälle (inkl. Nicht-Vakuitäts-Kontrolle, die den alten `heat_out`-Fehlrat reproduziert), ein Naht-Test über `compose_climate_band` und **die erste Glue-Abdeckung der Emissionsschiene überhaupt** (Zwei-Tick-Szenario — ein Ein-Tick-Test kann den Fall nicht zeigen, weil der EWMA beim Kaltstart mit dem Momentanwert startet und dann Regel 1 gewinnt).

**Bekannte Grenze:** ohne Außenfeuchte-Quelle bleibt die ganze Achse still (`no_data`-Tor, Design §9) — auch `mold_guard`, obwohl er weder `w_out` noch trockenere Außenluft braucht. Das Tor zu öffnen wäre eine Verhaltensausweitung und steht bewusst nicht in diesem Nachtrag.
