"""Tests for the ADR-0069 tier-2 activation lifecycle (pure)."""

from __future__ import annotations

from custom_components.poise.control.comfort_activation import (
    DWELL_TARGET_MIN,
    PPD_EXIT_TOL_PCT,
    STATE_ELIGIBLE,
    STATE_LIVE,
    STATE_SHADOW,
    STATE_SUSPENDED,
    ComfortActivation,
    TierActivation,
    activation_signature,
    cascade_after_invalidation,
    latch_dwelt,
    may_dwell,
    step_tier,
)

SIG = "m1|office|+0.00|"


def _step(act: TierActivation, **over: object) -> TierActivation:
    kw: dict[str, object] = {
        "ready": True,
        "entry_ok": True,
        "ppd": 8.0,
        "signature": SIG,
        "dt_min": 60.0,
        "allowed": True,
        "next_generation": 1,
        "impossible": False,
    }
    kw.update(over)
    return step_tier(act, **kw)  # type: ignore[arg-type]


def test_shadow_enters_eligible_only_when_ready_and_allowed() -> None:
    a = TierActivation()
    assert a.state == STATE_SHADOW
    assert _step(a, ready=False).state == STATE_SHADOW
    assert _step(a, allowed=False).state == STATE_SHADOW
    assert _step(a).state == STATE_ELIGIBLE


def test_dwell_grows_only_on_qualified_ticks_and_never_wall_clock() -> None:
    a = _step(TierActivation())  # -> eligible, dwell 0
    a = _step(a, dt_min=120.0)
    assert a.dwell_min == 120.0
    # Not ready / entry gate failed: the dwell FREEZES (no growth, no reset) —
    # three days of downtime or masked ticks add nothing.
    frozen = _step(a, ready=False, dt_min=10_000.0)
    assert frozen.dwell_min == 120.0 and frozen.state == STATE_ELIGIBLE
    frozen = _step(frozen, entry_ok=False, dt_min=10_000.0)
    assert frozen.dwell_min == 120.0


def test_full_dwell_goes_live_and_stamps_baseline() -> None:
    a = _step(TierActivation())
    a = _step(a, dt_min=DWELL_TARGET_MIN, ppd=7.5, next_generation=3)
    assert a.state == STATE_LIVE
    assert a.baseline_ppd == 7.5
    assert a.baseline_signature == SIG
    assert a.generation == 3


def _live(ppd: float = 7.5, generation: int = 1) -> TierActivation:
    return TierActivation(
        state=STATE_LIVE,
        dwell_min=DWELL_TARGET_MIN,
        baseline_ppd=ppd,
        baseline_signature=SIG,
        generation=generation,
    )


def test_live_holds_within_schmitt_band_and_suspends_beyond() -> None:
    a = _live(ppd=7.5)
    # Within the exit tolerance (strictly wider than the 1-pp entry tol).
    assert _step(a, ppd=7.5 + PPD_EXIT_TOL_PCT).state == STATE_LIVE
    worse = _step(a, ppd=7.5 + PPD_EXIT_TOL_PCT + 0.1)
    assert worse.state == STATE_SUSPENDED
    assert worse.baseline_ppd is None  # re-baseline required


def test_live_suspends_on_signature_change_or_readiness_loss() -> None:
    a = _live()
    assert _step(a, signature="m1|bedroom|+0.00|").state == STATE_SUSPENDED
    assert _step(a, ready=False).state == STATE_SUSPENDED


def test_suspended_requires_full_re_dwell() -> None:
    a = _step(_live(), ready=False)  # -> suspended
    a = _step(a)  # allowed + ready -> eligible again, dwell reset
    assert a.state == STATE_ELIGIBLE and a.dwell_min == 0.0


def test_structural_impossibility_retires_the_latch_to_shadow() -> None:
    # P1 field finding (fan-less Bad zone): a structurally impossible feature
    # must never dwell — and a STALE eligible/live latch (persisted before
    # the fix, or after a hardware swap removed the capability) RETIRES to
    # shadow instead of blocking the serialization forever. A live exit still
    # cascades via the caller's live->non-live detection.
    stale = TierActivation(state=STATE_ELIGIBLE, dwell_min=500.0, generation=1)
    assert _step(stale, impossible=True).state == STATE_SHADOW
    assert _step(_live(generation=2), impossible=True).state == STATE_SHADOW
    fresh = TierActivation()
    assert _step(fresh, impossible=True) == fresh  # shadow stays, no churn


