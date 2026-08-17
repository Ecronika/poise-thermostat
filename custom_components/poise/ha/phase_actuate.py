"""The ACTUATION phase of the tick -- every await, every commit (plan O.5).

Mode resolution -> hold routing -> mode adoption -> mode nudge -> fan write ->
setpoint observe/adopt -> setpoint write -> external-temperature feed, or, on
the disabled/off-held branch, the frost rescue.  Plus the unavailable path's
safe-state node, which is an actuation body living behind a thin sequencer
facade (see below).

WHY THIS MODULE EXISTS AS ITS OWN FILE.  The split follows the AWAIT TOPOLOGY.
This is the ONLY tick module that awaits the actuator and the ONLY one that
commits, and the structure gate pins exactly that:

    normal tick path : exactly 5 executor awaits -- run_mode_nudge,
                       run_fan_write, run_setpoint_write, run_ext_temp,
                       run_frost_rescue
    unavailable path : exactly 1 executor await -- run_unavailable_safe
    anything else    : 0 awaits

CAPABILITY NARROWING (binding, plan section 9).  Within the tick execution
only this class may hold or use the ``ActuatorExecutor``; ``coordinator.py``
stays the composition root and wires it in.  A phase that cannot reach the
writer cannot write -- the dependency direction carries the same cut as the
await topology.

THE UNAVAILABLE SAFE PATH (binding, plan O.5).  The body of the sixth executor
await lives HERE, while its position and its replaceable dispatch node stay
where they were:

    TickOrchestrator._run_unavailable_tick
      -> SequencerPorts.write_unavailable_safe_state()
      -> PoiseCoordinator._write_unavailable_safe_state()   # THE patch point
      -> TickOrchestrator._write_unavailable_safe_state()   # thin facade
      -> ActuatePhase.write_unavailable_safe_state()        # the body, verbatim

Receiver rules (binding, unchanged from the monolith): collaborators are the
injected ``self._runtime`` / ``self._reader`` / ``self._executor``, every
coordinator EFFECT goes through ``self._ports`` (an ``ActuatePorts`` view --
``commit_execution`` lives in this view and in no other), and the logger is the
injected ``self._log`` (channel ``custom_components.poise.coordinator`` is
behaviour).  Per-tick data travels as an ARGUMENT (``bindings``, ``config``) or
inside the frozen stage results, never as a field.

POSITION CONTRACTS ARE BEHAVIOUR.  The await positions, the commit positions
and the positioned post-await reads (the actuator read, ``device_min``, the
ext-select fresh read) keep their exact places; the per-segment dependency
proofs live in ``TickOrchestrator.resume_prepare``'s docstring.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import State
from homeassistant.util import dt as dt_util

from ..comfort.operative import operative_temperature
from ..const import EXTERNAL_FEED_KEEPALIVE_S, FROST_FLOOR_C, WRITE_DEADBAND_C
from ..contracts import ActuatorCommand, ActuatorPath
from ..control.lifecycle import resolve_safe_state
from ..control.override import mode_adopt_reason, setpoint_adopt_reason
from ..control.tick_resolve import (
    external_feed_due,
    frost_rescue_target,
    needs_mode_nudge,
    resolve_desired_mode,
)
from ..multi import lifecycle as _lifecycle
from ..runtime.tick_result import (
    ActuatorPlan,
    ClimateBandResult,
    EndHold,
    ExternalTemperaturePlan,
    FanFirstStageResult,
    HoldRoutingResult,
    IngestResult,
    ModeAdoptionResult,
    ModeNudgeResult,
    ModeResolutionResult,
    ObservationResult,
    OperativeResult,
    SafetyFloorsResult,
    SetpointObservation,
    WriteTargetResult,
)
from ..runtime.zone_runtime import ZoneRuntime
from ..safety.write_convergence import convergence_tolerance
from .actuator_executor import ActuatorExecutor
from .input_reader import InputReader, parse_attr_number
from .tick_snapshot import TickConfigSnapshot, ZoneBindings

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    from .tick_ports import ActuatePorts


class ActuatePhase:
    """The twelve actuation stages plus the unavailable safe-state body.

    Built by the composition root (``coordinator.py``); the sequencer drives
    the stages, and the coordinator's own ``_write_unavailable_safe_state``
    reaches the last method through the orchestrator's thin facade.  The three
    collaborators are injected ONCE so the stage bodies keep their expressions
    verbatim -- that literalness is the equivalence proof of the O.5 move.
    """

    __slots__ = ("_executor", "_log", "_ports", "_reader", "_runtime")

    def __init__(
        self,
        *,
        runtime: ZoneRuntime,
        reader: InputReader,
        executor: ActuatorExecutor,
        ports: ActuatePorts,
        logger: logging.Logger,
    ) -> None:
        self._runtime = runtime
        self._reader = reader
        self._executor = executor
        self._ports = ports
        self._log = logger

    def _stage_mode_resolution(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        op: OperativeResult,
        wt: WriteTargetResult,
        band: ClimateBandResult,
        config: TickConfigSnapshot,
        *,
        fan_first_requested: bool = False,
    ) -> ModeResolutionResult:
        """Mode arbitration + compressor-guard policy (ADR-0046 paragraph 8).

        Body in ``pipeline_actuate.stage_mode_resolution`` via the runtime — the
        invariant (unconditional ``final_mode``/guard resolution, pinned by
        test_frost_rescue_disabled) lives in the moved body."""
        return self._runtime.stage_mode_resolution(
            ing,
            obs,
            op,
            wt,
            band,
            cool_min_outdoor=config.cool_min_outdoor,
            cool_lockout_enabled=config.cool_lockout_enabled,
            heat_max_outdoor=config.heat_max_outdoor,
            heat_lockout_enabled=config.heat_lockout_enabled,
            compressor_guard=config.compressor_guard,
            comp_min_off_opt=config.comp_min_off_opt,
            comp_mode_hold_opt=config.comp_mode_hold_opt,
            fan_first_requested=fan_first_requested,
        )

    def _stage_hold_routing(self, wt: WriteTargetResult) -> HoldRoutingResult:
        """Own-write echo + off-hold routing + user-resume escape.

        INVARIANT (pinned): the off-hold frost route keeps its one-tick delay
        -- ``off_held`` reads the persisted hold at tick start; the adopting
        tick still runs the enabled block.

        Body in ``external_override.stage_hold_routing`` via the runtime. The
        user-resume escape's ``_end_hold`` is injected, so its teardown +
        IMMEDIATE bus fire keep their in-stage position.
        """
        return self._runtime.stage_hold_routing(wt, end_hold_fn=self._ports.end_hold)

    def _stage_mode_adoption(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        routing: HoldRoutingResult,
        config: TickConfigSnapshot,
    ) -> ModeAdoptionResult:
        """External-mode adoption, guard-reference freeze, hold pinning.

        INVARIANT (pinned): an active mode-hold pins the desired mode unless
        window/frost took over this tick (safety beats hold).

        Body in ``external_override.stage_mode_adoption`` via the runtime,
        with the unified ONE-call observation (decision AND reason; see the
        module docstring there). ``resolve_desired_mode``/``mode_adopt_reason``
        are plain imports since O.4 — no test ever patched them; the
        injected command facades keep the ``dt_util`` reads and the
        ``poise_override_ended`` fire at their in-stage positions.
        """
        return self._runtime.stage_mode_adoption(
            ing,
            obs,
            wt,
            res,
            routing,
            adopt_external_mode=config.adopt_external_mode,
            resolve_desired_mode_fn=resolve_desired_mode,
            mode_adopt_reason_fn=mode_adopt_reason,
            set_mode_override_fn=self._ports.set_mode_override,
            end_hold_fn=self._ports.end_hold,
        )

    async def _stage_mode_nudge(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        adoption: ModeAdoptionResult,
        bindings: ZoneBindings,
        *,
        mode_nudge_blocked: str,
    ) -> ModeNudgeResult:
        """Mode-nudge segment: Nudge-Plan → Nudge-Exec + Commit.

        The decision (nudge need + compressor-guard block) is resolved first
        and travels typed in ``ModeNudgeResult``; the ``ActuatorPlan`` later
        RECORDS it (``write_mode``/``hvac_mode``). This segment must execute
        BEFORE the setpoint observation/gate: the ``is_safety`` read of
        ``self._override`` below sits before the nudge await while the §4
        throttle's read sits after it — both positions are load-bearing
        (reorder proof 1 in ``resume_prepare``)."""
        now = ing.now
        frozen = ing.frozen
        window_open = obs.window_open
        act_state = wt.act_state
        _guard_pol = res.guard_pol
        act_modes = res.act_modes
        desired_hvac = adoption.desired_hvac
        _mode_nudge_blocked = mode_nudge_blocked
        # A device hvac_mode change this tick must carry its setpoint with it,
        # so it bypasses the §4 setpoint throttle below: a mode nudge without
        # its matching setpoint would e.g. flip an AC to cool while it still
        # holds the heat idle-hold (17.5) and overcool until the throttle clears
        # (idle-park heat->cool transition).
        _mode_nudge = needs_mode_nudge(
            act_state.state if act_state else None,
            desired_hvac,
            supported=desired_hvac in act_modes,
        )
        _guard_block = _lifecycle.guard_block_reason(
            _guard_pol,
            self._runtime.compressor.multi_lifecycle,
            dt_util.utcnow().timestamp(),
            desired=desired_hvac,
            current=act_state.state if act_state else None,
            # An active manual override is deliberately exempt from the
            # compressor-guard hold, same as a genuine safety trip (open
            # window / frozen sensor) -- ADR-0046 states this explicitly
            # (is_safety covers window->off, frost, override and frozen, never
            # blocked). A user's manual intent must not be held hostage by a
            # min-off/mode-hold timer.
            is_safety=window_open or frozen or self._runtime.user.override is not None,
        )
        if _mode_nudge and _guard_block:
            _mode_nudge = False  # compressor protection: hold this tick's nudge
            _mode_nudge_blocked = _guard_block
        # C.8 watchdog fold (pure, pre-commit): an identical re-nudge
        # (``desired == last_commanded_hvac`` — the inverse of the commit's
        # ``mode_changed``) against an unmoved device is divergence evidence;
        # a guard-blocked tick is not (``nudged=False``), and a state the
        # integration has not refreshed since our last mode command is no
        # evidence in either direction (poll latency / frozen echo). Must
        # read the baseline BEFORE the commit below moves it.
        self._runtime.safety.convergence.observe_mode(
            nudged=_mode_nudge,
            re_nudge=desired_hvac == self._runtime.external.last_commanded_hvac,
            current_matches_desired=(
                act_state is not None and act_state.state == desired_hvac
            ),
            evidence_fresh=self._convergence_evidence_fresh(
                act_state, self._runtime.external.last_hvac_cmd_ts, now
            ),
            now=now,
        )
        if _mode_nudge:
            # The executor sequence owns the boundary, the own-context
            # creation (tag our own mode change; the id reports even when the
            # dispatch throws — attempt state, test_phase0_attempt_success)
            # and the boundary log. The commit right HERE folds the stamps —
            # it must stay a SEPARATE commit from the setpoint write's below:
            # the code between the two sites reads the mode stamps. Stamp the
            # mode echo baseline so our own nudge is never re-read as an
            # external mode change next tick. Only re-arm the echo window on a
            # mode *change* -- re-arming on every identical re-nudge (a device
            # that never follows) would keep the window open forever and
            # permanently block adoption; evaluated at DISPATCH time, before
            # the stamp moves the ``_last_commanded_hvac`` baseline.
            report = await self._executor.run_mode_nudge(
                bindings.actuator,
                desired_hvac,
                mode_changed=desired_hvac != self._runtime.external.last_commanded_hvac,
            )
            self._ports.commit_execution(report, now=now)
        return ModeNudgeResult(
            mode_nudge=_mode_nudge,
            guard_block=_guard_block,
            mode_nudge_blocked=_mode_nudge_blocked,
        )

    @staticmethod
    def _convergence_evidence_fresh(
        act_state: State | None, last_cmd_mono: float | None, now_mono: float
    ) -> bool:
        """C.8: did the actuator state update AFTER our last command?

        A state the integration has not refreshed since the command can
        neither prove the device ignored it (poll latency) nor that it
        applied it (frozen own-context echo) — the watchdog holds on stale.
        ``last_updated`` is wall clock, the command stamps are monotonic; the
        comparison translates via "state age vs. elapsed since command",
        which needs no epoch alignment. No command this run -> trivially
        fresh (the state cannot be staler than a write that never happened).
        """
        if act_state is None:
            return False
        if last_cmd_mono is None:
            return True
        age_s = (dt_util.utcnow() - act_state.last_updated).total_seconds()
        return bool(age_s <= (now_mono - last_cmd_mono))

    async def _stage_fan_write(
        self,
        ing: IngestResult,
        wt: WriteTargetResult,
        band: ClimateBandResult,
        ff: FanFirstStageResult,
        bindings: ZoneBindings,
        config: TickConfigSnapshot,
    ) -> None:
        """ADR-0068 U6: the fan-stage write of the fan-first sequence
        (echo-gated by the FSM: only after fan_only was OBSERVED) and the
        ADR-0053 idle circulation over the SAME single path — exactly one
        live path moves the fan.

        Segment Fan-Plan → Fan-Exec + Commit; its position between the
        mode-nudge and setpoint-observe segments is the contract.
        """
        _ff = ff.decision
        _act_ff = wt.act_state
        _fan_cmd: str | None = None
        if _ff.command == "stage" and _ff.state.stage is not None:
            _fan_cmd = _ff.state.stage
        elif _ff.restore_stage is not None:
            # Exit restore (field decision): put the stage back to the
            # pre-sequence value ("auto" fallback) — once, never fighting.
            _fan_cmd = _ff.restore_stage
        elif (
            config.active_comfort
            and _ff.state.phase == "idle"
            and _act_ff is not None
            and _act_ff.state == "fan_only"
            and not ff.foreign_fan
            and ff.presence_ok
            and band.climate_diag.get("fan_circ_shadow") == "fan_low"
            and "low" in {m.lower() for m in ff.fan_modes}
            and (ff.device_fan or "").lower() != "low"
            and self._runtime.external.last_commanded_fan != "low"
        ):
            _fan_cmd = "low"
        if _fan_cmd is not None:
            fan_report = await self._executor.run_fan_write(
                bindings.actuator,
                _fan_cmd,
                fan_changed=(_fan_cmd != self._runtime.external.last_commanded_fan),
            )
            self._ports.commit_execution(fan_report, now=ing.now)

    def _stage_setpoint_observe(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        routing: HoldRoutingResult,
        nudge: ModeNudgeResult,
        config: TickConfigSnapshot,
    ) -> SetpointObservation:
        """Device setpoint observation, ADR-0052 paragraph-4 throttle,
        own-echo re-baseline and external-setpoint detection.

        Body in ``pipeline_actuate.stage_setpoint_observe`` via the runtime. The
        two ``parse_attr_number`` reads of the tick's ONE actuator State
        object (incl. the ``or 0.1`` step fallback) are pre-parsed here: the
        helper lives in ``ha/`` and importing it into the pipeline would pull
        homeassistant into the pure py310 suite. Both are side-effect-free
        reads of the same frozen State object the stage consumes, so the hoist
        to this call boundary is unobservable (no patch surface on either).

        The stage's ONE tracker observation yields the adoption decision AND
        the ``sp_adopt_reason`` (carried in the ``SetpointObservation``);
        ``setpoint_adopt_reason`` is a plain import since O.4 — no test ever
        patched it.
        """
        return self._runtime.stage_setpoint_observe(
            ing,
            obs,
            wt,
            res,
            routing,
            nudge,
            actual_sp=parse_attr_number(wt.act_state, "temperature"),
            # ATTR_TARGET_TEMP_STEP: HA serialises the step as
            # "target_temp_step", not under the property name.
            step=parse_attr_number(wt.act_state, "target_temp_step") or 0.1,
            adopt_external_setpoint=config.adopt_external_setpoint,
            setpoint_adopt_reason_fn=setpoint_adopt_reason,
        )

    def _stage_setpoint_adopt(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        routing: HoldRoutingResult,
        spo: SetpointObservation,
        bindings: ZoneBindings,
        *,
        mode_adopt_reason: str,
    ) -> str:
        """Adoption-reason surfacing, debounced log, prev-update and the
        adoption itself.

        Returns the tick's ``sp_adopt_reason`` (the diagnosis string).

        Body in ``external_override.stage_setpoint_adopt`` via the runtime.
        The reason travels IN ``spo`` — computed together with the decision
        by the ONE observation in ``_stage_setpoint_observe`` from
        character-equal arguments (the re-derivation here saw the same
        ``prev_device_sp``: the prev-update sat AFTER the reason call).
        ``obs``/``routing`` stay in the pinned facade signature; the unified
        chain consumed them in the observe stage. ``set_override`` (full hold
        lifecycle + immediate events) is injected and runs at its in-stage
        position, the debounce log keeps this module's logger channel.
        """
        return self._runtime.stage_setpoint_adopt(
            ing,
            spo,
            mode_adopt_reason=mode_adopt_reason,
            actuator_entity=bindings.actuator,
            logger=self._log,
            set_override_fn=self._ports.set_override,
        )

    def _plan_setpoint_write(
        self,
        wt: WriteTargetResult,
        adoption: ModeAdoptionResult,
        nudge: ModeNudgeResult,
        spo: SetpointObservation,
    ) -> ActuatorPlan:
        """Setpoint write gate → the tick's ``ActuatorPlan`` (gate position —
        see the reorder proofs in ``resume_prepare``).

        Body in ``pipeline_actuate.plan_setpoint_write`` via the runtime."""
        return self._runtime.plan_setpoint_write(wt, adoption, nudge, spo)

    async def _stage_setpoint_write(
        self,
        ing: IngestResult,
        wt: WriteTargetResult,
        res: ModeResolutionResult,
        adoption: ModeAdoptionResult,
        nudge: ModeNudgeResult,
        spo: SetpointObservation,
        bindings: ZoneBindings,
    ) -> ActuatorPlan:
        """Setpoint segment: gate/plan → dispatch → commit.

        The write DECISION is the ``ActuatorPlan`` from
        ``_plan_setpoint_write`` (same reads, same order, same await-free
        window as the inline gate); the executor sequence dispatches it and
        the commit folds the stamps. Returns the plan as the tick's
        actuator-write record for the ``TickPlan``.
        """
        now = ing.now
        final_mode = res.final_mode
        actual_sp = spo.actual_sp
        plan = self._plan_setpoint_write(wt, adoption, nudge, spo)
        # C.8 watchdog fold (pure, pre-commit): judged against ``last_cmd_sp``
        # — the value we COMMANDED, stamped by the commit and never
        # re-baselined (C.8f). Using the adoption baseline instead would let a
        # clamping device read as "converged" the moment the re-baseline moved
        # onto its clamp. Tolerance is the floored re-quantise distance, so a
        # device settling one step away still counts as converged. No evidence
        # from a state the integration has not refreshed since our last write
        # (poll latency) or from a late echo of a superseded command.
        self._runtime.safety.convergence.observe_setpoint(
            actual_sp=actual_sp,
            last_written_sp=self._runtime.external.last_cmd_sp,
            tolerance=convergence_tolerance(spo.step),
            wrote=plan.write_setpoint,
            evidence_fresh=(
                not spo.stale_own_echo
                and self._convergence_evidence_fresh(
                    wt.act_state, self._runtime.external.last_sp_write_ts, now
                )
            ),
            now=now,
        )
        if plan.write_setpoint:
            # By construction: values + the intended device mode
            # (``adoption.desired_hvac``, always a str) are set whenever
            # write_setpoint is.
            assert plan.raw_setpoint is not None
            assert plan.snapped_setpoint is not None
            assert plan.hvac_mode is not None
            cmd = ActuatorCommand(
                actuator_id=bindings.actuator,
                path=ActuatorPath.SETPOINT,
                value=plan.raw_setpoint,  # RAW on the wire
                hvac_mode=plan.hvac_mode,
                reason=plan.reason,
            )
            # The executor sequence owns the boundary, the own-context
            # creation (tag the call so the resulting state change carries a
            # Context we recognise as our own next tick — echo / clamp) and
            # the boundary log; the commit right here folds the stamps.
            # Attempt state commits even when the dispatch throws:
            # ``pre_write_sp`` — the device's reported setpoint just before
            # this write, the only other value a legit in-window echo can
            # carry (poll lag), remembered for next tick's three-value
            # adoption test — and the context-id registration. Success stamps
            # the SNAPPED target as the echo baseline (the raw value went on
            # the wire).
            report = await self._executor.run_setpoint_write(
                cmd,
                pre_write_value=actual_sp,
                snapped_value=plan.snapped_setpoint,
                final_mode=final_mode,
            )
            self._ports.commit_execution(report, now=now)
        return plan

    async def _stage_ext_temp_feed(
        self, ing: IngestResult, op: OperativeResult
    ) -> ExternalTemperaturePlan | None:
        """External-temperature segment: read → plan → dispatch → commit
        (ADR-0029). The select's state stays a positioned fresh read inside
        the write path, after the mode/setpoint awaits (reorder proof 4 in
        ``resume_prepare``). Returns the executed ``ExternalTemperaturePlan``
        (None when the segment did not run) as the record for the
        ``TickPlan``."""
        now = ing.now
        room = ing.room
        t_mrt = ing.t_mrt
        ext_num = op.ext_num
        ext_ok = op.ext_ok
        operative_active = op.operative_active
        # feed the true room temperature to a TRV external-temperature input
        # (ADR-0029): the thermostat then modulates against the real sensor.
        if ext_num and ext_ok:
            # ensure the TRV uses its external sensor (pavax-verified); on
            # the tick we switch it, skip the write so the device can settle
            # — the select-success -> feed-skip coupling is sequence-INTERNAL
            # and owned by the executor (``skip_feed_on_select_success``; a
            # failed select still feeds). It never surfaces as a commit stamp.
            # Positioned read: the select's state is read FRESH in the write
            # path, after the mode-nudge/setpoint awaits — a select change
            # during those service calls is observable and stays so. ``None``
            # covers both "no select discovered" and "no State object".
            _sel_state = self._reader.ext_select_state()
            _select_external = _sel_state is not None and _sel_state not in (
                "external",
                "unavailable",
            )
            fed = round(
                operative_temperature(room, t_mrt) if operative_active else room,
                1,
            )
            # Both plan gates are decided BEFORE the sequence runs.
            # ``external_feed_due`` is pure and reads only state the select
            # never touches (``_last_fed``/``_last_fed_ts``), so evaluating it
            # up front is unobservable; ``feed_value=None`` = no feed planned
            # this tick ("not due" — nothing dispatched, nothing stamped).
            # ``ext_select_state()`` returns non-None only when a sensor
            # select was discovered, so the proxied id is never None when the
            # select is planned. Both calls stay untagged (open F-CONTEXT);
            # the commit right here folds the feed stamps.
            plan = ExternalTemperaturePlan(
                select_external=_select_external,
                feed_value=(
                    fed
                    if external_feed_due(
                        self._runtime.actuator.last_fed,
                        fed,
                        last_fed_ts=self._runtime.actuator.last_fed_ts,
                        now=now,
                        keepalive_s=EXTERNAL_FEED_KEEPALIVE_S,
                        deadband=0.1,
                    )
                    else None
                ),
            )
            report = await self._executor.run_ext_temp(
                plan,
                select_entity_id=self._reader.sensor_select,
                number_entity_id=ext_num,
            )
            self._ports.commit_execution(report, now=now)
            return plan
        return None

    async def _stage_frost_rescue(
        self,
        ing: IngestResult,
        obs: ObservationResult,
        floors: SafetyFloorsResult,
        wt: WriteTargetResult,
        routing: HoldRoutingResult,
        bindings: ZoneBindings,
    ) -> ActuatorPlan | None:
        """Disabled/off-held path: Rescue-Plan → Exec + Commit + Events.

        The rescue gates (rescue_ok, ``frost_rescue_target``, the online
        gate, the heat-nudge need) decide the rescue ``ActuatorPlan``
        (``reason="frost_rescue"``: the floor travels raw; NO snapped echo
        baseline — the commit clears it). The ``EndHold("frost_rescue")``
        post-action stays decoupled from write success (pinned by the phase-0
        frost-rescue matrix); the events fire right here after the commit —
        after the write attempts, well before the end-of-tick savepoint —
        which is why this segment keeps them instead of the coordinator seam
        (Rescue-Plan→Exec+Commit+Events). Returns the executed plan (None when
        no rescue write ran) for the ``TickPlan``.
        """
        now = ing.now
        room = ing.room
        can_heat = obs.can_heat
        mold_min = floors.mold_min
        act_state = wt.act_state
        _actuator_online = wt.actuator_online
        _off_held = routing.off_held
        # A disabled zone still gets unconditional frost/mould protection
        # (README promise) — but rescue-only, so a reasonable manual setpoint
        # above the floor is never fought; a cool-only device has no frost
        # duty and is left alone (frost_rescue_target -> None). A user-held
        # ``off`` (device switched off via the remote, Poise still enabled) is
        # honoured like a disabled zone -- but unlike a truly disabled zone we
        # must NOT treat the warm off device as perpetual frost demand
        # (``frost_rescue_target`` rescues an off heater on principle), or we
        # would restart the device the user deliberately switched off. So an
        # off-HELD zone is rescued only when the ROOM is actually at the
        # frost/mould floor; a disabled zone keeps the unconditional rescue.
        _rescue_ok = (
            (not _off_held)
            or room <= FROST_FLOOR_C
            or (mold_min is not None and room <= mold_min)
        )
        rescue = (
            frost_rescue_target(
                can_heat=can_heat,
                actual_sp=parse_attr_number(act_state, "temperature"),
                device_state=act_state.state if act_state else None,
                frost_floor=FROST_FLOOR_C,
                mold_min=mold_min,
                deadband=WRITE_DEADBAND_C,
            )
            if _rescue_ok
            else None
        )
        # ``frost_rescue_target`` treats "unavailable" as "inactive" on
        # purpose (an off/unknown/unavailable device below the floor all
        # legitimately need the rescue floor) -- but that means it returns a
        # non-None target on EVERY tick for a genuinely offline actuator, so
        # unlike the enabled-branch setpoint write above, this write is gated
        # on ``_actuator_online``: otherwise a disabled zone with a dead
        # actuator would dispatch a real ``climate.set_temperature`` into the
        # void every tick. Off/unknown (actuator present, just not in "heat")
        # still get the rescue write.
        if rescue is not None and _actuator_online:
            _rmodes = (
                (act_state.attributes.get("hvac_modes") or []) if act_state else []
            )
            _cur = act_state.state if act_state else None
            # The decided rescue plan — the nudge need is evaluated directly
            # for the run_frost_rescue call.
            plan = ActuatorPlan(
                write_mode=_cur != "heat" and "heat" in _rmodes,
                hvac_mode="heat",
                write_setpoint=True,
                snapped_setpoint=None,  # no echo baseline for the floor
                raw_setpoint=rescue,
                reason="frost_rescue",
            )
            # The executor sequence owns the TWO INDEPENDENT boundaries — a
            # failed mode-nudge must never skip the safety setpoint write (the
            # floor still has to be sent) — plus both untagged payloads and
            # the boundary logs. The commit right here folds the stamps:
            # frost-rescue heat is our own safety mode, never a user change —
            # mode echo baseline, ts re-armed UNCONDITIONALLY; the frost floor
            # is our own value, not user intent -> ``last_written_sp=None``;
            # plus ``_mark_actuated``.
            report = await self._executor.run_frost_rescue(
                bindings.actuator,
                rescue,
                nudge=plan.write_mode,
            )
            # A frost/mould rescue that fires while an ``off`` hold is active
            # supersedes the user's off intent -- end the hold with an
            # accurate reason ("frost_rescue") instead of leaving the device
            # escape to end it next tick under the generic "user_resume". The
            # ``EndHold`` post-action (require_success=False) runs AFTER the
            # report fold and is never coupled to write success (phase-0
            # frost-rescue matrix, all four cells); the adapter fires the
            # returned ``poise_override_ended`` event right after the commit —
            # after the write attempts, well before the end-of-tick checkpoint.
            commit = self._ports.commit_execution(
                report,
                post_actions=((EndHold("frost_rescue"),) if _off_held else ()),
                now=now,
            )
            for ev in commit.events:
                self._ports.fire_override_ended(ev.reason)
            return plan
        return None

    async def write_unavailable_safe_state(self, bindings: ZoneBindings) -> None:
        """Command the frost/mould floor after a sustained room-sensor loss.

        A heat-capable actuator degrades to the health floor in heat (frost
        protection held by its own sensor -- fail toward warmth); a cool-only
        actuator is commanded off (it must not cool the room to the floor).
        Mirrors the frozen-sensor safe state for a fully unavailable sensor.
        The floor is clamped up to the device ``min_temp`` so a high-min AC
        does not thrash on an echo it cannot honour. Best-effort + idempotent;
        a failure must never break the tick.

        This is the unavailable path's plan_actuation + apply + commit node —
        ``resolve_safe_state`` produces the ``SafeStatePlan`` (or None =
        already safe), the executor sequence applies it, the commit folds the
        stamps. The actuator read below is await-relative behaviour, so the
        plan cannot be resolved in the prepare phase.
        """
        # Positioned read: the dirty flush follows this write (F-SAVEPOINT,
        # ADR-0064), so this read sees the device state at tick start.
        act = self._reader.actuator_state()
        modes = (
            [str(m) for m in (act.attributes.get("hvac_modes") or [])] if act else []
        )
        # Decide mode + setpoint together (pure), so a device in cool/auto/off
        # actually receives the set_hvac_mode('heat') it needs and does not
        # keep cooling toward the floor. Mode and setpoint writes are
        # independent and each idempotent.
        plan = resolve_safe_state(
            hvac_modes=modes,
            device_state=act.state if act is not None else None,
            device_setpoint=parse_attr_number(act, "temperature"),
            device_min=parse_attr_number(act, "min_temp"),
            floor=FROST_FLOOR_C,
        )
        if plan is None:
            return  # already in the safe state -> no re-write (idempotent)
        # The executor sequence owns the ONE shared boundary (a mode dispatch
        # error skips the setpoint write; splitting the boundary is the open
        # F-SAFESEQ), both payloads (untagged; tagging is the open F-CONTEXT)
        # and the boundary log; the
        # commit right here folds the stamps. Mode part: ``last_written_mode``
        # only after a real nudge (our own safe-state mode is never a user
        # change — mode echo). Setpoint part: ``last_target``; clear the
        # adoption baseline (``last_written_sp=None``) so our own safe-state
        # setpoint is never re-read as a user hold on recovery;
        # ``_mark_actuated``. No timestamp on this path: the commit needs no
        # ``now=``.
        report = await self._executor.run_unavailable_safe(
            plan, entity_id=bindings.actuator, zone_name=bindings.zone_name
        )
        self._ports.commit_execution(report)
