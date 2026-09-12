# ADR-0072: Schreibökonomie am Aktor — Kommando-Episode, Idempotenz-Veto, Ratenlimit, Raster-Hinweis

**Status:** Implementiert (v0.193.0) · **Wirkung:** Live-A · **Datum:** 2026-09-12 · **Bezug:** [Befund 2026-09-12 TRV-Schreiblast](../reviews/2026-09-12-TRV-Schreiblast-Zigbee.md) (R8, eingefroren), [Plan 2026-09-12 M2–M4](../Konzepte/2026-09-12_Plan_Schreiblast-M2-M4.md), ADR-0012 (Write-Totband, Repair-Issues), ADR-0015 (Aktorpfad), ADR-0029 (Geräte-Quirks), ADR-0052 §4 (Regelperiode — **nicht** angefasst), ADR-0055 (Regelgüte — geprüft, unverändert), ADR-0059 (Sollwert-Adoption)

> **Warum ein eigener ADR:** Der Befund brauchte acht Revisionen, weil eine Frage darin immer wieder falsch beantwortet wurde — *woher weiß Poise, dass ein Schreibvorgang nichts bewirken kann?* Die Antwort ist ein fehlendes Primitiv, nicht ein Parameter. Dieser ADR hält es fest, samt der beiden Prämissen-Löcher, die erst beim Implementieren aufgefallen sind.

## Kontext

Ein Aqara SRTS-A01 erhielt 1440 Sollwert-Schreibvorgänge pro Tag — einen pro Tick, dauerhaft, auf einem batteriebetriebenen Zigbee-Endgerät.

Die Kette: Ein `homeassistant:`-`customize:`-Block in der HA-Konfiguration erzwang `target_temp_step: 0.1` für fünf TRVs, deren wirksames Raster 0,5 K ist. Poise snappte damit auf 0,1, das Gerät legte sich 0,2 K daneben, und das Write-Totband aus ADR-0012 (`WRITE_DEADBAND_C = 0.2`, verglichen gegen den **gemeldeten** Gerätesollwert) war damit für immer erfüllt. `climate.badezimmer_sonoff_trv` stand nicht in dem Block, meldete ehrlich 0,5 — und schrieb null Mal. Das war die Kontrollgruppe, die den Befund trug.

Das Bestehende konnte das nicht sehen:

- **ADR-0012** vergleicht gegen den Gerätesollwert. Richtig, und genau deshalb blind gegen ein Gerät, das unseren Befehl nie erreicht.
- **ADR-0052 §4** drosselt mit `regulation_period_s`; für `slow_hydronic` (TRV) ist der Wert 0. Das ist eine thermodynamische Aussage, kein Schreibbudget.
- **ADR-0059** klassifiziert Sollwert-Herkunft über ein 120-s-Echo-Fenster. Bei 60 s Reassert-Takt wird dieses Fenster von jedem eigenen Schreibvorgang neu scharfgestellt — die Klassifikation kam nie aus `echo_window` heraus. **Die Terminierung durfte deshalb nicht von ihr abhängen.**

## 1. Vorentscheidungen

Drei Festlegungen, die der Befund offengelassen hat. Sie sind der Inhalt dieses ADR, nicht sein Ergebnis.

**V1 — Die Kommando-Episode ist das fehlende Primitiv, nicht eine von zwei Optionen.**
Die Terminierung einer Wiederholschleife ist ein **Fixpunkt-Argument**: Ein identisches Kommando, das den Aktorzustand zuletzt nicht verändert hat, verändert ihn auch beim nächsten Mal nicht. Dafür braucht es keinen HA-`Context`. Es braucht zwei Dinge: *welches Kommando gilt* (`last_cmd_sp`, vom Commit gestempelt und nie re-baselined) und *was sich seit dessen Entstehen bewegt hat*. `last_sp_write_ts` taugt für Zweiteres nicht — es markiert den letzten **physischen** Schreibvorgang und wird von jedem Reassert neu gesetzt. `cmd_episode_ts` markiert etwas anderes: den Moment, in dem `last_cmd_sp` tatsächlich **gewechselt** hat. Identische Reasserts fassen es nicht an. Damit entfällt die offene Frage „M2 primär oder an M4 gekoppelt" — beide sind Konsumenten desselben Ankers.

