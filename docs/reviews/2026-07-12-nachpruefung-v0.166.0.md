# Nachprüfung: v0.166.0 gegen das Review vom 12.07.2026

*Geprüfter Stand: Commit `d9dcc91` (main, v0.166.0, 12.07.2026 abends) gegen das Review zu `61f213e` (v0.163.0, `2026-07-12-review-v0.163.0.md`).*

## Prüfstand

| Prüfung | Ergebnis |
| --- | --- |
| CI | Lauf **#1139 auf `d9dcc91`: grün** (alle Jobs inkl. Glue-Gate und Card-Bundle-Guard); die fünf Zwischen-Uploads #1134–#1138 waren rot (Upload-Snapshots) |
| `ruff check` / `format` | ✅ sauber (230 Dateien) |
| `mypy` (strict, lokal mit HA 2024.12.5) | ⚠️ **22 Fehler** (v0.163: 21; +1 durch den neuen `HVACMode`-Import) — die CI-Blindstelle P3-17 (mypy ohne installiertes HA) besteht unverändert |
| Pure-Core | ✅ **747 Tests grün** (v0.163: 742; +5), Coverage 97,87 % |
| HA-Integration | ✅ **173 Tests grün** (v0.163: 163; +10 Review-Regressionstests); Glue-Coverage lokal **94,63 % < 95-%-Gate** (v0.163: 94,70 %) — CI grün, Gate bleibt umgebungsabhängig (P3-17). Einmaliger, nicht reproduzierbarer Collection-ERROR in `test_config_flow` unter Coverage (2 Wiederholungsläufe grün; Flake-Verdacht, niedrige Konfidenz). |
| Releases/Tags | Weiterhin **keine** (J1 offen); Entwicklung weiter per „Add files via upload“ |

## A. Erledigt (umgesetzt und mit Tests belegt)

