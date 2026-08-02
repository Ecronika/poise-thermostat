# Recherche: Behaglichkeitsmodus — den aktuell idealen Behaglichkeitszustand aktiv herstellen

**Datum:** 2026-07-30 · **Typ:** Recherche-Notiz (kein ADR, keine Entscheidung) · **Anlass:** Option eines Modus/Presets, das nicht nur die Temperatur regelt, sondern die Gesamt-Behaglichkeit (Temperatur, Feuchte, Luftbewegung) — ggf. über mehrere Gerätetypen (Klimaanlage, Lüfter, Ent-/Befeuchter, Heizungsthermostate) — aktiv optimiert. · **Bezug:** ADR-0023, ADR-0042, ADR-0046, ADR-0048, ADR-0050, ADR-0053, ADR-0054, ADR-0055, ADR-0058, ADR-0059, ADR-0060, ADR-0061, ADR-0066 · **Methode:** 7 parallele Recherche-Agenten (Code, Doku, Community, HA-Ökosystem, Kommerziell, Wissenschaft) + Vollständigkeits-Kritik; tragende Code-Behauptungen stichprobenverifiziert (override.py, multi/model.py, config_flow.py, tick_pipeline.py).

---

## 0. Kernbefund in fünf Sätzen

1. **Poise hat fast alle Bausteine eines Behaglichkeitsmodus bereits gebaut** — PMV/PPD-Bewertung, Fan-Kühleffekt, Lüfterumwälzung, Feuchte-Arbitrierung, Multi-Aktor-Datenmodell — aber fast alles davon ist bewusst Shadow; live aktuiert werden nur Sollwert, HVAC-Modus (inkl. `dry`/`fan_only`) und der TRV-Externfühler.
2. Die Kernfrage „worauf regelt der Modus?" ist projektintern schon einmal beantwortet worden: **ADR-0054 verwirft PMV als direkte Regelgröße** (zu Recht, s. §6) und sanktioniert stattdessen den gedeckelten ±1-K-PMV-Offset (Stufe 2) plus Fan-Credit (Stufe 3) — beides hängt am M1-Regelgüte-Gate (ADR-0055, selbst ~40 %).
3. Der Markt hat die Lücke, die ein Behaglichkeitsmodus füllen würde: **keine einzige HA-Lösung und kein Mainstream-Produkt orchestriert mehrere Gerätegattungen auf ein gemeinsames Behaglichkeitsziel** — Komfort-*Sensorik* ist Mainstream (Thermal Comfort: 868 Stars), Komfort als *Regelgröße* ist junges Early-Adopter-Feld ohne dominierende Lösung.
4. Ein Modus, der **Befeuchter oder Frischluft-Lüftung mit-steuert**, kollidiert frontal mit den normativen Non-Goals ADR-0048/0066 (inkl. Guard-Test) — Entfeuchtung (live seit v0.107) und Lüfter als Umwälzung/Kühlkredit (ADR-0053) sind dagegen sanktionierter Scope.
5. Die Wissenschaft stützt Poises vorsichtige Linie: PMV trifft die reale Empfindung nur zu ~34 %, clo/met (bei Poise Pauschalen) erklären bis ~87 % der PMV-Varianz — belastbar ist ein Behaglichkeitsmodus als **langsamer Sollwert-Übersetzer mit K-Äquivalenten (SET/Cooling Effect)**, nicht als PMV-Regler.

---

## 1. Bestandsaufnahme Poise (Code-Befund)

### 1.1 Was heute LIVE aktuiert (schreibt wirklich)

| Pfad | Code | Behaglichkeits-Bezug |
| --- | --- | --- |
| `climate.set_temperature` | `comfort/dual_setpoint.py` → `ha/tick_orchestrator.py:1302-1375` → `ha/actuator_executor.py:133-147` | Dual-Setpoint mit Totband, Eco-Widen, Taupunkt-Cap, Mold-Floor; MRT/operative Temperatur fließt live ein (`operative_to_air`, `dual_setpoint.py:119-120`) |
| `climate.set_hvac_mode` | `mode_arbitration` (`control/tick_pipeline.py:959-963`, verifiziert), `run_mode_nudge` (`tick_orchestrator.py:1799-1839`) | **`dry` wird real kommandiert** (ADR-0050, live seit v0.107): RH ≥ Kategorie-Decke im Totband → dry ersetzt idle; Verdichterschutz gated (ADR-0046 §8 live) |
| `fan_only` als Idle-Park | `control/tick_resolve.py:334-335`, `tick_orchestrator.py:1331-1342` | Schutz gegen Über-Trocknung — *nicht* Komfortkühlung |
| TRV-Externfühler-Feed | `number.set_value` (`tick_orchestrator.py:2002-2049`) | operative Temperatur an den TRV — „was der Raum fühlt" regelt live |
| Presence/Eco | `comfort/presence.py:48-101` → `tick_pipeline.py:823-844` | COMFORT/ROOM_ECO/AWAY live (ADR-0058) |
| Lüftungs-Hinweis | `tick_orchestrator.py:1450-1478` | Bus-Event + Notification — aktuiert **kein** Gerät (ADR-0066) |

