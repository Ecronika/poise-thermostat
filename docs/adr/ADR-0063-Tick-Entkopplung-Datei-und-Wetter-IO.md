# ADR-0063: Datei- und Wetter-I/O aus dem Tick-Lock — und was `tick_ms` danach misst

**Status:** Implementiert (v0.179.0) · **Wirkung:** Live-A · **Datum:** 2026-07-25 · **Bezug:** ADR-0011 (Feld-Trace/Golden-Replay), ADR-0020 (Performance-Budget), ADR-0025 (Optimal-Start/Coast), ADR-0026 (Schatten-Schätzer-Politik), ADR-0007 (Persistenz) · **Grundlage:** Refactoring-Bericht coordinator.py (Befund 5), ADR-0020-Budgetmessung

## Kontext

Der Tick hält den Coordinator-Lock. Zwei I/O-Operationen lagen darin:

1. **Trace-Append** (ADR-0011, Opt-in): `await recorder.append(line)` war das LETZTE beobachtbare Statement des Ticks. Die Executor-Runde plus Dateisystemzugriff zählten in `tick_ms`.
2. **Wetter-Forecast** (ADR-0025): bei abgelaufenem TTL rief jeder prädiktive Tick `weather.get_forecasts` **blockierend** auf — die einzige `blocking=True`-Serviceanfrage der Integration, mit 10 s Timeout. Eine langsame Wetter-Integration streckte den Tick bis zu diesem Timeout, mit gehaltenem Lock.

