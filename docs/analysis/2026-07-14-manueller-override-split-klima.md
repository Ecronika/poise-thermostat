# Fehleranalyse: Manuelle Fernbedienungs-Änderung an der Split-Klima wird nicht als Override erkannt und revertiert

**Datum:** 2026-07-14 ·
**Status:** Analyse abgeschlossen, Befunde code-verifiziert ·
**Bezug:** Bugreport „Klimaanlage per Fernbedienung verstellt; die Climate-Entität hat die Änderung angezeigt; Poise hat sie nicht als manuellen Override erkannt und kurze Zeit später rückgängig gemacht."

---

## 1. Zusammenfassung

Der gemeldete Fehler ist real, reproduzierbar und hat **zwei voneinander unabhängige Hauptursachen** — je nachdem, ob per Fernbedienung die **Zieltemperatur** oder der **Betriebsmodus** verstellt wurde:

1. **Sollwert-Fall — „Echo-Fenster-Poisoning":** Eine echte Nutzeränderung, die von irgendeinem Tick/Refresh innerhalb von 120 s nach Poises letztem eigenen Schreibvorgang beobachtet wird, wird **dauerhaft verschluckt** und beim nächsten zulässigen Write zurückgesetzt. Bei einer Split-Klima (FAST_AIR-Profil, Regulierungs-Drossel 300 s) erfolgt der Revert typischerweise **3–6 Minuten nach dem Eingriff** — exakt „kurze Zeit später". Kein Log, kein Event, keine Override-Spur.
2. **Modus-Fall — kein Adoptionspfad für `hvac_mode`:** Eine geräteseitige Modusänderung (cool→off, cool→fan_only, cool→dry, …) wird von `needs_mode_nudge` als Abweichung behandelt und **binnen Sekunden** zurückkommandiert. Es existiert im Live-Pfad überhaupt kein Mechanismus, der eine Modusänderung als Nutzerintention adoptiert.

