# ADR-0064: Persistenz-Checkpoint am Tick-Ende — ein Zustand, eine Momentaufnahme

**Status:** Implementiert (v0.179.0) · **Wirkung:** Live-D · **Datum:** 2026-07-25 · **Bezug:** ADR-0007 (Persistenz/Store-Format), ADR-0044 (Outcome-Scoring), ADR-0045 (Einsparbericht), ADR-0046 §8 (Verdichter-Lifecycle), ADR-0055 (Regelgüte-Metrik), ADR-0012 (Repair-Issues) · **Grundlage:** Refactoring-Bericht coordinator.py (Befund 12), Phase-0-Checkpoint-Test

## Kontext

Der Store-Checkpoint (`_maybe_save`) lag an **zwei** Stellen, und beide zu früh:

**Normaler Tick.** Der Save lief nach dem Commit der Aktor-Writes, aber **vor** `finalize_tick`. Alles, was das Finalize fortschreibt — der Kompressor-Lifecycle-Fold (ADR-0046 §8), die Outcome-Statistik (ADR-0044), der Einsparbericht (ADR-0045), die Regelgüte (ADR-0055), der Referenzrahmen-Offset (ADR-0056) und der Tau-Settle-Zustand — landete deshalb erst mit dem NÄCHSTEN Save auf Platte. Ein Save in Tick N schrieb den Finalize-Zustand von Tick N-1. Beim periodischen 30-Tick-Rhythmus fiel das nicht auf; beim dirty-getriebenen Save schon: eine Nutzeraktion löste einen Save aus, dessen Metriken einen Tick alt waren. Nach einem Neustart klaffte die Lücke zwischen Zustand und Metrik.

**Unavailable-Pfad.** Der Dirty-Flush lief **vor** dem Safe-State-Write. Dessen eigener `has_actuated`-Flip blieb damit unpersistiert und musste auf einen späteren Tick warten — der bei anhaltendem Sensorausfall nicht kommt, weil dieser Pfad keinen periodischen Save kennt.

Der Refactoring-Plan hat beide Positionen als Phase-0-Verhalten eingefroren (`test_phase0_persistence_checkpoint`) und die Korrektur als `F-SAVEPOINT` zurückgestellt.

## Entscheidung

**Ein Checkpoint, am Ende des Ticks.**

- Normaler Tick: der Save läuft **nach** `finalize_tick`. Die Momentaufnahme enthält Zustand *und* Metriken desselben Ticks.
- Unavailable-Pfad: der Dirty-Flush läuft **nach** dem Safe-State-Write. Nutzerabsicht und der `has_actuated`-Flip gehen gemeinsam auf Platte; der Tick lässt nichts offen.

Da die Position nicht mehr variiert, beschreibt die `PersistencePhase`-Direktive nur noch das **Gate**, nicht den Ort:

- `ALWAYS` — normaler Tick: `_maybe_save` läuft; dessen eigene Dirty-/Kadenz-Logik entscheidet, ob wirklich geschrieben wird.
- `DIRTY_ONLY` — Unavailable-Pfad: nur eine anstehende Nutzerabsicht wird geflusht, nie die periodische Kadenz. Ein Sensorausfall soll den Store nicht in Bewegung halten.

Die Save-*Entscheidung* selbst (Dirty/Kadenz, F6 „Dirty-Flag nur bei Erfolg löschen") bleibt unverändert im Adapter.

## Begründung

Ein Snapshot, der Zustand und Metrik aus verschiedenen Ticks mischt, ist nach einem Neustart schwer zu interpretieren und macht die Outcome-/Einspar-Auswertung um genau einen Tick unehrlich. Das Ende des Ticks ist der einzige Zeitpunkt, an dem alles, was dieser Tick verändert hat, auch tatsächlich verändert ist — jede frühere Position ist eine willkürliche Momentaufnahme mitten in der Transaktion.

Die zwei Positionen waren zudem eine Quelle stiller Sonderfälle: der Unavailable-Pfad musste den Flush eigens vorziehen, *weil* der normale Checkpoint hinter seinem Early-Return lag. Mit einem Checkpoint am Ende entfällt der Sonderfall; nur das Gate unterscheidet sich, und das aus einem klaren Grund.

**Akzeptierter Trade-off:** Wirft `finalize_tick` eine Ausnahme, speichert dieser Tick nicht. Verloren geht dabei nichts — `dirty` wird nur bei erfolgreichem Save gelöscht, eine anstehende Nutzerabsicht schreibt also der nächste Tick statt dieser. Der umgekehrte Fall (Save vor einem crashenden Finalize) hätte einen Zustand persistiert, dessen Tick nie zu Ende lief.

## Konsequenzen

**Positiv:** Store-Inhalt ist in sich konsistent; Lifecycle, Outcome, HDH/Einsparung, Regelgüte, Offset und Tau-Settle stammen aus demselben Tick wie der Rest; der Unavailable-Pfad lässt keinen Flip offen; die Checkpoint-Sonderfälle im Tick-Ablauf verschwinden.

**Negativ/Migration:** (a) `PersistencePhase.BEFORE_EXECUTION`/`AFTER_EXECUTION` heißen jetzt `DIRTY_ONLY`/`ALWAYS` — ein internes Kontrakt-Enum ohne Store-Berührung, die Persistenzformat-Version bleibt unverändert. (b) Auf dem Unavailable-Pfad entfällt der frühere Save-`await` **vor** der Safe-State-Entscheidung: die Ausfalluhr und der Aktor-Read liegen dadurch eine Save-Dauer früher — der Safe-State greift auf einem speichernden Tick minimal eher, und der Plan wird gegen eine minimal ältere Geräte-Momentaufnahme aufgelöst. Beides im Millisekundenbereich und gegenüber dem 15-Minuten-Timeout bedeutungslos. (c) Ein Absturz *innerhalb* von `finalize_tick` verschiebt den Save um einen Tick (siehe oben).

## Verifizierung

- `tests/integration/test_phase0_persistence_checkpoint.py` — von „speichert den Vor-Tick-Zustand" auf „speichert den Zustand DIESES Ticks" gekippt: ein Sentinel-Lifecycle aus dem Fold dieses Ticks steht im Payload, und die Outcome-/HDH-/RegQ-Werte im selben Payload sind die Nach-Finalize-Werte. `has_actuated` beim ersten erfolgreichen Setpoint-Write landet weiterhin im selben Tick. Der Unavailable-Test prüft jetzt die umgekehrte Reihenfolge (Safe-Write vor Flush) und dass `dirty` danach leer ist.
- `tests/test_phase1_tick_result.py` — Enum-Werte/Mitglieder und die beiden `TickPlan`-Formen auf das neue Gate umgestellt.
- Volle Glue- und Pure-Suite grün; die Store-Format-Tests (`test_storage.py`, `test_phase3_codec_wiring.py`, `test_migration*.py`) unverändert — das Format ist nicht berührt.

## Verknüpfungen

Löst den im Refactoring-Plan als `F-SAVEPOINT` geführten Verhaltensfix ein und beendet Befund 12 („der Save sieht den vorigen Tick"). Verfeinert ADR-0007 um die Checkpoint-Position; die Metrik-ADRs 0044/0045/0055/0056 und der Lifecycle-Fold aus ADR-0046 §8 werden dadurch erstmals tickgenau persistiert.
