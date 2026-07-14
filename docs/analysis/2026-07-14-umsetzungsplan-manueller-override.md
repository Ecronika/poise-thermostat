# Umsetzungsplan: Manuelle Gerätebedienung zuverlässig adoptieren — ohne Rückschritte

**Datum:** 2026-07-14 ·
**Basis:** Fehleranalyse `2026-07-14-manueller-override-split-klima.md` (Befunde B1–B10) ·
**Zweck:** Vor jeder Code-Änderung festlegen, (a) welche Änderungen an der Basis **zwingend** notwendig sind und in welchem Umfang, (b) wie der heutige Pfad aussieht, (c) was sich genau ändert und (d) wie verifiziert wird, dass **keine bestehende Funktion bricht**.

---

## 0. Vorgehensprinzip: Verifikation vor Veränderung

1. **Phase 0 zuerst:** Charakterisierungstests frieren das heutige Verhalten ein, *bevor* Produktivcode angefasst wird. Fehlverhalten wird als `xfail` markiert (mit Befund-Referenz), korrektes Verhalten als regulärer Test. Der spätere Fix darf **ausschließlich** `xfail→pass`-Übergänge erzeugen; jeder andere rote Test ist per Definition ein Rückschritt und blockiert den Merge.
2. **Kleinste zwingende Schnitte:** Jeder Baustein (K1–K4) ist einzeln mergebar und einzeln rückrollbar. Kein Baustein ändert pure Funktionen, deren Tests er nicht selbst erweitert.
3. **Bestehende Gates bleiben das Fundament:** CI (`.github/workflows/ci.yml`) erzwingt ruff, `mypy --strict`, Pure-Tests ≥ 85 % Coverage, Glue-Integrationstests ≥ 95 % Coverage, hassfest/HACS, Card-Build. Jeder Baustein läuft zusätzlich gegen die unten benannten gezielten Suiten.

**Zwingend notwendig** (beheben die zwei verifizierten Hauptursachen des Bugreports + machen den Fix im Feld nachweisbar):

| Baustein | Behebt | Umfang |
|---|---|---|
| K1 | B1/B3 — Echo-Fenster verschluckt Nutzer-Sollwertänderung dauerhaft | S (~15–25 Zeilen Produktivcode) |
| K2 | B2 — kein Adoptionspfad für `hvac_mode`; inkl. Kompressor-Guard-Ordering | M (~150–250 Zeilen) |
| K3 | B10 (teilweise) — Nicht-Adoption ist unsichtbar; Feld-Verifikation unmöglich | S |
| K4 | B10 — README/Options-Label versprechen mehr als der Code hält | XS (nur Doku) |

**Bewusst zurückgestellt** (empfohlen, aber nicht zwingend — Begründung in §7): Context-Attribution (V2), Deadband-Symmetrie (B4/V4), Neustart-Baseline (B5/V5), `heat_cool`-Unterstützung (B7), Fan/Swing (B8), Card-Chip, `sched_active`-Gate-Änderungen (B6).

---

## 1. Schutzgüter: Was auf keinen Fall brechen darf

Jede Zeile dieser Tabelle ist eine historisch begründete Funktion mit existierendem Pinning-Test. Diese Tests werden von K1–K4 **nicht verändert** — sie sind die Regressionswand.

