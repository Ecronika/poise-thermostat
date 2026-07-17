# Meinungsbild Wettbewerber — Nutzerfeedback aus GitHub, HA-Forum, Reddit und Simon42-Community (Stand 2026-07-17)

**Zweck:** Ergänzung zur [`Wettbewerbsanalyse_Markt_2026-07.md`](Wettbewerbsanalyse_Markt_2026-07.md). Ausgewertet wurden Kommentare, Diskussionen und Issues zu den gelisteten Wettbewerbern auf **GitHub** (Issues/Discussions/Release-Kommentare), im **Home-Assistant-Forum**, auf **Reddit** und in der deutschsprachigen **Simon42-Community**. Positive wie negative Meldungen, Bugs und Probleme sind bewertet und den Poise-Feature-Achsen (aktiv + „in Arbeit") zugeordnet; am Ende stehen die Stolpersteine aus Nutzersicht und die Konsequenzen für Poise.

**Methodik & Belastbarkeit:** Fünf parallele Recherche-Stränge (GitHub BT/VTherm · GitHub übrige Integrationen · HA-Forum · Reddit · Simon42). GitHub-Quellen sind mit Issue-/Discussion-Nummern direkt verifiziert. **Einschränkung:** community.home-assistant.io und community.simon42.com sind bot-geschützt (HTTP 403) — Foren-Befunde stammen aus Suchindex-Snippets; Antwortzahlen sind Mindestwerte aus Post-Ankern. **Reddit blockt Anthropic-Crawler vollständig** — Reddit-Stimmungen stammen aus Suchindex-Aggregaten und Sekundärquellen (gekennzeichnet); Einzel-Threads dort sind nicht URL-verifiziert. Kernaussagen aus Foren vor wörtlicher Zitierung im Volltext prüfen.

---

## 1. Kurzfazit: die Stolpersteine aus Nutzersicht (quellenübergreifend)

1. **Kalibrierung/externer Sensor ist das ungelöste Kernproblem des Feldes.** Jede Plattform hat eigene, inkompatible Offset-Mechanik (Target- vs. Offset-Kalibrierung bei BT, Danfoss-Refresh-Regeln „covered ≤30 min / uncovered ≤3 h", Z2M-Modi, Geräte-Limits ±2,4/±2,5 K). Nutzer verstehen die Konzepte nicht, Firmware verhält sich je Charge anders.
2. **Ventil-Thrashing:** binäres 0→100→0-Ventilfahren (BT vor 1.8, TRVZB vor FW 1.4.4, Tuya-Auf/Zu) → Verschleiß, Batterie, Thermen-Takten. Ein Feldvergleich (pro-it.rocks, 10 Tage Daten) maß mit VTherm-Setpoint-Führung ~90 % weniger Ventilbewegung und 2× schnelleres Aufheizen als BT (vor 1.8).
3. **Misstrauen gegen Blackbox-Lernen:** BTs „AI calibration" kann sich festfahren (vom Maintainer als Known Issue geführt), VTherm-auto-TPI lernt aus falschen Annahmen (154-Kommentare-Thread), SAT-Autotune wird manuell übersteuert, Danfoss Adaptation-Run bleibt undurchsichtig, tado verschob „AI"-Features hinter eine Paywall. Community-Konsens: **Lernen ja — aber lokal, erklärbar, abschaltbar.**
4. **Restart-/Update-Fragilität:** HA-Neustarts verlieren Zustand (PID-Integrale, gelernte Werte, Fenster-Restore), Major-Releases brechen Bestehendes (BT-1.8-Migrationswelle, Z2M 2.0, Shelly FW 1.5.1), Firmware-Updates setzen TRV-Einstellungen zurück.
5. **Doppelsteuerung:** zwei Regler auf einem Ventil (BT+AHC gleichzeitig, FRITZ!OS-Zeitpläne vs. HA, TRV-interner Wochenplan, TRVZB-Adaptive-Mode) arbeiten gegeneinander — häufige Ursache für „macht was es will"-Threads.
6. **Komplexität:** die mächtigsten Lösungen erzeugen die meisten Support-Posts (VTherm: „50–60 Konfigurationsvariablen", eigener Frust-Thread „Where does one get the required education?"; AHC: Selector-Fallen mit stillem 24×7-ON-Fallback; MultiZone: YAML-only).
7. **Mehrzonen-Lücke:** TRVs exponieren kein sauberes „call for heat" — Nutzer basteln Kesselbedarf aus Ventilpositionen selbst zusammen (Dauerthema im HA-Forum).
8. **Cloud-Frust als Marktverschiebung:** tado-Paywall (02/2025) + API-Quota 100 Calls/Tag (01/2026) gelten als Musterbeispiel für „Enshittification"; massive Abwanderung zu lokalem Zigbee/Thread und Community-Integrationen (tado_ce, tado-local). Lokal-ohne-Abo ist inzwischen ein Kaufkriterium, in der deutschen Community besonders ausgeprägt.
9. **Batterie vs. Regelgüte:** häufige externe Sensor-Writes verbessern die Regelung, fressen aber TRV-Batterien und Funkbudget (HmIP-Duty-Cycle bis 100 % durch BT-Offset-Writes) — Blueprints mussten Throttling nachrüsten.
10. **Nachtabsenkung ist kein Selbstläufer:** Community-Konsens differenziert — bei träger FBH/Brennwert eher kontraproduktiv, bei Radiatoren sinnvoll; fixe Vorheiz-Offsets gelten als „an milden Tagen Verschwendung, an kalten zu spät".

---

## 2. Meinungsbild je Poise-Feature-Achse

Legende: 👍 = positive Resonanz im Feld · ⚠️ = dokumentierte Probleme/Bugs · **→ Poise** = Bedeutung für Poise (mit ADR-Bezug).

### A1 — Sollwertführung & TRV-Kalibrierung mit externem Sensor *(Poise: Live)*
- 👍 Konsens aller Quellen: interner TRV-Sensor „lügt" (Heizkörpernähe), externer Sensor ist Pflicht — genau das ist BTs Kernversprechen und der Grund seiner Verbreitung. HA-Forum-Guide „Automating heating with smart TRVs" (t/792841) formuliert das als Standardwissen.
- ⚠️ BT: Sollwert „ändert sich von selbst" (meistkommentierte Issues [#1097](https://github.com/KartoffelToby/better_thermostat/issues/1097)/[#913](https://github.com/KartoffelToby/better_thermostat/issues/913)), Sonoff-Offset falsch ([#1489](https://github.com/KartoffelToby/better_thermostat/issues/1489)), Z2M-Kalibrierwerte ignoriert, ZHA-Limit ±2,5 K (Known-Issues [#1568](https://github.com/KartoffelToby/better_thermostat/issues/1568)); Simon42: Offset-Drift-Threads in Serie, „regelt Local Temperature Calibration massiv runter" (t/68975). panhans AHC: Kalibrier-Entity-Erkennung per Namens-Keyword bricht; schreibt Absolutwert in Offset-Entities ([#141](https://github.com/panhans/HomeAssistant/issues/141), [#157](https://github.com/panhans/HomeAssistant/issues/157)); Aqara-Kalibrierung bis zum Z2M-Koordinator-Crash ([#167](https://github.com/panhans/HomeAssistant/issues/167)). Danfoss: Auto-Offset-Modus fällt still auf internen Sensor zurück, wenn Refresh-Fenster (3 h) verpasst wird (t/276686, ~200 Antworten).
- **Markttrend:** Die Community wandert zu **TRV-nativen Lösungen ohne Regel-Integration** — Sonoff `external_temperature` (Z2M ≥2.1.2), Bosch `remote_temperature` („ohne HACS" als Feature gefeiert, Simon42 t/47498), Danfoss `external_measured_room_sensor`, HmIP-Wandthermostat-Kopplung. „BT ist damit für viele überflüssig."
- **→ Poise:** Bestätigt den Referenzrahmen-Ansatz (ADR-0056) und die Wahl des external-temperature-Pfads statt Offset-Tricks. Risiko: Poise erbt dieselben Geräte-Quirks (ADR-0029) — die Offset-Fehlerklassen von BT/AHC sind Pflicht-Regressionstests. Chance: „Kalibrierung, die einfach stimmt" ist das am häufigsten enttäuschte Versprechen im Feld.

### A2 — Direkte Ventilsteuerung / TPI *(Poise: Shadow, ADR-0036)*
- 👍 %-genaue Ventilsteuerung ist das meistgelobte technische Feature überhaupt: TRVZB-Ventilsteuerung in %-Schritten („nur 20 % öffnen, kaum Überschwingen", Simon42 t/17874, ≥73 Beiträge), VTherm `over_valve`/Self-Regulation ([Discussion #154](https://github.com/jmcollin78/versatile_thermostat/discussions/154)), AHC-V5-Ventilpositionierung kam auf Nutzerwunsch ([#79](https://github.com/panhans/HomeAssistant/issues/79)).
- ⚠️ Konfig-Fallen und Quirks dominieren: TRVZB `closing_degree` darf nicht konfiguriert werden (VTherm gepinnte [Discussion #860](https://github.com/jmcollin78/versatile_thermostat/discussions/860) — deckt sich mit Poises TRVZB-Firmware-Bug-Befund in ADR-0036), nichtlineare Ventilkennlinien (30-Kommentare-Discussion), `min_opening`-Bug ließ Ventile nie schließen ([#1220](https://github.com/jmcollin78/versatile_thermostat/issues/1220)), RoomMind-Proportionalmodus treibt AC-Setpoints auf Maximum ([#316](https://github.com/snazzybean/roommind/issues/316)); TRVZB liefert kein Ist-Öffnungs-Feedback → Wirkung schwer verifizierbar; BT bis 1.7 de facto binär (Forum t/980151).
- **→ Poise:** TPI-Direktventil trifft einen echten, artikulierten Bedarf. Die Fehlerklassen (closing_degree, Kennlinien-Nichtlinearität, fehlendes Feedback, stuck valve) sind bekannt und gehören in Harness-Tests; VTherms nachgerüstete Stuck-Valve-Erkennung ([PR #1827](https://github.com/jmcollin78/versatile_thermostat/pull/1827)) ist Feature-Referenz.

### A3 — Selbstlernende Physik / Lernzeit *(Poise: Live, EKF)*
- 👍 Es gibt Appetit: RoomMind wächst (368★) trotz mehrtägiger Lernphase; ThermoSmart-Beta wird wohlwollend aufgenommen; die Optimal-Start-Bastelszene (SmartHRT & Co.) lernt bewusst aus gemessenen Aufheizraten.
- ⚠️ Aber das Feld hat Vertrauen verspielt: BT „AI calibration" kann nach schnellem Temperaturabfall dauerhaft nicht mehr heizen (Known Issue #1568), „AI Time Based" ohne belastbare Erfolgsberichte (Forum t/774564, Simon42 t/32795); VTherm auto-TPI lernt falsch, wenn der Zentralkessel aus ist, kext wächst zu aggressiv → 1–2 K Overshoot ([Discussion #1428](https://github.com/jmcollin78/versatile_thermostat/discussions/1428), **154 Kommentare**; [#1685](https://github.com/jmcollin78/versatile_thermostat/issues/1685): 3,22 °C/h gelernt bei real 0,25); RoomMind-EKF: Zeitkonstante festgefahren ([#301](https://github.com/snazzybean/roommind/issues/301)), Lern-Korruption bei direkter Setpoint-Steuerung ([#241](https://github.com/snazzybean/roommind/issues/241)), Alpha-Oszillation (Release-Fix); HASmartThermostat-Autotune per README „not recommended"; IHP verlor Lernwerte bei Updates ([#125](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/125)/[#123](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/123), gefixt).
- **→ Poise:** Der Community-Konsens „**lokal, erklärbar, abschaltbar**" ist exakt Poises Architektur (Konfidenz als Entity ADR-0016, Lernzustand auf der Card ADR-0040, Shadow-first ADR-0026, Modus-Gating ADR-0024). Die dokumentierten Fehlerklassen der anderen — Lernen aus falschen Annahmen (Kessel aus, Fenster offen, Direktsteuerungs-Echo), festgefahrene Parameter, Zustandsverlust — sind genau die, gegen die ADR-0024 (Identifizierbarkeit), ADR-0030 (Anti-Garbage-In) und ADR-0007 (Persistenz) gebaut sind. Das gehört in die Doku als Differenzierung.

### A4 — Optimal Start / Nachtabsenkung *(Poise: Live, ADR-0025/0034)*
- 👍 Boomthema 2026: Adaptive HVAC Preheat (t/997235), SmartHRT (t/833025), Smart Dynamic Preheat (t/1009573, pures YAML) — alle mit derselben Begründung: fixe Vorlaufzeiten sind falsch, Vorlauf muss aus gemessener Aufheizrate kommen. tado Early Start / FRITZ „adaptiver Heizbeginn" (1-h-Deckel) sind die kommerziellen Anker.
- ⚠️ BT/VTherm haben kein termingebundenes Vorheizen — Nutzer koppeln extern (Scheduler Card, AHC) und kämpfen mit Übergabestellen. Nachtabsenkungs-Grundsatzdebatte wird differenziert geführt: bei FBH rät die Community überwiegend ab (Simon42 t/47951), bei Radiatoren pro Setback; datenbasierte Antworten fehlen fast völlig.
- **→ Poise:** Optimal Start mit Exponential-Inversion + Forecast (ADR-0025) ist dem gesamten Community-Stand voraus; die FBH-Skepsis bestätigt die Aktor-Dynamik-Profile (ADR-0052). Chance: die unbeantwortete Frage „lohnt sich Absenkung bei *meinem* Raum?" beantwortet Poises Effizienz-Report (ADR-0045) — kein Wettbewerber liefert diese Zahl. Nests „Time-to-Temperature"-Anzeige ist das UX-Vorbild für Optimal-Start-Transparenz.

### A5 — Fenster-offen-Erkennung *(Poise: Live, Slope + Bypass, ADR-0041)*
- 👍 Pflichtfeature in allen Quellen; VTherm ist der einzige verbreitete Vertreter mit sensorloser Auto-Erkennung.
- ⚠️ Die Fehlerklassen sind konsistent dokumentiert: Fehlalarme durch AC-Kaltluft (VTherm [#1039](https://github.com/jmcollin78/versatile_thermostat/issues/1039)), TRV-eigener 7-°C-Frostschutz wird als Nutzer-Soll übernommen ([#1284](https://github.com/jmcollin78/versatile_thermostat/issues/1284)), Restore nach Fenster-zu falsch/vergessen ([#683](https://github.com/jmcollin78/versatile_thermostat/issues/683); BT „kein Heizen nach Fensterschluss", #1568; TRV bleibt auf 5 °C, [#1195](https://github.com/KartoffelToby/better_thermostat/issues/1195)), HA-Restart mit offenem Fenster hängt ([#504](https://github.com/jmcollin78/versatile_thermostat/issues/504)), BT-Fensterlogik hing bis 07/2026 an der Sensor-Verfügbarkeit ([PR #2126](https://github.com/KartoffelToby/better_thermostat/pull/2126)); AHC schaltet zuvor ausgeschaltete Thermostate wieder ein ([#121](https://github.com/panhans/HomeAssistant/issues/121)). Simon42-Kernfrage: „vorherigen Sollwert nach Fenster-zu wiederherstellen" (t/41946).
- **→ Poise:** Die Restore-/Hänger-Fehlerklasse ist der eigentliche Schmerzpunkt, nicht die Erkennung selbst — Poises Lösung über den Solver (Floor statt Setpoint-Wechsel, kein Restore nötig) umgeht sie strukturell; das ist ein dokumentierbarer Vorteil. Slope-Fehlalarm-Quellen (AC, Türen) als Testfälle übernehmen.

### A6 — Overrides / manuelle Eingriffe & Auto-Rückkehr *(Poise: Live, ADR-0042/0059)*
- 👍 Universeller Wunsch in allen Quellen: „manuell drehen, ohne dass die Automatik sofort überschreibt — und automatischer Rückfall zum Plan" (HA-Forum „Self-Healing Override" t/1011118, Simon42 AHC-/VTherm-Threads, Netatmo/tado-Verhalten als Vorbild).
- ⚠️ BT: Presets/Services nach 1.8 geändert, Entity-Aliasing bricht Automationen ([#2104](https://github.com/KartoffelToby/better_thermostat/issues/2104)); VTherm: Preset springt von selbst auf „custom" ([#1900](https://github.com/jmcollin78/versatile_thermostat/issues/1900)); RoomMind: Schedule-off wird von „When Idle" überschrieben ([#368](https://github.com/snazzybean/roommind/issues/368)); AHC: Eco-Helper springt ([#101](https://github.com/panhans/HomeAssistant/issues/101)).
- **→ Poise:** ADR-0042/0059 (Override mit Auto-Rückkehr, geräteseitige Eingriffe adoptieren, `override_clamped` statt still klemmen) adressieren exakt den artikulierten Bedarf — kein verbreiteter Wettbewerber löst das vollständig. Differenzierungs-Punkt erster Ordnung.

### A7 — Mehrzonen / Kesselbedarf *(Poise: Live/teilw., ADR-0038/0039)*
- 👍 Referenz-Thread „Multi-zone boiler — 2 years of learnings" (t/339874): häufigere kleinere Zyklen statt Zonen-Schwingen — deckt sich mit Poises Kessel-Aggregat-Design. VTherm-Central-Boiler und AHC werden dafür genutzt; ebusd (Simon42 t/7885, ≥163 Beiträge) und BSB-LAN sind die deutschen DIY-Standards für den Erzeuger.
- ⚠️ Die Lücke ist klar benannt: **TRVs exponieren kein sauberes „call for heat"** — Nutzer aggregieren Ventilpositionen per Hand (t/821529, t/684083). BT-Gruppenlogik fehlerhaft („quorum of one", [#2063](https://github.com/KartoffelToby/better_thermostat/issues/2063) offen); VTherm-auto-TPI kollidiert mit Kessel-aus-Phasen (#1428); SAT-Multi-Room-Sync unzuverlässig ([#105](https://github.com/Alexwijn/SAT/issues/105)); MultiZone-Thermostat bricht bei HA-Updates ([#38](https://github.com/vindaalex/multizone-thermostat/issues/38)).
- **→ Poise:** Der Kesselbedarf-`binary_sensor` (ADR-0039) füllt eine real artikulierte Lücke; Anschlussfähigkeit an ebusd/BSB-LAN/OpenTherm (als Aktions-Ziel des Opt-in-Schalters) ist für die deutsche Zielgruppe wichtiger als OpenTherm-Direktregelung.

### A8 — MPC / Prädiktion *(Poise: Shadow, ADR-0033)*
- 👍 Konzept kommt an, wo es erklärbar ist: RoomMind-Kritik läuft „auf hohem Niveau" (Modulationsqualität statt Konzeptzweifel); BT-1.8-MPC wurde begrüßt.
- ⚠️ BT-MPC: Doku-Lücke („What is the target for the MPC algorithm?" [unbeantwortet](https://github.com/KartoffelToby/better_thermostat/discussions/1924)), heizt trotz „idle" ([#1789](https://github.com/KartoffelToby/better_thermostat/issues/1789)), Beta-Overshoot ([#1906](https://github.com/KartoffelToby/better_thermostat/issues/1906)). Im Forum ist „MPC" bislang eher Label als verifiziertes Verhalten.
- **→ Poise:** Shadow-first mit messbarem Flip-Gate (ADR-0055) ist die richtige Antwort auf genau dieses Glaubwürdigkeitsproblem; BTs unbeantwortete MPC-Zielfrage zeigt, dass die `mpc_*`-Diagnose + Card-Pill (Transparenz) ein echtes Differenzierungsmerkmal ist.

### A9 — Komfortband / Presets / adaptiver Komfort *(Poise: Live, EN 16798-1, ADR-0023/0061)*
- 👍 Eco/Comfort-Presets + Anwesenheit sind Standarderwartung (Simon42: Fritzbox-Presence). ASHRAE-55-Adaptiv-Blueprint (t/905689) zeigt Nischen-Interesse an normbasierten Bändern, wirbt mit 15–30 % Ersparnis.
- ⚠️ Dual-Smart: `hot_tolerance`-Default 0 → Dauertakten ([#506](https://github.com/swingerman/ha-dual-smart-thermostat/issues/506)); Preset-Randfälle bei VTherm/BT (s. A6). Kein verbreiteter Wettbewerber führt ein *normiertes* Band — das Thema existiert im Feld nur als Blueprint-Nische.
- **→ Poise:** Normband ist Alleinstellung, braucht aber Übersetzungsarbeit in der Doku (Nutzer denken in „Solltemperatur", nicht in Kategorien — die Card muss das Band erklären, ADR-0040/0057 leisten das).

### A10 — Feuchte / Schimmelschutz / Kühlen *(Poise: Live Dry-Pfad ADR-0050, Kühlband ADR-0051)*
- 👍 Schimmel/Taupunkt ist ein **deutsches Schwerpunktthema** (Simon42: Taupunkt-vs-absolute-Feuchte-Methodendebatte t/27742, Thermal-Comfort-Taupunktsteuerung t/15528; HA-Forum: Mold-Prevention-Threads). Werkzeug der Wahl ist die Sensorik (thermal_comfort, 863★) — **Heizung und Schimmelprävention werden fast nie integriert gedacht.**
- ⚠️ Dual-Smart-Feuchte-Features unreif (Sollwert springt nach Restart auf 50 % [#553](https://github.com/swingerman/ha-dual-smart-thermostat/issues/553), Hygrostat als Humidifier statt Dehumidifier [#369](https://github.com/swingerman/ha-dual-smart-thermostat/issues/369)); BT-Kühlen unfertig (Cooling-Presets erst 1.9-beta); VTherm-Kühl-Randfälle.
- **→ Poise:** Integrierter Schimmelschutz (DIN 4108-2) + Dry-Pfad füllt eine Lücke, die die Community bisher mit getrennten Lüfter-Automationen schließt — für den DACH-Markt ein Kernargument. Die Restart-Fehlerklasse (#553) als Persistenz-Testfall übernehmen.

### A11 — UI / Cards / Onboarding *(Poise: Live, ADR-0040/0057; Zero-Question-Flow ADR-0008)*
- ⚠️ Größte Einzelhürde im Feld: VTherm-Komplexität hat einen eigenen Frust-Thread („50–60 Variablen", t/950206), BT-Einsteiger scheitern am Konzept BT-Entität vs. TRV (Simon42 „ich check es nicht!" t/71034), BT-1.8-Card/Blueprints brachen ([#2034](https://github.com/KartoffelToby/better_thermostat/issues/2034)/[#2039](https://github.com/KartoffelToby/better_thermostat/issues/2039)), RoomMind-Panel verliert Features bei HA-Updates ([#334](https://github.com/snazzybean/roommind/issues/334)), MultiZone YAML-only überfordert ([#37](https://github.com/vindaalex/multizone-thermostat/issues/37)), AHC-Selector-Fallen enden im stillen 24×7-ON. ThermoSmarts einziges Issue war ein Config-Flow-Validierungsfehler ([#1](https://github.com/Mikasmarthome/ThermoSmart/issues/1)).
- 👍 Was gelobt wird: Einfachheit (Scheduler Card „nicht schön, aber zuverlässig"), AHC V5 („funktioniert genau so, wie es soll" — beste Bewertung der drei großen Lösungen in der Simon42-Community), BTs neue Website/Card nach 1.8.
- **→ Poise:** Bestätigt den Zero-Question-Hub (ADR-0008) und gebündelte Cards (ADR-0040) als strategisch richtig. Wichtigste Lehre: **stille Fallbacks sind Gift** — Nutzer fordern sichtbare Gründe („warum heizt es gerade (nicht)?"); Poises Reason-/Diagnose-Attribute und die Ampel (ADR-0049) adressieren das, müssen aber prominent bleiben.

### A12 — Zuverlässigkeit: Zigbee-Last, Batterie, Restarts, Geräte-Quirks *(Poise: Live, ADR-0006/0007/0012/0029)*
- ⚠️ Das entscheidende Kaufkriterium in allen Quellen: BT+HmIP flutet das Duty-Cycle-Budget (Simon42 t/1003 — Community-Warnung, BT nicht mit Homematic zu kombinieren); TRVZB: spontane Resets mit Dauerheizen (t/867420), `closing_steps` verstellt sich (t/665875), FW-Update setzt Einstellungen zurück (t/959388), external-Modus wechselt selbst auf external_2 (Simon42 t/68866), Adaptive Mode deaktiviert sich (t/81366); HASmartThermostat verliert PID-Integral bei Restart ([#266](https://github.com/ScratMan/HASmartThermostat/issues/266)); Z2M-2.0-Umstieg legte BT-Instanzen lahm ([#1549](https://github.com/KartoffelToby/better_thermostat/issues/1549)); FRITZ!DECT-Befehle brauchen 5–15 min (Simon42 t/38542); Shelly BLU TRV: Gateway-Pflicht, 5-TRV-Limit, BLE-Reichweite; Batterie-Threads überall.
- **→ Poise:** Write-Throttle (change-aware), Persistenz inkl. Shutdown-Flush, Repair-Issues und Geräte-Quirks (ADR-0029) zielen exakt auf diese Fehlerklassen. Die TRVZB-Reset-/Self-Reconfiguration-Fälle gehören als Anti-Garbage-In-/Watchdog-Szenarien in die Tests; der HmIP-Duty-Cycle-Fall begründet eine dokumentierte Funkbudget-Aussage („Poise schreibt nur bei Änderung").

---

## 3. Meinungsbild je Lösung (Kompaktbewertung)

| Lösung | Nutzer-Sentiment | Kernlob | Kernproblem laut Nutzern |
|---|---|---|---|
| **Better Thermostat** | gespalten, ermüdend („bei vielen läuft es, bei anderen gar nicht") | Konzept externer Sensor; v1.8-Rewrite begrüßt (14 🎉) | Kalibrier-Blackbox, Sollwert-Eigenleben, riskante Major-Releases (1 Monat Hotfixes nach 1.8), HmIP-Duty-Cycle, Gruppenlogik ([#2063](https://github.com/KartoffelToby/better_thermostat/issues/2063) offen) |
| **Versatile Thermostat** | positiv bei Power-Usern, Onboarding abschreckend | echte %-Ventilführung (messbar ~90 % weniger Ventilbewegung als BT vor 1.8), sehr responsiver Maintainer | auto-TPI lernt falsch (#1428), Komplexität („required education"-Thread), Restart-Randfälle |
| **Advanced Heating Control (panhans)** | klar positiv — beste Bewertung der „großen drei" in der dt. Community | „funktioniert genau so, wie es soll", V5-Ventilpositionierung | Kalibrier-Entity-Erkennung, Fenster-Logik überschreibt Off-Zustand, stille Selector-Fallbacks, Blueprint-Grenzen |
| **SAT** | positiv bei OpenTherm-Technikern | einziger Heizkurven+PID-Ansatz direkt auf Kesselmodulation | Overshoot-Kalibrierung v4-Regression ([#77](https://github.com/Alexwijn/SAT/issues/77)), Multi-Room-Sync, viele „stale"-Schließungen |
| **HASmartThermostat** | respektiert, aber wartungsmüde | solide PID-Basis, 527★ | Autotune offiziell „not recommended", Restart-Zustandsverlust, 55 offene Issues |
| **Dual Smart Thermostat** | konstruktiv-positiv (aktiver Maintainer) | Dual-Mode/Feature-Breite | UI-vs-YAML-Brüche, Toleranz-Defaults, Feuchte-Features unreif |
| **RoomMind** | engagiert-kritisch (hoher Issue-Durchsatz) | EKF-Konzept + Feature-Breite | Proportional-Logik bei AC/Mischräumen, EKF-Konvergenz-Bugs, Panel-Regressionen, „stale"-Schließungen |
| **ThermoSmart** | wohlwollend, dünne Datenlage | Feature-Versprechen deckungsgleich mit Poise | kein Track-Record; Config-Flow-Validierung ([#1](https://github.com/Mikasmarthome/ThermoSmart/issues/1)) |
| **IHP** | gemischt-positiv, vorbildlich reaktiver Maintainer | Adaptive-Start-Idee | Lernwerte gingen bei Updates verloren (gefixt), enge VTherm-Kopplung |
| **MultiZone Thermostat** | interessiert, aber überfordert | konzeptionell stark (PID-Ventil+Mehrzonen) | YAML-Einstiegshürde, bricht bei HA-Updates |
| **Sonoff TRVZB** | Preis-Leistungs-Liebling | %-Ventilsteuerung, natives external_temperature, FW-Fortschritt | FW-Lotterie, Resets, Adaptive-Mode-Kinderkrankheiten (öffnet nach Soll-Erreichen nicht wieder; ZHA-Lücke) |
| **Danfoss Ally** | Premium-solide | In-Device-Preheat, Adapterauswahl, nativer ext. Sensor | Offset-Refresh-Regeln fummelig, Adaptation-Run undurchsichtig, nächtliches Eigenleben (Uhr-Drift) |
| **Homematic IP Evo** | Hardware-Liebling DACH | leiseste/beste In-Device-Regelung, hydraulischer Abgleich | Preis; Offset-Workarounds verbieten sich wegen Duty-Cycle |
| **AVM FRITZ!DECT 301/302** | pragmatisch („hab ich schon") | DECT-Stabilität, keine Bridge | 5–15-min-Trägheit, FRITZ!OS-vs-HA-Doppelherrschaft |
| **tado°** | stark negativ gekippt | Hardware/UX weiterhin gelobt | Paywall-AGB 02/2025, API-Quota 100/Tag 01/2026, Cloud-Ausfälle → Exodus zu tado_ce/tado-local/Zigbee |
| **Shelly BLU TRV** | gemischt | lokale Ventilposition, Core-Integration | Gateway-Pflicht (max. 5 TRVs), BLE-Latenz/Reichweite, FW-1.5.1-Regelprobleme |
| **Aqara E1 / Moes-Tuya** | Budget-Frust | Preis | laut, ständiges Nachjustieren, 25-%-Ventilschritte, Kalibrierung defekt/kosmetisch, Modus-Resets |
| **Bosch II** | positiv (Geheimtipp) | `remote_temperature` ohne HACS via Z2M, Matter-Variante | Install-Code-Pairing umständlich |
| **Schedy / Scheduler Card** | Scheduler Card: beliebt-simpel; Schedy: eingefroren | Einfachheit | kein Regelanspruch |

---

## 4. Listen-Ergänzungen aus der Nutzerfeedback-Recherche (nach Sinnhaftigkeit)

Diese in der Community stark präsenten Lösungen fehlten in der Markt-Wettbewerbsanalyse und werden ergänzt (Kategorie in Klammern; keine davon ändert das Tier-1-Benchmark-Set):

1. **Optimal-Start-Community-Welle 2026** *(Disziplin-Referenz Optimal Start, A4)*: [SmartHRT](https://community.home-assistant.io/t/smarthrt-smart-heating-recovery-time-cool-sleep-warm-wake-up/833025) · [Smart Dynamic Preheat](https://community.home-assistant.io/t/smart-dynamic-preheat-calculates-lead-time-based-on-warm-up-rate-rather-than-a-fixed-offset-pure-yaml-no-extra-dependencies/1009573) (05/2026, pures YAML) · [Adaptive HVAC Preheat](https://community.home-assistant.io/t/adaptive-hvac-preheat-for-home-assistant-learns-your-system-hits-comfort-time/997235). Bedeutung: unabhängige Bestätigung des Poise-Kernversprechens; als leichtgewichtige Vergleichspunkte für die Optimal-Start-Disziplin geeignet.
2. **ebusd** ([Simon42-Thread ≥163 Beiträge](https://community.simon42.com/t/ebus-und-vaillant/7885)) und **BSB-LAN** *(Kessel-/Erzeuger-Ökosysteme, A7)*: die deutschen DIY-Standards für Vaillant/Wolf bzw. Brötje/Elco — die realen Andock-Ziele für Poises Kesselbedarf-Aktion; OpenTherm ist im DACH-Raum Nische.
3. **tado_ce** ([hiall-fyi/tado_ce](https://github.com/hiall-fyi/tado_ce)) und **tado-local** ([array81/tado-local](https://github.com/array81/tado-local)) *(Workaround-Integrationen, Marktsignal)*: Beleg der Cloud-Flucht; für Feld-A/B gegen tado der praktikable lokale Messpfad.
4. **Z2M-native Sensorkopplung ohne Regel-Integration** *(Baseline-Klasse, A1)*: Sonoff `external_temperature`-Blueprints (bereits gelistet), Bosch-`remote_temperature`-Automation ([Simon42 t/47498](https://community.simon42.com/t/loesung-zur-smarten-heizungssteuerung-in-home-assistant-mit-bosch-thermostaten-generation-2-und-zigbee2mqtt-ohne-3-anbieter-plugins-hacs/47498)), [TRV Calibrator Blueprint](https://community.home-assistant.io/t/trv-calibrator-calibrate-your-valve-with-an-external-sensor-probably-trv-agnostic/451424) — die „gute-genug"-Konkurrenz, gegen die Poise seinen Mehrwert erklären muss.
5. **Active Heating Manager** ([Add-on, t/955093](https://community.home-assistant.io/t/active-heating-manager-add-on/955093)) *(Mehrzonen-Nische, A7)*: Kesselsteuerung aus TRV-Demand.
6. **DIY-Heizkörperlüfter (ESPHome)** ([Simon42 t/1400](https://community.simon42.com/t/diy-heizkoerperluefter-mit-esphome-und-homeassistant/1400)) *(Rand-Referenz, A2/A10)*: populäres Effizienz-Add-on; perspektivisch relevant für Poises Fan-CE-Pfad (ADR-0054 Stufe 3).

Bereits gelistete Kandidaten, deren Community-Gewicht die Recherche bestätigt hat: panhans AHC (dt. Quasi-Standard), TRVZB-External-Temp-Blueprints (de-facto-Standard-Ökosystem), Danfoss-Load-Balancing-Blueprint, thermal_comfort, Scheduler Card, Heating X/HEATHER (Threads inzwischen geschlossen).

---

## 5. Konsequenzen für Poise

**Bestätigte Designentscheidungen (durch Nutzerfeedback belegt):**
- Shadow-first + messbares Flip-Gate (ADR-0026/0055) beantwortet das Blackbox-Misstrauen, das BT/„AI", auto-TPI und tado erzeugt haben.
- Solver-basierte Fenster-Reaktion ohne Setpoint-Restore (ADR-0035/0041) umgeht die häufigste Fehlerklasse des Feldes (verlorene/falsch wiederhergestellte Sollwerte).
- Override-Lebenszyklus mit Auto-Rückkehr und Geräte-Adoption (ADR-0042/0059) trifft einen universellen, ungelösten Wunsch.
- Kesselbedarf-Aggregat (ADR-0039) füllt die artikulierte „call for heat"-Lücke; Anschluss an ebusd/BSB-LAN dokumentieren.
- Zero-Question-Onboarding (ADR-0008), gebündelte Card (ADR-0040), Reason-Transparenz (ADR-0049) — Komplexität ist der meistgenannte Abwanderungsgrund bei VTherm/MultiZone.
- Write-Throttle/Änderungs-Gate (Funkbudget!) und Persistenz inkl. Shutdown-Flush (ADR-0006/0007) — Duty-Cycle- und Restart-Fehlerklassen sind Dauerbrenner.

**Risiken / offene Punkte aus dem Feld:**
1. **TRVZB-FW-Interferenz:** Adaptive Mode (FW 1.4.4) und selbstwechselnde external-Modi kollidieren potenziell mit Poises Schreibpfad — Erkennung + Repair-Hinweis vor dem TPI-Live-Flip (Nachtrag zu ADR-0036 empfohlen; deckt sich mit Wettbewerbsanalyse §4).
2. **Geräte-Quirk-Breite:** Die Offset-/Kalibrier-Fehlerklassen von BT/AHC (Absolutwert in Offset-Entity, Bereichs-Limits ±2,4/±2,5 K, Aqara-Crash-Klasse) als Regressionstests in `model_fixes`/Harness aufnehmen (ADR-0029).
3. **Lern-Korruptions-Szenarien der anderen als Testfälle:** Kessel-aus-Phasen (VTherm #1428), Direktsteuerungs-Echo (RoomMind #241), festgefahrene Zeitkonstante (RoomMind #301) — gegen ADR-0024/0030-Gates prüfen.
4. **Doku-Übersetzung Normband → Nutzererwartung:** Nutzer denken in Solltemperaturen; das EN-Band muss auf der Card selbsterklärend bleiben (ADR-0057-Folge).
5. **FBH-Erwartungsmanagement:** Community rät bei FBH von Absenkung ab — Poises Aktor-Dynamik-Profile (ADR-0052) und Effizienz-Report (ADR-0045) sollten diese Empfehlung pro Raum quantifizieren statt pauschalisieren.
6. **Update-Disziplin als Marktversprechen:** Die BT-1.8-Migrationswelle zeigt, wie teuer Breaking Changes sind — SemVer/Deprecation (ADR-0018) und Golden-File-Regression (ADR-0011) sind auch ein *Vertrauens*-Feature; in Release-Notes sichtbar machen.

**Marktchance in einem Satz:** Das Feld verlangt nachweislich „lokal, erklärbar, abschaltbar, updatefest, funkarm" — Poise ist architektonisch genau darauf gebaut; die Meinungsbild-Belege oben liefern die Argumentationsgrundlage für Doku, Card-Texte und den anstehenden Leistungsvergleich.
