"""Repair-issue reporting — the coordinator's HEALTH block, lifted out.

``coordinator.py`` keeps the HA coupling (``DataUpdateCoordinator`` lifecycle,
the tick lock, ``tick_ms``/``TickBudget``, persistence and the entity-facing
command API); the methods that translate Poise health into Home Assistant
repair issues live here: the transition-only ``issue()`` primitive, the
``emit()`` checkpoint primitive the tick flow drives, the ``notify_*``
checkpoint facades (heating/cooling failure, write convergence), the three
``sync_*_issue`` suggestion mirrors (idempotent per-tick create/delete, P3)
and the setup-time ``validate_configured_ext_temp()``.

The logger CHANNEL is behaviour: records must keep the name
``custom_components.poise.coordinator``, so the coordinator injects its
module logger as ``self._log``.

EMISSION POSITIONS ARE BEHAVIOUR (binding).  Nothing here defers, batches or
re-orders a create/delete.  ``issue()`` keeps its transition-only semantics
(create only on False->True, delete only on True->False) so a repeated call
with an unchanged flag stays a no-op, and ``emit()`` walks its tuple in the
given order.  Every ``notify_*`` facade is called from the tick flow as a
SYNCHRONOUS checkpoint at its position (mid-stage for the failure pair,
directly after the setpoint segment and on the disabled path for
convergence) — none may become a coroutine or be deferred to a stage end;
the three ``issue()`` calls inside ``validate_configured_ext_temp`` keep
their positions around the one await.

OWNED STATE, NOT BORROWED (plan S.3).  The reporter holds an ``IssueLedger``
— the set of repair-issue ids this entry currently owns — plus the entry
identity it stamps into issue ids and placeholders.  It used to reach all of
that through a coordinator backreference, for one concrete reason:
``PoiseCoordinator.async_bootstrap`` RE-ADOPTED the entry's issues by
*rebinding* ``self._active_issues``, so a set snapshotted here would have
decoupled at that moment.  ``IssueLedger.adopt()`` replaces the content in
place instead, which removed the reason and with it the backreference.  The
siblings ``_save_failures`` / ``_tick_failures`` stay coordinator-owned: their
only writers (``_note_save_result`` and ``_async_update_data``) live there.

``validate_configured_ext_temp`` no longer writes the coordinator's
``_trv_ext_temp`` either — it REPORTS whether the configured entity survives
validation and the coordinator performs the invalidation.  One field, one
writer, and the reporter needs nothing but its own inputs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from ..const import DOMAIN

if TYPE_CHECKING:
    from ..control.feedback import CloSuggestion
    from ..control.suggestion import OverrideSuggestion
from ..contracts import ActuatorPath
from ..devices.capability import (
    DeviceCapabilities,
    reliable_heat_mode_from,
    select_live_path,
)
from ..devices.model_fixes import (
    ext_temp_number_is_implausible,
)
from ..runtime.issue_ledger import IssueLedger
from ..runtime.tick_result import HealthUpdate
from .input_reader import InputReader


class HealthReporter:
    """Owns the repair-issue surface; one instance per ``PoiseCoordinator``.

    Constructed in ``PoiseCoordinator.__init__`` after the ``InputReader`` and
    before the ``TickOrchestrator`` (which receives ``emit`` as its health
    checkpoint callable), so every collaborator handed over already exists.
    """

    __slots__ = (
        "_actuator",
        "_entry_id",
        "_hass",
        "_issues",
        "_log",
        "_reader",
        "_zone_name",
    )

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        logger: logging.Logger,
        input_reader: InputReader,
        issues: IssueLedger,
        entry_id: str,
        zone_name: str,
        actuator: str,
    ) -> None:
        self._hass = hass
        # The coordinator module's own logger: the channel
        # ``custom_components.poise.coordinator`` is behaviour, so it is
        # injected rather than created here.
        self._log = logger
        self._reader = input_reader
        self._issues = issues
        # Identity, copied at construction. Safe because a change to
        # ``entry.data`` RELOADS the entry (see
        # ``PoiseCoordinator.structural_unchanged``), which builds a new
        # coordinator and with it a new reporter — unlike ``_trv_ext_temp``,
        # which mutates within a run and is therefore passed per call.
        self._entry_id = entry_id
        self._zone_name = zone_name
        self._actuator = actuator

    def issue(
        self,
        issue_id: str,
        active: bool,
        *,
        translation_key: str,
        placeholders: dict[str, str] | None = None,
    ) -> None:
        """Raise/clear a Home Assistant repair issue on transitions (ADR-0012)."""
        if active and issue_id not in self._issues:
            self._issues.add(issue_id)
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=translation_key,
                translation_placeholders=placeholders or {},
            )
        elif not active and issue_id in self._issues:
            self._issues.discard(issue_id)
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)

    def emit(self, updates: tuple[HealthUpdate, ...]) -> None:
        """Checkpoint primitive: apply stage-collected ``HealthUpdate``s to
        the issue registry, in order.

        Stages no longer write to the registry mid-body; they collect typed
        updates in per-issue evaluation order and the tick flow emits them at
        stage checkpoints whose positions preserve the emission points
        relative to the awaits. ``issue`` keeps the transition-only
        create/delete semantics, so a collected clear (``active=False``)
        deletes exactly as an inline call would.
        """
        for update in updates:
            self.issue(
                update.issue_id,
                update.active,
                translation_key=update.translation_key,
                placeholders=(
                    dict(update.placeholders)
                    if update.placeholders is not None
                    else None
                ),
            )

    def notify_failure(self, failed: bool) -> None:
        """Surface a persistent heating failure as a translated repair issue.

        Raised while ``failed``, cleared when it recovers, so the message is
        localised via ``translations/*`` like every other Poise diagnostic.
        Runs as a synchronous checkpoint emission inside the failure-detect
        stage.
        """
        self.emit(
            (
                HealthUpdate(
                    issue_id=f"heating_failure_{self._entry_id}",
                    active=failed,
                    translation_key="heating_failure",
                    placeholders={"zone": self._zone_name},
                ),
            )
        )

    def notify_cooling_failure(self, failed: bool) -> None:
        """Cooling pendant to :meth:`notify_failure` (review C.8) — same
        transition-only semantics, synchronous checkpoint emission inside the
        failure-detect stage."""
        self.emit(
            (
                HealthUpdate(
                    issue_id=f"cooling_failure_{self._entry_id}",
                    active=failed,
                    translation_key="cooling_failure",
                    placeholders={"zone": self._zone_name},
                ),
            )
        )

    def notify_convergence(self, active: bool) -> None:
        """Surface persistent write non-convergence as a repair issue (C.8).

        Raised while the watchdog escalates (the actuator keeps ignoring our
        setpoint/mode commands), cleared when a command finally lands or the
        evidence episode expires — transition-only like every other issue.
        Emitted synchronously right after the setpoint segment; the
        disabled/off-hold path clears it explicitly.
        """
        self.emit(
            (
                HealthUpdate(
                    issue_id=f"actuator_not_converging_{self._entry_id}",
                    active=active,
                    translation_key="actuator_not_converging",
                    placeholders={"zone": self._zone_name},
                ),
            )
        )

    def sync_clo_suggestion_issue(
        self, suggestion: CloSuggestion | None, *, enabled: bool
    ) -> None:
        """ADR-0067 F2: mirror the emittable clo reading into a fixable issue.

        Moved here from the coordinator (review 2026-08-19 P3) — the reporter
        owns the whole repair-issue surface. DELIBERATELY not routed through
        ``issue()``/the ledger: these suggestion mirrors are idempotent
        per-tick create/delete (``async_create_issue`` is idempotent), not
        transition-only, and the gate toggle is coordinator-owned tuning, so
        it arrives per call (``enabled``) like ``_trv_ext_temp`` does. Same
        trust rules as L2 (ADR-0060 §3: default on, per-zone opt-out); the
        caller already resolved the #4 conflict, so ``None`` here also covers
        a blocked reading.
        """
        issue_id = f"clo_suggestion_{self._entry_id}"
        if not (enabled and suggestion):
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=(
                "clo_suggestion_up"
                if suggestion.direction > 0
                else "clo_suggestion_down"
            ),
            translation_placeholders={
                "name": self._zone_name,
                "count": str(suggestion.evidence),
                # Mirrors control.feedback.CLO_SUGGEST_STEP (display only).
                "step": "0.1",
            },
            data={
                "entry_id": self._entry_id,
                "kind": "clo_offset",
                "direction": suggestion.direction,
                "key": suggestion.key,
            },
        )

    def sync_suggestion_issue(
        self,
        suggestion: OverrideSuggestion | None,
        suppressed: bool,
        *,
        enabled: bool,
    ) -> None:
        """Mirror the detected L2 pattern into a fixable repair issue.

        Moved here from the coordinator (review 2026-08-19 P3); see
        ``sync_clo_suggestion_issue`` for why it bypasses the ledger. Emission
        is gated on the ``override_suggestions`` toggle (ADR-0060 §3); the
        issue disappears as soon as the pattern does.
        """
        issue_id = f"override_suggestion_{self._entry_id}"
        if not (enabled and suggestion and not suppressed):
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
            return
        if suggestion.kind == "comfort_base":
            translation_key = (
                "override_suggestion_base_up"
                if suggestion.direction > 0
                else "override_suggestion_base_down"
            )
            step = f"{suggestion.step_k:.1f}"
        else:
            translation_key = "override_suggestion_earlier"
            step = str(suggestion.step_min)
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=translation_key,
            translation_placeholders={
                "name": self._zone_name,
                "count": str(suggestion.evidence),
                "step": step,
            },
            data={
                "entry_id": self._entry_id,
                "kind": suggestion.kind,
                "direction": suggestion.direction,
                "key": suggestion.key,
            },
        )

    def sync_calibration_available_issue(
        self, *, ext_temp_reserved: bool, enabled: bool
    ) -> None:
        """P1.5 D1: mirror "this zone COULD calibrate if you opted in" into a
        fixable repair issue (kind ``trv_calibration``).

        Active exactly when the D6 path choice WOULD pick calibration were
        the option on (``calibration_enabled=True`` forced through the same
        ``select_live_path`` the segments use — an external-temp input still
        wins) AND the option is currently off. The capability build mirrors
        ``ActuatePhase._calibration_live_path`` (null-safe hvac_modes, F29);
        the actuator read goes through the reader, keeping the S.4a read
        boundary. Bypasses the ledger like the other suggestion mirrors
        (idempotent per-tick create/delete). Its fix flow is Apply-ONLY (D1):
        no ``direction``, no cool-down stamp — rejection is HA's built-in
        "ignore issue", so the mirror keeps re-creating idempotently and HA
        keeps it hidden.
        """
        issue_id = f"calibration_available_{self._entry_id}"
        act_state = self._reader.actuator_state()
        hvac_modes = (
            [str(m) for m in (act_state.attributes.get("hvac_modes") or [])]
            if act_state is not None
            else []
        )
        caps = DeviceCapabilities(
            writable_valve=self._reader.valve_entity is not None,
            writable_calibration=self._reader.calibration_entity is not None,
            reliable_heat_mode=reliable_heat_mode_from(hvac_modes),
        )
        capable = (
            select_live_path(
                caps, ext_temp_reserved=ext_temp_reserved, calibration_enabled=True
            )
            is ActuatorPath.CALIBRATION
        )
        if not (capable and not enabled):
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="calibration_available",
            translation_placeholders={"name": self._zone_name},
            data={"entry_id": self._entry_id, "kind": "trv_calibration"},
        )

    def sync_season_hint_issue(
        self,
        hint: str | None,
        *,
        enabled: bool,
        threshold: float,
        t_rm: float | None,
    ) -> None:
        """ADR-0060 §2: mirror the season-mode advisory into a repair issue.

        Moved here from the coordinator (review 2026-08-19 P3). NON-fixable
        (purely advisory — the user switches the mode, never Poise); same
        trust rules as L2, and the issue disappears as soon as the condition
        does. ``threshold`` and ``t_rm`` are coordinator-owned readings and
        arrive per call.
        """
        issue_id = f"season_mode_hint_{self._entry_id}"
        if not (enabled and hint):
            ir.async_delete_issue(self._hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"season_hint_{hint}",
            translation_placeholders={
                "name": self._zone_name,
                "t_rm": str(t_rm) if t_rm is not None else "?",
                "threshold": f"{threshold:.0f}",
            },
        )

    async def validate_configured_ext_temp(self, entity_id: str | None) -> bool:
        """Vet the *configured* external-temp number once (not per tick).

        A value the user picked EXPLICITLY via CONF_TRV_EXTERNAL_TEMP is trusted
        unless it shows a POSITIVE non-temperature signal (a non-temperature
        device_class or unit, e.g. a valve's "%") — so a legitimately
        renamed/localised temperature input is NOT dropped on upgrade. On a real
        mismatch: stop feeding it AND hand the TRV's sensor source back to
        internal, or the device would keep regulating against a now-frozen
        external value; then raise a repair issue. When plausible or unset,
        clear it. A registry miss must never block setup.

        Returns whether the configured entity may keep feeding the TRV. The
        caller owns ``_trv_ext_temp`` and performs the invalidation (S.3):
        this method reports, it does not reach back.
        """
        issue_id = f"external_temp_implausible_{self._entry_id}"
        if not entity_id:
            self.issue(issue_id, False, translation_key="external_temp_implausible")
            return True
        try:
            # The registry/state signature read lives in the reader; its
            # errors propagate into THIS try — the "a registry miss must never
            # block setup" boundary stays here.
            device_class, unit = self._reader.configured_ext_temp_signature(entity_id)
            implausible = ext_temp_number_is_implausible(entity_id, device_class, unit)
        except Exception:  # noqa: BLE001 - a registry miss must not block setup
            self._log.debug(
                "Poise: external-temp validation failed for %s",
                entity_id,
                exc_info=True,
            )
            return True
        if not implausible:
            self.issue(issue_id, False, translation_key="external_temp_implausible")
            return True
        # Implausible: hand the TRV sensor source back to internal so the
        # device does not regulate against a frozen value. Dropping the feed
        # itself is the caller's write (S.3): one field, one writer.
        try:
            # Documented write-gate exception: this restore deliberately
            # DELEGATES to the shared lifecycle helper (same module the entry
            # teardown and the config_flow park use) instead of the tick
            # executor — a one-shot setup-time write with its own blocking
            # semantics, not a tick effect. The write-boundary gate's
            # actuator_lifecycle exception covers its service calls.
            from .actuator_lifecycle import restore_trv_internal

            await restore_trv_internal(self._hass, self._actuator)
        except Exception:  # noqa: BLE001 - best-effort restore must not block setup
            self._log.debug(
                "Poise: TRV sensor-source restore after ext-temp reject failed",
                exc_info=True,
            )
        self.issue(
            issue_id,
            True,
            translation_key="external_temp_implausible",
            placeholders={"entity": entity_id, "name": self._zone_name},
        )
        return False
