"""Ventilation advice: when opening a window helps — and when it harms.

ADR-0066 feature B (design 2026-07-Feuchte-Achse). A pure decision over
absolute humidity in/out [g/m^3], the EWMA-averaged surface RH (the mould
*cause*, EN ISO 13788 argues in monthly means — a tick value would be
norm-foreign and alarm-fatiguing) and the occupancy gate of ADR-0050/0058:
comfort reasons only while occupied, building protection always. ADVICE ONLY —
this verdict must never reach ``humidity_decide``, ``dual_setpoint`` or the
constraint solver, and never commands a device (ADR-0048; import-guard test).

The precedence, hysteresis-latch and dataclass-in/out shape mirror
``humidity_decide``. Heat-cost estimation (``vent_cost_*``) is a deliberately
later increment; the B.5 emission edge (``AdviceEmission`` /
``advice_transition``) lives below — delivery stays in the glue.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Working values (implementation plan §5; all published with the advice).
DEFAULT_DELTA_ON_GM3: float = 3.0  # field-established open threshold (blueprints)
DEFAULT_DELTA_OFF_GM3: float = 1.5  # asymmetric exit — same anti-chatter pattern
DEFAULT_DRY_ALERT_GM3: float = 5.0  # ~29 % RH @ 20 °C (design A.3)
DEFAULT_DRY_WARN_GM3: float = 7.0  # ~40 % RH @ 20 °C — physiological floor
DEFAULT_MOIST_GM3: float = 8.7  # 20 °C/50 % (DIN 4108-2 reference indoor climate)
DEFAULT_SURFACE_LIMIT_PCT: float = 80.0  # mould criterion (EN ISO 13788, mold.py)
DEFAULT_SURFACE_MARGIN_PP: float = 5.0  # technical margin (sensor noise, f_Rsi)
DEFAULT_CO2_PPM: float = 1000.0  # UBA de-facto ventilation line (ADR-0049)
# EWMA time constant for the surface-RH mean. Working value ~48 h (Airthings
# line) — a REACTIVITY compromise and calibration target, NOT normatively
# derived from the Sedlbauer isopleths (design §12.2 warning).
DEFAULT_SURFACE_TAU_MIN: float = 48.0 * 60.0


@dataclass(frozen=True, slots=True)
class VentConfig:
    delta_on_gm3: float = DEFAULT_DELTA_ON_GM3
    delta_off_gm3: float = DEFAULT_DELTA_OFF_GM3
    dry_alert_gm3: float = DEFAULT_DRY_ALERT_GM3
    dry_warn_gm3: float = DEFAULT_DRY_WARN_GM3
    moist_gm3: float = DEFAULT_MOIST_GM3
    surface_limit_pct: float = DEFAULT_SURFACE_LIMIT_PCT
    surface_margin_pp: float = DEFAULT_SURFACE_MARGIN_PP
    co2_ppm: float = DEFAULT_CO2_PPM


_DEFAULT = VentConfig()


@dataclass(frozen=True, slots=True)
class VentilationAdvice:
    action: str  # "idle" | "open" | "close" | "discourage"
    reason: str  # stable token: mold_risk|too_dry|moisture_out|co2|
    #             target_reached|thermal_floor|no_gain|no_data
    level: str  # "ok" | "warn" | "alert" (card urgency)
    delta_gm3: float | None  # w_in - w_out behind the advice (None w/o data)

    @property
    def advice_active(self) -> bool:
        """The hysteresis latch fed back as ``prev_advice_active``."""
        return self.action == "open"


def ewma_step(prev: float | None, x: float, dt_min: float, tau_min: float) -> float:
    """Time-aware exponential moving average step (surface-RH mean fold).

    First observation seeds with ``x`` (same cold-start rule as the T_rm
    tracker). ``tau_min`` is the e-folding time; a single shower spike moves a
    48-h mean by well under a point, a persistently wet wall does not.
    """
    if prev is None:
        return x
    if dt_min <= 0.0 or tau_min <= 0.0:
        return prev
    a = 1.0 - math.exp(-dt_min / tau_min)
    return prev + a * (x - prev)


def ventilation_advise(
    *,
    w_in_gm3: float | None,
    w_out_gm3: float | None,
    surface_rh_mean_pct: float | None,
    mold_floor_binding: bool,
    mold_capped: bool,
    room_at_thermal_floor: bool,
    co2_ppm: float | None,
    window_open: bool,
    occupied: bool,
    prev_advice_active: bool,
    cfg: VentConfig = _DEFAULT,
) -> VentilationAdvice:
    """Decision table B.2 of the design, precedence top-down.

    Building protection (mould, rule 1) and the dryness veto (rule 2) are
    never occupancy-gated; the comfort reasons (moisture, CO2 — rules 3/4)
    only fire while occupied. Rule 5 closes the loop event-driven instead of
    with the blueprints' fixed timer. Every moisture rule additionally
    requires OUTSIDE air to be drier than inside — venting against a more
    humid outdoors would import moisture, so without a plausible gain the
    advice degrades silently (``no_data``/``no_gain``), never wrongly.
    """
    if w_in_gm3 is None or w_out_gm3 is None:
        # Design §9: no indoor value or no outdoor source -> feature silent.
        return VentilationAdvice("idle", "no_data", "ok", None)
    delta = w_in_gm3 - w_out_gm3
    outside_drier = w_out_gm3 < w_in_gm3
    # Rule 1 — mould cause (EWMA mean, never gated). Escalates to alert when
    # the floor is currently costing heat (binding) or can no longer protect
    # (capped). Requires drier outside air to be actionable at all.
    if (
        surface_rh_mean_pct is not None
        and surface_rh_mean_pct >= cfg.surface_limit_pct - cfg.surface_margin_pp
        and outside_drier
    ):
        level = "alert" if (mold_floor_binding or mold_capped) else "warn"
        return VentilationAdvice("open", "mold_risk", level, round(delta, 1))
    # Rule 2 — dryness veto (never gated): venting a dry room against drier
    # outside air over-dries it further.
    if w_in_gm3 <= cfg.dry_warn_gm3 and outside_drier:
        return VentilationAdvice("discourage", "too_dry", "warn", round(delta, 1))
    # Rule 5a — thermal floor (never gated, BEFORE the comfort rules): the
    # room heating against the open window at the mould/frost floor must win
    # over any comfort reason to keep venting.
    if window_open and room_at_thermal_floor:
        return VentilationAdvice("close", "thermal_floor", "warn", round(delta, 1))
    # Rules 3/4 — comfort, occupancy-gated. Asymmetric hysteresis on delta.
    threshold = cfg.delta_off_gm3 if prev_advice_active else cfg.delta_on_gm3
    if occupied and delta >= threshold and w_in_gm3 > cfg.moist_gm3:
        return VentilationAdvice("open", "moisture_out", "ok", round(delta, 1))
    if occupied and co2_ppm is not None and co2_ppm >= cfg.co2_ppm:
        return VentilationAdvice("open", "co2", "ok", round(delta, 1))
    # Rule 5b — close: the cause is gone (event-driven, not a timer).
    if window_open and delta < cfg.delta_off_gm3:
        return VentilationAdvice("close", "target_reached", "ok", round(delta, 1))
    return VentilationAdvice("idle", "no_gain", "ok", round(delta, 1))


# --- B.5 emission edge (ADR-0066): pure decision, delivery stays in glue ----


@dataclass(frozen=True, slots=True)
class AdviceEmission:
    """What the glue should deliver for one advice transition.

    ``fire_event`` announces EVERY action change on the bus (automations see
    open AND the all-clear); the notification pair is the opt-in human rail
    and tracks only the "open" episode (self-clearing, design B.5).
    """

    fire_event: bool
    notify_create: bool
    notify_dismiss: bool


def advice_transition(
    prev_action: str, action: str, *, notify_opt_in: bool
) -> AdviceEmission:
    """Edge-detect one tick's advice ACTION token against the previous tick.

    ``prev_action == ""`` is the cold start (fresh runtime, no restore):
    settling into ``idle`` announces nothing, but waking up INTO an active
    advice (e.g. restart during an open episode) re-announces it — the
    notification would otherwise be lost across the restart.
    """
    changed = action != prev_action
    if not changed or (prev_action == "" and action == "idle"):
        return AdviceEmission(False, False, False)
    return AdviceEmission(
        fire_event=True,
        notify_create=notify_opt_in and action == "open",
        notify_dismiss=notify_opt_in and prev_action == "open",
    )
