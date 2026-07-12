# Poise Review Verification — Ergebnisbericht

Alle 18 Findings (F1–F18) wurden gegen den tatsächlichen Code geprüft. Bei offenen Fragen wurde die Entscheidung anhand der ADR-Dokumente getroffen, wie gewünscht.

**Bestätigt und behoben: F1, F2, F3, F4a, F4b, F5, F6, F7, F8, F9, F10, F12, F13, F14, F16 (15 von 18).**
**Widerlegt: F11 (ADR-0046 dokumentiert das Verhalten explizit als gewollt).**
**Als Bestandsschutz akzeptiert (kein Fix nötig/sinnvoll): F15, Teile von F17/F18.**

Für jeden Fix wurde vorab der exakte Bug am unveränderten Original nachvollzogen, dann behoben, und abschließend ein Regressionstest geschrieben, der nachweislich am Original fehlschlägt und an der reparierten Version besteht (Ausnahme: F14, siehe unten — dort ist "am Original fehlschlagen" prinzipbedingt nicht möglich).

Vollständiger Testlauf (368 Tests inkl. 10 neuer): grün bis auf einen vorbestehenden, mit dem Review nicht zusammenhängenden ADR-Index-Lint-Fehler (Artefakt des Staging — nicht alle 60 ADR-Dateien wurden übertragen). `ruff check`, `ruff format --check` und `mypy --strict` sind sauber.

## Behobene Findings

**F1 — UnboundLocalError im Schatten-Block bei deaktivierter Zone.** `final_mode`, `_guard_pol`, `_g_min_off`, `_g_mode_hold` wurden nur innerhalb `if self._enabled:` berechnet, aber im unconditional Shadow-Block referenziert → Crash bei jedem Tick einer deaktivierten Zone, verschluckt vom breiten `except`, fror dabei lautlos das Wallclock-Compressor-Lifecycle-Tracking ein. Zusätzlich einen vom Review nicht benannten Zwillingsbug am selben Muster gefunden (`_comp_block = _guard_block`) und mitbehoben. Fix: Mode-/Guard-Policy-Auflösung läuft jetzt unconditional; nur die tatsächlichen Schreib-Aktionen bleiben `enabled`-gated.

**F2 — Toter Aktor wird ungebremst weiterbeschrieben.** `_emit_health_issues` prüfte nur `states.get(...) is None` (entfernte Entität), nicht `state == "unavailable"` (Gerät vom Netz, State-Objekt bleibt registriert) — der häufigere Realfall. Kein Repair-Issue, und `should_write()` interpretierte den unbekannten Setpoint als "immer schreiben" → `climate.set_temperature` ging jeden Tick ins Leere. Fix: Unavailable-Check korrigiert + Schreib-Gate um `_actuator_online` erweitert.

**F3 — Unplausibler Rohwert springt direkt auf 20 °C-Fake-Default statt Degradationsleiter.** `ingest_temperature()` wurde ohne `last_good` aufgerufen — die "derived"-Stufe der Leiter war totes Wissen. Ein einzelner Zigbee-Glitch (z. B. Fehlmessung °F als °C) sprang direkt auf den erfundenen 20 °C-Default, der geregelt UND ans EKF gelernt wurde. Fix: `last_good=self._prev_room` übergeben; ein DEFAULT-Reading wird wie eine gefrorene Sensorlesung behandelt (Regelung fällt auf die Frost-/Schimmel-Health-Floor zurück, Lernen pausiert); eine DERIVED-Lesung wird weiterhin geregelt, aber nie ans EKF gelehrt und der Anker (`_prev_room`) bleibt über mehrere aufeinanderfolgende Glitches hinweg erhalten (kein Rückfall auf den harten Default schon nach dem zweiten Tick).