### 1.2 Was berechnet, aber nur Shadow/Diagnose ist

Alle in `diagnostics/shadows.py::compose_climate_band`, publiziert als Klima-Attribute:

| Baustein | Code | Stand |
| --- | --- | --- |
| **PMV/PPD (ISO 7730)** inkl. EN-Kategorie | `comfort/pmv.py:44-98`; Shadow `shadows.py:401-407` | Stufe 1 fertig inkl. Card-Ampel „Behaglichkeit" (v0.125/0.137); „PMV is never a direct setpoint" |
| **Fan-Kühleffekt (ASHRAE 55)** | `comfort/fan_cooling.py:30-111` (`fan_ce_k`, `fan_cool_sp_shadow`) | Shadow fertig (v0.128); Luftgeschwindigkeit aus realem Fan-Zustand (0,25–0,85 m/s Tabelle); Schreibpfad bleibt bewusst bei 0,1 m/s |
| **Idle-Lüfterumwälzung** | `comfort/fan_circulation.py:32-57` (`fan_circ_shadow`) | ADR-0053 Shadow ~40 %; `set_fan_mode` wird **nirgends** dispatcht |
| **Free-Running-Widening** | `comfort/free_running.py:34-53` (`fr_*`) | Shadow (adaptive Kühlkante dagegen live opt-in, ADR-0061) |
| **Feuchte-Achse aufwärts** | `rh_max_safe`/`abs_max_safe`/`vent_advice` (`shadows.py:411-467`, `comfort/mold.py:76-77`) | monitor-only, nie aktuiert |
| **Multi-Aktor-Arbitrierung** | `multi/` (Axis/Direction `model.py:19-35`, Discovery `discovery.py:83-191`, Lifecycle) | P0–P2 fertig; `humidity_resolver`/`air_movement_resolver` No-ops, `assignment_planner` „build, never execute" |

### 1.3 Die realen Lücken (Kritik-verifiziert)

