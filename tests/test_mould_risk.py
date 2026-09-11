from __future__ import annotations

import pytest

from custom_components.poise.comfort.mold import surface_temperature
from custom_components.poise.comfort.mould_risk import (
    ACUTE_WET_HOURS,
    DECLINE_GT_24H,
    DECLINE_LT_6H,
    DEFAULT_SUBSTRATE,
    INDEX_ENGAGE,
    INDEX_MAX,
    INDEX_RELEASE,
    ROOM_PROFILE_SUBSTRATE,
    SUBSTRATES,
    WARM_START_INDEX,
    SubstrateClass,
    critical_rh,
    evaluate,
    index_step,
    max_index,
    required_air_temperature,
)
from custom_components.poise.estimation.psychrometrics import (
    saturation_pressure,
    vapour_pressure,
)

SENSITIVE = SUBSTRATES[SubstrateClass.SENSITIVE]
VERY_SENSITIVE = SUBSTRATES[SubstrateClass.VERY_SENSITIVE]


# --- substrate table --------------------------------------------------------


def test_substrate_table_is_complete() -> None:
    assert set(SUBSTRATES) == set(SubstrateClass)


def test_default_substrate_is_sensitive() -> None:
    # Paper-faced plasterboard / wallpaper is the ordinary interior finish.
    assert DEFAULT_SUBSTRATE is SubstrateClass.SENSITIVE


def test_room_profile_map_is_latent_but_well_formed() -> None:
    # ROOM_PROFILE_SUBSTRATE is deliberately called by nobody yet (ADR-0071 §3).
    # Pinning it here keeps it honest AND keeps a dead-code gate from pruning a
    # constant that is prepared on purpose.
    assert set(ROOM_PROFILE_SUBSTRATE.values()) <= set(SubstrateClass)
    assert ROOM_PROFILE_SUBSTRATE["bathroom"] is SubstrateClass.MEDIUM_RESISTANT
    assert ROOM_PROFILE_SUBSTRATE["living"] is SubstrateClass.SENSITIVE


# --- critical_rh ------------------------------------------------------------


def test_critical_rh_reference_points() -> None:
    # Ojanen Eq. 1 reference values (the classic 80 / 82 / 88 triple).
    assert critical_rh(20.0, SENSITIVE) == pytest.approx(80.0, abs=0.1)
    assert critical_rh(10.0, SENSITIVE) == pytest.approx(82.0, abs=0.1)
    assert critical_rh(5.0, SENSITIVE) == pytest.approx(88.0, abs=0.1)


def test_critical_rh_above_20c_is_the_class_floor() -> None:
    # The cubic is only fitted to 20 °C; above it the class floor governs.
    assert critical_rh(25.0, SENSITIVE) == SENSITIVE.rh_min
    assert critical_rh(30.0, SUBSTRATES[SubstrateClass.RESISTANT]) == 85.0


def test_critical_rh_never_below_the_class_floor() -> None:
    # Resistant renders do not grow below 85 % however cold the cubic says.
    resistant = SUBSTRATES[SubstrateClass.RESISTANT]
    assert critical_rh(12.0, resistant) == pytest.approx(85.0)


def test_critical_rh_falls_from_0_to_20c() -> None:
    # Monotonically non-increasing. Not STRICT: the Ojanen cubic dips ~0.1 pp
    # under 80 % around 17 °C (regression noise), the rh_min clamp flattens
    # that tail, and it climbs back by 0.04 pp at exactly 20 °C. A 0.05 pp
    # tolerance covers the artefact without hiding a real inversion.
    prev = critical_rh(0.0, SENSITIVE)
    for step in range(1, 81):
        value = critical_rh(step * 0.25, SENSITIVE)
        assert value <= prev + 0.05
        prev = value
    assert critical_rh(0.0, SENSITIVE) > critical_rh(15.0, SENSITIVE)


# --- max_index --------------------------------------------------------------


def test_max_index_at_saturation_is_a_plus_b_minus_c() -> None:
    # x = 1 at 100 % surface RH -> M_max = a + b - c for every class.
    for spec in SUBSTRATES.values():
        expected = spec.a + spec.b - spec.c
        assert max_index(10.0, 100.0, spec) == pytest.approx(expected)


def test_max_index_is_zero_at_or_below_the_critical_line() -> None:
    crit = critical_rh(14.0, SENSITIVE)
    assert max_index(14.0, crit, SENSITIVE) == 0.0
    assert max_index(14.0, crit - 5.0, SENSITIVE) == 0.0


def test_max_index_stays_low_at_a_steady_82_percent() -> None:
    # The false positive that sank the static criterion: a permanently damp
    # 82 % wall tops out far below the engage threshold, so it must never be
    # able to drive the index to 2.
    assert max_index(14.0, 82.0, SENSITIVE) < INDEX_ENGAGE


