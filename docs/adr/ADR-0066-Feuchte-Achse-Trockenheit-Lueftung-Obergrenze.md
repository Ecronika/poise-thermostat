# ADR-0066: Feuchte-Achse — Trockenheits-Bewertung, Lüftungs-Empfehlung, schimmelsichere Feuchte-Obergrenze

**Status:** In Arbeit (90 %) · **Wirkung:** Live-D · **Datum:** 2026-07-26 · **Bezug:** ADR-0062 (Schimmelboden), ADR-0071 (Dosismodell — löst ADR-0062 ab; Quelle von `rh_max_safe`, siehe N3/N4.4), ADR-0048 (Monitoring vs. Control), ADR-0049 (Ampel), ADR-0050 (Dry-Pfad), ADR-0041 (Fenster), ADR-0058 (Presence), ADR-0016 (Attribut-Vertrag), ADR-0012 (Redaction) · **Grundlage:** [Designplan 2026-07-25](../design/2026-07-Feuchte-Achse-Designplan.md) + [Recherche](../research/2026-07-Feuchte-Steuerung-und-Lueftungshinweise.md) + [Implementierungsplan](../design/2026-07-Feuchte-Achse-Implementierungsplan.md)

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

## Nachtrag N3 (2026-09-11): `mold_guard` liest die Anforderung, nicht den durchgreifenden Boden — umgesetzt

**Anlass (Regression durch ADR-0071, im CI gefunden, nicht im Feld):** N2 formulierte den Schließ-Rat als „Fenster offen ∧ **Boden gebunden** ∧ Oberflächen-RH über der sicheren Grenze". Solange der Schimmelboden die Umkehrung des Momentanwerts war, waren „ein Boden greift durch" und „die Oberflächen brauchen es wärmer als die Kühlkante" **dieselbe Aussage** — die eine folgte aus der anderen, ohne Zeitverzug. ADR-0071 hat diese Gleichsetzung aufgelöst: das VTT-Dosismodell lässt den Boden erst nach gereiftem Index oder 48 h Dauernässe durchgreifen. Damit war `cool_edge_protected` in der N2-Regel kein Zustandsbeleg mehr, sondern ein **Wochen-Gate** vor einer Empfehlung. Der Glue-Test der Emissionsschiene fiel entsprechend um: Oberflächen-RH 82,2 % gegen eine Decke von 58,4 % — und der Rat lautete `open`/`heat_out`, also genau der Fehlrat, dessen Beseitigung der Anlass von N2 war.

**Entscheidung:** Die Regel `mold_guard` bekommt einen **eigenen, dosis-freien Eingang** `surface_needs_warmer` — „die zum Schutz der Oberflächen nötige Lufttemperatur hat die effektive Kühlkante erreicht" (dieselbe Vergleichsform wie `cool_edge_protected`, dieselbe Toleranz 0,05 K, aber auf dem **ungegateten** psychrometrischen Ergebnis von `mould_risk.required_air_temperature`). Wächter 5 bleibt unverändert am **durchgreifenden** Boden (`cool_edge_protected`).

**Die Grenze, an der hier getrennt wird, ist die zwischen Rat und Handlung.** Heizen ist eine Handlung: sie kostet Geld, übergeht den Nutzerwunsch und muss sich die Berechtigung über die Dosis verdienen — das ist die ganze Pointe von ADR-0071. Einen Rat zu geben kostet nichts und ist reversibel; er muss in der Geschwindigkeit des Risikos reagieren, nicht in der des Nachweises. Das ist dieselbe Trennlinie, die schon die Entscheidung „Lüften kann nur empfohlen, nie bevorzugt werden" trägt (ADR-0048).