1. **Config-Flow bindet exakt einen Aktor, hart auf die climate-Domain** (`config_flow.py:228`, selbst verifiziert; ebenso `:336`). Es gibt heute **keinen Weg**, einen Lüfter, (Ent-)Befeuchter oder Switch an eine Zone zu binden — die „fertige" Capability-Discovery ist reiner Pure-Layer ohne Glue/Storage/UI (`multi/schema.py:23-24`: „promoted … when the glue/storage lands in P3"). Der Config-Flow-/Storage-/Migration-Umbau ist der vermutlich größte Einzelbrocken des Vorhabens und in keinem Plan beziffert.
2. **Kein Ausführungspfad für fan/humidifier**: `ActuatorExecutor` kennt nur climate/number/select-Dispatches; `actuator.py` nur `SETPOINT`/`TPI_VALVE`. HA-seitig ist das **kein Blocker** (Integrationen dürfen Services fremder Entities rufen — Versatile Thermostat macht das mit switch/valve vor), aber es ist Neubau.
3. **Kein PMV/SET-Optimierer**: Es existiert kein Löser, der Temperaturziel, Feuchteziel und Luftgeschwindigkeit gemeinsam stellt. Der sanktionierte Pfad (ADR-0054 Stufe 2: PMV-invertierter ±1-K-Offset in `dual_setpoint.decide`, solver-geklemmt) ist vorbereitet, aber M1-gegated.
4. **Befeuchten kann Poise gar nicht**: `Direction.HUMIDIFY` ist „inventory-only; never actuated (ADR-0048)" (`multi/model.py:35`, verifiziert); `humidity_decide` kennt nur die Dry-Richtung.
5. **Kein Feedback-Kanal**: Für Ambi-artiges Präferenzlernen („zu warm/zu kalt") existiert weder Entity noch Service.
6. **Sensor-Konfiguration unvollständig**: weder CO₂- noch Luftgeschwindigkeits-Sensor im Config-Flow; velocity ist Tabellenschätzung, met fix 1,2, clo Saisonpauschale (1,0/0,5), RH-Fallback 50 % — der PMV ist explizit eine Schätzung (`pmv.py:10-12`).
7. **Override-Semantik nur für climate**: Die Adoption manueller Eingriffe (ADR-0059) existiert nur für die climate-Entität. Ein Ownership-/Konfliktmodell für Nebengeräte (fremde Automationen, manuell eingeschaltete Ventilatoren, Nachtruhe/Lärm, Min-Laufzeiten) ist designt (ADR-0046 §9 Lease), aber nicht gebaut — laut Community der häufigste Scheiterpunkt solcher Lösungen (§3).

---

## 2. Doku-Lage: was schon entschieden ist

- **„Komfortregime" ist besetzt**: `Plan_Komfortregime-und-EKF-Anregung.md` meint die Regime-Umschaltung adaptiv ↔ festes EN-Band (abgearbeitet, ADR-0023/0024 implementiert) — *nicht* einen Behaglichkeits-Nutzermodus. Ein neuer Modus braucht einen eigenen Begriff, um Verwechslung zu vermeiden.
- **ADR-0054 (PMV/PPD)**: PMV als direkte Regelgröße ist **Non-Goal** (clo/met unmessbar, springender Index thrasht den Aktor). Sanktioniert: Stufe 1 Diagnose ✅ → Stufe 2 gedeckelter ±1-K-Offset (gebaut vorbereitet, wartet allein auf M1) → Stufe 3 Fan-Credit (Shadow ✅; Sollwert-Kopplung will „idealerweise, dass Poise den Lüfter selbst kommandiert" → ADR-0053).
- **ADR-0046 (Multi-Aktor)**: Datenmodell, Adapter-Vertrag (inkl. `FanAdapter`, `HumidifierAdapter`), Präzedenz (Safety > Health > Komfort-thermisch > Komfort-Feuchte > Luftbewegung > Effizienz > Lärm), Standby-Policies, Ownership/Lease und Phasenplan P0–P8 stehen; P0–P2 umgesetzt, P3 (Thermal-Opt-in + Storage-Migration) ist der nächste Schritt. Die Phasen P4/P5 (Feuchte Shadow/Opt-in — „Entfeuchter/Befeuchter zuerst, AC-dry später") und P6/P7 (Luftbewegung) zeichnen die Aktuierung von Nebengeräten bereits vor.
- **ADR-0048/0066 (Non-Goals, mit Guard-Test `tests/test_non_goals.py`)**: keine aktive Befeuchtung, kein CO₂-/Lüftungs-Management; Feuchte-Achse „additiv, nie regelnd". **Spannungsfeld:** ADR-0046 P5 und der Reason-Code `humidify_capped_condensation_risk` antizipieren einen Befeuchter-Pfad, den ADR-0048 verbietet. Ein Behaglichkeitsmodus mit Befeuchter-Steuerung erfordert eine **explizite ADR-0048-Revision** (inkl. Guard-Test-Anpassung und Neubewertung der Befeuchterhygiene-Gründe) — das darf keine implizite Nebenwirkung sein.
- **ADR-0055 (M1, EN 15500-1 CA)** ist das einheitliche Flip-Gate für **alle** Shadow→Live-Übergänge (`flip_ok = identified ∧ dev ≤ 0,5 K ∧ ≤ 3 Zyklen/h ∧ ≥ 90 % Bandtreue ∧ Warm-up`) — selbst noch Shadow (~40 %), Feld-Kalibrierung über die Saison offen. **Jede Behaglichkeitsmodus-Roadmap hat diese harte Vorgänger-Abhängigkeit.**
- **ADR-0042/0059 + Dry-Recherche**: Modi sind Kategorie/Offset auf der Komfortbasis (nie freie Temperatur), Presets sind für **Komfortprofile** reserviert — ein „Behaglichkeit"-Preset wäre HA-spezifikationskonform; Betriebsmodi gehören dagegen in `hvac_modes`.

---

## 3. Nutzerwünsche (HA-Community, belegt)

**A) Gefühlte Temperatur als Regelgröße — der stärkste Wunsch.** Der Forumsthread „Heat Index / Apparent Temperature / Feels Like" läuft seit **Mai 2016** bis mindestens 2025; Nutzer wollen damit ausdrücklich Thermostate *steuern*, nicht nur anzeigen. Thermal Comfort (868 Stars) liefert nur Sensoren — genau diese Lücke benennen Nutzer („what the floor thermostat should be set to, and when to start a fan cycle"). Das Indoor Thermal Comfort Tool (PMV/PPD/SET, 2025) wird von Nutzern bereits eigenmächtig zur AC-Steuerung zweckentfremdet. Better Thermostat stellt selbst eine künftige „feels-like"-Regelung in Aussicht.

**B) Multi-Geräte-Orchestrierung.** 2025/26 erschien eine Welle von Blueprints (Smart Humidity Multi-Device, Room Humidity → Dry-Mode, ASHRAE-55 Adaptive Climate Control mit „exactly what I needed"-Echo). HA-Bordmittel erzwingen Fragmentierung: Generic Hygrostat = ein Schalter pro Entität; Befeuchter *und* Entfeuchter brauchen zwei Entitäten plus Eigenbau-Verriegelung.

**C) Schmerzpunkte** (= Designpflichten für Poise): Automationen kämpfen gegen manuelle Eingriffe (Ventilator nach 30 s wieder ausgeschaltet → Boolean-Helper-Workarounds); Ping-Pong/Kurzzyklen ohne Hysterese und Min-Laufzeiten; Formel-Wirrwarr beim Feels-like-Selbstbau (Heat Index gilt nur outdoor/>27 °C); fehlende Sensorik für v und MRT → Wunsch nach virtuellen Ersatzberechnungen (Poise hat mit `virtual_mrt`/`fan_velocity` genau das).

