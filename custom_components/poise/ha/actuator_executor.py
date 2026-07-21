"""The single WRITING Home-Assistant adapter.

``ActuatorExecutor`` owns the effect-call PRIMITIVES of the coordinator tick
(one named method per write-site class, each a character-exact passthrough of
the dispatch — payload shape, ``blocking=False``, context handling; they make
NO decisions, hold NO try boundaries and stamp NO state) and the five SEQUENCE
methods (``run_mode_nudge``, ``run_setpoint_write``, ``run_ext_temp``,
``run_frost_rescue``, ``run_unavailable_safe``) that own the per-effect TRY
BOUNDARIES and return an ordered ``ExecutionReport``.  The sequences still make
no domain decisions and stamp no domain state — every gate (throttle, guard,
deadband, off-hold, ``should_write``, ``external_feed_due``,
``resolve_safe_state``) is resolved by the caller BEFORE a sequence runs, and
all stamps are folded afterwards by the coordinator's ``commit_execution``.

* **Boundary logging is behaviour** (the logger CHANNEL is observable).  The
  coordinator injects its module logger
  (``custom_components.poise.coordinator``); each sequence emits its exact
  ``_LOGGER.exception(fmt, *args)`` record INSIDE its except — text, level
  (ERROR), channel, traceback and position in the await stream are fixed.  The
  commit path does no logging, so no exception transport is needed on
  ``EffectExecution``.

* **blocking=False is the contract**: every effect write dispatches
  fire-and-forget.  Home Assistant runs the service handler in a background
  task and SWALLOWS handler exceptions there
  (``_run_service_call_catch_exceptions``) — the coordinator's per-effect
  error boundaries therefore only ever see SYNCHRONOUS dispatch errors (e.g.
  ``ServiceNotFound``).  These primitives re-raise them UNCHANGED (no try of
  their own) and must never switch to ``blocking=True``.  The only
  ``blocking=True`` service calls in the integration are the forecast READ
  (``forecast_provider``, ``return_response`` — not an effect write) and the
  deliberate teardown writes in ``__init__.py`` (boiler OFF / actuator park /
  TRV sensor-source restore) — documented exceptions outside this class.

* **Sequence semantics** — owned by the sequence methods, preserved exactly:

  1. Frost rescue: TWO independent try boundaries (mode nudge, floor write) —
     nudge and write are INDEPENDENT: a failed nudge never skips the safety
     floor write, and the hold end (``EndHold("frost_rescue",
     require_success=False)``) stays a post-execution action OUTSIDE both
     boundaries (hold teardown is never coupled to write success; pinned by
     test_phase0_frost_rescue_matrix, all four cells).
  2. Unavailable-safe: ONE shared try around mode write AND setpoint write —
     a mode dispatch error skips the setpoint write, reported as
     ``attempted=False`` (independent boundaries are deferred to F-SAFESEQ).
  3. Ext-temp (ADR-0029): conditional select/feed sequence — a successful
     ``select_option`` SKIPS the feed for that tick (the device settles
     first), reported as ``attempted=False``; a failed select still feeds.
     The coupling is sequence-INTERNAL (``skip_feed_on_select_success``);
     it never surfaces as a commit stamp.

* **Context matrix**: only the enabled-path mode nudge and the tick setpoint
  write carry a context tag; the safe-state pair, the frost-rescue pair, the
  select switch and the ext-temp feed are deliberately untagged (until
  F-CONTEXT).  The tagged sequences CREATE the ``Context`` themselves (before
  the dispatch, so a synchronously failing call still reports its id — attempt
  state, pinned by test_phase0_attempt_success) and report the id via
  ``EffectExecution.context_id``; REGISTERING the id in ``own_context_ids`` is
  the commit's job.  The bare primitives still accept a ready-made ``Context``
  purely as a parameter.

* **Patch surface**: the setpoint path dispatches through the module attribute
  ``actuator_mod.write`` (the same module object the coordinator aliases via
  ``from . import actuator as actuator_mod``), resolved at call time — so
  ``patch.object(actuator_mod, "write", ...)`` keeps intercepting the awaited
  write (test_phase0_attempt_success's injection point).

Payload fine print: setpoint writes send the RAW value on the wire — snapping
to the device step is echo-BASELINE stamping in the coordinator
(``snap_to_step``), never part of the payload; ``ActuatorCommand.hvac_mode``
is not sent (diagnostics only, ADR-0046 §8).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import Context

from .. import actuator as actuator_mod
from ..contracts import ActuatorCommand, ActuatorPath
from ..runtime.tick_result import EffectExecution, ExecutionReport

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..control.lifecycle import SafeStatePlan
    from ..runtime.tick_result import ExternalTemperaturePlan


class ActuatorExecutor:
    """Call primitives + boundary-owning sequence methods.

    The primitives are one exact dispatch each: payload, ``blocking=False``,
    context handling.  Synchronous dispatch errors (``ServiceNotFound`` et al.)
    propagate to the caller UNCHANGED.  The ``run_*`` sequence methods wrap the
    primitives in the try boundaries, log via the injected coordinator logger
    and return an ordered ``ExecutionReport`` (module docstring); they never
    touch domain state — ``commit_execution`` folds the report afterwards.
    """

    def __init__(
        self, hass: HomeAssistant, logger: logging.Logger | None = None
    ) -> None:
        # The coordinator injects its module logger so every boundary record
        # keeps the ``custom_components.poise.coordinator`` channel — the
        # channel is behaviour.  The module-logger fallback exists only for
        # bare primitive use (primitives never log); production wiring must
        # inject.
        self._hass = hass
        self._log = logger if logger is not None else logging.getLogger(__name__)

    async def set_hvac_mode(
        self, entity_id: str, hvac_mode: str, *, context: Context | None = None
    ) -> None:
        """Dispatch one ``climate.set_hvac_mode`` (fire-and-forget).

        Covers all three mode-write sites: the unavailable-safe mode write (no
        context), the enabled-path mode nudge (``context=_own_ctx()`` — one of
        only two tagged sites) and the frost-rescue nudge (deliberately
        untagged).  ``context=None`` is an omitted kwarg (HA then creates a
        fresh, unregistered Context itself).
        """
        await self._hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": hvac_mode},
            blocking=False,
            context=context,
        )

    async def write_setpoint(
        self, command: ActuatorCommand, *, context: Context | None = None
    ) -> None:
        """Dispatch one arbitrated setpoint command via ``actuator_mod.write``.

        Covers the three ``climate.set_temperature`` sites: the
        unavailable-safe floor (reason ``unavailable_safe``, no context), the
        tick setpoint write (reason ``tick``, ``context=_own_ctx()`` — the
        second of the two tagged sites) and the frost-rescue floor (reason
        ``frost_rescue``, no context).  ``command.value`` goes on the wire RAW
        (unsnapped); the module-level dispatch keeps the
        ``patch.object(actuator_mod, "write", ...)`` test injection surface
        intact (module docstring).
        """
        await actuator_mod.write(self._hass, command, context=context)

    async def select_option(self, entity_id: str, option: str) -> None:
        """Dispatch one ``select.select_option`` (fire-and-forget, untagged).

        Covers the TRV sensor-source switch to "external" (ADR-0029).  No
        context parameter on purpose: the site is untagged until F-CONTEXT.
        The select-success -> feed-skip sequence (``switched=True`` for this
        tick) is the caller's semantics, not this primitive's (module
        docstring).
        """
        await self._hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": option},
            blocking=False,
        )

    async def set_number(self, entity_id: str, value: float) -> None:
        """Dispatch one ``number.set_value`` (fire-and-forget, untagged).

        Covers the external-temperature feed (ADR-0029; the value is the
        caller's already-rounded feed).  No context parameter on purpose
        (until F-CONTEXT).
        """
        await self._hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=False,
        )

    # ------------------------------------------------------------------
    # Sequence methods: the try boundaries + boundary logging, ordered
    # ExecutionReport out.  No domain stamps here — the coordinator's
    # ``commit_execution`` folds the report (module docstring).
    # ------------------------------------------------------------------

    async def run_mode_nudge(
        self, entity_id: str, desired_hvac: str, *, mode_changed: bool
    ) -> ExecutionReport:
        """Site 1 — the enabled-path mode nudge.

        One boundary around the tagged ``set_hvac_mode``.  The ``Context`` is
        created BEFORE the dispatch, so the reported ``context_id`` exists even
        when the call throws (attempt state, test_phase0_attempt_success).
        ``mode_changed`` is the caller's dispatch-time evaluation
        (``desired_hvac != last_commanded_hvac``) — the commit cannot recompute
        it after the baseline moved.
        """
        ctx = Context()  # tag our own mode change (attempt state)
        success = False
        try:
            await self.set_hvac_mode(entity_id, desired_hvac, context=ctx)
            success = True
        except Exception:  # noqa: BLE001 - mode nudge is best-effort
            self._log.exception(
                "Poise: set_hvac_mode(%s) failed for %s",
                desired_hvac,
                entity_id,
            )
        return ExecutionReport(
            executions=(
                EffectExecution(
                    effect_id="mode_nudge",
                    attempted=True,
                    success=success,
                    context_id=ctx.id,
                    pre_write_value=None,
                    commanded_value=None,
                    commanded_mode=desired_hvac,
                    mode_changed=mode_changed,
                ),
            )
        )

    async def run_setpoint_write(
        self,
        command: ActuatorCommand,
        *,
        pre_write_value: float | None,
        snapped_value: float,
        final_mode: str,
    ) -> ExecutionReport:
        """Site 2 — the tick setpoint write.

        One boundary around the tagged ``write_setpoint``; ``command.value``
        goes on the wire RAW.  ``pre_write_value`` is the device's reported
        setpoint just before this write (attempt stamp), ``snapped_value`` the
        caller's ``snap_to_step(target, step)`` echo baseline (success stamp —
        NEVER the raw wire value) and ``final_mode`` the mode string for
        ``last_written_mode``.
        """
        ctx = Context()  # tag; created before the dispatch (attempt state)
        success = False
        try:
            await self.write_setpoint(command, context=ctx)
            success = True
        except Exception:  # noqa: BLE001 - never let actuator I/O kill the tick
            self._log.exception(
                "Poise: actuator write failed for %s", command.actuator_id
            )
        return ExecutionReport(
            executions=(
                EffectExecution(
                    effect_id="setpoint_write",
                    attempted=True,
                    success=success,
                    context_id=ctx.id,
                    pre_write_value=pre_write_value,
                    commanded_value=snapped_value,
                    commanded_mode=final_mode,
                ),
            )
        )

    async def run_ext_temp(
        self,
        plan: ExternalTemperaturePlan,
        *,
        select_entity_id: str | None,
        number_entity_id: str,
    ) -> ExecutionReport:
        """Site 3 — TRV sensor-select switch + external-temp feed (ADR-0029).

        TWO boundaries with the sequence-INTERNAL coupling: a successful select
        switch skips the feed for this tick (the device settles first;
        ``skip_feed_on_select_success``), a failed select still feeds.  The
        skipped feed is reported ``attempted=False``; the select's success
        never becomes a commit stamp.  ``plan.feed_value`` is the caller's
        already-rounded, ``external_feed_due``-gated value (``None`` = no feed
        planned this tick).  Both calls are untagged (until F-CONTEXT).
        """
        executions: list[EffectExecution] = []
        switched = False
        if plan.select_external:
            if select_entity_id is None:
                raise ValueError("run_ext_temp: select planned without a select entity")
            select_success = False
            try:
                await self.select_option(select_entity_id, "external")
                select_success = True
                switched = True
            except Exception:  # noqa: BLE001
                self._log.exception("Poise: sensor-select switch failed")
            executions.append(
                EffectExecution(
                    effect_id="ext_select",
                    attempted=True,
                    success=select_success,
                    context_id=None,
                    pre_write_value=None,
                    commanded_value=None,
                )
            )
        if plan.feed_value is not None:
            skipped = switched and plan.skip_feed_on_select_success
            feed_success = False
            if not skipped:
                try:
                    await self.set_number(number_entity_id, plan.feed_value)
                    feed_success = True
                except Exception:  # noqa: BLE001 - feed is best-effort
                    self._log.exception(
                        "Poise: external-temp write failed for %s", number_entity_id
                    )
            executions.append(
                EffectExecution(
                    effect_id="ext_feed",
                    attempted=not skipped,
                    success=feed_success,
                    context_id=None,
                    pre_write_value=None,
                    commanded_value=plan.feed_value,
                )
            )
        return ExecutionReport(executions=tuple(executions))

    async def run_frost_rescue(
        self, entity_id: str, rescue_value: float, *, nudge: bool
    ) -> ExecutionReport:
        """Site 4 — frost/mould rescue.

        TWO INDEPENDENT boundaries: a failed mode nudge never skips the safety
        floor write (both effects are always attempted when planned).
        ``nudge`` is the caller's plan-time decision (``current != 'heat' and
        'heat' in modes``).  Both calls are untagged; the floor command uses
        ``reason='frost_rescue'`` with the raw value on the wire.  The hold end
        is NOT this sequence's business — it travels as
        ``EndHold('frost_rescue', require_success=False)`` through
        ``commit_execution`` (pinned by test_phase0_frost_rescue_matrix).
        """
        executions: list[EffectExecution] = []
        if nudge:
            nudge_success = False
            try:
                await self.set_hvac_mode(entity_id, "heat")
                nudge_success = True
            except Exception:  # noqa: BLE001 - nudge is best-effort
                self._log.exception(
                    "Poise: frost rescue nudge failed for %s", entity_id
                )
            executions.append(
                EffectExecution(
                    effect_id="rescue_nudge",
                    attempted=True,
                    success=nudge_success,
                    context_id=None,
                    pre_write_value=None,
                    commanded_value=None,
                    commanded_mode="heat",
                )
            )
        write_success = False
        try:
            await self.write_setpoint(
                ActuatorCommand(
                    actuator_id=entity_id,
                    path=ActuatorPath.SETPOINT,
                    value=rescue_value,
                    hvac_mode="heat",
                    reason="frost_rescue",
                )
            )
            write_success = True
        except Exception:  # noqa: BLE001 - frost rescue write is best-effort
            self._log.exception("Poise: frost rescue write failed for %s", entity_id)
        executions.append(
            EffectExecution(
                effect_id="rescue_write",
                attempted=True,
                success=write_success,
                context_id=None,
                pre_write_value=None,
                commanded_value=rescue_value,
            )
        )
        return ExecutionReport(executions=tuple(executions))

    async def run_unavailable_safe(
        self, plan: SafeStatePlan, *, entity_id: str, zone_name: str
    ) -> ExecutionReport:
        """Site 5 — unavailable-safe mode + setpoint.

        ONE SHARED boundary around both calls (independent boundaries are
        deferred to F-SAFESEQ): a mode dispatch error skips the setpoint write,
        which is then reported ``attempted=False``.  One log record for
        whichever call threw, with the exact zone-named text.  Both calls
        untagged; the floor command uses ``reason='unavailable_safe'``.
        """
        mode_planned = plan.write_mode
        setpoint_planned = plan.write_setpoint and plan.setpoint is not None
        mode_success = False
        setpoint_attempted = False
        setpoint_success = False
        try:
            if mode_planned:
                await self.set_hvac_mode(entity_id, plan.hvac_mode)
                mode_success = True
            if plan.write_setpoint and plan.setpoint is not None:
                setpoint_attempted = True
                await self.write_setpoint(
                    ActuatorCommand(
                        actuator_id=entity_id,
                        path=ActuatorPath.SETPOINT,
                        value=plan.setpoint,
                        hvac_mode=plan.hvac_mode,
                        reason="unavailable_safe",
                    )
                )
                setpoint_success = True
        except Exception:  # noqa: BLE001 - safe-state write must never kill the tick
            self._log.exception("Poise %s: unavailable-safe write failed", zone_name)
        executions: list[EffectExecution] = []
        if mode_planned:
            executions.append(
                EffectExecution(
                    effect_id="safe_mode",
                    attempted=True,
                    success=mode_success,
                    context_id=None,
                    pre_write_value=None,
                    commanded_value=None,
                    commanded_mode=plan.hvac_mode,
                )
            )
        if setpoint_planned:
            executions.append(
                EffectExecution(
                    effect_id="safe_setpoint",
                    attempted=setpoint_attempted,
                    success=setpoint_success,
                    context_id=None,
                    pre_write_value=None,
                    commanded_value=plan.setpoint,
                )
            )
        return ExecutionReport(executions=tuple(executions))
