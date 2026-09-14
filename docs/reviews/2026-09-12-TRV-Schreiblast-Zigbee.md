# Befund: Dauerhafte Sollwert-Wiederholschreibungen auf Zigbee-TRVs

**Datum:** 2026-09-12 · **Revision:** 8 · **Status:** Ursachenanalyse abgeschlossen, **eine Entwurfsfrage offen** (§6.2) · **Anlass:** Batterielebensdauer der Aqara-TRVs · **Instanz:** Live-Installation, Poise 0.192.0, HA 2026.6.2, Zigbee2MQTT 2.9.1, `zigbee-herdsman-converters` 26.12.0 · **Betroffen:** `control/tick_resolve.py` (Schreibtor), `control/dynamics.py` (Regelperiode) · **Bezug:** ADR-0012, ADR-0015, ADR-0029, ADR-0052 §4, ADR-0059

> **Revisionsgeschichte.**
> **R1** schrieb die fehlende Schrittweiten-Deklaration dem Zigbee2MQTT-Converter zu — **falsch**, widerlegt durch ein externes Review: `zigbee-herdsman-converters` 26.12.0 definiert den SRTS-A01 mit `withSetpoint("occupied_heating_setpoint", 5, 30, 0.5)`.
> **R2** maß die Kette daraufhin an jedem Übergang, entlastete Converter und Z2M und grenzte den Bruch auf den Übergang Discovery → HA-Entität ein. Die Vermutung, dort liege ein Fehler in Home Assistant, war **ebenfalls falsch**.
> **R3** schließt die Ursache: ein `homeassistant: customize:`-Eintrag in der HA-`configuration.yaml` überschreibt `target_temp_step` auf 0,1. **Keine Komponente ist defekt.** Die Poise-Maßnahmen bleiben bestehen und gewinnen an Gewicht.
> **R4** (zweites Review) präzisiert drei Stellen: die Quantisierung wird als *beobachtet* statt als Firmware-Eigenschaft formuliert, der Konvergenz-Wächter als *bestimmungsgemäß tolerant* statt als blind, und M2 bekommt eine Frischebedingung.
> **R5** (drittes Review) korrigiert einen Denkfehler in dieser Frischebedingung: `_convergence_evidence_fresh()` ist ein **reiner Zeitvergleich** und **kein Herkunftsnachweis** — eine spätere Handbedienung ist ebenso „frisch". Die Kausalitätsprüfung bleibt bei `is_own_write()` / `setpoint_adopt_reason()`; M2 übernimmt deren Ergebnis, statt es zu ersetzen. Zusätzlich wird eine verbliebene Formulierung in §6 an die Beweislage angeglichen.
> **R6** (viertes Review) stellt das Freigabekriterium von M2 von einer negativen auf eine positive Aussage um: nicht „nicht als extern erkannt", sondern „positiv als eigenes Echo/Settle klassifiziert". `adopted_sp is None` fasst Adoptionsabschaltung, Sicherheitsunterdrückung und echtes Eigen-Echo zusammen und taugt deshalb nicht als Eigentumsnachweis.
> **R7** (fünftes und sechstes Review) trennt innerhalb der positiven Seite: `stable_offset` ist eine Stabilitätsheuristik, **kein** Herkunftsnachweis. Die Klassifikation wird nach Evidenzart aufgeschlüsselt statt auf „eigen/fremd" verkürzt, und der Bericht hält fest, dass perfekte Herkunftserkennung ohne durchgereichten HA-Context grundsätzlich nicht immer möglich ist. Ergänzt: ein eigener Context muss der des **aktuellen** Kommandos sein (`stale_own_echo` sperrt M2), und die Wertgleichheit läuft gegen `last_cmd_sp` statt gegen die rebaselinebare Echo-Baseline `last_written_sp`.
> **R8** (siebtes Review) findet einen Zirkel: Der Commit erneuert `last_sp_write_ts` bei **jedem** Write, sodass das 120-s-Echo-Fenster unter einem 60-s-Reassert nie abläuft. Die laufende Schleife klassifiziert deshalb `echo_window`, **nicht** `stable_offset` — eine Aussage, die R7 falsch hatte. M2 in der bisherigen Form löst den No-Context-Fall damit nicht; die Entwurfsfrage bleibt offen (§6.2).

---

## 1. Symptom

MQTT-Mitschnitt über fünf Minuten (2026-09-11, 23:12–23:17 Uhr):

```
23:12:49  Küche TRV/set/occupied_heating_setpoint = 15.2
23:13:49  Küche TRV/set/occupied_heating_setpoint = 15.2
23:14:49  Küche TRV/set/occupied_heating_setpoint = 15.2
23:15:49  Küche TRV/set/occupied_heating_setpoint = 15.2
23:16:49  Küche TRV/set/occupied_heating_setpoint = 15.2
23:17:49  Küche TRV/set/occupied_heating_setpoint = 15.2
```

Exakt im 60-Sekunden-Takt — ein Schreibvorgang pro Poise-Tick — mit unverändertem Wert. Hochgerechnet **1440 Sollwert-Writes pro Tag**, alle ohne Wirkung.

Die vier anderen Zonen schrieben im selben Fenster keinen Sollwert. Deren einzige TRV-Kommunikation war der externe Temperatur-Feed mit rund einem Write pro Zone alle 5–10 Minuten, also grob 150–350 Writes pro Tag und Zone. Außer Poise schrieb in beiden Messfenstern **kein** weiterer Akteur auf die TRVs.

