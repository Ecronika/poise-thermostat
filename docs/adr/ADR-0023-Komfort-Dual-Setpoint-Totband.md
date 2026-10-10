# ADR-0023: Capability-aware Dual-Setpoint mit Totband

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-19, Nachträge N1–N3 2026-10-10 · **Bezug:** Livetest v0.6.0, ADR-0010/0016/0017 · **Verifizierung:** EN 16798-1 (Web), RoomMind/Versatile/BT-Code, eigenes Smart-Setpoint-Gist v5.3.1

## Umsetzungsstand (Nachtrag v0.101.0)
Punkte 2–7 sind **live verdrahtet und aktiv** (Capability-Gating, `decide_mode`-Richtung, Prioritäts-Totband, kapazitätskorrektes Idle-Hold, harte Frost-/Schimmel-/Taupunkt-Grenzen; MPC-Totband-Kosten als Shadow). **Punkt 1 — free-running-Widening:** das adaptive Totband-Widening fehlte zunächst (`decide()` verwarf `t_rm` via `_ = t_rm`; `adaptive_band` nur in totem `corridor.py` + `thermal_shock.py` genutzt; kein Test deckte den T_rm-Einfluss — externe Code-Audit-Bestätigung). Es ist nun als pures `comfort/free_running.py` (`free_running_widen`) umgesetzt und **shadow-first** im Coordinator verdrahtet (Diagnose `fr_active`/`fr_heat_sp`/`fr_cool_sp`/`fr_adaptive_lower`/`fr_adaptive_upper`, **keine Writes**); 5 Unit-Tests grün (T_rm speist nun nachweislich das Band). **Sicherheits-Gate:** das Widening greift nur, wenn der Raum **im fixen Totband schwebt** (10 ≤ T_rm ≤ 30, nicht extrapoliert, kein aktiver Heiz-/Kühl-Bedarf) und **hebt nie den Heiz-Sollwert** (`min`) — so kann es eine aktive Konditionierung nie unterdrücken und reproduziert nicht den Ur-Live-Bug (adaptive Neutraltemperatur als warmer Heizsollwert). **Aktivierung bewusst gated:** ein ungegatetes Adaptiv-Widening würde an Hitzetagen (T_rm hoch) den Kühl-Sollwert auf ~31 °C heben und **legitime Sommerkühlung unterdrücken** — die Diagnose macht genau dieses Verhalten zuerst sichtbar; der aktive Schreibpfad behält die fixen Auslegungsbänder (kohärent mit ADR-0051, das das Hitzetag-Kühlziel separat + gekappt regelt).

## Kontext
Livetest: Poise setzte den Sollwert = adaptive Neutraltemperatur `0.33·T_rm+18.8` → 24 °C bei T_rm 15,7 — zu warm fürs Heizen, und es heizte einen bereits 23,5 °C warmen Raum. Ein **einzelner** geklemmter Sollwert ist falsch: er kann ein Nur-Kühlen-Gerät im Sommer an die untere Grenze zwingen (Energieverschwendung) und ignoriert die Gerätefähigkeit.

## Entscheidungstreiber
Normtreue (Heizen ≠ freilaufend); kein unnötiges Konditionieren; Gerätefähigkeit (heizen/kühlen/beides); Nutzer-Priorität Komfort↔Effizienz; harte Sicherheits-/Gesundheitsgrenzen.

