# Nachprüfung: v0.168.0 gegen Review und Nachprüfung v0.167.0

*Geprüfter Stand: Commit `e32c1ac` (main, v0.168.0, Release `v0.168.0-alpha`) gegen das Review zu v0.163.0 und die Nachprüfungen zu v0.166.0/v0.167.0 (alle in `docs/reviews/`).*

## Prüfstand

| Prüfung | Ergebnis |
| --- | --- |
| CI | **#1180/#1181 auf `e32c1ac` grün** (main + Release-Tag); Zwischen-Uploads #1176–#1179 rot (Upload-Snapshots, bekanntes Muster) |
| Releases | **v0.167.0-alpha und v0.168.0-alpha existieren als Prerelease** mit Kurz-Changelog („adopt device-side setpoint changes as a hold (opt-out per zone)“) — J1 ist damit substanziell umgesetzt |
| `ruff check` / `format` | ✅ sauber (234 Dateien) |
| `mypy` (strict, lokal mit HA 2024.12.5) | ⚠️ 22 Fehler — unverändert (CI-Blindstelle P3-17) |
| Pure-Core | ✅ **755 Tests grün** (v0.167: 747; +8 Adoption-Tests), Coverage 97,73 % |
| HA-Integration | ✅ **187 Tests grün** (+3); Glue-Coverage lokal **95,33 %**, Gate grün — und **der Coverage-Teardown-Flake ist weg**: die neue `_flush_delayed_store_writes`-Fixture (conftest) drained die HA-Store-Timer genau wie in der v0.167-Nachprüfung empfohlen (B-neu-2 ✅, zur Laufzeit bestätigt) |

## A. Erledigt in v0.168.0

| Befund | Umsetzung | Beleg | Bewertung |
| --- | --- | --- | --- |
| **P1-4a** (Review, größter verbliebener Anwenderschmerz): TRV-Rad-/App-Eingriffe wurden binnen ≤ 60 s überschrieben | **Live umgesetzt (Default an, Opt-out je Zone):** pure Detektor `control/override.detect_external_setpoint` (Baseline-Guard: kein eigener Write → keine Adoption; Echo-Fenster 120 s; Deadband = max(0,2 K, Geräteschritt) gegen den zuletzt gesnappten `_last_written_sp`); Coordinator adoptiert per `set_override` (norm-geklemmt, Zonen-`override_policy`) und überspringt den Overwrite des Ticks; Sperre bei aktivem Geräte-Zeitplan; Option in „Manuelle Eingriffe“ (de/en); ADR-0059 §8-Nachtrag; README-Doku angepasst — die Aussage „Poise übernimmt den von Hand gestellten Wert“ stimmt jetzt auch fürs Gerät | const.py:36–41; control/override.py:206–244; coordinator.py:2636–2691; config_flow; docs/adr/ADR-0059 §8; 8 pure + 3 Integrationstests | ✅ Design und Doku stimmig, restart-sicher (Baseline nicht persistiert). **Aber: ein laufzeitbestätigter P1-Folgefehler, siehe B1.** |
| **B-neu-1** (v0.167): falscher „ohne dedizierten Test“-Satz im ADR-0046-Nachtrag | Satz durch korrekten Testverweis ersetzt (`test_p2_gates_and_defer.py::test_guard_defers_setpoint_write_under_min_off` inkl. Testinhalt) | docs/adr/ADR-0046 §8 | ✅ |
| **B-neu-2** (v0.167): Coverage-Teardown-Flake (`Lingering timer … Store._async_schedule_callback_delayed_write`) mit CI-Risiko | Autouse-Fixture `_flush_delayed_store_writes` in tests/integration/conftest.py: nach jedem Test 15 s Zeitsprung (< Tick-Intervall) + `async_block_till_done` — drained die HA-Core-Store-Timer deterministisch; Ursache im Docstring korrekt attribuiert | tests/integration/conftest.py:48–63 | ✅ lokal verifiziert: Coverage-Läufe jetzt ohne Teardown-Fehler |
| **J1** (Review): kein Release-Prozess | Zwei getaggte **Prerelease-Releases** (v0.167.0-alpha, v0.168.0-alpha) mit Changelog-Zeile | GitHub Releases | ✅ begonnen und etabliert; ausführlichere Release-Notes wären der nächste Schritt |
| Randnotiz v0.167: Keep-Alive nicht im README | Konfigurationstabelle dokumentiert den 10-min-Re-Push inkl. Danfoss-/TRVZB-Timeouts | README.md (External-temperature input) | ✅ |

