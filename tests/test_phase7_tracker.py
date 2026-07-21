"""Phase-7 S2 pure tests for ``control.external_override`` (plan phase 7).

The three adoption stages (hold routing V2/K2/M3, mode adoption K2/K3/M2/I6,
setpoint adoption B1/RC-F2) moved out of ``coordinator.py`` into hass-free
implementations over ``ZoneRuntime``, with ``ExternalOverrideTracker`` as the
echo-/foreign-change state machine over ``ExternalOverrideRuntime`` and the
K3 double call unified into ONE observation per channel (decision AND reason).
Behavioural equivalence end-to-end is pinned by the unchanged integration
suites (test_setpoint_adoption, test_mode_adoption, test_adopt_baseline_
restore, the phase-0 adopt/echo pins); THIS module exercises the pure pieces
directly:

* the K3 one-call equivalence proof as an executable matrix — for every gate
  combination and Layer-2 scenario the unified observation returns exactly
  the historical double-call's decision AND reason (both channels);
* the plan's mandatory pure cases: V2 echo re-baseline without timestamp
  renewal, the B1/RC-F2 post-adoption baseline choreography, the R4
  frost-floor phantom-hold guard, the B5 restart-baseline behaviour;
* the stage bodies' command wiring (M3 escape/re-align via the injected
  ``end_hold_fn``, adoption via ``set_mode_override_fn``/``set_override_fn``,
  the I6 pinning, the M2 freeze gate, the off-hold one-tick delay);
* the ``AdoptReason`` vocabulary registry: character-exact serialization and
  the debounce-log whitelist sync (exact historical tuple + complement).
"""

from __future__ import annotations

import itertools
import json
import logging
from typing import Any

import pytest

from custom_components.poise.clock import ManualClock
from custom_components.poise.const import (
    FROST_FLOOR_C,
    SETPOINT_ADOPT_ECHO_WINDOW_S,
    WRITE_DEADBAND_C,
)
from custom_components.poise.contracts import Reading, Source
from custom_components.poise.control.external_override import (
    SUPPRESSED_ADOPT_REASONS,
    AdoptReason,
    ExternalOverrideTracker,
    OverrideObservation,
)
from custom_components.poise.control.override import (
    detect_external_mode,
    detect_external_setpoint,
    mode_adopt_reason,
    setpoint_adopt_reason,
)
from custom_components.poise.control.tick_resolve import resolve_desired_mode
from custom_components.poise.runtime.state import ExternalOverrideRuntime
from custom_components.poise.runtime.tick_result import (
    HoldRoutingResult,
    IngestResult,
    ModeNudgeResult,
    ModeResolutionResult,
    ObservationResult,
    SetpointObservation,
    WriteTargetResult,
)
from custom_components.poise.runtime.zone_runtime import ZoneRuntime

NOW = 3600.0
ECHO = SETPOINT_ADOPT_ECHO_WINDOW_S
_LOG = logging.getLogger("tests.phase7_tracker")


def _runtime() -> ZoneRuntime:
    return ZoneRuntime(ManualClock(10_000.0))


class _Ctx:
    def __init__(self, cid: str) -> None:
        self.id = cid


class _State:
    """Minimal HA-``State`` stand-in (``state`` + ``context``) for the
    pure stages; the real type only flows through under TYPE_CHECKING."""

    def __init__(self, state: str, ctx: str | None = None) -> None:
        self.state = state
        self.context = _Ctx(ctx) if ctx is not None else None


def _ing(**over: Any) -> IngestResult:
    base: dict[str, Any] = {
        "now": NOW,
        "frozen": False,
        "sched_active": False,
        "fault_active": False,
        "heat_source_suspect": False,
        "reading": Reading(21.0, "°C", Source.MEASURED, 1.0, NOW),
        "room": 21.0,
        "rh": None,
        "t_out_eff": 5.0,
        "t_rm_eff": 5.0,
        "t_rm_source": None,
        "q_solar": 0.0,
        "q_solar_source": "none",
        "q_solar_internal": 0.0,
        "t_mrt": 21.0,
        "mrt_source": "room",
        "mrt_internal": 21.0,
    }
    base.update(over)
    return IngestResult(**base)


