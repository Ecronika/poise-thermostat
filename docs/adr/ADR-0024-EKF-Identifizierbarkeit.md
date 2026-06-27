# ADR-0024: EKF-Identifizierbarkeit & Parameter-Konfidenz

**Status:** Implementiert · **Datum:** 2026-06-19 · **Bezug:** Livetest v0.6.0, ADR-0002/0009 · **Verifizierung:** RoomMind `thermal_model.py`/`mpc_controller.py`, Better Thermostat `mpc.py`

## Kontext
Livetest: `tau_hours` = 200 (α an der Untergrenze 0,005). Bei stabil gehaltenem Raum ist der Wärmeverlust α schlecht **beobachtbar** (keine freie Auskühlung), und die gemeldete `confidence` 0,87 spiegelt nur die **Temperatur**-Verfolgung, nicht die **Parameter**-Korrektheit. Würde der MPC darauf vertrauen, steuerte er auf einem falschen Modell.

## Entscheidungstreiber
Parameter dürfen nicht unter geringer Anregung an Grenzen pegen; Konfidenz muss Identifizierbarkeit messen, nicht nur T-Tracking; der MPC darf erst bei echter Modellreife übernehmen.

## Befund (verifiziert)
Niemand löst es über formale Beobachtbarkeitsanalyse — alle **defensiv**:
- **RoomMind:** mode-gated Q + Jacobian-Nullspalten (Poise hat das); **α-Drift-Dämpfung** `q_alpha = _Q_ALPHA·min(1,(α/α_ref)²)`; **α-Pegging-Recovery** (Poise nur beim Laden); **Konfidenz = 0.3·data + 0.7·data·accuracy** (Beobachtungszähler je Modus × Kovarianz); **harte Daten-Gates** vor MPC (`MIN_IDLE_UPDATES=60`, `MIN_ACTIVE_UPDATES=20`, `pred_std<0.5`).
- **Better Thermostat:** Mindest-Anregungs-Gates (u≥0,05, echte ΔT, Raten-Plausibilität), aktive Anregungs-Injektion.

Poise hat nur mode-gating + Lade-Recovery; es fehlen α-Dämpfung, Modus-Zähler, identifizierbarkeitsbasierte Konfidenz und MPC-Daten-Gates — genau das erklärt das Live-Pegging.

## Entscheidung
Übernimm RoomMinds Defensiv-Mechanismen in `estimation/thermal_ekf.py`:
1. **α-Drift-Dämpfung:** Prozessrauschen von α skaliert mit `min(1, (α/α_ref)²)` → α wird unter geringer Anregung nicht an die Grenze gezogen.
2. **Modus-Beobachtungszähler** `n_idle`, `n_heating`, `n_cooling` (je nach u_h/u_c/q_solar im Tick).
3. **Konfidenz = `data_factor × accuracy_factor`:** `data_factor` aus den Modus-Zählern (Identifizierbarkeit, Schwellen 60/20), `accuracy_factor = 1 − temperature_std`. Damit steigt die Konfidenz erst, wenn das Gebäude wirklich identifiziert ist.
4. **`is_identified()`-Gate:** `n_idle ≥ 60 ∧ (n_heating ≥ 20 ∨ n_cooling ≥ 20) ∧ temperature_std < 0.5`. Als Feld `identified` an `ThermalState`; der `MpcController` übernimmt nur dann (zusätzlich zur weichen Überblendung aus ADR-0009).
5. **Laufzeit-Recovery:** klebt α anhaltend am Bound (z. B. ≥ 50 Updates), Reset auf Default + Kovarianz-Boost (wie die Lade-Recovery, Zähler bleiben).

## Begründung
Code-verifizierte, im Feld bewährte Defensiv-Mechanismen; sie beheben das α-Pegging und machen die Konfidenz aussagekräftig fürs MPC-Gating. Keine formale Beobachtbarkeitsanalyse nötig (auch das Feld verzichtet darauf).

## Konsequenzen
**Positiv:** α pegt nicht mehr unter geringer Anregung; Konfidenz misst Parameter-Reife; MPC übernimmt erst bei echter Identifikation → sicheres Scharfschalten.
**Negativ/Kosten:** mehr EKF-Zustand (Zähler) und Tuning (α_ref, Recovery-Schwelle); `ThermalState` um `identified` erweitert; bestehende Konfidenz-Werte ändern sich (niedriger, ehrlicher).

## Compliance
Parametrisierungen allgemeiner Filter-Verfahren; eigenständig nachimplementiert. Generisch.

## Verknüpfungen
Vertieft ADR-0002 (EKF) und ADR-0009 (Gating/Konfidenz). Liefert das `identified`-Gate, das der MPC (ADR-0001) vor dem Scharfschalten der Ventilmodulation braucht.