## B. Fehler und Unvollständigkeiten in der Umsetzung

**B1 (P1, zur Laufzeit bewiesen) — Ein adoptierter In-Band-Hold verlängert sich selbst endlos und macht Resume/Card-X wirkungslos.**

*Ursache:* Nach einer Adoption wird die Echo-Baseline `_last_written_sp` **nicht** auf den adoptierten Wert nachgeführt (sie wird nur bei einem realen Write gesetzt, coordinator.py:2690). Liegt der adoptierte Wert im Komfortband — der Normalfall —, entspricht das Tick-Ziel ab dem Folgetick dem Gerätewert, `should_write` ist False, es erfolgt **nie wieder ein Write**, die Baseline bleibt für immer stale. Damit meldet `detect_external_setpoint` **in jedem Tick erneut** eine „Änderung“ (Gerätewert ≠ alte Baseline), und `set_override` berechnet bei jedem Aufruf die Expiry neu von `utcnow()` (coordinator.py:552–564).

*Laufzeit-Beweis (PoC gegen `e32c1ac`, Aufbau identisch zum mitgelieferten `test_setpoint_adoption.py`, nur um einen zweiten/dritten Tick erweitert):*
1. `override_expires_at` wandert pro Tick um die verstrichene Zeit nach hinten (gemessen: +1,1 s bei 1,1 s Wall-Abstand) → **die Rückkehr-Policy (schedule/timer) ist für adoptierte Holds faktisch außer Kraft — der Hold endet nie von selbst.**
2. Nach `set_override(None)` (Service `poise.resume_schedule` / Card-X) ist der Hold **einen Tick später wieder da** (Override erneut 23.0) → verlorene Nutzerkontrolle: Der dokumentierte Rückweg zur Automatik funktioniert für geräteseitig adoptierte Holds nicht.
3. Nebenwirkungen je Tick: ein L1-Statistik-Eintrag (`_record_override_stat` — die rolling-50-Liste wird mit Duplikaten geflutet und für ADR-0060 unbrauchbar) und `_dirty = True` → **ein Store-Save pro Minute** (unnötige Flash-/IO-Last).

*Einordnung:* Genau die Fehlerklasse „Sollwert-/Automatik-Verhalten dreht durch“, die das Review als Community-Abbruchgrund Nr. 1 identifizierte — hier in der invertierten Form (der Nutzer-Hold hebelt die Automatik dauerhaft aus). Die mitgelieferten Tests decken nur den ersten Tick ab und können den Folgetick-Effekt prinzipbedingt nicht sehen. Out-of-Band-Adoptionen sind gesund (der geklemmte Wert wird geschrieben → Baseline zieht nach).

*Abhilfe (klein):* Nach erfolgreicher Adoption `self._last_written_sp = snap_to_step(<adoptierter Wert>, step)` und `self._last_sp_write_ts = now` setzen — der Gerätewert ist ab jetzt die bekannte Baseline; Expiry bleibt stehen, Resume wirkt, keine Tick-Saves. **Akzeptanzkriterium:** Regressionstest über ≥ 2 Ticks: Expiry unverändert zwischen Tick 1 und 2; nach `resume_schedule` + 1 Tick bleibt `_override is None`; Statistikliste wächst nicht.

**B2 (P3, gleiche Wurzel) — Safe-State-Writes führen die Baseline nicht nach.** `_write_unavailable_safe_state` und der Frost-Rescue-Pfad schreiben Sollwerte am normalen Write-Pfad vorbei und aktualisieren `_last_written_sp` nicht. Nach einer Sensor-Recovery kann so Poises **eigener** Safe-State-Sollwert (Floor) als „Nutzerintent“ adoptiert werden (Hold an der Bandunterkante, `override_clamped`). Abhilfe: Baseline auch dort setzen — oder dort auf `None` zurücksetzen (Baseline-Guard unterdrückt Adoption bis zum nächsten regulären Write).

**B3 (P3, gleiche Wurzel) — Lost-Command-Fall wird als Nutzerintent gelesen.** Geht Poises Write verloren (Gerät behält den alten Wert — Community-Cluster 8: Zigbee-Timeouts, TRVZB-Lockups), zeigt das Gerät nach 120 s einen Wert ≠ Baseline → der **eigene alte Sollwert** wird als Hold adoptiert, statt (wie vor v0.168) im nächsten Tick re-asserted zu werden. Die implizite Resend-Robustheit — im Review als Stärke hervorgehoben — ist damit genau für die flaky Geräte geschwächt, denen die Adoption dienen soll. Abhilfe: Baseline-Historie über die letzten zwei Writes (device_sp ≈ vorletzter Write → re-assert statt adopt).

