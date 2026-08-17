"""Pure assembly of the prepare->finalize contract.

One function, and it sits on a real SEQUENCER seam rather than inside a
phase: ``TickOrchestrator._build_finalize_context`` calls it from
``resume_prepare`` — before ``finalize_tick`` and before the savepoint await —
so the ``FinalizeContext`` carrier crosses the seam already complete.  That is
why this is its own module and not a corner of the report phase.

The assembly is pure construction from the typed stage results: no state
reads, no I/O, no logging, no error boundary.
``ZoneRuntime.build_finalize_context`` delegates here 1:1.

This module is hass-free (mypy --strict, py310-clean): the one HA type that
flows through (``State``, the tick's central positioned actuator read carried
by ``WriteTargetResult.act_state``) is imported under ``TYPE_CHECKING`` only.

Split out of ``control/tick_pipeline.py`` by plan P.1; the prepare and
actuation stages live in ``control/pipeline_prepare.py`` and
``control/pipeline_actuate.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..runtime.tick_result import (
    FinalizeContext,
    IntentsResult,
    ModeResolutionResult,
)

if TYPE_CHECKING:
    from ..comfort.dual_setpoint import ComfortDecision
    from ..runtime.tick_result import (
        ClimateBandResult,
        OperativeResult,
        PreparedState,
        SchedulePresenceResult,
        WriteTargetResult,
    )

# ---------------------------------------------------------------------------
# Finalize-context assembly
# ---------------------------------------------------------------------------


def build_finalize_context(
    *,
    state: PreparedState,
    sp: SchedulePresenceResult,
    op: OperativeResult,
    decision: ComfortDecision,
    wt: WriteTargetResult,
    band: ClimateBandResult,
    intents: IntentsResult,
    failed: bool,
    res: ModeResolutionResult,
    guard_block: str | None,
    mode_nudge_blocked: str,
    mode_adopt_reason: str,
    sp_adopt_reason: str,
) -> FinalizeContext:
    """Assemble the prepare->finalize contract from the typed stage results.

    Pure construction -- no state reads, no I/O, no logging -- so building it
    before the savepoint await is unobservable; the field set is pinned by
    test_phase1_tick_result.
    """
    ing = state.ingest
    obs = state.observation
    floors = state.floors
    return FinalizeContext(
        # Plan O.2: the tick's config view travels with the carrier that
        # already crossed the forecast seam -- no second parameter, no
        # coordinator read inside the finalize stages.
        config=state.config,
        now=ing.now,
        room=ing.room,
        room_decide=op.room_decide,
        reading_source=ing.reading.source,
        rh=ing.rh,
        dewpoint=floors.dewpoint,
        mold_min=floors.mold_min,
        mold_capped=floors.mold_capped,
        t_out_eff=ing.t_out_eff,
        t_rm_eff=ing.t_rm_eff,
        t_rm_source=ing.t_rm_source,
        q_solar=ing.q_solar,
        q_solar_source=ing.q_solar_source,
        q_solar_internal=ing.q_solar_internal,
        t_mrt=ing.t_mrt,
        mrt_source=ing.mrt_source,
        mrt_internal=ing.mrt_internal,
        sched=state.sched,
        frozen=ing.frozen,
        window_open=obs.window_open,
        # ADR-0055 CA fairness mask inputs (capability-aware scoring).
        can_heat=obs.can_heat,
        can_cool=obs.can_cool,
        decision=decision,
        eff_cool=wt.eff_cool,
        mode=wt.mode,
        target=wt.target,
        final_mode=res.final_mode,
        norm_binding=wt.norm_binding,
        binding_precedence=wt.binding_precedence,
        override_clamped=wt.override_clamped,
        heating=intents.heating,
        cooling=intents.cooling,
        failed=failed,
        adaptive_cool=obs.adaptive_cool,
        preheating=sp.preheating,
        preheat_outdoor=sp.preheat_outdoor,
        coasting=sp.coasting,
        act_state=wt.act_state,
        guard_pol=res.guard_pol,
        g_min_off=res.g_min_off,
        g_mode_hold=res.g_mode_hold,
        guard_block=guard_block,
        mode_nudge_blocked=mode_nudge_blocked,
        idle_park_mode=wt.idle_park_mode,
        mode_adopt_reason=mode_adopt_reason,
        sp_adopt_reason=sp_adopt_reason,
        climate_diag=band.climate_diag,
        sched_active=ing.sched_active,
        fault_active=ing.fault_active,
        heat_source_suspect=ing.heat_source_suspect,
        ext_num=op.ext_num,
        operative_active=op.operative_active,
        occupancy=sp.presence.occupancy,
    )