**D) Popularität**: Komfort-*Sensorik* Mainstream (9+ Jahre, 868 Stars); Komfort als *Regelgröße* junges Feld ohne dominierende Lösung; „Einknopf-Komfort" wird selten wörtlich gefordert, zeigt sich aber im Echo auf Set-and-forget-Blueprints.

---

## 4. Wettbewerb im HA-Ökosystem

| Lösung | Komfortmodell | Aktuiert? | Reife | Lücke |
| --- | --- | --- | --- | --- |
| Thermal Comfort (dolezsa) | psychrometrische Indizes, Perception | **nein** | 868 ★, De-facto-Standard | reine Anzeige |
| Comfort Advisor | Simmer-Index, „Can Open Windows" | nein | Nische, ruhend | Empfehlung only |
| Adaptive Climate Blueprint (msinhore) | ASHRAE-55 adaptiv, Kat. I–III | Sollwert ja, Modi nein | ~22 ★, jung | ein Gerät, kein Zustand/Lernen |
| schoolboyqueue-Blueprints | ASHRAE 55 + EN 16798 (Deckenventilator), Psychrometrie | ja (Thermostat, Fans, Bad-Lüfter) | jung | Blueprints laufen **unkoordiniert** nebeneinander |
| Better Thermostat | nur Temperatur | ja (TRV) | 1500+ ★ | kein Feuchte-/Komfortmodell; AC erst seit 2024 Beta |
| Versatile Thermostat | nur Temperatur | ja | 1100+ ★ | Feuchte-Issue #167 offen seit 2023 |
| Generic Hygrostat (Core) | festes RH-Band | ja (1 Schalter) | stabil | keine Temperatur-/Taupunktkopplung |
| Sensibo Climate React | Schwellen auf Temp/RH/„Feels like" | **ja** (voller AC-Zustand) | kommerziell, in Core | Ein-Gerät, Cloud, kein Lernen |
| Node-RED „Dew Point Comfort" V6 | Taupunkt-Komfortklassen | ja (Tado-AC + Entfeuchter + Deckenfan) | Bastel-Flow | vollständigste Koordination, aber ohne Norm/Lernen/Produktreife |

**Was es definitiv nicht gibt** (die Poise-Lücke): (1) einen Multi-Aktor-Komfort-Koordinator unter *einem* Komfortziel; (2) eine EN-16798-1-basierte *Integration* (ASHRAE 55 existiert nur als Blueprint); (3) „günstigster Weg zum Komfort" (niemand nutzt den Luftbewegungs-Kredit zur Aktor-*Wahl*); (4) Lernen der Komfort*definition* (gelernt werden nur Technik-Offsets); (5) Konfliktauflösung zwischen Geräten (Entfeuchter heizt, AC entfeuchtet, Fan wirkt nur bei Anwesenheit).

---

## 5. Kommerzielle Lösungen

- **tado° Air Comfort**: 2D-Bewertung Temp×RH gegen einen „internationalen Standard" (saisonal-adaptiv — konzeptionell Poises EN-16798-Basis), Schimmel-/Trockenheitswarnung, Lüftungsempfehlung — aber **Anzeige-/Empfehlungssystem, kein Regler**; der Mensch bleibt Aktor.
- **Ecobee „Feels Like"**: regelt auf gefühlte Temperatur per fester Formel (~2 °F je 10 % RH), kein ML — der Beweis, dass eine *einfache* Feuchte-Korrektur der Regelgröße produktreif ist (≙ ADR-0054 Stufe 2).
- **Sensibo Climate React / PureBoost**: Schwellen-Trigger auf Temp/RH/Feels-like inkl. „ab 75 % RH Dry statt Kühlen"; PureBoost ist das einzige gefundene echte Cross-Device-Beispiel (Elements-Monitor triggert AC-Fan + Luftreiniger). Teils Abo, cloudgebunden.
- **Ambi Climate (†2024)**: der Goldstandard fürs Konzept — personalisiertes Komfortmodell aus explizitem Feedback („too hot"…„too cold", Lernen ab dem 3. Feedback) + Kontext, mit separatem zweiten Modell für Raum-/AC-Dynamik (saubere Architekturidee: **Präferenzmodell ≠ Dynamikmodell**; Poise hat das zweite bereits im EKF). Cloud-Abschaltung April 2024 machte alle Geräte funktionslos — das stärkste Argument für Poises Local-First.
- **Daikin/Mitsubishi** (Intelligent Eye, 3D i-see: 752 Thermal-Zonen, Personen-/Hauttemperatur, Lamellen-Verfolgung): über HA-APIs praktisch nicht nachbildbar — Anti-Zugluft bleibt In-Gerät-Domäne.
- **Nest** (True Radiant/Airwave = Dynamik-Lernen, Restkälte per Lüfter), **Dyson** (3 Subsysteme, aber nur intern), **Bosch/HmIP/Wiser** (klassische Heiz-Heuristiken), **Havenwise/tado HPO** (lernen Gebäude, nicht Präferenz).