**V2 — Die Herkunftsklassifikation bleibt trotzdem.**
Der Fixpunkt entscheidet, ob ein Schreibvorgang *etwas bewirken kann*. Er entscheidet **nicht**, ob Poise die Regelhoheit abgeben darf. Gegenbeispiel: `last_cmd_sp` = 20,0, das Gerät steht stabil auf 20,4 nach einer unbemerkten Handbedienung. Der Fixpunkt allein sagt „nicht senden", und die Zone ist still verloren; über eine Toleranz ist das nicht heilbar, weil 0,4 unter der 0,5-Requantisierungstoleranz liegt. **Anker und Herkunft sind orthogonal:** Der Anker löst die Zirkularität, die Klassifikation gattet die Unterdrückung. Die beiden in eine Zahl zu falten war der Fehler, den die Revisionen R5–R7 nacheinander abgeräumt haben.

**V3 — Der Fixpunkt braucht Ausnahmen, und zwar mehr als eine.**
„Hat zuletzt nichts bewirkt" heißt nur dann „kann nie etwas bewirken", wenn Kanal und Gerätezustand unverändert sind. Beides ist hier messbar falsch. Siehe §4 — die Liste war zweimal zu kurz.

## 2. Entscheidung

### 2.1 Die Kommando-Episode

`ExternalOverrideRuntime.cmd_episode_ts` (transient) wird vom Commit gestempelt, wenn **entweder** der Kommandowert wechselt **oder** keine Episode läuft. Der zweite Fall ist nicht kosmetisch: Nach einem Aktorausfall (§4) ist der Kommandowert meist derselbe; ohne diese Klausel startet nie wieder eine Episode, kein Gatter kann je greifen, und die Schleife ist zurück — diesmal unbegrenzt.

`reasserts_suppressed` (transient) zählt im selben Rhythmus und wird mit jeder neuen Episode auf 0 gesetzt. Beide sind prozesslokal und werden bewusst **nicht** persistiert.

### 2.2 M2 — das Idempotenz-Veto

`control/write_economy.reassert_idempotent` ist wahr, wenn alle Bedingungen halten (Reihenfolge: billigste zuerst):

0. der Gerätemodus hat sich nicht gerade geändert (§4),
1. das Ziel **ist** das geltende Kommando (ein geändertes Ziel ist eine neue Episode),
2. eine Episode läuft und das Gerät hatte Zeit zu reagieren (`EPISODE_SETTLE_MIN_S = 90 s`),
3. das Gerät ist zur Ruhe gekommen (zwei identische Lesungen),
4. die Lesung ist **positiv** klassifiziert (§2.3),
5. die Liveness-Fluchtluke ist nicht abgelaufen (`REASSERT_LIVENESS_S = 3600 s`).

Bedingung 4 ist V2 in Code: ein Nicht-Statement über die Herkunft gibt das Gatter nie frei.

### 2.3 Herkunftsklassifikation

Sechs Klassen, nach Evidenzstärke getrennt, damit eine schwache Aussage später nicht als starke gelesen wird:

| Klasse | Evidenz | gibt frei |
|---|---|---|
| `proven_own_echo` | eigener `Context`, geltendes Kommando | ja |
| `current_command_match` | Wert liegt innerhalb `convergence_tolerance(step)` am geltenden Kommando | ja |
| `accepted_settle` | stabil und verträglich, aber unbewiesen | ja |
| `stale_own_echo` | eigener `Context`, **überholtes** Kommando | nein |
| `foreign` | externe Änderung erkannt | nein |
| `unknown` | keine Aussage möglich | nein |

`match_tolerance` ist dieselbe Zahl, nach der der Konvergenz-Watchdog urteilt — die beiden dürfen sich nicht darüber uneinig sein, was „das Gerät steht, wo wir es hingesetzt haben" heißt. Genau diese Uneinigkeit war der ursprüngliche Defekt.