Beide Ursachen widersprechen sowohl dem eigenen Doku-Versprechen des Projekts (README: „adopted … instead of being overwritten on the next tick") als auch dem klar dokumentierten Community-Konsens: **Ein manueller Eingriff muss gewinnen (nie binnen Sekunden/Minuten zurückgesetzt werden), aber garantiert enden (Schaltpunkt/Timer).** Poise hat die zweite Hälfte dieser Regel vorbildlich gebaut (Override-Lebenszyklus, ADR-0059) — die erste Hälfte (zuverlässige *Erkennung* des Eingriffs) hat strukturelle Lücken.

Alle Befunde wurden adversarial gegen den Code verifiziert (13 Befunde: 9 bestätigt, 4 in Details präzisiert, 0 widerlegt). Details in §3, Community-Abgleich in §4, Verbesserungsvorschläge in §5.

---

## 2. Symptom und Reproduktion

Beobachtet: IR-Fernbedienung → Split-Klima ändert sich → die HA-Climate-Entität des Aktors zeigt die Änderung an (die Geräteintegration meldet also korrekt zurück; Erkennbarkeit ist gegeben) → Poise adoptiert **keinen** Hold → wenig später steht der alte Zustand wieder da.

### Reproduktion A (Sollwert, deckungsgleich mit dem Report)

Split-Klima, FAST_AIR-Profil (climate + `can_cool` ⇒ `self_regulating=True`, `regulation_period_s=300`, `control/dynamics.py:48-57, 106-108`):

| Zeit | Ereignis | Code-Verhalten |
|---|---|---|
| t0 | Poise schreibt Sollwert 24.0 | Baseline gestempelt: `_last_written_sp=24.0`, `_last_sp_write_ts=t0` (`coordinator.py:2716-2717`) |
| t0+30 s | Nutzer stellt per IR 26.0 ein | Entität meldet 26.0 |
| t0+60 s (Tick) | Erstbeobachtung **im Echo-Fenster** (60 < 120, `override.py:250-251`) → keine Adoption; **aber `_prev_device_sp := 26.0`** (`coordinator.py:2672`, unbedingt jeden Tick) | Write durch Regulierungs-Drossel unterdrückt (`coordinator.py:2631-2644`) |
| t0+120/180/240 s | Echo-Fenster abgelaufen, aber **Stable-Offset-Guard** blockiert: `device_sp == prev_device_sp` (`override.py:254-257`) → Adoption dauerhaft unmöglich | Writes weiter gedrosselt |
| t0+300 s | Drossel abgelaufen → `should_write(26.0 vs 24.0)` → **Poise schreibt 24.0 zurück** (`coordinator.py:2686-2718`) | Nutzeränderung weg; `reason="tick"`, kein Log/Event |

Der Guard, der eigentlich das Wieder-Adoptieren eines vom Gerät re-quantisierten *eigenen* Writes verhindern soll, wird durch die In-Fenster-Beobachtung mit dem **Nutzerwert vergiftet** — danach „bewegt" sich der Wert nie wieder und kann strukturell nie adoptiert werden.

**Verschärfung Split-Klima:** Die typische IR-Aktion (Sollwert runter im Kühlbetrieb) startet/stoppt den Kompressor und flippt damit `hvac_action`; der Aktor-Listener (`coordinator.py:1064-1071`) löst dann **sofort** einen Refresh aus. Die Erstbeobachtung fällt damit für praktisch **jede** Nutzeränderung binnen 120 s nach einem Poise-Write ins Echo-Fenster — nicht nur für Änderungen in den ersten 60 s. Auf dem reinen 60-s-Raster wäre eine Änderung bei t0+60…110 s noch adoptiert worden (Erstbeobachtung bei t0+120 ≥ Fenster); der ereignisgetriebene Refresh nimmt ihr genau diesen Ausweg.

### Reproduktion B (Modus)

AC kühlt; Nutzer schaltet per IR auf `off` (oder `fan_only`/`dry`/`heat`):

1. Der Modus ist der **State** der Climate-Entität → der Aktor-Listener feuert sofort einen Refresh (~1–10 s, `coordinator.py:1042-1075`).
2. `resolve_desired_mode` liefert weiterhin Poises Wunschmodus (`tick_resolve.py:253-282`), `needs_mode_nudge` ist schlicht `current != desired` (`tick_resolve.py:248-250`) → `set_hvac_mode(cool)` (`coordinator.py:2601-2608`).
3. Der Kompressor-Guard blockt den ersten Rück-Nudge praktisch nie, weil `guard_block_reason` gegen den **Pre-Observe**-Lifecycle ausgewertet wird — `observe()` (das den Nutzer-Stopp einbucht) läuft erst *nach* dem Nudge im selben Tick (`coordinator.py:2934-2957`, `multi/lifecycle.py:115-117`).

**Revert binnen Sekunden**, ohne Override-Status. Der Nutzer kann das Gerät per Fernbedienung faktisch nicht ausschalten. Nebeneffekt: Der Kompressor wird unmittelbar nach dem Nutzer-Stopp wieder gestartet — der Min-Off-Schutz greift wegen der Auswertungsreihenfolge nicht (Verschleißrisiko, eigenständiger Defekt).

### Welcher Fall lag hier vor?

„Kurze Zeit später" (Minuten, nicht Sekunden) und „als Manueller Override nicht erkannt" passen am besten auf **Reproduktion A** (Sollwert; Revert nach 3–6 min). Eine Modusänderung wäre binnen Sekunden zurückgesetzt worden. Ein dritter, seltener Kandidat ist in §3.3 dokumentiert (Adoption griff, aber der Hold endete designbedingt am nächsten Schaltpunkt oder Presence-Wechsel — dann wäre der Revert ebenfalls „kurze Zeit später" sichtbar, aber mit Override-Phase dazwischen; der Report sagt „nicht erkannt", was dagegen spricht).

---

## 3. Verifizierte Befunde im Detail

Jeder Befund wurde von einem unabhängigen adversarialen Verifizierer Zeile für Zeile gegen den Code geprüft (Auftrag: widerlegen, nicht bestätigen).

### 3.1 Hauptursachen

| # | Befund | Verdikt | Kernbeleg |
|---|---|---|---|
| B1 | Echo-Fenster-Poisoning: In-Fenster-Beobachtung vergiftet `_prev_device_sp`; Stable-Offset-Guard blockiert danach dauerhaft; Revert beim ersten un-gedrosselten Write | **Bestätigt** (Generalisierung präzisiert: Kill-Zone = jede Erstbeobachtung < 120 s nach Write; bei Split-Klimas durch Event-Refreshes fast das gesamte Fenster) | `override.py:250-257`, `coordinator.py:2672, 2686-2718`, `dynamics.py:48-57` |
| B2 | Kein Adoptionspfad für `hvac_mode`; Rück-Nudge binnen Sekunden; `is_external_override` (Multi-Aktor-Shadow) ist dormant und feuert nie | **Bestätigt** | `tick_resolve.py:248-250`, `coordinator.py:2578-2614, 2959-2986`, `multi/lifecycle.py:160-182` |
| B3 | Das Echo-Fenster ist asymmetrisch: Es unterdrückt nur die *Adoption*, nie den *Write*. Auf un-gedrosselten Aktoren (TRV/SLOW_HYDRONIC) wird eine In-Fenster-Änderung **schon beim nächsten Tick (≤ 60 s)** zurückgeschrieben — das Fenster schützt Poises eigene Writes, nie den Nutzer | **Bestätigt** | `coordinator.py:2686-2700` (kein Echo-Gate), `tick_resolve.py:142-160`, `dynamics.py:59-68` |

### 3.2 Weitere bestätigte Lücken (gleiche Fehlerklasse, andere Auslöser)

| # | Befund | Verdikt | Wirkung |
|---|---|---|---|
| B4 | **Deadband-Asymmetrie:** Adoption verlangt \|Δ\| ≥ max(0.2, `step`) (`coordinator.py:2660`), der Revert-Write nur \|Δ\| ≥ 0.2 (`:2699`). Bei `target_temperature_step=1.0` kann eine 0.5-K-Korrektur **strukturell nie adoptiert, aber immer revertiert** werden; auch kumulierte Sub-Step-Änderungen über mehrere Ticks bleiben unter dem Bewegungs-Guard | **Bestätigt** | Jede Halbgrad-Korrektur per IR wird zuverlässig zurückgesetzt |
| B5 | **Neustart-Lücke:** `_last_written_sp`/`_last_sp_write_ts` sind runtime-only (fehlen in `_save_payload`, `coordinator.py:1505-1540`; Monotonic-Clock). Nach HA-Neustart ist Adoption bis zum ersten eigenen Write unmöglich (No-Baseline-Guard `override.py:248-249`), während der allererste Tick wegen `mode_changed=True` (auch `_last_written_mode` fehlt) **deadband-unabhängig sofort schreibt** — eine während des Neustarts/Updates gesetzte IR-Temperatur wird binnen der ersten Minute überschrieben. Gleiches Muster nach Safe-State/Frost-Rescue (`coordinator.py:1786, 2826` setzen die Baseline auf None) | **Bestätigt** | Nutzeränderungen rund um Neustarts/Ausfälle chancenlos |
| B6 | **Silente Deaktivierung durch `sched_active`:** Adoption ist hart aus, solange eine per **Namensheuristik** autodetektierte Entität `switch.*schedule*` am Aktor-Gerät `on` meldet (`coordinator.py:2665, 1077-1096, 1695-1698`; `model_fixes.py:29-31`) — ungetestet, im README/Options-Label undokumentiert; einziger Hinweis ist das Repair-Issue `device_schedule` | **Bestätigt** (Präzisierung: Switch-Entität, autodetektiert, nicht konfiguriert; bei IR-Setups selten, bei Tuya/Midea-ACs mit Timer-Switch realistisch) | Falls aktiv: *jede* IR-Änderung wird revertiert, trotz `adopt_external_setpoint=True` |
| B7 | **Dual-Setpoint-Blindheit:** Gelesen wird ausschließlich das Attribut `temperature` (`coordinator.py:2619`); `target_temp_high/low` kommen produktiv nirgends vor. Wählt der Nutzer per IR `heat_cool`/`auto`, ist der Detektor blind (`device_sp=None`), `should_write(None,…)=True` erzwingt **jeden Tick** einen Write (Mode-Nudge umgeht die Drossel), plus Rück-Nudge aus `heat_cool` heraus | **Bestätigt** | Kompletter Nutzereingriff unsichtbar + Write-Sturm |
| B8 | **fan_mode/swing_mode:** Für Poise unsichtbar (Attribut-Änderungen triggern keinen Refresh, `coordinator.py:1056-1071`), nirgends adoptiert, nirgends geschrieben (nur Shadow-Lesen für Diagnostik). Ein vom Nutzer gewählter `fan_only`-*HVAC-Modus* wird bei Heiz-/Kühlbedarf weggenudgt; der in ADR-0046 §15 versprochene Test „fan_only → kein off-Nudge" existiert nicht | **Bestätigt** | Nutzerwahl Lüfter/Lamellen ungeschützt; fan_only überlebt maximal einen Tick |
| B9 | **Kein Context, keine Attribution:** Die Echo-vs-Nutzer-Klassifikation ist zu 100 % Zeitfenster-/Deadband-Heuristik. Nirgends wird ein HA-`Context` erzeugt, gespeichert oder verglichen (`actuator.py:44` ruft `async_call` ohne `context=`; der Listener liest `event.context` nie) | **Bestätigt** (Präzisierung: Context allein würde IR-Änderungen nicht von *asynchronen Geräte-Echos* trennen — beide tragen frische Contexts; er trennt aber zuverlässig HA-interne Akteure und macht das Fenster nur noch für geräteseitige Updates nötig) | Grundursache hinter B1–B3 |
| B10 | **Doku-/Test-Lücke:** README:32 („adopted … instead of being overwritten on the next tick") und die Options-Labels versprechen Adoption ohne die drei realen Vorbedingungen (Echo-Blindfenster, Schedule-Gate, Bewegungs-Guard) und ohne Modalitätsgrenze (nur Sollwert). Kein Test deckt den Zwei-Phasen-Ablauf „Änderung im Fenster → Beobachtung nach Fensterablauf" ab; alle Adoptions-Tests laufen gegen einen heat-only-TRV, keiner gegen die Bugreport-Konstellation Split-Klima | **Bestätigt** | Der Bugreport ist die direkt vorhersagbare Folge dieser Erwartungslücke |

### 3.3 Plausible Zusatzbefunde (im Workflow gefunden, nicht separat adversarial verifiziert)

- **Design-Anteil „Revert trotz Adoption":** Greift die Adoption, endet der Hold per Default-Policy `schedule` am nächsten Schaltpunkt und per `override_end_on_presence_change` (Default an) bei jedem Presence-Flip — für Nutzer ohne Card-Blick optisch identisch zum Bug („meine Änderung wurde nach 15 min zurückgesetzt"). Das ist dokumentiertes ADR-0059-Verhalten, verstärkt aber die Verwechslungsgefahr, solange Erkennung und Anzeige lückenhaft sind.
- **Phantom-Adoption durch Per-Modus-Sollwertspeicher:** Split-Klimas führen je `hvac_mode` eigene Zieltemperaturen. Ein Poise-Mode-Nudge lässt das Gerät den Sollwert des neuen Modus melden; liegt Poises letzter Setpoint-Write > 120 s zurück und folgt (wegen Deadband) kein eigener Write, erfüllt dieser Sprung alle Adoptions-Gates und wird als manueller Hold adoptiert, den nie ein Nutzer gesetzt hat.
- **Adoption verkettet sich selbst:** Eine erfolgreiche (In-Band-)Adoption stempelt `_last_written_sp`/`_last_sp_write_ts` ohne realen Service-Call (`coordinator.py:2683-2684`) und öffnet damit ein frisches 120-s-Fenster — eine **zweite** Nutzerkorrektur kurz nach der ersten wird per B1 verschluckt.
- **Tick-Jitter am Fensterrand:** Die Echo-Grenze ist strikt `<` (`override.py:250`); ein bei t0+119.x feuernder „120-s-Tick" rutscht ins Fenster und vergiftet per B1.

---

## 4. Abgleich mit der Community-Erwartung

### 4.1 Der Konsens in einem Satz

> **Ein manueller Eingriff — egal ob per App, Gerätetaste, TRV-Rad oder IR-Fernbedienung — muss übernommen werden und gewinnen; er darf nie still binnen Sekunden/Minuten zurückgesetzt werden; und er muss über eine sichtbare, konfigurierbare Regel enden (nächster Schaltpunkt, Timer oder explizit).**

Poise erfüllt den *dritten* Teil dieser Regel besser als der Marktdurchschnitt (ADR-0059: Hold-Policies `schedule`/`timer`/`permanent`, Expiry bei Set-Zeit angekündigt, tado-16475- und VT-1961-Fallen explizit vermieden). Der Bugreport betrifft den *ersten* Teil — und dort liegt Poise derzeit hinter den Community-Referenzen.

### 4.2 Belege je Quelle

**Versatile Thermostat (over_climate — die direkteste Vergleichsklasse):**
- Issue #110 (vom Maintainer selbst): *„EXPECTED: the VTherm goes into manual preset and the target temperature is the target temp of the underlying"* — geräteseitige Änderung = manueller Eingriff, der übernommen wird.
- Discussion #472 (Wärmepumpe per Remote bedient), Maintainer: *„What we want is that VTherm follows the state on the underlying climate"* — Remote-Bedienung ist ein anerkannter Kern-Use-Case, kein Randfall.
- VT löst das über eine pro Thermostat angelegte Switch-Entität **„Follow underlying temp change"**, die Temperatur- **und** hvac_mode-Übernahme gemeinsam schaltet; `fan_mode` wird sogar bedingungslos gespiegelt.
- VTs eigene Schwächen bestätigen die Poise-Diagnose spiegelbildlich: VT nutzt ebenfalls **kein** Context-Tracking, sondern ein 10-s-Anti-Loop-Fenster — und erntet exakt dieselbe Fehlerklasse (#798: echte Remote-Änderungen werden verschluckt; #804: Echo-Loop; Doku warnt „changes too close together in time … ignored"). Poises 120-s-Fenster ist zwölfmal so groß wie VTs bereits problematisches 10-s-Fenster.
- #1875/#1961 (im Poise-Code zitiert) definieren die Ende-Semantik: Eingriff respektieren, aber zeitlich begrenzen; Rückkehrziel ist immer der Plan, nie ein früherer Manualwert.

**Better Thermostat:**
- Issue #1700 wörtlich: *„the setpoint on the TRV needs to remain as it was set manually"* — geräteseitiger Eingriff muss adoptiert werden, nie überschrieben.
- Issue #1766: Nutzer werten ungewolltes Revertieren als Vertragsbruch; die `child_lock`-Option ist der explizite **Opt-in** für „Externes ignorieren/revertieren" — Revertieren als *Default* ist umgekehrt zur Community-Erwartung.
- Technisch nutzt BT **Context-Vergleich** zur Echo-Erkennung (`if self.context == event.context: return` in `events/trv.py`) und übernimmt externe Setpoint-/Modusänderungen (`user turns the valve dial → BT follows`).
- Gegenrichtung (#1532): Fehlklassifikation „extern = Nutzerwunsch" ist genauso ein Bug — deckt sich mit Poises berechtigtem Anliegen hinter Echo-Fenster/Stable-Guard; das Problem ist nicht das Ziel, sondern die Heuristik.

**Home-Assistant-Core (idiomatischer Mechanismus):**
- Jeder State trägt ein `Context`-Objekt (`id`/`user_id`/`parent_id`); State-Änderungen aus eigenem Service-Call tragen dessen Context (≤ 5 s, `CONTEXT_RECENT_TIME_SECONDS`), geräteseitige Updates bekommen einen frischen Context mit `user_id=None`/`parent_id=None`.
- `generic_thermostat` ist die Referenzimplementierung: pro Service-Call ein Kind-Context, dessen `id` gemerkt wird; `new_state.context.id != self._last_context_id` ⇒ *„If the user toggles the switch, assume they want control"*. Die 2-s-Race-Lücke ist dort dokumentiert — d. h. auch Core hält eine ergänzende Fenster-Heuristik für nötig, aber als *Ausnahme*, nicht als einzigen Mechanismus.
- Community-Muster (`context.user_id == None and context.parent_id == None` ⇒ physisches Gerät) ist etabliert, mit bekannten Grenzen (Context als Heuristik, nicht Kausalkette).

**Kommerzielle Produkte (Erwartungsprägung der Nutzer):**
- **Nest:** Manuelle Änderung gilt *per Default* bis zum nächsten Schaltpunkt; unbegrenztes Halten nur per explizitem „Hold".
- **ecobee:** Hold-Dauer konfigurierbar (next transition / 2 h / 4 h / indefinite / ask); der unbemerkt klebende Dauer-Hold ist die bestdokumentierte Fehlerklasse des Markts.
- **tado:** Manual Control mit per-Raum wählbarer Ende-Regel — **auch für Eingriffe direkt am Gerät** (tado X: „Manual Control on tado Device" bekommt dieselbe Hold-Policy wie App-Eingriffe). Bemerkenswert: Beim Smart AC Control **verbietet** tado die IR-Koexistenz faktisch (nur Full-State-Remotes; „changes you make using your AC remote will not be reflected") — der Marktführer löst das Problem nicht, er umgeht es. Eine Integration, die IR-Eingriffe korrekt adoptiert, wäre hier tatsächlich *besser* als der Marktstandard.
- **Scheduler-Component #316 / HA-Threads 529152, 840750, 296651:** „Automatik setzt manuelle Änderung binnen Sekunden zurück" wird durchgängig als Bug behandelt; Automatik soll nur an Schaltpunkten/Ereignissen schreiben, nie als Dauer-Enforcement gegen den Nutzer.
- **ESPHome climate_ir / SmartIR:** Die Grenze der Erkennbarkeit liegt bei der *Geräteintegration* (IR ist unidirektional; nur mit Receiver/Netzwerk-AC kommt der Remote-Eingriff in die Entität). Im vorliegenden Fall hat die Entität die Änderung angezeigt — die Erkennbarkeit war also gegeben; die Lücke liegt vollständig bei Poise.

### 4.3 Soll/Ist je Modalität

| Modalität (per IR geändert) | Community-Erwartung | Poise-Ist | Bewertung |
|---|---|---|---|
| Zieltemperatur | Übernehmen als Hold mit Ende-Regel (VT #110, BT #1700, tado X, Nest) | Adoption existiert (ADR-0059 §8), fällt aber in der Kill-Zone (≤ 120 s nach eigenem Write), bei Sub-Step-Deltas, nach Neustarts und bei Schedule-Gate aus → Revert ohne Spur | **Lückenhaft** (B1, B3–B6) |
| `hvac_mode` (aus/ein, cool→fan_only/dry) | Übernehmen bzw. respektieren; Abschalten des Geräts ist Nutzerintention (VT-Follow deckt Modus mit ab; BT folgt dem Rad; tado X: gleiche Hold-Policy) | Kein Adoptionspfad; Rück-Nudge binnen Sekunden; Nutzer kann Gerät nicht ausschalten | **Fehlt komplett** (B2) |
| `fan_mode`/`swing_mode` | Mindestens nicht bekämpfen (VT spiegelt fan_mode bedingungslos) | Unsichtbar; indirekt durch eigene Kommandos/IR-Bridge-Vollframes überschreibbar | **Blind** (B8) |
| Ende-Semantik eines Holds | Sichtbar, konfigurierbar, wertunabhängig am Schaltpunkt | ADR-0059: vorbildlich (Policy, angekündigte Expiry, Preheat-Ende) | **Über Marktniveau** |
| Transparenz | Auto-Reverts müssen erklärbar sein (core#64284: versteckte Reverts überraschen) | Nicht-Adoption ist unsichtbar (kein Log/Event/Attribut); `device_adopt`-Herkunft auch im Erfolgsfall nicht angezeigt | **Lückenhaft** (B10) |

---

## 5. Verbesserungsvorschläge

Priorisiert; V1–V3 beheben den gemeldeten Fehler, V4–V8 schließen die verwandten Lücken.

### V1 — Kernfix Sollwert: Kill-Zone des Echo-Fensters schließen (klein, hohe Wirkung)

Das Echo-Fenster darf echte Nutzeränderungen nicht dauerhaft verschlucken. Zwei komplementäre, chirurgische Änderungen an `detect_external_setpoint`/Verdrahtung:

1. **Drei-Werte-Logik im Fenster:** Ein Echo/Lag kann nur zwei Werte melden: den **kommandierten** Wert (`last_written_sp`, ggf. re-quantisiert → Deadband ≥ step deckt das) oder den **Vor-Write-Wert** (Poll-Lag). Dem Detektor zusätzlich `pre_write_sp` (Gerätewert unmittelbar vor dem letzten Write) übergeben; meldet das Gerät im Fenster einen **dritten** Wert (≠ beiden, jenseits Deadband), ist das beweisbar eine Nutzeränderung → als `pending` vormerken und nach Fensterablauf adoptieren (oder sofort, wenn man dem Beweis traut).
2. **Poisoning stoppen:** `_prev_device_sp` nicht mit Werten aktualisieren, die *nur* wegen des Echo-Fensters unterdrückt wurden — bzw. den `pending`-Kandidaten aus (1) vom Stable-Offset-Guard ausnehmen. Der Guard behält seine Aufgabe (settled Re-Quantisierung des eigenen Writes nie adoptieren), verliert aber die Fähigkeit, vom Nutzerwert vergiftet zu werden.

Zusatz: den H-1-Listener-Filter (`coordinator.py:1064-1070`) für das `temperature`-Attribut des **Aktors** öffnen, damit eine IR-Sollwertänderung sofort (statt bis zu 60 s später) bewertet wird — mit dem Fix aus (1) ist die frühe Beobachtung dann kein Risiko mehr, sondern ein Vorteil.

### V2 — Attribution per HA-Context (idiomatisch, macht die Heuristik zur Rückfallebene)

Wie `generic_thermostat` und Better Thermostat: jeden eigenen Service-Call (`actuator.py`, Mode-Nudges, Frost-Rescue, Safe-State) mit einem eigenen Kind-`Context` absetzen und dessen `id` merken; im Aktor-Listener `event.context` vergleichen. Änderungen mit fremdem Context (insbesondere `user_id`/`parent_id` = None bei geräteseitigen Updates, gesetzte `user_id` bei UI-Eingriffen Dritter) sind Manual-Kandidaten. Grenzen einplanen (verifiziert): asynchrone Geräte-Echos des eigenen Writes tragen ebenfalls frische Contexts — für genau diese bleibt das (per V1 entschärfte) Echo-Fenster als Fallback. Ergebnis: UI-/Automations-Eingriffe werden exakt klassifiziert, das Zeitfenster gilt nur noch für den Rest.

### V3 — Adoptionspfad für `hvac_mode` (schließt Reproduktion B)

Eine geräteseitige Modusänderung, die Poise nicht kommandiert hat, wird als **Mode-Hold** mit dem bestehenden Override-Lebenszyklus (ADR-0059-Policies, Expiry-Ankündigung, Card-Pill) adoptiert statt weggenudgt:

- Nutzer `off` ⇒ Zone pausiert bis Policy-Ende (Schaltpunkt/Timer), Frost-/Mould-Floor bleibt als Sicherheitsnetz aktiv (Solver-Präzedenz besteht schon).
- Nutzer `fan_only`/`dry`/`heat` ⇒ Modus respektieren, Sollwert-Regelung im Rahmen des Modus fortführen.
- Vorarbeit existiert: `is_external_override` (`multi/lifecycle.py:173-182`) vergleicht bereits `hvac_mode` gegen ein `expected_echo` — dormant; in den Single-Aktor-Pfad verdrahten (Nudge-Entscheid *nach* `observe()`, was zugleich den Kompressor-Guard-Ordering-Defekt aus Reproduktion B behebt).
- Konfigurierbar analog VT/BT: `adopt_external_mode` (Default an, mit Policy), plus dokumentiertes Opt-out für Setups mit selbstständig schaltenden Geräten (Daikin-Klasse, VT-Warnung).
- ADR-0046 §3/§9 (ReasonCode `device_external_override`, Rückkehr-Policies) liefert die fertige Spezifikation — sie ist nur nie im Live-Pfad umgesetzt worden.

### V4 — Deadbands symmetrisch machen

Adoptions-Deadband von `max(WRITE_DEADBAND_C, step)` auf `WRITE_DEADBAND_C` senken; das `≥ step`-Kriterium nur noch **innerhalb** des Echo-Fensters zur Re-Quantisierungs-Abwehr verwenden (mit V1(1) ohnehin präziser gelöst). Regel: **Was der Write-Pfad als Abweichung behandelt (und revertieren würde), muss der Adoptionspfad als Eingriff erkennen können.** Kumulierte Sub-Step-Änderungen gegen `last_written_sp` statt nur gegen den Vortick prüfen.

### V5 — Baseline über Neustart/Safe-State retten

`_last_written_sp` (+ Wall-Clock-Write-Zeit statt Monotonic) in `_save_payload` aufnehmen und restaurieren. Nach Neustart ohne restaurierbare Baseline: erster Tick schreibt nicht blind, sondern behandelt eine Abweichung Gerät↔Plan wie einen Adoptionskandidaten (Grace-Tick) — damit überlebt eine während des Neustarts gesetzte IR-Temperatur. Nach Safe-State/Frost-Rescue analog re-baselinen statt nur `None` zu setzen.

### V6 — Transparenz: unterdrückte Adoption sichtbar machen

Jede erkannte-aber-nicht-adoptierte Fremdänderung loggt (DEBUG/INFO) und zählt ein Diagnose-Attribut mit Grund (`echo_window`, `stable_offset`, `deadband`, `device_schedule`, `no_baseline`). Die Card zeigt beim aktiven Hold die Herkunft (`device_adopt` vs. UI — heute wird der `reason` beim Setzen verworfen) und optional einen Hinweis-Chip „Geräteänderung nicht übernommen (Grund)". README/Options-Beschreibung um die realen Vorbedingungen und die Modalitätsgrenze korrigieren (B10); das `sched_active`-Gate dokumentieren.

### V7 — Testlücken schließen

- Integrationstest „Zwei-Phasen-Echo-Race" auf FAST_AIR: Write → Nutzeränderung im Fenster → Ticks bis nach Fensterablauf → **Adoption statt Revert** (fixiert V1).
- Modus-Szenarien: IR `cool→off/fan_only/heat` → Mode-Hold statt Rück-Nudge (fixiert V3); inkl. Kompressor-Guard-Ordering.
- Split-Klima-Konstellation generell (bisher testen alle Adoptionspfade nur heat-only-TRVs), `heat_cool`/Dual-Setpoint, `sched_active`-Gate, Sub-Step-Deltas, Neustart-Szenario.
- Den in ADR-0046 §15 versprochenen `fan_only`-Test nachliefern.

### V8 — Semantik-Feinschliff (Community-Alignment)

- Policy pro Eingriffskanal prüfen: tado X gibt Geräte-Eingriffen dieselbe Hold-Policy wie App-Eingriffen — Poise sollte das beibehalten, aber die Policy-Wahl (schedule/timer/permanent) auch pro Service-Aufruf annehmen (HA-FR-Muster „set temperature until").
- `heat_cool`: mindestens sauber degradieren (nicht jeden Tick schreiben), besser: als eigenen adoptierten Modus mit Band behandeln.
- Fan/Swing: nicht steuern ist ok — aber nie unbeabsichtigt überschreiben; wenn eigene Kommandos gerätebedingt Vollframes auslösen (IR-Bridges), zuletzt gesehene Nutzer-Fan/Swing-Werte mitfüttern, sofern die Bridge das erlaubt.

### Sofort-Workaround für Betroffene (bis zum Fix)

Manuelle Eingriffe über die **Poise-Climate-Entität bzw. die Card** vornehmen (dieser Pfad erzeugt zuverlässig einen Hold mit sichtbarer Ablaufzeit) statt über die IR-Fernbedienung. IR-Eingriffe funktionieren derzeit nur zufällig — genau dann, wenn der letzte Poise-Write > 120 s zurückliegt, die Änderung ≥ 1 Gerätestep beträgt und kein Neustart/Safe-State dazwischenlag.

---

## 6. Methodik

Multi-Agent-Analyse (18 Agenten): drei unabhängige Code-Leser (Tick-Pfad, Adoptionspfad, Tests/ADRs/Doku), drei Web-Rechercheure (Versatile Thermostat, Better Thermostat + HA-Core-Mechanik, kommerzielle Semantik + Foren), anschließend je Befund ein adversarialer Verifizierer mit dem expliziten Auftrag, den Befund zu **widerlegen** (Zeitachsen nachrechnen, Gates/Aufrufer/Tests prüfen). Verdikte: 9× bestätigt, 4× teilweise (Richtung korrekt, Details präzisiert — alle Präzisierungen sind oben eingearbeitet), 0× widerlegt. Zeilenangaben beziehen sich auf den Stand von Branch `claude/climate-manual-override-issue-q38mrm` (Basis `main`, Commit 93b25e9).
