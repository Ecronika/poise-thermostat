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

## Nachtrag (2026-07-03, v0.133.0): β_c-Anregung verdrahtet
**Befund:** Der EKF konnte `u_c` seit jeher (Zustand `beta_c`, `predict(..., u_c=...)`, `n_cooling`-Zähler, `cooling_identified = identified ∧ n_uc ≥ 20`). Der **Coordinator fütterte `u_c` aber nie** — er übergab nur `u_h`. Folge: außerhalb jeder Kühl-Anregung blieb `n_cooling = 0`, `cooling_identified` **dauerhaft False**, und der Sommer-MPC hing am β_c-Prior statt am gelernten Kühl-Gewinn. Das Heiz-Analogon (`u_h` aus `hvac_action == "heating"`) war längst verdrahtet — die Kühlseite war schlicht die vergessene Hälfte.

**Entscheidung:** Pures `cool_drive_signal(hvac_action, *, fallback_cooling) -> float` (Spiegel von `heat_drive_signal`): `1.0` bei `hvac_action == "cooling"`, sonst `0.0`; ohne gemeldete `hvac_action` fällt es auf die **Kühl-Absicht** zurück (`fallback_cooling = enabled ∧ ¬window_open ∧ mode == "cool"`). Der Coordinator hält `self._last_u_c` und übergibt es an `predict(..., u_c=self._last_u_c)`.

**Warum Intent-Fallback vertretbar:** Die Büro-AC meldet real **keine** `hvac_action` und **0 W** (ADR-0056-Kontext). Ohne Fallback bliebe die Kühl-ID auch im Sommer tot. Der v0.117.0-`idle_park`-Fix macht `mode == "cool"` ⇔ AC kühlt wirklich (im Totband idlet sie an der Kühlkante statt in `heat`), sodass die Absicht ein belastbarer u_c-Proxy ist. Meldet die AC später doch `hvac_action`, hat der reale Wert Vorrang.

**Grenze:** Verbessert nur die **Beobachtbarkeit** (Anregung), nicht die Gates. `cooling_identified` verlangt weiterhin `n_uc ≥ _ACTIVE_GATE (20)` **echte** Kühl-Ticks + `identified` — es kippt also erst nach hinreichender Sommer-Anregung, nicht sofort. Reine Schätz-Diagnose, kein Write. Feldverifikation der Kühl-Identifikation über das Sommerfenster steht aus.