Freigegeben wird nur, wenn der Adoptionsdetektor tatsächlich **gelaufen** ist (`command_echo`, `echo_window`, `stable_offset`). Bei abgeschaltetem oder unterdrücktem Detektor (`opt_out`, `schedule_active`, `safety_window`, …) liegt keine Aussage vor, und ein Nicht-Statement darf das Gatter nicht öffnen. Das ist es, was die 0,5-K-Match-Toleranz sicher macht: Eine unbemerkte Handbedienung 0,4 K daneben erreicht den Wertvergleich nur, solange der Detektor hinsieht.

### 2.4 M4 — das Ratenlimit

`reassert_throttled`, `MIN_SETPOINT_REASSERT_INTERVAL_S = 600 s`. Bewusst das **schwächere** Gatter: M2 beweist, dass ein Schreibvorgang nichts bewirken kann, und braucht dafür Einschwingen plus Herkunft; M4 beweist nichts und begrenzt nur die Rate. Es deckt damit genau die Fälle, die M2 zu Recht ablehnt — Gerät noch in Bewegung, Lesung nicht klassifizierbar: Poise drängt weiter, aber zehnmal pro Stunde statt sechzigmal.

Nie gedrosselt, weil nichts davon ein Reassert ist: ein **anderes Ziel** (Zeitplan, Override, Fensterereignis, Frost und jeder andere Sicherheitspfad erzeugen ein neues Kommando und gehen im selben Tick raus), ein **Moduswechsel**, der **erste** Schreibvorgang einer Episode.

`regulation_period_s` (ADR-0052 §4) bleibt unangetastet — der Parameter hat eine dokumentierte thermodynamische Bedeutung und ist kein Schreibbudget.

Eigenes Feld `reassert_throttled` neben `reassert_idempotent`, nicht verschmolzen: Beweis und Ratenlimit in ein Flag zu falten wäre dieselbe Verwechslung wie in V2.

### 2.5 M3 — der Raster-Hinweis

`quantization_settle_delta` meldet die gemessene Ruhedistanz in einem bewusst schmalen Band, und die Schmalheit ist die Aussage:

- **unten:** Distanzen ≤ `declared_step / 2` sind gewöhnliche Rundung auf dem angegebenen Raster — nichts zu sagen.
- **oben:** Distanzen > `convergence_tolerance(step)` geben M2 nie frei, der Zähler steigt nie, und ein klemmendes, geklemmtes oder falsch gemodetes Ventil kommt hier nie an. Das ist ein **Fehler**, kein Rat, und gehört dem Konvergenz-Watchdog.
- **Beweisschwelle:** `QUANT_MIN_SUPPRESSED = 5` unterdrückte Reasserts **derselben** Episode.
- `declared_step` ist das `target_temp_step`-Attribut des Geräts, nicht der aufgelöste Fallback: Wer nichts angibt, bekommt keine Aussage über eine Poise-Voreinstellung.

Der Hinweis erscheint als **nicht fixable** Reparatur-Meldung `declared_step_mismatch`. Nicht fixable, weil die Ursache außerhalb von Poise liegt (`customize`-Override, Converter-`temp_step`, Geräte-Eigenart) und Poise nicht in die Home-Assistant-Konfiguration des Nutzers schreibt, um sie zu „reparieren". Der Text nennt die **gemessene** Distanz und **zwei** mögliche Ursachen — gröberes Geräteraster oder fester Kalibrier-Offset —, ohne sich auf eine festzulegen; die Funktion kann sie nicht unterscheiden. Deshalb „vermutlich" im Titel.

Das **Rasterlernen** (das tatsächliche Raster aus Beobachtungen ableiten) ist ausdrücklich vertagt. Dieser Hinweis ist die billige Hälfte, die Poise ohnehin schon bezahlt.

### 2.6 Der Watchdog-Fold

Ein unterdrückter oder gedrosselter Reassert ist Schweigen, und Schweigen darf den Detektor für „Gerät übernimmt unsere Befehle nie" nicht blenden. `WriteConvergenceWatchdog.observe_setpoint` zählt Divergenz nur im `elif wrote:`-Zweig, also wird beides als die Evidenz eingespeist, die der Schreibvorgang erzeugt hätte:

```python
_suppressed = (spo.reassert_idempotent or spo.reassert_throttled) and not plan.write_setpoint
... observe_setpoint(..., wrote=plan.write_setpoint or _suppressed, ...)
```

Ohne diesen Fold wäre „weniger schreiben" gleichbedeutend mit „weniger merken". Der konvergierte Zweig läuft zuerst, also verändert der Fold am Normalfall nichts — beides ist getestet.

### 2.7 Sichtbarkeit

`reasserts_suppressed` und `declared_step` stehen in den Diagnosedaten neben `sp_diverged_writes`. Sie sind **nicht** in der `_ATTRS`-Allowlist der Climate-Entität: Schweigen muss prüfbar sein, ist aber keine Regelgröße und erweitert den ADR-0016-Attributvertrag nicht.

## 3. Rückwirkung auf ADR-0055 — geprüft, keine

Die Roadmap gatet jeden Shadow→live-Flip über die Regelgüte-Metrik. Die Befürchtung war ein Dilemma: Zählt ein unterdrückter Reassert als wirkungslose Handlung, verschlechtert er die Metrik; zählt er gar nicht, verändert er die Grundgesamtheit.

Beide Hörner setzen eine Handlungszählung voraus, die es nicht gibt. Die Metrik sieht Schreibvorgänge überhaupt nicht:

| Bein | rechnet aus | Reaktion |
|---|---|---|
| `deviation_k`, `in_band` | `room` gegen `[decision.heat_sp, eff_cool]` | keine — reine Raummessung gegen Poises beabsichtigtes Band |
| `cycles_per_hour` | `mode != last_mode`, mit `mode = wt.mode` | keine — Modus-Regimewechsel, und M2/M4 gatten nur Sollwerte |
| `minutes`, `ppd` | Elapsed-Uhren gewerteter Ticks | keine |

Auch die Grundgesamtheit bleibt: `_fold_regulation_quality` gatet auf `enabled`/`window_open`/`frozen`/`override`/`sched.is_comfort`/`ca_tick_scorable` — kein Kriterium liest den Schreibplan. **ADR-0055 bleibt unverändert.**

Ehrlicher Restpunkt: M2 gibt erst frei, wenn das Gerät innerhalb `convergence_tolerance(step)` (auf 0,5 K gefloort) steht. Poise akzeptiert damit einen Ruheversatz von bis zu 0,5 K und hört auf zu drängen. Dieser Versatz war vor M2 schon da — die Schreibvorgänge haben ihn ja nicht bewegt, das **ist** die Fixpunkt-Prämisse. Wäre die Prämisse falsch, säße der Raum schlechter und `deviation_k`/`in_band` würden das zeigen. Die Metrik ist gegenüber einem M2-Fehler also nicht blind; sie wird nur nicht verschoben, solange M2 richtig liegt. Zusammen mit dem Watchdog-Fold sind das zwei unabhängige Detektoren in dieselbe Richtung.

## 4. Was die Prämisse zerstört — die Liste, die zweimal zu kurz war

Die Fixpunkt-Prämisse lautet: *Das Gerät ist in dem Zustand, in dem dieses Kommando es zuletzt nicht bewegt hat.* Jede Änderung dieses Zustands macht sie nichtig. Drei Fälle, und **zwei davon habe ich beim ersten Anlauf übersehen**:

| Ereignis | Warum die Prämisse fällt | gefunden durch |
|---|---|---|
| Liveness (3600 s ohne Schreibvorgang) | Der Kanal ist nicht verlustfrei — Zigbee-Sleepy-Devices verlieren Writes | V3, von Anfang an geplant |
| **Moduswechsel** | Ein Gerät, das aus `off` zurückkommt oder heat↔cool wechselt, kann den Sollwert geparkt oder neu interpretiert haben, **während es dieselbe Zahl meldet**. `should_write` schreibt deshalb bei `mode_changed` bedingungslos — und das M2-Veto stand in der `and`-Kette davor und hätte es verschluckt | beim Implementieren von M4 |
| **Verfügbarkeits-Flanke** | Der Küchen-TRV meldet `power_outage_count: 852`. Über ein Gerät, das weg war und rebootet haben kann, sagt „hat zuletzt nichts bewirkt" nichts aus | `test_p3_18a_actuator_dropout_then_recovery_resumes_writes` wurde rot |

