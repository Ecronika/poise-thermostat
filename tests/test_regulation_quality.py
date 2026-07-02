"""Tests for the EN 15500-1 control-accuracy metric (ADR-0055)."""

from __future__ import annotations

from custom_components.poise.control.regulation_quality import (
    WARMUP_MIN,
    RegulationQuality,
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