---

## 2. Ursache

### 2.1 Die Setzung

In der HA-`configuration.yaml`:

```yaml
homeassistant:
  customize:
    climate.schlafzimmer_trv:
      target_temp_step: 0.1
    climate.wohnzimmer_trv:
      target_temp_step: 0.1
    climate.kuche_trv:
      target_temp_step: 0.1
    climate.buro_trv:
      target_temp_step: 0.1
    climate.badezimmer_trv:
      target_temp_step: 0.1
```

`customize` überschreibt das Zustandsattribut **nach** dem Anwenden der Discovery. Der Gerätehersteller, der Converter, Zigbee2MQTT und Home Assistant liefern durchgehend 0,5; die 0,1 entstehen erst in dieser Zeile.

### 2.2 Die vollständige Kette

| Stufe | Wert | Ergebnis |
|---|---|---|
| Aqara SRTS-A01 / ZCL | Setpoint technisch feiner codierbar; deklarierte Stellschrittweite 0,5 K, beobachteter interner Sollwert auf dem 0,5-K-Raster | — |
| `zigbee-herdsman-converters` 26.12.0 | `withSetpoint(…, 5, 30, 0.5)` | ✔ korrekt |
| Z2M-Discovery auf dem Broker | `temp_step: 0.5` | ✔ korrekt |
| HA wendet den Payload an | 0,5 | ✔ korrekt |
| **`homeassistant: customize:`** | **→ 0,1** | ✘ **Ursache** |
| HA-Entität `climate.kuche_trv` | `target_temp_step: 0.1` | Folge |
| Poise `spo.step` | 0,1 | ✔ liest korrekt |

### 2.3 Die Kontrollgruppe im eigenen Haus

Der Override listet fünf Entitäten. **`climate.badezimmer_sonoff_trv` steht nicht darin** — und genau diese Entität meldet den wahren Wert:

| Entität | im Override | `target_temp_step` |
|---|---|---|
| `climate.schlafzimmer_trv` | ja | 0,1 |
| `climate.wohnzimmer_trv` | ja | 0,1 |
| `climate.kuche_trv` | ja | 0,1 |
| `climate.buro_trv` | ja | 0,1 |
| `climate.badezimmer_trv` (offline) | ja | 0,1 |
| **`climate.badezimmer_sonoff_trv`** | **nein** | **0,5** |

Der Badezimmer-Aktor, den Poise tatsächlich fährt, ist damit die natürliche Kontrolle. Zum Messzeitpunkt: Poise-Ziel **22,3**, `snap_to_step(22.3, 0.5) = 22.5`, Gerät meldet **22,5**, Abstand null — **kein Write**, obwohl die Endziffer „,3" im Override-Fall eine Dauerschleife ausgelöst hätte. Das Snapping funktioniert genau wie entworfen, sobald es die richtige Zahl bekommt.

### 2.4 Wie daraus die Schleife wird

`control/tick_resolve.py::should_write` vergleicht den Zielwert gegen den **vom Aktor gemeldeten** Sollwert:

```python
return round(abs(target - actual), 3) >= deadband
```

mit `WRITE_DEADBAND_C = 0.2`. Mit `step = 0,1` bleibt 15,2 beim Snapping unverändert; der wirksame Sollwert landet bei 15,0; |15,2 − 15,0| = 0,2, und `0.2 >= 0.2` ist wahr. Poise schreibt, das Gerät meldet weiter 15,0, im nächsten Tick dieselbe Lage. **Eine stabile Schleife ohne Abbruchbedingung.** Die Testsuite fixiert dieses Verhalten ausdrücklich (`21.0 → 21.2` muss schreiben).

Der Vergleich gegen den Gerätewert statt gegen das eigene letzte Kommando ist Absicht (ADR-0012): nur so wird eine Handbedienung am Rad erkannt. Die Entscheidung ist richtig — sie verträgt sich nur nicht mit einer zu fein angegebenen Schrittweite.

### 2.5 Warum nichts Alarm geschlagen hat

`sp_diverged_writes` stand während der gesamten Messung auf **0**. `safety/write_convergence.py`:

```python
CONV_MIN_TOLERANCE_C: float = 0.5

def convergence_tolerance(step: float) -> float:
    return max(CONV_MIN_TOLERANCE_C, step)
```

Kommentar im Quelltext: *„never judge convergence sharper than half a Kelvin — the step read falls back to 0.1 when the device does not announce one."*

Präzise: **Der Wächter erkennt einen Clamp nur außerhalb seiner Konvergenztoleranz; Requantisierungen bis einschließlich 0,5 K gelten absichtlich als konvergiert.** Er misstraut der gemeldeten Schrittweite also bereits — das Schreibtor tut es nicht.

**Der Kern in einem Satz:** Zwei Stellen im Code beantworten dieselbe Frage — *steht das Gerät dort, wo wir es hinhaben wollten?* — mit unterschiedlichen Toleranzen. Die Lücke zwischen 0,2 und 0,5 ist genau der Bereich, in dem geschrieben, aber nichts gemeldet wird.

---

## 3. Wie oft die Schleife auftritt

