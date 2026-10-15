# ADR-0034: Optimal-Stop — vorausschauendes Ausrollen (Coast-down)

**Status:** Implementiert · **Wirkung:** Live-A · **Datum:** 2026-06-21, Nachtrag N1 2026-10-15 · **Bezug:** ADR-0025 (Zeitplan/Optimal-Start), ADR-0003 (Restwärme/Re-Entry-Klasse K5), ADR-0024 (EKF-`identified`), ADR-0032 (Closed-Loop) · **Verifizierung:** eigene EKF-Physik; Coast-Inversion **gegen RC-Plant validiert** (`tests/test_closed_loop.py::test_optimal_stop_coast_matches_plant`)

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

## Nachtrag N1 (2026-10-15, v0.196.2): Ausrollen nur vom Komfortziel, τ-Vertrauensgate

**Befund (Live, 10 Tage, alle fünf Zonen einer Wohnung):** Das Bad stand werktags das ganze Morgenfenster (05:30–07:00) auf `coasting`, Sollwert 20 °C statt 23 °C, bei 19,9–20,3 °C Raumtemperatur; das Ankleidezimmer ebenso. Zwei Ursachen greifen ineinander:
1. **Engage ohne Ausgangsniveau.** `coastdown_minutes` liefert 0, wenn der Raum schon an/unter `coast_lower` liegt, und eine lange Ausrollzeit bei kleinem α — beides ergibt `stop_now`. Optimal-Stop hat damit aus einem Raum **unter** dem Komfortziel ausgerollt; der Latch hielt die Basis danach bis Fensterende an der unteren Kante.
2. **`identified` sagt nichts über τ.** Das Gate zählt Beobachtungen und prüft die Temperatur-Kovarianz. In allen Zonen pendelte τ täglich zwischen ~20 h und dem 200-h-Anschlag (Anschlag 3,5–16,6 % der Zeit, 2–20 Recovery-Resets auf den 6,7-h-Prior); `identified` blieb durchgehend True. Ursache ist das 1R1C-Modell mit Außenluft als einziger Senke: beheizte Nachbarräume halten eine nicht heizende Zone warm, das Modell deutet das als nahezu perfekte Dämmung (eigene Folgeversion).

**Entscheidung:**
1. **Engage-Bedingung:** Ausrollen beginnt nur, wenn der Raum das Komfortziel erreicht hat (`room ≥ comfort_base − COAST_READY_BAND_K`, 0,3 K). Der Halte-Latch bleibt unverändert — nach dem Einstieg soll der Raum ja unter das Ziel fallen.
2. **τ-Vertrauensgate** `estimation/tau_trust.py`, gehalten im EKF (`ThermalEKF.tau_trust`, persistiert in dessen `to_dict`): τ gilt als vertrauenswürdig, wenn seit dem letzten Ereignis mindestens **24 h** beobachtet wurden und τ in dieser Zeit innerhalb eines **Faktors 2** blieb (max/min über Stundenbuckets). Ereignisse, die den Datensatz leeren: τ **nahe einer Schranke** (≥ 150 h bzw. ≤ 1 h; Klemmung 0,5–200 h) und ein **Recovery-Reset** (`_runtime_recovery` meldet ihn jetzt zurück). Beobachtungslücken > 10 min zählen nicht als Beobachtungszeit. Ein Speicherstand ohne `tau_trust` (Upgrade) startet untrauenswürdig.
3. **Gate für die Planer:** `ThermalEKF.planning_ready = identified ∧ tau_trust.trusted` ersetzt `identified` als Freigabe von Optimal-Start **und** Optimal-Stop in `plan_preheat`. Andere `identified`-Nutzer (Forecast-Abruf, Fenster-Schwelle, Shadows) bleiben unverändert.
4. **Diagnose:** Climate-Attribut `tau_trusted` (nicht im Recorder).

**Konsequenzen:** Bei dem gemessenen τ-Verhalten bleibt Optimal-Start/-Stop in allen Zonen vorerst aus: der Setback endet zur Komfortzeit (kein Vorheizen), am Fensterende wird bis zum Schluss geheizt. Das ist bewusst konservativ — ein Vorlauf aus einem τ, das sich täglich um den Faktor 10 ändert, ist geraten. Wieder freigegeben wird automatisch, sobald eine Zone 24 h stabil lernt; die eigentliche Abhilfe ist das Modell mit zweiter Senke (Folgeversion). `tau_settle` (90-min-EWMA, nur Lernticks) bleibt Diagnose — ein am Anschlag klebendes α wirkt dort „settled".
