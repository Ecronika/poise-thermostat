# Review: Anzeige-Diskrepanzen zwischen Poise Card und Climate-Entität

Stand: 2026-07-13 · Branch `claude/poise-climate-display-sync-m70lii` · reines Review, keine Code-Änderungen.

Anlass (Nutzerbericht): (1) Die IST-Temperaturen von Card und Climate-Entität stimmen nicht immer überein. (2) Bei einem manuellen Override, der kühlt — und bei dem das Gerät nachweislich kühlt — zeigt die Entität „Leerlauf" (idle).

**Kurzfassung:** Beide Beobachtungen sind reproduzierbar aus dem Code ableitbar und haben klar benennbare Ursachen. (1) Die Card zeigt als große IST-Zahl die *operative* Temperatur (Luft+Strahlung gemittelt), die Entität die *Luft*-Temperatur — zwei verschiedene, beide unbeschriftete Größen. (2) Die Entität leitet `hvac_action` aus dem publizierten Roh-Modus ab, der bei aktivem Override wörtlich `"manual"` lautet; die tatsächlich berechnete Richtung (`final_mode` = heat/cool/dry), mit der Poise den Aktor umschaltet, wird gar nicht publiziert. Die Entität meldet daher „idle", während der Aktor kühlt. Das widerspricht der dokumentierten HA-Semantik von `hvac_action` („was das Gerät *jetzt tut*") und bricht neben der UI auch Automationen und Statistiken, die darauf aufbauen.

---

## 1. Anzeige-Inventar: Wer zeigt was, aus welcher Quelle

### 1.1 Climate-Entität (`custom_components/poise/climate.py`)

| Anzeige | Quelle | Fundstelle |
| --- | --- | --- |
| `current_temperature` | `coordinator.data["current_temperature"]` = `round(room, 1)` — die **Luft**-Temperatur des Raumsensors nach Ingestion | `climate.py:209-210`, `coordinator.py:3171`, `coordinator.py:1855` |
| `hvac_action` | Eigene Ableitung: OFF wenn disabled → HEATING wenn `data["heating"]` → COOLING wenn `data["mode"] == "cool"` → sonst IDLE | `climate.py:239-247` |
| `hvac_mode` | `current_hvac_mode(enabled, climate_mode, …)` → auto/heat/cool/off (Betriebsart, nicht Aktivität) | `climate.py:227-237`, `devices/hvac_modes.py:25-42` |
| `target_temperature` | `data["target_temperature"]` = finaler Schreib-Sollwert (`wt.target`) | `climate.py:218-220`, `coordinator.py:3173` |
| `preset_mode` | `coordinator.preset` (none/eco/comfort/boost/away) | `climate.py:249-251` |

Die dafür maßgeblichen Coordinator-Signale:

- `mode` = `wt.mode` aus `resolve_write_target()`: einer aus `heat` / `cool` / `idle` / `off` (Fenster) / **`manual` (Override)** — `control/tick_resolve.py:93-100`, publiziert in `coordinator.py:3191`.
- `heating` = `enabled AND NOT window_open AND mode == "heat"` — reine **Absicht**, berechnet *vor* der Override-Richtungsauflösung — `coordinator.py:2438`.
- `cooling` = analog (`coordinator.py:2439`) — wird berechnet, aber **nicht publiziert** (fehlt in `_tick_data`); die Entität rekonstruiert Kühlen stattdessen aus `mode == "cool"`.
- `final_mode` = `mode_arbitration(override_mode(...), …)`: die **tatsächliche Richtungs-Entscheidung** inkl. Override (heat/cool/idle/dry) — `coordinator.py:2506-2532`. Sie steuert den realen Mode-Nudge an den Aktor (`resolve_desired_mode` → `climate.set_hvac_mode`, `coordinator.py:2556-2599`), wird aber **ebenfalls nicht publiziert**.

### 1.2 Poise Card (`card/src/poise-card.ts`)

