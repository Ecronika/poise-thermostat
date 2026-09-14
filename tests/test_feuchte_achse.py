"""ADR-0066 humidity axis (pure): absolute humidity, safe-RH ceiling, advice."""

from __future__ import annotations

from pathlib import Path

from custom_components.poise.comfort.mold import (
    max_safe_rh,
    surface_relative_humidity,
)
from custom_components.poise.comfort.ventilation import (
    AdviceEmission,
    VentilationAdvice,
    advice_transition,
    ewma_step,
    ventilation_advise,
)
from custom_components.poise.estimation.psychrometrics import (
    absolute_humidity,
    humidity_ratio,
)

# --- Feature A: absolute humidity reference points ---------------------------


def test_absolute_humidity_reference_points() -> None:
    # design A.3 anchor: 20 °C / 40 % RH ~ 7 g/m^3 (rounded in the design;
    # Magnus/Alduchov-Eskridge gives 6.90)
    assert abs(absolute_humidity(20.0, 40.0) - 6.9) < 0.05
    # 20 °C / 29 % ~ 5.0 g/m^3 (the alert floor)
    assert abs(absolute_humidity(20.0, 29.0) - 5.0) < 0.1
    # temperature-drift correction: same 40 % RH is drier air at 18 °C
    assert absolute_humidity(18.0, 40.0) < absolute_humidity(20.0, 40.0)


def test_unit_cross_reference_gm3_vs_gkg() -> None:
    # 20 °C/40 %: ~6.9 g/m^3 corresponds to ~5.8 g/kg (design §10 anchor)
    assert abs(humidity_ratio(20.0, 40.0) - 5.78) < 0.05
    # both scale together with RH at fixed temperature
    assert absolute_humidity(20.0, 60.0) > absolute_humidity(20.0, 40.0)


def test_absolute_humidity_monotone_in_rh() -> None:
    vals = [absolute_humidity(21.0, rh) for rh in (20, 35, 50, 65, 80, 95)]
    assert vals == sorted(vals)


# --- Feature C: mould-safe RH ceiling ---------------------------------------


def test_max_safe_rh_design_table_20c() -> None:
    # design C.1 table (20 °C room, f_Rsi 0.7): +5 -> ~60 %, -10 -> ~45 %,
    # -20 -> ~37 % (the number a foreign humidifier lacks)
    assert abs(max_safe_rh(20.0, 5.0) - 60.0) < 2.0
    assert abs(max_safe_rh(20.0, -10.0) - 45.0) < 2.0
    assert abs(max_safe_rh(20.0, -20.0) - 37.0) < 2.0
    # new-build envelope (f_Rsi 0.9): the conflict vanishes
    assert max_safe_rh(20.0, -20.0, f_rsi=0.9) > 60.0


def test_max_safe_rh_round_trip_inverts_the_surface_criterion() -> None:
    # inverse consistency (design §10). ADR-0071 retired
    # ``mold_min_air_temperature``, so the round trip is stated against the
    # criterion itself instead of against the retired inversion: the ceiling
    # returned for an air temperature must put the SURFACE exactly on the
    # limit it was solved for.
    t_air, t_out = 20.0, -5.0
    rh_max = max_safe_rh(t_air, t_out, limit=0.80)
    assert abs(surface_relative_humidity(t_air, rh_max, t_out) - 0.80) < 1e-9


def test_fabric_conflict_case_exists() -> None:
    # design C.3: at -20 °C outdoors the safe ceiling in g/m^3 undercuts the
    # 7 g/m^3 dryness floor -> a fabric problem, not a control problem.
    rh_max = max_safe_rh(20.0, -20.0)
    assert absolute_humidity(20.0, rh_max) < 7.0


# --- Feature B: ventilation advice ------------------------------------------


def _advise(**kw: object) -> VentilationAdvice:
    base: dict[str, object] = {
        "w_in_gm3": 10.0,
        "w_out_gm3": 5.0,
        # N5: the room's own RH, which the humidity limits are now paired
        # with. 60 % is what 10.0 g/m³ means at ~21 °C, so the base case is
        # physically consistent and sits clear of BOTH new lines (>= 50 for
        # the moisture entry, <= 35 for the dryness veto) — every existing
        # case keeps testing what it tested. The N5 cases below vary it.
        "rh_pct": 60.0,
        "surface_rh_mean_pct": None,
        "mold_floor_binding": False,
        "mold_capped": False,
        "room_at_thermal_floor": False,
        "co2_ppm": None,
        "window_open": False,
        "occupied": True,
        "prev_advice_active": False,
    }
    base.update(kw)
    return ventilation_advise(**base)  # type: ignore[arg-type]


