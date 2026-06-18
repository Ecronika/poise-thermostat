# Poise — Setpoint Thermostat

***Self-learning, norm-based climate control for Home Assistant — comfort kept in balance.***

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/Ecronika/poise-thermostat/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Poise** is a self-learning **thermostat** for Home Assistant that controls **TRVs, climate entities and heating/cooling** with engineering rigor. It unites norm-based comfort, a real building-physics model and direct valve control in a single, fully local integration — no cloud, no heavy dependencies.

It combines **EN 16798-1 adaptive comfort** on a true running-mean outdoor temperature, a real **operative-temperature / mean-radiant (MRT)** model, **mould protection (DIN 4108-2)**, a self-learning **Extended-Kalman building model with MPC planning**, **direct valve / TPI control** with per-device calibration, **cooling**, **KNX** exposure, and a conflict-free **arbitration layer** that turns every module's request into exactly one safe command per actuator.

> **Successor to Smart Setpoint.** Poise merges the five-component Smart Setpoint ecosystem (Blueprint, ha-preheat, TRM/PMOT, irradiance sensor, Virtual MRT) into one installable integration with guided onboarding.

## Highlights

- **Norm-based comfort** — EN 16798-1 adaptive bands (Cat. I–III) on a real running-mean `T_rm`, not the instantaneous outdoor temperature.
- **Operative temperature / MRT** — controls what the room actually *feels* like (air + mean radiant), not just air temperature.
- **Self-learning physics** — mode-gated Extended Kalman Filter learns each room's time constant, losses and solar/heating response; confidence is a real sensor entity.
- **Predictive control** — MPC plans variable heat/cool profiles; Optimal Start and Optimal Stop / coasting are advisory and measurable.
- **Direct valve control** — TPI / `valve_position` / `pi_heating_demand` with learned coefficients, TRV calibration, or PI-compensated setpoint — chosen automatically per device.
- **Mould & frost protection** — surface-humidity model (DIN 4108-2), unconditional safety floors.
- **Cooling & solar** — dual setpoints, measured global irradiance as a learned disturbance and an MRT input — counted once.
- **Efficiency you can see** — heating-degree-hour savings estimate in kWh / €.
- **Robust by design** — visible degradation ladder (measured → derived → estimated → default), repair issues, redacted diagnostics, fully local, zero heavy dependencies.
- **KNX expose** — operative temperature, setpoints, comfort band and heat demand on configurable group addresses (optional).

## Status

Alpha — under active development against a documented architecture (22 ADRs) and a production-identical simulation harness. See the roadmap for milestones (M1 norm comfort → M2 self-learning → M3 valve → M4 MPC → M5 release).

## Installation (HACS)

1. HACS → Integrations → ⋮ → *Custom repositories* → add `https://github.com/Ecronika/poise-thermostat` (type: Integration).
2. Install **Poise Setpoint Thermostat**, restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → Poise.*

---

### Repository topics (set on GitHub)

`home-assistant` · `homeassistant` · `hacs` · `custom-component` · `thermostat` · `climate` · `hvac` · `heating` · `cooling` · `trv` · `mpc` · `en16798` · `operative-temperature` · `comfort` · `knx` · `self-learning`

### One-line description (GitHub *About* / HACS)

> Self-learning thermostat for TRV, climate & heating — EN 16798 adaptive comfort, operative temperature/MRT, MPC, direct valve control, cooling, KNX. Fully local. Successor to Smart Setpoint.
