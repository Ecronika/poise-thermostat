"""Tests for the pure actuator↔room reference-frame offset (ADR-0056)."""

from __future__ import annotations

from custom_components.poise.control.reference_offset import (
    OffsetEstimate,
    compensated_setpoint,
    update_offset,
)


def _feed(pairs, *, dt_min=5.0, prev=None, **kw):
    est = prev
    for act, room in pairs:
        est = update_offset(est, actuator_temp=act, room_temp=room, dt_min=dt_min, **kw)
    return est


def test_first_sample_not_trusted() -> None:
    e = update_offset(None, actuator_temp=26.5, room_temp=25.3, dt_min=1.0)
    assert e is not None
    assert abs(e.offset - 1.2) < 1e-9
    assert e.trusted is False  # never trust a first sample
    assert e.minutes == 1.0


def test_missing_reading_holds_prev() -> None:
    e = update_offset(None, actuator_temp=26.0, room_temp=25.0, dt_min=1.0)
    assert update_offset(e, actuator_temp=None, room_temp=25.0, dt_min=1.0) is e
    assert update_offset(e, actuator_temp=26.0, room_temp=None, dt_min=1.0) is e


def test_offset_capped() -> None:
    e = update_offset(None, actuator_temp=30.0, room_temp=20.0, dt_min=1.0, cap=2.0)
    assert e is not None and e.offset == 2.0  # 10 K raw clamped to the cap
    assert e.raw == 10.0


def test_stable_offset_converges_and_trusts() -> None:
    # a steady +1.2 K offset, sampled past the 30-min warm-up
    e = _feed([(26.2, 25.0)] * 8, dt_min=5.0)  # 40 min
    assert e is not None
    assert 1.0 < e.offset <= 1.2
    assert e.deviation < 0.1
    assert e.trusted is True


def test_noisy_sign_flipping_offset_not_trusted() -> None:
    # the office-AC case: raw swings +1.5 / -1.5 -> big step-to-step change
    pairs = [(25.0 + (1.5 if i % 2 == 0 else -1.5), 25.0) for i in range(12)]
    e = _feed(pairs, dt_min=5.0)  # 60 min: warmed up, but unstable
    assert e is not None
    assert e.minutes >= 30.0
    assert e.deviation > 0.6  # noise floor exceeded
    assert e.trusted is False  # compensation stays suspended (VTherm caveat)


def test_compensated_setpoint_gating() -> None:
    trusted = OffsetEstimate(
        offset=1.2, deviation=0.05, minutes=60.0, trusted=True, raw=1.2
    )
    untrusted = OffsetEstimate(
        offset=1.2, deviation=1.4, minutes=60.0, trusted=False, raw=-1.3
    )
    # trusted + enabled -> W = S + offset
    assert compensated_setpoint(25.7, trusted, enabled=True) == 26.9
    # untrusted -> base unchanged
    assert compensated_setpoint(25.7, untrusted, enabled=True) == 25.7
    # disabled -> base unchanged even if trusted
    assert compensated_setpoint(25.7, trusted, enabled=False) == 25.7
    # no estimate -> base
    assert compensated_setpoint(25.7, None, enabled=True) == 25.7


def test_roundtrip_restore_conservative() -> None:
    e = _feed([(26.2, 25.0)] * 8, dt_min=5.0)
    assert e is not None and e.trusted is True
    r = OffsetEstimate.from_dict(e.to_dict())
    assert abs(r.offset - e.offset) < 1e-9
    assert abs(r.minutes - e.minutes) < 1e-9
    assert r.trusted is False  # never compensate straight after restore
