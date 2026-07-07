"""Tests for the heating-degree-hour kWh/€ savings estimate (ADR-0045)."""

from __future__ import annotations

from custom_components.poise.control.hdh_savings import (
    HdhConfig,
    HdhSavings,
    report_price_eur_kwh,
    saved_fraction_tick,
)

CFG = HdhConfig()


def test_report_price_explicit_wins() -> None:
    assert report_price_eur_kwh(0.42, "radiator", gas=0.11, electric=0.30) == 0.42


def test_report_price_radiator_is_gas() -> None:
    assert report_price_eur_kwh(None, "radiator", gas=0.11, electric=0.30) == 0.11


def test_report_price_electric_default() -> None:
    assert report_price_eur_kwh(None, "heat_pump", gas=0.11, electric=0.30) == 0.30
    assert report_price_eur_kwh(None, None, gas=0.11, electric=0.30) == 0.30


def test_setback_yields_saving_full_comfort_none() -> None:
    # comfort 21, outdoor 5 -> base 16. Setback to 18 -> saved 3 -> fraction 3/16.
    assert saved_fraction_tick(21.0, 18.0, 5.0, 1.0) == 3.0 / 16.0
    # holding full comfort (setpoint == comfort) -> no saving.
    assert saved_fraction_tick(21.0, 21.0, 5.0, 1.0) == 0.0


def test_no_heating_context_in_summer() -> None:
    # outdoor above comfort -> heating implausible -> zero, and accumulator stays empty.
    assert saved_fraction_tick(21.0, 18.0, 27.0, 1.0) == 0.0
    s = HdhSavings().observe(
        comfort=21.0, setpoint=18.0, outdoor=27.0, dt_min=5.0, now_month=7
    )
    assert s.eligible_min == 0.0 and s.report() == {"kwh": 0.0, "eur": 0.0, "pct": 0.0}


def test_monthly_report_kwh_and_eur() -> None:
    s = HdhSavings()
    # 600 min of a constant 25% saved fraction (e.g. base 16, saved 4).
    for _ in range(120):
        s = s.observe(comfort=21.0, setpoint=17.0, outdoor=5.0, dt_min=5.0, now_month=1)
    r = s.report()
    assert r["pct"] == 25.0  # 4/16
    assert r["kwh"] == round(0.25 * CFG.annual_kwh / 12.0, 2)
    assert r["eur"] == round(r["kwh"] * CFG.price_eur_kwh, 2)


def test_month_change_resets() -> None:
    s = HdhSavings()
    s = s.observe(comfort=21.0, setpoint=17.0, outdoor=5.0, dt_min=30.0, now_month=1)
    assert s.eligible_min == 30.0
    s = s.observe(comfort=21.0, setpoint=17.0, outdoor=5.0, dt_min=5.0, now_month=2)
    assert s.eligible_min == 5.0 and s.month == 2  # reset on new month


def test_fraction_clamped_and_roundtrip() -> None:
    # absurd setback below outdoor still clamps the reported fraction to <=100%.
    s = HdhSavings(saved_min=999.0, eligible_min=100.0, month=1)
    assert s.report()["pct"] == 100.0
    assert HdhSavings.from_dict(s.to_dict()) == s