**Fazit kommerzielle Seite**: Niemand regelt mehrere Gerätegattungen geschlossen auf ein Behaglichkeitsziel. Übertragbar auf Poise: Feels-like-Regelgröße, tado-artiges 2D-Komfortfeld (Card), Ambi-artiges Feedback-Lernen als lokales Offset-Lernen aufs Normband, PureBoost-artige Orchestrierung. Nicht übertragbar: Personen-Sensorik, Flotten-Cloud-ML.

---

## 6. Wissenschaftlich-normative Basis & Fallstricke

- **PMV-Validität ist begrenzt**: Trefferquote der realen Empfindung nur ~34 % (Cheung et al. 2019, ASHRAE-DB II); met+clo erklären bis ~87 % der PMV-Varianz — und genau die sind bei Poise Pauschalen. PMV-Feinheiten unter ±0,3 sind Scheingenauigkeit. **Personalisierte Modelle** erreichen ~0,73 vs. ~0,51 Genauigkeit → Feedback-Lernen ist wissenschaftlich der überlegene Endzustand.
- **PMV als Regelgröße wird auch in der Forschung fast nie direkt gefahren** — üblich ist die *äußere Schleife*, die einen Temperatur-Sollwert erzeugt (exakt Poises ADR-0054-Stufe-2-Muster). Einsparungen: ~9–19 % (kontextabhängig, simulationslastig); der Mehrwert liegt dort, wo Lufttemperatur den Komfort *falsch* abbildet (Strahlung, Feuchte, Luftbewegung).
- **SET/Cooling Effect als gemeinsame Währung**: ASHRAE 55-2020 rechnet ab v > 0,2 m/s über SET einen Cooling Effect in Kelvin. Größenordnungen: 0,5 m/s ≈ 2 K; 0,8 m/s ≈ 3 K (Obergrenze ohne Nutzerkontrolle); Deckenventilatoren 2–4 K bei 2–30 W → **Faktor 20–50 günstiger als Kompressorkühlung**; ~10 % HVAC-Einsparung je 1 K Sollwertanhebung; Feldstudien (Singapur, Kalifornien): bis ⅓ Einsparung bei 24→26,5 °C mit Fans. **Das ist die rationale Basis eines „günstigster Weg zum Komfort"-Arbitrierers: alle Maßnahmen in K-Äquivalente übersetzen, dann nach K pro Watt priorisieren.**
- **Feuchte ist im moderaten Bereich eine schwache Komfortgröße** — Be-/Entfeuchtung lässt sich komfortindex-basiert kaum begründen, wohl aber **gesundheits-/bauphysikalisch** (Schimmel: 80 % Oberflächen-RH, DIN 4108-2/EN ISO 13788; Trockenheit: Schleimhäute unter ~30 % RH). Winterbefeuchtung ist teuer (REHVA: +20/50/80 % Heizenergie bei 30/40/50 % RH) und EN 16798-1 rät zur Zurückhaltung (Default 20–30 % RH für kalte Klimate). ⇒ Poises bestehende Linie (Feuchte über Gesundheit/Bauphysik klemmen, nicht über PMV optimieren) ist normkonform und bleibt auch im Behaglichkeitsmodus richtig.
- **Ventilator-Sicherheitslogik**: bei trockener Hitze können Fans schaden (WHO 2024: nur unter 40 °C; ältere 35-°C-Grenze umstritten); im Heizfall Zugluft-Risiko (DR-Modell ISO 7730). Eine Fan-Freigabe braucht diese Guards.
- **Priorisierung (ableitbar, nicht normativ fixiert)**: Kühlfall — erst Luftbewegung (billigste K), dann Sollwertanhebung, dann sensible Kühlung; Entfeuchtung nur bei Taupunkt-/RH-Grenzverletzung, bevorzugt über die ohnehin laufende Kühlung. Heizfall — erst Sollwert/Strahlung, Fan aus, Befeuchtung (falls überhaupt) nur unterhalb der Gesundheitsgrenze und immer durch die außentemperaturabhängige Kondensationsgrenze gedeckelt.
- **Werkzeug**: `pythermalcomfort` (pmv_ppd, set_tmp, cooling_effect, adaptive_en, use_fans_heatwaves, clo_tout) als Referenz-/Testvektor-Quelle — Poise bleibt per ADR-0022 stdlib-only, nutzt die Bibliothek aber bereits als Testreferenz.

---

## 7. Einordnung: was „Behaglichkeitsmodus" für Poise sinnvoll heißen kann

Drei aufeinander aufbauende Ausbaustufen (keine Entscheidung, sondern die aus Befund + Markt + Wissenschaft ableitbaren Optionen):

### Stufe A — „Behaglichkeit herstellen" mit dem vorhandenen Aktor (kein ADR-Bruch)

