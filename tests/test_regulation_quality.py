"""Tests for the EN 15500-1 control-accuracy metric (ADR-0055)."""

from __future__ import annotations

from custom_components.poise.control.regulation_quality import (
    FLIP_TIER_ACTUATOR,
    FLIP_TIER_COMFORT,
    FLIP_TIER_REVERSIBLE,
    PPD_TOL_PCT,
    WARMUP_MIN,
    RegulationQuality,
    flip_metric_ok,
    meets_comfort_quality,
    meets_quality,
)


def _run(room: float, mode: str, n: int = 600, band=(20.0, 24.0)) -> RegulationQuality:
    q = RegulationQuality()
    for _ in range(n):
        q = q.observe(
            room=room,
            heat_sp=band[0],
            cool_sp=band[1],
            mode=mode,
            dt_min=1.0,
            horizon_h=1.0,
        )
    return q


def test_perfect_regulation() -> None:
    q = _run(21.0, "idle")
    assert q.deviation_k < 0.01
    assert q.time_in_band_pct > 99.0
    assert q.cycles_per_hour < 0.01


def test_sustained_undershoot() -> None:
    q = _run(18.0, "heat")  # 2 K below the band
    assert abs(q.deviation_k - 2.0) < 0.05
    assert q.time_in_band_pct < 1.0


def test_overshoot_scored_bilaterally() -> None:
    q = _run(25.5, "cool")  # 1.5 K above the band
    assert abs(q.deviation_k - 1.5) < 0.05


def test_hunting_raises_cycles_but_not_deviation() -> None:
    q = RegulationQuality()
    modes = ("heat", "idle")
    for i in range(600):
        q = q.observe(
            room=21.0,
            heat_sp=20.0,
            cool_sp=24.0,
            mode=modes[i % 2],
            dt_min=1.0,
            horizon_h=1.0,
        )
    assert q.cycles_per_hour > 30.0  # alternating every minute ~ 60/h
    assert q.deviation_k < 0.01  # yet perfectly in-band: band metric alone misses it


def test_no_phantom_transition_on_first_tick() -> None:
    q = RegulationQuality().observe(
        room=21.0, heat_sp=20.0, cool_sp=24.0, mode="heat", dt_min=1.0
    )
    assert q.cycles_per_hour == 0.0


def test_persistence_roundtrip() -> None:
    q = RegulationQuality(
        deviation_k=0.3,
        in_band=0.95,
        cycles_per_hour=1.2,
        minutes=5000.0,
        last_mode="heat",
    )
    assert RegulationQuality.from_dict(q.to_dict()) == q
    assert RegulationQuality.from_dict(None) == RegulationQuality()


# --- ADR-0055 N1: time-weighted PPD component + risk tiers -------------------


def test_ppd_fold_is_time_weighted_and_matures_separately() -> None:
    q = RegulationQuality()
    assert q.ppd == 5.0  # ISO 7730 theoretical optimum as the neutral seed
    for _ in range(600):
        q = q.observe_ppd(ppd=12.0, dt_min=1.0, horizon_h=1.0)
    assert abs(q.ppd - 12.0) < 0.1
    assert q.ppd_minutes == 600.0
    # The CA clock stays untouched — the two accumulators mature separately
    # (pmv_valid and the CA fairness mask diverge, e.g. bedroom met 0.7).
    assert q.minutes == 0.0
    assert q.deviation_k == 0.0


def test_ppd_persistence_roundtrip_and_legacy_dicts() -> None:
    q = RegulationQuality(deviation_k=0.3, ppd=9.5, ppd_minutes=1234.0)
    assert RegulationQuality.from_dict(q.to_dict()) == q
    # Pre-N1 store dicts carry no ppd keys -> defaults, never raising.
    legacy = {
        "deviation_k": 0.3,
        "in_band": 0.95,
        "cycles_per_hour": 1.0,
        "minutes": 10.0,
        "last_mode": "heat",
    }
    restored = RegulationQuality.from_dict(legacy)
    assert restored.ppd == 5.0
    assert restored.ppd_minutes == 0.0


def test_comfort_gate_needs_ppd_maturity_and_non_worsening() -> None:
    base = {
        "deviation_k": 0.2,
        "in_band": 0.97,
        "cycles_per_hour": 1.0,
        "minutes": WARMUP_MIN + 1.0,
        "ppd": 8.0,
        "ppd_minutes": WARMUP_MIN + 1.0,
    }
    q = RegulationQuality(**base)
    # Entry: the CA gate + a MATURE PPD figure (no baseline yet).
    assert meets_comfort_quality(q, identified=True)
    assert not meets_comfort_quality(q, identified=False)
    assert not meets_comfort_quality(
        RegulationQuality(**{**base, "ppd_minutes": 10.0}), identified=True
    )
    # The CA legs still bind for comfort features.
    assert not meets_comfort_quality(
        RegulationQuality(**{**base, "deviation_k": 0.9}), identified=True
    )
    # Keep-check: against the pre-flip baseline the time-weighted PPD must
    # not worsen beyond the tolerance (smaller deltas are pseudo-accuracy,
    # ADR-0054: PMV subtleties below +-0.3 carry no information).
    assert meets_comfort_quality(q, identified=True, baseline_ppd=8.0 - PPD_TOL_PCT)
    assert not meets_comfort_quality(
        q, identified=True, baseline_ppd=8.0 - PPD_TOL_PCT - 0.1
    )


def test_flip_tiers_route_to_the_right_gate() -> None:
    mature = {
        "deviation_k": 0.2,
        "in_band": 0.97,
        "cycles_per_hour": 1.0,
        "minutes": WARMUP_MIN + 1.0,
        "ppd": 8.0,
        "ppd_minutes": WARMUP_MIN + 1.0,
    }
    q = RegulationQuality(**mature)
    fresh = RegulationQuality()
    # Tier 1 actuator-critical (MPC/PI/TPI/valve): the full CA gate.
    assert flip_metric_ok(FLIP_TIER_ACTUATOR, q, identified=True)
    assert not flip_metric_ok(FLIP_TIER_ACTUATOR, fresh, identified=True)
    # Tier 2 comfort axes (PMV offset, fan credit): CA gate + PPD component.
    assert flip_metric_ok(FLIP_TIER_COMFORT, q, identified=True)
    assert not flip_metric_ok(
        FLIP_TIER_COMFORT,
        RegulationQuality(**{**mature, "ppd_minutes": 0.0}),
        identified=True,
    )
    # Tier 3 reversible compressor-free writes (fan low/off): the metric does
    # not gate — opt-in, presence and safety guards live in the wiring.
    assert flip_metric_ok(FLIP_TIER_REVERSIBLE, fresh, identified=False)
    # Unknown tiers fail CLOSED.
    assert not flip_metric_ok("wild", q, identified=True)


def test_flip_gate() -> None:
    base = {
        "deviation_k": 0.2,
        "in_band": 0.97,
        "cycles_per_hour": 1.0,
        "minutes": WARMUP_MIN + 1.0,
    }
    assert meets_quality(RegulationQuality(**base), identified=True)
    assert not meets_quality(RegulationQuality(**base), identified=False)
    assert not meets_quality(
        RegulationQuality(**{**base, "deviation_k": 0.9}), identified=True
    )
    assert not meets_quality(
        RegulationQuality(**{**base, "cycles_per_hour": 5.0}), identified=True
    )
    assert not meets_quality(
        RegulationQuality(**{**base, "in_band": 0.8}), identified=True
    )
    assert not meets_quality(
        RegulationQuality(**{**base, "minutes": 100.0}), identified=True
    )