## Befund (verifiziert)
- **EN 16798-1:** Auslegung nutzt **„den unteren Wert in der Heizsaison für das Heizsystem und den oberen Wert in der Kühlsaison für das Kühlsystem"** → **zwei getrennte Sollwerte** mit **neutralem Totband** dazwischen. Das Adaptivmodell gilt nur für *freilaufende* Gebäude (keine aktive Heizung/Kühlung).
- **RoomMind = Referenz:** `TargetTemps(heat,cool)` (Komfortkosten 0 im Band), `get_can_heat_cool()` aus `hvac_modes`+`climate_mode`, **symmetrisches Außen-Gating** (`heating_max=22` **und** `cooling_min=16` — „NEVER cool if outdoor < this") → Nur-Kühlen+kalt = idle, kein Heizen; Slider `comfort_weight`→`w_comfort/w_energy`+approach_rate.
- **Eigenes Gist:** löst die Sollwertwahl bereits gut (fester Profilwert ins Band, feste EN-Heiz/Kühl-Bänder Kat. II heat 20–24 / cool 23–26), **aber kein echtes Totband** (ein Sollwert je Richtung) und **kein Winter-Lockout** für Nur-Kühlgeräte.
- **Poise hat das Fundament:** `comfort/cooling.py` (`DualSetpoint`+`decide_mode` mit beidseitigem Gating) — nur nicht verdrahtet.

## Entscheidung
Die Comfort-Schicht liefert je Zone eine **`ComfortDecision`** statt eines Einzel-Sollwerts:
1. **Dual-Setpoint:** `heat_sp` (fester Heiz-Auslegungswert, `comfort_base` ∈ EN-Heizband, ~21) und `cool_sp` (fester Kühl-Auslegungswert, ~26). Dazwischen das **Totband**. Im **free-running**-Regime (10 ≤ T_rm ≤ 30, keine aktive Konditionierung) **erweitert** das EN-Adaptivband das Totband (senkt heat_sp / hebt cool_sp), aber es erzwingt nie einen warmen Heizsollwert.
2. **Capability** aus `hvac_modes` des Aktors → `can_heat`, `can_cool`; Nutzer-Override `climate_mode` (auto/heat_only/cool_only).
3. **Richtung = `decide_mode`** (RoomMind-Muster): heizen nur wenn `room<heat_sp ∧ can_heat ∧ outdoor≤heat_max`; kühlen nur wenn `room>cool_sp ∧ can_cool ∧ outdoor≥cool_min`; sonst **idle**.
4. **Priorität (`comfort_weight`):** verschiebt die Totbandbreite — Effizienz verbreitert (später/sparsamer), Komfort verengt (früher/präziser); Mapping auf die vorhandenen MPC-Gewichte.
5. **Idle = kein Energieaufwand:** der geschriebene Sollwert ist **kapazitätskorrekt** — heizfähig → `heat_sp` (TRV idlet oberhalb), nur-kühlfähig → `cool_sp` (idlet unterhalb). Nie an die falsche Bandgrenze klemmen.
6. **Harte Grenzen:** Frost + Schimmel-Mindesttemp als Heiz-Untergrenze; **Taupunkt-Cap** als Kühl-Obergrenze (gegen Kondensat).
7. **MPC-Kosten totband-bewusst:** Komfortkosten = 0 innerhalb `[heat_sp, cool_sp]` (RoomMind), asymmetrischer Overshoot-Penalty je Richtung.

## Begründung
Der Dual-Setpoint + Totband ist die normkonforme Lösung und behebt beide Live-Fehler (24 °C; Heizen eines warmen Raums). RoomMinds symmetrisches Gating schließt den vom Nutzer benannten Fehlfall (Nur-Kühlen+kalt) aus — die Lücke der eigenen Lösung. Poises `cooling.py` ist die fertige Basis.

## Konsequenzen
**Positiv:** normtreu; keine Energieverschwendung im Totband; gerätekorrekt; kein Heizen in der Kühlsaison und umgekehrt; Priorität steuert Effizienz/Komfort.
**Negativ/Kosten:** Comfort-Schicht von Einzel-Korridor auf Dual-Setpoint umgestellt (berührt `corridor.py`/Pipeline/MPC-Kosten); Capability-Erkennung aus `hvac_modes` nötig; drei neue Config-Werte (`comfort_base`, `climate_mode`, `comfort_weight`).

## Compliance
Norm- und gerätemuster eigenständig umgesetzt; generisch (Fähigkeit aus Standard-`hvac_modes`).

## Verknüpfungen
Erweitert ADR-0010 (Kühlung) und ADR-0017 (Operativ→Luft je Richtung); nutzt ADR-0015 (Capability) und ADR-0009 (MPC-Gewichte). Ersetzt die naive Einzel-Korridor-Zielbildung aus der ersten Comfort-Implementierung.

## Nachtrag N1 (2026-10-10, v0.195.0): Heizbereich nach Raumart — Wohnen ist nicht Büro

**Befund:** `comfort/en16798.py` führte einen einzigen Satz fester Heizgrenzen (Kat. I/II/III: 21–23 / 20–24 / 19–25 °C) mit dem Kommentar, nur Kat. II sei quellengestützt, I/III seien Extrapolation. Gegen die Quelle geprüft (EN 16798-1:2019, Auslegungskriterien wie in REHVA Journal 04/2019, Boerstra, Tabelle 1 tabelliert; operativ, 1,0 clo Winter / 1,2 met): Diese Werte sind exakt die **Büro**-Zeile. Für **Wohnräume** nennt dieselbe Tabelle **21–25 / 20–25 / 18–25 °C**; die Kühlbereiche sind für beide Raumarten gleich. Poise wandte die Bürozeile auf alle Zonen an. Feldwirkung (Zuhause-Anlage): Schlafzimmer und Küche (Kat. III, Basis 19, Effizienzgewicht 40 bzw. 50 %) wurden von 18,1 bzw. 18,3 °C — ihrer eigenen Einstellung — auf 19 °C hochgeklemmt; das Bad (Kat. II, Basis 24) saß auf der Büro-Obergrenze 24 °C, sodass die Tier-2-PMV-Verschiebung dort nie wirken konnte.

**Entscheidung:** `heating_band(category, residential=…)` liefert die Zeile zur Raumart. Die Raumart hängt am vorhandenen Raumprofil (`RoomProfile.residential`): `living`, `bedroom`, `kitchen`, `bathroom` sind Wohnräume; `office` — und damit auch jede Zone ohne oder mit unbekanntem Profil — bleibt auf der Bürozeile. Kein neues Konfigurationsfeld, kein Migrationsbedarf; Zonen mit Büroprofil verhalten sich exakt wie bisher. Verdrahtet an beiden Verwendungsstellen: der Komfortentscheidung (`decide(..., residential=)`, durchgereicht über `stage_comfort_solve`) und dem Optimal-Start-Zielwert (`phase_prepare`). Der Kommentar in `en16798.py` nennt jetzt die Quelle statt „Extrapolation".

**Nicht berührt:** der harte ASR-Deckel 26 °C (ADR-0027) liegt über allen neuen Obergrenzen; Frost-/Schimmel-Floors, Kühlbereiche, adaptive Bänder.

**Wirkung im Feld (erwartet, nicht gemessen):** Wohnraumzonen der Kat. III können wieder unter 19 °C geführt werden, wenn ihre Einstellung das verlangt; Kat.-I/II-Wohnräume dürfen bis 25 °C. Wer in einer Kat.-III-Wohnzone 19 °C will, hebt Basis oder Komfortgewicht an — die Klemme hat das bisher stillschweigend für ihn getan.

**Tests:** beide Zeilen gepinnt; Kat.-III-Schlafzimmerfall (Büro 19,0/en16798 → Wohnen 18,1/comfort_base); Bad-Fall (PMV +0,6: Büro 24,0 → Wohnen 24,6); Raumprofile benennen ihre Raumart, unbekannt/leer bleibt Büro.

## Nachtrag N2 (2026-10-10, v0.196.0): Kühlkante am Auslegungswert der Kategorie

**Befund (Norm-Review 2026-10-10, am Code bestätigt):** §1 sieht `cool_sp ~26` vor; der Code band die Kühlkante an die Heizbasis (`comfort_base + 2 K + widen`). Bei den Standardwerten (Basis 21, Gewicht 70) lag ein belegter, gekühlter Raum damit bei **23,45 °C operativ** — am unteren Rand des Kat.-II-Kühlbereichs 23–26 °C. EN 16798-1 legt die Kühlung auf den oberen Wert aus; der untere Rand kostet Kühlenergie ohne Komfortgewinn, den die Kategorie verlangt. Passt zur beobachteten Über-Kühlung im Büro (Sommer 2026).

**Entscheidung:** `COOLING_DESIGN[cat] = COOLING_UPPER[cat] − 1 K` (I 24,5 / II 25,0 / III 26,0 °C); 1 K Abstand, damit Regelabweichung die Grenze nicht reißt. Auf einem **kühlfähigen** Gerät startet die Kühlkante bei `max(COOLING_DESIGN, comfort_base + 2 K)` und wird wie bisher um Effizienz-Verbreiterung, Präsenz-Eco, PMV-Verschiebung und Lüfter-Gutschrift angehoben, dann in den Kategoriebereich geklemmt. Das `max` erhält die alte Kopplung als Untergrenze: Die Kante liegt **nie tiefer als bis v0.195.0**, und eine warme Basis behält ihr 2-K-Totband (Basis 24 → 26 °C).

**Nur kühlfähige Geräte (CI-Befund 2026-10-10):** Bei einem Gerät, das nicht kühlen kann, kostet die Kühlkante keine Energie — sie ist dort die Bezugsgröße der Lüftungsempfehlung: Freie Kühlung (Regel 3t) öffnet über ihr, und der Schimmel-Wächter (ADR-0066 N2) feuert, wenn die Bauteile eine wärmere Luft verlangen als diese Kante zulässt. Die erste Fassung hob die Kante auch dort an; der Glue-Test `test_mold_guard_reaches_the_bus_and_the_card_attributes` (Kat. III, Basis 17, Fensterzone) bekam dadurch statt „schließen/mold_guard" ein „öffnen/moisture_protect" — gerade das Ergebnis, das ADR-0066 N6/N7 für diese Lage ausschließt. Da die Schimmel-Anforderung bei 24 °C gekappt ist, hätte der Wächter mit einer Kante ≥ 24,5 °C nie mehr auslösen können. Nur-Heiz- und Fensterzonen behalten deshalb `comfort_base + 2 K`.

**Verhaltensänderung:** Nur kühlfähige Zonen im belegten Kühlbetrieb; dort ~1,5 K wärmer (Kat. II, Standard: 23,45 → 25,0 bzw. 25,45 °C mit Gewicht 70). Unbelegt (ADR-0061), Hitzetag-Anhebung (ADR-0051), Nur-Heiz-/Fensterzonen und deren Lüftungsempfehlungen unverändert; die Hitzetag-Anhebung greift ab etwa 32 °C außen (der frühere Kommentar „No-op bei 26 °C" war falsch).

**Nicht umgesetzt:** ein je Zone überschreibbarer Kühlwert. Die Kategorie wählt den Auslegungswert; ein eigenes Feld folgt nur bei Bedarf.

**Tests:** Auslegungswert je Kategorie, Untergrenze durch die alte Kopplung (Basis 24 → 26), Nur-Heiz-Zone behält die Kopplung (Kat. III, Basis 17 → 22), Verbreiterung wirkt weiter, Auslegungswerte liegen streng im Kategoriebereich; zwei Bestandstests auf die neuen Werte angepasst.

### Komfortgewicht neuer Zonen (Review-Punkt P3)
Bei Gewicht 70 senkte die Verbreiterung die belegte Heizkante um 0,45 K (Basis 21 → 20,55 °C operativ, 0,55 K über der Kat.-II-Untergrenze). Entscheidung (Variante B): **neue Zonen speichern beim Anlegen Gewicht 100** (`NEW_ZONE_COMFORT_WEIGHT`), die Heizkante ist dann exakt die eingegebene Basis. Zonen ohne gespeichertes Gewicht — alle vor v0.196.0 angelegten, deren Komfort-Abschnitt nie gespeichert wurde — behalten den Rückfallwert 70 (`DEFAULT_COMFORT_WEIGHT`); das Optionsformular zeigt und speichert den **effektiven** Wert der Zone, damit ein unveränderter Erst-Speichern nichts kippt (AR-16). Keine Migration, keine Änderung der Regelmathematik.

## Nachtrag N3 (2026-10-10, v0.196.1): Neue Zonen sind Wohnräume

**Befund (Folge-Review 2026-10-10):** Seit N1 wählt das Raumprofil auch den EN-Heizbereich. Der Standard blieb `office`, sodass die Wohnzeile nur bei aktiver Umstellung griff — für eine Home-Assistant-Integration der seltenere Fall.

**Entscheidung:** Wie beim Komfortgewicht (N2, Variante B): **neue Zonen speichern beim Anlegen `room_profile = living`** (`NEW_ZONE_ROOM_PROFILE`). Zonen ohne gespeichertes Profil behalten den Rückfall `office` (`DEFAULT_ROOM_PROFILE`); das Optionsformular zeigt und speichert den **effektiven** Wert (AR-16). Die Feldbeschreibung nennt jetzt die Wirkung auf den Heizbereich (sie sagte noch „wirkt nie auf den Sollwert", seit N1 falsch) und beim Komfortgewicht die Absenkung der Heizkante unter die Basis.

**Wirkung:** nur neue Zonen; dort Wohnzeile (Kat. II 20–25 °C) und die PMV-Annahme „living" (met 1,1, Sofa-Isolation).