Solange Poise mit 0,1 K rechnet und der wirksame Sollwert auf das nächstgelegene 0,5-K-Raster fällt, entscheidet allein der Zielwert:

| Nachkommastelle des Ziels | Abstand zum Raster | Folge |
|---|---|---|
| ,0 · ,5 | 0 | ruhig |
| ,1 · ,4 · ,6 · ,9 | 0,1 | ruhig (unter Totband) |
| **,2 · ,3 · ,7 · ,8** | **0,2** | **Dauerschleife** |

Vier von zehn Endziffern lösen sie aus. Das Büro hatte mit 20,6 Glück, die Küche mit 15,2 nicht — und die Küche fiel von selbst wieder heraus, als ihr Sollwert später auf 19,0 wanderte. Der Sollwert bewegt sich mit Zeitplan, Absenkung, Komfortband und Override ständig; jede der fünf Zonen durchläuft die betroffenen Endziffern regelmäßig.

**Ohne den Override entfällt diese Tabelle vollständig.**

**Belege für das Quantisierungsverhalten** (gerätegemeldete Werte, Messzeitpunkt 23:2x):

| Zone | Poise `heat_sp` | `occupied_heating_setpoint` | `internal_heating_setpoint` |
|---|---|---|---|
| Wohnzimmer | 18,3 | 18,3 | **18,5** |
| Büro | 20,6 | 20,5 | 20,5 |
| Küche | 15,2 | 15,0 | 15,0 |
| Schlafzimmer | 19,0 | 19,0 | 19,0 |

Alle Abweichungen sind sauberes Runden auf das nächste 0,5-Raster.

**Hypothese Wohnzimmer (nicht bewiesen):** Der `occupied`-Wert 18,3 ist vermutlich das Echo unseres eigenen Kommandos, das Z2M hält, bis das Gerät das Attribut selbst meldet; der `internal`-Wert steht bereits auf 18,5. Träfe das zu, startete die Schleife dort, sobald das Gerät meldet.

---

## 4. Zweiter, unabhängiger Befund: das Drosselkriterium

ADR-0052 §4 hat VTherms „Minimum Regulation Period" übernommen (`control/dynamics.py::regulation_throttled`, live seit v0.110.0):

| Profil | `regulation_period_s` | `self_regulating` |
|---|---|---|
| `fast_air` (AC, Luft-Luft-WP) | **300** | true |
| `slow_hydronic` (Heizkörper, **TRV**) | **0** | false |
| `very_slow` (Fußboden) | **0** | false |

Im ADR wörtlich: *„Dumme Setpoint-Aktoren (`regulation_period_s=0`, TRVs) werden nie gedrosselt."*

Die Begründung war stimmig — die Drossel schützt **thermische und kompressorseitige** Dynamik vor Kurztakten. TRVs haben keinen Verdichter, also brauchten sie sie nicht.

Sie schützt aber nichts vor den **Kosten einer Funkübertragung**. Aus dieser Richtung ist die Drossel dort aktiv, wo das Gerät am Netz hängt, und aus, wo es von zwei Zellen lebt. Das ist keine Fehlimplementierung, sondern ein Kriterium, das seinen eigenen Zweck erfüllt und einen zweiten nicht abdeckt.

---

## 5. Einordnung gegenüber dem Wettbewerb

**Versatile Thermostat** hat dieselben zwei Mechanismen und begründet sie ausdrücklich mit Batterie — die Schwellen existieren, „um das darunterliegende Gerät nicht zu überlasten: manche piepsen unangenehm, andere laufen auf Batterie":

- *Regulation threshold* (dtemp) — funktional `WRITE_DEADBAND_C`
- *Minimum regulation period* — funktional `regulation_period_s`

Beides benutzereinstellbar und für **alle** Gerätetypen wirksam, TRVs eingeschlossen.

**Better Thermostat**, der auf Zigbee-TRVs spezialisierte Mitbewerber, entscheidet strenger:

```python
if _temperature != _current_set_temperature:
```

Strikte Ungleichheit gegen den gemeldeten Gerätewert, ohne Toleranz und ohne Zeitschranke; vorher wird mit `round_by_step(value, step, f_rounding)` gerastert — dieselbe Idee wie `snap_to_step`, mit derselben Abhängigkeit von einer korrekten `step`-Angabe. Mit diesem Override hätte BT dasselbe Problem in schärferer Form: es würde auch im Büro-Fall (20,6 gegen 20,5) dauerhaft schreiben, wo Poises Totband noch greift.

HASmartThermostat und dual_smart sind PWM-/Relais-basiert; ihr Gegenstück ist `min_cycle_duration`.

**Keines der Projekte ist gegen eine zu fein angegebene Schrittweite abgesichert.** VTherm verlagert es auf den Nutzer, BT vertraut der Angabe.

---

## 6. Maßnahmen

### P0 — Override entfernen (Installation, sofort)

Die fünf `target_temp_step: 0.1`-Einträge aus dem `customize`-Block streichen und Home Assistant neu starten. Danach melden die Entitäten 0,5, Poise rastert vor dem Vergleich, und die Schleife entfällt — nachgewiesen am Badezimmer-Sonoff-TRV, das nie überschrieben wurde und sich exakt so verhält (Abschnitt 2.3).