**F4a — Fenstersensor-Ausfall wird wie "geschlossen" behandelt.** `_window_open()` erkannte `unavailable`/`unknown` nicht getrennt von "closed" (beides ≠ `"on"`). Ein toter Kontaktsensor hielt die Zone lautlos für immer bei "Fenster zu". Fix laut ADR-0041 §5 ("heizen wie ohne Sensor + Repair-Issue"): neues Repair-Issue `window_sensor_unavailable` (inkl. DE/EN-Übersetzung); ein Ausfall lässt `sensor_open=False` (unverändert), wodurch die Auto-Slope-Erkennung (F4b) als Fallback greift. Ein bestätigtes "on" von einem anderen, weiterhin funktionierenden Sensor wird trotzdem respektiert.

**F4b — Auto-Slope-Erkennung lief nie mit, sobald ein Fenstersensor konfiguriert war.** `if self._windows: return` deaktivierte den Slope-Detektor komplett, sobald irgendein Fenstersensor konfiguriert war — auch dann, wenn er ausfällt. ADR-0041 §2 legt Exklusivität bewusst fest ("Sensor schlägt Heuristik"), das wurde respektiert; der Nachtrag (Stufe 2, v0.67.0) verlangt aber den Fallback bei Sensorausfall. Fix: Der Detektor bleibt nur dann kalt, wenn der Sensor tatsächlich meldet; bei Ausfall läuft er als Fallback mit.

**F5 — Sensorausfall reißt keine Lern-/Fenster-Anker zurück.** Der `air is None`-Zweig setzte `{"available": False}` zurück, ohne `_last_mono`, `_prev_room`, `_prev_room_mono`, `_heatup_acc`, `_wa_ref_room`, `_wa_ref_mono`, `_wa_prev_mono` zu resetten — anders als der bereits vorhandene Fenster-/Frozen-Pause-Zweig (V5). Ein mehrtägiger Sensorausfall hätte beim Wiederanlauf eine reale-aussehende Zeitspanne über den Ausfall hinweg integriert. Fix: dieselben Anker werden jetzt auch hier zurückgesetzt.

**F6 — Dirty-Flag wird bei fehlgeschlagenem Save trotzdem gelöscht.** `self._dirty = False` stand vor dem `await self._store.save(...)`. Ein Storage-Fehler verlor damit lautlos die Information, dass ungespeicherte Änderungen existieren. Fix: `_dirty = False` erst nach erfolgreichem Save, innerhalb des try-Blocks.

**F7 — Fehlende Override-Expiry nach Neustart eines Pre-ADR-0059-Holds.** Ein Hold ohne persistierte `override_expires_at` (alte Version, oder anderweitig verlorenes Feld) blieb nach dem Neustart bei `None` — nicht weil er "permanent" ist, sondern weil er nie berechnet wurde. Ohne Fix läuft ein solcher Hold für immer weiter statt real abzulaufen. Fix: fehlende Expiry wird beim Bootstrap aus `override_set_wall`/`policy`/`timer_h`/`max_h` neu berechnet — exakt wie beim frischen Setzen.

**F8 — Person/Device-Tracker an einer benannten Zone wird als "unbekannt" statt "abwesend" gewertet.** `_tristate()` fiel bei jedem State außerhalb der festen Token-Liste (z. B. eine Zone wie "Work"/"Gym", die `person`-Entitäten als State melden) auf `None` zurück. `any_present()`s Fail-safe (unresolved → present) interpretierte eine bestätigt abwesende Person dann fälschlich als "zuhause" — das Gegenteil eines Fail-safes. Fix: für `person`/`device_tracker` gilt jeder nicht erkannte, aber aufgelöste State (kein unknown/unavailable) als "nicht zuhause".

**F9 — HDH-Ersparnis/Outcome-Session buchen pauschal 1 Minute pro Tick statt echter Zeit.** Ereignisgetriebene Refreshes (< 60 s) wurden trotzdem mit einer vollen simulierten Minute verbucht — exakt das Muster, das die benachbarte `_ca_dt`/`_ref_dt`-Buchführung bereits vermeidet. Fix: gleiche real-elapsed-dt-Logik (gedeckelt auf 2×Tick-Intervall) jetzt auch hier, neues `_hdh_last_mono`-Attribut.

