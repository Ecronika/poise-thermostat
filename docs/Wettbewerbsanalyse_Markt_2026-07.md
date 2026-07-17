# Wettbewerbsanalyse Markt — Erweiterung der Best-of-Wettbewerberliste (Stand 2026-07-17)

**Zweck:** Das ursprüngliche Best-of-Konzept stützte sich auf sieben Wettbewerber: ThermoSmart (TS), RoomMind (RM), Vesta, Versatile Thermostat (VT), Adaptive Climate (AC), schoolboyqueue (SBQ), Better Thermostat (BT). Dieses Dokument (a) aktualisiert den Status dieser sieben, (b) erweitert die Liste um weitere Markt-Wettbewerber im Smart-Home-/Home-Assistant-Bereich und (c) beantwortet die Frage: **Mit welchen Lösungen lohnt sich ein Leistungsvergleich?**

**Methodik:** Marktrecherche in fünf Segmenten (HACS-Integrationen, Baseline-Status, Blueprints/AppDaemon, kommerzielle Ökosysteme, fortgeschrittene OSS/MPC-Projekte); jeder Kandidat wurde einzeln adversarial gegen Repo-/Produktseiten verifiziert (Existenz, Regelungsansatz, Wartungsstand, Verbreitung). Alle Zahlen (Stars, Releases, Daten) Stand **2026-07-17**. Abgrenzung: Dieses Dokument ist eine *Markt*-Analyse; die quellcode-verifizierten *Technik*-Analysen bleiben Sache der ADRs (ADR-0000-Prozess).

**Begriffsklärung „Leistungsvergleich":** gemeint ist ein messbarer Regelgüte-/Ergebnisvergleich nach der Poise-eigenen Metrik-Infrastruktur — EN-15500-1-Control-Accuracy (`comfort_deviation_k`, `time_in_band`, `cycles_per_hour`, ADR-0055), Optimal-Start-Treffgenauigkeit (ADR-0025/0044) und HDH-kWh-Effizienz (ADR-0045) — im Closed-Loop-Harness (ADR-0011) und/oder als Feld-A/B auf identischer Hardware. Voraussetzung ist, dass die Lösung in HA closed-loop eine Raumtemperatur führt (Sollwert/Ventil schreibbar, Ist messbar).

---

## 1. Status der sieben Baseline-Wettbewerber (07/2026)