def _obs(**over: Any) -> ObservationResult:
    base: dict[str, Any] = {
        "window_open": False,
        "can_heat": True,
        "can_cool": True,
        "adaptive_cool": False,
        "device_max": 30.0,
    }
    base.update(over)
    return ObservationResult(**base)


def _wt(**over: Any) -> WriteTargetResult:
    base: dict[str, Any] = {
        "act_state": None,
        "actuator_online": True,
        "cool_ac": None,
        "idle_park_mode": None,
        "eff_cool": 26.0,
        "target": 21.5,
        "mode": "heat",
        "norm_binding": None,
        "binding_precedence": None,
        "override_clamped": False,
    }
    base.update(over)
    return WriteTargetResult(**base)


def _res(**over: Any) -> ModeResolutionResult:
    base: dict[str, Any] = {
        "final_mode": "heat",
        "act_modes": ["heat", "cool", "off"],
        "guard_pol": None,
        "g_min_off": 0.0,
        "g_mode_hold": 0.0,
        "guard_block": None,
        "mode_nudge_blocked": "",
    }
    base.update(over)
    return ModeResolutionResult(**base)


def _routing(**over: Any) -> HoldRoutingResult:
    base: dict[str, Any] = {
        "own_change": False,
        "off_held": False,
        "hold_resumed": False,
        "mode_adopt_reason": "",
        "sp_adopt_reason": "",
    }
    base.update(over)
    return HoldRoutingResult(**base)


def _nudge() -> ModeNudgeResult:
    return ModeNudgeResult(mode_nudge=False, guard_block=None, mode_nudge_blocked="")


def _spo(**over: Any) -> SetpointObservation:
    base: dict[str, Any] = {
        "actual_sp": 21.0,
        "step": 0.5,
        "mode_changed": False,
        "reg_throttled": False,
        "adopted_sp": None,
        "sp_adopt_reason": "",
    }
    base.update(over)
    return SetpointObservation(**base)


class _Commands:
    """Recording stand-ins for the coordinator's S1 command facades.

    They apply the user-state mutation the real facades perform through
    ``control.override_runtime`` (the stage bodies re-read
    ``rt.user.mode_override`` after the commands — I6/M3), and record the
    calls for assertions.  Bus events are the facades' business and out of
    scope here (pinned by the integration event-order suites).
    """

    def __init__(self, rt: ZoneRuntime) -> None:
        self.rt = rt
        self.ended: list[str] = []
        self.modes: list[str] = []
        self.overrides: list[tuple[float, str | None]] = []

    def end_hold(self, reason: str) -> None:
        self.ended.append(reason)
        self.rt.user.override = None
        self.rt.user.mode_override = None

    def set_mode_override(self, mode: str) -> None:
        self.modes.append(mode)
        self.rt.user.mode_override = mode

    def set_override(self, value: float | None, *, reason: str | None = None) -> None:
        if value is not None:
            self.overrides.append((float(value), reason))
        self.rt.user.override = value


def _hold_routing(rt: ZoneRuntime, wt: WriteTargetResult, cmds: _Commands):
    return rt.stage_hold_routing(wt, end_hold_fn=cmds.end_hold)


def _mode_adoption(
    rt: ZoneRuntime,
    cmds: _Commands,
    *,
    ing: IngestResult | None = None,
    obs: ObservationResult | None = None,
    wt: WriteTargetResult | None = None,
    res: ModeResolutionResult | None = None,
    routing: HoldRoutingResult | None = None,
    adopt: bool = True,
):
    return rt.stage_mode_adoption(
        ing or _ing(),
        obs or _obs(),
        wt if wt is not None else _wt(),
        res or _res(),
        routing or _routing(),
        adopt_external_mode=adopt,
        resolve_desired_mode_fn=resolve_desired_mode,
        mode_adopt_reason_fn=mode_adopt_reason,
        set_mode_override_fn=cmds.set_mode_override,
        end_hold_fn=cmds.end_hold,
    )


def _observe(
    rt: ZoneRuntime,
    *,
    actual_sp: float | None,
    step: float = 0.5,
    adopt: bool = True,
    ing: IngestResult | None = None,
    obs: ObservationResult | None = None,
    routing: HoldRoutingResult | None = None,
) -> SetpointObservation:
    return rt.stage_setpoint_observe(
        ing or _ing(),
        obs or _obs(),
        _wt(),
        _res(),
        routing or _routing(),
        _nudge(),
        actual_sp=actual_sp,
        step=step,
        adopt_external_setpoint=adopt,
        setpoint_adopt_reason_fn=setpoint_adopt_reason,
    )