def test_no_outdoor_source_is_silent() -> None:
    assert _advise(w_out_gm3=None).reason == "no_data"
    assert _advise(w_in_gm3=None).action == "idle"


def test_rule1_mold_mean_triggers_ungated_and_escalates() -> None:
    a = _advise(surface_rh_mean_pct=76.0, occupied=False)
    assert (a.action, a.reason, a.level) == ("open", "mold_risk", "warn")
    b = _advise(surface_rh_mean_pct=76.0, mold_floor_binding=True)
    assert b.level == "alert"
    c = _advise(surface_rh_mean_pct=76.0, mold_capped=True)
    assert c.level == "alert"


def test_rule2_dry_veto_ungated_and_excludes_mold() -> None:
    a = _advise(w_in_gm3=6.0, w_out_gm3=3.0, occupied=False)
    assert (a.action, a.reason) == ("discourage", "too_dry")
    # invariant (design §10): mold_risk and too_dry are mutually exclusive —
    # a room dry enough for the veto cannot carry a wet-wall mean that the
    # same moisture level could sustain; encode via precedence at boundary.
    b = _advise(w_in_gm3=6.0, w_out_gm3=3.0, surface_rh_mean_pct=76.0)
    assert b.reason in ("mold_risk", "too_dry")  # exactly one wins, never both


def test_rule3_moisture_comfort_is_occupancy_gated() -> None:
    a = _advise(w_in_gm3=10.0, w_out_gm3=6.0)  # delta 4.0 >= 3.0, moist room
    assert (a.action, a.reason) == ("open", "moisture_out")
    assert _advise(w_in_gm3=10.0, w_out_gm3=6.0, occupied=False).action == "idle"
    # not above the moisture band -> no comfort advice despite the delta
    assert _advise(w_in_gm3=8.0, w_out_gm3=4.0).action == "idle"


def test_rule3_hysteresis_latch_asymmetric() -> None:
    # delta 2.0 is below the 3.0 entry but above the 1.5 exit
    fresh = _advise(w_in_gm3=10.0, w_out_gm3=8.0)
    assert fresh.action == "idle"
    held = _advise(w_in_gm3=10.0, w_out_gm3=8.0, prev_advice_active=True)
    assert held.action == "open" and held.advice_active


def test_rule4_co2_gated_on_occupancy() -> None:
    a = _advise(w_in_gm3=8.0, w_out_gm3=6.0, co2_ppm=1200.0)
    assert (a.action, a.reason) == ("open", "co2")
    assert (
        _advise(w_in_gm3=8.0, w_out_gm3=6.0, co2_ppm=1200.0, occupied=False).action
        == "idle"
    )


def test_rule5_close_on_cause_gone_or_thermal_floor() -> None:
    a = _advise(w_in_gm3=8.0, w_out_gm3=7.2, window_open=True)  # delta < 1.5
    assert (a.action, a.reason) == ("close", "target_reached")
    b = _advise(
        w_in_gm3=10.0, w_out_gm3=6.0, window_open=True, room_at_thermal_floor=True
    )
    assert (b.action, b.reason) == ("close", "thermal_floor")
    # cause still present + window open -> keep advising open, not close
    c = _advise(w_in_gm3=10.0, w_out_gm3=6.0, window_open=True)
    assert c.action == "open"


def test_venting_against_more_humid_outside_never_advised() -> None:
    # outside wetter than inside: no mold/moisture advice can fire
    a = _advise(w_in_gm3=8.0, w_out_gm3=12.0, surface_rh_mean_pct=80.0)
    assert a.action in ("idle", "close")


# --- surface-RH EWMA fold (design §12.1c) -----------------------------------


def test_ewma_shower_spike_barely_moves_48h_mean() -> None:
    mean = 55.0
    # one 5-minute 95 % burst against tau = 48 h
    after = ewma_step(mean, 95.0, dt_min=5.0, tau_min=2880.0)
    assert after - mean < 0.1


def test_ewma_persistent_wet_wall_crosses_and_recovers() -> None:
    mean: float | None = 60.0
    for _ in range(3 * 24 * 12):  # 3 days of 5-min ticks at 85 %
        mean = ewma_step(mean, 85.0, dt_min=5.0, tau_min=2880.0)
    assert mean is not None and mean >= 75.0  # rule-1 line (80 - 5 margin)
    for _ in range(3 * 24 * 12):  # after airing: dry surface again
        mean = ewma_step(mean, 55.0, dt_min=5.0, tau_min=2880.0)
    assert mean < 75.0  # the retraction is a state change, not a timer