*B1–B3 teilen dieselbe Wurzel (Ein-Wert-Baseline ohne Nachführung) und lassen sich in einem Wurf beheben.*

**B4 (dritte Runde offen) — `review_verification_report.md` liegt weiterhin an der Repo-Wurzel** (Alt-Zyklus F1–F18). Verschieben nach `docs/reviews/` oder löschen.

**Randnotiz:** Adoption ist nicht auf `window_open`/`frozen` gegated — vertretbar, weil die Präzedenzkette (Fenster/Frost > Override) die Aktuierung schützt; ein während der Safety-Lage gedrehter Hold entsteht aber kommentarlos im Hintergrund und wird erst nach deren Ende wirksam (mit dem `override_expires_at`-Sensor immerhin sichtbar).

## C. Weiterhin offen (unverändert)

| Punkt | Status |
| --- | --- |
| **P1-3** Frontend/Backend-Vertragstest (~100 Card-Attribute) | offen |
| **P2-5** Harness: Plant ≙ EKF-Prior; `replay.py`-„same code path“; README „production-identical“ | offen |
| **J9** Troubleshooting-Guide + Gerätekompatibilitätsmatrix | offen |
| **J12** Feldtests über Geräteklassen, Trace-Sammlung, CA-Berichte | offen |
| P3-Reste | unverändert: PI-Shadow-dt/acc, Ratelimit „pro Aufruf“, `identified` richtungsagnostisch, FBH-4-h-Preheat-Horizont, virtuelle-MRT-Kopplung 0,08, CO₂-Karte ohne Backend, Card-Editor nur Englisch, i18n-Paritätstest, mypy-CI-Blindstelle (22 lokale Fehler), Registertabelle ohne Wirkung-Spalte |

## D. Gesamtbewertung

v0.168.0 arbeitet die v0.167-Nachprüfung vollständig ab (B-neu-1, B-neu-2 — der Flake-Fix ist genau die empfohlene Lösung und lokal verifiziert), etabliert echte Prerelease-Releases (J1) und liefert mit **P1-4a das wichtigste verbleibende Review-Feature**: Architektur (pure Detektor + Glue-Adoption über den regulären Hold-Lebenszyklus), Guards, Opt-out, Übersetzungen, ADR und README sind stimmig und auf dem Qualitätsniveau der vorherigen Fixes.

Die Umsetzung hat jedoch **einen laufzeitbestätigten P1-Folgefehler**: Für den Normalfall (adoptierter Wert im Komfortband) wird die Echo-Baseline nie nachgeführt, wodurch sich der Hold jeden Tick selbst verlängert, `poise.resume_schedule`/Card-X binnen ≤ 60 s rückgängig gemacht werden und pro Tick ein Store-Save anfällt. Der Kernnutzen des Features — „Hold mit definierter Rückkehr zur Automatik“ — ist damit in v0.168.0 nicht gegeben; die Rückkehr funktioniert nur für band-geklemmte Adoptionen. **Empfehlung: v0.168.0-alpha nicht als Teststand empfehlen; Fix (Baseline nach Adoption nachführen, eine Zeile + Zwei-Tick-Regressionstest) als v0.168.1/v0.169 nachschieben** und dabei B2/B3 (Safe-State-Baseline, Zwei-Write-Historie gegen Lost-Command-Adoption) gleich mit erledigen.

Danach ist P1-4 vollständig, und die Beta-Blocker-Liste des Reviews reduziert sich auf: Feldnachweis/Gerätematrix (J9/J12), Frontend-Vertragstest (P1-3) und die Harness-/Doku-Ehrlichkeit (P2-5).

---

*Nachprüfung erstellt am 13.07.2026 gegen `e32c1ac`; lokale Läufe mit Python 3.13.12, HA 2024.12.5. Methodik: vollständiger `git diff 88d4d0a..e32c1ac`, Ausführung aller Suiten (Coverage isoliert), Verifikation der Guards am Code und ein eigener Zwei-Tick-PoC auf Basis des mitgelieferten Adoptionstests (Expiry-Drift, Resume-Undo und Statistik-Wachstum gemessen).*
