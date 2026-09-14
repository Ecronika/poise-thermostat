# Befund 2026-09-12: Unerreichbarer Sollwert ist kein Heizungsfehler

**Status:** Offen — Hypothese formuliert, Messung läuft noch nicht · **Auslöser:** `heating_failure_01KVR01MQ9PVYSA82P609PBDE4`, Zone „Badezimmer Sonoff Test", 2026-09-12 15:39 UTC · **Bezug:** ADR-0012 (Heizungsfehler-Erkennung, Repair-Issues), ADR-0024 (EKF-Identifikation), ADR-0046 (Mehrzonen-Arbitrierung), ADR-0055 (Regelgüte)

> **Dieser Befund entscheidet nichts.** Er hält eine Hypothese, ihre Abgrenzung und den Messplan fest, damit die Kaltsaison sie bestätigen oder widerlegen kann. Die Regel aus ADR-0073 §1.6 — keine Konstante ohne Zahl — gilt für Diagnosen genauso: kein neuer Detektor ohne gemessene Trennschärfe.

## 1. Was beobachtet wurde

Eine gute halbe Stunde nach dem Neustart auf v0.194.0 meldete die Badezimmer-Zone `heating_failure: true`. Die Diagnose derselben Minute:

| Feld | Wert |
|---|---|
| `target_temperature` / `current_temperature` | 24,0 / 22,0 °C |
| `device_hvac_mode` / `hvac_action` | `heat` / `heating` |
| `tpi_duty` / `tpi_valve_percent` | 1.0 / 100 % |
| `valve_health` / `valve_closing_steps` | `ok` / 313 |
| `sp_diverged_writes` / `mode_diverged_nudges` | 0 / 0 |
| `tau_hours` / `confidence` / `identified` | 88,0 / 0,91 / true |
| `ca_deviation_k` / `ca_time_in_band` / `ca_minutes` | 0,23 K / 70,8 % / 72 708 |
| `multi_reason` | `thermal_heat_priority` |

## 2. Warum der Detektor auslöst, und warum er trotzdem das Falsche sagt

`safety/heating_failure.py` implementiert die ThermoSmart-Methode: Bedarf liegt vor, wenn das Gerät `heating` meldet **und** `setpoint − room >= DEFAULT_CMD_DELTA` (2,0 K); über ein rollendes 35-Minuten-Fenster muss der Raum dann `DEFAULT_MIN_RISE` (0,2 K) gewinnen, sonst rastet der Fehler ein.

Der Detektor sucht — laut seinem eigenen Modulkopf — nach **geschlossenem Ventil, leerem Heizkörper, abgeschaltetem Kessel**. Alle drei sind Ereignisse am Gerät oder an der Wärmequelle. Genau die schließt die Tabelle oben aus: Das Ventil ist kalibriert und voll offen, das Gerät meldet ehrlich `heating`, es nimmt unsere Kommandos an (`sp_diverged_writes: 0`), und das thermische Modell ist mit 0,91 Konfidenz identifiziert. Was hier vorliegt, ist keine ausgefallene Komponente, sondern eine **Wärmebilanz, die unterhalb des Ziels schließt**.

Erschwerend: Der Raum steht bei 22,0 gegen 24,0 exakt **auf** der 2,0-K-Bedarfsschwelle. Der Fehler wird daher nicht stabil anstehen, sondern um die Schwelle herum flackern — einrasten, nach 35 bedarfsfreien Minuten klären, wieder einrasten. Ein Repair-Issue, das niemand abstellen kann und das von selbst wiederkommt, ist dieselbe Geräuschklasse wie die verwaisten Issues aus ADR-0072 N1.2.

### 2.1 Der Flackermechanismus ist benennbar — und es ist die Anwesenheit

Das Flackern ist kein Zufall an der Schwelle, sondern ein Taktgeber. Die Zone hat `absence_after_min: 30.0` und einen Belegungssensor; `resolve_presence` (ADR-0058) schaltet innerhalb des Komfortfensters nach 30 Minuten Raumleere auf `ROOM_ECO`, was den Sollwert um `DEFAULT_ECO_DELTA_K` (2,0 K) senkt. Im Bad heißt das: **24,0 °C, solange der Raum als kürzlich benutzt gilt — 22,0 °C danach.**

Damit ergibt sich pro Badbenutzung dieser Ablauf:

