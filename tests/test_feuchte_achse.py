"""ADR-0066 humidity axis (pure): absolute humidity, safe-RH ceiling, advice."""

from __future__ import annotations

from pathlib import Path

from custom_components.poise.comfort.mold import (
    max_safe_rh,
    mold_min_air_temperature,
)
from custom_components.poise.comfort.ventilation import (
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


def test_max_safe_rh_round_trip_inverts_the_floor() -> None:
    # inverse consistency (design §10): the RH ceiling returned for a given
    # air temperature must, fed into the floor, reproduce that temperature.
    t_air, t_out = 20.0, -5.0
    rh_max = max_safe_rh(t_air, t_out)
    back = mold_min_air_temperature(t_out, rh_max, t_air)
    assert abs(back - t_air) < 0.1


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