**F10 — Wetter-Forecast-Fehler wirft den Cache weg und hämmert ohne Backoff.** Ein `except`-Zweig gab hart `fallback` zurück und ignorierte einen eventuell noch guten, nur leicht veralteten Cache; `_forecast_at` blieb unverändert, sodass ein dauerhaft ausgefallener Wetterdienst bei jedem einzelnen Tick erneut angerufen wurde. Fix: fällt bei Fehler auf den zwischengespeicherten Forecast zurück (degradiert selbst erst bei leerem Cache zu `fallback`) und startet einen `FORECAST_TTL_S`-Backoff (`_forecast_fail_at`) vor dem nächsten Retry.

**F12 — Fehlgeschlagener Tick bleibt unsichtbar.** Ein Fehler in `_run_once` wurde nur generisch von `DataUpdateCoordinator` geloggt, ohne Poise-eigenes Signal. Fix, gespiegelt am bestehenden `persistence_failed`-Muster: neues `tick_failing`-Repair-Issue nach 3 aufeinanderfolgenden Fehlschlägen (`_tick_failures`); die Exception wird in jedem Fall unverändert weitergereicht.

**F13 — `override_policy` (hot-apply-fähige Option) wird beim Bootstrap vom persistierten Store überschrieben.** ADR-0059 dokumentiert diese Einstellung explizit als "hot-apply-fähig" (Options-Eigentum), bereits korrekt in `__init__` über `_read_override_options` gelesen — der Bootstrap-Restore überschrieb sie danach trotzdem erneut aus dem alten Store-Wert, sodass eine spätere Options-Änderung beim nächsten Neustart lautlos zurückfiel. Fix: dieser Restore wurde entfernt.

**F14 — `async_apply_options` mutiert Felder ohne Lock, parallel zu einem laufenden Tick.** Die Feldmutationen liefen ohne Synchronisation gegen `_run_once`, der viele derselben Attribute liest. Fix: der Mutationsblock läuft jetzt unter demselben `self._lock` wie ein Tick — mit Absicht *ohne* den abschließenden `await self.async_request_refresh()`-Aufruf im Lock, da `asyncio.Lock` nicht reentrant ist und `async_request_refresh` intern denselben Lock erneut anfordert (sonst Deadlock). Per Konstruktion enthielt das Original keinen echten beobachtbaren Deadlock (da synchron ohne `await`-Punkt zwischen den Mutationen) — der Regressionstest prüft daher die Korrektheit des Fixes selbst (kein Deadlock bei gleichzeitigem Tick + Options-Apply), nicht "schlägt am Original fehl".

**F16 — AR-11-Actuated-Flag wird nicht persistiert.** `self._has_actuated = True` wurde an drei Stellen direkt gesetzt, ohne `self._dirty = True` zu setzen — ein Neustart nach der ersten echten Aktor-Schreibung, aber vor dem nächsten periodischen Save, hätte das Teardown-Park-Gate zurückgesetzt. Fix: neuer Helper `_mark_actuated()`, der beim ersten Flip `_dirty = True` setzt.

## Widerlegt

**F11 — Override umgeht den Kompressor-Guard.** ADR-0046, Nachtrag (2026-07-04, v0.140.0 → v0.145.0): *"is_safety unverändert (Fenster→off/Frost/Override/Frozen nie geblockt)"* — das ist explizit dokumentiertes, gewolltes Verhalten (Override ist sicherheitsrelevant und daher vom Guard ausgenommen), kein Bug.

## Akzeptiert ohne separaten Fix

**F15** — als niedrige Priorität eingestuft; die verteilte Health-Check-Struktur ist bereits gut kommentiert, ein größeres Refactoring hätte ein ungünstiges Regressionsrisiko-zu-Nutzen-Verhältnis. F2/F4a beheben die konkret gefährlichen lokalen Fälle bereits. **F17/F18** — soweit durch die obigen Fixes berührt (z. B. `_window_open()`-Docstring, `_observe_window_auto()`-Docstring), direkt mit aktualisiert; darüber hinausgehende reine Doku-/Test-Lücken ohne Verhaltensrisiko wurden nicht separat verfolgt.

