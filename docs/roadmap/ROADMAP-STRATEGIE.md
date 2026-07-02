# Poise — Roadmap-Strategie zur Weiterentwicklung

**Basis:** Code-Review v0.110.0 (`docs/review/CODE-REVIEW-v0.110.0.md`), Wettbewerbs- und Normen-Recherche (Stand Juli 2026)
**Ziel:** Die beste Einzelraum-Klimaregelung der Home-Assistant-Community werden — die stärksten Funktionen vorhandener Lösungen übernehmen und verbessern, dabei DE/EU-Regeln, Bauphysik und Thermokomfort-Modelle als Fundament nutzen, um **energiesparend, aber komfortabel zu heizen, zu kühlen, zu entfeuchten und Luft umzuwälzen**.

---

## 1. Positionierung & Leitplanken

**Poises verteidigbares Alleinstellungsmerkmal** ist die Kombination, die keine andere Community-Lösung hat:

1. **Normbasiert statt Bauchgefühl** — EN-16798-Bänder, DIN-4108-Schimmelfloor, ASR-Cap, Präzedenz-Solver mit erklärter bindender Ursache.
2. **Echte Gebäudephysik statt Heuristik** — 1R1C-EKF mit Identifizierbarkeits-Gating; Optimal Start/Stop analytisch aus dem gelernten Modell.
3. **Ehrlichkeit als Prozess** — Shadow-first, ADR-Register, Non-Goals als Tests, Kaltsaison-Gating vor Schreibrechten.
4. **Vollständig lokal, null schwere Dependencies, gebündelte Card.**

