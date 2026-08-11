from __future__ import annotations

import pytest

from custom_components.poise.control.optimal_start import (
    advise,
    forecast_day_mean,
    heatup_minutes,
    latched_forecast_day,
    mean_forecast_outdoor,
)
from custom_components.poise.estimation.thermal_ekf import ThermalModel

# Strong heater: t_eq = t_out + beta_h/alpha = 5 + 4/0.15 = 31.7 C >> target.
_STRONG = ThermalModel(alpha=0.15, beta_h=4.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)
# Weak heater: t_eq = 5 + 1/0.15 = 11.7 C, below a 21 C target.
_WEAK = ThermalModel(alpha=0.15, beta_h=1.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)


def test_already_warm_needs_no_lead() -> None:
    assert heatup_minutes(_STRONG, room=21.5, target=21.0, t_out=5.0) == 0.0


def test_reachable_returns_positive_lead() -> None:
    lead = heatup_minutes(_STRONG, room=18.0, target=21.0, t_out=5.0)
    assert lead is not None and lead > 0.0


def test_colder_room_needs_more_lead() -> None:
    warm = heatup_minutes(_STRONG, room=19.5, target=21.0, t_out=5.0)
    cold = heatup_minutes(_STRONG, room=17.0, target=21.0, t_out=5.0)
    assert warm is not None and cold is not None
    assert cold > warm


def test_colder_outdoor_needs_more_lead() -> None:
    mild = heatup_minutes(_STRONG, room=18.0, target=21.0, t_out=10.0)
    harsh = heatup_minutes(_STRONG, room=18.0, target=21.0, t_out=2.0)
    assert mild is not None and harsh is not None
    assert harsh > mild


def test_weak_heater_cannot_reach_target() -> None:
    assert heatup_minutes(_WEAK, room=18.0, target=21.0, t_out=5.0) is None


def test_beyond_horizon_is_unreachable() -> None:
    out = heatup_minutes(_STRONG, room=18.0, target=21.0, t_out=5.0, max_lead_h=0.1)
    assert out is None


def test_advise_starts_when_deadline_within_lead() -> None:
    a = advise(_STRONG, room=18.0, target=21.0, t_out=5.0, minutes_to_comfort=30.0)
    assert a.reachable
    assert a.lead_minutes > 30.0
    assert a.start_now


def test_advise_waits_when_deadline_far() -> None:
    a = advise(_STRONG, room=18.0, target=21.0, t_out=5.0, minutes_to_comfort=300.0)
    assert a.reachable
    assert not a.start_now


def test_advise_unreachable_does_best_effort() -> None:
    a = advise(_WEAK, room=18.0, target=21.0, t_out=5.0, minutes_to_comfort=10.0)
    assert not a.reachable
    assert a.start_now  # heat early so we arrive as warm as possible


def test_forecast_mean_constant_returns_constant() -> None:
    samples = [(0.0, 4.0), (60.0, 4.0), (120.0, 4.0)]
    assert mean_forecast_outdoor(samples, 120.0, fallback=99.0) == 4.0


def test_forecast_mean_linear_ramp_is_midpoint() -> None:
    # 0 C now rising to 10 C at 100 min -> mean over [0,100] is 5 C
    samples = [(0.0, 0.0), (100.0, 10.0)]
    assert mean_forecast_outdoor(samples, 100.0, fallback=99.0) == pytest.approx(5.0)


def test_forecast_mean_holds_flat_before_first_sample() -> None:
    # horizon ends before the first sample offset -> hold first value
    samples = [(60.0, 8.0), (120.0, 2.0)]
    assert mean_forecast_outdoor(samples, 30.0, fallback=99.0) == 8.0


def test_forecast_mean_empty_or_zero_horizon_falls_back() -> None:
    assert mean_forecast_outdoor([], 60.0, fallback=7.5) == 7.5
    assert mean_forecast_outdoor([(0.0, 3.0)], 0.0, fallback=7.5) == 7.5


def test_forecast_mean_partial_window_weights_by_time() -> None:
    # 0 C for first 30 min, then 12 C; mean over 60 min = (0*30 + ramp...).
    # samples: 0->0C, 30->0C, 30->12C approximated by 0@0, 30@0, 60@12
    samples = [(0.0, 0.0), (30.0, 0.0), (60.0, 12.0)]
    # area = 0 over [0,30] + trapezoid 0->12 over [30,60] = 0.5*12*30 = 180; /60 = 3
    assert mean_forecast_outdoor(samples, 60.0, fallback=99.0) == pytest.approx(3.0)


