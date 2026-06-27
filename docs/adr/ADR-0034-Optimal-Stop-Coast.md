# ADR-0034: Optimal-Stop — vorausschauendes Ausrollen (Coast-down)

**Status:** Implementiert · **Datum:** 2026-06-21 · **Bezug:** ADR-0025 (Zeitplan/Optimal-Start), ADR-0003 (Restwärme/Re-Entry-Klasse K5), ADR-0024 (EKF-`identified`), ADR-0032 (Closed-Loop) · **Verifizierung:** eigene EKF-Physik; Coast-Inversion **gegen RC-Plant validiert** (`tests/test_closed_loop.py::test_optimal_stop_coast_matches_plant`)

## Kontext
Optimal-Start (ADR-0025) heizt vorausschauend zum Komfortbeginn vor. Das symmetrische Gegenstück fehlte: am **Fensterende** weiter auf Komfort zu heizen verschenkt Energie, weil die Wärmemasse den Raum noch trägt. `optimal_stop.residual_fraction` existierte, ist aber ein MPC-**Störterm**, kein schedule-seitiger Ausroll-Entscheider. `ScheduleState` kannte nur die Zeit bis Komfort**beginn**, nicht bis Fenster**ende**.

## Entscheidung
1. **Schedule:** `ScheduleState.minutes_to_setback` (Minuten bis das laufende Komfortfenster endet; 0 im Setback) — Spiegel von `minutes_to_comfort`.
2. **Coast-Physik** `control/optimal_stop.coastdown_minutes`: geschlossene Inversion der ZOH-Abkühlung mit Heizung AUS. Mit `t_eq = t_out + β_s·q_solar/α` ist die Ausrollzeit `t = −ln((T_target−t_eq)/(T0−t_eq))/α`. Kühlt das Gleichgewicht nicht unter das Ziel (`t_eq ≥ Ziel`) → **None** (kein Ausrollen, weiterheizen). `advise_stop` meldet `stop_now`, sobald die Fensterende-Deadline in der Ausrollzeit liegt.
3. **Plan:** `plan_preheat` erhält einen Komfort-Zweig: wenn `optimal_stop` ∧ `can_heat` ∧ `identified` ∧ nahe Fensterende → effektive `base` früh auf die **untere Komfortkante** (`coast_lower = heat_lower`) gesenkt; der Raum rollt aus und landet zum Fensterende an der Komfortkante. Rein **beratend** (nur Sollwert-Fahrplan), kein zweiter Schreiber → K5-frei.
4. **Verdrahtung:** Coordinator exponiert `coasting` + `minutes_to_setback`. Optimal-Stop ist vorerst an das `optimal_start`-Flag **gekoppelt** (beides „prädiktive Zeitsteuerung"); ein eigener Schalter ist ein trivialer Folgesplit.

## Begründung
Dieselbe code-verifizierte EKF-Physik wie Optimal-Start/MPC (keine Heuristik). Das `identified`-Gate hält Optimal-Stop im Sommer/uneingelernt inaktiv. Die untere Komfortkante als Ausrollziel bleibt **innerhalb** EN-16798 — der Nutzer kühlt nie unter Komfort, spart aber die letzte Heizphase. Closed-Loop bestätigt: vorhergesagte Ausrollzeit trifft die Plant auf < 0,3 K genau.

## Konsequenzen
**Positiv:** prädiktives Zeitsteuerungs-Paar (Start + Stop) vollständig, energiesparend, K5-frei, gegated, harness-validiert. **Negativ/Offen:** (a) ein Komfortfenster/Tag (erbt ADR-0025-Grenze). (b) Konstant-Außen über die kurze Ausrollzeit (Forecast-Verfeinerung wie bei Optimal-Start möglich, aber über < 1 h Vorlauf vernachlässigbar). (c) eigener `optimal_stop`-Config-Schalter aufgeschoben. (d) `residual_fraction` (MPC-Störterm) bleibt separat und weiterhin unverdrahtet bis MPC aktiv.