Der Moduswechsel ist als prämissen-vernichtende Bedingung in **beiden** Gattern kodiert. Die Verfügbarkeits-Flanke bewusst **nicht** als dritter Sonderfall, sondern als eine Regel an der richtigen Stelle: **Ein offline stehender Aktor beendet die Kommando-Episode.** Während er weg ist, wird ohnehin nichts geschrieben — das Löschen kostet nichts und kauft das Einzige, was zählt: Der erste Tick nach seiner Rückkehr ist eine neue Episode und wird sofort geschrieben.

Dass die Liste zweimal zu kurz war, gehört in diesen ADR und nicht in eine Fußnote: Sie ist nicht erschöpfend bewiesen, sondern durch Tests erweitert worden. Ein vierter Fall ist möglich, und der Weg dorthin ist derselbe — ein roter Test, nicht eine Nachbesserung am Anker.

## 5. Verworfene Alternativen

- **`regulation_period_s` für TRVs von 0 hochsetzen.** Der Parameter beschreibt Aktordynamik. Ihn als Schreibbudget zu benutzen, hieße zwei Aussagen in eine Zahl zu legen — und die thermodynamische würde stillschweigend falsch.
- **Das Write-Totband erhöhen.** Behandelt das Symptom für dieses Raster und erzeugt bei anderen Rastern ein neues. Die Ursache ist nicht die Totbandbreite, sondern ein Ziel, das das Gerät nicht darstellen kann.
- **Nur unterdrücken, ohne den Watchdog-Fold.** Wäre „weniger schreiben" um den Preis von „weniger merken". Ein klemmendes Ventil würde still.
- **Herkunft und Fixpunkt in eine Zahl falten.** V2. Kostet die Zone bei unbemerkter Handbedienung.
- **`min_setpoint_reassert_interval_s` als Options-Feld.** Ein Regler an einem Schreibgatter braucht einen Anlass; niemand hat einen genannt, und 600 s liegen weit unter jeder thermischen Zeitkonstante hier. Ein Feld, das niemand richtig einstellen kann, ist eine Fehlerquelle, keine Freiheit.
- **M3-Rasterlernen jetzt.** Das tatsächliche Raster abzuleiten ist ein eigenes Inkrement. Der Hinweis in §2.5 nutzt Evidenz, die ohnehin anfällt.
- **Upstream-Änderung am Converter vorschlagen.** Der Converter deklariert 0,5 K korrekt; die falsche Angabe stammte aus der Nutzer-Konfiguration. Der Vorschlag war eine Revision lang im Bericht und wurde gestrichen — er hätte einen fremden Fehler behauptet.

## 6. Umsetzung (v0.193.0)

- **Pure:** `control/write_economy.py` (neu) — `classify_settle`, `reassert_idempotent`, `reassert_throttled`, `quantization_settle_delta` plus die Konstanten. Kein Home Assistant, kein Runtime-Objekt.
- **Zustand:** `runtime/state.py` — `cmd_episode_ts`, `reasserts_suppressed` (beide transient). Commit-Fold in `runtime/zone_runtime.py`.
- **Pipeline:** `control/pipeline_actuate.py` — beide Verdikte in der Observe-Stufe, beide Vetos im Gatter, Episodenende bei Offline-Aktor.
- **Glue:** `ha/phase_actuate.py` (Watchdog-Fold + Zähler), `ha/tick_orchestrator.py` (M3-Hinweis am bestehenden Sollwert-Checkpoint, neben dem Konvergenz-Verdikt — beide aus **einem** Weltzustand entschieden), `ha/tick_ports.py` (`notify_quantization`, SequencerPorts 21 → 22), `ha/health_reporter.py`, `coordinator.py`, `ha/phase_report.py` (zwei Diagnoseschlüssel).
- **i18n:** `declared_step_mismatch` in `strings.json`, `en.json`, `de.json`.
- **Tests:** `tests/test_write_economy.py` — 18 Fälle: T1-Terminierung, T2-Eskalation, Kontrollgruppe (ehrliches Raster, ein Schreibvorgang), V3-Liveness, M4-Rate, „neues Kommando nie gedrosselt", Moduswechsel gegen beide Gatter, Dropout/Wiederkehr, M3-Band in fünf Richtungen. `tests/integration/test_write_convergence_glue.py` — der zusammengebaute Tick schreibt nicht mehr jeden Tick, und der Hinweis überlebt den Löschpfad. `tests/integration/test_phase0_data_contract.py` — Schlüsselsatz neu eingefroren.

