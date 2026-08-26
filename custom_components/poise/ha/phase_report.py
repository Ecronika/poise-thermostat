"""The await-free REPORT phase of the tick (plan step O.5).

Two assembly stages: the outcome/HDH/RegQ/reference-offset/tau-settle folds
behind ONE collector boundary (``_stage_outcome_diag``), and the ``_tick_data``
payload assembly plus ``heat_demand`` (``_stage_assemble_tick_data``).

WHY THIS MODULE EXISTS AS ITS OWN FILE.  The split follows the AWAIT TOPOLOGY:
both stages are await-free and neither may write, so the structure gate pins 0
``await`` expressions and no ``ActuatorExecutor`` here.

TWO SIZE FACTS, both deliberate (plan O.6).  ``_stage_outcome_diag`` keeps its
state folds inside ONE ``safe_collect`` closure -- the effect of a failure in
fold N (defaults stand, folds N+1.. are skipped) is behaviour, so the boundary
does not move.  O.6 split the folds into the six ``_fold_*`` methods, called
from INSIDE that unchanged closure in unchanged text order (the plan said
"five"; measured, the closure holds six separable folds -- see
``_fold_tier2_inputs``).  ``_stage_assemble_tick_data`` is the named, numbered
permanent size exception: the big dict literal is the verbatim evidence of the
aliasing contract (``coordinator.data`` is object-identical with the traced
payload), and merging partial dicts with ``**`` would risk the key order the
trace golden replay depends on.

Receiver rules (binding, unchanged from the monolith): collaborators are the
injected ``self._runtime`` / ``self._reader`` / ``self._diag`` (the ONE broad
diagnostics boundary), the three suggestion-issue effects go through
``self._ports`` (a ``ReportPorts`` view), and the logger is the injected
``self._log`` (channel ``custom_components.poise.coordinator`` is behaviour).
Per-tick data travels inside the frozen ``FinalizeContext`` and the stage
results, never as a field.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from ..adaptive_cool import adaptive_cool_mode
from ..comfort.pmv import PMV_MODEL_REV, pmv_setpoint_offset
from ..comfort.readiness import pmv_control_ready, presence_control_ready, room_present
from ..const import TICK_INTERVAL_S
from ..control.comfort_activation import (
    DWELL_TARGET_MIN,
    ComfortActivation,
    activation_signature,
    cascade_after_invalidation,
    latch_dwelt,
    may_dwell,
    step_tier,
)
from ..control.dynamics import PROFILES
from ..control.feedback import clo_suggestion_reason, detect_feedback_pattern
from ..control.hub_aggregate import zone_heat_demand
from ..control.outcome_scoring import observe_session
from ..control.reference_offset import update_offset
from ..control.regulation_quality import (
    FLIP_TIER_COMFORT,
    ca_tick_scorable,
    flip_metric_ok,
)
from ..control.scoring_expectation import model_expected_minutes
from ..control.suggestion import (
    detect_override_pattern,
    resolve_suggestion_conflict,
    season_gate_floor,
    season_hint_t_rm,
    season_mode_hint,
    suggestion_suppressed,
)
from ..diagnostics.collector import DiagnosticsCollector
from ..diagnostics.shadows import build_outcome_diag, capped_elapsed_min
from ..estimation.tau_settle import update_settle
from ..ingestion import parse_finite
from ..runtime.tick_result import FinalizeContext, ShadowStageResult, ValveHealthResult
from ..runtime.zone_runtime import ZoneRuntime
from .input_reader import CalibrationMeta, InputReader
from .presenter import iso_utc as _iso_utc

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    from .tick_ports import ReportPorts


class ReportPhase:
    """The two await-free assembly stages of the finalize half.

    Built by the composition root (``coordinator.py``) and driven by the
    sequencer's ``finalize_tick``.  The three collaborators are injected ONCE
    so the stage bodies keep their expressions verbatim -- that literalness is
    the equivalence proof of the O.5 move.
    """

    __slots__ = ("_diag", "_log", "_ports", "_reader", "_runtime")

    def __init__(
        self,
        *,
        runtime: ZoneRuntime,
        reader: InputReader,
        diag: DiagnosticsCollector,
        ports: ReportPorts,
        logger: logging.Logger,
    ) -> None:
        self._runtime = runtime
        self._reader = reader
        self._diag = diag
        self._ports = ports
        self._log = logger

    def _stage_outcome_diag(self, ctx: FinalizeContext) -> dict[str, Any]:
        """ADR-0044/0045 outcome scoring + savings diagnostics behind the ONE
        collector boundary (``DiagnosticsCollector.safe_collect``). The
        returned mapping IS this stage's typed cross-stage value:
        ``safe_collect``'s replace-on-success dict — the full collected key
        set, or the defaults below on failure (the second observable
        key-shrink mechanism); a wrapper dataclass would only re-wrap the
        collector contract's own typed return.

        Plan O.6: the state folds are the ``_fold_*`` methods below, called
        from INSIDE this very closure in unchanged text order — the boundary
        did NOT travel with them. ``tests/integration/test_o6_outcome_
        folds.py`` injects a fault into each fold and pins the resulting
        degradation; it is green against the pre-split code too."""
        # Plan O.2: policy values come from this local, not the coordinator
        # backreference; only the two the ASSEMBLY needs stay in this frame.
        config, eff_cool = ctx.config, ctx.eff_cool
        # ADR-0044 outcome scoring + ADR-0045 efficiency report (diagnostic only;
        # never raises — a scoring slip must not break the control tick).
        outcome_diag: dict[str, Any] = {
            "outcome_last_score": None,
            "outcome_ts_avg": None,
            "outcome_obs_avg": None,
            "outcome_n": 0,
            "savings_kwh_month": 0.0,
            "savings_eur_month": 0.0,
            "savings_pct": 0.0,
        }

        # The boundary itself is ``DiagnosticsCollector.safe_collect`` — the
        # closure below runs the state folds + assembly in text order INSIDE
        # that one try, so an exception in fold N leaves ``outcome_diag`` on
        # the defaults, skips folds N+1… and freezes the metrics until the
        # next healthy tick (the open F-OUTFOLD would change that). The LIVE
        # reads (``user.enabled``, ``user.override``, ``dt_util.now()``) keep
        # their in-boundary positions INSIDE the folds, as does the per-fold
        # ``ctx`` unpacking — frozen-dataclass reads that cannot raise.
        def _collect_outcome_diag() -> dict[str, Any]:
            _tick_min = TICK_INTERVAL_S / 60.0
            self._fold_hdh_and_outcome(ctx, tick_min=_tick_min)
            self._fold_regulation_quality(ctx, tick_min=_tick_min)
            _pmv_ready = self._fold_tier2_activation(ctx, tick_min=_tick_min)
            self._fold_tier2_inputs(ctx, pmv_ready=_pmv_ready)
            _ref_conditioning = self._fold_reference_offset(ctx, tick_min=_tick_min)
            self._fold_tau_settle(
                ctx, tick_min=_tick_min, conditioning=_ref_conditioning
            )
            return build_outcome_diag(
                outcome_stats=self._runtime.diagnostics.outcome_stats,
                hdh=self._runtime.diagnostics.hdh,
                hdh_cfg=config.hdh_cfg,
                regq=self._runtime.diagnostics.regq,
                ref_offset=self._runtime.learning.ref_offset,
                ref_conditioning=_ref_conditioning,
                tau_settle=self._runtime.learning.tau_settle,
                eff_cool=eff_cool,
            )

        return self._diag.safe_collect(_collect_outcome_diag, outcome_diag)

    def _fold_hdh_and_outcome(self, ctx: FinalizeContext, *, tick_min: float) -> None:
        """Fold 1: HDH savings estimate + the ADR-0044 outcome session/stats.

        ONE fold, not two, because both book the same ``_hdh_dt``: the
        session's heating-time integral and the savings estimate have to
        credit the same minutes or the two figures drift apart.
        """
        now, room, heating = ctx.now, ctx.room, ctx.heating
        decision, t_out_eff, q_solar = ctx.decision, ctx.t_out_eff, ctx.q_solar
        sched, config = ctx.sched, ctx.config
        # Real elapsed dt (event-driven refreshes book < 60 s, not a flat
        # tick -- same reasoning as the CA/offset dt below), capped so a
        # masked gap adds ~2 ticks instead of silently over/under-crediting
        # the HDH savings estimate and the outcome-session heating-time
        # integral.
        _hdh_dt = capped_elapsed_min(
            self._runtime.diagnostics.hdh_last_mono, now, tick_min
        )
        self._runtime.diagnostics.hdh_last_mono = now
        self._runtime.diagnostics.hdh = self._runtime.diagnostics.hdh.observe(
            comfort=config.comfort_base,
            setpoint=decision.heat_sp,
            outdoor=t_out_eff,
            dt_min=_hdh_dt,
            now_month=dt_util.now().month,
            cfg=config.hdh_cfg,
        )
        self._runtime.diagnostics.outcome_session, _fin = observe_session(
            self._runtime.diagnostics.outcome_session,
            temp=room,
            target=decision.heat_sp,
            heating=heating,
            controlling=self._runtime.user.enabled,
            dt_min=_hdh_dt,
            expected_minutes=model_expected_minutes(
                self._runtime.learning.ekf.get_model()
                if self._runtime.learning.ekf.identified
                else None,
                room=room,
                target=decision.heat_sp,
                t_out=t_out_eff,
                q_solar=q_solar,
                # P2.1: ``None`` = no upcoming comfort start; always-comfort
                # previously yielded 0 here, so 0.0 is the fixed,
                # regression-free fallback (plan §0.6 p.3).
                fallback=float(sched.minutes_to_comfort or 0.0),
            ),
            q_solar=q_solar,
            outdoor=t_out_eff,
        )
        if _fin is not None:
            self._runtime.diagnostics.outcome_stats = (
                self._runtime.diagnostics.outcome_stats.observe(
                    _fin.score, _fin.controller
                )
            )

    def _fold_regulation_quality(
        self, ctx: FinalizeContext, *, tick_min: float
    ) -> None:
        """Fold 2: the ADR-0055 regulation-quality metric — the CA half and
        the time-weighted PPD half, which both write ``diagnostics.regq``
        and are therefore one fold, each with its own elapsed anchor.
        """
        now, room_decide, decision = ctx.now, ctx.room_decide, ctx.decision
        eff_cool, mode = ctx.eff_cool, ctx.mode
        window_open, frozen, sched = ctx.window_open, ctx.frozen, ctx.sched
        # ADR-0055 regulation-quality metric (EN 15500-1 CA): score only
        # unmasked comfort ticks (room_decide vs the effective band).
        # Field calibration 2026-08-08: additionally mask violations the
        # zone structurally cannot actuate against (heat-only zone above
        # the cool edge in a hot spell measures the weather, not the
        # controller) — ``ca_tick_scorable``, capability fairness.
        if (
            self._runtime.user.enabled
            and not window_open
            and not frozen
            and self._runtime.user.override is None
            and sched.is_comfort
            and ca_tick_scorable(
                room=room_decide,
                heat_sp=decision.heat_sp,
                cool_sp=eff_cool,
                can_heat=ctx.can_heat,
                can_cool=ctx.can_cool,
            )
        ):
            # Real elapsed (event-driven refreshes book < 60 s, not a flat
            # tick), capped so a masked gap adds ~2 ticks.
            _ca_dt = capped_elapsed_min(
                self._runtime.diagnostics.ca_last_mono, now, tick_min
            )
            self._runtime.diagnostics.ca_last_mono = now
            self._runtime.diagnostics.regq = self._runtime.diagnostics.regq.observe(
                room=room_decide,
                heat_sp=decision.heat_sp,
                cool_sp=eff_cool,
                mode=mode,
                dt_min=_ca_dt,
            )
        # ADR-0055 N1: time-weighted PPD — the comfort-flip gate
        # component. Same fairness mask as the CA fold above, additionally
        # gated on a VALID PMV (ISO 7730 domain, ADR-0054 V3); own elapsed
        # anchor because PMV validity and the CA mask diverge.
        _ppd_val = ctx.climate_diag.get("ppd")
        if (
            self._runtime.user.enabled
            and not window_open
            and not frozen
            and self._runtime.user.override is None
            and sched.is_comfort
            and ctx.climate_diag.get("pmv_valid") is True
            and isinstance(_ppd_val, (int, float))
        ):
            _ppd_dt = capped_elapsed_min(
                self._runtime.diagnostics.ppd_last_mono, now, tick_min
            )
            self._runtime.diagnostics.ppd_last_mono = now
            self._runtime.diagnostics.regq = self._runtime.diagnostics.regq.observe_ppd(
                ppd=float(_ppd_val), dt_min=_ppd_dt
            )

    def _fold_tier2_activation(self, ctx: FinalizeContext, *, tick_min: float) -> bool:
        """Fold 3: ADR-0069 U7/U8 tier-2 activation stepping (persisted
        latch). Returns ``_pmv_ready``, the one value fold 4 cannot re-derive
        from the state this fold writes.
        """
        now, config = ctx.now, ctx.config
        # ADR-0069 U7/U8: tier-2 activation stepping (persisted latch) +
        # the NEXT-tick solver inputs. Runs after the PPD fold so the
        # entry gate reads this tick's matured figures; the solver reads
        # the previous tick's latch (persisted state, never a per-tick
        # predicate) — same semantics as cool_sp_eff_prev.
        _t2_dt = capped_elapsed_min(
            self._runtime.diagnostics.tier2_last_mono, now, tick_min
        )
        self._runtime.diagnostics.tier2_last_mono = now
        _ca0 = self._runtime.diagnostics.comfort_activation
        _t2_identified = self._runtime.learning.ekf.identified
        _t2_entry = flip_metric_ok(
            FLIP_TIER_COMFORT,
            self._runtime.diagnostics.regq,
            identified=_t2_identified,
        )
        _t2_ppd = self._runtime.diagnostics.regq.ppd
        _pmv_ready = pmv_control_ready(
            rh=ctx.rh, pmv_valid=ctx.climate_diag.get("pmv_valid") is True
        )
        _pred_impossible = (
            ctx.climate_diag.get("fan_circ_reason") == "no_fan_capability"
        )
        _t2_gen = _ca0.generation
        _fan_next = step_tier(
            _ca0.fan_ce,
            ready=config.active_comfort,
            entry_ok=_t2_entry,
            ppd=_t2_ppd,
            signature=activation_signature(
                room_profile=config.room_profile,
                clo_offset=config.clo_offset,
                model_rev=PMV_MODEL_REV,
                predecessors=(),
            ),
            dt_min=_t2_dt,
            allowed=may_dwell(_ca0, "fan_ce", predecessor_impossible=_pred_impossible),
            next_generation=_t2_gen + 1,
            # P1 field finding: a fan-less zone retires fan_ce to shadow
            # (also a STALE persisted eligible), so the serialization's
            # deadlock escape actually reaches pmv_offset.
            impossible=_pred_impossible,
        )
        if _fan_next.state == "live" and _ca0.fan_ce.state != "live":
            _t2_gen += 1
        _ca1 = ComfortActivation(
            fan_ce=_fan_next, pmv_offset=_ca0.pmv_offset, generation=_t2_gen
        )
        if _ca0.fan_ce.state == "live" and _fan_next.state != "live":
            # The ADR-0069 cascade: dependents re-baseline.
            _ca1 = cascade_after_invalidation(
                _ca1, invalidated_generation=_ca0.fan_ce.generation
            )
        _pmv_next = step_tier(
            _ca1.pmv_offset,
            ready=config.active_comfort and _pmv_ready,
            entry_ok=_t2_entry,
            ppd=_t2_ppd,
            signature=activation_signature(
                room_profile=config.room_profile,
                clo_offset=config.clo_offset,
                model_rev=PMV_MODEL_REV,
                predecessors=(("fan_ce",) if _ca1.fan_ce.state == "live" else ()),
            ),
            dt_min=_t2_dt,
            allowed=may_dwell(
                _ca1, "pmv_offset", predecessor_impossible=_pred_impossible
            ),
            next_generation=_t2_gen + 1,
        )
        if _pmv_next.state == "live" and _ca1.pmv_offset.state != "live":
            _t2_gen += 1
        self._runtime.diagnostics.comfort_activation = ComfortActivation(
            fan_ce=_ca1.fan_ce, pmv_offset=_pmv_next, generation=_t2_gen
        )
        # ADR-0069 N1: maturing-progress flag for the card — which latch
        # grew qualified dwell THIS tick ("" = paused/none). Serialization
        # guarantees at most one dwelling feature.
        self._runtime.diagnostics.tier2_dwelling = (
            "fan_ce"
            if latch_dwelt(_ca0.fan_ce, _fan_next)
            else "pmv_offset"
            if latch_dwelt(_ca1.pmv_offset, _pmv_next)
            else ""
        )
        return _pmv_ready

    def _fold_tier2_inputs(self, ctx: FinalizeContext, *, pmv_ready: bool) -> None:
        """Fold 4: the NEXT-tick solver inputs of the tier-2 mechanism.

        Split from fold 3 for size (plan O.6 caps a fold at 80 code lines and
        the stepping alone is 78) along the seam the code already draws: this
        half writes ``latches``, not ``diagnostics``, and takes no elapsed dt.
        ``_ca1.fan_ce`` and ``_pmv_next`` of fold 3 are read back here through
        ``diagnostics.comfort_activation``, which fold 3's last write built
        from exactly those two objects — same objects, same states.
        """
        _ca = self._runtime.diagnostics.comfort_activation
        # NEXT-tick solver inputs: the CE credit only against a CONFIRMED
        # fan run (the shadow's velocity is hvac_action-gated, ADR-0068
        # §6 — a still room yields 0.0), the PMV shift only with real
        # control readiness (ADR-0069 §4).
        _ce_val = ctx.climate_diag.get("fan_ce_k")
        self._runtime.latches.fan_ce_credit_k = (
            float(_ce_val)
            if _ca.fan_ce.state == "live" and isinstance(_ce_val, (int, float))
            else 0.0
        )
        _pmv_val = ctx.climate_diag.get("pmv")
        self._runtime.latches.pmv_offset_k = (
            pmv_setpoint_offset(float(_pmv_val))
            if _ca.pmv_offset.state == "live"
            and pmv_ready
            and isinstance(_pmv_val, (int, float))
            else 0.0
        )

    def _fold_reference_offset(self, ctx: FinalizeContext, *, tick_min: float) -> bool:
        """Fold 5: ADR-0056 actuator<->room reference-frame offset.

        Returns ``_ref_conditioning`` — the EKF drive signal fold 6 and the
        assembly both consume, computed here at its original position.
        """
        now, room, act_state = ctx.now, ctx.room, ctx.act_state
        # ADR-0056 SHADOW: actuator<->room reference-frame offset (no writes).
        # Fold in a sample only while the actuator is actually conditioning
        # — its internal sensor carries the placement bias only under
        # active airflow/heat, so idle ticks would drag the offset toward
        # zero. Reuse the EKF drive signal (real hvac_action, intent
        # fallback); the warm-up therefore counts real conditioning time.
        # Diagnostic only: the write path stays room-referenced until
        # flip-gated live (ADR-0055).
        _ref_dt = capped_elapsed_min(
            self._runtime.learning.ref_last_mono, now, tick_min
        )
        self._runtime.learning.ref_last_mono = now
        # parse_finite mirrors the actuator_snapshot contract (no
        # availability gate, finite rejection — a NaN used to poison the
        # deviation EWMA until restart, review B.5).
        _act_f = parse_finite(
            act_state.attributes.get("current_temperature") if act_state else None
        )
        _ref_conditioning = (
            self._runtime.learning.last_u_h > 0.0
            or self._runtime.learning.last_u_c > 0.0
        )
        self._runtime.learning.ref_offset = update_offset(
            self._runtime.learning.ref_offset,
            actuator_temp=_act_f,
            room_temp=room,
            dt_min=_ref_dt,
            conditioning=_ref_conditioning,
        )
        return _ref_conditioning

    def _fold_tau_settle(
        self, ctx: FinalizeContext, *, tick_min: float, conditioning: bool
    ) -> None:
        """Fold 6: settle-based tau-confidence (the last state fold)."""
        now = ctx.now
        # SHADOW: settle-based τ-confidence — has α (=1/τ) actually
        # converged, not just been counted (ADR-0024)? Fed only on
        # learn-active ticks (the same excitation signal, where α can
        # move); diagnostic only, no writes, until it clamps the preheat
        # lead live (ADR-0055).
        _tau_dt = capped_elapsed_min(
            self._runtime.learning.tau_last_mono, now, tick_min
        )
        self._runtime.learning.tau_last_mono = now
        self._runtime.learning.tau_settle = update_settle(
            self._runtime.learning.tau_settle,
            alpha=self._runtime.learning.ekf.x[1],
            dt_min=_tau_dt,
            learn_active=conditioning,
        )

    def _stage_assemble_tick_data(
        self,
        ctx: FinalizeContext,
        *,
        shadow: ShadowStageResult,
        valve: ValveHealthResult,
        outcome_diag: dict[str, Any],
    ) -> dict[str, Any]:
        """The ``_tick_data`` assembly (presenter pre-form) plus
        ``heat_demand``, which MUST follow the assembly — it reads
        ``tpi_duty`` back out of the dict. Returns THE dict object itself: the
        trace consumes it, ``TickOutcome.diagnostics`` carries it and
        ``_present`` republishes it, so ``coordinator.data`` stays identical
        BY OBJECT to the traced payload (aliasing contract; the ``tick_ms*``
        attach in ``_async_update_data`` builds on the same dict).

        This stage deliberately exceeds the soft ~150-line stage bound — the
        large dict literal is kept verbatim as the aliasing-contract proof
        body; a cosmetic split would weaken the verbatim evidence without
        shrinking the proof surface."""
        now, room, rh, target = ctx.now, ctx.room, ctx.rh, ctx.target
        t_out_eff, t_rm_eff, t_rm_source = ctx.t_out_eff, ctx.t_rm_eff, ctx.t_rm_source
        q_solar, q_solar_source = ctx.q_solar, ctx.q_solar_source
        q_solar_internal, t_mrt = ctx.q_solar_internal, ctx.t_mrt
        mrt_source, mrt_internal = ctx.mrt_source, ctx.mrt_internal
        decision, mode, adaptive_cool = ctx.decision, ctx.mode, ctx.adaptive_cool
        heating, cooling, final_mode = ctx.heating, ctx.cooling, ctx.final_mode
        act_state, window_open, failed = ctx.act_state, ctx.window_open, ctx.failed
        override_clamped, mold_capped = ctx.override_clamped, ctx.mold_capped
        mold_min, dewpoint, sched = ctx.mold_min, ctx.dewpoint, ctx.sched
        reading_source, preheating = ctx.reading_source, ctx.preheating
        preheat_outdoor, coasting = ctx.preheat_outdoor, ctx.coasting
        frozen, norm_binding = ctx.frozen, ctx.norm_binding
        binding_precedence, sched_active = ctx.binding_precedence, ctx.sched_active
        fault_active, heat_source_suspect = ctx.fault_active, ctx.heat_source_suspect
        ext_num, operative_active = ctx.ext_num, ctx.operative_active
        climate_diag = ctx.climate_diag
        config = ctx.config  # plan O.2: the tick's read-only config view
        _mode_nudge_blocked = ctx.mode_nudge_blocked
        _idle_park_mode = ctx.idle_park_mode
        _mode_adopt_reason = ctx.mode_adopt_reason
        _sp_adopt_reason = ctx.sp_adopt_reason
        operative, binding = shadow.operative, shadow.binding
        _cover_peak, _cover_pos = shadow.cover_peak, shadow.cover_pos
        _cover_reason, shadow_objs = shadow.cover_reason, shadow.shadow_objs
        valve_health, closing_steps = valve.valve_health, valve.closing_steps
        idle_steps = valve.idle_steps
        # ADR-0060 §2: advisory season-mode hint — the zone's own lockout
        # thresholds define "season-wrong", T_rm's multi-day memory is the
        # "persistently"; hysteresis anchor is transient runtime state.
        # Computed BEFORE the L2 detection: its history floors that reading.
        # ``season_hint_t_rm`` keeps the hint silent when only the fabricated
        # outdoor fallback is available (t_rm_source None).
        _sugg_now = dt_util.utcnow().timestamp()
        _season_hint = season_mode_hint(
            climate_mode=self._runtime.user.climate_mode,
            t_rm=season_hint_t_rm(t_rm_eff, t_rm_source),
            heat_max_outdoor=config.heat_max_outdoor,
            cool_min_outdoor=config.cool_min_outdoor,
            prev_hint=self._runtime.diagnostics.season_hint_prev,
        )
        self._runtime.diagnostics.season_hint_prev = _season_hint
        # ADR-0060 §3 season gate: overrides recorded while the zone is
        # season-wrong are mode signals, not comfort evidence.  The stamp is
        # not dirty-marked — the periodic (30-tick) save picks it up, a crash
        # loses minutes of it at most, and the hint usually re-raises anyway.
        if _season_hint is not None:
            self._runtime.user.season_hint_last_active_ts = _sugg_now
        _l2_floor = season_gate_floor(
            hint_active=_season_hint is not None,
            last_active_ts=self._runtime.user.season_hint_last_active_ts,
            now_ts=_sugg_now,
        )
        # ADR-0060 L2 SHADOW: the suggestion the L1 statistic would raise —
        # always computed and published (the §3 field-tuning round needs the
        # would-be suggestions); the repair-issue EMISSION alone is opt-in
        # gated inside _sync_suggestion_issue.  The reading is season-gate
        # floored (§3): the raw ungated view stays reconstructable from the
        # dump (statistics + floor stamp) via the replay instrument.
        _sugg = detect_override_pattern(
            self._runtime.user.override_stats, now_ts=_sugg_now, since_ts=_l2_floor
        )
        _sugg_suppressed = _sugg is not None and suggestion_suppressed(
            _sugg.key,
            self._runtime.user.suggestion_rejected_key,
            self._runtime.user.suggestion_rejected_at,
            _sugg_now,
        )
        # ADR-0067 F2: the clo-family reading + the #4 conflict resolution
        # (never two competing readings; an open family keeps its slot).
        _fb_sugg = detect_feedback_pattern(
            self._runtime.user.feedback_stats, now_ts=_sugg_now
        )
        _fb_reason = clo_suggestion_reason(
            _fb_sugg,
            l2_pending=False,  # the collision is resolved below with slot memory
            override_direction=_sugg.direction if _sugg is not None else None,
            rejected_key=self._runtime.user.clo_suggestion_rejected_key,
            rejected_at=self._runtime.user.clo_suggestion_rejected_at,
            now_ts=_sugg_now,
        )
        _emit_l2, _emit_clo, _family = resolve_suggestion_conflict(
            l2_pending=_sugg is not None and not _sugg_suppressed,
            clo_pending=_fb_reason == "",
            open_family=self._runtime.diagnostics.pending_suggestion_family,
        )
        self._runtime.diagnostics.pending_suggestion_family = _family
        if _fb_reason == "" and not _emit_clo:
            _fb_reason = "l2_pending"
        try:
            self._ports.sync_suggestion_issue(_sugg, _sugg_suppressed or not _emit_l2)
            self._ports.sync_clo_suggestion_issue(_fb_sugg if _emit_clo else None)
            self._ports.sync_season_hint_issue(_season_hint)
            # P1.5 D1: "this zone COULD calibrate if you opted in" — the
            # condition itself is evaluated in the HealthReporter with the
            # segments' capability build; the tick contributes its two
            # per-tick facts (the reserved successor input, the opt-in gate).
            self._ports.sync_calibration_available_issue(
                ext_temp_reserved=ext_num is not None,
                enabled=config.trv_calibration,
            )
        except Exception:  # noqa: BLE001 - suggestion glue must never break the tick
            self._log.debug("Poise suggestion issue sync failed", exc_info=True)
        # P1.4: the calibration number's tri-state metadata for the cal_offset
        # attribute — cheap (None target short-circuits to "gone") and safe on
        # every path, calibration configured or not.
        _cal_meta = self._reader.calibration_meta()
        _tick_data: dict[str, Any] = {
            "available": True,
            **outcome_diag,
            **climate_diag,
            "dynamics_profile": self._runtime.compressor.dynamics.value,
            "pi_integral_time_h": round(
                PROFILES[self._runtime.compressor.dynamics].integral_time_h, 3
            ),
            "reg_period_s": PROFILES[
                self._runtime.compressor.dynamics
            ].regulation_period_s,
            # ADR-0046 §8 (live): the compressor-guard suppression reason this tick
            # ("" = not blocked). When set, dry_active reads as intent (queued),
            # not "drying now" — the card shows "drying soon (compressor guard)".
            "mode_nudge_blocked": _mode_nudge_blocked,
            # ADR-0038: monotonic stamp of when this snapshot was produced, so
            # the system hub can detect a silently stale zone (age-based
            # staleness).
            "mono_ts": now,
            "current_temperature": round(room, 1),
            "current_humidity": round(rh, 1) if rh is not None else None,
            "target_temperature": target,
            "operative_temperature": round(operative, 1),
            "t_rm": round(t_rm_eff, 1),
            "t_rm_source": t_rm_source,
            "t_rm_internal": (
                round(self._runtime.learning.trm_tracker.current, 1)
                if self._runtime.learning.trm_tracker.current is not None
                else None
            ),
            "q_solar": round(q_solar, 3),
            "q_solar_source": q_solar_source,
            "q_solar_internal": round(q_solar_internal, 3),
            "beta_s": round(self._runtime.learning.ekf.get_model().beta_s, 3),
            "mrt": round(t_mrt, 1),
            "mrt_source": mrt_source,
            "mrt_internal": round(mrt_internal, 1),
            "heat_sp": decision.heat_sp,
            "cool_sp": decision.cool_sp,
            "mode": mode,
            "comfort_low": decision.heat_sp,
            "comfort_high": decision.cool_sp,
            "binding_lower_cause": binding,
            "category": config.category.value,
            "adaptive_cool": adaptive_cool,
            "adaptive_cool_mode": adaptive_cool_mode(config.adaptive_cool_cfg),
            "heating": heating,
            # Display contract: publish the arbitrated direction (final_mode)
            # and the actuator's own reported action so the entity's
            # hvac_action stays truthful during an override (where the raw
            # mode is "manual") and can prefer the device's real state.
            # "cooling" is published symmetric to "heating" (raw intent) to
            # close the asymmetry.
            "cooling": cooling,
            "final_mode": final_mode,
            "actuator_hvac_action": (
                act_state.attributes.get("hvac_action") if act_state else None
            ),
            "idle_park_mode": _idle_park_mode,
            "window_open": window_open,
            "window_auto_detected": self._runtime.window.window_auto.open,
            "window_auto_threshold": round(self._runtime.window.wa_open_threshold, 1),
            "window_bypass": self._runtime.user.window_bypass,
            "preset": self._runtime.user.preset.value,
            # A mode-hold (possibly without a setpoint) is an active hold too,
            # so the Card shows the pill / "gilt bis …" / resume for it.
            "override_active": (
                self._runtime.user.override is not None
                or self._runtime.user.mode_override is not None
            ),
            "mode_override": self._runtime.user.mode_override,
            # Hold origin (ui_setpoint / device_adopt_*) + why this tick
            # did/did not adopt a device change (diagnostics; "" when nothing
            # seen).
            "override_reason": self._runtime.user.override_reason,
            "mode_adopt_reason": _mode_adopt_reason,
            "sp_adopt_reason": _sp_adopt_reason,
            # ADR-0059 §4: the manual-hold lifecycle for the Card ("gilt bis …").
            "override_expires_at": _iso_utc(self._runtime.user.override_expires_at),
            "override_policy": config.override_policy,
            "override_requested": self._runtime.user.override_requested,
            # ADR-0069 U1: control-readiness shadow keys — future tier wiring
            # consumes these; the diagnostic signals (pmv_valid, occupied)
            # keep their meaning untouched.
            "pmv_control_ready": pmv_control_ready(
                rh=ctx.rh, pmv_valid=ctx.climate_diag.get("pmv_valid") is True
            ),
            "presence_control_ready": presence_control_ready(ctx.occupancy),
            "room_present": room_present(ctx.occupancy),
            # ADR-0059 §5: the persisted L1 nudge log (observe-only). A shadow key
            # (absent from _ATTRS) -> diagnostics-only, never a recorded attribute.
            "override_stats": list(self._runtime.user.override_stats),
            "feedback_stats": list(self._runtime.user.feedback_stats),
            # ADR-0060 L2: the would-be suggestion (shadow keys, not _ATTRS).
            "suggestion_kind": _sugg.kind if _sugg else None,
            "suggestion_direction": _sugg.direction if _sugg else None,
            "suggestion_value": (
                (
                    _sugg.step_k
                    if _sugg.step_k is not None
                    else float(_sugg.step_min or 0)
                )
                if _sugg
                else None
            ),
            "suggestion_evidence": _sugg.evidence if _sugg else 0,
            "suggestion_suppressed": _sugg_suppressed,
            "season_hint": _season_hint,
            # ADR-0060 §3: the gate floor stamp (shadow key, not _ATTRS) — the
            # diagnostics dump lifts it next to the statistics it floors.
            "season_hint_last_active_ts": (
                self._runtime.user.season_hint_last_active_ts
            ),
            # ADR-0068 U6: fan-first observability (shadow keys, not _ATTRS).
            "fan_first_phase": self._runtime.latches.fan_first.phase,
            "fan_first_reason": self._runtime.diagnostics.fan_first_reason,
            # ADR-0069 E7 (Card): the mechanism toggle, published so the card
            # can gate the active-measure display on the real config state.
            "active_comfort": config.active_comfort,
            # ADR-0069 U7/U8: tier-2 latch states + the applied inputs.
            "tier2_fan_ce": (self._runtime.diagnostics.comfort_activation.fan_ce.state),
            "tier2_pmv_offset": (
                self._runtime.diagnostics.comfort_activation.pmv_offset.state
            ),
            # ADR-0069 N1: maturing progress for the card ("reift · X/24 h").
            # Dwell minutes are rounded to 10-min steps so the recorded
            # attribute changes ~6x/h instead of every tick.
            "tier2_fan_ce_dwell_min": (
                round(
                    self._runtime.diagnostics.comfort_activation.fan_ce.dwell_min / 10
                )
                * 10
            ),
            "tier2_pmv_dwell_min": (
                round(
                    self._runtime.diagnostics.comfort_activation.pmv_offset.dwell_min
                    / 10
                )
                * 10
            ),
            "tier2_dwell_target_min": int(DWELL_TARGET_MIN),
            "tier2_dwelling": self._runtime.diagnostics.tier2_dwelling,
            "fan_ce_credit_k": self._runtime.latches.fan_ce_credit_k,
            "pmv_offset_k": self._runtime.latches.pmv_offset_k,
            # ADR-0067 F2: the clo-family reading ("" reason = emittable).
            "clo_suggestion_direction": _fb_sugg.direction if _fb_sugg else None,
            "clo_suggestion_evidence": _fb_sugg.evidence if _fb_sugg else 0,
            "clo_suggestion_reason": _fb_reason,
            "boost_expires_at": _iso_utc(self._runtime.user.boost_expires_at),
            "override_clamped": override_clamped,
            "cover_predicted_peak": round(_cover_peak, 1),
            "cover_would_shade": _cover_pos > 0,
            "cover_shade_position": _cover_pos,
            "cover_shade_reason": _cover_reason,
            "window_auto_slope": self._runtime.window.window_auto.ema_slope,
            "heating_failure": failed,
            # C.8: pure cooling-detector latch (updated earlier this tick in
            # the failure-detect stage; no fault_active OR — see the stage).
            "cooling_failure": self._runtime.safety.cooling_failure.failed,
            # C.8 write-convergence telemetry: consecutive unconverged
            # re-asserts/re-nudges (0 = converging normally).
            "sp_diverged_writes": self._runtime.safety.convergence.sp_diverged_writes,
            "mode_diverged_nudges": (
                self._runtime.safety.convergence.mode_diverged_nudges
            ),
            "mold_capped": mold_capped,  # mould floor clipped at 24 °C
            # ADR-0057: publish the mould-protection floor + dewpoint so the card
            # can draw the "Schimmel" tick on the dial (display only, no control).
            "mould_floor": round(mold_min, 1) if mold_min is not None else None,
            "dewpoint": round(dewpoint, 1) if dewpoint is not None else None,
            "source": reading_source.value,
            "tau_hours": round(self._runtime.learning.ekf.tau_hours, 1),
            "confidence": round(self._runtime.learning.ekf.confidence, 2),
            "identified": self._runtime.learning.ekf.identified,
            "learning_phase": self._runtime.learning.ekf.learning_phase,
            "identification_progress": round(self._runtime.learning.ekf.data_factor, 2),
            "schedule_state": "comfort" if sched.is_comfort else "setback",
            "minutes_to_comfort": sched.minutes_to_comfort,
            "preheating": preheating,
            "preheat_outdoor": preheat_outdoor,
            "coasting": coasting,
            "minutes_to_setback": sched.minutes_to_setback,
            "sensor_frozen": frozen,
            "norm_binding": norm_binding,
            "binding_precedence": binding_precedence,
            "device_schedule_active": sched_active,
            "device_alarm": fault_active,
            "sensor_placement_suspect": heat_source_suspect,
            "trv_input_mode": (
                "operative" if operative_active else ("air" if ext_num else "none")
            ),
            "valve_health": valve_health,
            "valve_closing_steps": closing_steps,
            "valve_idle_steps": idle_steps,
            # P1.4 calibration diagnosis (shadow keys, deliberately NOT in
            # climate._RECORDED_ATTRS): reported offset when the number is
            # readable, last commanded offset, and the two per-tick verdicts
            # the sequencer stamped onto the diagnostics latches.
            "cal_offset": (
                _cal_meta.reported if isinstance(_cal_meta, CalibrationMeta) else None
            ),
            "cal_target": self._runtime.actuator.last_cal_value,
            "cal_diverged": self._runtime.diagnostics.cal_diverged,
            "cal_handoff_pending": self._runtime.diagnostics.cal_handoff_pending,
            **shadow_objs,
            "tpi_valve_entity": self._reader.valve_entity,
            "seasonless_phase": self._runtime.learning.seasonless.phase,
            "seasonless_rate": (
                round(p, 3)
                if (
                    p := self._runtime.learning.seasonless.heat_rate_prior(
                        decision.heat_sp, t_out_eff, dt_util.now().toordinal()
                    )
                )
                is not None
                else None
            ),
        }
        # Surface this zone's own boiler heat-demand (0..1) -- exactly the
        # value the hub aggregates from our data, so per-zone visibility can't
        # drift.
        _tick_data["heat_demand"] = zone_heat_demand(
            heating=heating,
            tpi_duty=_tick_data.get("tpi_duty"),
            frozen=frozen,
        )
        return _tick_data