Beides war Absicht gewesen (Determinismus im Golden-Replay bzw. „der Tick sieht immer die frischeste Prognose"), aber beides bezahlt der Regelpfad. ADR-0020 misst `tick_ms` als Skalierungssignal — und maß damit im Wesentlichen fremde Latenz.

## Entscheidung

### F-TRACEIO — Trace-Schreiben in eine Queue

Der Tick **baut** den Record weiterhin innerhalb der `_trace_enabled`-gegateten Swallow-Grenze und **stellt ihn nur ein** (`TraceRecorder.enqueue`, synchron, I/O-frei). Ein Drain-Task schreibt ihn auf dem Executor.

- **Reihenfolge:** genau EIN Drain-Task über einer FIFO-Queue → Dateireihenfolge = Tick-Reihenfolge (der Golden-Replay hängt daran).
- **Datei-Inhalt:** der Executor hängt weiter Zeile für Zeile an und prüft die Größenkappe vor jeder — die Bytes auf Platte sind identisch zum Vorzustand (2 Generationen, ~2× Kappe).
- **Beschränkt:** die Queue ist auf 512 Zeilen gedeckelt; bei stehendem Datenträger werden die ÄLTESTEN verworfen (mit genau einer Warnung), statt Speicher unbegrenzt wachsen zu lassen.
- **Unload:** `flush_on_unload()` schreibt die Restmenge; der Coordinator ruft es nach dem Final-Save, wenn nachweislich kein Tick mehr produziert.

Der Record-**Bau** bleibt bewusst im Tick und in der Swallow-Grenze: ihn herauszuziehen (etwa auf `TickOutcome.trace_record`, das deshalb `None` bleibt) würde einen geschluckten Bau-Fehler auf den Fehlerpfad des Ticks heben — ohne Gewinn an Tick-Zeit, denn der Bau ist reine Rechnung.

### F-FORECAST — Hintergrund-Refresh mit EINER bewussten Ausnahme

Gewählte Gate-Variante:

- **Warmer Cache:** ein abgelaufener, aber vorhandener Cache **bedient diesen Tick** und stößt den Refresh im Hintergrund an. Schlimmstenfalls rechnet Optimal-Start mit einer um einen Tick älteren Prognose — bei stündlichen Stützstellen weit innerhalb der Modellauflösung.
- **Kaltstart** (gar kein Cache — frischer Neustart, oder alle Stützstellen abgelaufen): **wartet weiterhin**. Genau dieser Tick entscheidet nach einem nächtlichen Neustart über eine Vorheiz-Kante; er darf nicht auf die flache Konstant-Außentemperatur zurückfallen. Er ist durch dasselbe 10-s-Timeout begrenzt und tritt höchstens einmal pro `FORECAST_TTL_S` auf (der Fehler-Backoff deckt den Rest ab).

Nebenbedingungen, explizit: **Single-Flight** (höchstens ein Refresh in Flug), **atomarer Snapshot** (der Refresh ERSETZT die Sample-Liste, mutiert sie nie in place), **Cancel** (`async_close` beim Unload, kein Task überlebt den Config-Entry).

### `tick_ms`-Semantik (dokumentierte Diagnose-Änderung)

`tick_ms`/`tick_ms_ewma`/`tick_ms_max`/`tick_over_budget` messen ab v0.179.0 **den Kontrollpfad**. Ein langsamer Datenträger oder eine langsame Wetter-Integration erscheinen nicht mehr darin. Der Wert wird dadurch als Skalierungssignal (ADR-0020) *aussagekräftiger* — er misst jetzt, was Poise selbst tut —, ist aber mit historischen Werten nicht vergleichbar.

## Begründung

Der Tick-Lock serialisiert die Regelung einer Zone. Alles, was darin wartet, verzögert Sicherheits- und Komfortentscheidungen und verfälscht zugleich die Messung, die diese Verzögerung aufdecken soll. Trace und Forecast sind beide *nicht* regelkritisch in dem Sinne, dass der aktuelle Tick auf ihr Ergebnis warten müsste — der Trace gar nicht, der Forecast nur beim allerersten Mal. Genau diese Asymmetrie bildet die Entscheidung ab, statt beide Fälle gleich zu behandeln.

Für den Forecast wurde die reine „nie warten"-Variante verworfen: sie hätte nach jedem Neustart einen prädiktiven Tick mit flacher Konstante bezahlt, und das ist der Tick, der zählt.

Beide Hintergrundarbeiten laufen als **getrackte** Tasks (`hass.async_create_task`), nicht als Background-Tasks: die Arbeit soll zu Ende geführt und nicht beim Herunterfahren abgeschnitten werden, und `hass.async_block_till_done()` macht sie in den Glue-Tests deterministisch. Der Forecast-Task wird beim Unload trotzdem explizit gecancelt, weil ein hängender 10-s-Call den Entry sonst überdauert.

## Konsequenzen

**Positiv:** Der Tick wartet nicht mehr auf Datei- oder Wetter-I/O; `tick_ms` misst den Regelpfad; ein stehender Datenträger kann Poise nicht mehr ausbremsen; ein hängender Wetter-Dienst kostet einmalig statt in jedem TTL-Zyklus.

**Negativ/Migration:** (a) `tick_ms`-Historie bricht — Automationen mit absoluten Schwellen neu kalibrieren. (b) Bei Absturz (nicht Unload) können bis zu 512 Trace-Zeilen ungeschrieben bleiben; für ein Opt-in-Diagnosewerkzeug akzeptiert. (c) Optimal-Start rechnet im eingeschwungenen Betrieb mit einer bis zu einen Tick älteren Prognose. (d) Der Forecast-Zeitstempel wird beim **Start** der Anfrage gesetzt, nicht bei ihrem Ende — eine langsame Anfrage verlängert die TTL dadurch nicht.

## Verifizierung

- `tests/integration/test_phase10_trace_io.py` — eine 400 ms blockierende Schreibfunktion darf `tick_ms` nicht erreichen (vorher hätte der Tick ≥ 400 ms gemeldet); FIFO-Reihenfolge über die Queue; `flush_on_unload` schreibt die Restmenge; Queue-Deckel verwirft die ältesten mit genau einer Warnung; `OSError` wird auf DEBUG geschluckt.
- `tests/integration/test_phase10_forecast_async.py` — Kaltstart wartet nachweislich (`tick_ms ≥ 400 ms`), der warme Stale-Tick nicht (`< 200 ms`), der Refresh findet trotzdem statt; Single-Flight; `async_close` cancelt; der Unload lässt keinen Task zurück.
- `tests/integration/test_phase0_forecast_gating.py`, `test_forecast_backoff.py`, `test_phase5a_executor.py` — Payload (`{"type": "hourly", "entity_id": …}`), Gating, TTL, Backoff und Last-Good-Cache unverändert; die Refetch-Assertions warten jetzt explizit auf den Hintergrund-Task.
- `tests/test_phase0_golden_replay.py` — der Golden-Trace bleibt bit-gleich (Reihenfolge und Inhalt der Datei sind unverändert).

## Verknüpfungen

Löst die im Refactoring-Plan als `F-TRACEIO`/`F-FORECAST` geführten Verhaltensfixes ein und beendet den dort dokumentierten „Trace-Append als letztes Statement unter dem Lock". Ändert die Semantik der ADR-0020-Kennzahl (dort als bekannte Diagnose-Änderung vermerkt). Berührt ADR-0011 nur in der Schreibmechanik, nicht im Format; der Replay-Vertrag bleibt.