def test_ewma_seeds_and_ignores_bad_dt() -> None:
    assert ewma_step(None, 70.0, dt_min=5.0, tau_min=2880.0) == 70.0
    assert ewma_step(60.0, 90.0, dt_min=0.0, tau_min=2880.0) == 60.0


# --- B.5 emission edge (ADR-0066): event on change, notify on open episode --


def test_advice_transition_edges() -> None:
    # steady state: nothing
    assert advice_transition("idle", "idle", notify_opt_in=True) == (
        advice_transition("open", "open", notify_opt_in=True)
    )
    assert not advice_transition("idle", "idle", notify_opt_in=True).fire_event
    # any change fires the bus event, notification only on the open episode
    em = advice_transition("idle", "open", notify_opt_in=True)
    assert em.fire_event and em.notify_create and not em.notify_dismiss
    em = advice_transition("open", "close", notify_opt_in=True)
    assert em.fire_event and em.notify_dismiss and not em.notify_create
    em = advice_transition("close", "idle", notify_opt_in=True)
    assert em.fire_event and not em.notify_create and not em.notify_dismiss
    # opt-out: event still fires, notifications never
    em = advice_transition("idle", "open", notify_opt_in=False)
    assert em.fire_event and not em.notify_create
    em = advice_transition("open", "idle", notify_opt_in=False)
    assert em.fire_event and not em.notify_dismiss


def test_advice_transition_cold_start() -> None:
    # settling into idle after a fresh start announces nothing ...
    em = advice_transition("", "idle", notify_opt_in=True)
    assert not (em.fire_event or em.notify_create or em.notify_dismiss)
    # ... but waking INTO an open episode re-announces (restart mid-episode)
    em = advice_transition("", "open", notify_opt_in=True)
    assert em.fire_event and em.notify_create and not em.notify_dismiss
    em = advice_transition("", "discourage", notify_opt_in=True)
    assert em.fire_event and not em.notify_create


# --- guard: advice never reaches the control path (ADR-0048, design §10) ----


# --- rule 3t: free-cooling advice (v0.188.0) --------------------------------


def _free_cool(**kw: object) -> VentilationAdvice:
    """Rule-3t base: window-only zone, room 26 over a 24.5 edge, 21 outside,
    equal absolute humidity (delta 0) so no moisture rule interferes."""
    base: dict[str, object] = {
        "w_in_gm3": 10.0,
        "w_out_gm3": 10.0,
        "room_c": 26.0,
        "cool_edge_c": 24.5,
        "t_out_c": 21.0,
        "cool_capable": False,
        "fan_capable": False,
        "occupied": False,
    }
    base.update(kw)
    return _advise(**base)


def test_rule3t_free_cooling_opens_for_window_only_zone() -> None:
    a = _free_cool()
    assert (a.action, a.reason, a.level) == ("open", "heat_out", "ok")
    # NOT occupancy-gated: night purge is most valuable in an empty room.
    assert _free_cool(occupied=True).reason == "heat_out"


def test_rule3t_capability_gate_blocks_cool_or_fan_zones() -> None:
    assert _free_cool(cool_capable=True).reason == "no_gain"
    assert _free_cool(fan_capable=True).reason == "no_gain"


def test_rule3t_needs_room_over_edge_and_cooler_outside() -> None:
    # room inside the band -> no advice
    assert _free_cool(room_c=24.0).reason == "no_gain"
    # outside only 1 K cooler -> below the 2 K entry threshold
    assert _free_cool(t_out_c=25.5).reason == "no_gain"
    # ... but an ACTIVE episode holds down to the 1 K exit edge (hysteresis)
    held = _free_cool(t_out_c=24.9, prev_heat_out=True, window_open=True)
    assert held.reason == "heat_out"
    # below the exit edge the open episode ends with a close advice
    done = _free_cool(t_out_c=25.7, prev_heat_out=True, window_open=True)
    assert (done.action, done.reason) == ("close", "cooled_off")


def test_rule3t_muggy_outside_vetoes_free_cooling() -> None:
    # outside 2 g/m3 MORE humid than inside -> never trade heat for mugginess
    a = _free_cool(w_in_gm3=10.0, w_out_gm3=12.0)
    assert a.reason == "no_gain"
    # 1 g/m3 more humid is within the guard -> still advised
    assert _free_cool(w_in_gm3=10.0, w_out_gm3=11.0).reason == "heat_out"