1. Jemand verlässt das Bad. `room_absent_min` läuft los, der Sollwert bleibt 30 Minuten auf 24,0.
2. In diesen 30 Minuten ist `setpoint − room` ≥ 2,0 K und das Gerät meldet `heating` → der Detektor hat Bedarf, sein 35-Minuten-Fenster läuft.
3. Nach 30 Minuten greift `ROOM_ECO`, der Sollwert fällt auf 22,0 — das ist genau die gemessene Raumtemperatur. Der Bedarf endet.
4. 35 bedarfsfreie Minuten später klärt der Latch.

Die Diagnose vom 12.09. wurde bei `room_absent_min: 24.1` gezogen — also mitten in Schritt 2. Das Issue ist damit kein Dauerzustand, sondern ein **Nebenprodukt jeder Badbenutzung**: Es erscheint, wenn jemand das Bad verlässt, und verschwindet gut eine Stunde später von selbst. Ob es überhaupt einrastet, hängt davon ab, ob das 35-Minuten-Fenster in Schritt 2 voll wird — bei 30 Minuten Karenz also knapp und wetterabhängig. Genau das erzeugt ein Erscheinungsbild ohne erkennbares Muster.

Das schärft §6.2: Die Flackerrate ist nicht gegen die Zeit zu messen, sondern **gegen die Badbenutzungen**. Und es verschiebt die Bewertung des Mangels: Eine Hysterese um `DEFAULT_CMD_DELTA` würde hier nichts helfen, weil der Sollwert springt, nicht die Temperatur. Was helfen würde, ist eine Karenz, die kürzer ist als das Detektorfenster — oder ein Detektor, der einen Sollwertsprung als Fensterabbruch wertet statt als Bedarfsende mit Latch.

## 3. Die Anlage (Betreiberangabe, 2026-09-12)

Das Badezimmer hat wenig Heizleistung und steht ungenutzt mit offener Tür. Die Wohnung wird generell mit offenen Türen betrieben. Die Wunschtemperatur erreicht das Bad nach Betreiberaussage nur im Sommer oder nach langem heißem Duschen.

Damit ist die Wohnung thermisch näherungsweise **eine** Zone. Der erreichbare Unterschied zwischen zwei Räumen wird dann nicht von der Regelung bestimmt, sondern vom Verhältnis aus Heizkörperleistung und konvektivem Austausch durch die offene Tür. Das gilt für jeden Thermostaten; es ist keine Eigenschaft von Poise. τ = 88 h ist genau die Signatur davon: Der Raum hat keine eigene Zeitkonstante mehr, er hat die gedämpfte der Wohnung.

Die Konfiguration verschärft es: `comfort_base: 24.0` bei `comfort_weight: 100` und Komfortfenster 05:00–22:00 heißt, dass Poise 17 Stunden am Tag ein Ziel hält, das die Anlage nicht erreicht — mit Ventil auf 100 % und dauerhaftem `thermal_heat_priority` in der Mehrzonen-Arbitrierung. Die Wärme verlässt den Raum durch die offene Tür, statt ihn aufzuheizen.

## 4. Hypothese

Poise sollte zwei Zustände unterscheiden, die heute beide als `heating_failure` erscheinen:

* **Defekt** — ein *Ereignis*. Etwas hat aufgehört zu funktionieren; es gibt einen Vorher/Nachher-Punkt.
* **Unerreichbarkeit** — ein *Zustand*. Die Anlage läuft bestimmungsgemäß am Anschlag, und die stationäre Bilanz schließt unterhalb des Sollwerts. Es gibt keinen Vorher/Nachher-Punkt; der Zustand war immer da und hängt an der Witterung.

Der Unterschied ist nicht kosmetisch, weil er auf verschiedene Handlungen zeigt: Ein Defekt gehört repariert, eine Unerreichbarkeit gehört **konfiguriert** (erreichbarer Sollwert plus Boost bei Bedarf) oder **hingenommen**.

### 4.1 Kandidaten für die Trennschärfe

Die ersten vier sind Momentaufnahmen und schließen nur aus; der fünfte ist der eigentliche Diskriminator und braucht Zeitreihen.

