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
# Free-cooling advice (rule 3t, v0.188.0): open when outside is at least
# DT_ON cooler than the room, keep the episode until the edge shrinks below
# DT_OFF (asymmetric anti-chatter, same pattern as the moisture deltas).
DEFAULT_HEAT_OUT_DT_ON_K: float = 2.0
DEFAULT_HEAT_OUT_DT_OFF_K: float = 1.0
# Moisture guard for free-cooling: never trade heat for muggy air — outside
# may be at most this much MORE humid than inside (delta = in - out >= -guard).
DEFAULT_HEAT_OUT_HUMID_GUARD_GM3: float = 1.0
# N2 (v0.192.0) mould guard: how close the smoothed surface RH may come to the
# safe ceiling before free-cooling is vetoed [pp]. Small on purpose — this is a
# guard against advising the LAST step toward the limit, not a second alarm.
DEFAULT_MOLD_GUARD_MARGIN_PP: float = 2.0


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
    heat_out_dt_on_k: float = DEFAULT_HEAT_OUT_DT_ON_K
    heat_out_dt_off_k: float = DEFAULT_HEAT_OUT_DT_OFF_K
    heat_out_humid_guard_gm3: float = DEFAULT_HEAT_OUT_HUMID_GUARD_GM3
    mold_guard_margin_pp: float = DEFAULT_MOLD_GUARD_MARGIN_PP


_DEFAULT = VentConfig()