| # | Invariante | Herkunft (warum sie existiert) | Pinning-Test (existiert) |
|---|---|---|---|
| I1 | Ein Echo des eigenen Writes wird nie als Hold adoptiert | Grundfunktion P1-4a | `test_adopt.py::test_echo_of_our_own_write_is_ignored` |
| I2 | Sub-Deadband-Requantisierung (Gerät rundet unseren Write) wird nie adoptiert | Zigbee-TRVs mit grobem Step | `test_adopt.py::test_sub_deadband_requantisation_is_ignored` |
| I3 | Ein stabil „gesettelter" Geräte-Offset wird nie (re-)adoptiert; Card-X/`resume_schedule` springt nicht zurück auf „Manuell" | Live-Bug „card-X springs back to manual"; Review B1 v0.168.0 | `test_adopt.py::test_stable_device_offset_is_not_adopted`, `test_setpoint_adoption.py::test_stable_device_offset_is_not_re_adopted`, `::test_adopted_hold_is_stable_across_ticks` |
| I4 | Ohne Baseline (Kaltstart) keine False-Adoption | Cold-Start-Schutz | `test_adopt.py::test_no_baseline_is_ignored`, `::test_first_observation_without_prev_still_gated_by_baseline` |
| I5 | Adoptierte Werte werden in die Norm-Hülle geklemmt (`sanitize_override`, `coordinator.py:551-555`) | C2-Trust-Boundary | `test_tick_resolve.py::test_write_target_override_clamped_into_band_and_norm` |
| I6 | Fenster-offen/Frost schlägt jeden aktiven Override | Solver-Präzedenz ADR-0035 | `test_tick_resolve.py::test_write_target_window_beats_active_override`, `::test_write_target_window_beats_out_of_band_override`, `tests/integration/test_window_cool_safety.py` |
| I7 | Opt-out `adopt_external_setpoint=False` wird respektiert | Options-Vertrag | `test_setpoint_adoption.py::test_opt_out_disables_adoption` |
| I8 | Hold-Lebenszyklus: Expiry bei Set-Zeit angekündigt; Ende an Schaltpunkt/Timer/Presence; Boost-Restore | ADR-0059 §1–§4, VT#1961-Guard | `tests/integration/test_override_lifecycle.py`, `test_override_mode.py`, `tests/test_override.py` |
| I9 | Mode-Nudge holt ein abgedriftetes Gerät zurück (off/auto/fremder Modus), `off`→`heat`-Mapping als Frostschutz, Idle-Park inkl. `fan_only` | Review V1/H1, ADR-0050/0053 | `test_tick_resolve.py::test_needs_mode_nudge_on_drift`, `::test_resolve_desired_mode`, `::test_idle_park*` |
| I10 | Kompressor-Guard: min-off/mode-hold blockt Starts und cool↔dry-Flips; Safety (Fenster/Frost/Override) bypassed ihn | ADR-0046 (F11-Nachtrag) | `tests/integration/test_compressor_guard.py` |
| I11 | Selbstregelnde Geräte werden max. 1×/Regulierungsperiode genudgt | ADR-0052 §4 | `tests/integration/test_regulation_throttle.py` |
| I12 | Kein Write-Sturm bei nicht verfügbarem Aktor; Safe-State-Verhalten | Review B2 | `tests/integration/test_actuator_unavailable_write_storm.py` |

Zusätzliche Regressionswand auf Systemebene: die Closed-Loop-/Replay-Harness (`tests/harness/`, ADR-0011/0032) und die Determinismus-Referenzfälle (ADR-0014). K1–K4 ändern keine Regelmathematik (Solver, PI/TPI/MPC, Comfort) — die Referenzfälle müssen **bitidentisch** bleiben; jede Abweichung dort ist ein sofortiges Stoppsignal.

---

## 2. Phase 0 — Charakterisierungstests (PR-0, nur Tests, kein Produktivcode)

Neue Tests, die den Ist-Zustand der zu ändernden Pfade dokumentieren. `xfail(strict=True)` mit Befund-ID, damit ein Fix sie *beweisbar* umdreht (strict-xfail schlägt fehl, sobald der Test unerwartet grün wird — der Fix muss den Marker entfernen):

