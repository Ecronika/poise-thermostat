# ADR-0033: MPC Live-Verdrahtung — Stufe 1 (Shadow)

**Status:** In Arbeit (70 %) · **Datum:** 2026-06-21 · **Bezug:** ADR-0001 (MPC), ADR-0009 (Gate), ADR-0026 (Schatten-Prinzip), ADR-0032 (Closed-Loop-Validierung) · **Verifizierung:** `control/mpc_shadow.py` + `tests/test_mpc_shadow.py`; volles Gate grün

## Kontext
Der prädiktive Kern ist im Harness end-to-end validiert (ADR-0032), war im Live-Coordinator aber gar nicht eingebunden: Poise schreibt heute nur den normgeklemmten Komfort-Sollwert; der MPC (`control/mpc.py`/`mpc_controller.py`) lief nie gegen den **echten** EKF-State. Der Live-Pfad (`coordinator._run_once` → `comfort_decide` → `resolve_write_target`) ist getrennt vom Harness-Pfad (`pipeline.run_tick` + Controller mit trivialem COLD-State).

## Entscheidungstreiber
M4 voranbringen, ohne dem unbeaufsichtigten System im Winter schlagartig Schreibhoheit zu geben. Die etablierte Disziplin (Schatten-Prinzip ADR-0026, „Harness vor Hardware" ADR-0011) verlangt: erst **beobachten**, dann **handeln**.

## Entscheidung
1. **Shadow-MPC** `control/mpc_shadow.evaluate_shadow` (pur, 100 % Cov): baut aus dem live EKF-Modell einen `ThermalState`, einen `ComfortCorridor` aus den Dual-Setpoint-Bändern (`target=heat_sp`, `lower=heat_sp`, `upper=cool_sp`) und ruft den **validierten** `MpcController` auf. Liefert `MpcShadow(active, power, weight, setpoint, regime)`.
2. **Gegated auf `identified`** (und `tau>0`): im Sommer/uneingelernt ist der Shadow inaktiv (`active=False`, alle Felder `None`) — keine Rechenlast-/Fehlalarm-Gefahr.
3. **Nur Diagnose, nie Aktorik:** Der Coordinator berechnet den Shadow nach `resolve_write_target` und exponiert `mpc_active/mpc_power/mpc_weight/mpc_setpoint/mpc_regime` als Climate-Attribute + zwei Diagnose-Sensoren (`mpc_power`, `mpc_weight`, in %). Der geschriebene Sollwert bleibt **unverändert** der bestehende Pfad.

## Flip-Kriterien (Stufe 2 → aktive Schreibhoheit, separater ADR)
Erst nachdem in der **kalten Saison** Live-Daten zeigen: (a) `mpc_weight` stabil hoch bei `identified`, (b) `mpc_setpoint` weicht plausibel und vorteilhaft vom statischen Komfort-Sollwert ab (antizipatorisches Zurücknehmen vor Überschwingen / rechtzeitiger Boost), (c) keine Pump-/Pendeltendenz über Tage. Dann gegated + mit Norm-Clamp als finaler Sicherung aktiv schalten.

## Konsequenzen
**Positiv:** M4 ist live verdrahtet (Beobachtungsstufe), der EKF-State-→-Controller-Seam existiert jetzt im echten Pfad und wird von Stufe 2 wiederverwendet; null Verhaltensänderung an der Aktorik; Winter liefert echte Belege statt Annahmen. **Negativ/Offen:** (a) Shadow rechnet jeden Tick einen MPC-Rollout — vernachlässigbar (stdlib, gegated auf `identified`). (b) Der Corridor-Mapping (`upper=cool_sp`) ist eine bewusste Vereinfachung; bei reiner Heizung ist `cool_sp` die obere Komfortbandkante. (c) Zwei Kontroll-Pfade (Live vs. `pipeline.run_tick`) bleiben getrennt — Konsolidierung ist ein späterer Aufräumschritt, kein Blocker.