def test_max_index_clamped_into_the_index_range() -> None:
    # Surfaces past saturation are still just x = 1, never more.
    assert max_index(14.0, 130.0, VERY_SENSITIVE) <= INDEX_MAX


# --- index_step -------------------------------------------------------------


def test_index_step_grows_only_above_the_critical_line() -> None:
    crit = critical_rh(14.0, SENSITIVE)
    wet = index_step(
        1.0,
        t_surface=14.0,
        rh_surface=crit + 10.0,
        dt_h=1.0,
        dry_hours=0.0,
        spec=SENSITIVE,
    )
    dry = index_step(
        1.0,
        t_surface=14.0,
        rh_surface=crit - 10.0,
        dt_h=1.0,
        dry_hours=1.0,
        spec=SENSITIVE,
    )
    assert wet > 1.0
    assert dry < 1.0


def test_index_step_does_not_grow_below_freezing() -> None:
    # Outside the Hukka & Viitanen validity window (0 < T < 50) there is no
    # growth term at all — an ice-cold surface is not a growth surface.
    assert (
        index_step(
            1.0,
            t_surface=-2.0,
            rh_surface=99.0,
            dt_h=1.0,
            dry_hours=1.0,
            spec=SENSITIVE,
        )
        < 1.0
    )


def test_index_step_decline_uses_the_class_factor() -> None:
    # C_mat: the sensitive class loses half the reference rate, the very
    # sensitive class the full rate.
    start = 3.0
    sens = index_step(
        start, t_surface=15.0, rh_surface=50.0, dt_h=1.0, dry_hours=2.0, spec=SENSITIVE
    )
    very = index_step(
        start,
        t_surface=15.0,
        rh_surface=50.0,
        dt_h=1.0,
        dry_hours=2.0,
        spec=VERY_SENSITIVE,
    )
    assert sens - start == pytest.approx(DECLINE_LT_6H * SENSITIVE.decline)
    assert very - start == pytest.approx(DECLINE_LT_6H * VERY_SENSITIVE.decline)
    assert sens > very  # half the decline = less loss


def test_index_step_plateau_between_6_and_24_dry_hours() -> None:
    # The reason a daily airing routine does not reset the dose: between 6 h
    # and 24 h of dryness the colony survives and the index does not move.
    for dry_hours in (6.5, 12.0, 24.0):
        assert index_step(
            3.0,
            t_surface=15.0,
            rh_surface=50.0,
            dt_h=1.0,
            dry_hours=dry_hours,
            spec=SENSITIVE,
        ) == pytest.approx(3.0)


def test_index_step_slow_decline_beyond_24_dry_hours() -> None:
    result = index_step(
        3.0, t_surface=15.0, rh_surface=50.0, dt_h=1.0, dry_hours=30.0, spec=SENSITIVE
    )
    assert result - 3.0 == pytest.approx(DECLINE_GT_24H * SENSITIVE.decline)


def test_index_step_clamps_at_zero_and_six() -> None:
    assert (
        index_step(
            0.0,
            t_surface=15.0,
            rh_surface=10.0,
            dt_h=500.0,
            dry_hours=48.0,
            spec=SENSITIVE,
        )
        == 0.0
    )
    assert (
        index_step(
            INDEX_MAX,
            t_surface=20.0,
            rh_surface=100.0,
            dt_h=5000.0,
            dry_hours=0.0,
            spec=VERY_SENSITIVE,
        )
        == INDEX_MAX
    )


# --- required_air_temperature ----------------------------------------------


def test_required_air_temperature_rises_with_room_humidity() -> None:
    previous = None
    for rh_room in (40.0, 50.0, 55.0, 60.0, 65.0):
        floor, _capped = required_air_temperature(
            t_out=0.0, rh_room=rh_room, t_room=20.0, f_rsi=0.7, spec=SENSITIVE
        )
        if previous is not None:
            assert floor >= previous
        previous = floor


def test_required_air_temperature_caps_at_the_ceiling() -> None:
    # Near-saturated room over a cold wall: heating alone cannot fix it, and
    # the caller has to learn that (dehumidify / ventilate), not get a silently
    # truncated floor.
    floor, capped = required_air_temperature(
        t_out=-5.0, rh_room=95.0, t_room=20.0, f_rsi=0.7, spec=SENSITIVE
    )
    assert floor == pytest.approx(24.0)
    assert capped is True


def test_required_air_temperature_round_trip_hits_the_critical_line() -> None:
    # The bisection is only trustworthy if the surface actually sits ON the
    # critical line at the returned floor (within half a percentage point).
    for t_out, rh_room, t_room in (
        (0.0, 50.0, 20.0),
        (0.0, 60.0, 20.0),
        (-5.0, 55.0, 20.0),
        (5.0, 60.0, 21.0),
    ):
        floor, capped = required_air_temperature(
            t_out=t_out, rh_room=rh_room, t_room=t_room, f_rsi=0.7, spec=SENSITIVE
        )
        assert capped is False
        t_si = surface_temperature(floor, t_out, 0.7)
        p_v = vapour_pressure(t_room, rh_room)
        surface_rh = 100.0 * p_v / saturation_pressure(t_si)
        assert surface_rh == pytest.approx(critical_rh(t_si, SENSITIVE), abs=0.5)