def test_plan_preheat_coasts_at_window_end() -> None:
    from custom_components.poise.control.optimal_start import plan_preheat
    from custom_components.poise.estimation.thermal_ekf import ThermalModel

    model = ThermalModel(alpha=0.15, beta_h=3.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)
    plan = plan_preheat(
        comfort_base=21.0,
        is_comfort=True,
        setback_offset=0.0,
        minutes_to_comfort=0.0,
        optimal_start_enabled=True,
        can_heat=True,
        identified=True,
        model=model,
        room=21.0,
        t_out_lead=5.0,
        heat_lower=20.0,
        heat_upper=24.0,
        optimal_stop_enabled=True,
        minutes_to_setback=5.0,
        coast_lower=20.0,
    )
    assert plan.coasting and plan.base == 20.0


def test_plan_preheat_no_coast_when_disabled() -> None:
    from custom_components.poise.control.optimal_start import plan_preheat
    from custom_components.poise.estimation.thermal_ekf import ThermalModel

    model = ThermalModel(alpha=0.15, beta_h=3.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)
    plan = plan_preheat(
        comfort_base=21.0,
        is_comfort=True,
        setback_offset=0.0,
        minutes_to_comfort=0.0,
        optimal_start_enabled=True,
        can_heat=True,
        identified=True,
        model=model,
        room=21.0,
        t_out_lead=5.0,
        heat_lower=20.0,
        heat_upper=24.0,
        optimal_stop_enabled=False,
        minutes_to_setback=5.0,
        coast_lower=20.0,
    )
    assert not plan.coasting and plan.base == 21.0


# --- ADR-0054 Nachtrag V1: forecast daily mean for the clo blend ------------


def test_forecast_day_mean_is_the_24h_window_mean() -> None:
    # 20 C rising to 30 C at 12 h (segment mean 25), then held flat at 30 C
    # for the second half -> (25*720 + 30*720) / 1440 = 27.5.
    samples = [(0.0, 20.0), (720.0, 30.0)]
    assert forecast_day_mean(samples) == pytest.approx(27.5)


def test_forecast_day_mean_none_without_samples() -> None:
    assert forecast_day_mean([]) is None


def test_latched_forecast_day_updates_once_per_day() -> None:
    # First evaluation of the day computes from the cache...
    key, val = latched_forecast_day(None, None, "2026-08-02", [(0.0, 24.0)])
    assert (key, val) == ("2026-08-02", 24.0)
    # ...later ticks of the SAME day keep the latched value even though the
    # rolling forecast cache has moved on (one clo update per day).
    key, val = latched_forecast_day(key, val, "2026-08-02", [(0.0, 30.0)])
    assert (key, val) == ("2026-08-02", 24.0)
    # A new local day recomputes from the fresh cache.
    key, val = latched_forecast_day(key, val, "2026-08-03", [(0.0, 30.0)])
    assert (key, val) == ("2026-08-03", 30.0)


def test_latched_forecast_day_new_day_without_forecast_clears() -> None:
    # Yesterday's anticipation must not linger into a forecast-less day.
    key, val = latched_forecast_day("2026-08-02", 31.0, "2026-08-03", [])
    assert (key, val) == ("2026-08-03", None)


def test_forecast_samples_drop_non_finite_temperatures() -> None:
    """B.5: weather services are external data — NaN/Inf temps must be
    skipped like unparseable ones, not folded into the forecast mean."""
    from datetime import UTC, datetime

    from custom_components.poise.control.optimal_start import (
        forecast_samples_from_response,
    )

    base = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    entries = [
        {"datetime": "2026-08-11T13:00:00+00:00", "temperature": 5.0},
        {"datetime": "2026-08-11T14:00:00+00:00", "temperature": float("nan")},
        {"datetime": "2026-08-11T15:00:00+00:00", "temperature": "inf"},
        {"datetime": "2026-08-11T16:00:00+00:00", "temperature": 7.0},
    ]
    out = forecast_samples_from_response(
        {"weather.home": {"forecast": entries}}, "weather.home", base
    )
    assert [t for _, t in out] == [5.0, 7.0]
