"""Repair-issue reporting — the coordinator's HEALTH block, lifted out.

``coordinator.py`` keeps the HA coupling (``DataUpdateCoordinator`` lifecycle,
the tick lock, ``tick_ms``/``TickBudget``, persistence and the entity-facing
command API); the methods that translate Poise health into Home Assistant
repair issues live here: the transition-only ``issue()`` primitive, the
``emit()`` checkpoint primitive the tick flow drives, the ``notify_*``
checkpoint facades (heating/cooling failure, write convergence) and the
setup-time ``validate_configured_ext_temp()``.

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

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from ..const import DOMAIN
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
            # DELEGATES to __init__.py's lifecycle helper (shared with entry
            # teardown and the config_flow park) instead of the tick executor
            # — a one-shot setup-time write with its own blocking semantics,
            # not a tick effect. The write-boundary gate's __init__.py
            # exception covers its service calls.
            from .. import _restore_trv_internal

            await _restore_trv_internal(self._hass, self._actuator)
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
