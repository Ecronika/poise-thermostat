# ADR-0073: Schreibökonomie, zweiter Durchgang — Modus, Sensorquelle, und der Zensus, den es vorher nicht gab

**Status:** Implementiert (v0.194.0) · **Wirkung:** Live-A · **Datum:** 2026-09-12, Nachtrag 2026-09-20 (§1.5a: Feed-Zähler aufgeteilt, v0.194.8) · **Bezug:** [ADR-0072](ADR-0072-Schreiboekonomie-Kommando-Episode.md) (Kommando-Episode — das Primitiv, auf dem hier aufgesetzt wird), ADR-0012 (Write-Totband), ADR-0015 (Aktorpfad), ADR-0029 (Externer Temperatur-Feed, Sensorquellen-Select), ADR-0046 §8 (Verdichterschutz — die andere Nudge-Sperre), ADR-0052 §4 (Regelperiode — weiterhin **nicht** angefasst)

> **Warum ein eigener ADR statt eines zweiten Nachtrags zu ADR-0072:** Weil hier eine andere Frage beantwortet wird. ADR-0072 fragt: *Woher weiß Poise, dass ein Schreibvorgang nichts bewirken kann?* — und antwortet mit einem Beweis (dem Fixpunkt). Dieser ADR fragt: *Was tut Poise, wenn ein Schreibvorgang etwas bewirken soll und nachweislich nicht wirkt?* Darauf gibt es keinen Beweis, nur eine Rate. Die beiden Antworten sehen im Code ähnlich aus und dürfen im Kopf nicht verwechselt werden.

## Kontext

ADR-0072 hat einen Kanal befestigt. Ein externes Review des Standes nach v0.193.1 hat gefragt, was mit den anderen ist — und die Frage war berechtigt: Poise schreibt auf **fünf** Kanäle, und für vier davon gab es weder eine Bremse noch eine Zahl.

Zwei davon haben dieselbe Bauform wie der Befund von ADR-0072, nämlich „Gate sagt jeden Tick ja, weil sich nichts ändert":

* **Modus.** `needs_mode_nudge` ist wörtlich `current != desired`, ausgewertet pro Tick. Ein TRV, das in seinen eigenen Wochenplan zurückfällt (`system_mode: auto` beim Sonoff TRVZB), ein Gerät, das `heat` ablehnt, ein verlorener Zigbee-Frame — jeder dieser Fälle erzeugt 1440 `set_hvac_mode`-Aufrufe am Tag, auf derselben Batterie, aus demselben Grund.
* **Sensorquellen-Select.** Die ADR-0029-Rückgabe ist in **jedem** Tick eines Raumsensor-Ausfalls fällig, solange der Select `external` meldet — und das Schreiben ist das Einzige, was das ändern könnte. Ein Gerät, das den Select eigenmächtig zurückstellt, wird also für die gesamte Dauer des Ausfalls im Minutentakt beschrieben.

Der dritte fehlende Kanal war keiner: Es war die Messung. Der Sollwert-Fix aus ADR-0072 war verteidigungsfähig, weil 1440/Tag **gemessen** waren, bevor eine Zeile Code fiel. Für Modus, Feed, Kalibrierung und Select existiert keine solche Zahl — nicht einmal eine schlechte.

## 1. Entscheidung

### 1.1 M5 — Ratenlimit für den Modus, und ausdrücklich kein Veto

`mode_reassert_throttled` in `control/write_economy.py`, `MIN_MODE_REASSERT_INTERVAL_S = 600.0`. Ein identischer Re-Nudge desselben Modus wartet; ein echter Moduswechsel (`desired != last_commanded_hvac` — dieselbe Prüfung, die der Executor zur Dispatch-Zeit als `mode_changed` auswertet) geht sofort raus, ebenso der erste Nudge eines Laufs.

**Es gibt bewusst kein M2-Gegenstück für den Modus, und das ist die eigentliche Entscheidung dieses Abschnitts.** Das Idempotenz-Veto ruht auf einem Fixpunkt: Das Gerät ist auf einem Wert zur Ruhe gekommen, den sein Raster darstellen kann, also kann dasselbe Kommando es beweisbar nicht bewegen. Nichts davon überträgt sich. Ein Gerät im falschen **Modus** hat sich nicht „auf eine darstellbare Näherung gelegt" — es hat das Kommando abgelehnt oder verloren. Die ehrliche Lesart eines Modus, der nicht greift, ist ein Fehler, und die Antwort auf einen Fehler ist Weiterbehaupten, nur langsamer. Sechzigmal pro Stunde ist keine Beharrlichkeit, sondern Rauschen; zehnmal pro Stunde ist beides nicht.