Messwerte der Akzeptanzschleife (dieselben Funktionen, in der Reihenfolge des Gatters):

| Szenario | vorher | mit M2 | mit M2+M4 |
|---|---|---|---|
| ehrliches 0,5-K-Raster, 30 min | 1 | 1 | 1 |
| Feldfall (0,1 deklariert), 30 min | 30 | 2 | 1 |
| Liveness-Fenster, 65 min | 65 | 2 | 2 |

## 7. Prüfstand

**Das Reproduktionsszenario bleibt auf beiden Ebenen** — die Frage aus Plan-Schritt 8.3 ist damit entschieden, und zwar gegen die billigere Antwort:

- **Unit** (`_run_reassert_loop`): trägt den Terminierungsbeweis und komponiert die echten Funktionen von Hand — inklusive M4, denn ohne ihn wäre die Schleife eine schwächere Maschine als die ausgelieferte und jede Zahl darin eine Obergrenze für ein Gatter, das es nicht mehr gibt.
- **Glue** (`test_a_requantising_device_is_not_rewritten_every_tick`): pinnt, dass der **zusammengebaute** Tick die Funktionen überhaupt noch erreicht — Observe rechnet, Gatter konsumiert, Commit stempelt. Eine Refaktorierung, die eines der drei abklemmt, ließe jeden Unit-Test grün und legte 1440 Schreibvorgänge am Tag zurück auf den Draht.

Beide Ebenen tragen eine Nicht-Vakuitäts-Prüfung: die Kontrollgruppe (ehrliches Raster, ein Schreibvorgang, grün vor und nach M2) und der Requantisierungs-Nachweis im Glue-Test.

## 8. Offene Punkte

1. **Die fünfte `customize`-Zeile** (Küche) steht noch. Sie ist absichtlich stehengeblieben — ein lebender Prüfstand. Sie fällt, wenn der Mitschnitt die Küche trotz 0,1-Override ruhig zeigt, und wenn die Ersatzfrage für den feineren Bedien-Stepper beantwortet ist (ungeklärt, ob `precision` bei Climate-Entitäten über `customize` wirkt).
2. **Die Metrik ist ein Proxy und heißt so.** Der Anlass ist Batterie, gemessen werden Writes/Tag. Aqara meldet den Ladestand grob und mit bis zu 24 h Verzug; alle sechs TRVs stehen auf 100 %. Ein Batterie-Vorher/Nachher ist über Wochen nicht auflösbar.
3. **M3-Rasterlernen**, Keep-alive 600 → 1800 s, Feed-Totband 0,1 → 0,2 K — drei unabhängige Inkremente, keines blockiert etwas.
4. Die Liste in §4 ist empirisch, nicht erschöpfend.

## Nachtrag N1 (2026-09-12, v0.193.1): Feldbefunde nach dem Rollout — umgesetzt

Der Rollout in der Referenzanlage hat den Mechanismus bestätigt und zwei Mängel gezeigt, beide außerhalb der Entscheidungen oben.