Ein Preset/Verhaltens-Toggle, der die bereits gebauten Shadows scharfschaltet: PMV-invertierter ±1-K-Offset (ADR-0054 Stufe 2), Fan-Credit auf die Kühlkante + `set_fan_mode`-Kommando (ADR-0054 Stufe 3 + ADR-0053), Idle-Umwälzung. Effekt: schwüle Luft → etwas tiefer kühlen; trockene Winterluft → weniger heizen; Fan hebt die Kühlkante, bevor der Verdichter läuft. **Abhängigkeit: M1-Gate (ADR-0055).** Technisch: neues `OverrideMode`-Member ist billig (Entity/Card/Persistenz ziehen generisch nach), aber ein Offset-0-Preset wäre deckungsgleich mit COMFORT — der Mehrwert muss aus dem *Verhalten* kommen. Zu klären: Preset (User-Intent) vs. Zonen-Feature-Toggle (Options-Achse, wie `adaptive_cool`); drei überlappende Bedienelemente (comfort_weight-Slider, COMFORT-Preset, neuer Modus) müssen entwirrt werden.

### Stufe B — Multi-Aktor-Orchestrierung im sanktionierten Scope (ADR-0046 P3–P7)

Klimagerät + dedizierter Lüfter + Entfeuchter koordiniert auf ein Ziel; Feuchte weiterhin nur abwärts. Das ist die eigentliche Marktlücke (§4) und architektonisch vollständig vorgezeichnet (Achsen, Adapter, Präzedenz, Lease, Standby). Realer Aufwand liegt aber weniger in der Regellogik als in: Config-Flow-/Storage-Umbau (heute 1 Aktor, climate-only — verifiziert), Executor-Pfade für fan/humidifier-Services, **Ownership-/Koexistenz-Modell für Nebengeräte** (ADR-0059-Adoption existiert nur für climate; genau hier scheitern die Community-Bastellösungen), Card-Darstellung des Mehrgeräte-Zustands. Der SET/K-pro-Watt-Arbitrierer (§6) wäre das Alleinstellungsmerkmal („Fan zuerst, Kompressor später").

### Stufe C — Befeuchtung + Präferenzlernen (ADR-Revision nötig)

Vollständige Behaglichkeit inkl. Winter-Trockenheit (Befeuchter-Ansteuerung mit hartem Kondensations-/Hygiene-Deckel) und Ambi-artigem „zu warm/zu kalt"-Feedback als lokal gelerntem Offset aufs Normband. Wissenschaftlich der stärkste Endzustand (~0,73 vs. 0,51), aber: erfordert explizite Revision von ADR-0048/0066 (samt Guard-Test und Hygiene-Neubewertung), einen neuen Feedback-Kanal (Entity/Service), und die energetische Ehrlichkeit (REHVA-Zahlen) gehört in die UI.

---

## 8. Offene Entscheidungsfragen (aus der Vollständigkeits-Kritik)

1. **Regelgröße festlegen**: PMV-Offset (validitätsschwach, aber sanktioniert und gebaut) vs. reines EN-Band (existiert schon ≈ COMFORT) vs. Feedback-Lernen (stärkste Evidenz, keine Infrastruktur). Ohne diese Festlegung ist der Modus nicht spezifizierbar. Naheliegend: A→C als Evolutionspfad, PMV/SET als Start, Feedback als Lernsignal obendrauf.
2. **Feuchte: Komfort- oder Gesundheitsgröße?** Als Gesundheitsgröße ist der Abwärts-Pfad bereits live und der Restnutzen des Modus liegt beim (verbotenen) Befeuchten — die Scope-Entscheidung „Befeuchten ja/nein" ist eine explizite ADR-Frage, keine Implementierungsfrage.
3. **M1-Restaufwand und Flip-Granularität** (pro Shadow einzeln oder global?) beziffern — es ist der kritische Pfad jeder Stufe.
4. **Aufwand Config-Flow/Executor/Migration** für Stufe B ehrlich schätzen (größter unbezifferter Brocken).
5. **Koexistenz-Kapitel**: Ownership, Min-Laufzeiten, Lärm/Nachtruhe, Adoption manueller Eingriffe an Nebengeräten — das Design-Kapitel mit dem höchsten Scheiterrisiko.
6. **Sensorik-Minimum und Degradationsleiter** des Modus definieren (reichen T+RH? Verhalten ohne MRT/velocity/CO₂?).
7. **Zieldefinition**: Komfort maximieren oder komfort-neutral den billigsten Weg wählen (bräuchte Kosten-/COP-Modell; `cop_balance_c`/`marginal_cost_sensor` sind bisher nur P0-Namenskonstanten)?
8. **Begriffsklärung**: „Komfortregime" (ADR-0023) und COMFORT-Preset sind besetzt — der neue Modus braucht einen eigenen, untechnischen Namen.

---

## 9. ADR-Revisionsbedarf für einen qualitativ hochwertigen Behaglichkeitsmodus

Bewertung nach Volltext-Lektüre der Revisionskandidaten (ADR-0048, ADR-0055, ADR-0060, ADR-0066 — 2026-07-30). Ergebnis: **zwei echte Revisionspunkte, zwei Nachtrags-Kandidaten, und eine Keep-Liste** — die Kernentscheidungen sind Qualitätsanker, keine Hindernisse.

### 9.1 Revidieren (echte Blocker, eng schneiden)

**R1 — ADR-0048 §3 „Keine aktive Befeuchtung" (+ ADR-0066-Folge).** *Nur für Ausbaustufe C nötig; der interne Widerspruch gehört aber so oder so aufgelöst.* Trockene Winterluft ist die häufigste Komfortklage, die Poise erkennen, aber nicht beheben darf. Die Guardrails für sichere Befeuchter-Ansteuerung sind bereits vollständig gebaut: ADR-0066 C berechnet `rh_max_safe`/`abs_max_safe` ausdrücklich als „die Obergrenze, die einem *fremden* Befeuchter fehlt", inkl. `fabric_conflict` — Poise rechnet die sichere Hülle aus und verbietet sich selbst, sie zu nutzen. Interner Widerspruch: ADR-0046 P5 plant „Humidity Opt-in — **Entfeuchter/Befeuchter zuerst**" samt Reason-Code `humidify_capped_condensation_risk` und Befeuchter-Standby-Policy (§7) — was ADR-0048 §3 normativ verbietet. Revisionsschnitt: Opt-in-Ansteuerung einer dedizierten `humidifier`-Entität, hart geklemmt durch `rh_max_safe` + Taupunkt, mit ehrlicher Energie-Anzeige (REHVA +20–80 %) und Guard-Test-Anpassung (`tests/test_non_goals.py`). Falls Stufe C nicht gewollt: stattdessen ADR-0046 P5 um den Befeuchter-Teil kürzen — der Widerspruch darf nicht stehen bleiben.

**R2 — ADR-0048-Nachtrag zu ADR-0046 §2: `air_movement` nur „Kühlkanten-Gutschrift + Umwälzung".** Der Nachtrag fixiert die Achse auf zwei passive Rollen. Der Behaglichkeitsmodus braucht die dritte: den Lüfter **aktiv als erste Kühlstufe** kommandieren („Fan zuerst, Kompressor später") — der größte Qualitäts-pro-Aufwand-Hebel (2–4 K bei 2–30 W, Faktor 20–50 günstiger als der Verdichter, §6). ADR-0053 §35 erkennt gestufte Kühlung (dual_smart-Muster) bereits als *anderen* Anwendungsfall an, und ADR-0054 Stufe 3 wünscht ausdrücklich, dass „idealerweise Poise den Lüfter kommandiert". Philosophisch unkritisch: bleibt thermischer Komfort über Luftbewegung, keine IAQ-/Frischluft-Lüftung — der Geist von ADR-0048 §1/§2 bleibt unberührt. Pflichtteil: Sicherheits-Guards (WHO-Hitzegrenze < 40 °C, Zugluft-/DR-Modell im Heizfall, 0,8 m/s ohne Nutzerkontrolle).