def test_rule3t_precedence_yields_to_mold_dry_and_thermal_floor() -> None:
    # mould (rule 1) outranks free-cooling
    a = _free_cool(w_out_gm3=5.0, surface_rh_mean_pct=76.0)
    assert a.reason == "mold_risk"
    # a still-valid moisture reason keeps the window open over cooled_off
    keep = _free_cool(
        w_in_gm3=12.0,
        w_out_gm3=5.0,
        t_out_c=25.7,
        prev_heat_out=True,
        window_open=True,
        occupied=True,
    )
    assert (keep.action, keep.reason) == ("open", "moisture_out")


# --- N2: protection-floor guard + the mold_guard close advice ---------------


def _bound_edge(**kw: object) -> VentilationAdvice:
    """The live case (kitchen, 2026-08-19), which rule 3t got wrong.

    Window open, outside 17.1 °C, the mould floor 22.1 °C holds BOTH the
    setpoint and the effective cooling edge (the published band collapsed onto
    a point), surface RH 77 % over a 69.6 % safe ceiling, outside absolutely
    DRIER (12.2 vs 13.8 g/m³) — so the risk driver is the surfaces cooling
    down behind the open window, not imported vapour.
    """
    base: dict[str, object] = {
        "w_in_gm3": 13.8,
        "w_out_gm3": 12.2,
        "room_c": 23.0,
        "cool_edge_c": 22.1,
        "t_out_c": 17.1,
        "cool_capable": False,
        "fan_capable": False,
        "occupied": False,
        "window_open": True,
        "cool_edge_protected": True,
        "surface_needs_warmer": True,
        "surface_rh_pct": 77.0,
        "rh_max_safe_pct": 69.6,
        "surface_rh_mean_pct": 72.0,
    }
    base.update(kw)
    return _advise(**base)


def test_the_defect_reproduces_without_the_new_guards() -> None:
    """Non-vacuity: with both guard inputs absent the OLD advice comes back —
    3t reads the protection-bound edge as a comfort target and advises airing
    the room down onto the mould floor."""
    old = _bound_edge(
        cool_edge_protected=False,
        surface_needs_warmer=False,
        surface_rh_mean_pct=None,
        rh_max_safe_pct=None,
    )
    assert (old.action, old.reason) == ("open", "heat_out")


def test_guard5_bound_cooling_edge_blocks_free_cooling() -> None:
    # the edge alone (no surface data at all) is enough to veto heat_out
    a = _free_cool(cool_edge_protected=True)
    assert a.reason == "no_gain"
    # ... and the veto is the ONLY reason it is gone
    assert _free_cool().reason == "heat_out"


def test_guard5_surface_rh_margin_blocks_free_cooling() -> None:
    # smoothed surface RH within 2 pp of the safe ceiling -> no free cooling
    near = _free_cool(surface_rh_mean_pct=68.0, rh_max_safe_pct=69.6)
    assert near.reason == "no_gain"
    # 2.6 pp below the ceiling is outside the margin -> unchanged advice
    clear = _free_cool(surface_rh_mean_pct=67.0, rh_max_safe_pct=69.6)
    assert clear.reason == "heat_out"


def test_mold_guard_advises_closing_before_the_air_floor_is_reached() -> None:
    a = _bound_edge()
    assert (a.action, a.reason, a.level) == ("close", "mold_guard", "warn")
    # building protection: NOT occupancy-gated, and no drier-outside condition
    assert _bound_edge(occupied=True).reason == "mold_guard"
    assert _bound_edge(w_out_gm3=15.0).reason == "mold_guard"


def test_mold_guard_needs_open_window_bound_edge_and_unsafe_surface() -> None:
    # closed window: nothing to close
    assert _bound_edge(window_open=False).reason != "mold_guard"
    # the fabric does NOT need it warmer than the edge: an ordinary cool edge
    # is a legitimate target
    assert _bound_edge(surface_needs_warmer=False).reason != "mold_guard"
    # surface still below the safe ceiling: no acute risk yet
    assert _bound_edge(surface_rh_pct=69.0).reason == "no_gain"
    # no ceiling published (no outdoor temperature) -> silent, never guessed
    assert _bound_edge(rh_max_safe_pct=None).reason == "no_gain"


