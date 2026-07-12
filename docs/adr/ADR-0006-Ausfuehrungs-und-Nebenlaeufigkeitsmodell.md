# ADR-0006: Ausführungs- & Nebenläufigkeitsmodell

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-18 · **Bezug:** E4, E6, K13 · **Verifizierung:** Code-Review (Thema B)

## Kontext
Der Strukturplan verlangt einen **atomaren** Tick in fester Reihenfolge und definierte Behandlung eventgetriggerter Sofort-Eingriffe (K13). Offen: wie technisch serialisieren, welche Zeitbasis.

## Entscheidungstreiber
Atomarität/Determinismus (G27), vorhersehbare Behandlung von Überlappung und Events, Restart-/DST-Festigkeit der Timer, Testbarkeit.

## Befund am Code (Belege)
- **Vesta = bestes atomares Tick-Skript:** `_async_tick_impl` mit explizit nummerierter Pipeline **Schritt 0–10** (Reset → Manual-Guard → Safety/Sensorausfall early-return → Window → Frost → effective target (pure) → Control+`_set_heaters` → Duty → Hardware-Fail → Learning+Save → Boiler). Plus **explizites Event-Coalescing** ohne Lock: `_tick_running`/`_tick_pending` — ein konkurrierender *geplanter* Tick wird verworfen, ein *event-/user-initiierter* setzt `_tick_pending` und läuft **genau einmal** nach („heater commands never silently dropped"). Listener planen via `async_create_task`, rufen nie synchron.
- **RoomMind:** kein eigener Lock, verlässt sich auf die `DataUpdateCoordinator`-Serialisierung; Events über entkoppeltes `async_request_refresh()`. Pro-Raum-Exceptions geschluckt (ein Raum bricht den Tick nicht ab).
- **ThermoSmart:** Instant-Override `_handle_trv_change` (Trigger `abs(neu−last_written) > 0.4`) endet mit `async_create_task(async_request_refresh())` — eventgetriebener Sofort-Recompute, serialisiert nur durch den Coordinator.
- **Zeitbasis:** Nur **RoomMind** nutzt `time.monotonic()` (Sensor-Staleness). **Vesta und ThermoSmart sind durchgängig Wall-Clock** (`time.time()`/`dt_util.now()` für Override-Timer, Delays, Min-Run, Decay) → **DST-/Clock-Jump-anfällig** (Negativbeleg). Versatile injiziert `self._now` für Tests.
- **Async:** RoomMind vorbildlich (blockierende CSV-I/O in `async_add_executor_job`). **Negativbeleg:** ThermoSmarts `async_save` ohne `asyncio.Lock`, aus mehreren Pfaden aufgerufen → Interleaving möglich.

## Entscheidung
1. **Atomare, nummerierte Tick-Pipeline** (Vesta-Muster): ein sequenzielles, von oben lesbares Skript mit early-returns für Sicherheit/Sensorausfall, in der Vertragsreihenfolge aus dem Strukturplan.
2. **Serialisierung = `asyncio.Lock` um den Tick + `_tick_pending`-Flag** (Vesta-Coalescing gehärtet): geplante Ticks bei Überlappung verwerfen, event-/user-Ticks genau einmal nachholen. Listener **planen** den Tick (`async_create_task`/`async_request_refresh`), rufen ihn nie synchron.
3. **Injizierbare monotone Uhr** (`clock: Callable[[], float] = time.monotonic`) für **alle Dauer-Timer** (Min-Run/Off, Window-Delay, Override-Ablauf, Grace); Wall-Clock nur für Kalender/Schedule. Für restart-feste Timer zusätzlich persistierte Wall-Clock-**Anker**.
4. **Blockierende I/O strikt in Executor** oder über native async-`Store`; **`asyncio.Lock` um Persistenz**.

## Begründung
Vesta liefert das lesbarste atomare Skript und das vorhersehbarste Event-Modell; ein zusätzlicher Lock macht Re-Entrancy wasserdicht (Vesta nutzt nur Flags). Monotone Zeit ist die direkte Lehre aus den DST-/Clock-Jump-Negativbelegen von Vesta/ThermoSmart; Injektion macht Timer testbar (Versatile-`self._now` bestätigt den Wert). Executor + Persistenz-Lock beheben ThermoSmarts ungeschützten Save.

## Konsequenzen
**Positiv:** deterministischer, atomarer Ablauf; kein stiller Verlust von Sofort-Eingriffen; restart-/DST-feste Timer; testbar mit virtueller Uhr.
**Negativ/Kosten:** persistierte Wall-Clock-Anker nötig, damit monotone Timer einen Neustart überdauern (monotonic startet bei 0); etwas mehr Infrastruktur als ein nackter Coordinator.

## Compliance
Allgemeingültige Muster, eigenständig umgesetzt; generisch.

## Verknüpfungen
Ruft die Schichten aus ADR-0005 in Vertragsreihenfolge. Liefert die Zeitbasis für ADR-0007 (Bootstrap/Timer) und ADR-0009 (Update-Intervalle/Gates).
