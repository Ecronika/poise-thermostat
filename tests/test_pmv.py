"""Tests for the ISO 7730 PMV/PPD comfort index (ADR-0054)."""

from __future__ import annotations

from custom_components.poise.comfort.pmv import pmv_ppd, predictive_clo


def test_iso7730_optimal_operative_temps_are_neutral() -> None:
    # ISO 7730 Annex D: PMV = 0 near these operative temps.
    assert abs(pmv_ppd(t_air=24.5, t_mrt=24.5, rh=50, clo=0.5, met=1.2).pmv) <= 0.1
    assert abs(pmv_ppd(t_air=22.0, t_mrt=22.0, rh=50, clo=1.0, met=1.2).pmv) <= 0.1


def test_ppd_floor_and_category() -> None:
    neutral = pmv_ppd(t_air=24.5, t_mrt=24.5, rh=50, clo=0.5, met=1.2)
    assert 5.0 <= neutral.ppd <= 5.3  # PPD minimum is 5 %
    assert neutral.category == "I"


def test_monotonic_in_temperature() -> None:
    pmvs = [
        pmv_ppd(t_air=t, t_mrt=t, rh=50, clo=0.5, met=1.2).pmv
        for t in (20, 22, 24, 26, 28)
    ]
    assert pmvs == sorted(pmvs)
    assert pmvs[0] < 0 < pmvs[-1]


def test_humidity_raises_warm_pmv() -> None:
    dry = pmv_ppd(t_air=28, t_mrt=28, rh=30, clo=0.5, met=1.2).pmv
    humid = pmv_ppd(t_air=28, t_mrt=28, rh=70, clo=0.5, met=1.2).pmv
    assert humid > dry  # muggy air feels warmer


def test_air_movement_lowers_warm_pmv() -> None:
    still = pmv_ppd(t_air=28, t_mrt=28, rh=50, clo=0.5, met=1.2, velocity=0.1).pmv
    fan = pmv_ppd(t_air=28, t_mrt=28, rh=50, clo=0.5, met=1.2, velocity=0.8).pmv
    assert fan < still - 0.3  # elevated air speed = real cooling (M3 coherence)


def test_category_out_of_band() -> None:
    assert pmv_ppd(t_air=30, t_mrt=30, rh=60, clo=0.5, met=1.2).category == "out"


def test_velocity_clamped_to_still_air_floor() -> None:
    a = pmv_ppd(t_air=26, t_mrt=26, rh=50, clo=0.5, met=1.2, velocity=0.0)
    b = pmv_ppd(t_air=26, t_mrt=26, rh=50, clo=0.5, met=1.2, velocity=0.1)
    assert a.pmv == b.pmv


# --- ADR-0054 Nachtrag V1: graded ASHRAE 55 predictive clo ------------------


def test_predictive_clo_ashrae_reference_vectors() -> None:
    # Piecewise Schiavon & Lee (2013) / ASHRAE 55 method 4; vectors match
    # pythermalcomfort's clo_tout (rounded there to 2 decimals).
    assert predictive_clo(-10.0) == 1.0
    assert abs(predictive_clo(0.0) - 0.818) <= 1e-3
    assert abs(predictive_clo(10.0) - 0.5895) <= 1e-3
    assert abs(predictive_clo(20.0) - 0.5064) <= 1e-3
    assert predictive_clo(26.0) == 0.46


def test_predictive_clo_continuous_at_breakpoints() -> None:
    # No jumps at the piecewise seams (-5 / 5 / 26 degC).
    for edge in (-5.0, 5.0, 26.0):
        below = predictive_clo(edge - 1e-3)
        above = predictive_clo(edge + 1e-3)
        assert abs(below - above) <= 0.01


def test_predictive_clo_removes_the_15c_seasonal_jump() -> None:
    # Regression against the old two-point switch: crossing 15 degC running
    # mean must not step the clothing estimate any more.
    assert abs(predictive_clo(14.9) - predictive_clo(15.1)) <= 0.01


def test_predictive_clo_forecast_blend_is_direction_symmetric() -> None:
    # Heat episode: T_rm 20, forecast day mean 28, w=0.4 -> T_eff 23.2.
    assert abs(predictive_clo(20.0, 28.0, anticipation=0.4) - 0.4824) <= 1e-3
    # Cold snap: T_rm 8, forecast -8, w=0.4 -> T_eff 1.6 (linear branch).
    assert abs(predictive_clo(8.0, -8.0, anticipation=0.4) - 0.7598) <= 1e-3
    # Default anticipation moves clo toward the forecast in BOTH directions.
    assert predictive_clo(20.0, 28.0) < predictive_clo(20.0)
    assert predictive_clo(8.0, -8.0) > predictive_clo(8.0)


def test_predictive_clo_degrades_without_forecast() -> None:
    # No forecast -> w = 0 -> exactly the running-mean-only model.
    assert predictive_clo(12.0, None, anticipation=0.4) == predictive_clo(12.0)


def test_predictive_clo_input_clamped_to_model_domain() -> None:
    # Validity range of the source model: -27.2 .. 26 degC.
    assert predictive_clo(-40.0) == 1.0
    assert predictive_clo(40.0) == 0.46
    # Blend result beyond the domain clamps too (T_eff 36 -> 26).
    assert predictive_clo(24.0, 60.0, anticipation=0.5) == 0.46


def test_predictive_clo_none_fallback_stays_summer_default() -> None:
    assert predictive_clo(None) == 0.5
    assert predictive_clo(None, 30.0) == 0.5


def test_predictive_clo_output_within_bounds() -> None:
    for t in range(-40, 41):
        assert 0.4 <= predictive_clo(float(t)) <= 1.2