### 9.2 Nachträge empfehlenswert (Qualität, keine Scope-Änderung)

**N1 — ADR-0055: das Flip-Gate misst Regelgüte, nicht Behaglichkeit.** Die CA-Metrik bewertet ausschließlich gegen das Temperaturband (`deviation_k`/`time_in_band`/`cycles_per_hour`). Für Komfort-Achsen-Flips ist das ein schwaches Abnahmekriterium: der Nutzen eines Fan-Flips zeigt sich im PPD, nicht in der Bandabweichung, und der PMV-Offset *verschiebt* das Band, gegen das die Metrik misst (das Eigenband-Problem benennt ADR-0055 in den Konsequenzen selbst). ADR-0054 liefert die Lösung mit: PMV/PPD sei „ein natürliches Komfort-Signal für die M1-Metrik". Nachtrag: für Komfort-Features eine PPD-Komponente ins Flip-Prädikat (zeitgewichteter PPD darf sich nicht verschlechtern). Zweitens **Risiko-Stufung explizit machen**: ADR-0055 beansprucht „alle Shadow→live-Flips", während ADR-0053 seine Lüfter-Aktuierung nur an Presence + Opt-in knüpft — diese Ambiguität auflösen. Ein reversibler `fan_mode=low`-Write ohne Verdichterbezug muss nicht eine volle Feldsaison hinter demselben Gate warten wie MPC-/Ventil-Aktuierung.

