# ADR-0044: Outcome-Scoring — ts-vs-obs-Selbstvalidierung

**Status:** akzeptiert (Umsetzung: pure Kern + Stats jetzt, Coordinator-Lifecycle als Glue, scharf sobald geheizt wird) · **Datum:** 2026-06-24 · **Bezug:** ADR-0002/0028 (EKF/seasonless für „expected"), ADR-0025 (Optimal-Start liefert Heizdauer-Erwartung), ADR-0026 (Schatten-Prinzip), ADR-0011 (Test-first) · **Grundlage:** `Konzept_Best-of-Integration.md` Feat 3; ThermoSmart `learning_engine.py`/`_calc_outcome_score` (quellcode-verifiziert, `Mikasmarthome/ThermoSmart`)

## Kontext
Das Konzept benennt **Outcome-Scoring** als das im ganzen Feld **einzigartige** Selbstvalidierungs-Feature: bewertet jede Heizsession und taggt sie `ts` (Regler aktiv) vs `obs` (nur beobachtet) → echtes A/B, ob die eigene Steuerung Mehrwert bringt. Es erschließt zudem die Konzept-Synergie #2: erst damit wird *messbar*, ob die (winter-scharfzuschaltende) Aktorik TPI/PI/MPC wirklich besser ist als Nichtstun. **Quellcode-verifiziert (ThermoSmart `learning_engine.py`):** `raw = reached·0.40 + speed·0.35 + accuracy·0.25`, dann `× Reliability-Discount` (Solar-Floor 0.60 ab ~400 W/m², Warm-Floor 0.70 ab 15 °C), Speed difficulty-adjustiert (kalt/Wind/Feucht/Regen machen die Erwartung nachsichtig), Session-Start bei `target−temp>0.5`, Ende bei reached/Timeout-90min/interrupt, <3 min verworfen, `controller="ts"|"obs"`.

## Entscheidung
1. **Pure Helfer `control/outcome_scoring.py` (test-first):** `outcome_score(...)` (reached/speed/accuracy + `env_discount`), `session_end_reason(...)` (reached/timeout/interrupt), `OutcomeStats` (laufender Mittel je `ts`/`obs`, persistierbar). Methode 1:1 aus dem verifizierten ThermoSmart-Code re-implementiert (kein Copy), **adaptiert auf Poises normalisiertes `q_solar` [0,1]** (Solar-Knee 0.4 statt 400 W/m²).
2. **„expected_minutes" aus dem eigenen Physik-Schätzer** (Optimal-Start `heatup_minutes`/seasonless) statt einer Heuristik — Poise-Vorteil: die Erwartung ist modellbasiert.
3. **Coordinator-Lifecycle als dünne Glue:** Session-Start/Peak/Ende-Erkennung im Tick; bei Ende `outcome_score` → `OutcomeStats.observe`; Diagnose `outcome_last_score`/`outcome_ts_avg`/`outcome_obs_avg`/`outcome_n`; Stats im Save-Payload.
4. **Tagging:** aktuell alle Sessions `ts` (Poise steuert, wenn enabled). Die `obs`-Population braucht den **Beobachtungs-Modus** (Feat 25, offen) — bis dahin füllt sich nur `ts`; die A/B-Mechanik steht aber bereit.

## Konsequenzen
**Positiv:** baut das feldweit einzigartige Validierungs-Feature; macht den Nutzen der Winter-Aktorik *quantifizierbar* (Synergie #2); pure+getestet, persistent. **Negativ/ehrlich:** sammelt **Heiz**-Sessions erst, wenn wieder geheizt wird — im Sommer (Räume zu warm) ist die Infrastruktur **bereit, aber idle**; der echte A/B-Vergleich braucht zusätzlich den `obs`-Modus (Feat 25). Es ist damit primär **Winter-Vorbereitung**: jetzt gebaut und getestet, scharf ab der Heizsaison.