def test_fanless_zone_unblocks_the_pmv_offset_dwell() -> None:
    # The review pin: zone without fan_only -> fan_ce stays shadow AND
    # pmv_offset may dwell via the deadlock escape (the eligible-blocker in
    # may_dwell never engages because the impossible latch retired).
    c = ComfortActivation()
    fan = _step(c.fan_ce, impossible=True)
    assert fan.state == STATE_SHADOW
    c2 = ComfortActivation(fan_ce=fan, pmv_offset=c.pmv_offset)
    assert may_dwell(c2, "pmv_offset", predecessor_impossible=True) is True
    pmv = _step(c2.pmv_offset)
    assert pmv.state == STATE_ELIGIBLE


def test_serialization_orders_and_deadlock_escape() -> None:
    c = ComfortActivation()
    # fan_ce (first in order) may always dwell.
    assert may_dwell(c, "fan_ce") is True
    # pmv_offset must wait for a LIVE fan_ce...
    assert may_dwell(c, "pmv_offset") is False
    c2 = ComfortActivation(fan_ce=_live(), pmv_offset=TierActivation())
    assert may_dwell(c2, "pmv_offset") is True
    # ...unless fan_ce is impossible in this zone (no fan_only capability) —
    # the serialization must not deadlock the second feature forever.
    assert may_dwell(c, "pmv_offset", predecessor_impossible=True) is True
    # Only one feature dwells at a time.
    c3 = ComfortActivation(
        fan_ce=TierActivation(state=STATE_ELIGIBLE), pmv_offset=TierActivation()
    )
    assert may_dwell(c3, "pmv_offset", predecessor_impossible=True) is False


def test_cascade_suspends_later_generations() -> None:
    c = ComfortActivation(
        fan_ce=_live(generation=1),
        pmv_offset=_live(generation=2),
        generation=2,
    )
    # fan_ce (gen 1) invalidated -> pmv_offset (gen 2) must re-baseline.
    after = cascade_after_invalidation(c, invalidated_generation=1)
    assert after.pmv_offset.state == STATE_SUSPENDED
    assert after.pmv_offset.baseline_ppd is None
    # The invalidated feature itself is the caller's business, not the cascade's.
    assert after.fan_ce.state == STATE_LIVE


def test_signature_carries_predecessors_so_a_dropout_organically_suspends() -> None:
    # The signature of the later feature includes the active predecessor set;
    # when fan_ce leaves live, the freshly computed signature changes and the
    # ordinary live check suspends pmv_offset even without the explicit cascade.
    sig_with_pred = activation_signature(
        room_profile="office",
        clo_offset=0.0,
        model_rev="m1",
        predecessors=("fan_ce",),
    )
    sig_without = activation_signature(
        room_profile="office", clo_offset=0.0, model_rev="m1", predecessors=()
    )
    assert sig_with_pred != sig_without
    b = TierActivation(
        state=STATE_LIVE,
        dwell_min=DWELL_TARGET_MIN,
        baseline_ppd=8.0,
        baseline_signature=sig_with_pred,
        generation=2,
    )
    assert _step(b, signature=sig_without).state == STATE_SUSPENDED


def test_persistence_roundtrip_and_garbage_tolerance() -> None:
    c = ComfortActivation(
        fan_ce=_live(generation=1),
        pmv_offset=TierActivation(state=STATE_ELIGIBLE, dwell_min=42.0),
        generation=1,
    )
    assert ComfortActivation.from_dict(c.to_dict()) == c
    assert ComfortActivation.from_dict(None) == ComfortActivation()
    garbage = {"fan_ce": {"state": 7, "dwell_min": "x"}, "generation": "y"}
    restored = ComfortActivation.from_dict(garbage)
    assert restored.fan_ce.state == STATE_SHADOW
    assert restored.generation == 0


def test_latch_dwelt_flags_only_a_grown_eligible_dwell() -> None:
    # Display-only helper for the card's maturing progress: True exactly when
    # this tick added qualified dwell time to an eligible latch.
    prev = TierActivation(state=STATE_ELIGIBLE, dwell_min=100.0)
    grown = _step(prev, dt_min=30.0)
    assert grown.state == STATE_ELIGIBLE and grown.dwell_min == 130.0
    assert latch_dwelt(prev, grown) is True
    # Frozen dwell (a non-qualifying tick) is NOT advancing.
    frozen = _step(prev, entry_ok=False)
    assert frozen == prev
    assert latch_dwelt(prev, frozen) is False
    # A flip to live is no longer "maturing" — the pill switches anyway.
    flipped = _step(prev, dt_min=DWELL_TARGET_MIN)
    assert flipped.state == STATE_LIVE
    assert latch_dwelt(prev, flipped) is False
    # Shadow/suspended never report progress.
    assert latch_dwelt(TierActivation(), TierActivation()) is False