def _adopt_stage(
    rt: ZoneRuntime,
    cmds: _Commands,
    spo: SetpointObservation,
    *,
    mode_reason: str = "",
    ing: IngestResult | None = None,
) -> str:
    return rt.stage_setpoint_adopt(
        ing or _ing(),
        spo,
        mode_adopt_reason=mode_reason,
        actuator_entity="climate.trv",
        logger=_LOG,
        set_override_fn=cmds.set_override,
    )


# ---------------------------------------------------------------------------
# AdoptReason vocabulary + whitelist sync (K3 enum)
# ---------------------------------------------------------------------------


def test_whitelist_is_exactly_the_historical_tuple() -> None:
    # The debounce whitelist of the historical adoption stage, order and
    # content verbatim (coordinator.py 4552-line state, Z. 3550-3563).
    assert SUPPRESSED_ADOPT_REASONS == (
        "echo_window",
        "own_echo",
        "opt_out",
        "safety_window",
        "safety_frozen",
        "hold_resumed",
        "stable_prev",
        "stable_offset",
        "no_baseline",
        "unsupported",
        "schedule_active",
    )


def test_whitelist_members_and_complement_are_the_enum() -> None:
    assert all(isinstance(r, AdoptReason) for r in SUPPRESSED_ADOPT_REASONS)
    # Never logged: the adopt decision itself, the disabled default, and the
    # nothing-was-suppressed codes.
    complement = {m.value for m in AdoptReason} - set(SUPPRESSED_ADOPT_REASONS)
    assert complement == {
        "",
        "adopt",
        "no_signal",
        "device_aligned",
        "own_command_echo",
        "command_echo",
        "implausible_frost",
    }


def test_enum_serializes_character_exact() -> None:
    # The three observable surfaces (coordinator.data values, %s debug-log
    # formatting, JSON store payloads) must all see the historical string.
    for member in AdoptReason:
        assert str(member) == member.value
        assert f"{member}" == member.value
        # The %-formatting path is the debug-log surface (logging uses it).
        assert "%s" % member == member.value  # noqa: UP031
        assert json.dumps(member) == json.dumps(member.value)
        assert member == member.value


def _mode_scenarios() -> list[dict[str, Any]]:
    base: dict[str, Any] = {
        "device_mode": "cool",
        "desired_mode": "heat",
        "last_commanded_mode": "heat",
        "last_cmd_ts": NOW - ECHO * 2,
        "now": NOW,
        "echo_window_s": ECHO,
        "supported_modes": ("heat", "cool", "off"),
        "prev_mode": "heat",
    }
    return [
        {**base},  # adopt
        {**base, "device_mode": None},  # no_signal
        {**base, "device_mode": "unavailable"},  # no_signal
        {**base, "device_mode": "heat"},  # device_aligned
        {**base, "device_mode": "dry"},  # unsupported (not listed)
        {
            **base,
            "device_mode": "heat_cool",
            "supported_modes": ("heat", "cool", "heat_cool"),
        },  # unsupported (B7)
        {**base, "device_mode": "cool", "last_commanded_mode": "cool"},  # own_cmd_echo
        {**base, "last_commanded_mode": None},  # no_baseline
        {**base, "last_cmd_ts": None},  # no_baseline
        {**base, "last_cmd_ts": NOW - ECHO / 2},  # echo_window
        {**base, "prev_mode": "cool"},  # stable_prev
    ]


