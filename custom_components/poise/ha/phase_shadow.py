"""The await-free SHADOW phase of the tick (plan step O.5).

The six independent diagnostics-only shadow segments (cover, MPC, TPI, PI,
compressor lifecycle, multi-source arbitration) plus the valve-health stage.
The setpoint is already written when these run: a failure in any predictive
shadow must never take control reporting offline, so each segment owns its own
error boundary (ADR-0065) and degrades to the neutral seed the sequencer built.

WHY THIS MODULE EXISTS AS ITS OWN FILE.  The split follows the AWAIT TOPOLOGY.
Everything here is await-free and nothing here may write: the structure gate
pins 0 ``await`` expressions and no ``ActuatorExecutor`` in this module, and
the ``ShadowPorts`` view is so narrow (one read-only property) that this class
cannot even TYPE a ``commit_execution`` call.

Receiver rules (binding, unchanged from the monolith): collaborators are the
injected ``self._runtime`` / ``self._reader``, the one coordinator read goes
through ``self._ports.mpc_params``, and the logger is the injected
``self._log`` (channel ``custom_components.poise.coordinator`` is behaviour).
Per-tick data travels as an ARGUMENT (``bindings``) or inside the frozen
``FinalizeContext``, never as a field.

PATCH SURFACE (binding, plan O.4/O.5).  **Patch where the name is looked up,
not where it is defined.**  One of the nine owner-module fault-injection
points is called here -- ``control.cover_shading.predict_peak_operative``,
reached as ``cover_shading.predict_peak_operative(...)`` so the lookup happens
at CALL time on the OWNER; that target did not move with this step.  Four
patch targets DID move here, all plain from-imports and therefore patched
where they are bound (``…poise.ha.phase_shadow.<name>``):
``evaluate_shadow``, ``evaluate_tpi_shadow``, ``evaluate_pi_shadow`` and
``evaluate_multi_shadow``.  ``tests/integration/test_phase10_shadow_segments.py``
proves per segment that those patches still bite.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from ..const import TICK_INTERVAL_S
from ..control import cover_shading
from ..control.cover_shading import shading_target_position
from ..control.mpc_shadow import evaluate_shadow
from ..control.pi_shadow import evaluate_pi_shadow
from ..control.tpi_shadow import evaluate_tpi_shadow
from ..diagnostics.shadows import (
    arbitration_shadow_objs,
    evaluate_cover_shadow,
    evaluate_multi_shadow,
    lifecycle_shadow_objs,
    mpc_shadow_objs,
    pi_shadow_objs,
    tpi_shadow_objs,
)
from ..multi import lifecycle as _lifecycle
from ..multi.model import DeviceHealth, Direction
from ..multi.shadow import evaluate_thermal_shadow
from ..runtime.tick_result import (
    FinalizeContext,
    HealthUpdate,
    LifecycleFoldResult,
    ShadowStageResult,
    ValveHealthResult,
)
from ..runtime.zone_runtime import ZoneRuntime
from ..safety.sensor_watchdog import valve_stuck
from .input_reader import InputReader
from .tick_snapshot import ZoneBindings

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    from .tick_ports import ShadowPorts


# Comfort mode -> thermal-arbitration direction (ADR-0046 P1 shadow). "idle" and
# any other value map to None (no thermal demand).
_THERMAL_DIR: dict[str, Direction] = {"heat": Direction.HEAT, "cool": Direction.COOL}


class ShadowPhase:
    """The six shadow segments and the valve-health stage.

    Built by the composition root (``coordinator.py``) and driven by the
    sequencer's ``finalize_tick``, which seeds the neutral result each segment
    overwrites its own fragment of.  The two collaborators are injected ONCE so
    the segment bodies keep their expressions verbatim -- that literalness is
    the equivalence proof of the O.5 move.
    """

    __slots__ = ("_log", "_ports", "_reader", "_runtime")

    def __init__(
        self,
        *,
        runtime: ZoneRuntime,
        reader: InputReader,
        ports: ShadowPorts,
        logger: logging.Logger,
    ) -> None:
        self._runtime = runtime
        self._reader = reader
        self._ports = ports
        self._log = logger

    def _stage_shadow_domain(
        self, ctx: FinalizeContext, neutral: ShadowStageResult, bindings: ZoneBindings
    ) -> ShadowStageResult:
        """The finalize shadows as SIX INDEPENDENT segments (ADR-0065),
        pinned by test_phase0_fault_shadow_domain.

        Order: peak forecast → MPC → TPI → PI(+acc) → lifecycle fold →
        thermal arbitration → ``shadow_objs``. Each step owns its own
        boundary and contributes its own ``shadow_objs`` fragment on top of
        the neutral seed, so a failing segment costs exactly its own keys —
        ``tpi_duty`` (and with it ``heat_demand``), the lifecycle fold and
        the ``_pi.acc`` advance included.

        The execution ORDER is unchanged, and so is every side effect and its
        position. The ONE surviving cross-segment dependency is data-borne,
        not error-domain coupling: the thermal arbitration consumes the folded
        lifecycle's ``DeviceRuntime``, so it is skipped when the fold itself
        failed — never when an earlier shadow did.
        """
        objs: dict[str, Any] = dict(neutral.shadow_objs)
        cover_peak, cover_pos, cover_reason, binding = self._shadow_cover(ctx, neutral)
        objs.update(self._shadow_mpc(ctx))
        objs.update(self._shadow_tpi(ctx))
        objs.update(self._shadow_pi(ctx))
        fold = self._shadow_lifecycle(ctx)
        if fold is not None:
            objs.update(fold.objs)
            objs.update(self._shadow_arbitration(ctx, fold, bindings))
        return ShadowStageResult(
            operative=neutral.operative,
            binding=binding,
            cover_peak=cover_peak,
            cover_pos=cover_pos,
            cover_reason=cover_reason,
            shadow_objs=objs,
        )

    def _shadow_failed(self, segment: str) -> None:
        """One shadow segment failed. The wording ``shadow evaluation failed``
        is load-bearing (user log filters key on it); the segment name says
        which fragment degraded."""
        self._log.exception(
            "Poise: shadow evaluation failed (%s); the written setpoint stands, "
            "diagnostics degraded this tick",
            segment,
        )

    def _shadow_cover(
        self, ctx: FinalizeContext, neutral: ShadowStageResult
    ) -> tuple[float, float, str, str]:
        """Predictive solar-shading shadow (ADR-0043) + binding classification.

        Returns ``(peak, position, reason, binding)`` — the neutral seed's
        values on failure. Composition in ``diagnostics/shadows.py``; the two
        kernels are passed as ``*_fn``. ``predict_peak_operative`` is read off
        ``control.cover_shading`` at call time, so patching
        ``control.cover_shading.predict_peak_operative``
        (test_phase0_fault_shadow_domain) keeps hitting the dispatch;
        ``shading_target_position`` is a plain import (never patched).
        """
        try:
            peak, pos, reason, binding = evaluate_cover_shadow(
                operative=neutral.operative,
                t_out_eff=ctx.t_out_eff,
                q_solar=ctx.q_solar,
                cool_sp=ctx.decision.cool_sp,
                heat_sp=ctx.decision.heat_sp,
                mold_min=ctx.mold_min,
                model=self._runtime.learning.ekf.get_model(),
                identified=self._runtime.learning.ekf.identified,
                temperature_std=self._runtime.learning.ekf.temperature_std,
                predict_peak_operative_fn=cover_shading.predict_peak_operative,
                shading_target_position_fn=shading_target_position,
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("cover")
            return (
                neutral.cover_peak,
                neutral.cover_pos,
                neutral.cover_reason,
                neutral.binding,
            )
        return peak, pos, reason, binding

    def _shadow_mpc(self, ctx: FinalizeContext) -> dict[str, Any]:
        """Shadow MPC (ADR-0033): what the predictive controller *would*
        command against the live EKF state; reported only, dormant until
        identified."""
        try:
            return mpc_shadow_objs(
                evaluate_shadow(
                    identified=self._runtime.learning.ekf.identified,
                    t_air=ctx.room,
                    t_out=ctx.t_out_eff,
                    t_rm=ctx.t_rm_eff,
                    tau_hours=self._runtime.learning.ekf.tau_hours,
                    model=self._runtime.learning.ekf.get_model(),
                    prediction_std=self._runtime.learning.ekf.temperature_std,
                    confidence=self._runtime.learning.ekf.confidence,
                    target=ctx.decision.heat_sp,
                    lower=ctx.decision.heat_sp,
                    upper=ctx.decision.cool_sp,
                    params=self._ports.mpc_params,
                )
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("mpc")
            return {}

    def _shadow_tpi(self, ctx: FinalizeContext) -> dict[str, Any]:
        """Shadow direct-valve TPI duty (ADR-0036): computed + reported only.

        F-TPI: its own boundary, so ``tpi_duty`` — and with it the published
        ``heat_demand`` (the live duty while it exists) — survives a failure
        in any other shadow.
        """
        try:
            return tpi_shadow_objs(
                evaluate_tpi_shadow(
                    valve_available=self._reader.valve_entity is not None,
                    model=self._runtime.learning.ekf.get_model(),
                    # Shadow honesty: regulate toward the WRITE path's resolved
                    # target (incl. band/frost/mould clamps), not the raw
                    # corridor edge — a live TPI would have to honour it
                    # exactly like the setpoint write does, and ``heat_demand``
                    # (hub boiler demand, R13) is fed from this duty. "manual"
                    # is the override mode (tick_resolve); a below-room manual
                    # target is directionally safe (heating duty clamps to 0).
                    target=(
                        ctx.target
                        if ctx.mode in ("heat", "manual")
                        else ctx.decision.heat_sp
                    ),
                    room=ctx.room,
                    t_out=ctx.t_out_eff,
                )
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("tpi")
            return {}

    def _shadow_pi(self, ctx: FinalizeContext) -> dict[str, Any]:
        """PI-compensated setpoint shadow (ADR-0037): setpoint-only devices.

        F-PIACC: the integrator advance is the segment's own side effect
        behind its own boundary — only a failure of the PI evaluation itself
        freezes ``acc``.
        """
        try:
            pi = evaluate_pi_shadow(
                self._runtime.learning.pi,
                applies=self._reader.valve_entity is None,
                # Same shadow-honesty rule as the TPI branch above: the write
                # path's resolved target ("manual" = override mode, incl.
                # clamps), not the raw corridor edge.
                target=(
                    ctx.target
                    if ctx.mode in ("heat", "manual")
                    else ctx.decision.heat_sp
                ),
                room=ctx.room,
                external=ctx.t_out_eff,  # real outdoor temp
                dt_h=TICK_INTERVAL_S / 3600.0,
            )
            # The shadow is pure — advance the persisted integrator here,
            # exactly once per tick, instead of as a hidden side effect of the
            # read.
            if pi.next_acc is not None:
                self._runtime.learning.pi.acc = pi.next_acc
            return pi_shadow_objs(pi)
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("pi")
            return {}

    def _shadow_lifecycle(self, ctx: FinalizeContext) -> LifecycleFoldResult | None:
        """Compressor-lifecycle fold + its gate diagnostics (ADR-0046 §8).

        F-LIFECYCLE: the fold is LIVE state — it feeds the next tick's
        compressor guard — and runs behind its own boundary, independent of
        every diagnostic shadow before it. ``None`` means the fold itself failed: the
        pre-tick lifecycle survives, the two ``compressor_gate_*`` keys stay
        absent and the arbitration segment (which needs this runtime) is
        skipped.
        """
        act_state, final_mode = ctx.act_state, ctx.final_mode
        try:
            _act_avail = act_state is not None and act_state.state not in (
                "unavailable",
                "unknown",
            )
            # Fold the actuator's run-state into the per-device lifecycle on a
            # wall-clock basis, then derive the resolver's min-off / health gate.
            now_wall = dt_util.utcnow().timestamp()
            _act_action = act_state.attributes.get("hvac_action") if act_state else None
            # INVARIANT (K2b, ADR-0046 §9): lifecycle observe() runs after
            # guard diagnosis; the pre-observe gate mirrors the write-path
            # guard. Pinned by test_dry_nudge_when_humid_and_idle. Folding
            # observe first would let the guard judge against its own intent
            # and self-armed mode hold.
            # ADR-0046 §8 compressor protection (LIVE): the same decision the
            # write path above already applied (_guard_block), surfaced here
            # as a diagnostic; the display policy uses the effective timers so
            # the remaining-time attributes match the live gate.
            _comp_pol = ctx.guard_pol or _lifecycle.LifecyclePolicy(
                min_off_s=ctx.g_min_off, min_mode_hold_s=ctx.g_mode_hold
            )
            # Fix the conditioning signal: an AC that reports no hvac_action (many
            # ESPHome/IR bridges) would otherwise read as permanently off and never
            # accrue a min-off lock. Fall back to Poise's intended mode (ADR-0024
            # cool-drive parity).
            self._runtime.compressor.multi_lifecycle = _lifecycle.observe(
                self._runtime.compressor.multi_lifecycle,
                conditioning=_lifecycle.compressor_running(_act_action, final_mode),
                mode=act_state.state if (act_state and _act_avail) else None,
                now=now_wall,
                health=(
                    DeviceHealth.OK.value
                    if _act_avail
                    else DeviceHealth.UNAVAILABLE.value
                ),
            )
            _multi_policy = _lifecycle.LifecyclePolicy()
            objs = lifecycle_shadow_objs(
                lifecycle=self._runtime.compressor.multi_lifecycle,
                now_wall=now_wall,
                multi_policy=_multi_policy,
                comp_pol=_comp_pol,
                comp_block=ctx.guard_block,
                min_off_remaining_fn=_lifecycle.min_off_remaining,
                mode_hold_remaining_fn=_lifecycle.mode_hold_remaining,
            )
            runtime = _lifecycle.to_runtime(
                self._runtime.compressor.multi_lifecycle, now_wall, _multi_policy
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("lifecycle")
            return None
        return LifecycleFoldResult(runtime=runtime, objs=objs)

    def _shadow_arbitration(
        self, ctx: FinalizeContext, fold: LifecycleFoldResult, bindings: ZoneBindings
    ) -> dict[str, Any]:
        """Phase-1/2 thermal-arbitration shadow (ADR-0046): transient
        ZoneDevice over the freshly folded lifecycle runtime.

        EntitySnapshot/ThermalDemand construction lives in
        ``diagnostics/shadows.py``; ``evaluate_thermal_shadow`` is a plain
        import since O.4 — no test ever patched it.
        """
        act_state = ctx.act_state
        try:
            return arbitration_shadow_objs(
                evaluate_multi_shadow(
                    entity_id=bindings.actuator,
                    hvac_modes=(
                        (act_state.attributes.get("hvac_modes") or [])
                        if act_state
                        else []
                    ),
                    available=act_state is not None
                    and act_state.state not in ("unavailable", "unknown"),
                    direction=_THERMAL_DIR.get(ctx.decision.mode),
                    target=ctx.decision.target,
                    runtime=fold.runtime,
                    evaluate_thermal_shadow_fn=evaluate_thermal_shadow,
                )
            )
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._shadow_failed("arbitration")
            return {}

    def _stage_valve_health(self, bindings: ZoneBindings) -> ValveHealthResult:
        """Valve-stuck detection over a fresh read of the calibration
        counts. Returns the finalize segment's only ``HealthUpdate`` for the
        caller's immediate emission."""
        # valve health: a near-zero closing-step count means the motorised
        # valve failed calibration / is jammed — advisory diagnostic + repair
        # issue.
        closing_steps, idle_steps = self._reader.valve_steps()
        v_stuck = valve_stuck(closing_steps)
        valve_health = (
            "stuck" if v_stuck else ("ok" if closing_steps is not None else "unknown")
        )
        return ValveHealthResult(
            closing_steps=closing_steps,
            idle_steps=idle_steps,
            valve_health=valve_health,
            health_updates=(
                HealthUpdate(
                    issue_id=f"valve_stuck_{bindings.entry_id}",
                    active=v_stuck,
                    translation_key="valve_stuck",
                    placeholders={"entity": self._reader.valve_closing_steps or "—"},
                ),
            ),
        )
