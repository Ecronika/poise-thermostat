# ADR-0009: EKF-Tuning & Konfidenz-Gating

**Status:** In Arbeit (80 %) · **Wirkung:** teilw. · **Datum:** 2026-06-18 · **Bezug:** E17, K11 · **Verifizierung:** Code-Review RoomMind `thermal_model.py`/`mpc_controller.py`, BT `mpc.py` (Thema E)

## Kontext
Der EKF (ADR-0002) braucht konkrete Rausch-/Bounds-Werte; das Umschalten MPC↔Bang-Bang braucht eine Strategie (K11: weiche Übergänge statt harter Flips).

## Entscheidungstreiber
Stabiles, konvergierendes Lernen; Robustheit gegen Ausreißer/τ-Oszillation; keine Verhaltensklippen am Reife-/Konfidenz-Schwellenrand; numerische Stabilität.

## Befund am Code (konkrete Zahlen)
- **RoomMind EKF (`thermal_model.py`):** Prozessrauschen diagonal & **parameterspezifisch** `_Q_T=0.01`, `_Q_ALPHA=0.0005`, `_Q_BETA_H/C=0.005`, `_Q_BETA_S/O=0.002`; Messrauschen `_R=0.04` (≈0,2 °C σ); Outlier `_ANOMALY_SIGMA=4.0` → `R×_ANOMALY_R_INFLATE=100` (**Soft-Reject**, kein Hard-Drop); Bounds `_ALPHA_MIN/MAX=0.005/2.0` (τ 200 h…30 min), `_BETA_H 0.1…200` usw.; Defaults `α=0.15 (~7 h)`, `β_h=3.0`; **Joseph-Form + PSD-Floor 1e-10**; **mode-gated Q** (Q nur auf beobachtbare Parameter, Kommentar warnt vor `alpha↔beta_h`-Kopplung → τ-Oszillation); Recovery-Reset bei gepegtem α + `boost_covariance(2.5)` nach physischer Änderung.
- **RoomMind MPC-Gating (`mpc_controller.py`):** `MPC_MAX_PREDICTION_STD=0.5`, `MIN_IDLE_UPDATES=60` (~3 h), `MIN_ACTIVE_UPDATES=20` (~1 h); Umschaltung ist ein **HARTER FLIP** (`if pred_std<0.5 and _has_enough_data: _evaluate_mpc else _evaluate_bangbang`). Das weiche Confidence-Maß (`0.3·data+0.7·data·accuracy`, `noise_floor=0.20`) steuert nur UI/Reife, **nicht** den Flip.
- **BT (`mpc.py`):** `kalman_R=0.04` (identisch zu RoomMind), `kalman_Q=0.001/s`, `adapt_alpha=0.1`, Gain/Loss-Clamps — aber nur skalarer Temperatur-Observer, kein augmentierter EKF.

## Entscheidung
1. **EKF-Tuning = RoomMind-Referenz übernehmen:** `R≈0.04`; **mode-gated, parameterspezifisches Q** (α sehr klein ~5e-4, β ~5e-3, T 1e-2); **4σ→R×100 Soft-Reject**; harte physikalische Bounds; **Joseph-Form + PSD-Floor**; Recovery-Reset + Kovarianz-Boost nach erkannter physischer Änderung.
2. **Gating verbessern gegenüber RoomMind:** den harten Flip durch **weiche Überblendung** ersetzen — `u = w·u_MPC + (1−w)·u_bangbang` mit `w = clamp((mpc_threshold − pred_std)/(mpc_threshold − noise_floor), 0, 1)` und **Hysterese** am Flip-Punkt gegen Regime-Pumpen. Die **Daten-Gates** (`n_idle≥60`, `n_active≥20`) bleiben als **harte Untergrenze** (darunter immer Bang-Bang).

## Begründung
RoomMinds EKF-Werte sind am Code belegt, physikalisch begründet und gegen die τ-Oszillation gehärtet (mode-gated Q) — die reifste Referenz im Feld; `R=0.04` wird unabhängig von BT bestätigt. Sein **harter** MPC-Flip ist aber genau die in K11 benannte Verhaltensklippe; die weiche Überblendung mit Hysterese behebt das, ohne die bewährten Daten-Gates aufzugeben.

## Konsequenzen
**Positiv:** stabiles, oszillationsarmes Lernen; ausreißerfest; sanfte, unauffällige Übergänge MPC↔Bang-Bang; numerisch robust.
**Negativ/Kosten:** Überblendungsfenster + Hysterese sind zusätzliche Tuning-Parameter (im Replay-Harness zu kalibrieren, ADR-0011); mode-gated Q erhöht die Implementierungskomplexität des EKF.

## Compliance
Tuning-Werte sind Parametrisierungen allgemeiner Verfahren (Kalman-Filter); eigenständig nachimplementiert, kein Code-Copy. Generisch.

## Verknüpfungen
Detail zu ADR-0002 (EKF) und ADR-0001 (Solver-Gate). Werte stammen teils aus der Default-Tabelle ADR-0008. Verifikation der Überblendung im Harness ADR-0011.