def test_mode_observation_equals_the_legacy_double_call() -> None:
    """K3 equivalence matrix (mode channel): decision AND reason of the ONE
    ``observe_mode`` call equal the historical detector + reason-chain pair
    for every gate combination and Layer-2 scenario."""
    for kw, (adopt, window, frozen, own, resumed) in itertools.product(
        _mode_scenarios(), itertools.product([False, True], repeat=5)
    ):
        external = ExternalOverrideRuntime(
            last_commanded_hvac=kw["last_commanded_mode"],
            last_hvac_cmd_ts=kw["last_cmd_ts"],
            prev_device_mode=kw["prev_mode"],
        )
        unified = ExternalOverrideTracker(external).observe_mode(
            device_mode=kw["device_mode"],
            desired_mode=kw["desired_mode"],
            now=kw["now"],
            echo_window_s=kw["echo_window_s"],
            supported_modes=kw["supported_modes"],
            adopt_enabled=adopt,
            window_open=window,
            frozen=frozen,
            own_change=own,
            hold_resumed=resumed,
            mode_adopt_reason_fn=mode_adopt_reason,
        )
        # The historical pair: detector under the gate conjunction ...
        legacy_decision = (
            detect_external_mode(**kw)
            if (adopt and not window and not frozen and not own and not resumed)
            else None
        )
        # ... and the Layer-1 chain in its historical order, else Layer-2.
        if not adopt:
            legacy_reason = "opt_out"
        elif window:
            legacy_reason = "safety_window"
        elif frozen:
            legacy_reason = "safety_frozen"
        elif own:
            legacy_reason = "own_echo"
        elif resumed:
            legacy_reason = "hold_resumed"
        else:
            legacy_reason = mode_adopt_reason(**kw)
        assert unified.adopt_mode == legacy_decision, kw
        assert unified.reason == legacy_reason, kw
        assert unified.reason in {m.value for m in AdoptReason}


def _sp_scenarios() -> list[dict[str, Any]]:
    base: dict[str, Any] = {
        "device_sp": 23.0,
        "last_written_sp": 21.0,
        "last_write_ts": NOW - ECHO * 2,
        "now": NOW,
        "echo_window_s": ECHO,
        "deadband": max(WRITE_DEADBAND_C, 0.5),
        "prev_device_sp": 21.0,
        "pre_write_sp": 20.5,
        "frost_floor": FROST_FLOOR_C,
    }
    return [
        {**base},  # adopt
        {**base, "last_written_sp": None},  # no_baseline
        {**base, "last_write_ts": None},  # no_baseline
        {**base, "device_sp": 21.2},  # command_echo (within one 0.5 step)
        {**base, "device_sp": FROST_FLOOR_C},  # implausible_frost
        {**base, "device_sp": FROST_FLOOR_C - 1.0},  # implausible_frost
        {**base, "last_write_ts": NOW - ECHO / 2},  # in-window: pre-write differs
        {
            **base,
            "last_write_ts": NOW - ECHO / 2,
            "device_sp": 20.5,
        },  # echo_window (matches pre-write -> suppressed)
        {
            **base,
            "last_write_ts": NOW - ECHO / 2,
            "pre_write_sp": None,
        },  # echo_window (no three-value proof)
        {**base, "device_sp": 21.2, "last_written_sp": 23.0},  # stable_offset
        {**base, "prev_device_sp": None},  # adopt (no stable-offset guard)
    ]


def test_setpoint_observation_equals_the_legacy_double_call() -> None:
    """K3 equivalence matrix (setpoint channel): decision AND reason of the
    ONE ``observe_setpoint`` call equal the historical detector (observe
    stage) + reason chain (adoption stage) for every gate combination."""
    for kw, (adopt, sched, own, window, frozen) in itertools.product(
        _sp_scenarios(), itertools.product([False, True], repeat=5)
    ):
        external = ExternalOverrideRuntime(
            last_written_sp=kw["last_written_sp"],
            prev_device_sp=kw["prev_device_sp"],
            last_sp_write_ts=kw["last_write_ts"],
            pre_write_sp=kw["pre_write_sp"],
        )
        unified = ExternalOverrideTracker(external).observe_setpoint(
            device_sp=kw["device_sp"],
            now=kw["now"],
            echo_window_s=kw["echo_window_s"],
            deadband=kw["deadband"],
            frost_floor=kw["frost_floor"],
            adopt_enabled=adopt,
            sched_active=sched,
            own_change=own,
            window_open=window,
            frozen=frozen,
            setpoint_adopt_reason_fn=setpoint_adopt_reason,
        )
        legacy_decision = (
            detect_external_setpoint(**kw)
            if (adopt and not sched and not own and not window and not frozen)
            else None
        )
        if not adopt:
            legacy_reason = "opt_out"
        elif sched:
            legacy_reason = "schedule_active"
        elif own:
            legacy_reason = "own_echo"
        elif window:
            legacy_reason = "safety_window"
        elif frozen:
            legacy_reason = "safety_frozen"
        else:
            legacy_reason = setpoint_adopt_reason(**kw)
        assert unified.adopt_setpoint == legacy_decision, kw
        assert unified.reason == legacy_reason, kw
        assert unified.reason in {m.value for m in AdoptReason}