def test_required_air_temperature_no_floor_when_already_safe() -> None:
    # A dry room over a mild outdoor temperature needs no protection at all.
    floor, capped = required_air_temperature(
        t_out=15.0, rh_room=35.0, t_room=21.0, f_rsi=0.7, spec=SENSITIVE
    )
    assert capped is False
    assert floor <= 15.0


# --- evaluate ---------------------------------------------------------------


def test_evaluate_without_humidity_passes_the_state_through() -> None:
    # Blind is not dry: freezing the dose beats eroding a real, earned index.
    risk = evaluate(
        t_room=21.0,
        rh_room=None,
        t_out=5.0,
        index=2.7,
        wet_hours=5.0,
        dry_hours=3.0,
        dt_h=1.0,
        was_engaged=True,
    )
    assert (risk.index, risk.wet_hours, risk.dry_hours) == (2.7, 5.0, 3.0)
    assert risk.engaged is False
    assert risk.floor is None
    assert risk.reason == "no_humidity"


def test_evaluate_dry_room_stays_clear() -> None:
    risk = evaluate(
        t_room=21.0,
        rh_room=40.0,
        t_out=5.0,
        index=WARM_START_INDEX,
        wet_hours=0.0,
        dry_hours=100.0,
        dt_h=1.0,
        was_engaged=False,
    )
    assert risk.surface_rh < risk.critical_rh
    assert risk.dry_hours == 101.0
    assert risk.wet_hours == 0.0
    assert risk.engaged is False
    assert risk.floor is None
    assert risk.reason == "clear"


def test_evaluate_acute_backstop_engages_after_48_wet_hours() -> None:
    # Day-1 effectiveness: the slow dose is still barely above the warm start
    # after two days, so ONLY the acute backstop can protect the room here.
    index, wet_hours, dry_hours, engaged = WARM_START_INDEX, 0.0, 0.0, False
    risk = None
    for _ in range(int(ACUTE_WET_HOURS)):
        risk = evaluate(
            t_room=20.0,
            rh_room=61.0,
            t_out=0.0,
            index=index,
            wet_hours=wet_hours,
            dry_hours=dry_hours,
            dt_h=1.0,
            was_engaged=engaged,
        )
        index, wet_hours = risk.index, risk.wet_hours
        dry_hours, engaged = risk.dry_hours, risk.engaged
    assert risk is not None
    assert risk.wet_hours == ACUTE_WET_HOURS
    assert risk.index < INDEX_ENGAGE  # the dose alone would NOT have engaged
    assert risk.engaged is True
    assert risk.reason == "acute"
    assert risk.floor is not None


def test_evaluate_hysteresis_holds_between_release_and_engage() -> None:
    def verdict(index: float, was_engaged: bool) -> object:
        return evaluate(
            t_room=21.0,
            rh_room=40.0,
            t_out=5.0,
            index=index,
            wet_hours=0.0,
            dry_hours=100.0,
            dt_h=1.0,
            was_engaged=was_engaged,
        )

    # Between INDEX_RELEASE and INDEX_ENGAGE the verdict depends purely on the
    # previous tick — that is the whole point of the band.
    assert INDEX_RELEASE < 1.7 < INDEX_ENGAGE
    held = verdict(1.7, True)
    fresh = verdict(1.7, False)
    assert held.engaged is True
    assert held.floor is not None
    assert fresh.engaged is False
    # Below the release line even a previously engaged zone lets go.
    released = verdict(1.4, True)
    assert released.engaged is False
    assert released.reason == "clear"


def test_evaluate_warm_start_selects_the_post_germination_k1_branch() -> None:
    # ADR-0071 §4: the 1.0 warm start puts a zone in the post-germination k1
    # branch from day 1 — that is a statement about WHICH branch, not about
    # speed. The direction of the speed difference is material-dependent: for
    # the VTT reference material (VERY_SENSITIVE) the post-germination branch
    # is the faster one (k1 2.0 vs 1.0), while the default class SENSITIVE
    # inverts the pair (0.386 vs 0.578) and grows more SLOWLY above index 1.
    # Day-one protection therefore never rests on the warm start; it rests on
    # the acute backstop (§5). This test pins the branch switch on the
    # reference material, where the effect is unambiguous.
    def step(index: float) -> float:
        return (
            evaluate(
                t_room=20.0,
                rh_room=70.0,
                t_out=0.0,
                index=index,
                wet_hours=0.0,
                dry_hours=0.0,
                dt_h=1.0,
                was_engaged=False,
                spec=VERY_SENSITIVE,
            ).index
            - index
        )

    assert step(WARM_START_INDEX) > step(0.0)