**N2 — ADR-0054: Kern behalten, markierte Lücken schließen.** „PMV nie direkte Regelgröße" ist richtig und wissenschaftlich gedeckt (34 % Trefferquote, clo/met ≈ 87 % der Varianz, §6) — nicht anfassen. Aber: die clo/met-Konfiguration ist im ADR selbst als „offen" markiert und wäre der billigste Qualitätsgewinn des Offsets (met fix 1,2 „Büro sitzend" ist fürs Schlafzimmer schlicht falsch). Den ±1-K-Deckel erst nach Felddaten neu bewerten, nicht jetzt. → Vertiefung: [2026-08-Bekleidungsmodell-clo-met.md](2026-08-Bekleidungsmodell-clo-met.md) (Kritik am clo_tout-Modell, Laufmittel-statt-6-Uhr-Beleg, met-Raumprofile, Schlafzimmer-Norm-Grenze, Feedback-Lernen als Ausweg).

### 9.3 Nicht revidieren (Qualitätsanker)

| ADR | Warum unangetastet lassen |
| --- | --- |
| ADR-0042 §1 + ADR-0035 (Modi = normgeklemmte Offsets, Solver-Präzedenz) | Genau das unterscheidet den Modus von Community-Bastellösungen, die gegen sich selbst kämpfen (§3) |
| ADR-0048 §1/§2 (keine RLT-Hygiene, keine CO₂-/Lüftungssteuerung) | Kein Aktor; Nutzer bevorzugen den Hinweis („Auto-Lüftung ging nach hinten los"); der Lüftungs-Nudge (ADR-0066 B) reicht dem Modus |
| ADR-0059/0060-Grundsatz „beobachten → vorschlagen → bestätigen, nie still" | Kollidiert *nicht* mit Ambi-artigem Feedback-Lernen: explizite „zu warm/zu kalt"-Buttons sind kein Override, sondern freiwilliges Signal; ADR-0060s Repair-Flow (≤ 0,5-K-Schritte, sichtbare Annahme, normgeklemmt) ist das fertige Auslieferungsvehikel → additiver Folge-ADR, keine Revision |
| ADR-0023 / ADR-0061 / ADR-0050 (Dual-Setpoint/Totband, Occupancy-Gating, gesundheitsbasierte Feuchte-Decken) | Normkorrekt und wissenschaftlich bestätigt (Feuchte gehört bauphysikalisch geklemmt, nicht PMV-optimiert, §6) |

### 9.4 Empfohlene Reihenfolge

**Erst R2** (Lüfter als Kühlstufe — größter Hebel, kleinste Kontroverse) → **dann N1** (sonst fehlt jedem Komfort-Flip das passende Abnahmekriterium) → **R1 nur bei bewusster Stufe-C-Entscheidung**. Jede Revision als eng geschnittener Folge-ADR nach ADR-0000-Prozess inkl. Guard-Test-Anpassung — nie als stille Aufweichung.

---

## 10. Quellen (Auswahl)

**Community/Nutzerwünsche:** HA-Forum 1282 (Feels-Like, seit 2016), 901623 (Indoor Thermal Comfort Tool), 905689 (ASHRAE-55-Blueprint), 989125 (Smart Humidity Multi-Device), 971133 (Room Humidity → Dry), 656123 (Humidity on Thermostat Card); GitHub better_thermostat #857, versatile_thermostat #167; simon42-Community (Otanes-Klima-Automation, Lüften/Schimmel).

**HA-Ökosystem:** github.com/dolezsa/thermal_comfort · lymanepp/ha-comfort-advisor · msinhore/adaptive-climate-blueprint · schoolboyqueue/home-assistant-blueprints · KartoffelToby/better_thermostat · jmcollin78/versatile_thermostat · HA-Docs generic_hygrostat/humidifier/fan/sensibo · Node-RED-Flow f37879ba (Dew Point Comfort V6).

**Kommerziell:** tado Air Comfort (support.tado.com/3405556) · Ecobee eco+ „Feels Like" · Sensibo Climate React/PureBoost · Ambi Climate (Modes 101; Abschaltung: ambiclimate.com „emotional farewell", HN 39203477) · Daikin Intelligent Eye · Mitsubishi 3D i-see · Nest True Radiant/Airwave · Dyson PH3A · Havenwise · tado Heat Pump Optimizer X.

**Wissenschaft/Norm:** Cheung et al. 2019 (doi:10.1016/j.buildenv.2019.01.055, PMV 34 %) · Humphreys & Nicol 2002 · Kim/Schiavon/Brager 2018 (Personal Comfort Models) · arXiv:2309.09073 (Active Learning) · CBE Thermal Comfort Tool + Fans Guidebook (Cooling Effect, Heatwave-Grenzen, 0,8 m/s) · Raftery et al. 2021 (99 Deckenfans) · Singapur-ZEB 2023 · REHVA „Effects of indoor air humidity" (+20/50/80 %) · DIN 4108-2/EN ISO 13788 (80 % Oberflächen-RH) · EN 16798-1 Annex B · pythermalcomfort-Doku · MDPI Buildings 12(1):38 (PMV-MPC ~19 %).

**Code-Verifikation (Stichproben, 2026-07-30):** `control/override.py:17-49` (Presets = Offsets) · `multi/model.py:22,35` (VENTILATION/HUMIDIFY Non-Goals) · `config_flow.py:228` (1 Aktor, climate-only) · `control/tick_pipeline.py:959-963` (mode_arbitration/dry live) · ADR-0046/0048/0053/0054/0055/0060/0066 + Plan_Komfortregime vollständig gelesen (0048/0055/0060/0066 für §9).