def test_observation_decision_follows_the_reason_verbatim() -> None:
    # The unified contract: adopt iff the ONE reason is exactly "adopt" —
    # decision and reason can never disagree, whatever the reason fn says.
    tracker = ExternalOverrideTracker(ExternalOverrideRuntime())
    for verdict, expected in [("adopt", 22.0), ("anything_else", None)]:
        obs = tracker.observe_setpoint(
            device_sp=22.0,
            now=NOW,
            echo_window_s=ECHO,
            deadband=0.5,
            frost_floor=FROST_FLOOR_C,
            adopt_enabled=True,
            sched_active=False,
            own_change=False,
            window_open=False,
            frozen=False,
            setpoint_adopt_reason_fn=lambda _v=verdict, **_kw: _v,
        )
        assert obs == OverrideObservation(reason=verdict, adopt_setpoint=expected)


# ---------------------------------------------------------------------------
# Plan-mandatory pure cases (V2 / B1+RC-F2 / R4 / B5)
# ---------------------------------------------------------------------------


def test_v2_own_echo_rebaselines_without_timestamp_renewal() -> None:
    rt = _runtime()
    rt.external.last_written_sp = 21.0
    rt.external.last_sp_write_ts = NOW - 30.0  # a recent real write
    spo = _observe(rt, actual_sp=21.8, routing=_routing(own_change=True))
    # V2: the settled device value becomes the echo baseline ...
    assert rt.external.last_written_sp == 21.8
    # ... but the WRITE timestamp is deliberately untouched (echo window and
    # §4 regulation throttle key off the real last-write time).
    assert rt.external.last_sp_write_ts == NOW - 30.0
    # ... and an own-context change is never adopted (K3: own_echo).
    assert spo.adopted_sp is None
    assert spo.sp_adopt_reason == "own_echo"


def test_b1_rcf2_adoption_baseline_choreography() -> None:
    rt = _runtime()
    cmds = _Commands(rt)
    rt.external.last_written_sp = 21.0
    rt.external.pre_write_sp = 19.0
    spo = _spo(actual_sp=22.4, step=0.5, adopted_sp=22.4, sp_adopt_reason="adopt")
    reason = _adopt_stage(rt, cmds, spo)
    assert reason == "adopt"
    # The hold is applied through the injected S1 facade, with the K3 origin.
    assert cmds.overrides == [(22.4, "device_adopt_setpoint")]
    # RC-F2: our *previous* command becomes the pre-write reference.
    assert rt.external.pre_write_sp == 21.0
    # B1: the adopted value (snapped to the device step) is the echo baseline.
    assert rt.external.last_written_sp == 22.5
    assert rt.external.last_sp_write_ts == NOW
    # The adopted hold persists across restarts (K1 dirty flag).
    assert rt.dirty is True
    # P1-4a: the prev reading was updated on the way (before the adoption).
    assert rt.external.prev_device_sp == 22.4


def test_r4_frost_floor_report_is_never_adopted() -> None:
    rt = _runtime()
    rt.external.last_written_sp = 21.0
    rt.external.prev_device_sp = 21.0
    rt.external.last_sp_write_ts = NOW - ECHO * 2
    for device_sp in (FROST_FLOOR_C, FROST_FLOOR_C - 2.0):
        spo = _observe(rt, actual_sp=device_sp)
        assert spo.adopted_sp is None
        assert spo.sp_adopt_reason == "implausible_frost"
    # Just above the floor stays a genuine user change.
    spo = _observe(rt, actual_sp=FROST_FLOOR_C + 1.0)
    assert spo.sp_adopt_reason == "adopt"
    assert spo.adopted_sp == FROST_FLOOR_C + 1.0


