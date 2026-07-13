# Poise — Setpoint Thermostat

***Self-learning, norm-based climate control for Home Assistant — comfort kept in balance.***

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-0.167.0-blue.svg)](https://github.com/Ecronika/poise-thermostat/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5.svg)](https://www.home-assistant.io/)
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
- **Humidity (dry) & hot-day cooling** — capability-gated and live: a `dry`-capable AC lowers humidity through the dead-band (cool-first, dew-point-guarded, 60 / 55 % hysteresis), and on hot days the cooling edge is raised toward the EN / ASR ceiling (rate-limited ≤ 0.5 K/tick); heat-only TRVs are unaffected (ADR-0050/0051).
- **Open-window reaction (sensor *or* sensorless)** — a configured window sensor or the **slope detector** (open threshold adapted to the learned time constant τ) drops the room to the frost/mould floor through the solver and pauses learning; a per-zone **bypass switch** overrides it. The sensor wins when present.
- **Comfort presets & timed override** — Eco / Comfort / Boost / Away as **norm-clamped offsets on the comfort base** (surfaced as HA preset modes, not free temperatures); a manual setpoint **auto-reverts** to the schedule/preset after a window so it never sticks, and a value pushed outside the comfort band is clamped to it and flagged (`override_clamped`) rather than limited silently.
- **Bundled Lovelace cards** — Poise ships its own cards inside the integration and **auto-registers** them (no separate HACS plugin, no manual resource URL). `poise-card` puts the **EN 16798 comfort band** front and centre — operative temperature & setpoint as markers in the live band, a 24 h history graph, clickable status chips, learning confidence and a **shadow pill that shows what the engine *would* do** (TPI %/PI/MPC). `poise-system-card` surfaces the multi-zone hub (boiler demand, heating zones, flow target, load shedding). Self-contained Lit/TS, only `lit` bundled (ADR-0040).
- **Robust by design** — degradation ladder (measured → derived → estimated → default), repair issues, redacted diagnostics, a change-aware setpoint write-throttle (compares against the device's real setpoint, snapped to its step), and learning + user intent (enable/override/mode) persisted across restarts (and flushed on Home Assistant shutdown, not only periodically). While enabled, Poise also keeps a heat-capable actuator in its `heat` mode so it follows Poise's setpoint instead of running its own `auto`/schedule.

### 🟡 Shadow / diagnostic (computed, not yet actuating)

- **Predictive MPC** — runs every tick against the live learned model and is exposed as `mpc_*` diagnostic values, but **never writes the actuator** in this version. Active write authority is gated on cold-season validation (ADR-0033).
- **Direct-valve TPI** — for a device with a writable valve-open entity (e.g. Sonoff TRVZB `valve_opening_degree`), the TPI valve duty is computed live and exposed as `tpi_*` diagnostics. The valve is **not written** yet — closed-loop validated in the harness, live actuation gated on cold-season validation (ADR-0036).
- **PI-compensated setpoint** — for a setpoint-only TRV (no writable valve), the PI-compensated setpoint that would cancel the device's steady-state droop is computed and exposed as `pi_*` diagnostics (not written); harness-validated (ADR-0037). Every device thus gets exactly one matching shadow: valve → TPI, otherwise → PI.
- **Multi-zone boiler demand** — an optional *Poise System* hub aggregates the call-for-heat across opt-in zones into one frost-safe, device-granular boiler-demand `binary_sensor`. Diagnostic by default (wire your own automation off it); **opt-in actuation** switches a configured boiler service with activation delay, keep-alive and min on/off cycling — the write path stays off unless you set the actions (ADR-0038/0039).
- **Comfort index (PMV/PPD)** — ISO 7730 predicted-mean-vote and %-dissatisfied from air / MRT / humidity with seasonal clo / met, exposed as `pmv` / `ppd` / category — humidity (and, staged, air velocity) finally enter the comfort *evaluation*; the norm band stays the control variable (ADR-0054).
- **Regulation-quality metric (EN 15500-1 CA)** — continuous, bilateral control accuracy: mean Kelvin outside the comfort band, time-in-band and a regime-change ("hunting") rate, time-weighted and persisted (`ca_*`). This is the measurable acceptance gate that will authorise each shadow→live flip — today it only measures (ADR-0055).
- **Fan cooling-effect** — the ASHRAE-55 elevated-air-speed credit a running fan would allow on the cooling setpoint (`fan_ce_k`), diagnostic only (ADR-0054 stage 3 / roadmap M3).
- **Efficiency report** — a live heating-degree-hour savings estimate in kWh / €, computed each tick and published as `savings_*` climate attributes (ADR-0045); diagnostic only, never actuates.

### 🗺️ Roadmap (built or designed, not in the active path)

- **Direct valve / TPI control (live actuation)** — auto-detected for devices with a writable valve-open number (Sonoff TRVZB `valve_opening_degree`, FW v1.1.4+) and harness-validated; today it runs as a diagnostic shadow (above), with live valve writing gated on cold-season validation. `valve_closing_degree` is never written (TRVZB firmware bug). `pi_heating_demand` / calibration paths exist generically.
- **KNX expose** — operative temperature, setpoints, comfort band and heat demand on group addresses (designed, optional).
- **Multi-zone resource coordination** — via the *Poise System* hub (ADR-0038/0039): boiler-demand aggregate + opt-in boiler actuation, plus **load-shedding, compressor-group protection and a flow-temperature allocator computed as diagnostic shadows** (smallest-gap shedding, per-group min-run/off, highest-request-wins flow with anti-hunt hysteresis — the last harness-validated against oscillation, ADR-0013). Zone-side / generator-side enforcement is the next stage.

## Manuelle Eingriffe & Rückkehr zur Automatik

Ein manueller Sollwert ist ein **temporärer Hold**, kein Dauerzustand: Poise übernimmt den von Hand gestellten Wert und kehrt anschließend automatisch in den geregelten Betrieb zurück. **Wann** zurückgekehrt wird, ist konfigurierbar (*Optionen → „Manuelle Eingriffe"*).

| Eingriff | gilt bis | wie beenden |
| --- | --- | --- |
| **Manueller Sollwert** | Policy `schedule` → bis zum nächsten Schaltpunkt; `timer` → fester Timer (Default 2 h); `permanent` → bis zum Widerruf | Modus wählen, X auf der Card, `poise.resume_schedule`, oder Ablauf abwarten |
| **Boost-Preset** | Default 60 min, danach Rückkehr zum vorherigen Preset | Ablauf abwarten oder anderes Preset wählen |
| **Eco / Comfort / Away** | Zustandswahl (kein Timer); **Away** endet über die Anwesenheit | anderes Preset / Modus wählen |
| **HVAC-Modus** | persistent — das ist **Konfiguration**, kein Override | Modus erneut wählen |

**Prioritätenkette** — der jeweils höhere Rang gewinnt:

**Fenster / Frost / Schimmel  >  manueller Sollwert  >  Preset  >  Zeitplan / Anwesenheit**

Sicherheits- und Kontextlagen (offenes Fenster, Frost- und Schimmelschutz) sind nie verhandelbar und setzen sich immer gegen einen manuellen Sollwert durch; dieser schlägt das aktive Preset, und das Preset schlägt Zeitplan und Anwesenheit.

**Wie beenden:** einen HVAC-Modus wählen, das **X** auf der Card antippen, den Service `poise.resume_schedule` aufrufen (Zone oder alle Zonen), oder den Ablauf abwarten.

> **Migration:** Bestehende Installationen behalten das heutige Verhalten (`timer` / 2 h). `schedule` ist nur der Default für **neu eingerichtete** Zonen.

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
| Comfort start / end | no | — | Daily comfort window (enables scheduled setback when set). |
| Outdoor / humidity / MRT / T_rm sensors | no | — | Improve accuracy (mould floor, operative temperature, running mean). |
| Window sensor | no | — | Door/window contact for the open-window reaction (else the slope detector is used). |
| Weather / irradiance | no | — | Forecast for optimal-start; measured solar gain. |
| External-temperature input | no | — | TRV `number` entity Poise feeds the true room temperature to (operative mode). Re-pushed at least every 10 min even when unchanged, so TRVs that time out an external input (e.g. Danfoss ~30 min, Sonoff TRVZB ~1 h) never fall back to their own mounted sensor. |
| Operative input | no | off | Control on operative (felt) temperature instead of air. |
| Adaptive cooling edge | no | auto | Active by default on cool-capable devices (`auto`): lifts the cooling edge to the EN 16798-1 adaptive upper for the running mean (ASR 26 °C capped) instead of over-cooling toward the fixed summer band. `off` forces the fixed summer band; heat-only TRVs are unaffected either way (ADR-0023 §1). |
| Compressor guard · min-off · mode-hold | no | auto · 300 s · 300 s | Single-AC anti-short-cycle (Tuning options): hold a cool/dry mode change that would restart the compressor within min-off, or flip cool↔dry within mode-hold — never a stop or a safety action. Blank timers use the fast-air profile default; set the guard to *off* to disable (ADR-0046 §8). |
| Actuator dynamics | no | auto | Controller time constants per actuator class — `auto` (classify from the learned model) or force `fast_air` / `slow_hydronic` / `very_slow`; faster profiles retune the PI/MPC and throttle setpoint nudges for self-regulating climate entities (ADR-0052). |
| Field-trace recording | no | off | Advanced/diagnostic: append one compact JSONL line per tick to `config/poise_traces/<id>.jsonl` (EKF drive inputs + model snapshot + decision), rotated at ~20 MB. For offline golden-file replay analysis (ADR-0011); pure observation, never touches control. |
| Outdoor cooling / heating lockout | no | 16 / 22 °C | Suppress cooling below / heating above these outdoor temperatures (ADR-0047). |
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

**Per room** — `climate.<room>` (the thermostat: comfort-band attributes, HA preset modes, and the live setpoint), a per-zone **`switch`** that toggles the open-window bypass, and **17 diagnostic `sensor` entities** (each suffixed onto the room name):

- `operative_temperature`, `t_rm`, `mrt`, `q_solar`, `beta_s`, `tau_hours` — comfort inputs and learned physics.
- `confidence`, `identification_progress`, `learning_phase` — model-learning progress.
- `mpc_power`, `mpc_weight` — predictive-shadow output.
- `ca_deviation_k`, `ca_cycles_per_h`, `ca_time_in_band` — the EN 15500-1 control-accuracy metric.
- `compressor_guard_blocked`, `tick_duration_ms` — single-AC guard state and per-tick compute budget.
- `override_expires_at` — the manual hold's end-time as a timestamp, enabled by default so the override is visible without the card (ADR-0059).

Everything else Poise exposes for transparency lives as **attributes on the `climate` entity — not as standalone sensors** — so read them from `climate.<room>`'s state attributes rather than looking for a `sensor.<room>_…`: the comfort index (`pmv` / `ppd`), the cooling / humidity shadows (`cool_sp_eff`, `dry_active`, `abs_humidity_gkg`, `fr_*`, `fan_ce_k`, `fan_velocity_ms`), the actuator↔room reference-frame offset (`ref_offset*`, `cool_sp_compensated`), the transparency flags (`override_clamped`, `mould_floor`, `dewpoint`), and the per-device `tpi_*` / `pi_*` shadow values. (For example there is no `sensor.<room>_pmv`; read the `pmv` attribute from the climate entity instead.)

**System hub** — one boiler-demand `binary_sensor` aggregate (with zone counts, flow target and load-shedding attributes).

---

### Repository topics (set on GitHub)

`home-assistant` · `homeassistant` · `hacs` · `custom-component` · `thermostat` · `climate` · `hvac` · `heating` · `cooling` · `trv` · `en16798` · `operative-temperature` · `comfort` · `self-learning`

### One-line description (GitHub *About* / HACS)

> Self-learning setpoint thermostat for TRV & climate entities — EN 16798 adaptive comfort, operative temperature/MRT, optimal start/stop, mould protection. Fully local. Successor to Smart Setpoint.