| ID | Szenario (Glue-Test, `tests/integration/`) | Heute | Ziel nach Fix |
|---|---|---|---|
| C1 | FAST_AIR-Split-Klima: Poise-Write bei t0, IR-Sollwertänderung bei t0+30 s, Ticks t0+60…300 | `xfail`: keine Adoption, Revert bei t0+300 (B1) | Adoption spätestens beim ersten Tick ≥ t0+120 |
| C2 | TRV (ungedrosselt): Write t0, Nutzeränderung t0+30, Tick t0+60 | `xfail`: Revert binnen ≤ 60 s (B3) | keine Rückschreibung; Adoption bei t0+120 |
| C3 | Zweite Nutzerkorrektur < 120 s nach erfolgreicher Adoption | `xfail`: verschluckt (Analyse §3.3 „Verkettung") | zweite Korrektur wird Hold-Wert |
| C4 | IR-Modusänderung cool→off / cool→fan_only an kühlender Split-Klima | `xfail`: Rück-Nudge binnen Sekunden, kein Override (B2) | Mode-Hold, Rückkehr per Policy |
| C5 | Nutzer-Stopp per IR, Gerät lief (Kompressor an) | `xfail`: sofortiger Wiederstart trotz min-off (T-4) | Guard hält Re-Nudge ≥ min-off |
| C6 | Slow-Poll-Echo: Gerät meldet nach dem Write > 120 s lang den **Vor-Write-Wert** | pass (wird nicht adoptiert) — bleibt pass | unverändert (Schutz von I1) |
| C7 | Tick-Jitter: „120-s-Tick" feuert bei 119.x s | `xfail`: Poisoning (B1-Randfall) | Adoption beim Folge-Tick |

Wichtiger Befund für die Risikobewertung: **Kein einziger bestehender Test assertiert das heutige Fehlverhalten** (Revert der Nutzeränderung). `test_change_within_echo_window_is_not_adopted` prüft nur „keine Adoption *im* Fenster-Tick" — das bleibt auch nach K1 korrekt. Es muss also kein bestehender Test gelockert oder gelöscht werden; die Fixes sind rein additiv gegenüber der Testbasis.

---

## 3. K1 — Kill-Zone des Echo-Fensters schließen (zwingend)

### Ist-Pfad (heute)

```
Tick (60 s / Event-Refresh)                          coordinator.py
  actual_sp = Attribut "temperature" des Aktors      :2619
  _adopted = detect_external_setpoint(
      device_sp, last_written_sp, last_write_ts,
      echo_window=120 s, deadband=max(0.2, step),
      prev_device_sp)                                :2653-2667
      ├─ Fenster aktiv (< 120 s seit Write) → None   override.py:250-251
      ├─ |Δ zu last_written| < deadband     → None   override.py:252-253
      └─ device_sp == prev_device_sp        → None   override.py:254-257  (Stable-Guard)
  _prev_device_sp = actual_sp   ← IMMER, auch wenn nur
                                  das Fenster unterdrückt hat   :2672   ← Defekt
  kein _adopted → Write-Pfad überschreibt Nutzerwert,
  sobald should_write + Throttle es erlauben          :2686-2718
```

Der unbedingte `_prev_device_sp`-Stempel macht aus der *temporären* Fenster-Unterdrückung eine *permanente* Stable-Guard-Blockade („Poisoning", Befund B1).

### Änderung (Soll) — minimal-invasiv

**Eine einzige Verhaltensänderung:** `_prev_device_sp` wird **nicht** aktualisiert, solange das Echo-Fenster offen ist (d. h. genau dann, wenn die Adoption ausschließlich wegen des Fensters unterdrückt wird). Der Vergleichswert bleibt auf der letzten Beobachtung **vor** dem eigenen Write eingefroren:

```
if last_sp_write_ts is None or (now - last_sp_write_ts) >= SETPOINT_ADOPT_ECHO_WINDOW_S:
    self._prev_device_sp = actual_sp        # wie bisher
# sonst: einfrieren — eine In-Fenster-Beobachtung darf den Bewegungs-Guard nicht füttern
```

Wirkungsnachweis an den vier maßgeblichen Szenarien:

| Szenario | Ablauf mit K1 | Ergebnis |
|---|---|---|
| **Bug (C1/C2):** Write 21 bei t0 (prev=Vor-Write-Wert 24), Nutzer 26 bei t0+30 | t0+60: Fenster → keine Adoption, **prev bleibt 24**. t0+120: Fenster zu; Δ zu last_written=5 ✓; „bewegt" (26≠24) ✓ → **Adoption** | Bug behoben; max. Latenz ≈ Fensterlänge |
| **I3 (Card-X-Respring):** Hold 23 beendet, Poise schreibt 20, Gerät bleibt bei 23 | prev war vor dem Write 23; t0+120: device 23 == prev 23 → Stable-Guard → keine Adoption | I3 intakt |
| **I1/C6 (Slow-Poll-Echo):** Gerät meldet > 120 s den Vor-Write-Wert 24 | prev eingefroren auf 24; nach Fensterablauf: device 24 == prev 24 → Stable-Guard | Sogar besser als heute (heute schützt nur der Zufall, dass der Wert „stabil" wirkt) |
| **I2 (Requant):** Write 20, Gerät settelt 20.5 (step 1.0) | Δ zu last_written = 0.5 < deadband(1.0) → unterdrückt, unabhängig von prev | I2 intakt |

Zusätzlich in K1 (severabel, gleiche Stelle): der H-1-Listener-Filter (`coordinator.py:1064-1070`) lässt künftig auch reine `temperature`-Attributänderungen **des Aktors** als Refresh-Trigger durch. Heute wird eine IR-Sollwertänderung ohne `hvac_action`-Flip bis zu 60 s spät gesehen; mit eingefrorenem prev ist eine frühe In-Fenster-Beobachtung kein Risiko mehr, sondern verkürzt nur die Adoption-Latenz. (Debounce von `async_request_refresh` begrenzt die Tick-Rate; Verifikation: kein Tick-Budget-Überlauf, `test_tick_budget`-Suite.)

**Bekannte, akzeptierte Restlücke (dokumentieren, nicht lösen):** Stellt der Nutzer *innerhalb* des Fensters exakt den Vor-Write-Wert wieder her, ist das von einem Poll-Lag-Echo prinzipiell ununterscheidbar → wird weiterhin revertiert. Ebenso bleibt die In-Fenster-*Sofort*-Adoption (Drei-Werte-Logik über `pre_write_sp`) bewusst außen vor: sie brächte Latenzgewinn ≤ 120 s, öffnet aber die I3-Klasse für Geräte mit verdeckten internen Clamps. Falls später gewünscht → eigener Baustein mit eigener Risikoanalyse (§7).

### Verifikation K1 (Funktionslücken-Nachweis)

1. **Unverändert grün (Regressionswand):** alle 11 Pure-Tests `tests/test_adopt.py` (Detektor-Signatur unverändert), alle 5 Glue-Tests `test_setpoint_adoption.py` — insbesondere I3-Tests (`test_stable_device_offset_is_not_re_adopted` sät `_prev_device_sp` explizit; der Pfad ist identisch, da dort das Fenster bereits abgelaufen ist) und `test_change_within_echo_window_is_not_adopted` (K1 adoptiert weiterhin nichts *im* Fenster).
2. **Umgedreht (xfail→pass):** C1, C2, C3, C7.
3. **Neu (Absicherung der Änderung selbst):** Glue-Test „prev bleibt während des Fensters eingefroren und wird beim ersten Post-Fenster-Tick nachgeführt"; C6 als regulärer Test.
4. **Suiten:** `pytest tests/test_adopt.py tests/test_tick_resolve.py tests/integration/test_setpoint_adoption.py tests/integration/test_regulation_throttle.py tests/integration/test_actuator_unavailable_write_storm.py` + volle CI-Matrix.
5. **Systemebene:** Determinismus-/Closed-Loop-Referenzfälle bitidentisch (K1 ändert keine Regelgröße, nur das Adoption-Gate).

---

## 4. K2 — Adoptionspfad für `hvac_mode` + Guard-Ordering (zwingend)

### Ist-Pfad (heute)

```
Aktor-State-Change (Modus = State) → Listener :1042-1075 → Refresh in Sekunden
Tick:
  desired_hvac = resolve_desired_mode(final_mode, …)        tick_resolve.py:253-282
  needs_mode_nudge(current, desired)  = current != desired  tick_resolve.py:248-250
  guard_block_reason(...)  ← wertet PRE-observe-Lifecycle aus :2583-2597
      is_on=True (Stopp noch nicht verbucht) → min_off_remaining=0 → blockt nie
  → set_hvac_mode(desired)                                   :2601-2608
  _lifecycle.observe()  ← erst NACH dem Nudge                :2947-2957
  is_external_override (multi/lifecycle.py:173-182)          dormant, rein Diagnose
```

Jede geräteseitige Modusänderung wird binnen Sekunden zurückkommandiert; ein Nutzer-Stopp führt zum sofortigen Kompressor-Wiederstart.

### Änderung (Soll) — minimal zwingender Umfang

**K2a — Mode-Hold (Kernfunktion):**

1. **Eigene Kommandos stempeln:** Jeder `set_hvac_mode`-Call (Nudge `:2603`, Frost-Rescue `:2804`, Safe-State `:1765`, Park `__init__.py:515`) stempelt `_last_commanded_hvac` + Monotonic-Zeitstempel. Analogon zur Setpoint-Baseline; Mode-Echo-Fenster konservativ = `SETPOINT_ADOPT_ECHO_WINDOW_S`.
2. **Externe Modusänderung erkennen** (im Tick, vor dem Nudge-Entscheid): `current_mode` weicht von `desired` **und** von `_last_commanded_hvac` ab, außerhalb des Mode-Echo-Fensters, und hat sich gegenüber der letzten Beobachtung *bewegt* (gleiche Move-Guard-Idee wie beim Sollwert) → externer Eingriff.
3. **Adoption als Mode-Hold:** neues Zustandsfeld (`_mode_override: str | None`) mit **demselben Lebenszyklus wie der Sollwert-Hold** — `resolve_hold_expiry` mit der Zonen-Policy, Expiry-Ankündigung, Ende an Schaltpunkt/Timer/Presence-Flip (`hold_expired` wird wiederverwendet, kein neuer Lifecycle-Code). Persistiert in `_save_payload` (wie der bestehende Override, F13-Muster).
4. **Semantik pro Modus (bewusst eng):**
   - `off` ⇒ Zone verhält sich wie „temporär deaktiviert": kein Nudge, kein Setpoint-Write; **Frost-/Mould-Rescue bleibt aktiv** — das ist exakt die bereits existierende, getestete Maschinerie des Disabled-Zweigs (`coordinator.py:2773 ff.`, `test_frost_rescue_disabled.py`). Kein neues Sicherheitskonzept nötig.
   - `fan_only` / `dry` / `heat` / `cool` ⇒ `desired_hvac := gehaltener Modus` (Nudge entfällt, weil current == desired); Sollwert-Regelung läuft im Rahmen des Modus weiter.
   - Nur Modi aus der realen `hvac_modes`-Liste des Geräts werden adoptiert; `heat_cool` wird in v1 **nicht** adoptiert (B7 separat), sondern wie heute behandelt.
5. **Präzedenz unverändert:** Fenster-offen/Frost (I6) schlagen den Mode-Hold — der Safety-Pfad läuft *vor* der Hold-Auswertung, identisch zur heutigen Override-Präzedenz (`is_safety` in `:2596` wird um den Mode-Hold **nicht** erweitert; ein Mode-Hold ist Komfort, keine Safety).
6. **Option:** `adopt_external_mode` (Default **an**, Community-Erwartung; dokumentiertes Opt-out für selbstschaltende Geräte der Daikin-Klasse — VT-Warnung aus der Analyse §4.2).
7. **Pure Funktionen bleiben pur und unverändert:** `needs_mode_nudge`/`resolve_desired_mode` werden nicht angefasst; das Gating passiert ausschließlich im Coordinator (desired wird vor dem Nudge durch den Hold ersetzt). Dadurch bleiben alle `test_tick_resolve.py`-Tests wörtlich gültig (I9).

**K2b — Guard-Ordering (klein, severabel):** `_lifecycle.observe()` wird vor den Nudge-Entscheid gezogen (bzw. `guard_block_reason` erhält den Post-Observe-Zustand). Damit bucht ein Nutzer-Stopp den Kompressor-Stopp ein, **bevor** über einen Re-Nudge entschieden wird → min-off greift (C5). Betrifft auch das legitime Re-Nudge nach Mode-Hold-Ablauf.

### Verifikation K2 (Funktionslücken-Nachweis)

1. **Unverändert grün:** `test_tick_resolve.py` komplett (I9 — pure Funktionen unberührt); `test_compressor_guard.py` (I10 — K2b macht den Guard *strenger*, nie lockerer: bestehende Block-Fälle bleiben Block-Fälle, nachweisen per Suite); `test_window_cool_safety.py`, `test_frost_rescue_disabled.py` (I6); `test_dry_actuation.py`, `test_idle_reversible.py`, `test_hvac_action_wiring.py` (Modus-Pfade); `test_override_lifecycle.py`/`test_override_mode.py` (I8 — Sollwert-Hold-Lebenszyklus unangetastet); `test_hub_glue_coverage.py` (Boiler-Aggregat: eine off-gehaltene Zone meldet keinen Demand — identisch zur Disabled-Zone, bestehendes Verhalten).
2. **Umgedreht:** C4 (Mode-Hold statt Rück-Nudge), C5 (min-off hält Re-Nudge).
3. **Neu:** Mode-Hold endet am Schaltpunkt/Timer/Presence-Flip und Poise nudgt danach zurück (mit Guard!); Fenster-offen erzwingt Safety-off trotz aktivem `cool`-Hold; Opt-out; Modus-Echo (Poise nudgt cool, Gerät meldet cool 90 s später) wird nie adoptiert; Gerät meldet `unavailable`/`unknown` → kein Hold; Idle-Park (`fan_only` von Poise kommandiert) wird durch den Kommando-Stempel nie als extern fehlklassifiziert.
4. **Ausdrücklicher Risikofokus (je ein Test):** (a) Sollwert-Hold + Mode-Hold gleichzeitig (IR sendet Modus+Temp in einem Frame — der Normalfall!): beide werden konsistent adoptiert, `override_mode` (`control/cooling.py:58-91`) darf den gehaltenen Modus nicht sofort wieder verlassen; (b) selbstschaltendes Gerät simuliert (Modus flippt ohne Nutzereingriff kurz nach eigenem Kommando) → Echo-Fenster fängt es.
5. **Suiten:** volle Integration-Suite + Closed-Loop-Szenario „IR-Eingriff während Kühlbetrieb" in `tests/harness` als Referenzfall.

---

## 5. K3 — Beobachtbarkeit (zwingend, verhaltensneutral)

**Ist:** Eine erkannte-aber-unterdrückte Fremdänderung hinterlässt keinerlei Spur; der `reason`-Parameter von `set_override` wird beim Setzen verworfen (`coordinator.py:551-591`) — `device_adopt` ist nirgends sichtbar.

**Soll:** (1) INFO-Log + Diagnose-Attribut (`external_change_suppressed`: letzter Grund `echo_window | stable_offset | deadband | device_schedule | no_baseline | opt_out` + Zähler) im Adoptionsblock; (2) `override_source` (`device | ui | service`) wird beim Setzen gespeichert und in Diagnostics/Entity-Attributen exponiert. Keine Regeländerung, keine Card-Pflicht (Card-Chip → §7).

**Verifikation:** `test_diagnostics_data.py` + neue Assertions; expliziter Nachweis der Verhaltensneutralität: kompletter Testlauf vor/nach K3 identisch bis auf die neuen Attribute (kein Test darf auf Attribut-Vollständigkeit matchen — prüfen: `diagnostics_data`-Snapshots sind additiv-tolerant).

## 6. K4 — Doku-Ehrlichkeit (zwingend, XS)

README:32 („instead of being overwritten on the next tick"), README-Tabelle „Manuelle Eingriffe", `strings.json:211`/`de.json:356`: Vorbedingungen (Echo-Fenster, Bewegungs-Guard, Geräte-Schedule-Gate) und Modalitätsgrenzen (nach K2: Sollwert + Modus; Fan/Swing weiterhin nicht) korrekt benennen. Verifikation: Doc-Review; der bestehende CI-Doc-Drift-Guard (Card-Optionen) bleibt grün.

---

## 7. Zurückgestellt — mit Begründung und Wiedervorlage-Kriterium

| Thema | Warum nicht zwingend | Wiedervorlage wenn |
|---|---|---|
| Context-Attribution (V2) | K1/K2 beheben den Bug ohne Architekturwechsel; Context trennt IR-Eingriffe ohnehin nicht von asynchronen Geräte-Echos (Analyse B9) | UI-/Automations-Eingriffe Dritter präzise klassifiziert werden sollen (Card-Herkunft „wer") |
| In-Fenster-Sofort-Adoption (Drei-Werte-Logik, `pre_write_sp`) | Latenzgewinn ≤ 120 s vs. Risiko der I3-Klasse bei verdeckten Geräte-Clamps | Feld-Telemetrie aus K3 zeigt relevante Häufigkeit von In-Fenster-Eingriffen |
| Deadband-Symmetrie (B4) | Sub-Step-Eingriffe sind bei IR-Fernbedienungen selten (Remote-Step == Geräte-Step); Absenkung riskiert Requant-Re-Adoption (I2) | K3-Zähler `deadband` schlägt im Feld an |
| Neustart-Baseline (B5) | Seltener Pfad; braucht Wall-Clock-Migration des Stempels | nach K1-Stabilisierung; eigener Plan |
| `heat_cool`/Dual-Setpoint (B7), Fan/Swing (B8) | eigenständige Featureentscheidungen, kein Bezug zum gemeldeten Vorfall | Produktentscheidung |
| `sched_active`-Gate (B6) | im IR-Setup fast nie aktiv; Verhalten ist vertretbar (Geräte-Schedule bewegt den Sollwert), nur unsichtbar → wird durch K3 sichtbar | K3 zeigt False-Positives der Namensheuristik |

---

## 8. Ablauf, Reihenfolge, Abnahme

**PR-Reihenfolge** (jede Stufe nur bei voll grüner CI-Matrix inkl. Coverage-Gates):

1. **PR-0** Phase-0-Charakterisierung (C1–C7, nur Tests). Beweist zugleich, dass die Analyse-Zeitachsen im Test-Harness reproduzierbar sind.
2. **PR-1** K1 (+ zugehörige xfail-Marker entfernen: C1, C2, C3, C7). Kleinster Schnitt zuerst — behebt den wahrscheinlichsten Hergang des Bugreports.
3. **PR-2** K2a + K2b (entfernt C4, C5). Enthält Options-Migration (`adopt_external_mode`, Config-Version per `migration.py`, ADR-0018-Release-Note).
4. **PR-3** K3 + K4 (kann mit PR-1/PR-2 gebündelt werden).
5. Neuer ADR-Nachtrag zu ADR-0059 (Mode-Hold + prev-Freeze formal festschreiben; ADR-0046-§3-Bezug für `device_external_override`).

**Abnahmekriterien (Definition of Done) je Baustein:**

| Baustein | Nutzer-sichtbar | Test-Beweis | Kein-Rückschritt-Beweis |
|---|---|---|---|
| K1 | IR-Temperaturänderung überlebt und erscheint als Hold-Pill mit Ablaufzeit — auch < 2 min nach einem Poise-Write | C1/C2/C3/C7 grün ohne xfail | `test_adopt.py` + `test_setpoint_adoption.py` unverändert grün; Referenzfälle bitidentisch |
| K2 | IR-Modusänderung (inkl. Ausschalten) bleibt bestehen, Rückkehr zur Automatik zur angekündigten Zeit; kein Kompressor-Sofortwiederstart | C4/C5 grün | `test_tick_resolve.py`, `test_compressor_guard.py`, `test_window_cool_safety.py`, `test_frost_rescue_disabled.py` unverändert grün |
| K3 | Unterdrückte Eingriffe sind in Diagnostics erklärbar | neue Diagnostics-Assertions | Testlauf vor/nach identisch (additiv) |
| K4 | Doku beschreibt reales Verhalten | Doc-Review | CI-Doc-Guards grün |

**Rollback:** K1 ist ein lokal begrenzter Guard-Umbau (eine Bedingung), K2 ist options-gated (`adopt_external_mode=False` stellt exakt das heutige Nudge-Verhalten wieder her — dieser Äquivalenzpfad bekommt einen eigenen Test), K3/K4 sind verhaltensneutral. Damit ist jede Stufe unabhängig zurücknehmbar, ohne die anderen zu berühren.
