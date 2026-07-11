# ADR-0059: Override-Lebenszyklus — Gültigkeit, Rückkehr, Feedback & Vorschlags-Lernen für manuelle Eingriffe

**Status:** In Arbeit (70 %) · **Datum:** 2026-07-11 · **Bezug:** ADR-0042 (Override/Preset-Modell, implementiert — wird *erweitert*, nicht abgelöst), ADR-0025 (Zeitplan/Optimal-Start), ADR-0058 (Presence), ADR-0035 (Constraint-Solver), ADR-0016/0040/0057 (Card-Vertrag), ADR-0008 (Config), ADR-0012 (Repair-Issues), ADR-0019 (KNX-Expose, künftig) · **Grundlage:** `docs/Meinungsbild_Manueller-Eingriff-Sollwert-und-Modus.md` (verifizierte Wettbewerbs-/Community-/Norm-Recherche, 2026-07-11)

> **Umsetzungsstand (v0.162.0):** v1 umgesetzt — HoldPolicy (schedule/timer/permanent), Boost-Timer, Presence-Ende, angekündigte Ablaufzeit, Event `poise_override_ended` + Service `poise.resume_schedule`, Feedback-Attribute + Card-Hold-Pill, Config-Sektion + Migration, L1-Erfassung. Offen (v2): L2-Vorschläge, §3 Preheat-Glättung, Feld-Tuning, Live-Verifikation.

## Kontext

ADR-0042 hat den manuellen Sollwert-Override mit **fester 2-h-Auto-Rückkehr** geliefert und die erweiterten Rückkehrregeln („bis nächster Schedule-Punkt", „bis Anwesenheitswechsel"), den Zustandsautomaten mit Ablauf-Attribut und die Card-Anzeige bewusst offen gelassen. Der Ist-Stand (Code-verifiziert):

- `set_override` sanitisiert, klemmt, persistiert Wanduhr-Zeitstempel; Ablauf **stumm** nach fix 2 h im Tick (`coordinator.py:1431-1442`, `control/override.py:52-63`); `OverrideConfig` ist hart kodiert, **kein** Config-Feld (`coordinator.py:333`).
- „Bis nächster Schaltpunkt" fehlt, obwohl `ComfortSchedule.state_at` `minutes_to_setback`/`minutes_to_comfort` bereits pro Tick liefert (`comfort/schedule.py:81-98`) — der Expiry-Check konsumiert sie nicht. Presence-Wechsel (ADR-0058) beendet nichts: ein Boost-Hold heizt nach Verlassen des Hauses bis zu 2 h weiter (nur bandgeklemmt).
- `set_hvac_mode` schreibt den store-owned `climate_mode` **dauerhaft** und löscht den Override auch bei OFF (`climate.py:254-262`); Presets laufen **nie** ab (auch Boost +1,5 K hält unbegrenzt).
- Feedback: nur `override_clamped` und `mode='manual'` sind im Card-Vertrag; `override_active`/`preset` liegen im Tick-Dict, fehlen aber in `_ATTRS` (der Preset-Fallback-Chip in `poise-card.ts:433-435` ist toter Code). **Kein** Ablauf-Attribut, kein Countdown, keine Resume-Aktion, der Wunschwert vor der Klemme wird verworfen (`coordinator.py:497`).