def test_mold_guard_reads_the_requirement_not_the_enforced_floor() -> None:
    """ADR-0071: the guard must fire on a zone whose dose has NOT engaged.

    This is the whole point of the split. The VTT model needs weeks of dose
    (or 48 h of acute wetness) before a floor is enforced, so a guard tied to
    ``cool_edge_protected`` would stay silent through the entire ramp-up of
    every new installation — while the walls are already over the safe line.
    Advice costs nothing; it reacts to the risk, not to the dose.
    """
    fresh = _bound_edge(cool_edge_protected=False, surface_needs_warmer=True)
    assert (fresh.action, fresh.reason) == ("close", "mold_guard")
    # ... and the converse: guard 5 still reads the ENFORCED floor, so a bare
    # requirement does not veto free cooling on its own.
    assert _free_cool(surface_needs_warmer=True).reason == "heat_out"


def test_mold_guard_precedence_below_rule1_and_above_the_rest() -> None:
    # rule 1 wins: drier outside + an acute 48-h mean means airing still helps
    assert _bound_edge(surface_rh_mean_pct=76.0).reason == "mold_risk"
    # ... over the dryness veto (rule 2)
    assert _bound_edge(w_in_gm3=6.0, w_out_gm3=3.0).reason == "mold_guard"
    # ... over the thermal floor (rule 5a), which only fires once the AIR
    # reaches the floor — too late when the WALLS are already over the limit
    assert _bound_edge(room_at_thermal_floor=True).reason == "mold_guard"
    # ... and over the comfort rules
    assert _bound_edge(occupied=True, w_out_gm3=5.0).reason == "mold_guard"


def test_advice_transition_tracks_the_mold_guard_episode() -> None:
    # entering the guard: event + the opt-in notification
    em = advice_transition(
        "idle", "close", notify_opt_in=True, prev_reason="", reason="mold_guard"
    )
    assert (em.fire_event, em.notify_create, em.notify_dismiss) == (True, True, False)
    # a harmless close ESCALATING into the guard is an edge although the
    # ACTION token does not move
    em = advice_transition(
        "close",
        "close",
        notify_opt_in=True,
        prev_reason="target_reached",
        reason="mold_guard",
    )
    assert (em.fire_event, em.notify_create) == (True, True)
    # ... and leaving it clears the notification again
    em = advice_transition(
        "close",
        "close",
        notify_opt_in=True,
        prev_reason="mold_guard",
        reason="target_reached",
    )
    assert (em.fire_event, em.notify_dismiss) == (True, True)
    # harmless close reasons among themselves stay silent (no event storm)
    em = advice_transition(
        "close",
        "close",
        notify_opt_in=True,
        prev_reason="target_reached",
        reason="cooled_off",
    )
    assert not em.fire_event
    # without the new arguments the edge is bit-identical to before
    assert advice_transition("idle", "open", notify_opt_in=True) == AdviceEmission(
        True, True, False
    )


def test_ventilation_verdict_never_enters_the_control_path() -> None:
    pkg = Path(__file__).resolve().parents[1] / "custom_components" / "poise"
    for rel in (
        "comfort/humidity.py",
        "comfort/dual_setpoint.py",
        "constraints.py",
        "control/tick_resolve.py",
        "arbitration.py",
    ):
        src = (pkg / rel).read_text(encoding="utf-8")
        assert "ventilation_advise" not in src, f"{rel} must not consume the advice"
        assert "VentilationAdvice" not in src, f"{rel} must not consume the advice"


# --- N4 (v0.194.2): the four corrections of the 2026-09-13 review -------------


def _n4_advise(**over: object) -> VentilationAdvice:
    """A neutral tick: moist-ish room, drier outside, nothing else in play.

    Named apart from ``_advise`` above on purpose, and renamed in N5 after it
    bit: written as a second ``_advise`` in N4, this definition SHADOWED the
    module's own helper, so every earlier test in this file silently ran
    against these defaults instead of theirs. It stayed invisible only because
    both bases agreed wherever it mattered — until N5 added a key to one of
    them and four unrelated tests failed. Two helpers, two names.
    """
    base: dict[str, object] = dict(
        w_in_gm3=10.0,
        w_out_gm3=9.0,
        # N5: see the note on the other helper — 60 % RH for ~10 g/m³, clear
        # of both new lines so these cases keep testing what they test.
        rh_pct=60.0,
        surface_rh_mean_pct=None,
        mold_floor_binding=False,
        mold_capped=False,
        room_at_thermal_floor=False,
        co2_ppm=None,
        window_open=False,
        occupied=True,
        prev_advice_active=False,
    )
    base.update(over)
    return ventilation_advise(**base)  # type: ignore[arg-type]