**Leitplanken für alles Folgende:**
- Sicherheitspfade (Frost/Schimmel/Kessel/Kühlgeräte) haben Vorrang vor jedem Feature (P0-Liste aus dem Review zuerst).
- Kein Feature verlässt den Shadow-Status ohne messbares Abnahmekriterium (siehe M1: Regelgüte-Metrik).
- Der Nicht-Ziele-Katalog (ADR-0048: keine VDI-6022-Hygiene, keine CO₂-Aktuierung, kein aktives Befeuchten) bleibt — er ist rechtlich und fachlich die richtige Abgrenzung. CO₂/Lüftung bleiben Monitoring + Empfehlung („Lüften lohnt sich jetzt": Außenluft absolut trockener als innen — die dafür nötige Absolutfeuchte-Funktion fehlt noch in `psychrometrics.py`).

---

## 2. Wettbewerbsanalyse: Was übernehmen, was besser machen

### 2.1 Feature-Matrix (Community-Lösungen, Stand 07/2026)

| Fähigkeit | [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) (~1.100★) | [Better Thermostat](https://github.com/KartoffelToby/better_thermostat) | [smart_thermostat PID](https://github.com/ScratMan/HASmartThermostat) | [dual_smart_thermostat](https://github.com/swingerman/ha-dual-smart-thermostat) | [Adv. Heating Control Blueprint](https://community.home-assistant.io/t/advanced-heating-control/469873) | **Poise v0.110** |
|---|---|---|---|---|---|---|
| Aktor-Typen | Switch, Climate, Ventil | Climate (TRV) | Switch/PWM | Switch (heat/cool/fan/dry) | Climate | Climate (Setpoint); Ventil/TPI als Shadow |
| Regelalgorithmus | TPI + **Auto-TPI (lernend)**, Selbstregulation | Kalibrier-Modi: Normal/Aggressiv/**AI Time Based/MPC/PID/TPI** | PID + **Autotune** | Hysterese | Zeitplan + Regeln | Setpoint + Normklemme; MPC/TPI/PI Shadow mit EKF-Modell |
| TRV-Kalibrierung (interner Sensor) | Ventil-Kalibrierung | **Kernfeature** (target- oder offsetbasiert) | — | — | für Tado/Aqara/Danfoss/Tuya | External-Temp-Feed + PI-Kompensator (Shadow); `calibration.py` unverdrahtet |
| Fenstererkennung | Sensor + **Auto (Slope)** | Sensor | — | „openings" | mehrere Sensoren | Sensor + Auto-Slope (adaptiv via τ) — härtebedürftig (Review V6) |
| Presence/Motion/Geofencing | **ja (nativ)** | — | — | — | Party/Gast-Modus | **fehlt** |
| Load-Shedding/Overpowering | **ja (nativ)** | — | — | — | — | Shadow (Hub), ohne Enforcement |
| Heizungsausfall-/Ventilklemm-Erkennung | **ja, inkl. Stuck-Valve-Diagnose** | Offline-Schutz | — | — | Kalkschutzfahrt | Heating-Failure + valve_stuck-Issue |
| Zentralsteuerung/Multizonen | zentrale Modi | — | — | — | globales Schema | **Hub: Kesselaggregat, Vorlauf-Allokator, Kompressorgruppen (Shadow)** |
| Kühlen/Dry/Fan | Kühl-Modus | — | AC-Unterstützung | **heat+cool+fan+dry, Bodenschutz** | — | Dual-Setpoint, Dry live, Fan Shadow, Kühl-Sicherheitslücke (V1) |
| Energie-Reporting | Energie-Attribut | — | — | — | — | HDH-Schätzung (kWh/€), kein Energy-Dashboard-Anschluss |
| Normbezug (EN/DIN/ASR) | — | — | — | — | — | **einzigartig** |
| Selbstlernende Gebäudephysik | Auto-TPI-Koeffizienten | „AI Time Based" | Autotune einmalig | — | — | **EKF kontinuierlich + Konfidenz** — konzeptionell führend |
| Timed Presets / Auto-Revert | **timed preset mit Restore** | — | — | — | Zeitpläne | 2-h-Override-Auto-Revert (fix) |
| UI-Karte | eigene UI-Card (separat) | eigene Card | — | — | — | **gebündelt + auto-registriert** — best-in-class Auslieferung |

Kommerzielle Messlatte (tado Auto-Assist, Netatmo, Homematic IP, Danfoss Ally): Geofencing + Fenster-offen als *Abo-Kernfeatures*, Wetteradaption, Monatsreports. Alles davon ist lokal reproduzierbar — ein explizites Marketing-Argument für Poise („tado-Features ohne Cloud-Abo").

### 2.2 Übernehmen & besser machen (konkret)

**Von Versatile Thermostat übernehmen:**
1. **Presence/Motion/Kalender-Kopplung** — größte funktionale Lücke von Poise. Besser machen: Belegung nicht als Preset-Schalter, sondern als Eingang des Komfortfensters/`occupied`-Flags im Dual-Setpoint (nach dem Setback-Fix V3) und später als `q_occ`-Anregung des EKF (β_o wird heute nie gefüttert).
2. **Timed Presets** (Boost 30/60/120 min mit Rückkehr) — passt exakt in die vorhandene Override-Maschinerie.
3. **Load-Shedding mit Enforcement** — VTherm kann Overpowering nativ; Poise hat das bessere Fundament (zentrale Arbitrierung + `ResourceRelease`-Vertrag), aber der Rückkanal ist unverdrahtet. Verdrahten = sofortiger Feature-Vorsprung (smallest-gap-Shedding ist fairer als VTherms first-come).
4. **Stuck-Valve-Diagnose** kommandiert-vs-real ausbauen (Poise hat `valve_health` bereits als Shadow).

**Von Better Thermostat übernehmen:**
5. **TRV-Kalibrierung als Live-Pfad** — BTs Kernnutzen. Poise hat mit External-Temp-Feed (pavax-verifiziert) und PI-Kompensator (ADR-0037) die *besseren* Mechanismen, aber `calibration.py` (BT-Formeln, korrekt implementiert) ist toter Code. Live schalten mit Gating auf frisches TRV-Temp-Update + Rate-Limit (BTs bekannte Offset-Oszillations-Issues vermeiden — z. B. [#1410](https://github.com/KartoffelToby/better_thermostat/issues/1410)).

**Von smart_thermostat/PID-Familie:** 6. **PWM/Switch-Aktoren** als Aktortyp (Infrarot, Wandheizung, Pelletofen-Relais) — öffnet eine große Nutzergruppe; Poises TPI-Duty existiert bereits, es fehlt nur der Switch-Writer im Aktor-Choke-Point.

**Von dual_smart_thermostat:** 7. **Bodentemperatur-Schutz** (Floor-Sensor min/max) für FBH — trivial im Constraint-Solver abbildbar (SAFETY-Cap/Floor) und für den DACH-Markt (FBH-Neubau) wichtig.

**Vom Blueprint-Ökosystem:** 8. **Kalk-/Festsitzschutzfahrt** (wöchentliches Ventil-Öffnen im Sommer) — Hygienefaktor für TRV-Lebensdauer, einfach zu implementieren, wird von Nutzern aktiv gesucht.

**Was niemand hat (Differenzierung ausbauen):** Norm-Compliance-Reporting (EN-16798-Anhang-C-Stundenstatistik als Sensor), erklärende bindende Ursachen („warum 20,4 °C: Schimmelfloor"), Kaltsaison-validierte Regler-Freischaltung, Multizonen-Erzeugerkoordination mit Vorlauf-Allokator.

---

## 3. Normen, Gesetze, Regeln als Produktstrategie (DE/EU)

| Regelwerk | Relevanz für Poise | Roadmap-Konsequenz |
|---|---|---|
| **GEG §63** — Pflicht zur selbsttätigen raumweisen Regelung bei Wasser-Zentralheizungen ([buzer.de/63_GEG.htm](https://www.buzer.de/63_GEG.htm)) | Poise *ist* funktional eine Einzelraumregelung; keine Rechtspflicht für Software, aber Anschlussargument | Doku-Kapitel „Poise & GEG": Einordnung, Grenzen (keine bauaufsichtliche Konformitätsvermutung), Zusammenspiel mit TRV-Pflichtbestand |
| **EPBD-Recast (EU) 2024/1275** — Gebäudeautomation, Smart Readiness Indicator ([Danfoss-Überblick](https://www.danfoss.com/de-de/about-danfoss/articles/dhs/new-en-iso-52120-bacs-standard-for-building-efficiency/)) | SRI bewertet exakt Poise-Funktionen (Einzelraumregelung, Optimal Start, Bedarfsführung, Reporting) | SRI-/BACS-Selbsteinstufung dokumentieren; Office-Vermarktung |
| **EN ISO 52120-1** — GA-Effizienzklassen A–D; Klasse A = Raumautomation mit Bedarfsführung + Monitoring, bis ~30 % Einsparung ggü. C in Büros ([SHKwissen](https://www.haustechnikdialog.de/SHKwissen/3300/Effizienzklassen-bei-der-Gebaeudeautomation), [DIN EN ISO 52120-1:2025-02](https://www.dinmedia.de/en/standard/din-en-iso-52120-1/345026735)) | Poise-Funktionsliste auf die Tabellen-Funktionen der Norm mappen; heute wirksam ≈ Klasse C, Bausteine für A vorhanden | **Funktions-Mapping als Doku + Diagnose-Attribut** („erfüllte 52120-Funktionen"); Klasse-A-Lücken (bedarfsgeführter Vorlauf, Monitoring) gezielt schließen (M4/M2) |
| **EN 15500-1** — Regelgüte-Kennwert CA für Einzelraumregler | Ohne modulierten Live-Regler kein CA-Nachweis möglich | **CA-artige Regelabweichungs-Metrik als Sensor** (zeitgewichtete \|Ist−Soll\| im Komfortfenster) = zugleich das messbare Flip-Kriterium für TPI/PI/MPC (M1) |
| **Ökodesign/ErP, VO (EU) 811/2013** — Temperature-Control-Klassen (I–VIII); Klasse V (modulierender Raumregler) +3 %, VI (Witterungsführung+Raumsensor) +4 %, VIII (Multi-Raumsensor) +5 % Verbund-Bonus ([Sorel-Erläuterung](https://www.sorel.de/en/erp-class-compound-system-blog/)) | Poise+Hub+Vorlauf-Allokator entspricht funktional Klasse VI/VIII — als Software ohne Label, aber als *Architektur-Blaupause* | Witterungsgeführte Vorlauf-Führung (M4) explizit an Klasse-VI/VIII-Funktionalität ausrichten; Doku „funktionale Äquivalenz, kein Label" |
| **ASR A3.5** — Arbeitsstätten: +26 °C-Schwelle, Stufen 26/30/35 °C mit Maßnahmenpflichten | Cap ist umgesetzt; Stufenlogik fehlt | Office-Modus: Stufen als Ampel/Ereignisse (Melde-, nicht Regelfunktion) (M6) |
| **DIN 4108-2 / EN ISO 13788** | Kern korrekt; f_Rsi fix, Über-Eis fehlt | f_Rsi konfigurierbar/lernbar; Ice-Zweig der Magnus-Formel; RH-Sensor-Ausfall → Repair-Issue (M0/M2) |
| **DIN 1946-6 / VDI 6022** | Bewusstes Nicht-Ziel | Beibehalten; nur Monitoring/Hinweise |
| **Cyber Resilience Act (EU) 2024/2847** — volle Geltung ab 11.12.2027; **rein nicht-kommerzielle OSS ist ausgenommen** ([cyber-regulierung.de](https://www.cyber-regulierung.de/eu-cybersecurity-regulierung/cra-open-source-software/), [BSI](https://www.bsi.bund.de/DE/Themen/Unternehmen-und-Organisationen/Informationen-und-Empfehlungen/Cyber_Resilience_Act/cyber_resilience_act_node.html)) | Poise (MIT, unentgeltlich, kein kommerzieller Support) fällt unter die OSS-Ausnahme; bei späterer Kommerzialisierung greifen Herstellerpflichten | Security-Praxis trotzdem CRA-nah halten (ADR-0022 ist schon auf Kurs): SBOM=„keine Dependencies", Security-Policy, Coordinated-Disclosure-Hinweis, gepinnte CI-Actions |
| **DSGVO** | Lokale Klimadaten, keine Cloud — minimal betroffen; Diagnostics-Redaktion existiert | Redaktionslücke (compressor_group-Namen in Live-Daten) schließen; Doku-Satz zur Datenhaltung |

---

## 4. Bauphysik & Thermokomfort: fachliche Weiterentwicklung

1. **Adaptives Komfortmodell scharf schalten (Free-Running/Sommer).** Formeln sind implementiert und getestet; nach Härtung der Referenzrahmen-Bugs (Luft vs. operativ, Review) als Opt-in live schalten: im Sommer ohne aktive Kühlung führt das adaptive Band (Θ_comf = 0,33·T_rm + 18,8) statt des fixen Kühlbands → weniger Kühlbedarf bei norm-gedeckter Behaglichkeit.
2. **Ventilator-Kühlwirkung nutzen (ASHRAE 55 / Elevated Air Speed).** Erhöhte Luftgeschwindigkeit erlaubt höhere Betriebstemperaturen; der Cooling Effect wird SET-basiert berechnet, Referenzimplementierung [`pythermalcomfort.cooling_effect()`](https://pythermalcomfort.readthedocs.io/en/latest/documentation/models.html); typischer Bereich Deckenventilator/Standventilator 0,36–0,8 m/s ([CBE Fans Guidebook](https://cbe-berkeley.gitbook.io/fans-guidebook/full-guidebook/codes-and-standards)). Konkret: läuft `fan_only`/Ventilator, Kühlsollwert um den berechneten CE-Offset (typ. 1–2,5 K) anheben und `operative.py` mit realistischer v speisen statt fix 0,1 m/s. **Das ist der Schlüssel zu „kühlen ohne Kompressor"** — Umwälzung wird vom Komfort- zum Energiesparfeature.
3. **PMV/PPD als Opt-in-Diagnose (ISO 7730).** Kein Regelziel (clo/met sind im Wohnraum nicht messbar), aber als Diagnose mit dokumentierten Defaults (Winter 1,0 clo / Sommer 0,5 clo, 1,2 met) sinnvoll: PPD-Sensor + Kategorie-Verortung. Pure-stdlib-Implementierung der ISO-7730-Gleichungen passt zur No-Dependency-Doktrin (pythermalcomfort nur als Referenz für Testvektoren).
4. **Feuchte normgerecht:** Kategoriegebundene RH-Grenzen (EN 16798-1 Anhang B: Entfeuchtungs-Auslegung Cat I 50/II 60/III 70 %) + absolutes Kriterium ~12 g/kg; Taupunktführung für Kühlflächen ist mit `dewpoint+2 K` schon angelegt. Absolutfeuchte-Funktion (g/m³) ergänzen → „Lüftungsempfehlung"-Binary-Sensor (innen/außen-Vergleich).
5. **Schimmel: von statisch zu dynamisch.** Stufe 1: f_Rsi konfigurierbar (Altbau < 0,7) und perspektivisch aus EKF-Envelope-Kopplung schätzen; Über-Eis-Sättigung (Alduchov-Eskridge ice). Stufe 2: zeitintegrierendes Risiko (Isoplethen-/VTT-Mould-Index-Ansatz) statt Momentan-80-% — weniger Überheizen bei kurzen Feuchtespitzen, mehr Schutz bei Dauerfeuchte = Energie *und* Sicherheit.
6. **Lokale Behaglichkeit als Warnungen:** |MRT − T_Luft| > Schwelle → „kalte Fensterfläche"-Hinweis (Strahlungsasymmetrie-Proxy aus vorhandener virtueller MRT, ISO-7730-motiviert, keine neue Hardware).
7. **Träge Systeme (FBH/Wärmepumpe):** Nachtabsenkung lohnt bei hoher Trägheit kaum — nach dem Setback-Fix eine dynamikprofil-abhängige Absenkempfehlung (VERY_SLOW → flache Absenkung 1–2 K, Hinweis statt Dogma); Optimal-Stop/Start-Latches (Review) sind Voraussetzung.

---

## 5. Roadmap-Phasen

### M0 — Stabilisierung (sofort, v0.111–v0.113)
Die P0-Liste aus dem Review (§9): Kühlgeräte-Sicherheitssemantik, Kessel-Robustheit, OFF-Frostschutz, Setback-Entkopplung, Lernpausen-Fix, Fenster-Detektor-Härtung, Reconfigure-Fixes, Forecast-Timeout, Doku-/Versions-Drift. **Abnahme:** neue Regressionstests je Fix; Plant um Sensor-Quantisierung + Rauschen erweitert, damit V5/V6 closed-loop reproduzierbar sind.

### M1 — Messbarkeit & Winter-Scharfschaltung (Heizsaison 2026/27)
- **Regelgüte-Metrik** (EN-15500-CA-artig: zeitgewichtete |Ist−Soll| im Komfortfenster) + Pendel-Detektor (Regimewechsel/h) als Sensoren → die ADR-0033-Flip-Kriterien werden ausführbare Zahlen statt Prosa.
- Golden-File-Replays realer anonymisierter Trajektorien (löst ADR-0011 ein); Tick-Dauer-Messung (schließt ADR-0020).
- Vor dem Flip: PI-Anti-Windup (Conditional Integration), Bumpless Profile-Switch, Hysterese/Dwell im MPC-Controller-Seam, MPC-Rollout mit Forecast+Solar füttern (heute konstantes t_out), Preheat/Coast-Latch.
- **Dann:** PI-Kompensator und TPI-Direktventil (TRVZB) von Shadow auf aktiv — gated auf die Metrik, pro Geräteklasse.
- EKF: `identified` um Parameter-Kovarianz-Gate ergänzen; Seasonless-Episoden-Erfassung (killt den Quantisierungsbias).

### M2 — Energie & Alltag (parallel zur Heizsaison)
- Setback/Presets wirksam (V3-Fix) + **Presence/Geofencing/Kalender** (VTherm-Parität, §2.2) + Timed Presets.
- **Energy-Dashboard-Anschluss:** geschätzte Heizenergie als Long-Term-Statistics (`state_class: total_increasing`), HDH-Report dorthin migrieren; EN-16798-**Anhang-C-Langzeitstatistik** (Stunden außerhalb Band je Kategorie) als Sensor — „normbasiert" wird messbar.
- Onboarding: Config-Flow in Abschnitte/Steps (Pflicht → Komfort → Sensorik → Experte), Selector-Übersetzungen, Repair-Hinweise „Schimmelschutz inaktiv (kein RH-Sensor)"/„kein Außensensor"; brands-PR (Bronze abschließen), dann Silber-Lücken (Coverage 95 %).
- TRV-Kalibrierung live (BT-Parität, §2.2 Punkt 5); Kalkschutzfahrt.

### M3 — Sommer: Kühlen, Entfeuchten, Umwälzen (Frühjahr–Sommer 2027)
- Kühlrichtungs-Sicherheit (M0) + adaptive Bänder live (§4.1) + **Fan-CE-Offset** (§4.2) + kategoriegebundene Feuchte + Taupunktführung (§4.4); Dry-Pfad um Mindestlauf-/Lockout-Zeiten härten; `beta_c`-Anregung füttern, sobald Kühlen aktuiert (Sommer-Identifikation).
- Sommer-Validierungskampagne analog Kaltsaison: eigene Closed-Loop-Szenarien (AC, Fenster, Feuchte).

### M4 — Multizonen & Erzeuger (Heizsaison 2027/28)
- `ResourceRelease`-Rückkanal verdrahten → Load-Shedding mit Enforcement (Zone komponiert Hub-Cap als High-Precedence-Constraint — der Solver nimmt das bereits generisch entgegen).
- **Witterungsgeführte Vorlauf-Führung** (Heizkurve aus EKF-Bedarf statt statischer design_flow_temp) → funktional ErP-Klasse VI/VIII, ISO-52120-Klasse-A-Baustein.
- Kompressorgruppen: eigene Timer (min_off ≥ 600 s), Persistenz, `max_starts_per_h` anbinden. Kessel: PWM/Modulation statt binär, System-Heating-Failure (Kessel ON, aber kein Gap schließt sich).
- PWM/Switch-Aktortyp (§2.2 Punkt 6) + Floor-Schutz (Punkt 7).

### M5 — Plattform & Community-Skalierung (laufend)
- Quality Scale Gold-Kandidatur (Docs, disabled-by-default-Diagnose-Entities — löst zugleich die Recorder-Last, icons.json); HACS-Default-Aufnahme; °F/Locale-Support der Card, Editor-Vervollständigung, History-Refresh; weitere Sprachen via Community.
- Doku-Offensive: „Poise & GEG/52120/SRI", Erklärseiten je bindender Ursache (Card verlinkt), Vergleichsseite zu BT/VTherm (ehrlich).
- ADR-Status-Linter in CI (Tabelle vs. Header vs. Code); Actions per SHA pinnen; Dependabot; wöchentlicher Lauf gegen HA-dev.

### M6 — Differenzierung Office & Fachwelt (2028)
- **Office-Paket:** Bulk-/Template-Onboarding (Area-Import), Wochen-/Kalenderprofile, ASR-Stufenampel, CA-/Anhang-C-Compliance-Report (CSV/Long-Term-Stats), 20-Zonen-Performancebudget.
- KNX-Expose (ADR-0019) für die Integrator-Zielgruppe; PMV/PPD-Diagnose (§4.3); Mould-Index (§4.5); SRI-Selbsteinstufungs-Doku.
- Optional erkunden: Preissignal-/PV-Überschuss-Hooks (EPEX/Tibber-Sensor als Eingang der Komfort-vs-Energie-Gewichtung; Wärmepumpen-Vorlauf zuerst) — bewusst *nach* der Regelgüte-Basis, sonst optimiert man auf ein unkalibriertes Modell.

---

## 6. Priorisierung, Risiken, KPIs

**Reihenfolge-Logik:** Sicherheit (M0) → Messbarkeit (M1) → sichtbarer Nutzen (M2) → Saisonfähigkeit (M3) → Systemebene (M4). Community-Wachstum (M5) läuft parallel, Differenzierung (M6) zuletzt — Vertrauen entsteht bei Thermostaten durch Zuverlässigkeit, nicht durch Featurezahl (Kernlektion aus den BT-/VTherm-Issue-Trackern).

**Top-Risiken:**
1. *Ein-Personen-Bus-Faktor + „Add files via upload"-Git-Historie* → echte Commit-Historie, CONTRIBUTING, Issue-Templates (M5) senken die Beitragshürde.
2. *Live-Flip der Regler enttäuscht* → deshalb Metrik vor Flip (M1), pro Geräteklasse, Rollback-Schalter.
3. *HA-API-Drift* (climate-Domain entwickelt sich weiter, z. B. TURN_ON/OFF-Pflicht seit 2024.2, Humidity-/Fan-Konventionen — [Climate-Entity-Doku](https://developers.home-assistant.io/docs/core/entity/climate/)) → wöchentlicher CI-Lauf gegen HA-dev (M5).
4. *Feature-Parität-Falle*: VTherm hat 8 Jahre Vorsprung an Kleinfunktionen — nicht alles nachbauen, sondern die Matrix-Lücken mit Hebel (Presence, Kalibrierung, Shedding-Enforcement) schließen und den Norm-/Physik-Vorsprung ausbauen.

**KPIs je Meilenstein:** M0: 0 offene P0, Fehlalarmrate Fenster-Detektor < 1/Woche/Zone in der Noisy-Plant; M1: CA-Metrik live, TPI/PI aktiv auf ≥ 2 Geräteklassen mit Metrik-Verbesserung ggü. Setpoint-Durchgriff; M2: gemessene Setback-Absenkung = konfigurierte; Energy-Dashboard-Integration; Bronze vollständig, Silber beantragt; M3: Sommer-Suite grün, CE-Offset aktiv; M4: Shedding wirksam (Zonen-Cap nachweisbar), witterungsgeführter Vorlauf; M5: HACS-Default, >1.000 aktive Installationen; M6: erstes dokumentiertes Office-Deployment ≥ 10 Zonen.

---

## Quellen

- [Versatile Thermostat (jmcollin78)](https://github.com/jmcollin78/versatile_thermostat) · [Community-Thread](https://community.home-assistant.io/t/versatile-thermostat-a-full-feature-thermostat-energy-door-window-presence-motion-preset-management/546761)
- [Better Thermostat (KartoffelToby)](https://github.com/KartoffelToby/better_thermostat) · [Doku/Konfiguration](https://better-thermostat.org/configuration/) · [Issue #1410 (Kalibrier-Oszillation)](https://github.com/KartoffelToby/better_thermostat/issues/1410)
- [HASmartThermostat PID (ScratMan)](https://github.com/ScratMan/HASmartThermostat) · [Advanced Heating Control V5 (panhans)](https://hablueprints.directory/blueprint/401-advanced-heating-control-v5/)
- [GEG §63 Raumweise Regelung](https://www.buzer.de/63_GEG.htm) · [Haufe: Raumweise Regelung im Bestand](https://www.haufe.de/immobilien/verwalterpraxis-gold/bestandsgebaeude-geg-122-raumweise-regelung-der-raumtemperatur_idesk_PI44806_HI16025933.html) · [PG-GEG-Auslegung §§61/63](https://geg-info.de/geg_praxisdialog/211102_10_geg_auslegung_aelbsttaetige_regelungseinrichtungen_zentralheizungen.pdf)
- [DIN EN ISO 52120-1:2025-02](https://www.dinmedia.de/en/standard/din-en-iso-52120-1/345026735) · [Danfoss zur EN ISO 52120](https://www.danfoss.com/de-de/about-danfoss/articles/dhs/new-en-iso-52120-bacs-standard-for-building-efficiency/) · [SHKwissen GA-Effizienzklassen](https://www.haustechnikdialog.de/SHKwissen/3300/Effizienzklassen-bei-der-Gebaeudeautomation)
- [Sorel: ErP-Klassen von Verbundanlagen (Temperature-Control-Klassen I–VIII)](https://www.sorel.de/en/erp-class-compound-system-blog/) · VO (EU) 811/2013 (Klassenprozente aus Verordnungstext)
- [CRA & Open Source](https://www.cyber-regulierung.de/eu-cybersecurity-regulierung/cra-open-source-software/) · [BSI zum CRA](https://www.bsi.bund.de/DE/Themen/Unternehmen-und-Organisationen/Informationen-und-Empfehlungen/Cyber_Resilience_Act/cyber_resilience_act_node.html) · [EU-Kommission CRA](https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act)
- [pythermalcomfort-Modelle (PMV, Cooling Effect)](https://pythermalcomfort.readthedocs.io/en/latest/documentation/models.html) · [CBE Fans-for-Cooling Guidebook](https://cbe-berkeley.gitbook.io/fans-guidebook/full-guidebook/codes-and-standards) · [ASHRAE 55 (Überblick)](https://en.wikipedia.org/wiki/ASHRAE_55)
- [HA Climate-Entity Developer-Doku](https://developers.home-assistant.io/docs/core/entity/climate/) · [HA-Releases 2026](https://www.home-assistant.io/blog/2026/06/03/release-20266/)

*Normwerte zu EN 16798-1 (Kategorien, Anhang B), ISO 7730, DIN 4108-2/EN ISO 13788 und VO (EU) 811/2013 stammen aus dem Fachwissen der Analyse und wurden gegen die Implementierung in `custom_components/poise/comfort/` quergeprüft; für eine Veröffentlichung mit Normzitaten sind die Originaltexte heranzuziehen.*