def test_b5_restart_baseline_enables_first_tick_adoption() -> None:
    # The persisted B5 baselines + the restore path's "long expired" echo
    # stamps: a device-side change right after the restart must be adopted
    # instead of reading as no_baseline (and a stable value must NOT be).
    rt = _runtime()
    rt.external.last_written_sp = 21.0
    rt.external.prev_device_sp = 21.0
    stale = rt.clock.monotonic() - ECHO * 2.0  # the restore stamp rule
    rt.external.last_sp_write_ts = stale
    ing = _ing(now=rt.clock.monotonic())
    spo = _observe(rt, actual_sp=23.0, ing=ing)
    assert spo.sp_adopt_reason == "adopt"
    assert spo.adopted_sp == 23.0
    # The stable settled value keeps reading as our own echo, not a change.
    rt2 = _runtime()
    rt2.external.last_written_sp = 21.0
    rt2.external.prev_device_sp = 21.0
    rt2.external.last_sp_write_ts = stale
    spo2 = _observe(rt2, actual_sp=21.0, ing=ing)
    assert spo2.sp_adopt_reason == "command_echo"
    assert spo2.adopted_sp is None
    # Without the persisted baselines the first tick stays conservative.
    rt3 = _runtime()
    spo3 = _observe(rt3, actual_sp=23.0, ing=ing)
    assert spo3.sp_adopt_reason == "no_baseline"
    assert spo3.adopted_sp is None


# ---------------------------------------------------------------------------
# stage_hold_routing (V2/K2/M3)
# ---------------------------------------------------------------------------


def test_hold_routing_defaults_and_k3_init() -> None:
    rt = _runtime()
    cmds = _Commands(rt)
    routing = _hold_routing(rt, _wt(act_state=_State("heat", "ctx-foreign")), cmds)
    assert routing == _routing()
    assert cmds.ended == []


def test_hold_routing_detects_the_own_write_echo() -> None:
    rt = _runtime()
    rt.external.own_write_ctx_ids.append("ctx-own")
    cmds = _Commands(rt)
    routing = _hold_routing(rt, _wt(act_state=_State("heat", "ctx-own")), cmds)
    assert routing.own_change is True
    # No context at all (or a foreign one) is never our echo.
    assert _hold_routing(rt, _wt(act_state=_State("heat")), cmds).own_change is False
    assert _hold_routing(rt, _wt(act_state=None), cmds).own_change is False


def test_hold_routing_m3_escape_ends_the_off_hold() -> None:
    rt = _runtime()
    rt.user.mode_override = "off"
    cmds = _Commands(rt)
    routing = _hold_routing(rt, _wt(act_state=_State("heat", "ctx-foreign")), cmds)
    # The user switched the device back on at the device: resume, don't re-adopt.
    assert cmds.ended == ["user_resume"]
    assert routing.off_held is False
    assert routing.hold_resumed is True


def test_hold_routing_off_hold_keeps_the_one_tick_delay() -> None:
    rt = _runtime()
    cmds = _Commands(rt)
    # Device off / unknown / unavailable / absent: the hold stays routed to
    # the frost branch (off_held True) and nothing ends.
    for state in (_State("off"), _State("unknown"), _State("unavailable"), None):
        rt.user.mode_override = "off"
        routing = _hold_routing(rt, _wt(act_state=state), cmds)
        assert routing.off_held is True
        assert routing.hold_resumed is False
    assert cmds.ended == []


def test_hold_routing_own_echo_never_escapes_the_off_hold() -> None:
    rt = _runtime()
    rt.user.mode_override = "off"
    rt.external.own_write_ctx_ids.append("ctx-own")
    cmds = _Commands(rt)
    routing = _hold_routing(rt, _wt(act_state=_State("heat", "ctx-own")), cmds)
    assert cmds.ended == []
    assert routing.off_held is True
    assert routing.own_change is True


# ---------------------------------------------------------------------------
# stage_mode_adoption (K2/K3/M2/M3/I6)
# ---------------------------------------------------------------------------


def _seed_mode_baseline(rt: ZoneRuntime) -> None:
    rt.external.last_commanded_hvac = "heat"
    rt.external.last_hvac_cmd_ts = NOW - ECHO * 2
    rt.external.prev_device_mode = "heat"