def test_n4_building_protection_survives_a_missing_outdoor_humidity() -> None:
    """The global ``no_data`` gate swallowed rules that never needed the data.

    ``mold_guard``'s own comment says it deliberately requires no drier outside
    air — and until v0.194.1 a missing ``w_out`` returned ``no_data`` three
    lines above it. The same held for ``thermal_floor``, which is purely
    thermal. That matters more after N4.1, because the outdoor humidity is now
    absent whenever the outdoor TEMPERATURE is: a global gate would have
    silenced the mould advice exactly when a sensor failed.
    """
    guard = _n4_advise(
        w_out_gm3=None,
        window_open=True,
        surface_rh_pct=82.0,
        rh_max_safe_pct=58.0,
        surface_needs_warmer=True,
    )
    assert (guard.action, guard.reason) == ("close", "mold_guard")
    assert guard.delta_gm3 is None  # no number is published without the data

    floor = _n4_advise(
        w_in_gm3=None, w_out_gm3=None, window_open=True, room_at_thermal_floor=True
    )
    assert (floor.action, floor.reason) == ("close", "thermal_floor")

    # ...and the honest token survives for the case that really has nothing.
    assert _n4_advise(w_in_gm3=None, w_out_gm3=None).reason == "no_data"


def test_n4_moisture_rules_stay_silent_without_both_sides() -> None:
    """The other half of the same change: a rule that NEEDS the comparison
    must not fire on half of it. Free-cooling included — its muggy-air veto is
    unevaluable without the outdoor value, and it is a comfort decision."""
    assert _n4_advise(w_out_gm3=None, w_in_gm3=12.0).reason == "no_data"
    cool = _n4_advise(
        w_out_gm3=None,
        room_c=26.0,
        cool_edge_c=24.0,
        t_out_c=20.0,
    )
    assert cool.reason != "heat_out"


def test_n4_too_dry_closes_an_open_window_instead_of_discouraging_it() -> None:
    """Same rule, same precedence, same token — only the verb follows the
    window state, as rules 1b and 5a already do. "Better not open" is not
    actionable advice for a window that is already open."""
    assert _n4_advise(w_in_gm3=6.0, w_out_gm3=4.0, window_open=True).action == "close"
    assert _n4_advise(w_in_gm3=6.0, w_out_gm3=4.0).action == "discourage"
    # the reason token is unchanged, so the card text and the event keep working
    assert _n4_advise(w_in_gm3=6.0, w_out_gm3=4.0, window_open=True).reason == "too_dry"


def test_n4_mold_risk_keeps_the_fixed_limit_on_purpose() -> None:
    """The one review proposal that was built and then REJECTED.

    Moving rule 1 onto ADR-0071's dynamic ``rh_max_safe`` looks like the
    obvious consistency fix — N3 did exactly that for the mould guard. It is
    the wrong direction here, and the N2 regression case says why: a LOW safe
    ceiling means a COLD surface, and a cold surface argues for closing the
    window. Tying the "open" advice to that ceiling makes it fire earliest
    where opening does the most harm.

    The live kitchen case is the proof: smoothed mean 72 %, ceiling 69.6 %.
    Against the fixed 80 % - 5 pp rule 1 stays silent and ``mold_guard`` gets
    to say "close"; against 69.6 - 5 pp it would say "open" instead.
    """
    kitchen = _bound_edge()
    assert (kitchen.action, kitchen.reason) == ("close", "mold_guard")
    # the dynamic ceiling is present in that very call — and deliberately not
    # what rule 1 reads.
    assert (
        _n4_advise(surface_rh_mean_pct=72.0, rh_max_safe_pct=69.6).reason != "mold_risk"
    )
    # the fixed limit still fires where it should: absolutely wet surfaces.
    assert _n4_advise(surface_rh_mean_pct=76.0).reason == "mold_risk"


def test_n4_1_outdoor_humidity_needs_a_measured_temperature() -> None:
    """N4.1, the defect this release is named after — the arithmetic that made
    it visible, kept as a test so the sign cannot flip back unnoticed.

    Room 22 °C/55 % against a genuinely MUGGIER outside of 18 °C/80 %: the
    honest delta is negative and no rule may fire. Pairing the same outdoor RH
    with a substituted temperature (T_rm 10 °C, or the 5 °C control fallback)
    understates the outdoor moisture by ~5-7 g/m³ and turns the sign around,
    straight past the 3.0 g/m³ open threshold.
    """
    w_in = absolute_humidity(22.0, 55.0)
    honest = absolute_humidity(18.0, 80.0)
    assert w_in - honest < 0.0  # outside really is moister
    assert _n4_advise(w_in_gm3=w_in, w_out_gm3=honest).reason != "moisture_out"

    for substitute in (10.0, 5.0):
        fabricated = absolute_humidity(substitute, 80.0)
        assert w_in - fabricated >= 3.0, "the substitute clears the open threshold"
        assert (
            _n4_advise(w_in_gm3=w_in, w_out_gm3=fabricated).reason == "moisture_out"
        ), "which is precisely the wrong advice N4.1 removes at the source"


