# Poise — Setpoint Thermostat

***Self-learning, norm-based climate control for Home Assistant — comfort kept in balance.***

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-0.191.0-blue.svg)](https://github.com/Ecronika/poise-thermostat/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.10%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Poise** is a self-learning **thermostat** for Home Assistant. It controls TRVs and climate entities through a single, fully local integration — no cloud, no heavy dependencies — using norm-based comfort and a real building-physics model rather than static setpoints.

Today Poise is an **intelligent setpoint controller**: it learns each room's thermal behaviour and writes one safe, norm-clamped setpoint per actuator. The deeper machinery (predictive MPC, direct valve control, KNX) is built and tested but, by design, **not yet driving the actuator** — see the capability status below for exactly what is active.

> **Successor to Smart Setpoint.** Poise merges the five-component Smart Setpoint ecosystem (Blueprint, ha-preheat, TRM/PMOT, irradiance sensor, Virtual MRT) into one installable integration with guided onboarding.

## Capability status

Honest separation of what runs today vs. what is staged. Poise is **Alpha**.

### ✅ Active (drives control / visible today)

- **Norm-based comfort** — active heating/cooling holds the configured comfort base within fixed EN 16798-1 design bands (Cat. I–III), the norm-correct choice for a conditioned room. A real running-mean `T_rm` drives the diagnostics, the seasonless heat-rate prior and optimal-start/stop timing. In the cooling season an **occupied** room uses the fixed EN category band (norm-correct for an actively-cooled space — the adaptive model applies only to free-running buildings), while an **unoccupied** room may free-run: the cool edge lifts toward the EN adaptive upper (ASR-capped) to save energy, and the comfort/efficiency slider governs how far (ADR-0061). The free-running *heating* widening stays a shadow diagnostic.
- **Operative temperature / MRT** — controls what the room *feels* like (air + mean radiant), via a virtual-MRT estimator that a real MRT/globe sensor overrides when present.
- **Self-learning physics** — mode-gated Extended Kalman Filter learns each room's time constant, losses and solar/heating response; confidence and identification are real sensor entities.
- **Optimal Start & Optimal Stop** — forecast-aware pre-heating to the comfort deadline and coast-down to the lower comfort edge at window end; advisory (re-entry-free) and gated on an *identified* model.
- **Mould & frost protection** — surface-humidity model (DIN 4108-2) and unconditional safety floors.
- **Solar accounting** — measured global irradiance as a learned disturbance feeding the MRT/comfort path — counted once.
- **Precedence constraint solver** — every bound (frost/mould/ASR cap/device max) is composed with explicit precedence into exactly one safe command per actuator.
- **Cooling decision & modes** — capability-aware dual setpoints; `COOL` is surfaced as an HVAC mode **only when the actuator supports cooling** (heat-only TRVs stay HEAT/OFF).
- **Humidity (dry) & hot-day cooling** — capability-gated and live: a `dry`-capable AC lowers humidity through the dead-band (cool-first, dew-point-guarded, category-bound RH ceiling with 5 % hysteresis; the comfort ceiling only applies while the room is **occupied**, the absolute 12 g/kg health/mould backstop always), and on hot days the cooling edge is raised toward the EN / ASR ceiling (rate-limited ≤ 0.5 K/tick); heat-only TRVs are unaffected (ADR-0050/0051).
- **Open-window reaction (sensor *or* sensorless)** — a configured window sensor or the **slope detector** (open threshold adapted to the learned time constant τ) drops the room to the frost/mould floor through the solver and pauses learning; a per-zone **bypass switch** overrides it. The sensor wins when present.
- **Comfort presets & timed override** — Eco / Comfort / Boost / Away as **norm-clamped offsets on the comfort base** (surfaced as HA preset modes, not free temperatures); a manual setpoint **auto-reverts** to the schedule/preset after a window so it never sticks, and a value pushed outside the comfort band is clamped to it and flagged (`override_clamped`) rather than limited silently. A setpoint or HVAC mode changed **on the device itself** (TRV wheel / IR remote / vendor app) is adopted as such a hold — with the zone's return rule — *once Poise can tell it apart from an echo of its own write*; the preconditions and the modality limits are spelled out under [Geräteseitige Eingriffe (Adoption)](#geräteseitige-eingriffe-adoption) (default on, opt-out per zone; ADR-0059).
- **„Aktive Behaglichkeit" (opt-in)** — with the per-zone `active_comfort` toggle ON (default off), a fan-capable AC uses the **fan as the first cooling stage** (echo-gated fan-first sequence with dwell/anti-flap, ADR-0068) plus the ADR-0053 idle circulation; the tier-2 comfort measures (fan-CE credit on the cooling edge, capped PMV band shift) additionally wait for the ADR-0055 maturity gates (ADR-0069).
- **Bundled Lovelace cards** — Poise ships its own cards inside the integration and **auto-registers** them (no separate HACS plugin, no manual resource URL). `poise-card` puts the **EN 16798 comfort band** front and centre — operative temperature & setpoint as markers in the live band, a 24 h history graph, clickable status chips, learning confidence and a **shadow pill that shows what the engine *would* do** (TPI %/PI/MPC). `poise-system-card` surfaces the multi-zone hub (boiler demand, heating zones, flow target, load shedding). Self-contained Lit/TS, only `lit` bundled (ADR-0040).
- **Robust by design** — degradation ladder (measured → derived → estimated → default), repair issues, redacted diagnostics, a change-aware setpoint write-throttle (compares against the device's real setpoint, snapped to its step), and learning + user intent (enable/override/mode) persisted across restarts (and flushed on Home Assistant shutdown, not only periodically). While enabled, Poise also keeps a heat-capable actuator in its `heat` mode so it follows Poise's setpoint instead of running its own `auto`/schedule.

### 🟡 Shadow / diagnostic (computed, not yet actuating)

- **Predictive MPC** — runs every tick against the live learned model and is exposed as `mpc_*` diagnostic values, but **never writes the actuator** in this version. Active write authority is gated on cold-season validation (ADR-0033).
- **Direct-valve TPI** — for a device with a writable valve-open entity (e.g. Sonoff TRVZB `valve_opening_degree`), the TPI valve duty is computed live and exposed as `tpi_*` diagnostics. The valve is **not written** yet — closed-loop validated in the harness, live actuation gated on cold-season validation (ADR-0036).
- **PI-compensated setpoint** — for a setpoint-only TRV (no writable valve), the PI-compensated setpoint that would cancel the device's steady-state droop is computed and exposed as `pi_*` diagnostics (not written); harness-validated (ADR-0037). Every device thus gets exactly one matching shadow: valve → TPI, otherwise → PI.
- **Multi-zone boiler demand** — an optional *Poise System* hub aggregates the call-for-heat across opt-in zones into one frost-safe, device-granular boiler-demand `binary_sensor`. Diagnostic by default (wire your own automation off it); **opt-in actuation** switches a configured boiler service with activation delay, keep-alive and min on/off cycling — the write path stays off unless you set the actions (ADR-0038/0039). Each zone also publishes its own `heat_demand` (0–1, the exact value the hub aggregates) so per-zone boiler contribution is visible without the hub.
- **Adoption transparency** — when you change the device by hand, Poise exposes `mode_adopt_reason` / `sp_adopt_reason`: why it did or did not adopt that change this tick (e.g. `own_echo`, `safety_window`, `stable_offset`, `hold_resumed`) — observe-only, so a manual change that "didn't stick" is no longer a mystery.
- **Comfort index (PMV/PPD)** — ISO 7730 predicted-mean-vote and %-dissatisfied from air / MRT / humidity with seasonal clo / met, exposed as `pmv` / `ppd` / category — humidity (and, staged, air velocity) finally enter the comfort *evaluation*; the norm band stays the control variable (ADR-0054).
- **Regulation-quality metric (EN 15500-1 CA)** — continuous, bilateral control accuracy: mean Kelvin outside the comfort band, time-in-band and a regime-change ("hunting") rate, time-weighted and persisted (`ca_*`). This is the measurable acceptance gate that will authorise each shadow→live flip — today it only measures (ADR-0055).
- **Fan cooling-effect** — the ASHRAE-55 elevated-air-speed credit a running fan would allow on the cooling setpoint (`fan_ce_k`); the credit itself stays diagnostic until the tier-2 maturity gates release it (ADR-0054/0069 — the fan-first *sequence* is the separate opt-in above).
- **Efficiency report** — a live heating-degree-hour savings estimate in kWh / €, computed each tick and published as `savings_*` climate attributes (ADR-0045); diagnostic only, never actuates.
- **Humidity axis (advise-only)** — absolute humidity in g/m³ (`abs_humidity_gm3`, plus the outdoor comparison from a dedicated sensor or the weather entity), a **ventilation advice** built from mould cause (~48 h surface-RH mean), dryness veto, moisture/CO₂ comfort rules and a **free-cooling rule** for zones that can neither cool nor move air (open when outside is ≥2 K cooler than an over-warm room and not muggier, hold to 1 K, then advise closing — night purge, not occupancy-gated) (`vent_action`/`vent_reason`/`vent_level`), and the **mould-safe humidity ceiling** (`rh_max_safe` / `abs_max_safe`) a third-party humidifier should respect. Surfaces: card lamp (dry side judged in g/m³) + chip, bus event `poise_ventilation_advice` on every advice change, an opt-in self-clearing notification, and a `vent_advice` diagnostic sensor. Never actuates — no fan, no window, no humidifier commands (ADR-0066, ADR-0048 line).

### 🗺️ Roadmap (built or designed, not in the active path)

- **Direct valve / TPI control (live actuation)** — auto-detected for devices with a writable valve-open number (Sonoff TRVZB `valve_opening_degree`, FW v1.1.4+) and harness-validated; today it runs as a diagnostic shadow (above), with live valve writing gated on cold-season validation. `valve_closing_degree` is never written (TRVZB firmware bug). A generic `pi_heating_demand` path exists; the TRV-offset **calibration** helpers (`control/calibration.py`) are written and unit-tested but **not yet wired into the tick** — operative mode instead feeds the true room temperature to the TRV's own external-input `number` (below), and **without that input Poise performs no live TRV compensation**.
- **KNX expose** — operative temperature, setpoints, comfort band and heat demand on group addresses (designed, optional).
- **Multi-zone resource coordination** — via the *Poise System* hub (ADR-0038/0039): boiler-demand aggregate + opt-in boiler actuation, plus **load-shedding, compressor-group protection and a flow-temperature allocator computed as diagnostic shadows** (smallest-gap shedding, per-group min-run/off, highest-request-wins flow with anti-hunt hysteresis — the last harness-validated against oscillation, ADR-0013). Zone-side / generator-side enforcement is the next stage.

## Manuelle Eingriffe & Rückkehr zur Automatik

Ein manueller Sollwert ist ein **temporärer Hold**, kein Dauerzustand: Poise übernimmt den von Hand gestellten Wert und kehrt anschließend automatisch in den geregelten Betrieb zurück. **Wann** zurückgekehrt wird, ist konfigurierbar (*Optionen → „Manuelle Eingriffe"*).

| Eingriff | gilt bis | wie beenden |
| --- | --- | --- |
| **Manueller Sollwert** | Policy `schedule` → bis zum nächsten Schaltpunkt (hart gedeckelt auf 8 h; ohne konfiguriertes Zeitfenster greift der Timer); `timer` → fester Timer (Default 2 h); `permanent` → bis zum Widerruf | Modus wählen, X auf der Card, `poise.resume_schedule`, oder Ablauf abwarten |
| **Boost-Preset** | Default 60 min, danach Rückkehr zum vorherigen Preset | Ablauf abwarten oder anderes Preset wählen |
| **Eco / Comfort / Away** | Zustandswahl (kein Timer); **Away** endet über die Anwesenheit | anderes Preset / Modus wählen |
| **HVAC-Modus** | persistent — das ist **Konfiguration**, kein Override | Modus erneut wählen |

**Prioritätenkette** — der jeweils höhere Rang gewinnt:

**Fenster / Frost / Schimmel  >  manueller Sollwert  >  Preset  >  Zeitplan / Anwesenheit**

Sicherheits- und Kontextlagen (offenes Fenster, Frost- und Schimmelschutz) sind nie verhandelbar und setzen sich immer gegen einen manuellen Sollwert durch; dieser schlägt das aktive Preset, und das Preset schlägt Zeitplan und Anwesenheit.

**Wie beenden:** einen HVAC-Modus wählen, das **X** auf der Card antippen, den Service `poise.resume_schedule` aufrufen (Zone oder alle Zonen), oder den Ablauf abwarten.

> **Migration:** Bestehende Installationen behalten das heutige Verhalten (`timer` / 2 h). `schedule` ist nur der Default für **neu eingerichtete** Zonen.

### Geräteseitige Eingriffe (Adoption)

Wird **am Gerät selbst** verstellt (TRV-Rad, IR-Fernbedienung, Hersteller-App), übernimmt Poise das als denselben Hold wie einen Eingriff in der Poise-UI — mit der Rückkehrregel der Zone, statt beim nächsten Tick zurückzuschreiben. Standardmäßig an, je Zone abschaltbar (*Optionen → „Manuelle Eingriffe"*).

**Die Übernahme ist bedingt, nicht bedingungslos.** Poise sieht an der `climate`-Entität nur einen neuen Wert — nicht, *wer* ihn gesetzt hat. Übernommen wird deshalb nur, was sich sicher vom Echo des eigenen Schreibvorgangs unterscheiden lässt. Im Zweifel gilt: **nicht übernehmen** — ein verworfener Eingriff kostet eine Wiederholung, eine falsche Übernahme friert die Regelung auf einem Phantom-Sollwert ein.

| Wird **nicht** übernommen, wenn … | Grund (Diagnose) |
| --- | --- |
| die Zone die Übernahme abgeschaltet hat | `opt_out` |
| Poise den Wert selbst geschrieben hat (erkannt am HA-`Context`) | `own_echo` |
| Poise in dieser Zone noch nie selbst geschrieben hat — es fehlt der Vergleichswert (**seit v0.174.0 neustartfest**: er wird mitgespeichert, betrifft also nur Neuinstallationen bzw. die Zeit bis zum ersten eigenen Schreibvorgang) | `no_baseline` |
| die Änderung **binnen 120 s** auf einen eigenen Schreibvorgang folgt und nicht nachweislich auch vom Wert *davor* abweicht | `echo_window` |
| die Abweichung unter der Geräteschrittweite liegt | `command_echo` |
| der gemeldete Wert sich seit der letzten Ablesung nicht bewegt hat (ein stehender Versatz — Rundung / interne Kompensation — wird nie erneut übernommen) | `stable_offset` |
| beim **Modus**: der gemeldete Modus sich seit der letzten Ablesung nicht bewegt hat | `stable_prev` |
| beim **Sollwert**: die geräteeigene Zeitschaltuhr läuft (eine auf dem Aktor-Gerät automatisch erkannte Zeitplan-`switch`-Entität ist `on`) — dann stellt das Programm, nicht der Mensch | `schedule_active` |
| beim **Sollwert**: der gemeldete Wert liegt auf/unter dem Frostschutz-Boden (7 °C) — kein plausibler Nutzerwunsch, sondern Geräte-Reset/Frostmodus | `implausible_frost` |
| bei **Sollwert und Modus**: Fenster offen oder Sensorik eingefroren — Sicherheit schlägt Eingriff | `safety_window`, `safety_frozen` |
| beim **Modus**: das Gerät kann den Modus nicht oder er ist `heat_cool` | `unsupported` |

Ein übernommener Sollwert ist ein normaler Hold und steht damit **unter** der Prioritätenkette oben: Fenster, Frost und Schimmelschutz klemmen ihn weiterhin, und ein Wert außerhalb des Komfortbands wird auf die Bandkante geklemmt und als `override_clamped` ausgewiesen.

**Modalitätsgrenze:** übernommen werden **Sollwert und HVAC-Modus**. *Nicht* übernommen werden Lüfterstufe, Swing, geräteseitige Presets und `heat_cool`-Doppelsollwerte — diese Verstellungen lässt Poise unangetastet stehen, sie erzeugen aber auch keinen Hold.

**Nachvollziehbarkeit:** die Herkunft eines Holds steht als `override_reason` an der `climate`-Entität (`ui_setpoint`, `device_adopt_setpoint`, `device_adopt_mode`, `frost_rescue`); die Card zeigt sie als „Gerät" / „App" an der Hold-Pille. Der Grund **je Tick** — auch der einer *unterdrückten* Übernahme aus der Tabelle oben — steht als `sp_adopt_reason` / `mode_adopt_reason` in den Attributen der `climate`-Entität und im Debug-Log.

## Use cases

Poise is for rooms whose heating or cooling already lives in Home Assistant and whose comfort you want *held* rather than scheduled by hand.

- **Make a radiator valve behave like a room thermostat.** A TRV regulates against its own body — bolted to the radiator, metres from where you sit. Point Poise at a free-standing room sensor and it writes the setpoint the valve needs so that the *room*, not the valve, lands in the comfort band. Where the TRV has an external-temperature input, Poise feeds the true room temperature into the device as well and hands the sensor source back to `internal` when you remove the zone.
- **Stop hand-tuning the night setback and the morning start.** Configure a comfort *window* instead of a temperature schedule. Poise learns the room's time constant and heat-up rate and starts early enough to be at comfort *when the window opens* (optimal start), then coasts down to the lower comfort edge before it closes (optimal stop) instead of heating into an empty room.
- **Heat to a norm band instead of a number.** The target is an EN 16798-1 comfort band around your comfort base, with an unconditional frost floor and a DIN 4108-2 mould floor underneath it and an ASR A3.5 ceiling above. You pick the category and the comfort-vs-energy weight; the precedence solver composes every bound into exactly one safe command per actuator.
- **Keep a manual change from sticking forever.** A setpoint set on the card, in the HA UI or on the TRV's own wheel becomes a *temporary hold* with a defined end (next switch point / timer / permanent — your choice per zone), never a silent permanent override.
- **Don't fight an open window.** With a window contact, or without one via the slope detector, the room drops to the safety floor and learning pauses. A per-zone bypass switch covers the "yes, I really do want to heat with the window open" case.
- **Give a shared boiler one demand signal.** The optional *Poise System* hub aggregates the call-for-heat of the zones that opt in into one frost-safe `binary_sensor` you can automate off — or let it switch the boiler itself with activation delay, keep-alive and minimum on/off times.
- **Watch the predictive engine before trusting it.** MPC, direct-valve TPI and the PI setpoint compensator run every tick against the live learned model and publish what they *would* command, without touching the actuator; the EN 15500-1 control-accuracy metric measures the controller that is actually driving.

## Scope & Non-Goals

Poise controls heating/cooling **setpoints** and protects against **surface condensation / mould** (building physics). To stay honest and publishable, it explicitly does **not**:

1. **Maintain mechanical-ventilation / AC hygiene** — no VDI 6022 filter, maintenance or cleaning monitoring, and no operation-block on overdue hygiene. Poise owns no air-handling hardware.
2. **Manage CO₂-based or burst ("Stoßlüften") ventilation, nor size/rate ventilation.** Poise *displays* CO₂ for awareness but never acts on it; CO₂ → fresh air belongs in a dedicated ventilation device or a separate HA automation (the standard `air_quality` trigger → `fan` pattern).
3. **Actively humidify.** An AC / heat pump / TRV can only *remove* moisture (cooling / `dry`), never add it — raising humidity needs a separate appliance, which HA models as its own `humidifier` domain. Poise only **lowers** humidity.

Poise's mould protection (`mold.py`, surface-RH / condensation per **DIN 4108-2 / EN ISO 13788**) is **building physics** and stays — it is **not** a substitute for **VDI 6022** ventilation-system hygiene.

**Monitoring vs. control.** Poise may *read and display* any indoor-environment metric (temperature, humidity, CO₂) and may *nudge* you (e.g. "CO₂ high — open a window"); it only *acts* on quantities it can move with the actuators it owns: setpoint / heat / cool, and humidity *downward* via cooling / `dry`. CO₂ and active humidification are monitor / inform-only. (ADR-0048)

## Status

Alpha — under active development against a documented architecture (60+ ADRs) and a production-identical simulation harness, in which the predictive core (EKF → MPC → optimal start/stop → gate) is validated end-to-end. Roadmap milestones: M1 norm comfort ✅ → M2 self-learning ✅ → M3 valve (hardware-parked) → M4 MPC (shadow live, active gated on winter validation) → M5 release.

## Installation (HACS)

1. HACS → Integrations → ⋮ → *Custom repositories* → add `https://github.com/Ecronika/poise-thermostat` (type: Integration).
2. Install **Poise Setpoint Thermostat**, restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → Poise.*

Use a **free-standing room sensor** (not the TRV's internal sensor) for best results; Poise raises a repair issue if it detects a likely heat-source-mounted sensor.


## Supported devices

Poise is not a device integration: it drives whatever Home Assistant `climate` entity you point it at, through the standard `climate` services. Compatibility therefore follows from the *entity's* capabilities, not from the brand — and every device adaptation below keys off detected entities and attributes, never off a model name (ADR-0029).

### What a thermostat must offer

| Requirement | What happens otherwise |
| --- | --- |
| Home Assistant on **metric units (°C)** | Setup aborts: *"Poise requires a metric (°C) Home Assistant."* The control path is Celsius-only. |
| A `climate` entity with **one target temperature** | Poise writes a single `climate.set_temperature`. A device whose only conditioning mode is `heat_cool` (dual setpoint) is rejected in the flow with *"This device only supports the combined heat/cool (dual-setpoint) mode."* |
| A **separate room sensor** | A sensor sitting on the actuator's own device is rejected in the flow — that is the TRV's built-in sensor, which reads the radiator. |
| **One zone per thermostat** | A thermostat already used by another Poise zone is rejected (*"Each thermostat can belong to only one zone."*). Poise is the single writer for its actuator. |

**Heat/cool capability** is read from the entity's `hvac_modes`: heating from `heat`, `heat_cool` or `auto`; cooling **only** from an explicit `cool` or `heat_cool`. `auto` alone never enables cooling — many radiator TRVs expose `auto` for their internal weekly program and cannot cool at all. A heat-only TRV therefore only ever shows `heat` / `off`.

### Optional device features Poise picks up automatically

If the actuator's device also exposes any of these, Poise detects and uses them; nothing here is configured by hand.

| Detected on the device | What Poise does with it |
| --- | --- |
| a writable valve-position `number` — id containing `valve_position`, `pi_heating_demand`, `heating_demand` or `valve_opening_degree` | selects the direct-valve (TPI) actuation path and publishes the duty as `tpi_*` (**shadow** today, see [Known limitations](#known-limitations)). `valve_closing_degree` is explicitly excluded and never written. |
| a writable calibration `number` — `local_temperature_calibration`, `temperature_offset`, `temperature_calibration` | the calibration path; built and unit-tested, **not yet wired into the tick**. |
| a `number` whose id contains `external` (temperature device class or none) | feeds the fused room temperature into the TRV and switches its sensor-source `select` to `external`; re-pushed at least every 10 min so a device that times the input out never falls back to its own sensor. Restored to `internal` when the zone is deleted. |
| a `switch` whose id contains `schedule` | detects the device's own weekly program and raises a repair issue. Poise never flips that switch for you — a second program is yours to end — but it does hold a heat-capable actuator in `heat`, so the device follows the written setpoint instead of its own `auto`. |
| a `switch`/`select` containing `adaptive` or `smart_temperature` | detects a second control loop running on the device itself and raises a repair issue. |
| a `binary_sensor` containing `valve_alarm`, `fault`, `problem` or `alarm` | surfaces the device fault as a repair issue and feeds the heating-failure detector. |
| a battery level | low-battery repair issue at or below **15 %**. |
| valve step counters (`closing_steps` / `idle_steps`) | stuck/uncalibrated-valve detection. |
| `hvac_action` / `running_state` | heating- and cooling-failure detection, and the HVAC action shown on the Poise entity. |

### What has actually been on a bench

Honest scope: exactly one device class has been verified against real hardware.

- **Sonoff TRVZB** (Zigbee, heat-only, setpoint + writable valve opening). The setpoint path is the live one. The direct-valve mechanism was bench-tested on a real device on 2026-08-14 (protocol as an addendum in `docs/adr/ADR-0036-TPI-Direktventil-TRVZB.md`): `valve_opening_degree` is an **opening limit**, not a drive command — writes while the valve is idle persist but move nothing; limit changes inside an open regime do move the valve; and the device's own `smart_temperature_control` must be **off** or limit writes are ignored entirely. That last finding is why the device's adaptive/smart mode has its own repair issue.
- Everything else — the cooling, `dry` and compressor-guard paths for AC / heat-pump `climate` entities, the generic `pi_heating_demand` valve path, the quirk detectors written against Zigbee TRV naming (Aqara E1 SRTS-A01 and Sonoff TRVZB are the examples named in the code) — is validated in the simulation harness and against the capability detection, **not on a bench**. If your device meets the requirements above it will be driven; Poise simply cannot yet publish a broad tested-hardware list.


## Removing the integration

Poise has no cloud account or external state. To remove it: *Settings → Devices & Services →* Poise → the **⋮** menu on the entry → **Delete**. Repeat for each room entry and (if present) the *Poise System* hub entry. On deletion Poise first parks the actuator in a safe end state — a heating device to its setback temperature in `heat`, a direct valve closed, a cool-only device off — restores a TRV's external sensor source back to `internal`, and deletes the stored learned model and trace file. Deleting the *Poise System* hub also switches its boiler off, but only when Poise was actually actuating it (both boiler actions configured); a shadow-only hub is left untouched. If you installed it as a HACS custom repository and no longer want updates, also remove it from *HACS → Integrations*.


## Configuration

Poise is configured entirely through the UI (config flow) — there are no YAML keys. The menu offers **Room** (a per-zone thermostat) and **System** (the optional multi-zone hub). Settings can be edited in place later via *Reconfigure*, which preserves the learned model.

### Room (per-zone thermostat)

| Option | Required | Default | Purpose |
| --- | --- | --- | --- |
| Room temperature sensor | yes | — | Free-standing room sensor Poise controls to (not the TRV's internal sensor). |
| Actuator (climate) | yes | — | TRV / climate entity Poise writes the setpoint to. One entry per actuator. |
| Comfort base | yes | 21 °C | Centre of the EN 16798-1 comfort band. |
| Comfort category | yes | II | EN 16798-1 design category (I tightest … III widest). |
| Comfort weight | yes | 70 % | Comfort-vs-energy priority used by preheat / band widening. |
| Setback delta | yes | 3 K | Night / away setback below the comfort base. |
| Optimal start | yes | on | Forecast-aware preheat to the comfort deadline. |
| Comfort start / end (+ windows 2–8) | no | — | Daily comfort window(s) (enables scheduled setback when set). The options form offers one additional empty window once the previous one is filled (n+1 pattern, up to 8; clear both times to remove one). Overlapping windows merge; optimal start preheats to **every** window start (ADR-0070). |
| Outdoor / humidity / MRT / T_rm sensors | no | — | Improve accuracy (mould floor, operative temperature, running mean). |
| Outdoor-humidity sensor | no | — | Dedicated outdoor-RH sensor for the ventilation advice (else the weather entity's `humidity` attribute is used, ADR-0066). |
| Presence (home) · occupancy sensor · absence delay | no | — · — · 30 min | ADR-0058 presence coupling: person/tracker entities gate the house, a motion/occupancy sensor gates the room. **Inside** a comfort window, occupancy extends comfort — the band only relaxes (Eco widening) after the room has been empty for the absence delay, and returning restores it immediately. Occupancy does **not** raise the band outside the window(s) (use Boost or another window for spontaneous use; ADR-0058 N2). A dead sensor fails safe to *present*. |
| Room profile | no | office | met/clo assumption for the PMV evaluation (`office` / `living` / `bedroom` / `kitchen` / `bathroom`, ADR-0054). |
| Aktive Behaglichkeit | no | off | Opt-in fan-first cooling + comfort actuation building blocks (ADR-0069). |
| Ventilation notification | no | off | Opt-in self-clearing notification for the ventilation advice (the bus event always fires, ADR-0066). |
| Suggestion learning | no | on | ADR-0060 override-pattern suggestions as fixable repair issues; the toggle is the per-zone opt-out. |
| Window sensor | no | — | Door/window contact for the open-window reaction (else the slope detector is used). |
| Weather / irradiance | no | — | Forecast for optimal-start; measured solar gain. |
| External-temperature input | no | — | TRV `number` entity Poise feeds the true room temperature to (operative mode). Re-pushed at least every 10 min even when unchanged, so TRVs that time out an external input (e.g. Danfoss ~30 min, Sonoff TRVZB ~1 h) never fall back to their own mounted sensor. |
| Operative input | no | off | Control on operative (felt) temperature instead of air. |
| Adaptive cooling edge | no | auto | Active by default on cool-capable devices (`auto`): lifts the cooling edge to the EN 16798-1 adaptive upper for the running mean (ASR 26 °C capped) instead of over-cooling toward the fixed summer band. `off` forces the fixed summer band; heat-only TRVs are unaffected either way (ADR-0023 §1). |
| Compressor guard · min-off · mode-hold | no | auto · 300 s · 300 s | Single-AC anti-short-cycle (*Optionen → Erweitert*): hold a cool/dry mode change that would restart the compressor within min-off, or flip cool↔dry within mode-hold — never a stop or a safety action. Blank timers use the fast-air profile default; set the guard to *off* to disable (ADR-0046 §8). |
| Actuator dynamics | no | auto | Controller time constants per actuator class — `auto` (classify from the learned model) or force `fast_air` / `slow_hydronic` / `very_slow`; faster profiles retune the PI/MPC and throttle setpoint nudges for self-regulating climate entities (ADR-0052). |
| Field-trace recording | no | off | Advanced/diagnostic: append one compact JSONL line per tick to `config/poise_traces/<id>.jsonl` (EKF drive inputs + model snapshot + decision + the humidity/dehumidification axis and real device mode — schema v2, versioned `v` with a v1-backward-compatible loader), rotated at ~20 MB. For offline golden-file replay analysis (ADR-0011); pure observation, never touches control. |
| Outdoor cooling / heating lockout | no | on, 16 / 22 °C | Suppress cooling below / heating above these outdoor temperatures; each direction has its own enable toggle (ADR-0047). |
| Thermal-shock ΔT · cool hard cap | no | 7 K · 26 °C | Heat-day cooling raise toward `outdoor − ΔT`, capped at the ASR ceiling (raising the cap is an explicit opt-in, ADR-0051). |
| Annual consumption · tariff | no | — | Baseline for the heating-degree-hour → kWh / € savings estimate. |
| Controls boiler | no | off | This zone contributes to the *Poise System* boiler-demand aggregate. |
| Compressor group · declared power · design flow temp · source policy | no | — | Multi-zone resource-coordination hints (shadow stage). |

> **Climate mode is set on the thermostat, not in the options.** A zone's heat/cool mode (internally `auto` / `heat_only` / `cool_only`) is chosen on the Poise `climate` entity via its HVAC mode (`heat` / `cool` / `auto` / `off`, per device capability); it is store-owned and persists across restarts — it is not a config-flow field. A heat-only TRV only ever exposes `heat` / `off`.

### System (optional multi-zone hub)

A single *Poise System* entry aggregates the call-for-heat of opt-in zones into one boiler-demand sensor. **Boiler actuation is opt-in:** leave the on/off actions empty and the hub stays purely diagnostic (wire your own automation off the sensor); set them to switch a boiler with activation delay, keep-alive and minimum on/off cycling. The **min-on / min-off timers are clamped up to a 120 s floor** — a physical anti-short-cycle dwell a too-short setting can never undercut (`keep-alive = 0` remains a valid "off"). Options: boiler count / power thresholds, on/off actions, activation-delay · keep-alive · min-on · min-off, max-power & current-power sensors, max flow temperature, flow hysteresis, and default heat source.

### Card (dashboard display)

Poise ships its own Lovelace card (auto-registered — no separate install). Add it via *Add card → Poise* and configure it in the **visual editor**, or in YAML. Everything here is display-only; unknown values fall back to sane defaults (ADR-0057).

| Option | Default | Purpose |
| --- | --- | --- |
| `entity` | — | The Poise `climate` entity to display. |
| `density` | `comfortable` | `comfortable` or `compact` (tighter spacing for small cards). |
| `controls` | `dial` | `dial` (drag to set), `buttons` (+/− steppers), or `none` (display-only — e.g. a locked wall tablet). |
| `history` | `{ show: true, hours: 24 }` | Temperature history graph; `hours` is `12` / `24` / `48`; `false` hides it. |
| `sections.chips` | all | Condition chips to show, a subset of `[hvac, window, temperature, humidity, co2, ca]` (`false` = none). |
| `sections.pmv` | `true` | Comfort (PMV / PPD) lamp. |
| `sections.shadow_pill` | `true` | Shadow-mode detail pill (`show_shadow` is the legacy alias). |
| `sections.learning` | `true` | Learning-progress / confidence line. |
| `sections.presets` | `true` | HA preset buttons (Eco / Comfort / Boost / Away …). |
| `temperature_scale` · `humidity_thresholds` · `co2_scheme` · `co2_thresholds` | comfort · — · `uba` · — | Room-condition traffic-light thresholds (ADR-0049; card-side verdict, no recorder load). |
| `abs_humidity_floors` | — | Dry-side `[alertLo, warnLo]` thresholds in g/m³ for the humidity lamp (ADR-0066). |

The dial also draws a **mould-limit tick** at the anti-condensation floor whenever a humidity sensor is configured, so the safe lower bound stays visible.

```yaml
type: custom:poise-card
entity: climate.wohnzimmer
density: comfortable
controls: dial            # dial | buttons | none
history:
  show: true
  hours: 24
sections:
  chips: [hvac, window, humidity, co2]
  pmv: true
  shadow_pill: true
  learning: true
  presets: true
```

## Entities created

**Per room** — `climate.<room>` (the thermostat: comfort-band attributes, HA preset modes, and the live setpoint), a per-zone **`switch`** that toggles the open-window bypass, two **`button`** entities (*too warm* / *too cold* — the voluntary comfort-feedback channel behind the clo-offset learning, ADR-0067; also callable as the service `poise.comfort_feedback`), and **23 diagnostic `sensor` entities** (each suffixed onto the room name):

- `operative_temperature`, `t_rm`, `mrt`, `q_solar`, `beta_s`, `tau_hours` — comfort inputs and learned physics.
- `confidence`, `identification_progress`, `learning_phase` — model-learning progress.
- `mpc_power`, `mpc_weight`, `mpc_setpoint` — predictive-shadow output.
- `tpi_valve_percent`, `pi_setpoint`, `pi_offset`, `ref_offset` — the per-device actuation shadow (valve duty *or* droop compensation) and the actuator↔room frame offset, as long-term-statistics series for the winter shadow→live evaluation.
- `ca_deviation_k`, `ca_cycles_per_h`, `ca_time_in_band` — the EN 15500-1 control-accuracy metric.
- `compressor_guard_blocked`, `tick_duration_ms` — single-AC guard state and per-tick compute budget.
- `vent_advice` — the ventilation-advice state token (`idle` / `open` / `close` / `discourage`) for automations (ADR-0066).
- `override_expires_at` — the manual hold's end-time as a timestamp, enabled by default so the override is visible without the card (ADR-0059).

Only four are enabled on a fresh install — `operative_temperature`, `confidence` (*Model confidence*), `learning_phase` and `override_expires_at` — plus the climate entity, the bypass switch and the two feedback buttons. The other 19 sensors are registered but disabled; enable the ones you want under *Settings → Devices & Services → Entities*.

Everything else Poise exposes for transparency lives as **attributes on the `climate` entity — not as standalone sensors** — so read them from `climate.<room>`'s state attributes rather than looking for a `sensor.<room>_…`: the comfort index (`pmv` / `ppd`), the cooling / humidity shadows (`cool_sp_eff`, `dry_active`, `abs_humidity_gkg`, `fr_*`, `fan_ce_k`, `fan_velocity_ms`), the reference-frame details (`ref_offset_dev`, `ref_offset_trusted`, `cool_sp_compensated`), the transparency flags (`override_clamped`, `mould_floor`, `dewpoint`), the hold lifecycle (`override_active`, `override_reason`, `sp_adopt_reason`, `mode_adopt_reason`), the savings estimate (`savings_*`) and this zone's `heat_demand`. (For example there is no `sensor.<room>_pmv`; read the `pmv` attribute from the climate entity instead. The four `tpi_*`/`pi_*`/`ref_offset` values above are the exception — they exist *both* as attributes and as the disabled-by-default statistics sensors listed earlier.)

**System hub** — one boiler-demand `binary_sensor` aggregate (with zone counts, flow target and load-shedding attributes).

> **Entity ids in the examples below** follow Home Assistant's usual `has_entity_name` slug: the device (room) name plus the *translated* entity name — a room called *Wohnzimmer* gets `climate.wohnzimmer`, `sensor.wohnzimmer_model_confidence`, `switch.wohnzimmer_ignore_open_window_reaction`, `button.wohnzimmer_too_warm`. Check yours in *Developer tools → States*.


## How Poise updates its data

Poise polls no network and no cloud (`iot_class: local_polling` refers to polling Home Assistant's own state machine). Each **room** entry is a `DataUpdateCoordinator` with a **60-second** update interval; that scheduled tick *is* the control loop — read inputs, estimate, decide, write at most one command per actuator, publish.

Between scheduled ticks a change on one of these entities requests an **extra tick immediately**:

| Reacts at once | Only picked up by the next scheduled tick |
| --- | --- |
| room temperature sensor · window sensor(s) · the actuator itself · presence (person / device_tracker) · occupancy sensor | outdoor temperature · humidity · running-mean `T_rm` · MRT · irradiance · the weather entity · the TRV's external-temperature `number` |

Two filters stop that from becoming a refresh storm: a state-change event whose **state value is unchanged** is dropped (pure attribute churn — the single exception is the actuator's `hvac_action`), and the surviving requests are coalesced by the coordinator's request-refresh debouncer, so a burst collapses into one tick. Your own commands (setpoint, HVAC mode, preset, the bypass switch) also request a refresh, so a change you make is acted on at once instead of up to a minute later.

The **weather forecast** behind optimal start is not polled on the tick: it comes from Home Assistant's own `weather.get_forecasts` behind a TTL cache with back-off. Only a cold cache awaits I/O; a stale-but-present cache is served immediately and refreshed in the background.

The optional **Poise System hub** deliberately runs *without* a coordinator update interval (`update_interval=None`). It is driven by its own 60-second timer registered at setup, so boiler keep-alive and the minimum on/off cycling keep running even when no zone is publishing.

Learned model and user intent are written to Home Assistant's `.storage`, and flushed on Home Assistant shutdown rather than only periodically.


## Examples

### Announce when automatic control comes back

Poise fires `poise_override_ended` on the bus when a manual hold ends. Payload: `zone`, `entry_id`, `reason` (`expired_timer` · `schedule_point` · `presence_change` · `user_resume` · `mode_change`) and `entity_id` when the climate entity is known.

```yaml
automation:
  - alias: "Poise: automatic control resumed"
    triggers:
      - trigger: event
        event_type: poise_override_ended
    actions:
      - action: notify.persistent_notification
        data:
          title: "Poise · {{ trigger.event.data.zone }}"
          message: >-
            Manual hold ended ({{ trigger.event.data.reason }}) —
            the zone follows the schedule again.
```

### Drop every manual hold when the house empties

`poise.resume_schedule` clears the active hold *and* the preset. Called **without a target** it applies to every Poise room zone; with a target only to the zones behind those entities/devices/areas.

```yaml
automation:
  - alias: "Poise: resume the schedule when everyone has left"
    triggers:
      - trigger: state
        entity_id: group.family
        to: "not_home"
        for: "00:10:00"
    actions:
      - action: poise.resume_schedule   # no target = all room zones
```

### Act on the ventilation advice

`poise_ventilation_advice` fires on every change of the advice **action**, with `zone`, `entry_id`, `action` (`idle` · `open` · `close` · `discourage`), `reason` and `delta_gm3` (indoor − outdoor absolute humidity). The same token is also available as the `vent_advice` sensor and the `vent_action` climate attribute — the event is the fast rail, the sensor the slow one.

```yaml
automation:
  - alias: "Poise: airing advice"
    triggers:
      - trigger: event
        event_type: poise_ventilation_advice
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.action == 'open' }}"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >-
            {{ trigger.event.data.zone }}: airing recommended
            ({{ trigger.event.data.reason }},
            {{ trigger.event.data.delta_gm3 }} g/m³ vs. outside).
```

Poise never opens a window, runs a fan or drives a humidifier itself — this advice is exactly the seam where your own automation takes over.

### Switch a shared boiler off the hub's demand sensor

For a hub left in its default **diagnostic-only** mode (no boiler actions configured):

```yaml
automation:
  - alias: "Poise: boiler follows the aggregated demand"
    triggers:
      - trigger: state
        entity_id: binary_sensor.poise_system_boiler_demand
        to: ["on", "off"]
    actions:
      # resolves to switch.turn_on / switch.turn_off
      - action: "switch.turn_{{ trigger.to_state.state }}"
        target:
          entity_id: switch.boiler
```

If you would rather let Poise do it, configure the hub's on/off actions instead — then it owns the boiler with activation delay, keep-alive and the 120 s-floored minimum on/off dwell, and you should *not* run this automation as well.

### Feed comfort feedback from a physical button

Same channel as the two `button` entities; the service just makes it reachable from a wall switch, a voice assistant or a dashboard tap.

```yaml
automation:
  - alias: "Poise: wall button reports 'too cold'"
    triggers:
      - trigger: state
        entity_id: binary_sensor.wohnzimmer_wall_button
        to: "on"
    actions:
      - action: poise.comfort_feedback
        target:
          entity_id: climate.wohnzimmer
        data:
          direction: cold      # warm | cold
```

Feedback is observe-only: it folds into the household clothing assumption and may surface a *fixable* repair issue suggesting a clo change. Presses in masked situations (window open, active hold, setback/absent, frozen sensors, invalid PMV) are discarded.

### Air a room on purpose without losing the heating

```yaml
automation:
  - alias: "Poise: deliberate airing keeps the heating on"
    triggers:
      - trigger: state
        entity_id: input_boolean.deliberate_airing
        to: "on"
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.badezimmer_ignore_open_window_reaction
```

### Notice a heating failure

The climate entity carries `heating_failure` / `cooling_failure` as attributes (and Poise raises the matching repair issue itself):

```yaml
automation:
  - alias: "Poise: heating failure"
    triggers:
      - trigger: state
        entity_id: climate.wohnzimmer
        attribute: heating_failure
        to: true
        for: "00:15:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "Wohnzimmer is not warming up despite a heating demand."
```

### Dashboard without the Poise card

The bundled `custom:poise-card` (see [Card](#card-dashboard-display)) is the intended surface, but everything it shows is readable from plain cards too:

```yaml
type: entities
title: Wohnzimmer — Poise
entities:
  - entity: climate.wohnzimmer
  - entity: sensor.wohnzimmer_operative_temperature
  - entity: sensor.wohnzimmer_model_confidence
  - entity: sensor.wohnzimmer_learning_phase
  - entity: sensor.wohnzimmer_override_expires_at
  - type: attribute
    entity: climate.wohnzimmer
    attribute: comfort_low
    name: Comfort band — lower
  - type: attribute
    entity: climate.wohnzimmer
    attribute: comfort_high
    name: Comfort band — upper
  - type: attribute
    entity: climate.wohnzimmer
    attribute: pmv
    name: Comfort index (PMV)
  - entity: button.wohnzimmer_too_warm
  - entity: button.wohnzimmer_too_cold
```


## Known limitations

Poise is **Alpha**. The list below is the honest counterpart to the [Capability status](#capability-status) at the top.

### The predictive machinery does not drive yet

Everything under *Shadow / diagnostic* is computed every tick against the live learned model and published, but **writes nothing**. That is enforced structurally, not by convention: within the tick exactly one adapter module may dispatch service calls (pinned by a test), and the only actuation path it ever constructs is the plain setpoint write.

- **MPC** (`mpc_*`) never commands the actuator; live authority is gated on cold-season validation (ADR-0033).
- **Direct-valve TPI** (`tpi_*`) is computed for devices with a writable valve opening but the valve is not written (ADR-0036). `valve_closing_degree` is never written at all.
- **PI setpoint compensation** (`pi_*`) is computed for setpoint-only TRVs and not applied (ADR-0037).
- **TRV offset calibration** (`control/calibration.py`) is written and unit-tested but **not wired into the tick**. Without a TRV external-temperature input, Poise performs no live TRV offset compensation.
- **Multi-zone load shedding, compressor-group protection and the flow-temperature allocator** are shadow computations; only the boiler-demand aggregate (and, opt-in, the boiler switch itself) actuates.
- **Fan cooling-effect credit** (`fan_ce_k`) and the **PMV band shift** stay diagnostic until the ADR-0055/0069 maturity gates release them.
- **The efficiency report** (`savings_*`) and the **humidity/ventilation axis** are observe-only by design — no fan, no window, no humidifier is ever commanded.
- **KNX expose** is designed, not built.

### Environment and device constraints

- **Celsius only.** Setup aborts on an imperial/°F Home Assistant; the whole control path is metric.
- **`heat_cool`-only actuators are rejected.** Poise writes exactly one target temperature per actuator, so a device whose only conditioning mode is the dual-setpoint `heat_cool` cannot be driven. A device that *also* offers plain `heat` or `cool` is fine.
- **Single writer per actuator.** One thermostat belongs to exactly one Poise zone, and Poise assumes it is the only thing writing that setpoint. A second controller — another automation, a Generic Thermostat, the device's own weekly program or its internal adaptive/smart-temperature loop — will fight it. Poise *detects* the device-side cases and raises a repair issue, but it deliberately does not switch them off for you.
- **One actuator per zone.** Multi-actuator arbitration is designed (ADR-0046) but a zone still writes a single climate entity.
- **Only setpoint and HVAC mode are adopted from the device.** Fan speed, swing, device-side presets and `heat_cool` dual setpoints are left alone and create no hold. Adoption is also conditional — see [Geräteseitige Eingriffe (Adoption)](#geräteseitige-eingriffe-adoption) for every reason a device-side change is *not* taken over.
- **Home Assistant 2025.10 or newer** (enforced by HACS); the integration is UI-configured only — there are no YAML keys.

### It has to learn first

- A fresh zone starts in `learning_phase: cold` and is not `identified`. Optimal start/stop and the shadow estimators are gated on an identified model, so the first days behave like a plain setpoint thermostat.
- The learned model lives per zone. Reconfiguring preserves it; deleting the entry deletes it.
- Learning **pauses** while a window is open, while the room sensor is frozen, and during detected heating/cooling failures — deliberately, so the estimator never learns from a broken room.
- Room sensor placement dominates the result. A sensor on or near the radiator yields an implausibly short time constant and Poise raises a repair issue about it; the model degrades regardless.

### Explicit non-goals

Poise does not manage ventilation-system hygiene (VDI 6022), does not act on CO₂, and cannot humidify — see [Scope & Non-Goals](#scope--non-goals).


## Troubleshooting

Poise reports problems as Home Assistant **repair issues** (*Settings → System → Repairs*) rather than log noise. Almost all of them are transition-based: they appear when the condition starts and disappear on their own when it ends. Three are *fixable* — they offer an **Apply / Ignore** choice instead of just text.

### Inputs and sensors

| Repair issue | What it means | What to do |
| --- | --- | --- |
| **Room sensor unavailable** | The configured room temperature sensor is `unavailable`; Poise cannot control this room. | Check the sensor/device. Clears automatically. |
| **Room sensor frozen** | The reading has not changed for a long time (dead battery, stalled integration). Learning is paused; control continues on the last value. | Check battery/integration. Clears on the next real update. |
| **Room sensor may be at the heat source** | The learned time constant is implausibly short — typical of a sensor on or near the radiator (e.g. a TRV's built-in sensor). | Move to a free-standing position away from the heater. The room model degrades until you do. |
| **Window sensor unavailable** | The configured window contact(s) cannot be read; Poise falls back to slope-based auto-detection. | Check the contact. Clears automatically. |
| **Mould protection inactive** | The humidity sensor is unavailable, so the mould-avoidance minimum temperature cannot be computed. Frost protection still applies. | Check the humidity sensor. Clears automatically. |
| **A required entity is disabled** | The room sensor or the thermostat is *disabled* in the entity registry, so it will never publish a state and a retry loop would never end. | Re-enable it under *Settings → Devices & Services → Entities*, then reload Poise. |

### The thermostat / actuator

| Repair issue | What it means | What to do |
| --- | --- | --- |
| **Thermostat unavailable** | The controlled climate entity is `unavailable`; no setpoint can be written. | Check the device/integration. Clears automatically. |
| **Thermostat's own schedule is active** | The device's built-in weekly program is switched on and will fight Poise. | Turn the device schedule off so Poise owns the setpoint. |
| **Thermostat's own adaptive mode is active** | The device runs its own adaptive/smart-temperature loop — a second regulator on the same valve. | Turn that mode off. (On a Sonoff TRVZB this is also what makes valve-opening writes ineffective.) |
| **Thermostat reports a fault** | The device signals a valve/installation fault — not mounted correctly, valve failure, bad calibration, broken external-sensor link. | Check the device; re-mount or re-pair. |
| **Valve may be stuck** | The valve's calibration step count is near zero — calibration failed or the valve is mechanically jammed. | Re-pair or re-calibrate the TRV; clears once a normal step count is reported. |
| **Thermostat battery low** | Battery at or below 15 %; sensing and valve actuation degrade before the device dies. | Replace the battery. |
| **Actuator not applying commands** | Writes are dispatched but the device keeps reporting a different setpoint or mode — the write-convergence watchdog escalated. | Check the Zigbee/Wi-Fi link, the device's child lock, or an internal smart mode overriding external commands. Clears when a command finally lands. |
| **External-temperature input implausible** | The `number` entity configured as the TRV's external-temperature input does not look like a temperature input. Poise stopped feeding it and handed the TRV's sensor source back to `internal`. | Pick a different entity in the zone's *Reconfigure*, or clear the field. |
| **Operative input not available** | Operative TRV input is enabled but no usable external-temperature input exists for this thermostat; Poise fell back to air-side control. | Configure a valid external-temperature `number`, or switch operative input off. |

### Control and safety

| Repair issue | What it means | What to do |
| --- | --- | --- |
| **Heating failure — *zone*** | The room is not warming up despite a heating demand. Poise keeps commanding heat. | Check the valve/radiator/boiler. Clears when the room warms. |
| **Cooling failure — *zone*** | The room is not cooling despite a cooling demand. | Check the AC/heat pump (compressor, filter, airflow) and that windows are closed. |
| **Control tick repeatedly failing** | Several consecutive control updates raised an error; control is not running reliably for this room. | Look for the underlying exception in the Home Assistant log — and please report it. |
| **Cannot save learned model** | Repeated failures writing to `.storage`; learning and recent changes would be lost on restart. | Check disk space and the `.storage` directory. Clears on the next successful save. |

### Multi-zone hub

| Repair issue | What it means | What to do |
| --- | --- | --- |
| **Freezing room not controlling the shared boiler** | Listed rooms sit at frost-protection temperature but are not opted into the boiler aggregate, so it will not fire for them. | Enable *This room may request the shared boiler* under *Reconfigure → Shared plant* for rooms the boiler actually heats. A cooling-only room can stay off. |
| **Room sensor lost — heating on frost protection** | Listed rooms lost their temperature sensor and fell back to local frost protection; the hub is firing the boiler so they do not freeze. | Fix the sensor (battery/integration). Comfort control is degraded until it returns. |

### Suggestions and hints (advisory)

These come from the override-pattern learning and are gated on the per-zone *Suggestion learning* toggle (default on). The first three are **fixable**: choosing *Apply* writes the config change through the normal options path; either choice stamps a 30-day cool-down for that pattern.

| Repair issue | What it means |
| --- | --- |
| **Raise / lower the comfort base?** *(fixable)* | You repeatedly overrode the setpoint in the same direction. Apply shifts the comfort base by the offered step. |
| **Start the comfort window earlier?** *(fixable)* | You repeatedly overrode *before* the comfort window opened. Apply moves the window start earlier. |
| **Raise / lower the clothing assumption?** *(fixable)* | Your *too warm* / *too cold* feedback consistently points one way. Apply shifts the clo offset by 0.1. |
| **Heat-only / cool-only mode in the wrong season** | The zone's climate mode is pinned to one direction while the outdoor running mean has been past the opposite lockout for days, so conditioning is gated anyway. Purely advisory — Poise never switches the mode itself. |

### Things that are not repair issues

| Symptom | Explanation |
| --- | --- |
| The setpoint I typed was changed | A value outside the comfort band is **clamped to the band edge** and flagged as `override_clamped` rather than silently accepted. Frost, mould and the open-window reaction outrank a manual hold entirely. |
| My change on the TRV wheel "didn't stick" | Device-side adoption is conditional. The per-tick reason is on the climate entity as `sp_adopt_reason` / `mode_adopt_reason` (`own_echo`, `echo_window`, `stable_offset`, `schedule_active`, `safety_window`, …); the table under [Geräteseitige Eingriffe (Adoption)](#geräteseitige-eingriffe-adoption) explains each one. |
| Optimal start does nothing | It is gated on an *identified* model. Check `sensor.<room>_learning_phase` and `sensor.<room>_model_confidence`. |
| The `mpc_*` / `tpi_*` / `pi_*` sensors are missing | They ship **disabled by default**; enable them under *Settings → Devices & Services → Entities*. Only four diagnostic sensors are enabled on a fresh install. |
| There is no `sensor.<room>_pmv` | The comfort index and most shadow values are **attributes on the climate entity**, not separate sensors — see [Entities created](#entities-created). |
| Nothing is written to the actuator | Poise writes only on a real change: the setpoint is compared against the device's actual value, snapped to its step, and skipped when it already matches. |

For anything else, `custom_components.poise` at debug level logs the per-tick decision, and *Settings → Devices & Services → Poise → ⋮ → Download diagnostics* produces a redacted dump worth attaching to an issue.

---

### Repository topics (set on GitHub)

`home-assistant` · `homeassistant` · `hacs` · `custom-component` · `thermostat` · `climate` · `hvac` · `heating` · `cooling` · `trv` · `en16798` · `operative-temperature`
