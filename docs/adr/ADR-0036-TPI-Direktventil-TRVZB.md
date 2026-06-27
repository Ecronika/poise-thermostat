# ADR-0036: TPI-Direktventilansteuerung (Sonoff TRVZB-Klasse)

**Status:** In Arbeit (70 %) · **Datum:** 2026-06-22 · **Bezug:** ADR-0004 (TPI), ADR-0011 („Harness vor Hardware"), ADR-0015 (Aktorpfad-Capability), ADR-0032 (Closed-Loop) · **Verifizierung:** `tests/test_closed_loop.py` (TPI gegen RC-Plant), `tests/test_capability.py`, `tests/test_actuator.py`; Quellen z2m/VTherm/HA-Community

## Kontext
Mit dem Sonoff TRVZB liegt erstmals Hardware mit **schreibbarem Ventil** vor. Recherche (Zigbee2MQTT, Versatile Thermostat, HA-Community) korrigiert unsere bisherige Annahme: `valve_opening_degree` (FW v1.1.4+) ist eine **schreibbare Open-Position-Steuerung 0–100 %**, kein reines Max-Limit — VTherm steuert das Ventil genau darüber per TPI + externem Fühler. Mangels Heizbedarf (Sommer) wird **im Harness statt am Gerät** validiert.

## Entscheidung
1. **Capability:** `valve_opening_degree` als writable Ventilpfad (`AUTO_VALVE_PATTERNS`); `select_path` wählt damit `TPI_VALVE`. **`valve_closing_degree` bleibt ausgeschlossen** (Firmware-Bug: Schreiben zerstört `running_state`/`hvac_action`).
2. **Aktorik:** `actuator.service_call_for` implementiert `TPI_VALVE` → `number.set_value` auf die Opening-Number, Wert 0–100 %. Pur, HA-frei testbar.
3. **Regler:** der bestehende reine `control/tpi.py` (Proportional + Außen-Feedforward, Modell-Seed, Online-Nudge) liefert die Duty 0–1.
4. **Validierung (Harness vor Hardware):** `run_tpi_control` treibt die RC-Plant mit der Duty als `power`. Befund: Seed aus Modell trifft den physikalischen Steady-State (t_out 8, Ziel 21 → Duty ≈0,65 = `8+20·d`), konvergiert ohne Pendeln, kalt → volle Duty. Direktventil-Regelung ist damit **gegen echte Physik validiert, ohne Heizsaison**.

## Technik (Force-Open)
`valve_opening_degree` ist die Position, die das Ventil **beim Öffnen** einnimmt. Für echte Duty-Modulation muss der TRV „öffnen wollen": hoher Sollwert + `smart_temperature_control` AUS (sonst ignoriert das Gerät die manuelle Öffnung). Dann ist die Opening-% die effektive Durchfluss-Duty.

## Konsequenzen
**Positiv:** Direktventil-Pfad gebaut + harness-validiert + capability-erkannt; generisch für Geräte mit schreibbarer Öffnung. **Offen/Negativ:** (a) Coordinator-Verdrahtung des `TPI_VALVE`-Pfads (Ventil-Number auflösen, Duty schreiben, Force-Open/`smart_temperature_control` managen) folgt **shadow-first** (Duty als Diagnose, kein Schreiben), dann live ab kalter Saison — analog MPC (ADR-0033). (b) Die Force-Open-Technik + `smart_temperature_control`-Verwaltung sind am echten Gerät zu verifizieren. (c) `temperature_accuracy`/Ventil-Gesundheit als Folgeschritte.

## Nachtrag — Online-Lernen (Auto-TPI), review M5

Der gebaute, unit-getestete `TpiLearner` (Online-Nudge der Koeffizienten aus Soll-vs-Ist-Anstieg) ist **bewusst noch nicht instanziiert**: Koeffizienten lassen sich erst lernen, wenn Poise das Ventil real treibt (kalt-saison-gegateter Aktiv-TPI-Schritt). Wettbewerbsbeleg: Versatile Thermostat liefert genau dieses Muster als **opt-in Auto-TPI** (EMA-Nudging aus gemessener Steigung, persistiert) — Online-Adaption ist also best-of, nicht spekulativ. Wird mit dem Aktiv-TPI-Schritt als opt-in Auto-TPI-Manager verdrahtet (lernen → Koeffizienten schreiben → zustandslose Per-Zyklus-Duty konsumiert sie). Bis dahin staged, nicht tot (review M5).