**Messung.** Diagnose der Küchen-Zone, eine knappe Stunde nach dem Neustart: `reasserts_suppressed: 37` in **einer einzigen, ununterbrochenen Kommando-Episode** — der Zähler wird bei jedem Kommandowechsel zurückgesetzt, also hat `last_cmd_sp` sich kein Mal geändert. Der befürchtete Fall „Sollwert wandert, jede neue Episode kostet einen Schreibvorgang" tritt nicht ein, und der Grund ist strukturell: In der Absenkung bindet `binding_lower_cause: en16798`, also die Normuntergrenze, die sich mit T_rm über Stunden bewegt. Dazu `sp_diverged_writes: 0`, `ca_deviation_k: 0.0`, `ca_time_in_band: 100.0` über 1412 gewertete Minuten, und `sp_adopt_reason: "command_echo"` — M2 gibt auf `PROVEN_OWN_ECHO` frei, der stärksten der drei Klassen aus §2.3, nicht auf `accepted_settle`.

**N1.1 — Dezimaltrennzeichen.** Home Assistant rendert Repair-Platzhalter **unübersetzt**: Was die Integration übergibt, steht wörtlich in jeder Sprache. Der deutsche Text zeigte damit „eine Sollwert-Schrittweite von 0.1 K". `ha/presenter.decimal(value, language=…)` formatiert jetzt für die Instanzsprache. Zwei Grenzen, benannt statt versteckt: `hass.config.language` ist die **Instanz**-, nicht die Betrachtersprache (bei Abweichung folgt das Trennzeichen der Instanz), und nur Deutsch ist Sonderfall, weil `en`/`de` die gesamte i18n dieser Integration ist (ADR-0021).

**N1.2 — Verwaiste Repair-Issues.** Poise baut seine Issue-Ids als `f"{key}_{entry_id}"`, HAs Issue-Registry ist aber nicht entry-gebunden: Beim Löschen eines Eintrags blieben sie stehen. Gefunden wurde ein Eintrag vom 23. Juni, dessen Config-Entry längst weg war — und weil der Repair-Dialog aus dem Eintrag rendert, ließ er sich nicht einmal wegklicken. AR-29 hatte seinerzeit nur das **eine** globale Hub-Issue namentlich abgeräumt; die Per-Entry-Familie war übersehen. `async_remove_entry` löscht sie jetzt per Suffix (kein Key-Katalog — der würde still veralten), und ein einmaliger Lauf in `async_setup` räumt die bereits gestrandeten ab. Der Prädikat `orphan_entry_id` löscht ausschließlich den mittleren Fall: Schwanz sieht wie eine Entry-Id aus (26-stellige ULID oder 32-stelliges Hex älterer Installationen) **und** gehört zu keinem lebenden Eintrag irgendeiner Domain. Ein globales Issue wie `frost_zone_not_controlling_boiler` (Schwanz `boiler`) bleibt unberührt.

---

## Konsequenzen

Poise schreibt einen Sollwert noch, wenn er etwas bewirken kann, und sagt es, wenn ein Gerät ein Raster meldet, das es nicht umsetzt. Der Feldfall fällt von rund 1440 auf **etwa 24** Schreibvorgänge am Tag — Faktor 60 —, ohne dass die Regelung, der Konvergenz-Watchdog oder die Freigabemetrik etwas verlieren.

**Korrektur (Review 2026-09-12):** Hier stand zunächst „auf 2 Schreibvorgänge am Tag". Das war die Zahl aus dem 30-Minuten-Testfenster in §6, fälschlich als Tagesrate gelesen. Die stationäre Rate folgt aus `REASSERT_LIVENESS_S = 3600`: ein freigegebener Reassert pro Stunde und Zone, also ~24/Tag. **Zwei pro Tag waren nie das Ziel** — sie wären nur mit einem Liveness-Intervall um 12 Stunden zu haben, und das ist der falsche Tausch: Ein TRV, dem ein Schreibvorgang verloren ging oder das rebootet hat, bliebe dann einen halben Tag falsch eingestellt. Die Stunde ist die bewusste Wahl, die Zahl im Text war der Fehler.

Der Preis ist ehrlich zu benennen: Poise akzeptiert jetzt einen Ruheversatz von bis zu 0,5 K, statt ewig dagegen zu schreiben. Das ist keine neue Ungenauigkeit — der Versatz war vorher auch da, nur lauter.
