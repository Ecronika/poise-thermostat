# ADR-0037: PI-kompensierter Sollwert (Shadow) für setpoint-only-TRVs

**Status:** In Arbeit (65 %) · **Datum:** 2026-06-22 · **Bezug:** ADR-0015 (Aktorpfad PI_SETPOINT), ADR-0026/0033 (Schatten-Prinzip), ADR-0011 (Harness vor Hardware), ADR-0036 (TPI-Shadow, Schwester) · **Verifizierung:** `tests/test_closed_loop.py` (Droop-Reduktion gegen RC-Plant), `tests/test_pi_shadow.py`

## Kontext
TRVs ohne schreibbares Ventil regeln mit ihrer eigenen Proportionalsteuerung gegen einen Sollwert — und settlen im stationären Zustand **unter** dem Sollwert (Droop). Der gebaute, aber nie verdrahtete `PiCompensator` (`control/pi.py`, Versatile-Methode) schiebt einen kompensierten Sollwert (`kp·err + ki·∫err + k_ext·(room−external)`, Anti-Windup, ±offset_max), der den Droop aufhebt. Mangels Heizbedarf wird im Harness statt am Gerät validiert.

## Entscheidung
1. **Harness-Validierung:** `run_pi_setpoint` modelliert Plant + Proportional-TRV. Befund: bare TRV settelt bei 19,1 °C (Ziel 21), mit Kompensation 20,5 °C (Sollwert auf 22,7 hochgeschoben) — **Droop um 1,4 K reduziert**, gegen echte Physik.
2. **Stufe-1 Shadow:** `control/pi_shadow.py` (`evaluate_pi_shadow`) berechnet den kompensierten Sollwert live und exponiert `pi_active`/`pi_setpoint`/`pi_offset` als Diagnose — **kein Schreiben**. Aktiv nur, wenn das Gerät **kein** schreibbares Ventil hat (komplementär zum TPI-Shadow: Ventil→TPI, sonst→PI). `external == room` (Poise-Sensor).
3. Aktives Schreiben des kompensierten Sollwerts (Stufe 2) ist eine spätere, evidenz-gegatete Entscheidung.

## Konsequenzen
**Positiv:** der Setpoint-Pfad-Kompensator ist harness-validiert + shadow-verdrahtet; jedes Gerät bekommt jetzt genau einen passenden Shadow (Ventil→TPI, sonst→PI). **Negativ/Offen:** (a) der Integrator akkumuliert im Shadow gegen den realen Raumfehler des **bestehenden** Reglers — als „was würde helfen"-Diagnose korrekt, im Live-Betrieb (Stufe 2) reflektiert er den echten Kreis. (b) `k_ext`-Term ist 0, solange Raum==externer Fühler; bei abweichendem TRV-Sensor erst live relevant. (c) Live-Aktivierung am echten setpoint-only-TRV steht aus (unsere Testgeräte nutzen den External-Feed-Pfad).