**Vorher klären, warum der Override gesetzt wurde.** Die naheliegende Absicht ist eine feinere Schrittweite im Bedien-Stepper der Oberfläche. Dafür ist `target_temp_step` das falsche Mittel: Das Attribut beschreibt, was das **Gerät** annehmen kann, und wird von jedem Verbraucher so gelesen — von Poise, vom Konvergenz-Wächter, von Karten und von fremden Automationen. Der Stepper wird feiner, und alle anderen bekommen eine unwahre Angabe.

Für den SRTS-A01 ist eine Stellschrittweite von 0,5 K deklariert, und die Messungen zeigen den wirksamen internen Sollwert auf genau diesem Raster. Ein Stepper in 0,1er-Schritten verspricht damit eine Genauigkeit, die auf dem Weg zum Ventil ohnehin verlorengeht. Falls eine feinere **Anzeige** gewünscht ist, ist das eine getrennte Frage — HA trennt Darstellung (`precision`) von Stellschrittweite (`temp_step`); ob sich `precision` bei Climate-Entitäten über `customize` setzen lässt, müsste vorher geprüft werden.

> Der in R1 vorgeschlagene Z2M-Override und der Upstream-Beitrag `withValueStep(0.5)` **entfallen** — der Converter ist korrekt. Die in R2 aufgestellte Vermutung eines HA-Fehlers ist **widerlegt**; ein Issue gegen Home Assistant ist gegenstandslos.

### M2 — Idempotenz wiederholter eigener Kommandos (Poise, primär)

**Nicht** `convergence_tolerance(step)` pauschal zum neuen Totband von `should_write` machen: Auf einem ehrlichen 0,1-K-Gerät würde eine fremde Handverstellung von 0,3 oder 0,4 K dann als „nah genug am eigenen Kommando" gelten und verschluckt.

Stattdessen eine enge Regel für **denselben** Sollwert:

- gewünschter Sollwert identisch zum letzten eigenen Kommando, **und**
- es liegt ein **frischer** Gerätezustand nach diesem Kommando vor, **und**
- dessen Abweichung liegt innerhalb der zugelassenen Settle-/Requantisierungstoleranz, **und**
- die vorgelagerte Beobachtungslogik hat den Zustand **positiv** klassifiziert — als eigenes Kommandoecho **des aktuellen** Kommandos, als Wertgleichheit mit dem **aktuellen** Kommando (`last_cmd_sp`, nicht der rebaselinebaren Echo-Baseline), oder als **akzeptierten stabilen Settle/Clamp**; bloßes Ausbleiben einer Adoption genügt **nicht**, ein akzeptierter Settle ist **kein kausal bewiesenes Eigen-Echo**, und ein als `stale_own_echo` markiertes Echo gibt **nicht** frei, **und**
- kein Moduswechsel und kein anderer zwingender Schreibgrund liegt vor

→ **denselben Sollwert nicht erneut senden.** Ändert sich das Ziel hinreichend, wird normal geschrieben. Die External-Override-Erkennung (ADR-0059) bleibt unverändert **vor** diesem Gate.

**Die Frische-Bedingung ist notwendig, beweist aber allein keine Herkunft.** `_convergence_evidence_fresh()` ist ein reiner Zeitvergleich — `age_s <= (now_mono - last_cmd_mono)`, also „hat sich der Aktorzustand nach unserem letzten Kommando aktualisiert". Der Kontext bzw. Verursacher der Zustandsänderung geht dort nicht ein. Eine spätere Handbedienung am Rad wäre damit ebenfalls „frisch".

Deshalb genügt „Ziel = letztes Kommando ∧ Istwert innerhalb einer Toleranz ∧ frisch" nicht. Sonst entstünde folgender Fall: Poise befiehlt 20,0; jemand verstellt das Gerät auf 20,4; HA meldet einen neuen, frischen Zustand; greift die External-Erkennung aus irgendeinem Grund nicht, läse die Idempotenzregel 20,4 als „akzeptiertes Settle" und stellte das Schreiben dauerhaft ein.

**Die Kausalitätsfrage gehört deshalb dorthin, wo Poise sie bereits beantwortet.** Die Zuständigkeiten trennen sauber:

| Frage | Zuständig |
|---|---|
| Ist die Beobachtung neu genug, um überhaupt Aussagekraft zu haben? | `_convergence_evidence_fresh()` |
| Ist sie unser Echo/Settle oder ein fremder Eingriff? | `ExternalOverrideTracker.is_own_write()` (HA-Context gegen `own_write_ctx_ids`) und `setpoint_adopt_reason()` (`command_echo` · `echo_window` · `stable_offset` · `adopt` · …) |
| Müssen wir denselben, bereits akzeptierten Befehl erneut senden? | **M2** |

M2 sollte die vorhandene `evidence_fresh`-Definition für die **zeitliche** Gültigkeit wiederverwenden und zusätzlich das Ergebnis der bestehenden External-Override-/Echo-Klassifikation übernehmen. Eine eigene zweite Frische- oder Fremdänderungslogik darf M2 **nicht** einführen — das wäre derselbe Fehler wie die heutige Doppeltoleranz, nur eine Ebene höher.

#### „Nicht adoptiert" ist kein Eigentumsnachweis

Das Freigabekriterium muss **positiv** formuliert sein. `ExternalOverrideTracker.observe_setpoint()` entscheidet in einer Kette, und `adopt_setpoint` ist nur bei `reason == "adopt"` gesetzt:

```
opt_out → schedule_active → own_echo → safety_window → safety_frozen
        → setpoint_adopt_reason_fn(…)   # no_baseline · command_echo ·
                                        # implausible_frost · echo_window ·
                                        # stable_offset · adopt
```

`adopted_sp is None` — worauf `plan_setpoint_write()` heute allein schaut — fasst damit Sachverhalte zusammen, die über die Herkunft **Unterschiedliches** aussagen:

| Grund | Test im Code | Klassifikation | Herkunft | M2 |
|---|---|---|---|---|
| `own_echo`, **nicht** stale | Context in `own_write_ctx_ids` **und** `== last_sp_ctx_id` | `PROVEN_OWN_ECHO` | **kausal nachgewiesen** | frei |
| Treffer auf das **aktuelle** Kommando | `\|device_sp − last_cmd_sp\| < Match-Toleranz` | `CURRENT_COMMAND_MATCH` | starke Evidenz, aber **wertbasiert** | frei |
| `stable_offset` | `\|device_sp − prev_device_sp\| < deadband` | `ACCEPTED_SETTLE` | **kein Nachweis** — nur „bewegt sich nicht mehr" | frei |
| `own_echo`, **stale** | eigener Context, aber `!= last_sp_ctx_id` | `STALE_OWN_ECHO` | Echo eines **überholten** Kommandos | **gesperrt** |
| `adopt` | — | `FOREIGN` | externe Änderung erkannt | gesperrt |
| `opt_out`, `schedule_active` | Adoption abgeschaltet | `UNKNOWN` | keine Aussage | gesperrt |
| `safety_window`, `safety_frozen`, `implausible_frost` | Sicherheitsunterdrückung | `UNKNOWN` | keine Aussage | gesperrt |
| `no_baseline`, `echo_window` | kein Bezug / mehrdeutig | `UNKNOWN` | keine Aussage | gesperrt |

Würde M2 auf „nicht adoptiert" aufsetzen, unterdrückte es das Schreiben auch dann, wenn die Adoption nur gerade abgeschaltet oder sicherheitsbedingt ausgesetzt ist — also genau in den Fällen, in denen über die Herkunft **nichts** ausgesagt wurde. Das wäre eine stillschweigende Umdeutung von „nicht adoptiert" in „gehört uns".

**Ebenso wenig trägt die Gegenrichtung.** `stable_offset` ist keine schwächere Form von Eigentum, sondern eine bewusste konservative Heuristik: Der Quelltext behandelt einen unveränderten Wert deshalb nicht als Nutzeränderung, weil *„a stable settle/clamp of our own write is not [a user change]"*. Wer ihn zum Eigentumsnachweis erhebt, behauptet mehr, als der Test hergibt.

**Die Wertgleichheit muss gegen die richtige Baseline laufen.** Poise führt zwei, und sie driften absichtlich auseinander:

- `last_written_sp` ist die **Echo-/Adoptionsbaseline**. `rebaseline_own_echo(actual_sp)` setzt sie auf den tatsächlich zurückgemeldeten Gerätewert — also auch auf einen Clamp oder eine Requantisierung, *„so future reports of it are recognised as echoes"*. Sie folgt dem Settle.
- `last_cmd_sp` ist die **Kommando-Wahrheit**: vom Commit gestempelt, *„never [rebaselined]"*, und genau deshalb das, wogegen der Konvergenz-Wächter urteilt.

Das bestehende `command_echo` prüft gegen `last_written_sp` und ist für die **Adoption** genau richtig. Für M2 ist es das nicht, und zwar in Kombination mit dem eben behandelten Fall: Ein verspätetes Echo eines überholten Kommandos wird zwar als `stale_own_echo` gesperrt — es rebaselined `last_written_sp` aber trotzdem auf den alten Wert. Meldet die Integration denselben alten Wert danach unter neuem oder fremdem Context, liefert `command_echo` einen Treffer gegen die **verschobene** Baseline, obwohl er nicht dem aktuellen Kommando entspricht:

> Poise hat 15,0 geschrieben → neues Ziel und Kommando 15,4 → verspätetes Own-Echo von 15,0 (`stale_own_echo`, M2 gesperrt, aber `last_written_sp` → 15,0) → nächster Tick meldet 15,0 unter neuem Context → `command_echo` trifft, obwohl 15,4 gilt.

**Deshalb leitet M2 `CURRENT_COMMAND_MATCH` nicht aus `sp_adopt_reason == "command_echo"` ab, sondern prüft gegen `last_cmd_sp`.** Das ist keine zweite Fremdänderungslogik — `last_cmd_sp` existiert bereits genau als nicht rebaselinete Kommando-Wahrheit, M2 benutzt dieselbe Größe wie der Konvergenz-Wächter. Das bestehende `command_echo` behält seine heutige Bedeutung im Override-Layer unverändert.

**Ein eigener Context genügt ebenfalls nicht — er muss der des AKTUELLEN Kommandos sein.** `is_own_write()` prüft nur die Mitgliedschaft im Ring `own_write_ctx_ids`; damit kann auch das verspätete Echo eines längst überholten Poise-Kommandos zunächst als `own_echo` erscheinen. Poise kennt den Fall und rechnet ihn separat aus:

```python
stale_own_echo = _own_change and _settle_ctx != rt.external.last_sp_ctx_id
```

Der Konvergenz-Wächter behandelt ihn bereits konsequent — ein so markiertes Echo *„carries no evidence"*. **M2 muss dieselbe Sperre übernehmen:** `PROVEN_OWN_ECHO` darf nur vergeben werden, wenn `stale_own_echo` falsch ist; andernfalls `STALE_OWN_ECHO`, und das Gate bleibt zu. Sonst würde ein Reassert ausgerechnet dann unterdrückt, wenn Poise sein Ziel gerade geändert hat und das Gerät noch auf dem alten Wert steht.

**Und genau darauf kommt es für diesen Fehlerfall an.** Im gemessenen Fall greift `command_echo` nicht: |15,0 − 15,2| = 0,2 ist nicht *kleiner* als das Totband 0,2. Danach entscheidet das Echo-Fenster — und dort bleibt die laufende Schleife hängen, siehe §6.2. Die Klassifikation lautet **`echo_window`**, nicht `stable_offset`. Ein M2, das nur kausal bewiesene Herkunft akzeptierte, hätte die hier untersuchte Schleife also **gar nicht aufgelöst** — und mit der reinen Settle-Freigabe allein wird sie es ebenfalls nicht.

**Die epistemische Grenze gehört dazu:** Ohne durchgereichten HA-Context ist perfekte Herkunftserkennung grundsätzlich nicht immer möglich. Liefert ein Adapter den späteren Geräte-Report unter fremdem oder neuem Context, bleibt nur die wertbasierte Beurteilung. Poise trifft an dieser Stelle bereits eine bewusste Entscheidung; M2 verwendet sie **wieder**, statt eine zweite Heuristik daneben zu stellen.

**Empfehlung für die Umsetzung:** Das Write-Gate soll keine `sp_adopt_reason`-Strings auswerten müssen. Sauberer ist eine explizite Klassifikation aus der Beobachtung heraus:

```
PROVEN_OWN_ECHO · CURRENT_COMMAND_MATCH · ACCEPTED_SETTLE   # M2 frei
STALE_OWN_ECHO  · FOREIGN               · UNKNOWN           # M2 gesperrt
```

Die drei freigebenden Klassen sind absichtlich **getrennt**, obwohl sie für M2 dieselbe Entscheidung ergeben: Sie unterscheiden sich in der Evidenzstärke, und die Diagnose soll das zeigen können, ohne dass jemand später aus einer schwachen eine starke Aussage macht. `ACCEPTED_SETTLE` heißt deshalb nicht `OWN_SETTLE` — „mit unserem Kommando vereinbar und akzeptiert", nicht „nachweislich von uns verursacht". **M2 darf nur bei den drei Klassen der oberen Zeile unterdrücken.** Damit bleibt die Herkunftsentscheidung im Observation-/Override-Layer, wo sie hingehört, und das Write-Gate muss dessen interne Gründeliste nicht kennen — dieselbe Zuständigkeitstrennung, deren Verletzung diesen ganzen Bericht ausgelöst hat.

Damit behandelt M2 die ganze Fehlerklasse: *Gerät akzeptiert den Befehl und meldet anschließend einen geringfügig anderen, stabilen Wert zurück* — unabhängig davon, ob die falsche Schrittweite aus einem Gerät, einem Converter oder der eigenen Konfiguration stammt.

#### Der 60/120-Zirkel — warum M2 einen eigenen Episodenanker braucht

`SETPOINT_ADOPT_ECHO_WINDOW_S = 120.0`, und der Commit stempelt bei **jedem** erfolgreichen Setpoint-Write neu:

```python
if execution.success:
    …
    self.external.last_sp_write_ts = now       # ohne Vergleich mit dem vorigen Kommando
```

Bei einem Tick von 60 s heißt das: Der Reassert erneuert das 120-s-Fenster, bevor es ablaufen kann.

```
t=0    15,2 schreiben  → last_sp_write_ts = 0
t=60   15,2 schreiben  → last_sp_write_ts = 60     ← Fenster neu gestartet
t=120  15,2 schreiben  → last_sp_write_ts = 120    ← und wieder
```

`setpoint_adopt_reason()` prüft `stable_offset` **erst nach** `(now - last_write_ts) < echo_window_s`. Solange die Schleife läuft, ist dieser Zweig **unerreichbar**; die Beobachtung bleibt bei `echo_window`, das R7 als `UNKNOWN` einstuft und damit M2 sperrt. Das ergibt einen Zirkel:

> M2 wartet auf `ACCEPTED_SETTLE` → `ACCEPTED_SETTLE` setzt das Ende des Echo-Fensters voraus → jeder noch nicht unterdrückte Reassert startet das Fenster neu.

`CURRENT_COMMAND_MATCH` bricht ihn nicht auf: Bei einer Match-Toleranz in Höhe des heutigen Totbands ist |15,0 − 15,2| = 0,2 gerade **kein** Treffer. Und sie auf die 0,5-K-Konvergenztoleranz zu verbreitern, holte genau die Gefahr zurück, die R6/R7 ausgeräumt haben — Werte gälten als „nah genug am aktuellen Kommando", ohne dass die Herkunft geklärt wäre. **Die Match-Toleranz in der Tabelle oben ist deshalb kein Implementierungsdetail, sondern eine offene Entwurfsentscheidung.**