# --- N5 (v0.194.3): the follow-up review of v0.194.2 --------------------------


def test_n5_free_cooling_separates_the_comfort_edge_from_the_air_gain() -> None:
    """Rule 3t asks two questions and must read a different temperature for each.

    The review's case, measured: air 24.5 °C, warm surfaces lifting the
    operative temperature to 26.0, cooling edge 25.0. The comfort solver calls
    that room too warm — it judges on ``room_decide`` and so does every other
    consumer of ``eff_cool`` — while rule 3t, reading the air, saw 24.5 < 25.0
    and stayed silent. Swapping the air for the operative value wholesale would
    have been the mirror defect: the window exchanges AIR, so crediting the
    outside with the 1.5 K radiant excess opens against a gain that is not
    there.
    """
    kw: dict[str, object] = {
        "w_in_gm3": 10.0,
        "w_out_gm3": 10.0,  # delta 0 — no moisture rule in play
        "cool_edge_c": 25.0,
        "cool_capable": False,
        "fan_capable": False,
        "occupied": False,
    }
    # (a) operative over the edge AND a real 2.5 K air gain -> open.
    assert (
        _advise(room_c=24.5, room_decide_c=26.0, t_out_c=22.0, **kw).reason
        == "heat_out"
    )
    # (b) same room, outside only 0.5 K under the AIR. The operative value
    # would clear the 2.0 K entry (26.0 - 2.0 = 24.0 >= 24.0); the air does
    # not. No advice — this is the half the wholesale swap would have broken.
    assert (
        _advise(room_c=24.5, room_decide_c=26.0, t_out_c=24.0, **kw).reason
        != "heat_out"
    )
    # (c) the converse: air over the edge but COLD surfaces pulling the
    # operative value under it. The solver does not call that room too warm,
    # so neither may rule 3t.
    assert (
        _advise(room_c=25.5, room_decide_c=24.5, t_out_c=22.0, **kw).reason
        != "heat_out"
    )
    # (d) no MRT model -> one temperature, and the rule behaves as before.
    assert _advise(room_c=26.0, t_out_c=22.0, **kw).reason == "heat_out"


def test_n5_moisture_entry_needs_the_absolute_and_the_relative_line() -> None:
    """8.7 g/m³ alone told a hot, dry room to air itself out.

    The threshold encodes 20 °C/50 %, the DIN 4108-2 reference indoor climate —
    a DESIGN climate, never an operating threshold. Read as an operating one it
    drifts with room temperature: the same 8.7 g/m³ is 56.8 % RH at 18 °C and
    32.1 % at 28 °C. The dryness veto cannot catch the warm end, because its
    own limit is absolute too (7 g/m³ = 25.8 % RH at 28 °C).
    """
    # 28 °C / 33 % = 8.96 g/m³: over the absolute line, objectively dry air.
    assert _advise(w_in_gm3=8.96, w_out_gm3=5.0, rh_pct=33.0).reason != "moisture_out"
    # 16 °C / 65 % = 8.84 g/m³: barely over the same line, and genuinely damp.
    assert _advise(w_in_gm3=8.84, w_out_gm3=5.0, rh_pct=65.0).reason == "moisture_out"
    # The relative line alone is not enough either: 18 °C / 52 % = 7.97 g/m³
    # carries less water than the reference climate.
    assert _advise(w_in_gm3=7.97, w_out_gm3=4.0, rh_pct=52.0).reason != "moisture_out"


def test_n5_dryness_veto_takes_either_axis() -> None:
    """The veto is an OR, and each half catches what the other cannot."""
    # absolute half, unchanged: 7 g/m³ in a normally humid-reading room.
    assert _advise(w_in_gm3=6.0, w_out_gm3=3.0, rh_pct=55.0).reason == "too_dry"
    # relative half: 26 °C / 33 % = 8.02 g/m³ — ABOVE the absolute floor and
    # still parched. Nothing objected to drying it further before N5.
    assert _advise(w_in_gm3=8.02, w_out_gm3=5.0, rh_pct=33.0).reason == "too_dry"