@dataclass(frozen=True, slots=True)
class VentilationAdvice:
    action: str  # "idle" | "open" | "close" | "discourage"
    reason: str  # stable token: mold_risk|mold_guard|too_dry|moisture_out|co2|
    #             heat_out|cooled_off|target_reached|thermal_floor|
    #             no_gain|no_data
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
    room_c: float | None = None,
    cool_edge_c: float | None = None,
    t_out_c: float | None = None,
    cool_capable: bool = False,
    fan_capable: bool = False,
    prev_heat_out: bool = False,
    surface_rh_pct: float | None = None,
    rh_max_safe_pct: float | None = None,
    cool_edge_protected: bool = False,
) -> VentilationAdvice:
    """Decision table B.2 of the design, precedence top-down.

    Building protection (mould, rule 1) and the dryness veto (rule 2) are
    never occupancy-gated; the comfort reasons (moisture, CO2 — rules 3/4)
    only fire while occupied. Rule 5 closes the loop event-driven instead of
    with the blueprints' fixed timer. Every moisture rule additionally
    requires OUTSIDE air to be drier than inside — venting against a more
    humid outdoors would import moisture, so without a plausible gain the
    advice degrades silently (``no_data``/``no_gain``), never wrongly.

    Rule 3t (free-cooling, v0.188.0) is the thermal sibling for zones that
    can neither cool nor move air (``cool_capable``/``fan_capable`` false —
    the window is their only summer relief): room above the cool edge AND
    outside at least ``heat_out_dt_on_k`` cooler opens; the episode holds
    (``prev_heat_out``) until the edge shrinks below ``heat_out_dt_off_k`` or
    the room reaches the band, then ``cooled_off`` advises closing. The
    moisture guard vetoes muggy outside air (delta >= -humid_guard). NOT
    occupancy-gated by design: night purge is most valuable in an empty room.

    N2 (v0.192.0) adds the two halves of the mould guard. Guard 5 vetoes
    ``heat_out`` when the cooling edge is itself held up by a protection floor
    (``cool_edge_protected`` — such an edge is not a comfort target: airing
    down onto it works AGAINST the protection) or when the smoothed surface RH
    has come within ``mold_guard_margin_pp`` of the safe ceiling. The
    ``mold_guard`` rule is the active counterpart: an open window over a bound
    floor with the CURRENT surface RH already past the ceiling advises closing
    — before rule 5a, which waits for the AIR to reach the floor and is
    therefore too late once the WALLS are over the limit. It deliberately does
    NOT require drier outside air: the risk driver is the surfaces cooling
    down, not imported vapour.
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
    # Rule 1b (N2) — mould GUARD: close the window before the fabric pays.
    # Below rule 1 (drier outside air plus an acute 48-h mean still argues for
    # airing) but above everything else, including the dryness veto, which
    # would only "discourage" where the building needs the window shut. Reads
    # the CURRENT surface RH, not the 48-h mean: the mean is deliberately slow
    # (mould CAUSE), while this is the acute state. Building protection ->
    # never occupancy-gated, and no drier-outside condition.
    if (
        window_open
        and cool_edge_protected
        and surface_rh_pct is not None
        and rh_max_safe_pct is not None
        and surface_rh_pct > rh_max_safe_pct
    ):
        return VentilationAdvice("close", "mold_guard", "warn", round(delta, 1))
    # Rule 2 — dryness veto (never gated): venting a dry room against drier
    # outside air over-dries it further.
    if w_in_gm3 <= cfg.dry_warn_gm3 and outside_drier:
        return VentilationAdvice("discourage", "too_dry", "warn", round(delta, 1))
    # Rule 5a — thermal floor (never gated, BEFORE the comfort rules): the
    # room heating against the open window at the mould/frost floor must win
    # over any comfort reason to keep venting.
    if window_open and room_at_thermal_floor:
        return VentilationAdvice("close", "thermal_floor", "warn", round(delta, 1))
    # Rule 3t — free-cooling (heat_out): capability-gated (window-only zones),
    # asymmetric dT hysteresis, muggy-outside veto. Not occupancy-gated.
    free_cool_zone = not cool_capable and not fan_capable
    # Guard 5 (N2): never advise cooling toward an edge that a protection floor
    # holds up, and stop one margin short of the mould-safe ceiling.
    surface_near_limit = (
        surface_rh_mean_pct is not None
        and rh_max_safe_pct is not None
        and surface_rh_mean_pct >= rh_max_safe_pct - cfg.mold_guard_margin_pp
    )
    if (
        free_cool_zone
        and not cool_edge_protected
        and not surface_near_limit
        and room_c is not None
        and cool_edge_c is not None
        and t_out_c is not None
        and room_c > cool_edge_c
        and t_out_c
        <= room_c - (cfg.heat_out_dt_off_k if prev_heat_out else cfg.heat_out_dt_on_k)
        and delta >= -cfg.heat_out_humid_guard_gm3
    ):
        return VentilationAdvice("open", "heat_out", "ok", round(delta, 1))
    # Rules 3/4 — comfort, occupancy-gated. Asymmetric hysteresis on delta.
    threshold = cfg.delta_off_gm3 if prev_advice_active else cfg.delta_on_gm3
    if occupied and delta >= threshold and w_in_gm3 > cfg.moist_gm3:
        return VentilationAdvice("open", "moisture_out", "ok", round(delta, 1))
    if occupied and co2_ppm is not None and co2_ppm >= cfg.co2_ppm:
        return VentilationAdvice("open", "co2", "ok", round(delta, 1))
    # Rule 3t close — the free-cooling episode ends (edge gone, room in band,
    # or outside turned muggy) while the window is still open. AFTER rules
    # 3/4 on purpose: a still-valid moisture/CO2 reason keeps the window open.
    if window_open and prev_heat_out:
        return VentilationAdvice("close", "cooled_off", "ok", round(delta, 1))
    # Rule 5b — close: the cause is gone (event-driven, not a timer).
    if window_open and delta < cfg.delta_off_gm3:
        return VentilationAdvice("close", "target_reached", "ok", round(delta, 1))
    return VentilationAdvice("idle", "no_gain", "ok", round(delta, 1))


# --- B.5 emission edge (ADR-0066): pure decision, delivery stays in glue ----

# Advice REASONS that carry an episode of their own on the human rails, even
# though their action token is a plain "close" (ADR-0066 N2). Everything else
# is announced by its ACTION change alone.
NOTIFY_REASONS: tuple[str, ...] = ("mold_guard",)


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
    prev_action: str,
    action: str,
    *,
    notify_opt_in: bool,
    prev_reason: str = "",
    reason: str = "",
) -> AdviceEmission:
    """Edge-detect one tick's advice ACTION token against the previous tick.

    ``prev_action == ""`` is the cold start (fresh runtime, no restore):
    settling into ``idle`` announces nothing, but waking up INTO an active
    advice (e.g. restart during an open episode) re-announces it — the
    notification would otherwise be lost across the restart.

    N2 (v0.192.0): a few REASONS carry an episode of their own and must reach
    the human rails even though their action token is the same ``close`` the
    harmless all-clears use (``mold_guard``). For those — and only those — the
    edge is the pair, so ``target_reached -> mold_guard`` announces while
    ``target_reached -> cooled_off`` stays silent. Called without the reason
    arguments this function is bit-identical to the pre-N2 behaviour.
    """
    prev_key = (prev_action, prev_reason if prev_reason in NOTIFY_REASONS else "")
    key = (action, reason if reason in NOTIFY_REASONS else "")
    if key == prev_key or (prev_action == "" and action == "idle"):
        return AdviceEmission(False, False, False)
    episode = action == "open" or reason in NOTIFY_REASONS
    prev_episode = prev_action == "open" or prev_reason in NOTIFY_REASONS
    return AdviceEmission(
        fire_event=True,
        notify_create=notify_opt_in and episode,
        notify_dismiss=notify_opt_in and prev_episode and not episode,
    )