Die Diagnose bleibt, wo sie hingehört: bei `safety/write_convergence`.

### 1.2 Der Fold-Platz ist Teil der Entscheidung

Die Drossel sitzt **nach** `convergence.observe_mode(...)` und **vor** dem Dispatch. Beide Hälften tragen.

*Danach*, weil ein gedrosselter Re-Nudge genau dieselbe Evidenz ist wie ein gesendeter: Das Gerät steht immer noch im falschen Modus und bewegt sich immer noch nicht. Das ist das T2-Argument aus ADR-0072 §2.6, unverändert auf den zweiten Kanal angewandt. Läge die Drossel davor, bekäme der Detektor für „dieses Gerät wendet unsere Kommandos nie an" eine Evidenz pro zehn Minuten statt eine pro Tick — das Limit hätte dann die **Diagnoserate** geändert, obwohl es die **Schreibrate** ändern sollte.

*Davor*, weil sie den Schreibvorgang tatsächlich abbestellen muss. Ein vom Verdichterschutz (ADR-0046 §8) blockierter Tick ist der Gegenfall: Der setzt `_mode_nudge` schon oberhalb auf `False` und ist absichtlich **keine** Evidenz — dort haben wir nicht behauptet und nichts gelernt.

### 1.3 Zwei Uhren für den Modus, weil eine nicht reicht

`last_hvac_cmd_ts` wird nur bei einem echten Moduswechsel gestempelt. Das ist richtig und muss so bleiben: Der Stempel schärft das Modus-Echofenster, und ein Neuschärfen bei jedem identischen Re-Nudge hielte das Fenster für immer offen und blockierte die Modus-Adoption dauerhaft.

Genau diese Eigenschaft macht ihn als Uhr für ein Ratenlimit unbrauchbar — ein Stempel, der stillsteht, kann keine Rate messen. Das Limit liefe einmal ab und danach nie wieder. Also gibt es `last_mode_nudge_ts`, gestempelt bei **jedem** Dispatch. Dieselbe Aufteilung wie auf der Sollwert-Seite: `last_sp_write_ts` (physischer Schreibvorgang) gegen `cmd_episode_ts` (Kommandowechsel), gespiegelt.

Folge, ausdrücklich: `now=` ist jetzt bei **jedem** erfolgreichen `mode_nudge`-Commit Pflicht, nicht mehr nur bei einem wechselnden.

### 1.4 Backoff für die Sensorquellen-Rückgabe

`sensor_source_handback_target` bekommt `last_attempt_ts`/`now`, `SELECT_HANDBACK_RETRY_S = 300.0`. Der **erste** Versuch eines Ausfalls bleibt sofort — ein Raumsensor-Ausfall ist ein Sicherheitsereignis, und die Rückgabe darf nicht hinter einem Timer warten; erst die Wiederholungen sind gebremst. 300 s statt 600 s, weil dieser Pfad nur während eines Ausfalls läuft und der Gesundheitsboden des sicheren Zustands erst dann gegen den geräteeigenen Sensor durchgesetzt wird, wenn die Rückgabe gegriffen hat.

Ohne `last_attempt_ts`/`now` ist der Backoff aus — die reinen Aufrufer, die nur „ist eine Rückgabe fällig" fragen, bleiben unverändert.

### 1.5 Der Write-Zensus

Fünf Zähler auf `ActuatorRuntime`: `setpoint_writes`, `mode_writes`, `external_temp_writes`, `calibration_writes`, `select_writes`. Kumulativ seit Prozessstart, transient, nur im Diagnose-Dump — **nicht** in der `_ATTRS`-Erlaubnisliste, also keine Änderung am Attributvertrag aus ADR-0016.

Drei Gestaltungsentscheidungen:

1. **Einmal gefaltet, nicht pro Zweig.** Der Zensus liegt am Kopf der Commit-Schleife, über eine Tabelle `effect_id → Kanal`. Ein Zähler, der neben der Regel wohnt, die er zählt, kann nicht von ihr abdriften.
2. **Rettungs- und Sicherer-Zustand-Pfade zählen auf dieselben Kanäle.** `rescue_write` und `safe_setpoint` schreiben dasselbe physische Register wie `setpoint_write`; ein Zensus, der sie versteckte, würde genau die Situationen untertreiben (Ausfall, Frost), in denen die Schreibvorgänge sich häufen.
3. **Transient.** Ein persistierter Zähler würde das Vorher/Nachher einer Parameteränderung verwischen — das Einzige, wozu der Zensus da ist. Ein Neustart ist eine sichtbare Unstetigkeit, kein stiller Reset.

