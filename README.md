# Poise — Setpoint Thermostat

***Self-learning, norm-based climate control for Home Assistant — comfort kept in balance.***

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-0.53.0-blue.svg)](https://github.com/Ecronika/poise-thermostat/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Poise** is a self-learning **thermostat** for Home Assistant. It controls TRVs and climate entities through a single, fully local integration — no cloud, no heavy dependencies — using norm-based comfort and a real building-physics model rather than static setpoints.

Today Poise is an **intelligent setpoint controller**: it learns each room's thermal behaviour and writes one safe, norm-clamped setpoint per actuator. The deeper machinery (predictive MPC, direct valve control, KNX) is built and tested but, by design, **not yet driving the actuator** — see the capability status below for exactly what is active.

> **Successor to Smart Setpoint.** Poise merges the five-component Smart Setpoint ecosystem (Blueprint, ha-preheat, TRM/PMOT, irradiance sensor, Virtual MRT) into one installable integration with guided onboarding.

## Capability status

Honest separation of what runs today vs. what is staged. Poise is **Alpha**.

### ✅ Active (drives control / visible today)

- **Norm-based comfort** — active heating/cooling holds the configured comfort base within fixed EN 16798-1 design bands (Cat. I–III), the norm-correct choice for a conditioned room. A real running-mean `T_rm` drives the diagnostics, the seasonless heat-rate prior and optimal-start/stop timing (adaptive free-running bands are computed but are not the live setpoint).
- **Operative temperature / MRT** — controls what the room *feels* like (air + mean radiant), via a virtual-MRT estimator that a real MRT/globe sensor overrides when present.
- **Self-learning physics** — mode-gated Extended Kalman Filter learns each room's time constant, losses and solar/heating response; confidence and identification are real sensor entities.
- **Optimal Start & Optimal Stop** — forecast-aware pre-heating to the comfort deadline and coast-down to the lower comfort edge at window end; advisory (re-entry-free) and gated on an *identified* model.
- **Mould & frost protection** — surface-humidity model (DIN 4108-2) and unconditional safety floors.
- **Solar accounting** — measured global irradiance as a learned disturbance feeding the MRT/comfort path — counted once.
- **Precedence constraint solver** — every bound (frost/mould/ASR cap/device max) is composed with explicit precedence into exactly one safe command per actuator.
- **Cooling decision & modes** — capability-aware dual setpoints; `COOL` is surfaced as an HVAC mode **only when the actuator supports cooling** (heat-only TRVs stay HEAT/OFF).
- **Bundled Lovelace cards** — Poise ships its own cards inside the integration and **auto-registers** them (no separate HACS plugin, no manual resource URL). `poise-card` puts the **EN 16798 comfort band** front and centre — operative temperature & setpoint as markers in the live band, a 24 h history graph, clickable status chips, learning confidence and a **shadow pill that shows what the engine *would* do** (TPI %/PI/MPC). `poise-system-card` surfaces the multi-zone hub (boiler demand, heating zones, flow target, load shedding). Self-contained Lit/TS, only `lit` bundled (ADR-0040).
- **Robust by design** — degradation ladder (measured → derived → estimated → default), repair issues, redacted diagnostics, a change-aware setpoint write-throttle (compares against the device's real setpoint, snapped to its step), and learning + user intent (enable/override/mode) persisted across restarts. While enabled, Poise also keeps a heat-capable actuator in its `heat` mode so it follows Poise's setpoint instead of running its own `auto`/schedule.

### 🟡 Shadow / diagnostic (computed, not yet actuating)

- **Predictive MPC** — runs every tick against the live learned model and is exposed as `mpc_*` diagnostic values, but **never writes the actuator** in this version. Active write authority is gated on cold-season validation (ADR-0033).
- **Direct-valve TPI** — for a device with a writable valve-open entity (e.g. Sonoff TRVZB `valve_opening_degree`), the TPI valve duty is computed live and exposed as `tpi_*` diagnostics. The valve is **not written** yet — closed-loop validated in the harness, live actuation gated on cold-season validation (ADR-0036).
- **PI-compensated setpoint** — for a setpoint-only TRV (no writable valve), the PI-compensated setpoint that would cancel the device's steady-state droop is computed and exposed as `pi_*` diagnostics (not written); harness-validated (ADR-0037). Every device thus gets exactly one matching shadow: valve → TPI, otherwise → PI.
- **Multi-zone boiler demand** — an optional *Poise System* hub aggregates the call-for-heat across opt-in zones into one frost-safe, device-granular boiler-demand `binary_sensor`. Diagnostic by default (wire your own automation off it); **opt-in actuation** switches a configured boiler service with activation delay, keep-alive and min on/off cycling — the write path stays off unless you set the actions (ADR-0038/0039).

### 🗺️ Roadmap (built or designed, not in the active path)

- **Direct valve / TPI control (live actuation)** — auto-detected for devices with a writable valve-open number (Sonoff TRVZB `valve_opening_degree`, FW v1.1.4+) and harness-validated; today it runs as a diagnostic shadow (above), with live valve writing gated on cold-season validation. `valve_closing_degree` is never written (TRVZB firmware bug). `pi_heating_demand` / calibration paths exist generically.
- **KNX expose** — operative temperature, setpoints, comfort band and heat demand on group addresses (designed, optional).
- **Multi-zone resource coordination** — via the *Poise System* hub (ADR-0038/0039): boiler-demand aggregate + opt-in boiler actuation, plus **load-shedding, compressor-group protection and a flow-temperature allocator computed as diagnostic shadows** (smallest-gap shedding, per-group min-run/off, highest-request-wins flow with anti-hunt hysteresis — the last harness-validated against oscillation, ADR-0013). Zone-side / generator-side enforcement is the next stage.
- **Efficiency report** — heating-degree-hour savings in kWh / €.

## Status

Alpha — under active development against a documented architecture (35+ ADRs) and a production-identical simulation harness, in which the predictive core (EKF → MPC → optimal start/stop → gate) is validated end-to-end. Roadmap milestones: M1 norm comfort ✅ → M2 self-learning ✅ → M3 valve (hardware-parked) → M4 MPC (shadow live, active gated on winter validation) → M5 release.

## Installation (HACS)

1. HACS → Integrations → ⋮ → *Custom repositories* → add `https://github.com/Ecronika/poise-thermostat` (type: Integration).
2. Install **Poise Setpoint Thermostat**, restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → Poise.*

Use a **free-standing room sensor** (not the TRV's internal sensor) for best results; Poise raises a repair issue if it detects a likely heat-source-mounted sensor.

---

### Repository topics (set on GitHub)

`home-assistant` · `homeassistant` · `hacs` · `custom-component` · `thermostat` · `climate` · `hvac` · `heating` · `cooling` · `trv` · `en16798` · `operative-temperature` · `comfort` · `self-learning`

### One-line description (GitHub *About* / HACS)

> Self-learning setpoint thermostat for TRV & climate entities — EN 16798 adaptive comfort, operative temperature/MRT, optimal start/stop, mould protection. Fully local. Successor to Smart Setpoint.