def test_n5_dryness_line_sits_at_35_so_summer_free_cooling_survives() -> None:
    """Why the relative dryness line is 35 % and not the 40 % that mirrors 7 g/m³.

    Rule 2 sits ABOVE rule 3t. A 40 % line would veto free-cooling for a 26 °C
    room at 40 % RH (9.72 g/m³ — dry by no measure), and the veto would quietly
    cost the hot-day advice that rule 3t exists for. 35 % keeps that case
    free-coolable and still catches the genuinely dry room one step below.
    """
    summer: dict[str, object] = {
        "w_in_gm3": 9.72,  # 26 °C / 40 %
        "w_out_gm3": 8.0,  # drier outside, so rule 2 would be actionable
        "room_c": 26.0,
        "cool_edge_c": 24.5,
        "t_out_c": 21.0,
        "cool_capable": False,
        "fan_capable": False,
        "occupied": False,
    }
    assert _advise(rh_pct=40.0, **summer).reason == "heat_out"
    assert _advise(rh_pct=34.0, **summer).reason == "too_dry"


# --- N6 (v0.194.4): the live bedroom finding, 2026-09-14 ---------------------


def _bedroom_0914(**kw: object) -> VentilationAdvice:
    """The live tick, read off the running instance on 2026-09-14 06:38.

    Bedroom: air 22.0 °C / 62 % RH (12.0 g/m³) against 8.3 g/m³ outside, so
    3.7 g/m³ to gain. Modelled surface RH 79.0 % over a 62.8 % ceiling, 48-h
    mean 67.26 % (under rule 1's line, so the "open for mould" escape hatch is
    shut). No floor enforced anywhere: ``mould_engaged`` false, no binding.
    Cooling edge 22.0 — exactly the room temperature.
    """
    base: dict[str, object] = {
        "w_in_gm3": 12.0,
        "w_out_gm3": 8.3,
        "rh_pct": 62.0,
        "room_c": 22.0,
        "cool_edge_c": 22.0,
        "t_out_c": 12.0,
        "surface_rh_pct": 79.0,
        "rh_max_safe_pct": 62.8,
        "surface_rh_mean_pct": 67.26,
        "surface_needs_warmer": True,
        "cool_edge_protected": False,
        "window_open": True,
        "occupied": True,
        "cool_capable": False,
        "fan_capable": False,
    }
    base.update(kw)
    return _advise(**base)


def test_n6_advice_no_longer_inverts_on_the_window_contact() -> None:
    """The defect, as the instance recorded it to the second.

    04:03:24 window opens -> ``close``/``mold_guard``. 04:32:13 it shuts ->
    ``open``/``moisture_out``. 04:33:51 it opens -> ``close``. Nothing else
    changed in between: both physical conditions of the guard were already
    true with the window SHUT, so the only window-dependent term in the rule
    was the contact itself — and 1b outranks rule 3. The advice was therefore
    impossible to follow, and this test is the statement of that: one and the
    same tick must not produce opposite advice depending on the contact.
    """
    open_window = _bedroom_0914(window_open=True)
    shut_window = _bedroom_0914(window_open=False)
    assert (open_window.action, open_window.reason) == ("open", "moisture_out")
    assert (shut_window.action, shut_window.reason) == ("open", "moisture_out")


def test_n6_stand_down_needs_a_real_drying_gain_and_no_enforced_floor() -> None:
    """Both halves of the stand-down, and the case it must not touch."""
    # Halve the gain to under the moisture rule's own entry threshold and the
    # guard speaks again: without something to win, an open window over cold
    # wet walls is the cause, not the cure.
    assert _bedroom_0914(w_out_gm3=10.5).reason == "mold_guard"  # delta 1.5
    # An ENFORCED floor overrides the stand-down whatever the outside offers.
    assert _bedroom_0914(cool_edge_protected=True).reason == "mold_guard"
    # And the 2026-08-19 kitchen — the case the rule was built for — is
    # untouched: 1.6 g/m³ to gain AND a protection-bound edge, so it fails the
    # stand-down twice over.
    assert _bound_edge().reason == "mold_guard"


def test_n6_stand_down_stays_silent_without_outdoor_humidity() -> None:
    """No ``delta`` means nothing argues that airing would help.

    The N4.2 promise — building protection survives a missing outdoor sensor —
    must not be quietly undone by a rule that reads the same data.
    """
    blind = _bedroom_0914(w_out_gm3=None)
    assert (blind.action, blind.reason) == ("close", "mold_guard")
    assert blind.delta_gm3 is None