`fan_write` hat absichtlich keinen Kanal: keine thermische Aktuierung, keiner der fünf genannten Kanäle.

### 1.5a Der Feed-Zähler wird aufgeteilt (Nachtrag, v0.194.8)

Die erste Zensuswoche hat gezeigt, dass `external_temp_writes` die Frage, für die er gebaut wurde, **nicht** beantworten kann. `external_feed_due` ist ein ODER aus „Wert bewegt (≥ 0,1 K)" und „Keepalive abgelaufen (600 s)", und **jeder** Schreibvorgang setzt die Keepalive-Uhr zurück. Die beiden Auslöser verschlucken sich also gegenseitig: ein Totbandschreiben verschiebt das nächste Keepalive-Schreiben, ein Keepalive-Schreiben setzt den Vergleichswert für das nächste Totband. Aus einer Summe ist der Anteil nicht rekonstruierbar — und damit ist §1.6 („keine Konstante ohne Zahl") für **beide** Feed-Konstanten unerfüllbar.

Gemessen über 84,1 h auf fünf Zonen (Neustart 2026-09-16, aus der Zustands-Histogramm-Verteilung bestimmt, da kein Uptime-Sensor existiert):

| Zone | Sollwert | Feed | Feed/Tag | mittlerer Feed-Abstand |
|---|---:|---:|---:|---:|
| Bad | 95 | 590 | 168 | 8,55 min |
| Büro | 32 | 578 | 165 | 8,73 min |
| Wohnzimmer | 27 | 568 | 162 | 8,88 min |
| Küche | 77 | 564 | 161 | 8,95 min |
| Schlafzimmer | 34 | 543 | 155 | 9,30 min |

Kalibrierung 0, Modus 0, Select 7 gesamt. Feed zu Sollwert steht **10,7 : 1** — der Feed ist der mit Abstand teuerste Kanal, nicht der Sollwert.

**Und der mittlere Abstand liegt unter der Keepalive.** 8,55–9,30 min gegen 10 min: 7,6–16,9 % der Feeds kommen aus dem Totband, nicht aus der Uhr. Damit ist die stehende Schlussfolgerung vom 12.09. („reine Keepalive-Kadenz, 144/Tag") **widerlegt** — über eine Woche, nicht über einen Tag. Sie stand auf einem zu kurzen Fenster.

Also ein sechster Zähler: `external_temp_writes_deadband`, eine **Teilmenge** von `external_temp_writes`; der Keepalive-Anteil ist die Differenz. Entschieden wird er **im Commit**, nicht im Plan: dort liegen `last_fed` und der gesendete Wert noch ungestempelt nebeneinander, dasselbe Prädikat auf denselben zwei Zahlen. Ein vom Plan durchgereichter „Grund" wäre eine zweite Kopie des Gates und dürfte von ihm abweichen. `tests/test_phase6b_stages.py` fährt Gate und Commit deshalb gemeinsam.

Das Feed-Totband bekommt bei dieser Gelegenheit einen Namen (`EXTERNAL_FEED_DEADBAND_K = 0.1`) — es stand als Literal an der Aufrufstelle, und Commit und Plan müssen dieselbe Zahl prüfen. Verhalten unverändert.


### 1.6 Was hier ausdrücklich **nicht** entschieden wird

Kein einziger Schwellwert wird getunt. Nicht das Feed-Totband (0,1 K), nicht die Feed-Keepalive (600 s), nicht `CALIBRATION_MIN_INTERVAL_S` (300 s).

Das ist die Reihenfolge-Entscheidung dieses ADR, und sie ist die wichtigste darin: **Struktur zuerst, Zahlen nach der Messung.** Der Sollwert-Fix war verteidigungsfähig, weil die 1440 vor dem Code standen. Eine Keepalive von 600 auf 1800 zu heben, ohne zu wissen, wie viele Feed-Schreibvorgänge tatsächlich anfallen, wäre genau die Sorte plausibler Änderung, die dieser Befund acht Revisionen lang widerlegt hat. Der Zensus aus §1.5 ist die Voraussetzung; Phase 2b ist der Termin.

## 2. Der externe Temperatur-Feed — recherchiert, und zwei Befunde geändert

Der Feed war der vierte Punkt des Reviews. Er wird hier **nicht** geändert, aber die Recherche gehört festgehalten, weil sie die Phase-2b-Entscheidung vorbestimmt und weil sie einen Fehler im aktuellen Stand aufgedeckt hat.

**Geräte-Timeouts sind real, aber weit auseinander und überwiegend undokumentiert.**

| Gerät | Verhalten | Quelle |
|---|---|---|
| Danfoss Ally (`external_measured_room_sensor`, −8000…3500 in 0,01 °C, −8000 = aus) | `radiator_covered: false`: Deaktivierung nach **3 h** ohne Update, Empfehlung „höchstens alle 30 min bzw. bei 0,1 K Änderung". `radiator_covered: true`: **35 min**, Empfehlung höchstens alle 5 min | Z2M-Gerätedoku 014G2461 |
| SONOFF TRVZB (`external_temperature_input`, `temperature_sensor_select`) | Rückfall auf den internen Sensor bestätigt, **Dauer nirgends dokumentiert**; Z2M sagt ausdrücklich, die Synchronisation sei Sache des Aufrufers | Z2M-Gerätedoku TRVZB, Z2M-Diskussion #26308 |
| Aqara SRTS-A01 (`sensor: internal/external`, `external_temperature_input`) | Rückfall vorhanden, **Dauer unbekannt**; ZHA-PR #4564 nennt kein Intervall | Z2M-Gerätedoku SRTS-A01, zha-device-handlers #4564 |

**Befund 1 — die aktuelle Keepalive ist zu schnell, nicht zu langsam.** `EXTERNAL_FEED_KEEPALIVE_S = 600.0` ist beim Danfoss im Auto-Offset-Modus dreimal häufiger als der Hersteller ausdrücklich empfiehlt („höchstens alle 30 Minuten"). Eine globale Konstante kann das nicht auflösen: Derselbe Hersteller verlangt im `radiator_covered`-Modus **alle 5 Minuten**. Die Keepalive gehört damit an die Gerätefamilie, nicht an eine `Final`-Zeile in `const.py`.

**Befund 2 — es gibt zwei Ausfallarten, nicht eine.** Beim Aqara und beim TRVZB berichten Anwender nicht, dass der **Wert** verfällt, sondern dass der **Modus** zurückspringt: `sensor`/`temperature_sensor_select` steht plötzlich wieder auf `internal` (TRVZB: Z2M #29650, „at random times", closed as not planned; Aqara: das verbreitete HA-Blueprint prüft deshalb bei jedem Feed, ob der Select noch `external` ist, und setzt ihn sonst neu). Eine reine `external_temperature_timeout`-Capability deckt nur die halbe Ausfallart ab. Die zweite braucht keinen Timer, sondern eine Re-Assertion mit Backoff — dieselbe Bauform wie §1.4.

**Der Algorithmus bleibt, wie er ist.** `external_feed_due` ist bereits „Änderung ≥ Totband → sofort, sonst erst wenn die Keepalive abläuft". An Phase 2b geht also nur die Parametrierung: Totband 0,1 → 0,2 K, Keepalive **pro Gerätefamilie** (Danfoss auto-offset 1800 s, `radiator_covered` 300 s, alles Unbekannte 1200–1500 s) und die Select-Re-Assertion als zweite, unabhängige Achse.

## 3. Verworfene Alternativen

* **Ein Idempotenz-Veto für den Modus** („das Gerät steht seit N Ticks in `auto`, also bringt `heat` nichts"). Die Prämisse ist falsch: Dass ein Kommando bisher nicht griff, beweist beim Modus nichts über das nächste — anders als beim Sollwert gibt es keine Rasterdarstellung, die den Fixpunkt trägt. Ein solches Veto würde eine Zone still verlieren.
* **Die Drossel vor den Watchdog-Fold legen.** Wäre ein Zeile kürzer und würde den Divergenz-Detektor um den Faktor zehn verlangsamen. Siehe §1.2.
* **`last_hvac_cmd_ts` unbedingt stempeln** und sich die zweite Uhr sparen. Hält das Echofenster dauerhaft offen und blockiert die Modus-Adoption — der Fehler, den die bestehende `mode_changed`-Gatterung ausdrücklich verhindert.
* **Den Zensus persistieren.** Verwischt genau die Unstetigkeit, die man beim Auswerten braucht.
* **Die Konstanten jetzt schon tunen.** §1.6.
* **Eine einzige `external_temperature_timeout`-Zahl für alle Geräte.** §2, Befund 1 und 2.

## 4. Umsetzung (v0.194.0)

| Ort | Was |
|---|---|
| `control/write_economy.py` | `MIN_MODE_REASSERT_INTERVAL_S`, `mode_reassert_throttled` (rein) |
| `safety/sensor_watchdog.py` | `SELECT_HANDBACK_RETRY_S`, Backoff-Parameter an `sensor_source_handback_target` (rückwärtskompatibel) |
| `runtime/state.py` | `last_mode_nudge_ts`, `mode_reasserts_suppressed` (external); `last_handback_ts` + fünf Zähler (actuator) — alle transient |
| `runtime/zone_runtime.py` | `_WRITE_CHANNELS`-Tabelle + der einmalige Zensus-Fold; `now=`-Pflicht für jeden `mode_nudge`-Commit |
| `ha/phase_actuate.py` | M5-Gate nach dem Watchdog-Fold; Backoff-Stempel auf dem Unavailable-Pfad |
| `ha/phase_report.py` | sechs Diagnose-Schlüssel, keiner in `_ATTRS` |

## 5. Prüfstand

Rein (`tests/test_write_economy.py`): `_run_mode_nudge_loop` komponiert `needs_mode_nudge` + M5 + Commit in der Reihenfolge des echten Segments. 30 Minuten Verweigerung ergeben **3** Nudges statt 30, und der Lauf verstummt nie (180 Minuten → 18). Die T2-Beziehung ist als Gleichung gepinnt: jeder Re-Nudge ist Evidenz, gesendet oder gedrosselt. Der Backoff ist an seinen vier Kanten geprüft, inklusive „ein Select auf `internal` wird gar nicht erst geschrieben".

Verträge: `tests/test_phase6b_stages.py` hält die beiden Modus-Uhren jetzt getrennt fest — `last_hvac_cmd_ts is None`, `last_mode_nudge_ts == NOW` — statt wie bisher beides in einem Satz. `tests/integration/test_phase0_data_contract.py` friert die sechs neuen Dump-Schlüssel ein.

## 6. Offene Punkte

1. **Phase 2b wartet auf Daten**, nicht auf Code: eine Woche Zensus aus der Referenzanlage, dann Feed-Totband, Feed-Keepalive pro Gerätefamilie und `CALIBRATION_MIN_INTERVAL_S`. *Stand 20.09.:* die Woche liegt vor (§1.5a), aber sie hat zuerst den Zähler widerlegt und nicht die Konstante — die Uhr für Phase 2b läuft ab der Aufteilung neu. `CALIBRATION_MIN_INTERVAL_S` bleibt ausdrücklich unangetastet: **0** Kalibrierschreibvorgänge in fünf Zonen über 84 h sind keine Grundlage für eine Änderung, in keine Richtung.
2. **Select-Re-Assertion als eigene Achse** (§2, Befund 2) — noch nicht entworfen.
3. **Die Gerätedatenbank braucht drei Zustände, nicht zwei:** dokumentierter Timeout, bestätigter Rückfall ohne Dauer, kein externer Eingang. Beim Aqara steht ausdrücklich *Timeout vorhanden / wahrscheinlich mehrere Stunden; konkrete Dauer unbekannt* — daraus darf keine erfundene „30 min" werden.
4. Aus ADR-0072 §8 unverändert offen: M3-Rasterlernen, die fünfte `customize`-Zeile (die Messung liegt inzwischen vor, sie kann fallen). Die Bedienstepper-Frage ist vom Betreiber verworfen.

---

## Konsequenzen

Der Modus-Kanal kann nicht mehr 1440-mal am Tag dasselbe sagen, ohne dass irgendetwas leiser wird — und er wird trotzdem nie still, weil ein Modus, der nicht greift, ein Fehler ist und kein Darstellungsartefakt. Die Sensorquellen-Rückgabe kostet einen Ausfall lang nicht mehr einen Schreibvorgang pro Minute. Und zum ersten Mal existiert für alle fünf Kanäle eine Zahl.

Der Preis ist benannt: Ein Moduswechsel, der auf dem Funk verloren geht, wird im schlimmsten Fall zehn Minuten später wiederholt statt eine. Das ist derselbe Tausch wie bei `REASSERT_LIVENESS_S` in ADR-0072, in derselben Größenordnung, und er liegt weit unter jeder thermischen Zeitkonstante im Spiel.

Was dieser ADR ausdrücklich **nicht** liefert, ist eine bessere Feed-Parametrierung — obwohl die Recherche dafür fertig in §2 liegt und der Befund („wir feeden den Danfoss dreimal so oft wie der Hersteller erlaubt") unbequem genug wäre, ihn sofort zu ändern. Er wartet auf den Zensus. Das ist die Lehre aus ADR-0072, angewandt auf uns selbst.