| Anzeige | Quelle | Fundstelle |
| --- | --- | --- |
| Große IST-Zahl in der Dial-Mitte | `operative_temperature ?? current_temperature` — bevorzugt die **operative** Temperatur | `poise-card.ts:237, 326` |
| IST-Punkt auf dem Dial-Ring (`opdot`) | dieselbe operative Größe | `poise-card.ts:267-268, 309-314` |
| Temperatur-Lampe (Monitoring) | dieselbe operative Größe | `poise-card.ts:565-566` |
| Historien-Chart (IST-Linie) | `operative_temperature ?? current_temperature` aus der Historie | `poise-card.ts:149` |
| Handle-Farbe (orange/blau/neutral) | `hvac_action` der Entität (`heating`→orange, `cooling`→blau, sonst neutral) | `poise-card.ts:264-265, 708-709` |
| Sollwert (Mitte, Handle, Chart) | `temperature` (kommandierter/gehaltener Sollwert) | `override.ts:35-39`, `poise-card.ts:241, 249` |
| Hold-Pill („Manuell 22,5° · 45 min") | `override_active`, `override_policy`, `override_expires_at` | `poise-card.ts:468-488` |
| Komfort-Verdikt + Band | operative Größe gegen `comfort_low/high` | `poise-card.ts:203-212` |

Die operative Temperatur ist `T_op = a·T_Luft + (1−a)·T_MRT` mit `a = 0.5` bei ruhender Luft (`comfort/operative.py:12-24`, `coordinator.py:2806`); die MRT stammt aus einem Globe-/MRT-Sensor oder der virtuellen Schätzung (`tick_resolve.py:48-52`).

---

## 2. Zustandsmatrix: interner Zustand → Entität vs. Card vs. Realität

| Interner Zustand (Tick) | publ. `mode` | publ. `heating` | Entität `hvac_action` | Aktor real (Mode-Nudge) | Card |
| --- | --- | --- | --- | --- | --- |
| Heizbedarf (Automatik) | `heat` | `true` | **heating** | heizt (oder Ventil bereits satt → Gerät meldet selbst idle) | Handle orange |
| Kühlbedarf (Automatik) | `cool` | `false` | **cooling** | kühlt; bei aktivem Kompressor-Guard ggf. noch im alten Modus | Handle blau, ggf. Guard-Chip |
| Totband (idle) | `idle` | `false` | idle | parkt in heat/cool/**fan_only** (Umluft läuft!) | Handle neutral |
| Totband + Entfeuchten (`final_mode == "dry"`) | `idle` | `false` | **idle** ⚠️ | **entfeuchtet aktiv** (`dry`) | Handle neutral; kein Dry-Chip |
| **Manueller Override, Richtung kühlen** | **`manual`** | `false` | **idle** ⚠️⚠️ | **kühlt** (Nudge auf `cool` + Sollwert) | Hold-Pill ✓, aber Handle neutral ⚠️ |
| **Manueller Override, Richtung heizen** | **`manual`** | `false` | **idle** ⚠️⚠️ | **heizt** | Hold-Pill ✓, Handle neutral ⚠️ |
| Fenster offen | `off` | `false` | idle | hält Frost-Floor in `heat` (`resolve_desired_mode`: off→heat) | Fenster-Chip ✓ |
| Sensor eingefroren (heizfähig) | `heat` | `true` | heating | hält Health-Floor | — |
| Vorheizen (optimal start) | `heat` | `true` | heating (nicht PREHEATING) | heizt | Chip „Vorheizen" ✓ |
| Zone deaktiviert | — | `false` | off | — | — |

Die drei ⚠️-Zeilen sind die vom Nutzer beanstandeten bzw. gleichartigen Fälle. Die beiden ⚠️⚠️-Zeilen sind der gemeldete Kern-Defekt.

---

## 3. Befunde im Detail

### D1 — IST-Temperatur: Card zeigt operativ, Entität zeigt Luft (Nutzerbericht 1)

- Card-Mitte, Dial-Punkt, Lampe und Chart zeigen `operative_temperature` (Fallback `current_temperature`); die Entität publiziert als `current_temperature` die Luft-Temperatur. Differenz = `0.5·(T_MRT − T_Luft)` — bei kalten Außenwänden im Winter oder Sonneneinstrahlung im Sommer schnell 0,5–1,5 K. „Nicht immer" (so der Bericht) ist exakt richtig: Bei MRT ≈ Luft stimmen beide überein, sonst nicht.
- Verschärfend: Ein Klick auf die Kartenmitte öffnet den More-Info-Dialog der Entität (`poise-card.ts:162-171, 319-325`) — dort steht die *andere* Zahl direkt neben der Card, ohne dass irgendwo erklärt würde, dass es zwei verschiedene Messgrößen sind. Keine der beiden Zahlen trägt ein Label („operativ" / „Luft"); die Card hat dafür auch keinen Übersetzungsschlüssel (`localize.ts`).
- Konzeptionell ist die Wahl der Card *richtig* (Poise regelt Komfort in operativer Temperatur, ADR-0017) — das Problem ist ausschließlich die fehlende Kennzeichnung und die fehlende Gegenstelle auf Entitätsseite.

### D2 — `hvac_action` = idle bei aktivem Override, obwohl gekühlt/geheizt wird (Nutzerbericht 2)

Ursachenkette:

1. `resolve_write_target()` etikettiert einen aktiven Override wörtlich als `mode = "manual"` (`tick_resolve.py:96-98`).
2. `heating`/`cooling` werden **vor** der Override-Richtungsauflösung aus diesem Roh-Modus berechnet (`coordinator.py:2438-2439`) → bei Override immer `false`.
3. Die tatsächliche Richtung wird danach korrekt bestimmt: `override_mode()` kollabiert das Band auf ±0,5 K um den Haltewert und liefert heat/cool/idle inkl. Capability- und Outdoor-Gates (`control/cooling.py:58-91`, `coordinator.py:2506-2527`); `final_mode` schaltet den Aktor real um (`coordinator.py:2556-2599`). **`final_mode` wird jedoch nicht publiziert.**
4. Die Entität sieht nur `heating == False` und `mode == "manual"` → `HVACAction.IDLE` (`climate.py:239-247`).

Folgen: Die Poise-Entität meldet „Leerlauf", während (a) der Aktor kühlt und (b) dessen eigene Climate-Entität in HA sichtbar „cooling" meldet — zwei Entitäten desselben Systems widersprechen sich sichtbar. Der Defekt betrifft symmetrisch auch **heizende** Overrides. Da die Card die Handle-Farbe aus derselben `hvac_action` bezieht (`poise-card.ts:264-265`), fehlt auch auf der Card jedes Richtungssignal — die Hold-Pill nennt Wert und Restzeit, aber nicht, ob gerade gekühlt oder geheizt wird.

### D3 — `hvac_action` ist generell Absicht, nicht Ist-Zustand

Auch außerhalb des Overrides weicht die Semantik von der HA-Definition („current action") ab:

- `mode == "cool"` → Entität meldet pauschal COOLING, selbst wenn der Kompressor-Guard den Umschalt-Nudge diesen Tick zurückhält (`coordinator.py:2589-2591`) und das Gerät real noch gar nicht kühlt.
- `final_mode == "dry"` (Entfeuchten im Totband) → publiziert wird `mode == "idle"`, die Entität meldet IDLE, obwohl das Gerät aktiv entfeuchtet. HA kennt dafür `HVACAction.DRYING`. Auch die Card zeigt Entfeuchten nirgends aktiv an (nur die Feuchte-Lampe; `dry_active` ist als Attribut da, wird aber nicht gerendert).
- Idle-Park in `fan_only` (Umluft, `tick_resolve.py:334-335`) → IDLE, obwohl der Lüfter läuft (`HVACAction.FAN` existiert).
- Bemerkenswert: Für interne Zwecke nutzt der Coordinator längst den *realen* Gerätezustand mit Intent-Fallback — EKF-Drive (`heat_drive_signal`/`cool_drive_signal`, `tick_resolve.py:202-227`) und Heizausfall-Detektor (`coordinator.py:2457-2462`). Nur die nach außen sichtbare `hvac_action` bleibt auf dem groben Intent-Pfad.

### D4 — Asymmetrischer Publikations-Contract

`heating` wird publiziert, das spiegelbildlich berechnete `cooling` nicht (`coordinator.py:2438-2439` vs. `3198`). Genau diese Lücke zwingt `climate.py` zur fehleranfälligen `mode == "cool"`-Heuristik. Wäre `cooling` (bzw. besser `final_mode`) publiziert, wäre D2 nie entstanden — die Ableitung in der Entität hätte auf ein konsistentes Signal zugreifen können.

### D5 — Erklärlücke der nativen HA-Ansichten

Bei Fenster-offen, Kompressor-Guard, Frost-/Schimmel-Floor oder Lockouts zeigt die native HA-Thermostat-Karte/More-Info nur „Leerlauf"/„Heizen" ohne Grund. Die Poise Card erklärt diese Zustände über Chips (Fenster, Guard, Clamp, Ausfall) — wer aber More-Info oder eine Standard-Karte nutzt, sieht die Diskrepanz ohne Erklärung. Das ist die vom Nutzer formulierte Alternative „entweder visuell erklären oder gleich anzeigen": Aktuell wird auf der Card erklärt, auf der Entitätsseite weder erklärt noch gleich angezeigt.

---

## 4. Erwartungshaltung der Nutzer (Recherche)

1. **HA-Semantik ist eindeutig:** Die Entwickler-Doku definiert `hvac_action` als „the **current action**" — ausdrücklich abgegrenzt vom Modus: Ein Gerät im Modus heat, das das Ziel erreicht hat, heizt *nicht* mehr ([HA Developer Docs: Climate entity](https://developers.home-assistant.io/docs/core/entity/climate/)). Nutzer und Ökosystem erwarten also: heating/cooling ⇔ das Gerät arbeitet jetzt tatsächlich in diese Richtung; idle ⇔ es tut es nicht. Ein manuell veranlasstes, aktives Kühlen ist demnach zwingend `cooling` — die Herkunft des Sollwerts (Schedule vs. Hold) ist für `hvac_action` irrelevant.
2. **Falsche `hvac_action` wird als Bug gemeldet, nicht als Eigenheit toleriert:** Es gibt eine ganze Familie solcher Reports — Nest meldet „off" statt „idle" ([core#62797](https://github.com/home-assistant/core/issues/62797)), Generic Thermostat bleibt fälschlich auf dem alten Action-Wert ([core#110656](https://github.com/home-assistant/core/issues/110656)), die Thermostat-Karte zeigt eine veraltete Action ([frontend#20017](https://github.com/home-assistant/frontend/issues/20017)). Die Erwartungshaltung „Action = Wahrheit" ist im Ökosystem fest verankert.
3. **`hvac_action` ist API, nicht nur Anzeige:** Die offizielle Automations-Bedingung `climate.is_heating` prüft genau dieses Attribut ([HA: Thermostat is heating](https://www.home-assistant.io/conditions/climate.is_heating/)), und verbreitete Muster tracken Heiz-/Kühl-Laufzeiten über `hvac_action`-History ([Beispiel](https://blog.stefandroid.com/2022/11/12/home-assistant-track-heating-cooling.html)). Der Override-idle-Defekt verfälscht also auch Automationen, Laufzeitstatistiken und Energie-Auswertungen — jede Override-Kühlphase fehlt in den Daten.
4. **„Warum"-Erklärungen gehören in eigene Entitäten, nicht in `hvac_action`:** Der Vorschlag, `hvac_action` um einen Grund (`HVACActionReason`: Fenster, Override, Limits …) zu erweitern, wurde vom HA-Architekturrat abgelehnt — Diagnose-Information soll als separate Sensor-Entities am Gerät hängen ([architecture#1064](https://github.com/home-assistant/architecture/discussions/1064)). Für Poise heißt das: `hvac_action` streng standardkonform halten; die Erklärschicht (Chips, ggf. Diagnose-Sensoren) ist der richtige — und bereits eingeschlagene — Weg.
5. **Abweichende „gefühlte" Temperaturen verwirren, wenn sie unmarkiert sind:** Ecobees „Feels like"-Anzeige (Adjust for Humidity) erzeugt genau die hier gemeldete Verwirrung — so regelmäßig, dass ein eigener Support-Artikel existiert ([ecobee: My temperature is inaccurate](https://support.ecobee.com/s/articles/My-ecobee-temperature-is-inaccurate?language=en_US)). Die Lehre ist nicht „keine operative Temperatur zeigen", sondern: die abweichende Größe **kennzeichnen**, den Rohwert zugänglich lassen und beide konsistent halten. Kommerzielle Thermostate (Nest, tado) zeigen im Zweifel die gemessene Lufttemperatur und verstecken Komfortmodelle hinter beschrifteten Features.

---

## 5. Verbesserungsvorschläge (priorisiert)

### V1 — `final_mode` publizieren und `hvac_action` daraus ableiten (Kern-Fix für D2/D3, klein, geringes Risiko)

Der Coordinator kennt die Wahrheit bereits (`final_mode`, unconditional berechnet seit dem F1-Fix); sie muss nur in `_tick_data` (z. B. als `"final_mode"`, plus `"cooling"`-Flag analog `heating` aus `final_mode` statt `mode`) und in die Entität:

```python
# climate.py — Ziellogik (Skizze)
if not enabled: OFF
match final_mode:
    "heat" → HEATING       # inkl. Override-heizt, Frost-/Frozen-Halten
    "cool" → COOLING       # inkl. Override-kühlt
    "dry"  → DRYING        # Entfeuchten sichtbar machen
    _      → FAN wenn fan_only-Park aktiv, sonst IDLE
```

Damit zeigt die Entität beim Override exakt die Richtung, mit der Poise den Aktor umschaltet — der gemeldete Fall ist behoben; `heating`/`cooling` bleiben konsistent zur EKF-/Failure-Logik. Optional in derselben Änderung: `preheating` → `HVACAction.PREHEATING` (die native HA-Karte zeigt dann „Vorheizen" von selbst — ein Erklär-Gewinn gratis).

### V2 — Zweite Stufe: realen Aktor-Zustand bevorzugen (D3 vollständig)

Wie bei `heat_drive_signal`/`actuator_running` die reale `hvac_action` des Aktors nutzen, Intent nur als Fallback: Dann meldet Poise „idle", wenn das TRV-Ventil satt geschlossen ist, und „cooling" erst, wenn der Kompressor (nach Guard) wirklich läuft — die strengste Auslegung der HA-Semantik. Trade-off: hängt an der Melde-Qualität/-Latenz des Geräts; gegen Flattern ggf. kurze Haltezeit. V1 ist ohne V2 bereits ein korrekter, konsistenter Zustand („Intent-basiert, aber richtungstreu"); V2 ist die Kür.

### V3 — IST-Temperatur: kennzeichnen statt angleichen (D1)

Empfehlung zweigleisig:

- **(a) Card:** Die große Zahl als operativ ausweisen und bei relevanter Abweichung (z. B. ≥ 0,3 K) die Luft-Temperatur sekundär zeigen — etwa „21,4° operativ · Luft 22,1°" (neue Übersetzungsschlüssel `operative`/`air`; Tooltip/aria erklärt die Größe). So bleibt die fachlich richtige Regelgröße prominent, und der Sprung zur More-Info-Zahl ist erklärt statt widersprüchlich.
- **(b) Integration:** `operative_temperature` zusätzlich als eigene Sensor-Entität `sensor.<zone>_operative_temperature` anlegen (Diagnose-/Messklasse). Das folgt der HA-Architekturlinie aus architecture#1064, macht die Größe in More-Info, Historie und Recorder-Statistik erstklassig sichtbar und gibt Automationen eine saubere Quelle.

**Nicht empfohlen:** die operative Temperatur als `current_temperature` der Climate-Entität zu publizieren. Das würde die Erwartung „current_temperature = Messwert des Raumsensors" brechen, bestehende Historien stauchen und externe Automationen stillschweigend umdefinieren — der ecobee-Fall zeigt, dass genau daraus Support-Fälle entstehen.

### V4 — Override-Feedback auf der Card vervollständigen (D2-UX)

Mit V1 färbt sich der Dial-Handle beim Override automatisch korrekt (blau/orange). Zusätzlich die Hold-Pill um die Richtung ergänzen — „Manuell 22,0° · kühlt · 45 min" (Icon/Pfeil genügt) — damit die Card den Zustand auch ohne Farbwahrnehmung erklärt. Der Unterbau (`holdView` in `override.ts`) ist pur und leicht erweiterbar.

### V5 — Erklärschicht für die native Ansicht (D5)

Die Gründe existieren als Attribute (`window_open`, `mode_nudge_blocked`, `binding_lower_cause`, `override_active` …). Ein kompakter Diagnose-Sensor „Poise Status/Grund" (z. B. `idle (Fenster offen)`, `cooling (manuell bis 22:00)`) je Zone macht sie in More-Info und Standard-Karten sichtbar — konform zur architecture#1064-Leitlinie, ohne `hvac_action` zu überfrachten.

### V6 — Regressionstests für den Anzeige-Contract

Es gibt derzeit keinen Test, der `PoiseClimate.hvac_action` abdeckt (kein Treffer in `tests/`). Vorschlag: Zustandsmatrix aus §2 als Testtabelle — insbesondere Override×{kühlt, heizt, idle}, dry-im-Totband, fan_only-Park, Fenster, Frozen, Guard-blockiert, disabled. Auf Card-Seite ein Test, dass Handle-Klasse und Hold-Pill der (korrigierten) `hvac_action` folgen, sowie ein Contract-Test „Card-IST == publizierte operative Größe, gekennzeichnet".

### Reihenfolge

1. **V1** (Defekt-Fix, kleine Änderung an Coordinator-Publikation + `climate.py`, sofortige Wirkung auf UI, Automationen, Statistik) + **V6** (Tests dazu).
2. **V3a** (Card-Kennzeichnung — kleine UI-Änderung) und **V4** (Richtungs-Pill) in einem Card-Release.
3. **V3b** (Operative-Sensor) und **V5** (Grund-Sensor) als gemeinsames „Diagnose-Entities"-Paket.
4. **V2** danach, wenn Melde-Latenzen der realen Geräte evaluiert sind.

---

## Nachtrag (2026-07-13): Verifikation der Umsetzung in v0.170.1-alpha

Geprüft wurde der Tag `v0.170.1-alpha` (Commit `d858512`) per Code-Diff gegen den Review-Stand (`e32c1ac`), lokalem Testlauf und CI-Status.

### Korrekt umgesetzt

- **V1 + V2 (in einem Schritt):** Der Coordinator publiziert `final_mode`, `actuator_hvac_action`, `idle_park_mode` und das symmetrische `cooling` (`coordinator.py`, Block „Display contract"). Die Entität leitet `hvac_action` über das neue pure `resolve_hvac_action()` ab (`devices/hvac_modes.py`): reale Geräte-Action als Ground Truth (heating/cooling/drying/fan/idle/preheating/defrosting, case-insensitive), Fallback auf die arbitrierte Richtung — nie mehr das rohe `"manual"`-Tag. Beide gemeldeten Defekte sind damit behoben; zusätzlich korrekt gelöst: Guard-gehaltener Kompressor liest „idle", Entfeuchten liest „drying", fan_only-Park liest „fan", „off"-Meldung des Geräts fällt auf Intent zurück, `ValueError`-Guard für HVACAction-Werte älterer Cores.
- **V3a:** `airHint()` (Schwelle 0,3 K) zeigt die Luft-Temperatur sekundär unter der operativen Zahl („operativ · Luft 22,1°"), inkl. DE/EN-Übersetzungsschlüsseln und `title`-Kennzeichnung.
- **V4:** Hold-Pill nennt die Richtung aus der (jetzt korrekten) `hvac_action` — „Manuell 22,0° · kühlt · 45 min" (`holdDirection()`/`holdView()`).
- **V6:** Zustandsmatrix als pure Tests (`tests/test_hvac_action.py`, inkl. beider Defekt-Fälle), Wiring-Test (`tests/integration/test_hvac_action_wiring.py`), Card-Tests für `holdDirection`/`airHint`. Verifiziert: pure Python-Suite lokal grün, Card-Tests 52/52 grün, `tsc --noEmit` sauber, CI am Tag-Commit grün (inkl. HA-Runtime-Integrationstests; lokal nicht lauffähig, da der HA-Harness Python ≥ 3.12 verlangt).
- **V3b/V5** (Operative-/Grund-Sensor) sind nicht enthalten — entspricht der empfohlenen Reihenfolge (späteres Paket), kein Mangel dieses Releases.

### 🔴 Release-blockierende Regression: `poise-card` wird nicht mehr registriert

Am Ende von `card/src/poise-card.ts` wurde — offenbar beim Einfügen der `.opair`-CSS-Regel am Style-Ende — der komplette nachfolgende Registrierungsblock mit entfernt: `window.customCards.push({type: "poise-card", …})`, `customElements.define("poise-card", PoiseCard)` und das Versions-Logging. Der Build-Einstieg ist genau diese Datei (`build.mjs: entryPoints: ["src/poise-card.ts"]`), und das ausgelieferte Bundle `custom_components/poise/frontend/poise-card.js` wurde nachweislich aus diesem Stand gebaut (es enthält die neuen `opair`/„kühlt"-Features): Es definiert nur noch `poise-card-editor`, `poise-system-card` und `poise-system-card-editor` — **kein `poise-card`**.

**Wirkung:** Jedes Dashboard mit `type: custom:poise-card` zeigt in v0.170.1-alpha den roten HA-Fehler „Custom element doesn't exist: poise-card"; die Card fehlt zudem im Card-Picker. Die korrekt implementierten Card-Verbesserungen (V3a/V4) erreichen so keinen Nutzer; nur die Entitäts-Seite (korrigierte `hvac_action`) ist wirksam. Die System-Card ist nicht betroffen (registriert sich selbst).

**Warum unbemerkt:** Die CI (`ci.yml`) enthält keinen Card-Job (kein `npm test`/`typecheck`), die Card-Unit-Tests importieren nur pure Module (die Registrierung ist ein Modul-Seiteneffekt), und `tsc` bemängelt entfernte Statements nicht.

**Empfehlung (Hotfix v0.170.2):**
1. Registrierungsblock am Ende von `poise-card.ts` wiederherstellen und das Bundle neu bauen.
2. Regressions-Guard: Build-Check in `build.mjs` (nach dem esbuild-Lauf prüfen, dass das Bundle `customElements.define("poise-card"` enthält und sonst mit Fehler abbrechen) — plus Card-Job (`typecheck` + `test` + Build-Check) in der CI.

## Quellen

- [Home Assistant Developer Docs — Climate entity (`hvac_action` = current action)](https://developers.home-assistant.io/docs/core/entity/climate/)
- [HA-Bedingung „Thermostat is heating" (Automationen prüfen `hvac_action`)](https://www.home-assistant.io/conditions/climate.is_heating/)
- [core#62797 — Nest: hvac_action „off" statt „idle"](https://github.com/home-assistant/core/issues/62797)
- [core#110656 — Generic Thermostat: hvac_action kehrt nicht zu idle zurück](https://github.com/home-assistant/core/issues/110656)
- [frontend#20017 — Thermostat-Karte zeigt veraltete hvac_action](https://github.com/home-assistant/frontend/issues/20017)
- [architecture#1064 — HVACActionReason-Vorschlag, abgelehnt zugunsten separater Sensor-Entities](https://github.com/home-assistant/architecture/discussions/1064)
- [ecobee — „My ecobee temperature is inaccurate" (Feels-like-Verwirrung)](https://support.ecobee.com/s/articles/My-ecobee-temperature-is-inaccurate?language=en_US)
- [Laufzeit-Tracking über hvac_action-History (Beispiel)](https://blog.stefandroid.com/2022/11/12/home-assistant-track-heating-cooling.html)
