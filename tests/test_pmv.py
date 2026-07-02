"""Tests for the ISO 7730 PMV/PPD comfort index (ADR-0054)."""

from __future__ import annotations

from custom_components.poise.comfort.pmv import pmv_ppd, seasonal_clo


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


def test_seasonal_clo_defaults() -> None:
    assert seasonal_clo(5.0) == 1.0
    assert seasonal_clo(20.0) == 0.5
    assert seasonal_clo(None) == 0.5