| Codename | Projekt | Status 07/2026 | Vergleich weiterhin sinnvoll? |
|---|---|---|---|
| **BT** | [KartoffelToby/better_thermostat](https://github.com/KartoffelToby/better_thermostat) · 1,5k ★ | **Strategisch verändert:** v1.8.0 (02.06.2026) ist ein Komplett-Rewrite (>50 000 geänderte Zeilen) mit **MPC, TPI, PID und „AI Time Based" als wählbaren Regelalgorithmen plus direkter Ventilsteuerung**; 1.9.0-Betas (07/2026) ergänzen Cooling-Presets und Z-Wave-Ventil-Quirks. Wartungsflaute 2024–2026 ist beendet. | **Ja — Pflicht.** BT ist vom „reinen Kalibrierer" zum direkten Regelungs-Wettbewerber geworden. Die ADR-Befunde zu BT (nur Kalibrierung, binärer Außen-Lockout, kein Optimal-Start) beziehen sich auf ≤1.7 und müssen bei Zitaten künftig versioniert werden. |
| **VT** | [jmcollin78/versatile_thermostat](https://github.com/jmcollin78/versatile_thermostat) · 1,1k ★ | Sehr aktiv: v10.0 (29.04.2026) bringt **„Smart PI"** (adaptiv) neben TPI/auto-TPI sowie einen **Plugin-Mechanismus** für Dritt-Erweiterungen (Ökosystem-Öffnung). | **Ja — Pflicht.** TPI-Referenz-Baseline mit hoher Verbreitung. |
| **TS** | [Mikasmarthome/ThermoSmart](https://github.com/Mikasmarthome/ThermoSmart) · 10 ★ | Aktiv: v1.2.0 (09.07.2026). Lernende Gebäudethermik (3-stufiges Beobachtungs-Staging), TPI mit gelernten Koeffizienten, direkte Ventilsteuerung, wetterprädiktives Preheating, **explizite Sonoff-TRVZB-Geräteprofile**. | **Ja.** Trotz Mini-Verbreitung der direkteste „Poise-Klon" auf identischer Zielhardware — der interessanteste Lernkurven-Vergleich (EKF vs. Beobachtungs-Staging). |
| **RM** | [snazzybean/roommind](https://github.com/snazzybean/roommind) · 368 ★ | Sehr aktiv: v1.7.5 (05.07.2026), hohe Release-Kadenz, erfordert HA 2026.2+. EKF-Thermalmodell, proportionale Ventilsteuerung, Solar, Schimmelschutz, Beschattung. | **Ja — Pflicht.** Gleiche Waffengattung (EKF vs. EKF), inzwischen drittgrößte aktiv gepflegte Integration im Segment. |
| **Vesta** | [portbusy/ha-vesta](https://github.com/portbusy/ha-vesta) · 11 ★ | Jung (Repo 03/2026), moderat aktiv (v1.7.7, 04/2026). Konzeptionell ein Scheduler-/Präsenz-Layer (Raten-Lernen, GPS-Preheating), **kein Regelalgorithmus**. | **Nein** — nur noch Feature-Referenz (GPS-Annäherungs-Preheating, pragmatisches Raten-Lernen). |
| **AC** | msinhore/adaptive-climate (+ [Blueprint](https://github.com/msinhore/adaptive-climate-blueprint) · 22 ★) | **Integrations-Repo existiert nicht mehr (404).** Blueprint seit 07/2025 ohne Aktivität, 0 Releases. | **Nein — abschreiben.** ASHRAE-55-Adaptivkomfort bleibt Konzept-Referenz (Pendant zu Poises EN 16798-1), aber kein Benchmark-Gegner mehr. |
| **SBQ** | [schoolboyqueue/home-assistant-blueprints](https://github.com/schoolboyqueue/home-assistant-blueprints) · 10 ★ | Ruhend: letzte Commits 01.02.2026, letztes Release v1.8.1 (01/2026). | **Nein** — Feature-Referenz (einzige bekannte Blueprint-Umsetzung von EN-16798-Komfort + Psychrometrie/Taupunkt/Enthalpie; Ventilator-Integration ins Komfortmodell). |

---

## 2. Erweiterung: neue Wettbewerber im Feld

### 2.1 HA-Integrationen mit eigenem Regelungsanspruch (direkteste Erweiterung)

| Projekt | Ansatz | Aktivität / Verbreitung | Einordnung |
|---|---|---|---|
| **[HASmartThermostat](https://github.com/ScratMan/HASmartThermostat)** (ScratMan) | Klassischer PID + PWM (15-min-Zyklus), 7 Autotune-Regeln (README warnt: Autotune „not recommended"), Außentemp-Kompensation | 527 ★ · langsam, aber aktiv (v2026.2-Betas 02/2026) | **Leistungsvergleich** — die klassische PID-Baseline; genau der Vergleich („gut getunter PID vs. lernendes System"), den Poises Lernansatz rechtfertigen muss |
| **[SAT — Smart Autotune Thermostat](https://github.com/Alexwijn/SAT)** (Alexwijn) | PID mit Auto-Gain-Tuning + selbstlernende Heizkurve, Kessel-Vorlauf via OpenTherm-Modulation, Overshoot Protection, Multi-Room-TRV-Sync | 247 ★ · aktiv (v4.2.1, 01/2026) | **Leistungsvergleich (disziplinspezifisch)** — regelt primär den Kessel-Vorlauf (OpenTherm-Hardware), Poise primär TRVs; fair vergleichbar auf Ebene Raumhaltegüte/Optimal-Start. Läuft notfalls auch ohne OT als PID-On/Off |
| **[Dual Smart Thermostat](https://github.com/swingerman/ha-dual-smart-thermostat)** (swingerman) | Erweiterte Hysterese für Heizen+Kühlen, Auto-Mode-Prioritäts-Engine (heat/cool/dry/fan), AUX-Heizstufe, Fußboden-Limits | 226 ★ · sehr aktiv (v0.13.1, 06/2026) | **Leistungsvergleich** — der „gut gemachte klassische" Regler; zusätzlich relevant für Poises Kühl-/Dry-Pfad (ADR-0050/0051), bereits ADR-Sekundärquelle |
| **[MultiZone Thermostat](https://github.com/vindaalex/multizone-thermostat)** (vindaalex) | On/Off, **PID auf proportionale Ventile**, Wetterkompensation; Master-Satellite-Mehrzonen mit Wärmebedarfs-Aggregation | 42 ★ · aktiv, niedrige Kadenz (v0.7.3, 05/2026) | **Leistungsvergleich (Nische)** — konzeptionell Poise am nächsten unter den Klassikern: PID-Direktventil + Mehrzonen-Kesselbedarf, nur ohne Lernen/MPC |
| **[Adaptive Climate](https://github.com/afewyards/ha-adaptive-climate)** (afewyards; Namenskollision mit msinhore-AC!) | **Lernender 5-Term-PID** (Auto-Gain-Optimierung aus Heizzyklus-Metriken mit Konfidenz/Rollback), physikbasierte Initialisierung, prädiktives Vorheizen, Mehrzonen; stark erweiterter HASmartThermostat-Fork | 2 ★ · sehr aktiv, explizit experimentell (v0.65.1, 06/2026) | **Beobachten + Leistungsvergleich light** — dieselbe Ambition wie Poise mit PID- statt EKF/MPC-Mitteln; null Verbreitung, aber fachlich der spannendste „lernende PID"-Gegner |
| **[Intelligent Heating Pilot](https://github.com/RastaChaum/Intelligent-Heating-Pilot)** (RastaChaum) | Optimal-Start-Layer **auf** Versatile Thermostat: Online-Lernen der Aufheizrate (Trimmed-Mean, Zyklenerkennung), Adaptive Start | 47 ★ · Beta, seit 04/2026 ruhend | **Disziplin-Benchmark Optimal-Start** — kein Gesamtregler; vergleichbar allein in der Disziplin Vorheizzeitpunkt-Treffgenauigkeit |
| **HA Core [generic_thermostat](https://www.home-assistant.io/integrations/generic_thermostat/)** | Reine Hysterese (cold/hot tolerance, min_cycle) | Core; verbreitetster Thermostat-Baustein (~4 % der Analytics-Installationen) | **Leistungsvergleich — Pflicht-Nulllinie.** Ohne Hysterese-Baseline ist kein Benchmark-Ergebnis einordbar. (Hinweis: `bang_bang` ist ESPHome, nicht HA-Core.) |
| [Climate Group Helper](https://github.com/bjrnptrsn/climate_group_helper) | Gruppierung + TRV-Kalibrierung (absolut/Delta/skaliert, Heartbeat), Sync-Modi; Regelung verbleibt im TRV | 107 ★ · wöchentliche Releases, HACS-Default | Feature-Referenz (Kalibrier-Modi, Multi-Geräte-Sync); Kalibrier-Ansatz im Benchmark bereits durch BT abgedeckt |
| [Smarter Thermostat](https://github.com/cr212/smarter_thermostat) (cr212) | BT-Fork mit MPC (physikalisches Raum-/Heizkörpermodell), PID-Autotune, TPI | 0 ★ · aktiv (v1.8.0-cr2, 05/2026) | Nur Algorithmus-Referenz; beobachten, ob upstream einfließt |
| [Valves](https://github.com/rusitschka/valves) (rusitschka) | Direkte absolute Ventilposition + Lernen der Raum-/Ventilcharakteristik | 11 ★ · verwaist (letzter Commit 12/2023) | Konzept-Beleg für Poises TPI-Direktventil-Idee; kein Benchmark-Gegner |
| [Smart Offset Thermostat](https://github.com/fabilau/hass_smart_offset_thermostat) | Lernender Sollwert-Offset (TRV- vs. Raumsensor) — funktional ein simpler Verwandter von Poises PI-Kompensator (ADR-0037) | 5 ★ · ruhend seit 02/2026 | Feature-Referenz |
| [Smart Thermostat](https://github.com/hacker-cb/hassio-component-smart-thermostat) (hacker-cb) | PID+PWM, Aktor-Abstraktion switch/climate/number | 66 ★ · ruhend seit 01/2025 | Redundant zu HASmartThermostat |
| [ClimateAdvisor](https://github.com/gunkl/ClimateAdvisor) (ex SmartHVAC) | Regelbasiert + Lern-Engine, optional **LLM (Claude-API) für Erklär-Berichte** über einem deterministischen Regler; US-HVAC-Fokus | 2 ★ · sehr aktiv, v0.5 (07/2026) | Feature-Referenz — Muster „LLM erklärt, regelt aber nicht" ist für Poises Diagnose-/Card-Story interessant |
| [Heating Analytics](https://github.com/thuemah/heating_analytics) (thuemah, 2026-Neuerscheinung) | Lokales Gebäudephysik-Lernen (Trägheit, Solar, Wind) + kWh-Prognose; bewusst feed-forward, **regelt nicht** | 10 ★ · sehr aktiv (v1.3.11, 07/2026) | Feature-Referenz für Modell-Identifikation/Validierung der EKF-Schätzungen |
| [haos_mpc](https://github.com/sebzuddas/haos_mpc) (sebzuddas) | Forschungsprojekt: EKF + PySINDy-Systemidentifikation + MPC für HA-Heizung | 0 ★ · verwaist (06/2024), unfertig | Beleg, dass Poises Architektur dem Stand der Technik entspricht; SINDy als interessante Alternative zum EKF-Parameterlernen |

### 2.2 Blueprint-/AppDaemon-Ebene

| Projekt | Ansatz | Aktivität / Verbreitung | Einordnung |
|---|---|---|---|
| **[Advanced Heating Control](https://github.com/panhans/HomeAssistant)** (panhans) | De-facto-Standard der Blueprint-Welt: Zeitpläne, Anwesenheit/Proximity, Fenster, Kalibrierung vieler Hersteller, seit V5 **dynamische proportionale Ventilpositionierung** (`valve_opening_degree`, 3 Modi) — kein Lernen, keine Prädiktion | ~7 800 Blueprint-Imports (V5 + Dev), 158 ★, Forum-Thread >3 400 Antworten (aktiv bis 06/2026); Repo-Commits zuletzt 01/2026 | **Leistungsvergleich — Pflicht.** Die wichtigste Referenz „einfache Heuristik vs. lernende Regelung", schreibt Sollwerte *und* Ventilöffnung auf identischer Hardware (TRVZB) |
| **[Sonoff TRVZB External Temperature Blueprint](https://github.com/shaggee/Sonoff-TRVZB-external-temp-report-and-update-interval)** (photomoose-Derivat) | Schreibt zyklisch externen Raumsensor in `external_temperature` des TRVZB → interner TRV-Regler regelt auf echte Raumtemperatur; Fail-safe-Fallback | Forum-Thread (seit 02/2025) mit 170+ Antworten, mehrere Varianten; v1.6.0 (04/2026) | **Leistungsvergleich — Pflicht-Baseline auf Zielhardware:** „TRVZB-interner Regler + externer Sensor" ist die verbreitetste Community-Antwort auf genau Poises Kernproblem |
| [Schedy](https://github.com/bob1de/hass-apps) (AppDaemon) | Deklarative Sollwert-Regel-Engine; kein Regler | 88 ★ · Maintenance-only seit 02/2022 | Nur Konzept-Referenz (Override-Semantik, Setpoint-Verify/Resend) |
| [Scheduler component + card](https://github.com/nielsfaber/scheduler-component) (nielsfaber) | Generischer Zeitplan-Scheduler mit Lovelace-UI | ~891/~1 200 ★, Card aktiv (v4.0.19, 06/2026) | UX-Referenz für Zeitplan-Bedienung (Card-Vertrag), kein Regler |
| „Window open, climate off"-Blueprint-Familie | Fenster-offen-Pause mit Entprellung + Restore | Thread seit 2020, 10+ Seiten, aktive Derivate | Definiert Community-Erwartung an Poises Fenster-Semantik (ADR-0041) |
| [HEATHER 3](https://github.com/AndySymons/HEATHER-3-Heating-Control-for-Home-Assistant) (AndySymons) | Kalenderbasierte Sollwertführung, TRV-Verify/Retry, Zonen-/Kesselbedarf per YAML-Packages | 0 ★ · seit 01/2025 inaktiv | Konzept-Referenz (Setpoint-Verify/Retry-Robustheit) |

### 2.3 Kommerzielle Ökosysteme (der Maßstab der Endnutzer)

| Produkt | Regel-Intelligenz im Produkt | HA-Anbindung | Einordnung |
|---|---|---|---|
| **Sonoff TRVZB** (Poises Ziel-Aktor) | Bis FW 1.4.x Zweipunkt/Hysterese; **seit FW 1.4.4 (02/2026) optionaler „Adaptive Mode" = PID-Ventilregelung im Gerät** (default aus; in Z2M ~2.9.x als „Smart Temperature Control", ZHA-Quirk existiert) | Voll lokal (Z2M/ZHA), Ventilöffnungsgrad schreibbar | **Leistungsvergleich — der fairste Benchmark überhaupt:** identische Hardware, drei Regler: TRVZB-Hysterese vs. TRVZB-PID (Adaptive) vs. Poise-TPI-Direktventil. Für Poise-Betrieb muss Adaptive Mode sicher deaktiviert sein (Interferenz!); FW-Version als Versuchsvariable protokollieren |
| **Danfoss Ally eTRV** | Technisch anspruchsvollster Lokal-Kommerz-TRV: `schedule_with_preheat` (Optimal Start im Gerät), Adaptation Run (Ventilkennlinien-Lernen), Multi-TRV-Lastabgleich pro Raum, externer Sensor mit Auto-Offset | Voll lokal (Z2M/ZHA) | **Leistungsvergleich:** Ally-Preheat vs. Poise-Optimal-Start bei gleicher Raumklasse (bereits ADR-0059-Referenz) |
| **tado° (V3+/X)** | Early Start (gelerntes Vorheizen), Auto-Assist (Geofencing, Fenster), Wetter | Cloud-API seit 01/2026 hart quotiert (100 Req/Tag ohne Abo); **tado X lokal via Matter**; V3+ lokal via HomeKit/`tado_ce` (150 ★, v4.2.0 07/2026) | **Leistungsvergleich (Feld-A/B):** der Maßstab, an dem Endnutzer „selbstlernende Heizung" messen; nur über die lokalen Pfade fair reproduzierbar |
| **Homematic IP Evo (HmIP-eTRV-E)** | Adaptive In-Device-Regelung (~4 Tage Einschwingen, gelernte Parameter + PI), automatischer dynamischer hydraulischer Abgleich (Fraunhofer-IEE-bestätigt) | Voll lokal via RaspberryMatic/OpenCCU + „Homematic(IP) Local" | **Leistungsvergleich (DACH-Referenz):** der wahrscheinlichste „Warum nicht einfach Homematic?"-Einwand der Zielgruppe; Ventilöffnung als Sensor lesbar |
| **AVM FRITZ!DECT 302 / Smart Thermo 302** | „Adaptiver Heizbeginn" (einfaches Optimal Start, max. 1 h Vorlauf); sonst Zweipunkt | Lokal via FRITZ!Box (Core-Integration); bekannte Doppelherrschaft FRITZ!OS-Zeitpläne vs. HA | **Leistungsvergleich (DE-Marktrelevanz):** „hab ich schon zu Hause"-Baseline; gut schlagbar, aber marktrelevant. Zeitplan-Übersteuerung im Versuchsdesign kontrollieren |
| **Shelly TRV / BLU TRV** | Geräteinterner „adaptive heating control algorithm" (PID-artig, stufenlos); externer Sensor; direkte Ventilpositions-Übersteuerung möglich (deaktiviert interne Regelung) | Voll lokal; BLU TRV seit HA 2025.2 in Core | **Leistungsvergleich:** zweitwichtigster Hardware-Benchmark nach TRVZB; perspektivisch sogar als Poise-Aktor denkbar |
| **Schneider/Drayton Wiser** | TPI im Hub, „Comfort Mode" (Optimal-Start-artig, gelernte Aufheizrate), Eco Mode (Wetter); **Heat-Demand-% pro Raum** exponiert | Voll lokal (REST-API des Hubs; [HACS-Integration](https://github.com/asantaga/wiserHomeAssistantPlatform) 315 ★, v3.4.19 02/2026) | **Leistungsvergleich:** Poises eigene Bausteine (TPI + Optimal Start + Bedarfs-%) in Firmware gegossen, ungewöhnlich gut messbar |
| **Honeywell/Resideo evohome** | Multizonen (12), zonaler Wärmebedarf → aggregierte Kesselanforderung (TPI/OpenTherm), Optimal Start/Stop, Fuzzy-Logik im HR92 | Cloud (Core, „legacy") oder **voll lokal via [ramses_cc](https://github.com/ramses-rf/ramses_cc)** (sehr aktiv, v0.58.2 vom 16.07.2026; liest Heat-Demand pro Zone) | **Leistungsvergleich (Disziplin Mehrzonen/Kessel):** direkteste kommerzielle Analogie zu Poises Architektur (ADR-0038/0039); Hardware-Beschaffung nötig |
| **Plugwise Adam + Tom/Floor/Lisa** | Zonenregelung mit OpenTherm-Kesselansteuerung aus Zonenbedarf | Voll lokal, HA-**Core**-Integration | **Leistungsvergleich (Disziplin Mehrzonen):** drittes großes EU-Zonen-Ökosystem, einziges mit lokaler Core-Integration |
| **Bosch Smart Home HK-Thermostat II [+M]** | Konventionelle In-Device-Regelung, Fenster, Führungsfühler-Konzept; keine Prädiktion | Vorbildlich lokal: Matter over Thread ([+M]), lokale SHC-REST-API, Z2M-Direktpairing | Solide kommerzielle Baseline (Leistungsvergleich zweiter Reihe) |
| **SwitchBot Smart Radiator Thermostat** (EU-Launch 10/2025) | TRV + optionales Home Climate Panel als externer Führungsfühler (vendor-intern) | Matter via Hub Mini | Beobachten — jüngste kommerzielle Direkt-Alternative zum Setup „TRV + externer Raumsensor" |
| Netatmo Energy | Auto-Adapt/Anticipation (prädiktiver Heizbeginn), PID/Hysterese wählbar (PID erst nach Lernphase) | **Nur Cloud**, wiederkehrende API-Probleme | Konzept-Referenz; kein reproduzierbarer Vergleich |
| Google Nest | Auto-Schedule, True Radiant/Early-On (gelerntes Vorheizen), Time-to-Temperature-UX | Cloud (SDM); **kompletter EU-Marktrückzug angekündigt 04/2025** | Konzept-/UX-Referenz (Time-to-Temp-Anzeige für Optimal-Start-Transparenz) |
| Ecobee (eco+) | Smart Recovery, Multi-Sensor-Occupancy („Follow Me"), **„Feels like" = Feuchte im Komfortmodell** | Cloud oder lokal via HomeKit | Konzept-Referenz (Feuchte-Komfort → Parallele zu PMV/PPD, ADR-0054) |
| Eve Thermo (Gen 5, 12/2025) | Keine Lern-Intelligenz; autarke On-Device-Schedules | Matter over Thread, „Works with HA" | Referenz für saubere Matter-TRV-Integration |
| Aqara E1 / Moes BRT-100 & Tuya-TS0601-Familie | Einfache Hysterese; Tuya-Kalibrierung grob/teils defekt | Lokal (Z2M/ZHA) | Kompatibilitäts-/Risiko-Referenz (falls Support über TRVZB hinaus); kein Erkenntnisgewinn im Benchmark |
| Vaillant ambiSENSE / myVAILLANT | Hersteller-Einzelraumregelung + witterungsgeführter Erzeuger | Cloud mit strikten Quoten ([mypyllant](https://github.com/signalkraft/mypyllant-component) 327 ★) | Kategorie „Wärmeerzeuger-Hersteller" — Referenz, kein Vergleich |
| Heatmiser Neo (UK, Fußbodenheizung) | Optimum Start/Preheat im Gerät, Floor-Limits | Lokal (neoHub-TCP; HACS 116 ★) | FBH-Kategorie-Referenz; andere Emitter-Physik |
| KNX-Einzelraumregelung (MDT AKH, stellvertretend) | Parametrierter PI + PWM im Aktor; kein Lernen | Voll lokal via KNX-Core-Integration | Ingenieurs-Goldstandard als Regelgüte-Erwartungswert; anderer Hardware-Kontext (Poises KNX-Expose ADR-0019 bleibt konkurrenzlos) |

### 2.4 Angrenzende OSS-Projekte (keine Regelungs-Wettbewerber, aber relevant)

- **[EMHASS](https://github.com/davidusb-geek/emhass)** (638 ★, sehr aktiv, CVXPY-MPC seit 01/2026): Energie-Dispatch-Optimierung. **Achtung, Korrektur zur Intuition:** EMHASS *hat* ein dokumentiertes lineares Raumthermik-Modell für thermische Lasten (heating_rate, cooling_constant, Komfortband, Außentemp-Forecast) — es bleibt aber Last-Dispatch (wann heizt was gegen Strompreis/PV), keine Komfort-Regelgüte. Perspektivisch **Komplement** (Poise-Wärmebedarf als deferrable Load melden), kein Benchmark-Gegner.
- **Predheat/[Predbat](https://github.com/springfall2008/batpred)**: Predheat (48-h-Raumtemp-/Kostenprognose) ist archiviert und in Predbat (305 ★, aktiv) aufgegangen — gleiche Ökosystem-Schnittstelle wie EMHASS.
- **[ESPHome PID Climate](https://esphome.io/components/climate/pid.html)**: verbreitetster DIY-Firmware-PID (Ziegler-Nichols-Relay-Autotune, Deadband); Referenz für TPI/PI-Parametrierung, regelt aber eigene ESP-Ausgänge, keine HA-TRVs.
- **[thermal_comfort](https://github.com/dolezsa/thermal_comfort)** (863 ★): De-facto-Standard für Feuchte-/Taupunkt-Sensorik in HA — kein PMV/PPD; gutes Differenzierungsargument für ADR-0054.
- **[pythermalcomfort](https://github.com/CenterForTheBuiltEnvironment/pythermalcomfort)** (218 ★, 4.0.2 06/2026): wissenschaftliche Referenzimplementierung — bereits Testvektor-Quelle von ADR-0054; für Zahlen-Validierung, nicht für Regelgüte.
- **[CompCurve](https://github.com/rawnsley/CompCurve)** (3 ★): nichtlineare Heizkurve inkl. Wind-/Solar-Termen + raumübergreifende Heat-Demand-Aggregation — Konzept-Referenz für ADR-0039; die ernsthafte Heizkurven-Konkurrenz läuft über SAT.

---

## 3. Empfehlung: Mit wem lohnt der Leistungsvergleich?

### Tier 1 — Kern-Benchmark-Set (Pflicht)

Software-Gegner (alle lokal, closed-loop in HA, aktiv gewartet, markt- oder technikrelevant):

1. **HA generic_thermostat** — Hysterese-Nulllinie; ohne sie ist kein Ergebnis einordbar.
2. **Better Thermostat ≥1.8** — größte Verbreitung im Segment *und* seit dem Rewrite direkter Algorithmus-Wettbewerber (MPC/TPI/PID). Wichtigster Einzelvergleich.
3. **Versatile Thermostat v10** — TPI/„Smart PI"-Referenz, zweitgrößte Verbreitung.
4. **RoomMind** — einziger zweiter EKF-Vertreter: „gleiche Waffengattung"-Vergleich (Lernkonvergenz, Solar, Ventilpfad).
5. **ThermoSmart** — direktester Klon auf identischer Zielhardware (TRVZB-Profile, Optimal-Start, TPI, Outcome-Scoring); Lernkurven-Duell EKF vs. Beobachtungs-Staging.
6. **HASmartThermostat** — klassische PID-Baseline (manuell getunt, nicht Autotune).

Hardware-/Firmware-Gegner auf identischer Zielhardware:

7. **Sonoff TRVZB Firmware selbst** — Dreikampf auf demselben Ventil: Werks-Hysterese vs. FW-1.4.4-„Adaptive Mode" (PID) vs. Poise-TPI-Direktventil; plus **photomoose-Blueprint** (externer Sensor → `external_temperature`) als verbreitetste Community-Baseline. Das ist der fairste und für die Zielgruppe überzeugendste Vergleich, den Poise fahren kann.
8. **Advanced Heating Control (panhans)** — Blueprint-Massenstandard mit proportionaler Ventilpositionierung: „einfache Heuristik vs. lernende Regelung" vor riesigem Publikum.

### Tier 2 — disziplinspezifische Vergleiche (lohnend, je nach verfügbarer Hardware/Saison)

- **Optimal Start:** Danfoss Ally (`schedule_with_preheat`, im Gerät), tado X (Early Start, lokal via Matter), AVM FRITZ!DECT 302 (adaptiver Heizbeginn, 1-h-Limit), Wiser Comfort Mode, IHP (VTherm-Aufsatz). Metrik: Treffgenauigkeit Zielzeit/Zieltemperatur + Vorheiz-Energie (ADR-0025/0044-Infrastruktur).
- **In-Device-Regelgüte (Kommerz):** Homematic IP Evo (DACH-Referenz, lokal via RaspberryMatic), Shelly BLU TRV (PID + Ventilzugriff), Bosch II [+M] (Matter-Baseline). Feld-A/B in Raumpaaren.
- **Mehrzonen-/Kesselbedarf:** evohome via ramses_cc (Heat-Demand pro Zone lesbar!), Wiser (Heat-Demand-%), Plugwise Adam, MultiZone Thermostat, SAT (OpenTherm-Modulation). Vergleich gegen ADR-0038/0039-Aggregat.
- **Klassik gut gemacht:** Dual Smart Thermostat (auch für Kühl-/Dry-Pfad ADR-0050/0051).
- **Beobachten (heute zu klein, technisch relevant):** Adaptive Climate (afewyards, lernender PID), Smarter Thermostat (BT-Fork MPC), SwitchBot TRV.

### Nicht lohnend (mit Grund)

| Kandidat | Grund |
|---|---|
| Vesta, HEATHER 3, Schedy, Scheduler, Fenster-Blueprints | Scheduler/Automation ohne Regelanspruch — Vergleich hätte keine Aussagekraft |
| Adaptive Climate (msinhore), schoolboyqueue | tot bzw. ruhend; nur noch Konzept-Referenz (Adaptivkomfort/Psychrometrie) |
| Netatmo, Nest, Ecobee, Vaillant ambiSENSE | cloud-gebunden/quotiert bzw. US-Ganzhaus-Kontext — nicht fair reproduzierbar |
| Eve, Aqara, Moes/Tuya | keine Regel-Intelligenz über Hysterese hinaus; Budget-Baseline-Rolle erfüllt der TRVZB besser |
| KNX/MDT, Heatmiser, ESPHome PID | andere Hardware-Klasse (thermische Antriebe/FBH/DIY-ESP) — als Erwartungswert-Referenz ja, als Marktvergleich nein |
| EMHASS, Predheat/Predbat, Heating Analytics, CompCurve, thermal_comfort, pythermalcomfort | keine Raumkomfort-Regelung (Dispatch/Prognose/Sensorik/Bibliothek) — Referenzen bzw. Komplemente |
| Valves, haos_mpc, Smart Offset, hacker-cb, ClimateAdvisor | verwaist oder <10 ★ ohne Marktrelevanz |

### Vorgeschlagene Vergleichs-Methodik (knapp)

1. **Stufe A — Harness (sofort machbar, ADR-0011):** Wettbewerber-Algorithmen (Hysterese, PID, TPI, BT-Kalibrierlogik) als Vergleichsregler gegen dieselbe `RCPlant` im Closed-Loop-Harness fahren; Metriken: `comfort_deviation_k`, `time_in_band`, `cycles_per_hour` (ADR-0055), Energie-Proxy (Ventil-Duty/HDH). Compliance wie gehabt: Methoden nachimplementieren, kein Code-Copy (G29/G30).
2. **Stufe B — Feld-A/B (Heizsaison):** Raumpaare mit identischen Sonoff TRVZB; ein Raum Poise, einer der jeweilige Gegner (BT/VTherm/TRVZB-Firmware/panhans-Blueprint). Eine CA-Messperiode pro Konstellation; Maskierungsregeln aus ADR-0055 übernehmen.
3. **Design-Caveats (verifiziert):** TRVZB „Adaptive Mode" bei Poise-Betrieb sicher deaktivieren (Interferenz) und FW-Version protokollieren; FRITZ!OS-Zeitplan-Doppelherrschaft kontrollieren; tado nur über lokale Pfade (Matter/HomeKit) messen (Cloud-Quota 100 Req/Tag); BT-Versionsstand dokumentieren (≤1.7 vs. ≥1.8 sind faktisch verschiedene Produkte).

---

## 4. Konsequenzen für bestehende ADRs

- **ADR-Zitate zu Better Thermostat** (u. a. ADR-0025 „kein Optimal-Start", ADR-0051 „nur binärer Außen-Lockout", ADR-0048) beschreiben den Stand ≤1.7. Seit v1.8 (06/2026) hat BT MPC/TPI/PID + direkte Ventilsteuerung — bei künftigen ADR-Bezügen Version angeben; eine Quellcode-Re-Verifizierung von BT ≥1.8 ist der wichtigste offene Recherche-Punkt.
- **Adaptive Climate (msinhore)** als lebender Wettbewerber streichen (Repo 404); Konzept-Zitate (ASHRAE-55-Adaptivband, ADR-0051) bleiben gültig, Quelle ist das Blueprint-Repo.
- **Sonoff TRVZB FW 1.4.4 „Adaptive Mode"** berührt ADR-0036 (TPI-Direktventil): vor dem Live-Flip prüfen, dass der Modus deaktiviert ist bzw. ein Repair-Hinweis existiert (Interferenz zweier Regler auf einem Ventil).
- **Versatile Thermostat v10 Plugin-Mechanismus** ist strategisch beobachtenswert (Ökosystem-Öffnung; IHP zeigt, dass Dritt-Layer auf VTherm bauen).