1. `sp_diverged_writes == 0` und `mode_diverged_nudges == 0` — das Gerät nimmt an, was wir schreiben. Ein Aktor, der unsere Kommandos verliert, fällt hier auf.
2. `valve_health == "ok"` mit substanziellen `valve_closing_steps` — das Ventil ist beweglich und kalibriert (`valve_stuck` greift unter 10 Schritten).
3. `hvac_action == "heating"` bei `tpi_duty == 1.0` — das Gerät fordert Wärme in voller Höhe an, hält also nicht still.
4. `identified == true` mit hoher Konfidenz — der EKF hat eine konsistente Anlage gesehen. Ein leerer Heizkörper oder ein abgestellter Kessel ließe die Aufheizrate einbrechen, das Modell also anders aussehen.
5. **Die erreichbare Übertemperatur fällt monoton mit der Außentemperatur.** Bei einer Leistungsgrenze ist der stationäre Abstand eine Funktion der Witterung; bei einem Defekt springt er. Das ist der Punkt, an dem sich die beiden Zustände sauber trennen — und der einzige, der ohne Kaltsaison nicht messbar ist.

## 5. Warum jetzt nicht entschieden wird

**Heute heizt genau ein Raum gegen die ganze Wohnung.** Das ist der Extremfall der Kopplung, nicht der Normalfall: Der Bad-Heizkörper speist eine offene Wohnung, deren übrige Räume noch keine Wärme anfordern. Sobald im Herbst mehrere Zonen gleichzeitig heizen, wird die Kopplung symmetrisch, das Gefälle über die offenen Türen kleiner und der stationäre Abstand des Bades geringer. Ob dann überhaupt noch ein Befund übrig bleibt — und in wie vielen Zonen — ist genau die offene Frage.

Ein Detektor, der auf der Datenlage einer einzelnen September-Zone entworfen wird, würde diese Verzerrung mit einbauen. Dieselbe Lehre wie bei der Schreiblast: Der Sollwert-Fix war verteidigungsfähig, weil 1440/Tag gemessen waren, bevor eine Zeile Code fiel.

## 6. Messplan Kaltsaison

Nötige Daten sind vorhanden; `trace_recording` ist in den betroffenen Zonen aktiv.

1. **Je Zone, stationär:** `heat_sp − current_temperature` in den Fenstern mit `tpi_duty == 1.0` bzw. Ventil 100 %, aufgetragen gegen `t_rm`. Erwartung bei Leistungsgrenze: monotoner Zusammenhang, keine Sprünge.
2. **Flackerrate:** wie oft `heating_failure` je Zone einrastet und wieder klart — aufgetragen **gegen die Raumbenutzungen**, nicht gegen die Zeit (§2.1). Zu prüfen ist, ob das Einrasten mit dem 30-Minuten-Karenzfenster nach Verlassen des Raums zusammenfällt.
3. **Kopplung:** Temperaturdifferenz Bad ↔ benachbarte Zone, aufgelöst nach der Anzahl gleichzeitig heizender Zonen. Das ist die Messung, die den September-Extremfall vom Winterfall trennt.
4. **Gegenprobe:** mindestens eine Zone, die ihren Sollwert erreicht, als Kontrollgruppe — dieselbe Rolle, die `climate.badezimmer_sonoff_trv` im Schreiblast-Befund hatte.

## 7. Sofortmaßnahme (Konfiguration, unabhängig von diesem Befund)

Unabhängig davon, ob Poise je eine eigene Diagnose bekommt: Ein Sollwert, den die Anlage 17 Stunden am Tag nicht erreicht, kostet dauerhaft volles Ventil und Vorrang in der Arbitrierung, ohne den Raum wärmer zu machen. `comfort_base` im Bad auf einen erreichbaren Wert und das Duschen über den ohnehin konfigurierten Boost (`override_policy: "timer"`, `boost_duration_min: 60`) löst die Bedarfsbedingung **wahrheitsgemäß** auf, statt die Meldung wegzuklicken. Die Schimmelpflicht bleibt davon unberührt (`mould_index: 1.0`, `surface_rh_mean: 68,9 %` gegen `rh_max_safe: 75,7 %`).

## 8. Offene Punkte

