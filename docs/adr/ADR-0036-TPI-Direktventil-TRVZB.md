# ADR-0036: TPI-Direktventilansteuerung (Sonoff TRVZB-Klasse)

**Status:** In Arbeit (80 %) · **Wirkung:** Live-D · **Datum:** 2026-06-22 · **Bezug:** ADR-0004 (TPI), ADR-0011 („Harness vor Hardware"), ADR-0015 (Aktorpfad-Capability), ADR-0032 (Closed-Loop) · **Verifizierung:** `tests/test_closed_loop.py` (TPI gegen RC-Plant), `tests/test_capability.py`, `tests/test_actuator.py`; Quellen z2m/VTherm/HA-Community; Mechaniktest am Gerät 2026-08-14 (Nachtrag unten)

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

## Nachtrag 2026-08-14 — Mechaniktest am echten Gerät (ADR-0036b): Konsequenz (b) erledigt

Interaktiver Test am TRVZB „Badezimmer" der Heim-Instanz (Zigbee2MQTT, Poise 0.189.0+Instrumentierung), gesteuert über HA-Entwicklerwerkzeuge; Motorlauf akustisch am Gerät verifiziert (Tobias vor Ort), Gerätezustand parallel digital per Template-Tool. Vier Befunde:

1. **`valve_opening_degree` ist ein Öffnungs-Limit, kein Fahrbefehl.** Ein Write außerhalb des Öffnungs-Regimes (Ventil zu, kein Heizbedarf) wird persistiert (Readback zeigt den neuen Wert), bewegt den Motor aber **nicht** (100→0 ohne jedes Geräusch). Die Formulierung „schreibbare Open-Position-Steuerung" aus dem Kontext-Abschnitt gilt also nur **im geöffneten Zustand**; der Abschnitt „Technik (Force-Open)" beschreibt das Verhalten korrekt und ist hiermit hardware-bestätigt.
2. **Force-Open funktioniert wie entworfen.** Poise-Hold 30 °C (Soll ≫ Raum) bei `smart_temperature_control` AUS → Ventil öffnete hörbar binnen eines Ticks auf das eingestellte Opening-Limit.
3. **Limit-Nachführung ist live und bidirektional → Duty-Mechanismus tauglich.** Im offenen Regime führte das Gerät Limit-Änderungen unmittelbar als Motorfahrt aus: 100→30 (Zufahrt hörbar), 30→70 (Auffahrt hörbar). Damit ist die Kernannahme des `TPI_VALVE`-Pfads — Opening-% als effektive Durchfluss-Duty, per `number.set_value` moduliert — am Gerät belegt.
4. **R1-Interferenz bestätigt: mit `smart_temperature_control` AN sind Limit-Writes wirkungslos.** Dieselbe Limit-Änderung, die bei AUS sofort fuhr, bewirkte bei AN keinerlei Bewegung — der interne Regler übersteuert den manuellen Pfad vollständig. **Konsequenz für den Live-TPI-Schritt:** Der Coordinator muss `smart_temperature_control` AUS aktiv asserten (nicht nur einmalig setzen), bevor/solange er Duty schreibt; ein extern (App/Physik-Taste) wieder eingeschalteter interner Regler macht die Duty-Modulation sonst still unwirksam.

Testaufbau-Lehre: Der erste Versuch (Limit-Write im Idle-Zustand) schlug erwartbar „stumm" fehl — für jede künftige Hardware-Verifikation zuerst das Öffnungs-Regime herstellen (Sollwert hoch + Smart-Control AUS), dann Limits variieren. Aufräum-Endzustand digital verifiziert: `valve_opening_degree=100`, `smart_temperature_control=off`, Poise-Hold beendet (`override_active=False`), Soll zurück im Zeitplan. Offen aus Konsequenzen bleiben (a) Coordinator-Verdrahtung (shadow-first, live ab Kaltsaison) und (c) `temperature_accuracy`/Ventil-Gesundheit.
