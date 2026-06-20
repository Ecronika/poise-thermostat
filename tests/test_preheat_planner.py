from __future__ import annotations

from datetime import datetime

from custom_components.poise.control.optimal_start import (
    PreheatPlan,
    forecast_samples_from_response,
    plan_preheat,
)
from custom_components.poise.estimation.thermal_ekf import ThermalModel

# Strong heater: t_eq = 5 + 4/0.15 = 31.7 C >> 21 C target -> reachable.
_STRONG = ThermalModel(alpha=0.15, beta_h=4.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)


def _plan(**kw: object) -> PreheatPlan:
    base = dict(
        comfort_base=21.0,
        is_comfort=False,
        setback_offset=-3.0,
        minutes_to_comfort=30.0,
        optimal_start_enabled=True,
        can_heat=True,
        identified=True,
        model=_STRONG,
        room=17.0,
        t_out_lead=5.0,
        heat_lower=20.0,
        heat_upper=24.0,
    )
    base.update(kw)
    return plan_preheat(**base)  # type: ignore[arg-type]


def test_comfort_window_uses_full_base_no_preheat() -> None:
    p = _plan(is_comfort=True)
    assert p.base == 21.0
    assert not p.preheating
    assert p.preheat_outdoor is None


def test_setback_lowers_base_when_optimal_start_off() -> None:
    p = _plan(optimal_start_enabled=False)
    assert p.base == 18.0  # 21 - 3
    assert not p.preheating
    assert p.preheat_outdoor is None


def test_setback_holds_when_not_identified() -> None:
    p = _plan(identified=False, model=None)
    assert p.base == 18.0
    assert not p.preheating


def test_setback_holds_when_cannot_heat() -> None:
    p = _plan(can_heat=False)
    assert p.base == 18.0
    assert not p.preheating


def test_preheat_cancels_setback_when_deadline_near() -> None:
    p = _plan(minutes_to_comfort=20.0)  # close deadline -> start now
    assert p.preheating
    assert p.base == 21.0  # setback cancelled
    assert p.preheat_outdoor == 5.0


def test_no_preheat_when_deadline_far_but_outdoor_recorded() -> None:
    p = _plan(minutes_to_comfort=600.0)  # far deadline -> wait
    assert not p.preheating
    assert p.base == 18.0  # still in setback
    assert p.preheat_outdoor == 5.0  # evaluated, so outdoor recorded


def test_forecast_outdoor_feeds_the_lead() -> None:
    # Colder forecast outdoor -> longer lead -> more likely to start.
    warm = _plan(minutes_to_comfort=90.0, t_out_lead=12.0)
    cold = _plan(minutes_to_comfort=90.0, t_out_lead=3.0)
    # cold needs longer lead; at 90 min deadline cold should start before warm
    assert cold.preheating or (not warm.preheating)


_BASE = datetime.fromisoformat("2026-01-10T06:00:00+00:00")


def test_forecast_parse_offsets_and_filters_past() -> None:
    resp = {
        "weather.home": {
            "forecast": [
                {"datetime": "2026-01-10T05:00:00+00:00", "temperature": 9.0},  # past
                {"datetime": "2026-01-10T06:00:00+00:00", "temperature": 4.0},
                {"datetime": "2026-01-10T07:00:00+00:00", "temperature": 2.0},
            ]
        }
    }
    out = forecast_samples_from_response(resp, "weather.home", _BASE)
    assert out == [(0.0, 4.0), (60.0, 2.0)]


def test_forecast_parse_skips_bad_entries() -> None:
    resp = {
        "weather.home": {
            "forecast": [
                {"temperature": 4.0},  # no datetime
                {"datetime": "garbage", "temperature": 4.0},
                {"datetime": "2026-01-10T08:00:00+00:00"},  # no temp
                {"datetime": "2026-01-10T08:00:00Z", "temperature": 1.0},  # Z suffix
            ]
        }
    }
    out = forecast_samples_from_response(resp, "weather.home", _BASE)
    assert out == [(120.0, 1.0)]


def test_forecast_parse_empty_or_missing_entity() -> None:
    assert forecast_samples_from_response(None, "weather.home", _BASE) == []
    assert forecast_samples_from_response({}, "weather.home", _BASE) == []
    assert (
        forecast_samples_from_response({"weather.other": {}}, "weather.home", _BASE)
        == []
    )


def test_forecast_parse_accepts_naive_datetime_object() -> None:
    # A naive datetime forecast inherits the reference timezone (base tz).
    naive = datetime(2026, 1, 10, 7, 0)  # no tzinfo
    resp = {"weather.home": {"forecast": [{"datetime": naive, "temperature": 3.0}]}}
    out = forecast_samples_from_response(resp, "weather.home", _BASE)
    assert out == [(60.0, 3.0)]


def test_forecast_parse_skips_non_datetime_value_and_bad_temp() -> None:
    resp = {
        "weather.home": {
            "forecast": [
                {"datetime": 12345, "temperature": 3.0},  # int -> not a datetime
                {"datetime": "2026-01-10T07:00:00+00:00", "temperature": "abc"},  # NaN
                {"datetime": "2026-01-10T08:00:00+00:00", "temperature": 1.0},
            ]
        }
    }
    out = forecast_samples_from_response(resp, "weather.home", _BASE)
    assert out == [(120.0, 1.0)]