**Zum naheliegenden Fehlauslöser** (Bad nach dem Duschen: Oberfläche akut über der Grenze, Fenster offen, draußen trocken-kalt): Der wird nicht von dieser Bedingung gefangen, sondern von der **Präzedenz**. Regel 1 (`mold_risk`, „öffnen") sitzt über `mold_guard` und feuert bei trockenerer Außenluft und akutem 48-h-Mittel zuerst. Der Küchenfall von N2 erreicht `mold_guard` gerade deshalb, weil sein Mittel noch unter der Rule-1-Linie liegt, während die Wände bereits drüber sind. Diese Konstruktion ist unverändert; N3 ändert nur, welcher der beiden Eingänge der Regel die Dosis passieren muss.

**Wirkung.** Der Rat greift jetzt auch auf einer frischen Installation und nach jedem Zonen-Reset, statt erst nach der Reifezeit des Index. Regelung und Writes unverändert (ADR-0048). `surface_needs_warmer` hat den Default `False`, alte Aufrufstellen sind bit-identisch.

**Nachweise.** `tests/test_feuchte_achse.py`: der neue Fall `test_mold_guard_reads_the_requirement_not_the_enforced_floor` (Rat greift ohne durchgreifenden Boden; Umkehrprobe, dass die blanke Anforderung Wächter 5 **nicht** auslöst), die angepasste Notwendigkeitsprüfung und die unveränderte Nicht-Vakuitäts-Kontrolle. `tests/test_phase8_shadows.py`: der Küchenfall zusätzlich mit `mould_engaged=False` an der Naht. `tests/integration/test_vent_advice_glue.py` läuft unverändert wieder grün — das war der Fund.

## Nachtrag N4 (2026-09-13, v0.194.2): Außenfeuchte nur aus gemessenen Außenwerten; Datentor regelindividuell; `too_dry` schließt — umgesetzt

**Anlass (externes Review, verifiziert in [docs/reviews/2026-09-13](../reviews/2026-09-13-externes-review-lueftungsempfehlung-verifikation.md)):** Zwei Befunde des Reviews sind echte, undokumentierte Defekte, und sie hängen zusammen — der erste verschlimmert den zweiten. Ein dritter ist ein Drei-Zeilen-Fehler im Verb. Ein vierter wurde gebaut und nach dem Bau **verworfen**; er steht hier, weil eine stille Verwerfung dieselbe Frage in einem Jahr wieder auslöst.

### N4.1 — Die Feuchte-Achse rechnet nur mit einer **gemessenen** Außentemperatur

`control/pipeline_prepare.py` bildet seit jeher einen Ersatzwert: `t_out_eff = t_out ?? t_rm ?? 5,0 °C`. Für die thermische Kette ist das dokumentiert und konservativ — ein zu kalt angenommenes Außen führt zu wärmeren Oberflächen-Anforderungen, also in Richtung Schutz. Für die Feuchte ist derselbe Wert **falsch**, weil `rh_out` eine eigene, aktuelle Quelle ist (dedizierter Sensor vor Weather-Attribut, Inkrement 3): fällt nur der Temperaturkanal aus, wird die **aktuelle** Außen-RH mit einer **gemittelten oder erfundenen** Temperatur zu einem Luftzustand verrechnet, den es nirgends gibt.

Die Fehlerrichtung ist die ungünstige. T_rm liegt im Alltag unter der aktuellen Außentemperatur, der 5-°C-Fallback fast immer; `w_out` fällt damit zu niedrig aus und `delta = w_in − w_out` zu hoch. Gerechnet (Magnus): außen 18 °C / 80 % ergibt real 12,26 g/m³ und gegen einen Raum 22 °C / 55 % (10,65 g/m³) ein `delta` von **−1,61** — draußen ist es feuchter. Mit T_rm = 10 °C werden daraus 7,51 g/m³ und `delta` = **+3,14**, mit dem Fallback 5,43 g/m³ und **+5,22**. Beide überschreiten die 3,0-Eintrittsschwelle: Poise rät zum Lüften **gegen** feuchtere Außenluft, also genau zu dem Feuchteeintrag, den Regel 3 verhindern soll. Das Vorzeichen kippt vollständig.

**Entscheidung:** `IngestResult` trägt die **gemessene** Außentemperatur als zweites, eigenes Feld `t_out_measured` neben `t_out_eff` (Default `None`, alte Aufrufstellen bit-identisch). `compose_climate_band` bildet `w_out` ausschließlich daraus; fehlt sie, ist `w_out` `None` und die Feuchteregeln schweigen. Die **Schimmelkette an derselben Naht bleibt bei `t_out_eff`** — dort ist der Ersatzwert eine thermische Randbedingung und irrt in Richtung kälterer Oberflächen, also in Richtung Schutz. Zwei Außentemperaturen nebeneinander sind daher kein Versehen, sondern die Entscheidung: der Ersatzwert dort, wo sein Irrtum konservativ ist, der Messwert dort, wo ein Paar aus zwei Quellen gebildet wird.

### N4.2 — Das `no_data`-Tor gilt **pro Regel**, nicht global

Bis v0.194.1 begann `ventilation_advise` mit `if w_in is None or w_out is None: return no_data`. Das erschlug den Gebäudeschutz mit: Regel 1b (`mold_guard`), deren eigener Kommentar seit N2 sagt, sie brauche **bewusst keine** trockenere Außenluft, und Regel 5a (`thermal_floor`), die rein thermisch ist. ADR-0050 trennt Gebäudeschutz von Komfort ausdrücklich dadurch, dass der Schutz **nie** gegatet wird — das muss das Datentor einschließen. N2 hat diese Lücke unter „Bekannte Grenze" bereits benannt und ihre Schließung bewusst vertagt; N4.1 macht sie tragend: `w_out` ist nun häufiger `None`, ein globales Tor würde den Schimmel-Schließrat also genau dann verstummen lassen, wenn der Außensensor das ist, was ausgefallen ist.

**Entscheidung:** ein gemeinsames `have_moisture`, und jede Regel nennt ihre eigene Voraussetzung — geschrieben als explizite `is not None`-Prüfung dort, wo danach gerechnet wird (`delta is not None` **ist** „beide Seiten da"): ein `bool` trägt keine Typverengung, und `mypy --strict` sieht die Subtraktion sonst nicht als sicher an. Feuchteregeln (1, 2, 3, 3t-Feuchtewächter, 5b) tragen `have_moisture`; `mold_guard`, `thermal_floor`, CO₂ und der `cooled_off`-Schluss tragen es nicht. Regel 3t bleibt **mit** Tor: ihr Schwüle-Wächter ist ohne Außenfeuchte nicht auswertbar, und Freikühlen ist Komfort — ohne Wächter schweigt sie, statt zu raten. Der Endzweig unterscheidet jetzt ehrlich: `no_gain` heißt „die Achse hatte Daten und sagt nein", `no_data` heißt „sie hatte keine". Das Vokabular wächst nicht.

### N4.3 — `too_dry` schließt ein offenes Fenster, statt davon abzuraten

Regel 2 lieferte immer `discourage`. Steht das Fenster bereits offen, ist „lieber nicht öffnen" das falsche Verb; die handlungsfähige Empfehlung ist „schließen". Gleiche Regel, gleiche Präzedenz, gleicher Grund-Token — nur die Aktion folgt dem Fensterzustand, genau wie bei 1b und 5a. Der Chip zeigt diesen Schließrat nicht (nur `NOTIFY_REASONS`, also `mold_guard`, hat eine eigene Episode); Event und Attribut tragen ihn.

### N4.4 — **Verworfen:** `mold_risk` auf `rh_max_safe` koppeln

Das Review sah eine Inkonsistenz darin, dass Regel 1 weiter gegen das feste 80 %-Limit prüft, während N3 den **Guard** auf die dynamische Decke `rh_max_safe` (ADR-0071) umgestellt hat; die Verifikation hat das als Priorität 4 übernommen. Umgesetzt, und der N2-Regressionsfall hat es gefangen: Der Live-Tick Küche (48-h-Mittel 72 %, `rh_max_safe` 69,6 %) überschreitet 69,6 − 5 sofort, Regel 1 rät **`open`** — und Regel 1 sitzt über `mold_guard`. Damit wäre exakt der Fehlrat zurück, für dessen Beseitigung N2 existiert.

Der Grund ist kein Versehen im Code, sondern die Bedeutung der Variablen. Ein **niedriges** `rh_max_safe` bedeutet eine **kalte** Oberfläche — und eine kalte Oberfläche spricht fürs Schließen, nicht fürs Öffnen. Den Öffnen-Rat an diese Decke zu hängen lässt ihn dort am frühesten feuern, wo Öffnen schadet. Die beiden Regeln stellen bewusst **verschiedene** Fragen: Regel 1 fragt absolut („sind die Oberflächen nass, unabhängig davon, was diese Wand verträgt"), der Guard relativ („überschreitet sie, was diese Wand verträgt"). N3 hat den relativen Eingang dorthin gebracht, wo er hingehört; ihn zusätzlich in die absolute Regel zu ziehen wäre keine Vereinheitlichung, sondern ein Kategorienfehler. Festgenagelt durch `test_n4_mold_risk_keeps_the_fixed_limit_on_purpose`, damit der Vorschlag nicht stumm wiederkehrt; die Verifikation ist entsprechend korrigiert (Punkt 12, Priorität 4).

**Wirkung.** Geänderter Rat in drei Lagen (kein Fehl-`open` bei fehlender Außentemperatur; Gebäudeschutz bleibt bei fehlender Außenfeuchte hörbar; `close` statt `discourage` bei trockener Luft und offenem Fenster). Regelung, Writes und Schimmelboden unverändert — der Rat bleibt Anzeige/Event (ADR-0048); die Schimmelkette an der Naht rechnet weiter mit `t_out_eff`.

**Nachweise.** `tests/test_feuchte_achse.py`, fünf neue Fälle: `test_n4_building_protection_survives_a_missing_outdoor_humidity`, `test_n4_moisture_rules_stay_silent_without_both_sides`, `test_n4_too_dry_closes_an_open_window_instead_of_discouraging_it`, `test_n4_mold_risk_keeps_the_fixed_limit_on_purpose` (die Verwerfungs-Schranke aus N4.4), `test_n4_1_outdoor_humidity_needs_a_measured_temperature` (nagelt die Vorzeichen-Rechnung oben fest). `tests/test_phase1_tick_result.py`: der Feldvertrag um `t_out_measured` erweitert.

**Offen (aus der Verifikation, bewusst nicht in N4; die ersten beiden sind in N5 erledigt):** ~~8,7 g/m³ als alleinige Eintrittsschwelle driftet mit der Raumtemperatur (56,8 % rF bei 18 °C, 32,1 % bei 28 °C) — das braucht eine Entscheidung, keinen Fix~~ (N5.2); ~~`room_c` auf die operative Temperatur~~ (N5.1); Schließen nach Anlass über `prev_vent_reason`; g/kg als interne Rechengröße; ein Fähigkeitsmodell, das Umluft von Zuluft unterscheidet (HAs `fan_modes` kann das nicht); τ-Kalibrierung an Felddaten.

## Nachtrag N5 (2026-09-13, v0.194.3): operative Kante für das Freikühlen; relative Begleiter für die beiden absoluten Feuchtegrenzen — umgesetzt

**Anlass (Nachprüfung des externen Reviewers zu v0.194.2, verifiziert in [docs/reviews/2026-09-13 (Nachprüfung)](../reviews/2026-09-13-externes-review-lueftungsempfehlung-nachpruefung.md)):** Die N4-Korrekturen wurden bestätigt, die Verwerfung aus N4.4 nach erneuter Prüfung ebenfalls. Zwei der verbliebenen offenen Punkte sind jedoch klein genug für denselben Zyklus — und einer davon war in N4 als „offen" notiert, ohne dass die Schwere klar war.

### N5.1 — Regel 3t stellt zwei Fragen und braucht dafür zwei Temperaturen

`ventilation_advise` bekam bis v0.194.2 ein einziges `room_c` und benutzte es für beides:

1. **„Ist der Raum über der Komfortkante?"** — diese Kante ist `eff_cool`, und **jeder andere** Verbraucher von `eff_cool` in derselben Komposition vergleicht sie gegen `room_decide` (siehe `in_deadband` in `compose_climate_band`). Das ist die operative Temperatur, sobald das MRT-Modell läuft. Regel 3t verglich sie gegen die **Lufttemperatur**: bei warmen Bauteilen sagt der Komfortsolver „zu warm" (operativ 26,0 über einer Kante von 25,0), während 3t mit 24,5 < 25,0 gar keinen Kühlbedarf sieht.
2. **„Bringt Öffnen etwas?"** — das ist Luft gegen Luft. Ein Fenster tauscht Luft, keine Strahlung. Die operative Temperatur in die dT-Hysterese zu geben, schreibt der Außenluft den gesamten Strahlungsüberschuss gut — im Beispiel 1,5 K von 2,0 K Einschaltschwelle — und öffnet gegen einen Gewinn, den es nicht gibt.

**Entscheidung:** zwei Eingänge. `room_decide_c` für die Kantenfrage, `room_c` (Luft) für die Hysterese. `room_decide_c` hat den Default `None` und spiegelt dann `room_c`, also sind alte Aufrufstellen bit-identisch. Der Vorschlag der Nachprüfung, `room_c` pauschal durch `room_decide` zu ersetzen, hätte nur die Spiegelseite desselben Fehlers erzeugt; das ist der Grund, warum hier zwei Parameter stehen und nicht eine Ersetzung.

### N5.2 — Jede absolute Feuchtegrenze bekommt einen relativen Begleiter

Eine Grammzahl bedeutet bei jeder Raumtemperatur eine andere relative Feuchte. `8,7 g/m³` sind **56,8 % rF bei 18 °C**, aber nur **32,1 % bei 28 °C** — Poise konnte einem 28 °C warmen Raum mit 33 % rF (8,96 g/m³) das Lüften „wegen Feuchte" empfehlen. Das Trockenheits-Veto konnte das nicht fangen, weil seine eigene Grenze ebenfalls absolut ist: 7 g/m³ sind bei 28 °C nur 25,8 % rF.

Dazu kommt ein Einwand, der schwerer wiegt als die Drift selbst: **8,7 g/m³ ist das Referenz-Innenklima 20 °C/50 % der DIN 4108-2 — ein Bemessungsklima, nie eine Betriebsschwelle.** Es beschreibt, wogegen man ein Bauteil auslegt, nicht, wann man ein Fenster öffnet.

**Entscheidung:** beide Grenzen bekommen einen relativen Begleiter, und beide Begleiter sind **derselbe Punkt auf der anderen Achse** — es musste nichts neu kalibriert werden:

| Grenze | absolut | relativ | Verknüpfung |
|---|---|---|---|
| Feuchte-Eintritt (Regel 3) | `> 8,7 g/m³` | `>= 50 % rF` | **UND** |
| Trockenheits-Veto (Regel 2) | `<= 7,0 g/m³` | `<= 35 % rF` | **ODER** |

`8,7 g/m³` **sind** 50 % rF bei 20 °C: die beiden Bedingungen fallen im Referenzklima zusammen, und darunter bindet die absolute, darüber die relative. Das UND ist deshalb keine Verschärfung, sondern die temperaturrobuste Form derselben Linie. Das ODER beim Veto ist die Gegenrichtung: zu trocken ist ein Raum auf zwei Arten, und jede Art genügt.

**Warum 35 % und nicht die 40 %, die 7 g/m³ spiegeln würden:** Regel 2 sitzt **über** Regel 3t. Eine 40-%-Linie würde einem Sommerraum mit 26 °C/40 % (9,72 g/m³ — nach keinem Maßstab trocken) das Freikühlen verbieten, und das Veto würde still den Hitzetag-Rat kosten, für den 3t existiert. 35 % hält diesen Fall freikühlbar und fängt den wirklich trockenen Raum eine Stufe darunter. Der Wert liegt im Band 35–40 %, das die Nachprüfung genannt hat; festgehalten durch `test_n5_dryness_line_sits_at_35_so_summer_free_cooling_survives`.

`rh_pct` ist die Raumfeuchte, aus der `w_in_gm3` an der Naht ohnehin gerechnet wird — die beiden treffen immer gemeinsam ein, es kommt keine Datenquelle hinzu.

### N5.3 — Die N4.1-Invariante wird strukturell statt kommentiert

Regel 3t bekam weiter `t_out_eff`. Das war seit N4.1 **nachweislich** folgenlos: 3t verlangt `delta`, `delta` verlangt `w_out`, `w_out` verlangt `t_out_measured` — und wo die gesetzt ist, **ist** `t_out_eff` genau dieser Messwert, weil der Ersatzwert nur bei fehlender Messung entsteht. Statt das zu kommentieren, reicht die Naht jetzt `t_out_measured` direkt durch. Verhalten bit-identisch, aber eine spätere Änderung am Fallback kann diese Regel nicht mehr versehentlich erreichen.

### Nebenbefund aus der Umsetzung: ein Test-Helfer hat einen anderen verdeckt

Die N4-Fälle brachten einen zweiten `_advise`-Helfer in `tests/test_feuchte_achse.py` mit — gleicher Name, eigene Defaults. Auf Modulebene **verdeckt** die spätere Definition die frühere, also liefen sämtliche älteren Fälle der Datei gegen die N4-Defaults statt gegen ihre eigenen. Sichtbar wurde das erst, als N5 einem der beiden Bestände einen Schlüssel hinzufügte und vier unbeteiligte Tests fielen. Der Helfer heißt jetzt `_n4_advise`, und der Grund steht in seinem Docstring — die Fälle selbst sind unverändert.

**Wirkung.** Geänderter Rat in drei Lagen: Freikühlen wird bei warmen Bauteilen überhaupt erst geraten und bei zu kleinem Luftgewinn nicht mehr; der Feuchte-Rat schweigt im warmen, relativ trockenen Raum; das Trockenheits-Veto greift auch dort, wo die Grammzahl unauffällig ist. Regelung, Writes und Schimmelboden unverändert (ADR-0048).

**Nachweise.** `tests/test_feuchte_achse.py`: `test_n5_free_cooling_separates_the_comfort_edge_from_the_air_gain` (vier Fälle, darunter die Spiegelseite, die der pauschale Tausch gebrochen hätte), `test_n5_moisture_entry_needs_the_absolute_and_the_relative_line`, `test_n5_dryness_veto_takes_either_axis`, `test_n5_dryness_line_sits_at_35_so_summer_free_cooling_survives`. `tests/test_phase8_shadows.py`: `test_free_cooling_edge_is_judged_on_the_operative_temperature` an der Naht; der dortige Helfer spiegelt `room_decide` jetzt auf `room`, statt es bei 22,0 festzunageln — das war unsichtbar, bis Regel 3t den Wert las.

**Offen (unverändert, in dieser Reihenfolge):** `mold_risk` — Eintritt und „Fenster offen halten" trennen, damit der 48-h-EWMA nicht 10 bis 20 Stunden lang den Schließschutz überstimmt (nachgerechnet: 48·ln(25/20) = 10,7 h von 80 auf unter 75 %); ursachenspezifische Ausstiege über `prev_vent_reason` statt des generischen `target_reached` — die beiden gehören zusammen; g/kg als interne Rechengröße; ein Fähigkeitsmodell, das Umluft von Zuluft unterscheidet; τ-Kalibrierung an Felddaten; der Kommentar zu 8,7 g/m³ gegen die Normausgabe DIN 4108-2:2026-05.

## Nachtrag N6 (2026-09-14, v0.194.4): `mold_guard` tritt zurück, solange Lüften die Behandlung ist — umgesetzt

**Anlass (Feldbefund an der laufenden Anlage, [docs/reviews/2026-09-14](../reviews/2026-09-14-Feldbefund-Luftungsrat-kippt-am-Fensterkontakt.md)):** Der Rat kippte **im selben Moment, in dem das Fenster geöffnet wurde** — 04:03:24 Fenster auf, in derselben Sekunde `close`/`mold_guard`; 04:32:13 Fenster zu, in derselben Sekunde `open`/`moisture_out`; 04:33:51 wieder auf, wieder `close`. Der Rat war damit nicht befolgbar.

**Die Ursache ist keine fehlende Hysterese, sondern eine fehlende Rückkopplung.** `mold_guard` verlangt Fenster offen ∧ `surface_needs_warmer` ∧ Oberflächen-RH über der Decke. Die beiden physikalischen Bedingungen waren **schon bei geschlossenem Fenster** erfüllt (79,0 % gegen 62,8 %) — der einzige fensterabhängige Term der Regel *war der Kontakt selbst*, und 1b steht über Regel 3. Nichts in der Regel maß, was das Lüften bewirkt.

Dazu kam die Asymmetrie, die die externe Nachprüfung als Befund 2 benannt hatte: die Öffnen-Seite (Regel 1) liest ein **träges 48-h-Mittel gegen ein festes** 80-%-Limit (67,26 % — feuert nicht), die Schließen-Seite den **Momentanwert gegen eine dynamische** Decke (79,0 gegen 62,8 — feuert immer). Der Notausgang „draußen ist trockener, also lüften" war damit zu, während die Schließen-Regel dauernd offen stand.

### N6.1 — Die Regel widerspricht der eigenen laufenden Empfehlung nicht

**Entscheidung:** `mold_guard` schweigt, solange eine **Lüftungs-Episode läuft, die diese Achse selbst angeordnet hat** (letzter Rat `open` mit Grund `moisture_out` oder `mold_risk`) **und dieser Grund noch gültig ist** — es sei denn, ein Schutzboden greift durch (`cool_edge_protected`), denn dann zahlt das Bauteil bereits. Ein Fenster, das ohne Poises Zutun geöffnet wurde, und ein Fenster, das nach dem Ende der Episode offen bleibt, treffen den Wächter unverändert an.

**Ein Prädikat, an einer Stelle gerechnet.** Die Gültigkeit ist nicht nachgebaut, sondern **dieselbe** Bedingung, die Regel 3 auswertet: `moisture_reason_valid` wird oberhalb von Regel 1b einmal berechnet und von beiden gelesen. Das ist keine Kosmetik, sondern der Grund, warum der Rücktritt nicht mehr driften kann. Der erste Entwurf baute die Bedingung an zwei Stellen unterschiedlich nach — der Rücktritt an `delta >= delta_on` (3,0), die Regel, die er schützen sollte, hält ihre laufende Episode aber bis `delta_off` (1,5). Ein lüftender Raum wäre also bei 3,0 g/m³ in den Wächter zurückgefallen, und der Rat wäre ein zweites Mal gekippt — diesmal an der Schwelle statt am Fensterkontakt. Mit einem Prädikat beginnt und endet der Rücktritt exakt mit dem Grund, dem er weicht, einschließlich der beiden Innenfeuchte-Linien: ein Raum, der unter sie getrocknet ist, hört auf, ein Grund fürs Offenhalten zu sein, auch wenn draußen noch 5 g/m³ trockenere Luft steht. Der Wächter übernimmt dann **im selben Tick** — es entsteht keine Lücke, in der bei offenem Fenster und nassen Wänden `idle` steht.

**Der erste Versuch war falsch, und die Integrationssuite hat ihn in derselben Stunde erlegt.** Er hängte den Rücktritt an den **Trocknungsgewinn**: Außenluft um mindestens die Eintrittsschwelle der Feuchteregel (3,0 g/m³) trockener. Die beiden Feldfälle trennten sich darauf sauber — Küche 2026-08-19: 1,6 g/m³; Schlafzimmer 2026-09-14: 3,7 g/m³ — und das sah nach der Antwort aus. Im Winter ist kalte Außenluft aber **immer** absolut trockener: das Glue-Szenario (23 °C/60 % gegen 6 °C/85 %) hat **6,2 g/m³** Gewinn, mehr als das Schlafzimmer, und der Wächter wäre für die gesamte Heizperiode abgeschaltet gewesen — genau dann, wenn man ihn braucht. **Der Gewinn trennt die Fälle nicht.**

Was sie trennt, ist **wessen Anweisung gerade ausgeführt wird.** Poise hatte dem Schlafzimmer das Öffnen geraten und sich in der Sekunde, in der das Fenster sich bewegte, selbst widersprochen. Die Küche 2026-08-19 und der Glue-Fall haben keine solche Episode: dort stand vorher `heat_out` bzw. gar kein Öffnen-Rat. Deshalb ist die Bedingung die enge — **den eigenen, noch gültigen Öffnen-Rat nicht zurücknehmen** — und nicht die physikalisch klingende, aber unbrauchbare über den Gewinn. `heat_out` zählt dabei bewusst nicht als „eigene" Episode: das ist die thermische Regel, sie trägt ihre eigenen Wächter.

| Fall | eigene Episode? | Kante schutz-gebunden | Rat |
|---|---|---|---|
| Küche 2026-08-19 (N2) | nein | ja | `close`/`mold_guard` — unverändert |
| Glue-Szenario (N3, Winter) | nein (vorher `heat_out`) | nein | `close`/`mold_guard` — unverändert |
| Schlafzimmer 2026-09-14 | **ja** (`moisture_out`) | nein | `open`/`moisture_out` |

Ohne Außenfeuchte kann keine Feuchteregel das Öffnen geraten haben, also läuft keine Episode — die N4.2-Zusage (Gebäudeschutz überlebt den Ausfall des Außensensors) bleibt unberührt und ist als Fall festgehalten.

**Reichweite des `cool_edge_protected`-Vorrangs:** Er gilt **innerhalb von Regel 1b**, nicht global. Regel 1 (`mold_risk`, öffnen) sitzt weiterhin darüber und kann bei akutem 48-h-Mittel und trockenerer Außenluft `open` liefern, auch wenn ein Schutzboden greift — dort wird 1b gar nicht erreicht. Das ist kein Widerspruch zu N6, sondern genau die Trennung von Eintritt und Halten bei `mold_risk`, die weiterhin offen ist.

### N6.2 — Asymmetrische Marge statt Punktvergleich

`surface_needs_warmer` verglich die nötige Lufttemperatur mit der Kühlkante auf 0,05 K genau — eine halbe Anzeigestufe, also ein **Punktvergleich**. In dieser Wohnung sitzen die Räume exakt auf ihrer Kante (Raum 22,0, Kante 22,0) und die Raumfeuchte 0,2 g/m³ unter der eigenen Decke: ein Zehntel Gramm entscheidet. Sichtbar wurde das zweifach — als Selbstauflösung um 04:37:37 bei unverändert offenem Fenster, und als Unterschied zwischen zwei fast gleichen Räumen (Küche 11,9 g/m³ riet korrekt `open`, Schlafzimmer 12,0 riet `close`).

**Entscheidung:** Eintritt weiter 0,05 K unter der Kante, **Loslassen erst 0,35 K darunter** — dieselbe Eintritt-eng/Ausstieg-weit-Form wie bei jeder anderen Schwelle der Achse, verankert am vorhandenen `prev_vent_reason`. Die 0,35 K sind wie τ = 48 h ein **Arbeitswert/Kalibrierziel, nicht normativ**: rund drei Anzeigestufen, genug, dass der freigegebene Zustand sichtbar ein anderer ist als der eingetretene, und wenig genug, dass eine echte Erholung nicht lange festgehalten wird. Die Marge liegt an der Naht, weil beide Zahlen dort leben und die pure Regel sie nie sieht — dieselbe Stelle, an der auch `cool_edge_protected` entschieden wird.

**Keine Nebenwirkung auf N3.** Die enge Fassung lässt den Nachweisfall von N3 („frische Installation, nasse Wände, kein Boden durchgreifend") unverändert — er hat keine laufende Episode. Die erste, gewinnbasierte Fassung hätte ihn gekippt; das war der zweite Hinweis darauf, dass sie zu breit war.

**Wirkung.** Der Rat ist nicht mehr vom Fensterkontakt abhängig: derselbe Tick liefert bei offenem wie bei geschlossenem Fenster dieselbe Empfehlung, und sie ist befolgbar. Regelung, Writes und Schimmelboden unverändert (ADR-0048).

**Nachweise (N6b, aus dem externen Review zu `b024be0`).** `test_n6b_stand_down_shares_the_moisture_rule_own_hysteresis` (3,7 → 2,5 → 2,0 halten, 1,4 übergibt im selben Tick), `test_n6b_stand_down_needs_the_whole_moisture_reason_not_just_the_gain` (sein Gegenfall: 8,6 g/m³ / 45 % bei Δ 3,6, mit und ohne laufende Episode), `test_n6b_cold_winter_air_does_not_switch_the_guard_off` (das Glue-Szenario als purer Fall), `test_n6b_episode_hands_over_to_the_guard_in_order` (die ganze Übergabe, Tick für Tick).

**Nachweise (N6).** `tests/test_feuchte_achse.py`: `test_n6_advice_no_longer_inverts_on_the_window_contact` (der Live-Tick, vor und nach dem Öffnen), `test_n6_stand_down_is_only_for_this_axis_own_running_episode` (keine Episode, greifender Boden, `heat_out` als Vorgänger, und der unveränderte N2-Küchenfall), `test_n6_stand_down_stays_silent_without_outdoor_humidity`. `tests/test_phase8_shadows.py`: `test_mold_guard_releases_on_a_wider_margin_than_it_enters` an der Naht, und die N3-Probe um ihre N6-Gegenprobe ergänzt — identische Eingänge, einziger Unterschied ist die laufende Episode. `tests/integration/test_vent_advice_glue.py` läuft unverändert wieder grün; es war der Fund.

**Offen (unverändert):** ursachenspezifische Ausstiege über `prev_vent_reason` statt des generischen `target_reached`; g/kg als interne Rechengröße; Fähigkeitsmodell Umluft vs. Zuluft; τ-Kalibrierung — N6 nimmt dem EWMA-Befund die Dringlichkeit, hebt ihn aber nicht auf.

## Nachtrag N7 (2026-09-14, v0.194.5): `mold_guard` vergleicht wieder gleiche Bezugsgrößen; ungegateter Feuchte-Schutzrat `moisture_protect` — umgesetzt

**Anlass:** der [Bad-Feldbefund](../reviews/2026-09-14-Feldbefund-Bad-ohne-Lueftungsrat.md) und die externe Prüfung dazu. Der Bericht deckte zwei unabhängige Probleme auf: dem akuten Bauteilschutz fehlt ein ungegateter Lüftungsrat, und der bestehende `mold_guard` rechnete mit einem bezugsgrößenfalschen RH-Vergleich.

### N7.1 — Die Schimmelgrenze wird auf der Raumluft gelesen, nicht auf der Oberfläche

Regel 1b prüfte seit N2 `surface_rh_pct > rh_max_safe_pct`. Links steht eine **Oberflächen**-RH, rechts die **Raumluft**-Obergrenze (`max_safe_rh` sagt es im eigenen Docstring: „Mould-safe **ROOM**-RH ceiling"). Beide sind „% RH", aber bei **verschiedenen Bezugstemperaturen** — zwei Koordinaten derselben Wasserdampfmenge, nicht direkt vergleichbar. Der Quotient `p_sat(T_Raum)/p_sat(T_si)` lag im Feld bei 1,20–1,27, die Regel sprach also ab etwa `rh_max_safe / 1,2` an.

An drei realen Ticks nachgerechnet (t_out jeweils aus den publizierten Werten zurückgerechnet; die Nachrechnung reproduziert `surface_rh` und `rh_max_safe` auf 0,1 genau):

| Fall | Raum vs `rh_max_safe` | Oberfläche vs `critical_rh` | w_in vs `abs_max_safe` | kanonisch kritisch? |
|---|---|---|---|---|
| Bad, 14.09. | 69,5 vs 63,3 → **+6,2** | 87,9 vs 80,0 → **+7,9** | **+1,24** | ja |
| Schlafzimmer, 14.09. | 62,0 vs 62,8 → **−0,8** | 79,0 vs 80,0 → **−1,0** | **−0,15** | **nein** |
| Küche, 19.08. (Anlass von N2) | 66,0 vs 68,6 → **−2,6** | 77,0 vs 80,0 → **−3,0** | **−0,53** | **nein** |

Die drei kanonischen Formen stimmen exakt überein — **eine** Grenze in drei Koordinatensystemen. Der alte Vergleich war eine vierte Variante und die einzige, die in allen drei Fällen auslöste.

**Entscheidung:** `rh_pct > rh_max_safe_pct`. Gleiche Bezugsgröße auf beiden Seiten, keine neue Schnittstelle — `rh_pct` steht seit N5 ohnehin in der Signatur. `surface_rh_pct` bleibt Parameter und Attribut: es ist, was die Karte zeigt und was die Schwere lesbar macht; die andere Hälfte des Wächters (`surface_needs_warmer`) ist ein Temperaturvergleich und unberührt. `surface_rh > critical_rh` wäre gleichwertig, müsste aber `critical_rh` erst in die pure Funktion tragen; `w_in > abs_max_safe` ist dieselbe Grenze absolut und taugt als **Schweregrad** („der Raum trägt 1,24 g/m³ mehr Wasserdampf, als die Bauteilsituation zulässt"), nicht als zweite Bedingung.

**Tragweite, offen ausgesprochen:** Die beiden Feldfälle, auf denen N2 und N6 aufgebaut wurden, waren nach der kanonischen Grenze **nicht** kritisch. Der Schlafzimmer-Flip von N6 hätte es unter N7.1 gar nicht gegeben — die N6-Standdown-Logik bleibt trotzdem richtig und nötig, nur greift sie jetzt bei Räumen, die wirklich über ihrer Linie liegen. Der thermische Teil von N2 (Wächter 5, `cool_edge_protected`/`surface_needs_warmer`) ist unberührt und verhindert den ursprünglichen `heat_out`-Fehlrat weiterhin.

**Folge für die Fixtures:** Die Testvorlagen führten Raum-RH, Oberflächen-RH und Decke unabhängig voneinander und waren dadurch physikalisch inkonsistent (77 % Oberfläche, 69,6 % Decke, 60 % Raum — zueinander unmöglich). Sie tragen jetzt zusammengehörige Werte, und die historischen Ticks haben ihren eigenen Fall (`test_n7_1_the_two_field_cases_were_under_their_own_limit`).

### N7.2 — `moisture_protect`: Feuchteabfuhr als Gebäudeschutz, nicht als Komfort

**Anlass (Bad, 14.09. 07:41):** 22,4 °C / 69,5 % rF (13,8 g/m³) gegen 8,6 außen — 5,1 g/m³ Gewinn —, 6,2 pp über der eigenen sicheren Raumgrenze, kein Schutzboden greift, Fenster zu. `moisture_out` erfüllte **jede** Feuchtebedingung und schwieg allein an `occupied=False`; der einzige ungegatete Öffnen-Rat (`mold_risk`) wartete auf ein 48-h-Mittel, das 5,6 pp zu niedrig stand und ~17 h unveränderter Bedingungen gebraucht hätte.

**Entscheidung:** ein **zweiter Eintritt in dieselbe Feuchte-Episode**, nicht eine konkurrierende Regel:

* **Eintritt** (ungegatet): `rh_pct > rh_max_safe_pct` **und** Δ ≥ `delta_on_gm3` **und** kein durchgreifender Schutzboden.
* **Halten**: an der **eigenen** Vorgeschichte (`prev_vent_reason == "moisture_protect"`) mit `delta_off_gm3` — die ursachenspezifische Form, in die der Rest der Achse noch wachsen soll, statt am globalen `prev_advice_active`.
* **Ausstieg**: fällt der Grund weg, während das Fenster offen ist, gibt es einen **expliziten `close`/`target_reached`** — Regel 5b wartet auf ein verbrauchtes Δ, und das Δ ist nicht, was diese Episode beendet hat. Ohne den Ausstieg bliebe das Fenster unter einem `idle`-Rat offen stehen.
* **Standdown**: `mold_guard` schweigt auch für diese Episode (N6 unverändert, zweiter Anker).

**Platzierung: unter 1b und unter 5a, bewusst.** Ein bereits offenes Fenster über einem Raum über seiner Linie *ist* die N2-Lage; diese Regel über den Wächter zu stellen würde genau den Konflikt wieder öffnen, den N6 geschlossen hat — das Glue-Szenario vom 13.09. (23 °C/60 % gegen eine 58,4-%-Decke) liegt ebenfalls über seiner Linie. Der Weg, ein Fenster offen zu halten, ist der Standdown über die **eigene laufende Episode**, nicht eine höhere Präzedenz. Unter 5a, weil ein Raum, dessen **Luft** den Schutzboden erreicht hat, durch weiteres Lüften darunter gekühlt wird. Was die Regel dadurch ändert, ist genau der Fall, den der Wächter nie erreicht: ein **geschlossenes** Fenster.

**Begründung der fehlenden Belegungssperre** — dieselbe, die N1 für das Freikühlen gegeben hat („Nachtauskühlung ist im leeren Raum am wertvollsten"), nur stärker: ein Bad ist genau dann am nassesten, wenn niemand mehr darin steht, und genau dann ist ein Präsenzmodell am unsichersten. Der Bad-Befund zeigt beides zugleich — die konfigurierte Präsenzquelle blieb mit 51 % unter ihrer ~55-%-Schwelle, während ein zweiter Belegungssensor desselben Raums „belegt, jetzt gerade" meldete.

**Modelltrennung, jetzt explizit:** **Langzeit-/Dosisrisiko** (VTT-Mould-Index mit seinem 48-h-Akutbackstop für Dauernässe, ADR-0071) entscheidet über **Heizen/Schutzboden**; **akute Überschreitung plus realer Außentrocknungsgewinn** entscheidet über die **Lüftungsempfehlung**. Ein Rat kostet nichts und ist reversibel, ein Schutzboden kostet Geld und übergeht den Nutzerwunsch — dieselbe Trennlinie, die N3 zwischen Rat und Handlung gezogen hat. Die beiden „48 h" im System sind verschiedene Mechanismen mit derselben Zahl: der Dosis-Backstop (ADR-0071) und die Zeitkonstante τ des EWMA `surface_rh_mean` (Regel 1).

**Vokabular +1** (`moisture_protect`, ein Öffnen-Grund). Karte: eigenes Label (`Bauteilschutz` / `fabric protection`) und Aufnahme in die bekannten Öffnen-Gründe, damit die Begründung nicht als leerer Chip erscheint.

**Wirkung.** Ein Raum über seiner eigenen Feuchtegrenze bekommt den Lüftungsrat unabhängig von der Anwesenheit; ein Raum darunter bekommt keinen Schließ-Rat mehr, den die Bezugsgrößenverwechslung erzeugt hat. Regelung, Writes und Schimmelboden unverändert (ADR-0048).

**Nachweise.** `tests/test_feuchte_achse.py`: `test_n7_1_the_two_field_cases_were_under_their_own_limit`, `test_n7_2_protection_airing_is_not_occupancy_gated`, `test_n7_2_protection_has_its_own_entry_and_hold_thresholds`, `test_n7_2_protection_episode_ends_with_an_explicit_close`, `test_n7_2_protection_does_not_outrank_the_mould_guard`, dazu die auf konsistente Werte umgestellten Bestandsfälle. `card/test/monitoring.test.ts`: Chip und i18n des neuen Grundes. Das Glue-Szenario der Emissionsschiene ist unverändert grün (Raum 60 % über einer 58,4-%-Decke).

**Offen (unverändert):** Trennung von Eintritt und Halten bei `mold_risk`; ursachenspezifische Ausstiege für die übrigen Gründe statt des generischen `target_reached`; g/kg als interne Rechengröße; Fähigkeitsmodell Umluft vs. Zuluft; τ-Kalibrierung; Substrat/`f_Rsi` als sichtbarer Kalibrierpunkt, bevor `rh_max_safe` weiter Schutz-Trigger wird. **Neu vorgemerkt, nicht Teil dieser Version:** [Poise adoptiert unter bestimmten Bedingungen den eigenen Schreibwert als Handverstellung](../reviews/2026-09-14-Feldbefund-Kueche-eigener-Schreibwert-als-Handverstellung.md).