**Was M2 braucht:** eine vom physischen Reassert unabhängige Vorstellung einer **logischen Kommando-Episode**. Sie beginnt, wenn sich `last_cmd_sp` tatsächlich ändert, und wird durch identische Wiederholungen desselben Sollwerts **nicht** neu gestartet. Über mehrere frische Beobachtungen innerhalb derselben Episode kann Poise dann feststellen, dass sich das Gerät stabil bei 15,0 festsetzt — auch wenn zwischendurch identische Reasserts hinausgingen.

`last_sp_write_ts` selbst umzudefinieren ist **keine** Option: Der Stempel trägt bereits das Echo-Fenster des Override-Layers und die ADR-0052-§4-Drossel und meint dort zu Recht den realen letzten *Write*.

**Alternative, und zugleich eine Einschränkung der Maßnahmenreihenfolge:** M4 kann den Zirkel von außen aufbrechen. Sperrt eine Wiederholsperre identische Reasserts länger als 120 s, läuft das Echo-Fenster aus und `stable_offset` wird sichtbar. Das ist elegant, hat aber eine architektonische Folge: **Im No-Context-Fall wäre M2 dann nicht mehr unabhängig von M4**, und die Einordnung „M2 primär, M4 ergänzend" träfe so nicht mehr zu. Welcher der beiden Wege gilt — eigener Episodenanker in M2 oder bewusste Kopplung an M4 —, ist die **verbleibende offene Entwurfsfrage** und gehört in den ADR, nicht in diesen Bericht.

**Regressionstests mindestens für:** `15.2 → Gerät 15.0 → kein zweiter Write` · `15.2 → neues Ziel 15.4 → Write` · ehrliches 0,1-K-Gerät · fremde Handverstellung · Moduswechsel · verspätetes Echo eines älteren Kommandos.

**Zwingend** ist dazu der Test, der den 60/120-Zirkel abdeckt:

> `echo_window = 120 s`, Tick und Reassert 60 s, **kein** durchgereichter Own-Context, Kommando 15,2, Gerät meldet dauerhaft 15,0 → der Mechanismus muss die Wiederholschleife **terminieren**. Identische Reasserts dürfen die notwendige Settle-Evidenz nicht dauerhaft verhindern.

Dazu ein Test, der die **Mehrdeutigkeit selbst festhält**, damit die Architekturentscheidung später nicht versehentlich verschärft wird:

> Poise schreibt 15,2 → die Integration meldet später unter fremdem oder neuem Context stabil 15,0 → nach Ablauf des Echo-Fensters klassifiziert die Beobachtung `stable_offset` → **M2 darf den Reassert unterdrücken**, die Diagnose darf diesen Zustand aber **nicht** als bewiesenes Eigen-Echo ausweisen.

Und einen, der die verschobene Baseline abfängt — er prüft ausdrücklich den **Folge-Tick**:

> Poise hat 15,0 geschrieben, aktuelles Kommando ist 15,4 → verspätetes Own-Echo von 15,0 → M2 gesperrt (`stale_own_echo`) → **nächster Tick**, 15,0 unter neuem Context: M2 darf **auch jetzt nicht** freigeben, weder direkt noch über die inzwischen auf 15,0 verschobene `last_written_sp`-Baseline.

### M4 — Wiederholsperre als zweite Schicht (Poise, ergänzend)

`regulation_period_s` **nicht** umdefinieren — der Parameter hat eine klar dokumentierte thermodynamische Bedeutung.

Stattdessen ein orthogonaler Mechanismus, etwa `min_setpoint_reassert_interval_s` oder eine allgemeine `WritePolicy`, der ausschließlich **Wiederholungen desselben Kommandos** begrenzt. Neue Sollwerte aus Zeitplan, Override, Fensterereignis oder Sicherheitspfad gehen weiterhin sofort raus; ein nicht konvergierendes identisches Kommando geht nicht mehr jede Minute über Zigbee. Defense in Depth, unabhängig von M2.

### M3 — Rastererkennung, zunächst nur als Diagnose (zurückgestellt)

Automatisches Rasterlernen ist für diesen Fall unnötig — der richtige Wert ist bekannt und wird korrekt geliefert. Ein einzelnes Paar `15.2 → 15.0` kann außerdem von einem Clamp, einer Min-/Max-Grenze, einem Betriebsmodus oder einem transienten Zustand stammen. Belastbares Lernen bräuchte mehrere eigene Kommandos an verschiedenen Rasterpositionen, Herkunftsprüfung, Konfidenz, Ausschluss der Grenzwerte sowie Persistenz und Invalidierung.

Zunächst genügt eine Diagnoseausgabe:

```
declared_step=0.1, repeated_settle_delta=0.2, possible_quantization_mismatch=true
```

Das hätte diesen Fall am ersten Tag sichtbar gemacht. Erst wenn solche Fälle bei mehreren Geräten auftreten, lohnt ein ADR-0029-Vorgang für echtes Rasterlernen.

### Nebenmaßnahmen

- **Feed-Totband 0,1 → 0,2 K:** unabhängig vom Hauptbefund, halbiert grob die wertgetriebenen Writes des externen Temperatur-Feeds. Vorher separat messen.
- **Keep-alive 600 → 1800 s:** zurückgestellt. Ein Timeout des externen Eingangs ist nirgends dokumentiert; die Community berichtet einen Rückfall auf „internal" in der Größenordnung von Tagen. Ohne eigene Messung nicht ändern.