1. Der Messplan aus §6 läuft frühestens ab Mitte Oktober an.
2. Ob die Unterscheidung ein eigener Detektor wird, eine zusätzliche Klassifikation innerhalb von `heating_failure`, oder nur ein anderer Text im Repair-Issue, ist bewusst offen — das entscheidet die gemessene Trennschärfe, nicht der Entwurf.
3. Das Flackern aus §2.1 ist ein eigenständiger Mangel, unabhängig von der Diagnosefrage. Eine Hysterese um `DEFAULT_CMD_DELTA` greift dabei am falschen Ende — der Sollwert springt, nicht die Temperatur. Zu prüfen sind stattdessen: Karenz kürzer als das Detektorfenster, oder ein Sollwertsprung, der das laufende Fenster abbricht statt es als Bedarfsende mit Latch zu werten. Entscheidung erst mit der Rate aus §6.2.
4. **Der Hausgate greift — verifiziert am 12.09., siehe §9.** Ein Wochentags-Zeitplan für das Werktagsproblem ist damit überflüssig.
4. Die Mehrzonen-Kopplung über offene Türen ist in keinem ADR beschrieben. Falls §6.3 sie deutlich zeigt, ist das ein eigenes Thema — nicht Teil dieses Befunds.

## 9. Nachtrag 2026-09-12: der Hausgate ist verifiziert

Anlass war die Frage, ob die Komfortzeit des Bades (05:00–22:00, maskenlos, also alle Tage) werktags durch eine Wochentagsmaske eingeschränkt werden sollte — die Wohnung ist werktags 07–17 Uhr leer. Die Antwort ist nein, und zwar aus Messung, nicht aus Entwurf.

**Historie der beiden Personen-Entitäten, Do 10.09. und Fr 11.09.:** Keine der beiden ist zwischen etwa 06:30 und 17:30 (bzw. 19:00) im Zustand `Zuhause`. Die Zustände in diesem Fenster sind durchgehend `Büro` (benannte Zone) oder `Abwesend`. Lücken mit `unknown`/`unavailable` gibt es in den zwei Tagen nicht — die grauen Segmente der Zeitleiste sind `Abwesend`, nicht „unbekannt" (stichprobenhaft geprüft: 10.09. 12:03:59–12:48:44, 44:44 min).

**Das genügt, um den Gate zu schließen.** `InputReader.tristate` behandelt eine Person in einer BENANNTEN Zone ausdrücklich als aufgelöstes, sicheres „nicht zu Hause" und nicht als Sensorfehler — nur `unknown`/`unavailable` liefern `None` und damit den fail-safe „anwesend". `any_present` OR-reduziert über die konfigurierten Entitäten; beide `False` heißt `home is False`, und `resolve_presence` liefert dann `AWAY`, unabhängig vom Komfortfenster. Der volle Setback-Pfad läuft also werktags von selbst.

**Kreuzprobe an zwei unabhängigen Zeitpunkten:** Zum Aufnahmezeitpunkt der Diagnose (Sa 12.09., 17:51 Ortszeit) waren beide Personen `Zuhause` — passend zu `home_present: true` im Dump. Rund fünfzehn Minuten später standen beide auf `Abwesend`, passend zum Live-Zustand in den Entwicklerwerkzeugen. Die Verknüpfung zwischen `presence_home` und diesen Entitäten ist damit aus zwei übereinstimmenden Zeitpunkten erschlossen, nicht aus der Konfiguration gelesen; der Options-Dialog der Zone wäre der letzte Beweis, falls er je gebraucht wird.

**Zwei Folgerungen.**

Erstens ist die Wochentagsmaske (P2.3, `comfort_days(_N)`) hier das schwächere Werkzeug, obwohl sie vorhanden und einsatzbereit ist: Ein Kalender rät, die Anwesenheit misst. Feiertag, Krankheit und Urlaub — vom Betreiber selbst als die Ausnahmen genannt — trägt der Gate ohne Zutun, eine Maske bekäme sie falsch. Was dem Kalender bleibt, ist das, was wirklich kalendarisch ist: wann geduscht wird. Das heutige Fenster 05:00–22:00 leistet das nicht.

Zweitens schließt das den Werktags-Tagbereich als Quelle des `heating_failure` aus: Dort läuft `AWAY`, der Sollwert driftet, die Bedarfsbedingung `setpoint − room >= 2,0 K` bei gemeldetem `heating` entsteht gar nicht erst. Das Issue muss also aus Abenden und Wochenenden stammen — genau das Muster, das §2.1 aus der 30-Minuten-Karenz nach Badbenutzung herleitet. Die beiden Befunde stützen sich gegenseitig.