def test_mode_adoption_adopts_a_foreign_device_mode() -> None:
    rt = _runtime()
    _seed_mode_baseline(rt)
    cmds = _Commands(rt)
    result = _mode_adoption(rt, cmds, wt=_wt(act_state=_State("cool")))
    assert result.mode_adopt_reason == "adopt"
    assert cmds.modes == ["cool"]
    # I6: the fresh hold pins the desired mode within the same tick.
    assert result.desired_hvac == "cool"


def test_mode_adoption_layer1_gates_in_chain_order() -> None:
    rt = _runtime()
    _seed_mode_baseline(rt)
    cmds = _Commands(rt)
    wt = _wt(act_state=_State("cool"))
    # opt_out wins over everything, then window > frozen > own > resumed.
    cases = [
        (
            {"adopt": False, "obs": _obs(window_open=True), "ing": _ing(frozen=True)},
            "opt_out",
        ),
        ({"obs": _obs(window_open=True), "ing": _ing(frozen=True)}, "safety_window"),
        ({"ing": _ing(frozen=True)}, "safety_frozen"),
        ({"routing": _routing(own_change=True, hold_resumed=True)}, "own_echo"),
        ({"routing": _routing(hold_resumed=True)}, "hold_resumed"),
    ]
    for over, expected in cases:
        result = _mode_adoption(rt, cmds, wt=wt, **over)  # type: ignore[arg-type]
        assert result.mode_adopt_reason == expected, expected
    assert cmds.modes == []  # none of the gated ticks adopted


def test_mode_adoption_m2_freeze_gate_positions() -> None:
    # Inside the echo window the move-guard reference is frozen; outside
    # (or with no command yet) it follows the device.  The freeze check runs
    # AFTER the observation (historical position): an in-window foreign mode
    # reads echo_window AND does not poison prev_device_mode.
    rt = _runtime()
    _seed_mode_baseline(rt)
    rt.external.last_hvac_cmd_ts = NOW - ECHO / 2  # window still open
    cmds = _Commands(rt)
    result = _mode_adoption(rt, cmds, wt=_wt(act_state=_State("cool")))
    assert result.mode_adopt_reason == "echo_window"
    assert rt.external.prev_device_mode == "heat"  # frozen, not "cool"
    rt.external.last_hvac_cmd_ts = NOW - ECHO * 2  # window elapsed
    rt.external.prev_device_mode = "cool"  # device settled on "cool" before
    result = _mode_adoption(rt, cmds, wt=_wt(act_state=_State("cool")))
    assert result.mode_adopt_reason == "stable_prev"  # unchanged mode: no action
    assert rt.external.prev_device_mode == "cool"  # reference follows again
    rt2 = _runtime()
    cmds2 = _Commands(rt2)
    _mode_adoption(rt2, cmds2, wt=_wt(act_state=_State("cool")))
    assert rt2.external.prev_device_mode == "cool"  # no command yet -> stamped


def test_mode_adoption_m3_realign_ends_the_hold() -> None:
    rt = _runtime()
    _seed_mode_baseline(rt)
    rt.user.mode_override = "cool"  # active mode-hold
    cmds = _Commands(rt)
    # The user selects the plan mode again at the device (device == desired).
    result = _mode_adoption(rt, cmds, wt=_wt(act_state=_State("heat")))
    assert result.mode_adopt_reason == "device_aligned"
    assert cmds.ended == ["user_resume"]
    assert result.desired_hvac == "heat"  # hold gone -> nothing pinned


def test_mode_adoption_i6_hold_pins_unless_safety() -> None:
    rt = _runtime()
    _seed_mode_baseline(rt)
    rt.external.prev_device_mode = "cool"  # settled: stable_prev, no re-adopt
    rt.user.mode_override = "cool"
    cmds = _Commands(rt)
    # A device still reporting the held mode: nothing to adopt or re-align,
    # the hold pins the desired mode.
    result = _mode_adoption(rt, cmds, wt=_wt(act_state=_State("cool")))
    assert result.desired_hvac == "cool"
    assert cmds.ended == []
    # Safety beats the hold this tick (I6): window-open unpins ...
    result = _mode_adoption(
        rt, cmds, wt=_wt(act_state=_State("cool")), obs=_obs(window_open=True)
    )
    assert result.desired_hvac == "heat"
    # ... and so does a frozen sensor.
    result = _mode_adoption(
        rt, cmds, wt=_wt(act_state=_State("cool")), ing=_ing(frozen=True)
    )
    assert result.desired_hvac == "heat"