Die Recherche (Meinungsbild) ergibt einen klaren Korridor: Markt-Default ist „bis zum nächsten Schaltpunkt" (Nest, evohome, Wiser, HmIP-Auto, FRITZ, Bosch, Danfoss, Eve); fester Timer ist das gewünschte Sicherheitsnetz (Netatmo 3 h/5 min–12 h; VTherm #1875 „heating on high all night"); ecobees unbegrenzter Werksdefault und HmIPs unsichtbarer Dauer-MANU sind die dokumentierten Gegenbilder. Stilles Lernen aus Eingriffen ist der dokumentierte Fehlschlag der Kategorie (Nest Auto-Schedule → Googles eigener Schwenk auf bestätigungspflichtige „Suggestions"; ThermoCoach: Vorschläge sparen 12,4 % mehr als Nest-Lernen). Matter 1.4 normiert das Zielbild: Hold mit Dauer, `SetpointHoldExpiryTimestamp` als Ablauf-Attribut, `SetpointChangeSource` (Manual/Schedule/External) gegen Lern-Feedback-Schleifen.

## Entscheidungstreiber

1. **Beide Community-Forderungen gleichzeitig erfüllen:** Eingriffe garantiert respektieren (kein Sekunden-Revert — BT#1700/scheduler#316-Klasse) UND garantiert vergessen (kein klebender Override — VT#1875/HmIP-MANU-Klasse).
2. **Norm-Treue bleibt unantastbar:** jeder Eingriff läuft weiter durch den Präzedenz-Solver (ADR-0035); Frost-/Schimmel-Floor und ASR-Deckel sind nie verhandelbar.
3. **Determinismus & Testbarkeit** (ADR-0011/0014): Rückkehrregeln als pure, test-first Zustandslogik; dokumentierte Wettbewerber-Fehlerklassen werden zu Regressionstests.
4. **Ein Wahrheitswert** (ADR-0016/0042 §6): Card liest exakt das, was der Coordinator entscheidet — inklusive Ablaufzeit.
5. **Interop-Anschluss:** Attribut-Semantik kompatibel zu Matter (`HoldDuration`/`ExpiryTimestamp`/`ChangeSource`) und KNX (DPT 20.102, begrenzte Sollwertverschiebung) für ADR-0019.

## Betrachtete Optionen

**Q1 Gültigkeit:** (a) feste Dauer wie heute (Netatmo-Modell; einfach, aber ignoriert den Zeitplan — ein 21:55-Override läuft stur bis 23:55 statt am Setback-Beginn 22:00 zu enden); (b) unbegrenzt bis Widerruf (ecobee-Werksdefault; dokumentierte „stuck in hold"-Fehlerklasse — verworfen); (c) fest „bis nächster Schaltpunkt" ohne Timer (HmIP/FRITZ; ohne Zeitplan kein Ablauf, kein Sicherheitsnetz); (d) **konfigurierbare Rückkehrregel mit kontextuellem Default + Sicherheitsnetz** (ecobee-Optionen × tado-Dreiteilung × Matter-Hold) — gewählt.

**Q2 Lernen:** (a) stilles Lernen (Nest Auto-Schedule — am Markt gescheitert, verworfen); (b) gar nichts (Marktstandard tado/HmIP/evohome — verschenkt Poises Datenlage); (c) **beobachten → vorschlagen → bestätigen** (ecobee Schedule Assistant, Nest 4. Gen Suggestions, ThermoCoach) — gewählt, gestaffelt.

**Q3 Rückkehr:** (a) harter stiller Sprung (Markt-Standard — akzeptiert, aber verbesserbar); (b) Sollwert-Rampe (kein Wettbewerber; regelungstechnisch redundant zum Solver); (c) **angekündigter Sprung + physikalische Glättung via Optimal-Start** (Danfoss `schedule_with_preheat`-Muster mit Poises besserer EKF-Physik) — gewählt.

**Q4 Feedback:** (a) nur Zustands-Icon (tado-Gerät/HmIP — erklärt Ablauf nicht); (b) **Restzeit + Abbruch + Ablauf-Attribut + Warum** (ecobee-Bubble/VTherm-Card + Matter-`ExpiryTimestamp` + FRITZ-`nextchange`) — gewählt.

**Q5 Doku:** (a) fragmentierte Hilfe-Artikel (Nest, 8+ Artikel — nachweislich unzureichend); (b) **eine Verhaltens-Sektion mit Prioritätenkette + Erklärung im Moment des Eingriffs** — gewählt.

## Entscheidung

### 1. Rückkehrregel (`HoldPolicy`) statt fixer Frist — pure Zustandslogik in `control/override.py`

Jeder manuelle Sollwert-Override trägt eine explizite Rückkehrregel; der Ablauf-Check wird eine pure Funktion `hold_expired(policy, set_at, now, next_switchpoint, presence_transition)`:

- **`schedule` (Default bei konfiguriertem Komfortfenster):** endet am **nächsten Schaltpunkt** (Setback-Beginn *oder* Komfort-Beginn, aus `minutes_to_setback`/`minutes_to_comfort`), **wertunabhängig** (tado-16475-Falle: Ende am Zeitpunkt, nie am Temperaturdelta). Zusätzlich gedeckelt durch `override_max_h` (Sicherheitsnetz, Default 8 h) für den Fall langer fensterloser Strecken.
- **`timer` (Default ohne Zeitplan = heutiges Verhalten):** feste Dauer, konfigurierbar 0,5–24 h (Default 2 h, Matter-Korridor ≤1440 min).
- **`permanent`:** bewusste Opt-in-Option (ecobee/„Urlaubs"-Fälle); niemals stiller Default.
- **Presence-Ende (orthogonaler Zusatz, Default an):** ein **Haus-Gate-Wechsel** (ADR-0058 `home` kippt in beliebiger Richtung) beendet den Override sofort — die tado-V3+-Semantik („until next automatic change" endet am Home/Away-Wechsel); Raum-Occupancy beendet **nichts** (PIR-Asymmetrie). Wer tado-X-Verhalten will (manuell schlägt Away), schaltet die Option ab.

**Stacking-Regeln (Fehlerklassen aus dem Feld):** Ein erneuter manueller Eingriff während eines aktiven Overrides ersetzt Wert und startet die Frist neu, **verändert aber nie das Rückkehrziel** — Rückkehrziel ist immer der Plan/Preset-Zustand, nie ein früherer Manualwert (VT#1961). Der Ablauf wird auch vollzogen, während ein anderer Layer (Fenster, Frozen-Sensor) aktiv ist — der Override wird dann still gelöscht und der Layer regelt weiter (Schedy#35; heutiges Poise-Verhalten, wird als Regressionstest festgeschrieben). Die Solver-Präzedenz (ADR-0035) garantiert weiterhin, dass ein Schaltpunkt niemals einen Kontext-Override (Fenster/Frost) aushebelt (VT#537).

### 2. Presets & Modus

- **Boost wird timed:** Boost erhält als einziges Preset eine Ablauffrist (`boost_duration_min`, Default 60 min, Korridor 15 min–3 h — Wiser/tado/TRVZB-Umfeld) und restauriert das **beim Aktivieren eingefrorene** Vorgänger-Preset (VT#1961-Guard). Eco/Comfort/Away bleiben Zustandswahl ohne Frist (Away endet über Presence, ADR-0058).
- **HVAC-Moduswechsel bleibt persistent** (Markt-Konsens Nest/ecobee: Modus ist Konfiguration, kein Override; ecobees Schedule-Datenmodell kann den Modus strukturell nicht ändern — dieselbe saubere Trennung gilt für Poise). Die HmIP-„MANU-Falle" existiert bei Poise nicht, weil es keinen dauerhaften Manu-Sollwert-Modus gibt. **Korrektur im Detail:** `set_hvac_mode(OFF)` löscht den Override künftig **nicht** mehr (heute `climate.py:261` immer) — „aus + später mit Hold weiter" wird möglich; nur ein *aktiver* Moduswechsel (heat/cool/auto) beendet ihn.
- **Kein Modus-Auto-Revert in v1** (kein Wettbewerber hat ihn; der Foren-Bedarf betrifft HmIPs Sollwert-MANU, das Poise nicht kennt). Offen für v2: Hinweis-Repair bei saisonwidrigem `heat_only`/`cool_only`.

### 3. Rückkehr zur Automatik: angekündigt, atomar, physikalisch geglättet

- Der Rücksprung bleibt ein **atomarer Solver-Übergang im Tick** (keine Sonderpfade, keine künstliche Sollwert-Rampe — Markt-Standard, akzeptiert solange sichtbar).
- **Passive Ankündigung ab dem Moment des Eingriffs:** Ablaufzeitpunkt ist von Anfang an sichtbar (Attribut + Card, s. §4) — das ecobee/Netatmo/FRITZ-`nextchange`-Muster ersetzt aktive Benachrichtigungen.
- **Physikalische Glättung:** endet ein Override per `schedule`-Regel am Beginn eines Komfortfensters, gilt der **Preheat-Start als Schaltpunkt** — liegt das Optimal-Start-Ziel über dem Override, endet der Override bereits bei `start_now`, sodass der Raum zur Komfortzeit warm ist (Danfoss-`schedule_with_preheat`-Semantik mit ADR-0025-Physik; tados Gegenteil — Early-Start-Unterdrückung — erzeugt dokumentiert kalte Blockstarts).
- **Event `poise_override_ended`** (`reason: expired_timer | schedule_point | presence_change | user_resume | mode_change`) für Automationen (Netatmo-Webhook-Muster); kein Bestätigungsdialog, keine Push-Pflicht.

### 4. Feedback: ein Wahrheitswert, Restzeit, Warum, Ein-Klick-Rückkehr

- **Neue Vertrags-Attribute** (`_ATTRS`, ADR-0016-Muster wie `mould_floor`): `override_active` (Fix des toten Chips), `override_expires_at` (ISO-Zeitstempel, `SetpointHoldExpiryTimestamp`-Analogon; null bei `permanent`), `override_policy`, `override_requested` (Wunschwert **vor** der Klemme — heute verworfen, `coordinator.py:497`), `preset`, `boost_expires_at`.
- **Card:** Hold-Pill nach ecobee/VTherm-Vorbild — Hand-Icon (tado-Ikonografie) + „Manuell 22,5° · noch 45 min" + **X = „Zeitplan fortsetzen"** (`set_override(None)`); Countdown über die vorhandene Minuten-Chip-Mechanik (`poise-card.ts:473-479`, wie preheating/coasting). `override_clamped` wird erklärend: „22,5° statt 24° (Normgrenze)" statt nur „Sollwert geklemmt". Beim Verstellen am Dial erscheint sofort die Gültigkeit („gilt bis 22:00") — **Erklärung im Moment des Eingriffs, die kein Wettbewerber bietet**.
- **Service `poise.resume_schedule`** (Zone oder alle Zonen — evohome-`AutoWithReset`/tado-„Resume all rooms"-Muster) für Voice/Automation/Dashboard.
- i18n vollständig: `localize.ts` EN/DE + `strings.json`/`de.json` (ADR-0021).

### 5. Lernen: beobachten → vorschlagen → bestätigen (nie still)

- **Grundsatz (normativ für alle Folge-ADRs):** Manuelle Eingriffe sind **Ausnahmen, keine Trainingssignale**; kein Poise-Mechanismus verschiebt still Komfortbasis, Zeitplan oder Preset-Offsets (Yang/Newman „exception flagging"; Matter-Preset-Semantik: Override nullt das Preset, ändert nie seine Definition).
- **Stufe L1 — erfassen (mit v1):** pro Zone eine kontextgefilterte Override-Statistik (Diagnose, persistiert): Zeitpunkt, Richtung, `override_requested`-Delta zur effektiven Basis, Schedule-Phase, Presence-Level. Gezählt wird nur der **Nutzerpfad** (`climate.set_temperature`/Card/Service) — nie eigene Writes; Eingriffe während `AWAY`/Urlaub/Fenster-offen werden markiert und vom Muster ausgeschlossen (Nest-Urlaubs-Fehlerklasse; Matter-`SetpointChangeSource`-Prinzip Manual≠External).
- **Stufe L2 — vorschlagen (v2):** erkennt die Statistik ein **Mehr-Tages-Muster** (≥3 gleichgerichtete Eingriffe ≥0,5 K in derselben Schedule-Phase innerhalb von 14 Tagen — Nest-Patent-Zweiphasenprinzip, konservativ), erzeugt Poise ein **Repair-Issue mit Fix-Flow** (ADR-0012): „Abends wurde 3× auf +1 K erhöht — Komfortbasis um 0,5 K anheben?" bzw. „Komfortfenster 30 min früher beginnen?". Vorschlags-Schrittweite ≤0,5 K bzw. ≤30 min, Ergebnis bleibt norm-geclampt (ADR-0027). Annahme ändert die Config sichtbar (Reconfigure-Pfad), Ablehnung unterdrückt das Muster 30 Tage. Feature als Ganzes abschaltbar; Löschen der Statistik löscht sie wirklich (Nest-Artefakt-Lehre).
- **Nie in Scope:** EKF/MPC lernen weiterhin ausschließlich Physik; die CA-Metrik pausiert bei Override (bestehendes Verhalten).

### 6. Konfiguration (ADR-0008, Options-Sektion „Manuelle Eingriffe")

`override_policy` (schedule | timer | permanent; Default „schedule, ohne Zeitplan timer") · `override_timer_h` (0,5–24, Default 2) · `override_max_h` (Deckel für `schedule`, Default 8) · `override_end_on_presence_change` (bool, Default an) · `boost_duration_min` (15–180, Default 60) · `override_suggestions` (bool, Default an, nur L2). Alle hot-apply-fähig; ecobees „askMe" wird bewusst **nicht** portiert (HA-UI kann beim Eingriff nicht modal fragen — dafür ist die Gültigkeit sofort sichtbar).

### 7. Dokumentation (Q5)

- **README-Sektion „Manuelle Eingriffe & Rückkehr zur Automatik"** (+ Spiegel in `card/README.md`): eine Tabelle *Eingriff → gilt bis → wie beenden* + die Prioritätenkette (Fenster/Frost/Schimmel > manueller Sollwert > Preset > Zeitplan/Presence) — die Ebenen-Konflikte sind der Top-Stolperstein aller Wettbewerber. Verhaltensänderungen an Defaults nur mit Release-Note/Migration (tado-„wtf"-Lehre), Migration bestehender Installationen: `timer/2 h` (exakt heutiges Verhalten), `schedule` nur für neue Einrichtungen als Default.
- **In der UI selbst** (incidental intelligibility): Gültigkeit beim Eingriff, Restzeit als Chip, Klemmgrund im Klartext.
- **Dieser ADR** dokumentiert die Architektur; die Statistik-/Vorschlagsmechanik erhält bei Umsetzung von L2 einen Nachtrag oder Folge-ADR.

## Begründung

Gegen (a)/(b)-Optionen: Die fixe Frist ignoriert den Zeitplan (der 21:55-Fall), der unbegrenzte Default ist die am besten dokumentierte Fehlerklasse des Markts („stuck in hold", MANU-Falle). Der kontextuelle Default („Schaltpunkt, sonst Timer") reproduziert die Erwartung der deutschen Gerätewelt (HmIP/FRITZ/Bosch/Danfoss) und behält das VT#1875-Sicherheitsnetz, das ADR-0042 bereits richtig gesetzt hat. Vorschlags-Lernen statt stillem Lernen folgt dem einzigen quantitativen Feldbeleg (ThermoCoach +12,4 % vs. Nest) und Googles eigener Kurskorrektur; Poises Alleinstellung bleibt, dass jeder Vorschlag norm-geclampt ist (Offset-Modell ADR-0042 §1). Die Rückkehr-Glättung über Optimal-Start nutzt vorhandene, harness-validierte Physik statt neuer Regelmechanik. Das Feedback-Modell übernimmt das Beste aus ecobee (Bubble), VTherm-Card (Restzeit+X), FRITZ (`nextchange`) und Matter (`ExpiryTimestamp`) — und schließt mit der Warum-Anzeige die im gesamten Feld dokumentierte Lücke.

## Konsequenzen

**Positiv:** kein klebender und kein stur-2-h-Override mehr; Presence-Kopplung schließt das „Boost heizt leeres Haus"-Loch; Card erklärt erstmals Zustand *und* Zukunft („bis 22:00"); Lernen wird möglich, ohne Vertrauen zu riskieren; Attribut-Semantik ist Matter/KNX-anschlussfähig (ADR-0019). **Negativ/Kosten:** mehr Zustandslogik (HoldPolicy × Presence × Fenster — beherrscht durch pure test-first Automaten + die Fehlerklassen-Regressionstests); zwei neue Options-Felder-Gruppen (Konfigurationsfläche wächst); L2-Vorschläge brauchen sorgfältige Schwellen-Tuning-Runde am Feld-Trace, sonst Vorschlags-Spam; Boost-Timer ändert dokumentiertes Verhalten (Migration nötig). Reihenfolge: nach Abschluss ADR-0058-Restpunkte (Presence-Level ist Eingang der Presence-Ende-Regel).

## Verifizierung (geplant)

- `control/override.py`: `hold_expired`-Zustandsautomat pure + Tests: Schaltpunkt-Ende wertunabhängig; Timer-Deckel; Presence-Flanke beidseitig; Doppel-Override friert Rückkehrziel ein (VT#1961-Klasse); Ablauf bei aktivem Fenster-Layer → Plan, nie Manualwert (Schedy#35-Klasse); OFF löscht Hold nicht mehr.
- `tests/test_tick_resolve.py`-Erweiterung: Solver-Präzedenz Kontext-Override > Schaltpunkt (VT#537-Klasse); `override_requested` überlebt die Klemme als Attribut.
- Card-Unit-Tests (`card/test`): Hold-Pill rendert aus `override_expires_at`, X ruft `set_override(None)`-Service, toter Preset-Chip reaktiviert.
- Integration: Restart-Persistenz von Policy + Ablaufzeit (Wanduhr, Review-C5-Muster); Event-Emission je `reason`.
- L1-Statistik: Golden-File-Replay über Feld-Traces (ADR-0011) — kein Eintrag aus Poise-eigenen Writes.

## Compliance

Alle Wettbewerber-Mechaniken wurden aus öffentlicher Doku/Quellcode **konzeptionell** übernommen und eigenständig nachimplementiert (kein Code-Copy; Quellen im Meinungsbild). Keine gerätespezifischen Sonderwege im Kern: HoldPolicy, Statistik und Attribute sind geräteneutral; Matter/KNX-Bezüge sind Semantik-Anleihen, keine Protokollabhängigkeit. Norm-Klemmen (ADR-0027/0035) bleiben für jeden Pfad — auch Vorschläge — unumgehbar.

## Verknüpfungen

Erweitert ADR-0042 (dessen „OFFEN"-Punkte hiermit entschieden sind) und ADR-0016/0040/0057 (Card-Vertrag um Override-Attribute). Konsumiert ADR-0025 (Schaltpunkte, Optimal-Start als Rückkehr-Glättung) und ADR-0058 (Haus-Gate als Ende-Trigger). Liefert die Ablauf-/Quelle-Semantik für ADR-0019 (KNX: DPT 20.102 Auto=0 als Resume, begrenzte Sollwertverschiebung, Ablaufzeit analog `SetpointHoldExpiryTimestamp`). Folge-Entscheidungen: L2-Schwellen-Tuning (Nachtrag nach Feld-Traces), optionaler Modus-Saison-Hinweis (v2), Frost-/Aus-Preset (ADR-0042 §4, weiterhin offen).