## Neue Dateien

Zehn neue Regressionstests unter `tests/integration/` (je Fix gegen das unveränderte Original verifiziert: schlägt am Original fehl, besteht am Fix — mit der oben genannten Ausnahme F14), plus ein neuer Testfall in `test_frost_rescue_disabled.py` (F1) und `strings.json`/`translations/{en,de}.json` um zwei neue Repair-Issue-Texte (`window_sensor_unavailable`, `tick_failing`) erweitert.

## Nachtrag: zwei vom Folge-Review korrekt gefundene Lücken in meinem eigenen F4b/F2-Fix

Ein unabhängiges Folge-Review hat zwei Stellen gefunden, an denen meine ursprüngliche Behebung selbst unvollständig war. Beide habe ich nachgeprüft — beide waren real — und behoben:

**F4b-Nachzügler — Fenster-Latch klebt nach Sensor-Recovery.** Mein F4a/F4b-Fix ließ den Slope-Detektor bei Sensorausfall mitlaufen (§5-Failsafe), aber sobald der Sensor wieder gesund meldete, kehrte `_observe_window_auto` sofort zu einem reinen `return` zurück — ohne den während des Ausfalls womöglich gesetzten `open=True`-Zustand zurückzusetzen. Da die Funktion dann nicht mehr aufgerufen wird, feuert auch `step_window_auto`s eigener Anti-Stick-Timer nie mehr. Ergebnis: ein einmal während eines Sensorausfalls erkanntes "offenes Fenster" blieb über `effective_window_open`s OR-Verknüpfung dauerhaft aktiv, obwohl der echte, wieder gesunde Sensor korrekt "zu" meldete — Regelung bliebe kälter als nötig, ohne erkennbaren Grund. Ein Kommentar an der `effective_window_open`-Stelle behauptete zudem fälschlich, der Detektor liefe „always … sensor or not". Fix: der Reset auf `WindowAutoState()` (inkl. `_wa_ref_*`-Anker) passiert jetzt noch VOR der `effective_window_open`-Berechnung in genau dem Tick, in dem der Sensor wieder gesund meldet — nicht erst einen Tick später. Neuer Regressionstest `test_recovered_sensor_clears_a_latched_auto_open`.

**F2-Nachzügler — Frost-Rescue schreibt weiter auf toten Aktuator.** `frost_rescue_target()` behandelt `"unavailable"` absichtlich wie `"off"`/`"unknown"` (alle drei brauchen potenziell die Frost-Floor) — das ist für den enabled-Pfad korrekt, aber der disabled-Zweig hatte (anders als der enabled-Zweig) keine `_actuator_online`-Sperre um den eigentlichen Schreibvorgang. Ein disabled Zone mit tot gemeldetem Aktuator bekam dadurch jeden Tick einen echten `climate.set_temperature`-Aufruf ins Leere. Fix: Schreib- und Mode-Nudge-Block zusätzlich auf `_actuator_online` gegated; off/unknown (Gerät vorhanden, nur nicht im Heizmodus) bekommen die Rescue-Schreibung weiterhin wie vorgesehen. Neuer Regressionstest `test_disabled_zone_does_not_spam_an_offline_actuator`.

Beide Fixes wurden gegen meinen eigenen vorherigen (unvollständigen) Stand verifiziert: die neuen Tests schlagen dort nachweislich fehl und bestehen erst mit der jetzigen Version. Zusätzlich habe ich an der F11-Stelle (`is_safety=…`) einen erklärenden Kommentar mit ADR-0046-Zitat ergänzt — das Folge-Review bemängelte zu Recht, dass die (korrekte) Entscheidung "kein Bug" im Code selbst nirgends dokumentiert war.

Vollständiger Testlauf nach diesen zwei Nachzüglern weiterhin grün (bis auf denselben vorbestehenden ADR-Lint-Fehler); `ruff`/`mypy --strict` sauber.