# ---------------------------------------------------------------------------
# stage_setpoint_adopt (K3 surfacing, debounce log, prev-update)
# ---------------------------------------------------------------------------


def test_setpoint_adopt_returns_the_carried_reason_and_updates_prev() -> None:
    rt = _runtime()
    cmds = _Commands(rt)
    spo = _spo(actual_sp=21.3, sp_adopt_reason="command_echo")
    assert _adopt_stage(rt, cmds, spo) == "command_echo"
    assert rt.external.prev_device_sp == 21.3  # updated every tick
    assert cmds.overrides == []  # nothing adopted
    assert rt.dirty is False


def test_setpoint_adopt_debounces_the_suppression_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rt = _runtime()
    cmds = _Commands(rt)
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        _adopt_stage(rt, cmds, _spo(sp_adopt_reason="echo_window"))
        assert rt.user.last_adopt_log == "echo_window"
        _adopt_stage(rt, cmds, _spo(sp_adopt_reason="echo_window"))
    records = [r for r in caplog.records if "not adopted" in r.getMessage()]
    assert len(records) == 1  # debounced on the unchanged reason
    assert records[0].getMessage() == (
        "Poise climate.trv: device change not adopted (mode=- setpoint=echo_window)"
    )
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        _adopt_stage(rt, cmds, _spo(sp_adopt_reason="stable_offset"))
    records = [r for r in caplog.records if "not adopted" in r.getMessage()]
    assert len(records) == 2  # a NEW reason logs again
    assert rt.user.last_adopt_log == "stable_offset"


def test_setpoint_adopt_log_prefers_the_mode_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rt = _runtime()
    cmds = _Commands(rt)
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        _adopt_stage(
            rt, cmds, _spo(sp_adopt_reason="echo_window"), mode_reason="unsupported"
        )
    records = [r for r in caplog.records if "not adopted" in r.getMessage()]
    assert rt.user.last_adopt_log == "unsupported"  # mode channel first
    assert records[0].getMessage() == (
        "Poise climate.trv: device change not adopted "
        "(mode=unsupported setpoint=echo_window)"
    )


def test_setpoint_adopt_never_logs_the_adopt_or_empty_codes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rt = _runtime()
    cmds = _Commands(rt)
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        _adopt_stage(
            rt,
            cmds,
            _spo(actual_sp=22.4, adopted_sp=22.4, sp_adopt_reason="adopt"),
        )
        _adopt_stage(rt, cmds, _spo(sp_adopt_reason="device_aligned"))
        _adopt_stage(rt, cmds, _spo(sp_adopt_reason=""))
    assert [r for r in caplog.records if "not adopted" in r.getMessage()] == []
    assert rt.user.last_adopt_log == ""


# ---------------------------------------------------------------------------
# Channel vocabulary sync (both K3 channels speak only the enum)
# ---------------------------------------------------------------------------


def test_both_channel_vocabularies_are_covered_by_the_enum() -> None:
    values = {m.value for m in AdoptReason}
    # Layer-1 glue codes of both historical chains + the "" default.
    layer1 = {
        "",
        "opt_out",
        "safety_window",
        "safety_frozen",
        "own_echo",
        "hold_resumed",
        "schedule_active",
    }
    assert layer1 <= values
    # Every REACHABLE Layer-2 code of both pure reason functions, driven
    # through the scenario matrices (guard-order coverage).
    mode_seen = {mode_adopt_reason(**kw) for kw in _mode_scenarios()}
    assert mode_seen == {
        "adopt",
        "no_signal",
        "device_aligned",
        "unsupported",
        "own_command_echo",
        "no_baseline",
        "echo_window",
        "stable_prev",
    }
    sp_seen = {setpoint_adopt_reason(**kw) for kw in _sp_scenarios()}
    assert sp_seen == {
        "adopt",
        "no_baseline",
        "command_echo",
        "implausible_frost",
        "echo_window",
        "stable_offset",
    }
    assert (mode_seen | sp_seen) <= values
    # And the enum carries nothing beyond the two channels' union.
    assert values == layer1 | mode_seen | sp_seen
