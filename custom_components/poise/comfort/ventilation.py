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
# N5: the two thresholds above are ABSOLUTE, and an absolute gram count means a
# different relative humidity at every room temperature — 8.7 g/m³ is 56.8 % RH
# at 18 °C but only 32.1 % at 28 °C. Both are therefore paired with a RELATIVE
# companion, and both companions are the SAME point expressed on the other
# axis, so nothing new had to be calibrated:
#   * 8.7 g/m³ IS 50 % RH at the 20 °C reference temperature -> moist_rh_pct.
#     The two conditions coincide at the reference climate the number comes
#     from; below it the absolute test binds, above it the relative one does.
#   * 7.0 g/m³ IS ~40 % RH at 20 °C. The dryness veto does NOT take 40 here
#     but 35, deliberately: rule 2 sits ABOVE rule 3t, so a 40 % line would
#     veto free-cooling for a summer room at 26 °C/40 % (9.8 g/m³ — not dry by
#     any measure), and the veto would quietly cost the hot-day advice the 3t
#     rule exists for. 35 % keeps that case free-coolable and still catches
#     the physiologically dry room. Inside the 35–40 % band the review named.
DEFAULT_MOIST_RH_PCT: float = 50.0
DEFAULT_DRY_WARN_RH_PCT: float = 35.0
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
    moist_rh_pct: float = DEFAULT_MOIST_RH_PCT
    dry_warn_rh_pct: float = DEFAULT_DRY_WARN_RH_PCT
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
    rh_pct: float | None = None,
    room_c: float | None = None,
    room_decide_c: float | None = None,
    cool_edge_c: float | None = None,
    t_out_c: float | None = None,
    cool_capable: bool = False,
    fan_capable: bool = False,
    prev_heat_out: bool = False,
    prev_moisture_airing: bool = False,
    prev_moisture_protect: bool = False,
    surface_rh_pct: float | None = None,
    rh_max_safe_pct: float | None = None,
    cool_edge_protected: bool = False,
    surface_needs_warmer: bool = False,
) -> VentilationAdvice:
    """Decision table B.2 of the design, precedence top-down.

    Building protection (mould, rule 1) and the dryness veto (rule 2) are
    never occupancy-gated; the comfort reasons (moisture, CO2 — rules 3/4)
    only fire while occupied. Rule 5 closes the loop event-driven instead of
    with the blueprints' fixed timer. Every moisture rule additionally
    requires OUTSIDE air to be drier than inside — venting against a more
    humid outdoors would import moisture, so without a plausible gain the
    advice degrades silently (``no_data``/``no_gain``), never wrongly.

    N5 (v0.194.3) pairs the two absolute humidity limits with a relative
    companion, because a gram count means a different RH at every room
    temperature: the moisture ENTRY needs both (they are the same point at the
    20 °C reference, and each binds on its own side of it), the dryness VETO
    accepts either. ``rh_pct`` is the room's own relative humidity — the
    reading ``w_in_gm3`` was computed from, so at the seam the two always
    arrive together.

    Rule 3t (free-cooling, v0.188.0) is the thermal sibling for zones that
    can neither cool nor move air (``cool_capable``/``fan_capable`` false —
    the window is their only summer relief): room above the cool edge (on
    ``room_decide_c``, the temperature the comfort solver judges by) AND
    outside at least ``heat_out_dt_on_k`` cooler than the room AIR (``room_c``
    — a window exchanges air, see N5 at the rule) opens; the episode holds
    (``prev_heat_out``) until the edge shrinks below ``heat_out_dt_off_k`` or
    the room reaches the band, then ``cooled_off`` advises closing. The
    moisture guard vetoes muggy outside air (delta >= -humid_guard). NOT
    occupancy-gated by design: night purge is most valuable in an empty room.

    N2 (v0.192.0) adds the two halves of the mould guard. Guard 5 vetoes
    ``heat_out`` when the cooling edge is itself held up by an ENFORCED
    protection floor (``cool_edge_protected`` — such an edge is not a comfort
    target: airing down onto it works AGAINST the protection) or when the
    smoothed surface RH has come within ``mold_guard_margin_pp`` of the safe
    ceiling. The ``mold_guard`` rule is the active counterpart: an open window
    over an edge the FABRIC would need warmer, with the CURRENT surface RH
    already past the ceiling, advises closing — before rule 5a, which waits
    for the AIR to reach the floor and is therefore too late once the WALLS
    are over the limit. It deliberately does NOT require drier outside air:
    the risk driver is the surfaces cooling down, not imported vapour.

    ADR-0071 splits those two inputs, which were ONE input until then. While
    the mould floor was an inversion of the current reading, "a floor is
    enforced" and "the fabric needs it warmer than the cooling edge" were the
    same statement. The VTT dose model made the first one slow on purpose —
    it gates HEATING, and a fresh zone needs weeks of dose (or 48 h of acute
    wetness) before any floor is enforced. Advice is not an action: it costs
    nothing and must react at the speed of the risk, so ``mold_guard`` reads
    ``surface_needs_warmer`` — the psychrometric requirement, computed every
    tick regardless of the dose — while guard 5, which vetoes a REAL comfort
    decision, keeps reading the enforced floor.
    """
    # N4: the data gate is PER RULE, not global. Until v0.194.1 a missing
    # indoor or outdoor humidity returned ``no_data`` here and took the
    # building-protection rules with it — including rule 1b, whose own comment
    # says it deliberately needs no outdoor humidity, and rule 5a, which is
    # purely thermal. Gebäudeschutz is never gated (ADR-0050 separation), and
    # that has to include the data gate. The correction of the outdoor-humidity
    # source (N4.1) makes this load-bearing: ``w_out`` is now absent more
    # often, so a global gate would silence the mould advice exactly when the
    # outdoor sensor is the thing that failed.
    # The three derived values are spelled with explicit ``is not None`` tests
    # rather than through ``have_moisture``: a bool carries no narrowing, so
    # mypy --strict cannot see that the subtraction is safe. ``delta is not
    # None`` IS "both sides present", which is why the rules below lean on it.
    have_moisture = w_in_gm3 is not None and w_out_gm3 is not None
    delta = (
        w_in_gm3 - w_out_gm3 if w_in_gm3 is not None and w_out_gm3 is not None else None
    )
    outside_drier = delta is not None and delta > 0.0
    _d = round(delta, 1) if delta is not None else None
    # Rule 1 — mould cause (EWMA mean, never gated). Escalates to alert when
    # the floor is currently costing heat (binding) or can no longer protect
    # (capped). Requires drier outside air to be actionable at all.
    # N4, REJECTED after implementation: the 2026-09-13 review proposed moving
    # this limit onto the dynamic ``rh_max_safe`` of ADR-0071, as N3 did for
    # the mould GUARD. Built, and the N2 regression case caught it: the live
    # kitchen tick (mean 72 %, ceiling 69.6 %) then clears 69.6 - 5 and rule 1
    # advises OPEN — the exact defect N2 exists to remove.
    #
    # The reason is not an oversight, it is the variables. A LOW ``rh_max_safe``
    # means a COLD surface, and a cold surface argues for closing the window,
    # not for opening it. Tying the "open" advice to that ceiling makes it fire
    # earliest in precisely the situation where opening is harmful. The fixed
    # 80 % asks a different and, here, the right question: are the surfaces
    # ABSOLUTELY wet, regardless of what this wall could tolerate. The guard
    # below owns the relative question. Pinned by
    # ``test_n4_mold_risk_keeps_the_fixed_limit_on_purpose``.
    if (
        have_moisture
        and surface_rh_mean_pct is not None
        and surface_rh_mean_pct >= cfg.surface_limit_pct - cfg.surface_margin_pp
        and outside_drier
    ):
        level = "alert" if (mold_floor_binding or mold_capped) else "warn"
        return VentilationAdvice("open", "mold_risk", level, _d)
    # Rule 1b (N2) — mould GUARD: close the window before the fabric pays.
    # Below rule 1 (drier outside air plus an acute 48-h mean still argues for
    # airing) but above everything else, including the dryness veto, which
    # would only "discourage" where the building needs the window shut. Reads
    # the CURRENT surface RH, not the 48-h mean: the mean is deliberately slow
    # (mould CAUSE), while this is the acute state. Building protection ->
    # never occupancy-gated, and no drier-outside condition.
    # ADR-0071: ``surface_needs_warmer``, NOT the enforced floor — see the
    # docstring. The rule-1 precedence above is also what keeps the obvious
    # false positive out: a bathroom after a shower has an acute mean too, and
    # with drier air outside rule 1 says "open" before this rule is reached.
    # N6 (live finding, bedroom 2026-09-14): the rule STANDS DOWN while an
    # airing episode THIS advice itself asked for is still running. Its two
    # physical conditions say nothing about the window — they were already
    # true with it shut — so the only window-dependent term was the contact
    # itself, and since 1b outranks rule 3, the advice inverted on the
    # contact: open the window and the same second it said "close", close it
    # and it said "open". Not a missing hysteresis, a missing FEEDBACK:
    # nothing in the rule measured what the airing achieved.
    #
    # The first attempt keyed the stand-down on the DRYING GAIN — outside
    # drier by at least the moisture rule's entry threshold — and the
    # integration suite killed it within the hour: in winter cold outdoor air
    # is always absolutely drier (23 °C/60 % against 6 °C/85 % is 6.2 g/m³ of
    # gain, more than the bedroom's 3.7), so that version disabled the mould
    # guard for the whole heating season, which is exactly when it is needed.
    # The gain does not separate the two cases. What separates them is WHOSE
    # instruction is being carried out: Poise had told the bedroom to open,
    # and then contradicted itself the second the window moved. So the rule
    # is the narrow one — do not reverse your own open-advice while it still
    # stands. The moisture rule's own exit hysteresis (``delta_off_gm3``) ends
    # the episode; ``target_reached`` closes the window; and the tick AFTER
    # that the guard is free again and speaks if the walls are still wet.
    # Nothing else changes: a window opened without Poise asking for it, or
    # one still open after the episode ended, meets the guard as before.
    #
    # An ENFORCED protection floor overrides the stand-down: once a floor is
    # actually holding the cooling edge up, the fabric is already paying and
    # the advice stays "close" whatever the episode says.
    #
    # N6b: "an episode is running" is not enough — it must still be VALID.
    # The predicate of rule 3 is therefore computed ONCE, here, and consumed
    # in both places; rebuilding it in two spots is how the first draft came
    # to stand down on ``delta >= delta_on`` while the rule it was protecting
    # held on down to ``delta_off``. With one predicate the stand-down starts
    # and ends exactly with the reason it defers to — including the indoor
    # humidity lines, so a room that has dried below them stops being a
    # reason to keep the window open even while the outside air is still
    # much drier.
    threshold = cfg.delta_off_gm3 if prev_advice_active else cfg.delta_on_gm3
    moisture_reason_valid = (
        occupied
        and delta is not None
        and delta >= threshold
        # N5: AND, not OR — the two halves are the same line seen from two
        # sides, and each is the binding one on its side of the 20 °C
        # reference. Without the relative half a 28 °C room at 33 % RH carries
        # 9 g/m³, clears the absolute 8.7 and gets told to air out a room that
        # is objectively DRY; the dryness veto cannot catch it either, because
        # its own limit (7 g/m³ = 25.8 % RH at 28 °C) is absolute too. Without
        # the absolute half an 18 °C room at 52 % RH (8.0 g/m³) would be told
        # to vent air that carries less water than the reference climate.
        and w_in_gm3 is not None
        and w_in_gm3 > cfg.moist_gm3
        and rh_pct is not None
        and rh_pct >= cfg.moist_rh_pct
    )
    # N7 (2026-09-14) — the SECOND entry into the same moisture episode, and
    # the one the bathroom needed: moisture removal is building protection,
    # not comfort, once the room carries more vapour than its own fabric
    # tolerates. Ungated by occupancy, for the reason N1 already gave for
    # free-cooling — a bathroom is at its wettest exactly when nobody is left
    # standing in it, and a presence model is least certain precisely then.
    #
    # The limit is ``rh_max_safe``: the room-air RH at which the modelled
    # surface sits on its critical line. It is the SAME limit rule 1b reads —
    # since N7.1 in the same coordinate — so the two can never disagree about
    # whether the fabric is over its line, only about what to do while the
    # window is open, and there the stand-down below decides.
    #
    # Own hysteresis on the own reason, not on the global ``prev_advice_active``
    # anchor: entry at ``delta_on``, hold at ``delta_off``. That is the
    # cause-specific shape the rest of the axis is meant to grow into.
    protect_threshold = cfg.delta_off_gm3 if prev_moisture_protect else cfg.delta_on_gm3
    protect_reason_valid = (
        rh_pct is not None
        and rh_max_safe_pct is not None
        and rh_pct > rh_max_safe_pct
        and delta is not None
        and delta >= protect_threshold
        # An ENFORCED floor means the fabric is already being paid for with
        # heat; airing then works against the protection rather than for it.
        and not cool_edge_protected
    )
    own_airing_running = (
        prev_moisture_airing and moisture_reason_valid and not cool_edge_protected
    ) or (prev_moisture_protect and protect_reason_valid)
    if (
        window_open
        and not own_airing_running
        and surface_needs_warmer
        and rh_pct is not None
        and rh_max_safe_pct is not None
        # N7.1 (external review 2026-09-14): the canonical comparison. Until
        # v0.194.4 this read ``surface_rh_pct > rh_max_safe_pct`` — a SURFACE
        # relative humidity against a ROOM-air ceiling. Both are "% RH", but at
        # different reference temperatures, so they are two coordinates of the
        # same vapour load and not comparable; the quotient
        # ``p_sat(T_room)/p_sat(T_si)`` ran at 1.20-1.27 in the field, i.e. the
        # rule fired from roughly ``rh_max_safe / 1.2`` upwards. Measured on
        # three real ticks it fired in all three, while the canonical limit was
        # exceeded in only one: bathroom +6.2 pp, bedroom -0.8 pp, the 2026-08-19
        # kitchen -2.6 pp. The two field cases N2 and N6 were built on were
        # therefore NOT over the mould line.
        #
        # ``rh_max_safe_pct`` IS the safe ROOM-air RH, so the like-for-like form
        # is the room's own ``rh_pct`` — no new value, no new parameter (N5 put
        # ``rh_pct`` in this signature). ``surface_rh_pct > critical_rh`` would
        # be equivalent but would have to carry ``critical_rh`` in first;
        # ``w_in > abs_max_safe`` is the same limit again in absolute
        # coordinates. One limit, three coordinate systems.
        #
        # ``surface_rh_pct`` stays in the signature: it is what the CARD shows
        # and what makes the severity legible, and the guard's other half
        # (``surface_needs_warmer``) is a temperature comparison, untouched.
        and rh_pct > rh_max_safe_pct
    ):
        # N4: reachable without any humidity data now — which is what its own
        # comment above always claimed. N6 does not change that: without the
        # outdoor humidity no moisture rule can have advised opening, so no
        # episode is running and the rule still speaks.
        return VentilationAdvice("close", "mold_guard", "warn", _d)
    # Rule 2 — dryness veto (never gated): venting a dry room against drier
    # outside air over-dries it further.
    # N4: with the window ALREADY open, "better not open" is the wrong verb —
    # the actionable advice is to close it. Same rule, same precedence, same
    # reason token; only the action follows the window state, exactly as rules
    # 1b/5a do.
    # N5: OR, not AND. The absolute gram count and the relative reading are two
    # different ways for a room to be too dry, and each catches what the other
    # misses — 7 g/m³ is the physiological floor for a 20 °C room, while a warm
    # room can sit at 10 g/m³ and still be parched (26 °C/35 % = 8.5 g/m³ is
    # ABOVE the absolute floor). Either one is enough to stop drying it further.
    too_dry = (w_in_gm3 is not None and w_in_gm3 <= cfg.dry_warn_gm3) or (
        rh_pct is not None and rh_pct <= cfg.dry_warn_rh_pct
    )
    if too_dry and outside_drier:
        return VentilationAdvice(
            "close" if window_open else "discourage", "too_dry", "warn", _d
        )
    # Rule 5a — thermal floor (never gated, BEFORE the comfort rules): the
    # room heating against the open window at the mould/frost floor must win
    # over any comfort reason to keep venting.
    if window_open and room_at_thermal_floor:
        return VentilationAdvice("close", "thermal_floor", "warn", _d)
    # Rule 2b (N7) — moisture removal as BUILDING PROTECTION, never gated.
    # Predicate computed above rule 1b, because the guard's stand-down defers
    # to it. Placed HERE, below the guard and below the thermal floor, and
    # deliberately not above them:
    #
    #   * below 1b, because an open window over a room that is over its line
    #     is the N2 situation, and letting this rule outrank the guard would
    #     re-open exactly the conflict N6 closed. The way to keep a window
    #     open is the stand-down — this rule's OWN running episode — not a
    #     higher precedence. The 2026-09-13 glue scenario proves the point:
    #     23 °C/60 % against a 58.4 % ceiling is over the line too, and a
    #     rule 2b above the guard would turn that close back into an open.
    #   * below 5a, because a room whose AIR has reached the protection floor
    #     is being cooled below it by further airing.
    #
    # What it does change is the case the guard can never reach: a CLOSED
    # window. The bathroom of 2026-09-14 — 69.5 % against a 63.3 % ceiling,
    # 5.1 g/m³ to gain, empty for seven hours — had every moisture condition
    # met and was silent only because rule 3 is occupancy-gated.
    if protect_reason_valid:
        return VentilationAdvice("open", "moisture_protect", "warn", _d)
    # Rule 2b-close (N7) — the episode this axis started must end explicitly.
    # Without it a protection airing that reaches its goal while the outside
    # air is still much drier falls through to ``no_gain`` and leaves the
    # window open with an ``idle`` advice: rule 5b only closes on a spent
    # DELTA, and the delta is not what ended this episode. ``target_reached``
    # is the honest token — the cause is gone, event-driven, exactly what it
    # has always meant.
    if window_open and prev_moisture_protect and not moisture_reason_valid:
        return VentilationAdvice("close", "target_reached", "ok", _d)
    # Rule 3t — free-cooling (heat_out): capability-gated (window-only zones),
    # asymmetric dT hysteresis, muggy-outside veto. Not occupancy-gated.
    free_cool_zone = not cool_capable and not fan_capable
    # N5: rule 3t asks TWO physically different questions, and until v0.194.2
    # both read the same ``room_c``:
    #   1. "is the room above the comfort edge?" — that edge is the comfort
    #      solver's, decided on ``room_decide`` (operative temperature when the
    #      MRT model is on), and every other consumer of ``eff_cool`` in the
    #      composition compares it against exactly that. Rule 3t compared it
    #      against the AIR temperature, so with warm surfaces the solver could
    #      say "too warm" (operative 26.0 over a 25.0 edge) while 3t saw no
    #      cooling need at all (air 24.5 under 25.0).
    #   2. "does opening the window help?" — that one is air against air. The
    #      exchange through a window is an air exchange; feeding the operative
    #      temperature into the dT hysteresis would credit the outside with the
    #      whole MRT excess (1.5 K in the example above — most of the 2.0 K
    #      entry threshold) and open against too little real gain.
    # Hence two inputs. ``room_decide_c`` defaults to ``room_c``, so a caller
    # that has only one temperature behaves exactly as before.
    room_edge_c = room_decide_c if room_decide_c is not None else room_c
    # Guard 5 (N2): never advise cooling toward an edge that a protection floor
    # holds up, and stop one margin short of the mould-safe ceiling.
    surface_near_limit = (
        surface_rh_mean_pct is not None
        and rh_max_safe_pct is not None
        and surface_rh_mean_pct >= rh_max_safe_pct - cfg.mold_guard_margin_pp
    )
    if (
        # N4: no outdoor humidity -> the muggy-air veto cannot be evaluated,
        # and free-cooling is a comfort decision: without the veto it stays
        # silent rather than guessing. ``delta is not None`` says exactly that
        # (both sides present) and narrows for the veto clause below.
        delta is not None
        and free_cool_zone
        and not cool_edge_protected
        and not surface_near_limit
        and room_c is not None
        and room_edge_c is not None
        and cool_edge_c is not None
        and t_out_c is not None
        and room_edge_c > cool_edge_c
        and t_out_c
        <= room_c - (cfg.heat_out_dt_off_k if prev_heat_out else cfg.heat_out_dt_on_k)
        and delta >= -cfg.heat_out_humid_guard_gm3
    ):
        return VentilationAdvice("open", "heat_out", "ok", _d)
    # Rules 3/4 — comfort, occupancy-gated. Asymmetric hysteresis on delta.
    # The predicate itself is ``moisture_reason_valid``, computed above rule 1b
    # because the mould guard's stand-down defers to exactly this reason (N6b).
    if moisture_reason_valid:
        return VentilationAdvice("open", "moisture_out", "ok", _d)
    # N4: CO2 needs no humidity at all — one of the rules the global gate used
    # to swallow. Still inert until the ADR-0049 backend lands.
    if occupied and co2_ppm is not None and co2_ppm >= cfg.co2_ppm:
        return VentilationAdvice("open", "co2", "ok", _d)
    # Rule 3t close — the free-cooling episode ends (edge gone, room in band,
    # or outside turned muggy) while the window is still open. AFTER rules
    # 3/4 on purpose: a still-valid moisture/CO2 reason keeps the window open.
    if window_open and prev_heat_out:
        return VentilationAdvice("close", "cooled_off", "ok", _d)
    # Rule 5b — close: the cause is gone (event-driven, not a timer).
    if window_open and delta is not None and delta < cfg.delta_off_gm3:
        return VentilationAdvice("close", "target_reached", "ok", _d)
    # N4: ``no_data`` survives as the honest token for "the moisture axis had
    # nothing to say"; ``no_gain`` still means "it had, and the answer is no".
    return VentilationAdvice(
        "idle", "no_gain" if have_moisture else "no_data", "ok", _d
    )


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