| Review-Befund | Umsetzung v0.164–0.166 | Beleg |
| --- | --- | --- |
| **P1-1** Fenster-schlägt-Override ungetestet | Zwei Resolvertests + Integrationstest ergänzt — exakt die geforderte Mutationsabdeckung | tests/test_tick_resolve.py (`test_write_target_window_beats_active_override`, `…_out_of_band_override`); tests/integration/test_review_write_floor.py (`test_p1_1_window_beats_active_override`) |
| **P2-1** Schimmelfloor heizt bei offenem Fenster bis 24 °C | Schimmel-Anteil des Floors wird für die ersten 30 min der Fensterepisode unterdrückt (`WINDOW_MOULD_SUPPRESS_S=1800`), Frostfloor nie; Diagnose-Attribut `mould_floor` zeigt weiter den echten Wert | const.py:21–24; coordinator.py:2155–2160, 2255–2270, 3179; Test `test_p2_1_mould_floor_suppressed_under_fresh_window` |
| **P2-6** 30-Tick-Save ungetestet | Test: genau ein periodischer Save je `EKF_SAVE_EVERY_TICKS` + Dirty-Flush im Folge-Tick | tests/integration/test_review_persistence.py |
| **P2-7** Preset/Modus/Enabled-Restore ohne Assertion | Reload-Test assertet alle drei gemeinsam | tests/integration/test_review_persistence.py |
| **P2-8** Heizausfall nur englische Notification | Vollständig auf übersetztes Repair-Issue `heating_failure` umgestellt (de/en, Auto-Clear); Notification-Code inkl. Unload-Dismiss entfernt | coordinator.py:1473–1485; strings.json/translations |
| **P2-9** 18 Entities default-enabled | 13 Diagnose-Sensoren `entity_registry_enabled_default=False`; sichtbar bleiben climate, Bypass-Switch, operative Temperatur, Konfidenz, Lernphase (= 5) — deckungsgleich mit der Review-Empfehlung; mit Test | sensor.py; switch.py:44–46; tests/integration/test_entity_defaults.py |
| **P2-10 (teilw.)** README-Drift | Entitätenliste komplett neu geschrieben (Sensoren vs. Climate-Attribute explizit, inkl. „kein `sensor.<raum>_pmv`“-Hinweis); „35+ ADRs“→„60+“; Effizienzreport von Roadmap in die Shadow-Sektion verschoben | README.md:174–186 |
| **P2-11 (Kern)** ADR-Wirkungsdimension | `**Wirkung:**`-Feld in allen 62 ADRs, Vokabular in ADR-0000 + Register definiert, Lint erzwingt Existenz + Vokabular; Stichprobe der kritischen Zuordnungen korrekt (0050/0051/0052/0058 = Live-A; 0033/0036/0037/0044/0045/0055 = Live-D; 0046 = teilw.); ADR-0015-Nachtrag zur 0036-Revision ergänzt | docs/adr/*, tests/test_adr_status_lint.py |
| **P2-12** Repair-Issue verweist auf falschen Ort | Text nennt jetzt „Reconfigure → Anlagen-Anbindung (Mehrzonen)“ und den wörtlichen Feldnamen (de+en) | strings.json/translations `frost_zone_not_boiler` |
| **P3-1** Floor nicht auf `min_temp` geklemmt | `device_min` als SAFETY-Floor im Constraint-Solver, `_device_min()` im Coordinator; pure + Integrationstest | tick_resolve.py:118–128; coordinator.py:1254–1266; `test_p3_1_device_min_temp_is_a_write_floor` |
| **P3-18** Aktor-Recovery/Feuchteausfall ungetestet | Tests: Write-Wiederaufnahme nach Aktor-Rückkehr; `mould_protection_inactive` bei RH-Ausfall inkl. Clear | tests/integration/test_review_degradation.py |
| **P3-19** quality_scale veraltet | `action-setup`/`docs-actions` auf `done` mit `poise.resume_schedule`; „63 modules“ entfernt | quality_scale.yaml |
| **P1-2 (Code)** Fahrenheit | °F-Gate: `async_step_user` und `async_step_reconfigure` brechen auf `US_CUSTOMARY_SYSTEM` mit übersetztem Abort ab | config_flow.py:840–843, 911–914 |
| **P2-4 (Code)** heat_cool-only | Gate in Room- und Reconfigure-Step (`_heat_cool_only`, HVACMode-basiert), übersetzter Fehlertext | config_flow.py:781–797, 862–866, 956–959 |
| **Bonus: ADR-0061** (nicht im Review gefordert) | Adaptive Kühlkante nur noch bei `occupied=False` — norm-korrekt begründet (EN-16798-adaptiv gilt nur free-running; das Review hatte genau diese Einschränkung der Normkonformität moniert), entmaskiert den `comfort_weight`-Regler; mit Test und README-Anpassung | comfort/dual_setpoint.py:100–109; docs/adr/ADR-0061; `test_adaptive_cool_edge_gated_on_occupancy` |

## B. Fehler und Unvollständigkeiten in der Umsetzung

**B1 (gravierendster Befund) — P2-3 „atomarer Mode+Setpoint-Write“: dokumentiert, aber nicht implementiert; die im ADR benannten Tests existieren nicht.**
Der ADR-0046-Nachtrag §8 (v0.166.0) behauptet: *„(a) `actuator.service_call_for` trägt einen konditionierenden Modus atomar in denselben `set_temperature`-Call … Pure Abdeckung `tests/test_actuator.py` (Ride-along + Auslassung), Guard-Defer in `tests/integration/test_compressor_guard.py`“*. Tatsächlich sind auf `d9dcc91`:
- `actuator.py` **unverändert** — `service_call_for` sendet weiterhin nur `{entity_id, temperature}`; das `hvac_mode`-Feld des Commands wird nie übertragen;
- `contracts.py` unverändert;
- `tests/test_actuator.py` und `tests/integration/test_compressor_guard.py` **unverändert** — die beiden im ADR benannten Testabdeckungen existieren nicht (verifiziert per `git diff 61f213e d9dcc91`);
- der neue Coordinator-Kommentar *„so service_call_for can switch mode+setpoint atomically“* (coordinator.py:2644–2646) ist damit falsch.
Real implementiert ist nur Teil (b): das Write-Gate `and not _mode_nudge_blocked` (coordinator.py:2626–2631) schiebt den Sollwert-Write des neuen Regimes auf, solange der Verdichterschutz den Moduswechsel hält — das ist korrekt und behebt den Guard-Fall, ist aber **ungetestet**. Der zweite P2-3-Restfall (Standalone-Nudge schlägt fehl → Setpoint des neuen Regimes landet im alten Modus) besteht unverändert, und der Nudge bleibt ein separater Call vor dem Write.
**Bewertung:** funktional eine Verbesserung, aber der ADR-Nachtrag dokumentiert einen Stand, der nicht ausgeliefert wurde — exakt die ADR↔Code-Drift-Klasse, die das Review unter P2-11 kritisierte, hier frisch erzeugt. **Abhilfe:** entweder (a) nachziehen (`service_call_for` um konditionierende Modi heat/cool/dry erweitern, Standalone-Nudge im Write-Fall entfallen lassen, die zwei benannten Tests real anlegen) oder den Nachtrag auf den tatsächlichen Stand kürzen.

**B2 — Beide neuen Flow-Gates sind ungetestet.** Für das °F-Gate und das heat_cool-Gate existiert kein einziger Test (`grep -r imperial|US_CUSTOMARY|heat_cool_only tests/`: 0 Treffer). Die Gate-Zeilen sind lokal ungedeckt (config_flow.py 96 %, 8 missed lines) und drücken das Glue-Coverage-Gate. Das widerspricht der sonst konsequent gelebten Regel „jeder Fix mit Regressionstest“, die bei allen anderen Punkten (P1-1, P2-1, P2-6, P2-7, P2-9, P3-1, P3-18) eingehalten wurde. Restlücke P2-4: Ist der Aktor zur Flow-Zeit `unavailable` (keine `hvac_modes`), passiert das Gate (im Docstring dokumentiert); zur Laufzeit gibt es kein Fallnetz.

**B3 — P2-11 nur zur Hälfte:** Die Registertabelle hat **keine** Wirkung-Spalte, der Lint prüft nur Header-Existenz + Vokabular (kein Header↔Register-Abgleich, wie es ihn für den Status gibt). Vor allem: Die Register-Prosa („Umsetzungsstand“) behauptet weiterhin, 0050/0051/0052 seien eine *„Shadow-Messschicht (… keine Writes …)“* — im direkten Widerspruch zu den neuen `Wirkung: Live-A`-Headern derselben ADRs. Der Widerspruch, den das Review monierte, steht jetzt innerhalb desselben Dokuments.

**B4 — `review_verification_report.md` liegt an der Repo-Wurzel** und behandelt einen älteren Review-Zyklus (F1–F18; diese Fixes waren in v0.163.0 bereits enthalten). Am jetzigen Ort erweckt die Datei den Eindruck, das aktuelle Review sei abgearbeitet. Gehört nach `docs/reviews/` (mit Datums-/Zyklus-Kennzeichnung) oder gelöscht.

**B5 — Kleinere Randfälle der P2-1-Umsetzung:** `_window_open_since` ist monotonic und wird nicht persistiert — ein HA-Neustart bei offenem Fenster startet die 30-min-Unterdrückung neu (Wirkung: Schimmelfloor greift nach Neustart bis zu 30 min später; energetisch konservativ, Schutzlücke minimal). Kein Fix zwingend, eine Kommentarzeile wäre ehrlich.

**B6 — Unverändert offene Gate-/Typing-Beobachtungen (P3-17):** Glue-Coverage-Gate lokal erneut knapp rot (94,63 %), mypy-strict-Anspruch für Glue weiterhin nur ohne installiertes HA haltbar (jetzt 22 lokale Fehler).

## C. Nicht adressiert (aus dem „Jetzt“-Block des Reviews)

| Punkt | Status v0.166.0 |
| --- | --- |
| **P1-3** Frontend/Backend-Vertragstest (~100 Card-Attribute) | fehlt — kein neuer Test, Card-Tests weiter gegen synthetische Fixtures |
| **P1-4a** Geräteseitige Sollwertänderung (TRV-Rad) wird überschrieben | unverändert; README behauptet weiterhin uneingeschränkt „Poise übernimmt den von Hand gestellten Wert“ |
| **P1-4b** Override-Sichtbarkeit ohne Poise-Card (`override_expires_at` als Sensor, Erst-Override-Hinweis) | fehlt |
| **P2-2** Keep-Alive des External-Temp-Feeds (Danfoss-/TRVZB-Timeout) | unverändert (`_last_fed`-Deadband ohne Zeitkomponente, coordinator.py:2670–2680) |
| **P2-5** Harness: Plant ≙ EKF-Prior, `replay.py`-„same code path“-Behauptung | unverändert; auch die README-Behauptung „production-identical simulation harness“ steht noch |
| **J1** Releases/Tags/Changelog | weiterhin keine (Releases leer; sechs Snapshot-Uploads mit fünf roten Zwischen-CI-Läufen am 12.07.) |
| **J9** Troubleshooting-Guide + Gerätekompatibilitätsmatrix | fehlt (docs/ enthält weiter nur ADRs + Reviews) |
| P3-Reste (PI-dt/acc, Ratelimit pro Aufruf, `identified` richtungsagnostisch, FBH-4-h-Horizont, virtuelle-MRT-Kopplung 0,08, CO₂-Karte, Card-Editor-Lokalisierung, i18n-Paritätstest, HA-Minimum ungeprüft) | unverändert — waren überwiegend dem „Danach“-Block zugeordnet, hier nur der Vollständigkeit halber |

## D. Gesamtbewertung

Von den 19 im „Jetzt“-Block priorisierten Punkten sind **11 substanziell umgesetzt**, davon 9 mit echten Regressionstests — Tempo und Testdisziplin sind bemerkenswert, und die Zuordnung der neuen Wirkung-Header deckt sich exakt mit dem Audit des Reviews. Die kritischen Testlücken des Reviews (P1-1, P2-6, P2-7) sind geschlossen, der physikalisch schwerwiegendste Regelungs-Befund (P2-1) sauber gelöst, die Entitäten-Flut (P2-9) genau wie empfohlen reduziert.

Dem stehen drei Mängel gegenüber: (1) der **ADR-0046-Nachtrag dokumentiert eine nicht existierende Implementierung samt zweier nicht existierender Tests** (B1) — vor dem nächsten Upload korrigieren, sonst entwertet es das frisch eingeführte Wirkung-Vokabular; (2) die beiden neuen **Flow-Gates sind ungetestet** (B2); (3) der **größte Anwenderschmerz (P1-4: Geräte-Sollwerte, Override-Sichtbarkeit) und die größte Gerätekompatibilitäts-Lücke (P2-2 Keep-Alive) sind unbearbeitet**, ebenso der Release-Prozess (J1) — damit bleiben die Beta-Blocker 1–3 des Reviews bestehen.

**Empfohlene Reihenfolge für v0.167:** B1 auflösen (Code nachziehen *oder* ADR korrigieren) → Tests für °F-/heat_cool-Gate und Guard-Defer → P2-2 Keep-Alive (klein, hoher Feldnutzen) → P1-4b `override_expires_at`-Sensor (klein) → J1 erstes getaggtes Release → P1-4a und P1-3 als nächste größere Blöcke.

---

*Nachprüfung erstellt am 12.07.2026 gegen `d9dcc91`; lokale Läufe mit Python 3.13.12, HA 2024.12.5, Node 22.22.2. Methodik: vollständiger `git diff 61f213e..d9dcc91`, Ausführung aller Suiten, Stichproben-Verifikation jeder Behauptung im Code (u. a. `actuator.py`-Stand, Test-Existenz per Diff, Wirkung-Token per Header-Grep).*