### Reihenfolge

**P0** (Override entfernen) → **M2** (genereller Poise-Robustheitsfix) → **M4** (Wiederholsperre) → **M3** (erst nach weiteren realen Fällen).

**Mit einem Vorbehalt:** Ob M4 wirklich nur ergänzend ist, hängt an der offenen Entwurfsfrage aus §6.2. Bekommt M2 einen eigenen Kommando-Episodenanker, bleibt die Reihenfolge wie oben. Wird stattdessen die Kopplung gewählt, ist M4 im No-Context-Fall **Voraussetzung** für M2 und muss zusammen mit ihm ausgeliefert werden.

---

## 7. Was dieser Fall über Poise zeigt

Die Ursache liegt in der Installation, nicht im Code. Der Poise-Befund verliert dadurch nicht an Gewicht, sondern gewinnt:

**Eine einzelne, plausibel aussehende Konfigurationszeile hat auf einem Batteriegerät eine Dauerschreibschleife mit 1440 Schreibvorgängen pro Tag ausgelöst — und keine einzige Diagnose hat angeschlagen.** Der Konvergenz-Wächter wertete die 0,2-K-Abweichung **bestimmungsgemäß als konvergiert**; eine Schreibraten-Grenze ist für TRVs bewusst abgeschaltet; eine Plausibilitätsprüfung der gemeldeten Metadaten gibt es nicht.

Das ist der eigentliche Punkt: **Die Schleife entsteht aus zwei lokal richtigen Entscheidungen.** Das Schreibtor vergleicht gegen den Gerätewert, um Handbedienung zu erkennen — richtig. Der Wächter toleriert eine Quantisierungsstufe, um Re-Quantisierung nicht als Fehler zu melden — ebenfalls richtig. Erst ihr Zusammenspiel lässt einen Bereich offen, in dem geschrieben, aber nichts gemeldet wird.

Poise war an dieser Stelle robuster als Better Thermostat und hat trotzdem nicht gereicht. Genau deshalb sind M2 und M4 unabhängig von P0 umzusetzen: Die Quelle einer falschen Schrittweite ist austauschbar — ein Gerät, ein Converter, eine `customize`-Zeile. Die Verteidigung darf es nicht sein.

---

## 8. Was nicht bewiesen ist

- Die Echo-Deutung des Wohnzimmer-Wertepaares (18,3 gegen 18,5) ist eine Hypothese.
- Das Quantisierungsverhalten der E1 stützt sich auf drei Messpunkte plus die Kontrollmessung am Sonoff-TRV; sie sind konsistent, decken aber nicht den ganzen Wertebereich ab. **Welche Schicht quantisiert, ist nicht nachgewiesen** — beobachtet ist, dass der gemeldete interne Sollwert auf dem 0,5-K-Raster landet; ob das die Gerätefirmware, der Converter oder der Schreibpfad tut, wurde nicht getrennt.
- Die Hochrechnung auf 1440 Writes pro Tag unterstellt einen dauerhaft auf einer betroffenen Endziffer stehenden Zielwert. Die Küche ist später von selbst herausgefallen (Sollwert 19,0) — die Fehlerklasse bleibt, die Tagesmenge schwankt.
- Die Messfenster umfassen fünf bzw. sieben Minuten in der Nacht. Andere Schreiber (die noch aktive Ventilkalibrierung) können darin schlicht nicht gefeuert haben.
- Die Absicht hinter dem `customize`-Eintrag ist nicht dokumentiert; die Vermutung „feinerer Bedien-Stepper" ist eine Annahme.

---

## 9. Quellen

- Zigbee2MQTT — [Aqara SRTS-A01](https://www.zigbee2mqtt.io/devices/SRTS-A01.html), [Home-Assistant-Integration](https://www.zigbee2mqtt.io/guide/usage/integrations/home_assistant.html), [Logging](https://www.zigbee2mqtt.io/guide/configuration/logging.html)
- Home Assistant — [MQTT Climate](https://www.home-assistant.io/integrations/climate.mqtt/), [Customizing entities](https://www.home-assistant.io/docs/configuration/customizing-devices/)
- Versatile Thermostat — [over_climate](https://www.versatile-thermostat.org/en/docs/over-climate/)
- Better Thermostat — [`utils/controlling.py`](https://github.com/KartoffelToby/better_thermostat/blob/master/custom_components/better_thermostat/utils/controlling.py), [`utils/helpers.py`](https://github.com/KartoffelToby/better_thermostat/blob/master/custom_components/better_thermostat/utils/helpers.py)
- Intern: ADR-0012, ADR-0015, ADR-0029, ADR-0052 §4, ADR-0059 · `control/tick_resolve.py`, `control/dynamics.py`, `safety/write_convergence.py`, `const.py`
- Messungen: MQTT-Mitschnitte `zigbee2mqtt/#` (2026-09-11, 23:12–23:17 und 23:27–23:35), Discovery `homeassistant/climate/#` und `homeassistant/device/#`, HA-Entity-Registry und REST-State, Kontrollmessung `climate.badezimmer_sonoff_trv` (2026-09-12), HA-`configuration.yaml`
