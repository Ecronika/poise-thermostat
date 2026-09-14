# Feldbefund 2026-09-14: Poise adoptiert den eigenen Schreibwert als Handverstellung (Küche)

**Status:** **nur festgehalten, nicht behoben** — vorgemerkt hinter der Lüftungsachse · **Quelle:** laufende Instanz v0.194.3, Zone „Küche TRV", Recorder + Config-Entry-Diagnose, 2026-09-14 · Alle Zeiten UTC (lokal +2 h)

## 1. Was passiert ist

| Zeit (UTC) | Ereignis |
|---|---|
| 19:00:24 | Zeitplan → `setback`; Poise entscheidet 15,2 °C und schreibt |
| 19:00:29 | TRV meldet **15,2** — der Befehl kommt an |
| 19:00:30 | TRV meldet **15,0** — das Gerät rastet selbst nach |
| 19:01:24 | nächster Tick: Poise liest 15,0 und **adoptiert** → `device_adopt_setpoint` |

Zonenzustand danach: `override_active: true`, `override_reason: "device_adopt_setpoint"`, `override_requested: 15`, `override_clamped: true` (auf 15,2 geklemmt), `override_policy: "schedule"`, Ablauf `2026-09-15T03:01:24Z`. Override-Statistik: `delta −4`, `phase: setback`. Ein Phantom-Hold über die ganze Nacht, ohne dass jemand am Rad gedreht hat.

## 2. Warum beide Sperren versagen

Die Küchen-TRV meldet `target_temp_step: 0.1`, rastet real aber auf 0,5.

* **Echo-Prüfung.** Deadband ist `max(WRITE_DEADBAND_C, step)` = `max(0,2, 0,1)` = **0,2**. Der Rest ist |15,0 − 15,2| = **exakt 0,2**, und die Prüfung ist ein striktes Kleiner: `0.2 < 0.2` → False. Sie verfehlt den Fall um genau den Wert, mit dem sie vergleicht.
* **Echo-Fenster-Ausnahme.** Innerhalb von 120 s gilt ein Wert als beweisbare Nutzeränderung, wenn er sich von der **Vor-Schreib-Lesung** unterscheidet: `pre_write_sp` = 19,0, |15,0 − 19,0| = 4,0 ≥ 0,2 → `adopt`. Sie vergleicht nicht gegen das, was wir geschrieben haben — dass unser eigener Schreibvorgang den Wert dorthin bewegt hat, kann sie nicht sehen.
* **Context-Gate (Layer 1).** Der Sprung auf 15,2 trägt Poises Kontext; die Nachrastung auf 15,0 eine Sekunde später kommt vom Gerät und trägt ihn nicht.

**Zwei Pfade, dieselben 0,2 K, gegensätzliche Urteile:** die Konvergenzprüfung nimmt `convergence_tolerance(step)` = `max(0,5, 0,1)` = 0,5 und meldet „konvergiert" (`sp_diverged_writes: 0`), die Adoption nimmt 0,2 und meldet „der Nutzer war dran".

## 3. Mit ehrlich gemeldeter Rastung wäre es nicht passiert

Bei `target_temp_step: 0.5` hätten **zwei unabhängige** Sperren gegriffen:

1. `snap_to_step(15.2, 0.5)` = **15,0** — Poise hätte den Wert selbst gerastet, das Gerät hätte nichts nachzurasten gehabt. Der Docstring nennt genau diesen Fall.
2. Der Deadband wäre `max(0,2, 0,5)` = 0,5 gewesen → jeder Rest unterhalb eines Geräteschritts liest sich als `command_echo`. Der Kommentar an dieser Stelle nennt „21.5 → 21.8 auf einem 0,5-K-Raster" als den Fall, den der Step-Anteil fangen soll.

**Die Ursache ist damit nicht der 0,2-Randfall, sondern die Quelle.** Beide Sperren sind mit demselben `step` parametriert, und `step` kommt ungeprüft aus der Selbstauskunft des Geräts. Sie sind nicht unabhängig — sie fallen gemeinsam aus, sobald ein Gerät ein feineres Raster meldet, als es einhält.

Verschärfend: **Poise misst die echte Rastung bereits.** Das M3-Advisory (ADR-0073, `quantization_settle_delta`) meldet genau dann, wenn das Gerät wiederholt weiter vom Befehl zur Ruhe kommt, als sein deklarierter Schritt erklären kann; die Diagnose führt `declared_step: 0.1`. Das Wissen entsteht — es fließt nur nicht auf die Toleranzen zurück, die es bräuchten.

## 4. Drei mögliche Korrekturtiefen

1. **`<=` statt `<`** in der Echo-Prüfung — schließt nur diesen Randfall.
2. **Echo-Fenster-Ausnahme zusätzlich gegen `last_written_sp`** prüfen, nicht nur gegen `pre_write_sp` — schließt die Klasse „unser eigener Schreibwert wird adoptiert".
3. **Beobachteten Schritt aus dem M3-Advisory als effektiven `step` zurückspeisen** — schließt die Ursache, ist aber eine Zustandsänderung mit Einlaufzeit und braucht eine eigene Entscheidung.

## 5. Einordnung

Die Küche ist die Testzone mit absichtlich falsch gemeldeter Rastung; im Feld trifft der Fall Geräte, die ein feineres Raster bewerben, als sie einhalten. Die Wirkung ist ein Phantom-Hold bis zum Ablauf der Hold-Policy — hier harmlos, weil 15 dem Setback-Sollwert entspricht, aber die Zone folgt in dieser Zeit keiner Zeitplan- oder Schutzanpassung und die Karte zeigt eine Handverstellung, die nie stattgefunden hat.
