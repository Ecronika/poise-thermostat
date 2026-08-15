"""Repair-issue reporting — the coordinator's HEALTH block, lifted out.

``coordinator.py`` keeps the HA coupling (``DataUpdateCoordinator`` lifecycle,
the tick lock, ``tick_ms``/``TickBudget``, persistence and the entity-facing
command API); the four methods that translate Poise health into Home Assistant
repair issues live here: the transition-only ``issue()`` primitive, the
``emit()`` checkpoint primitive the tick flow drives, the heating-failure
``notify_failure()`` and the setup-time ``validate_configured_ext_temp()``.

The logger CHANNEL is behaviour: records must keep the name
``custom_components.poise.coordinator``, so the coordinator injects its
module logger as ``self._log``.

EMISSION POSITIONS ARE BEHAVIOUR (binding).  Nothing here defers, batches or
re-orders a create/delete.  ``issue()`` keeps its transition-only semantics
(create only on False->True, delete only on True->False) so a repeated call
with an unchanged flag stays a no-op, and ``emit()`` walks its tuple in the
given order.  ``notify_failure()`` is called from
``TickOrchestrator._stage_failure_detect`` as a SYNCHRONOUS checkpoint in the
middle of the stage — it must never become a coroutine and must never be
deferred to the stage end; the three ``issue()`` calls inside
``validate_configured_ext_temp`` keep their positions around the one await.

NO OWN STATE (binding).  ``_active_issues`` deliberately stays a real
coordinator attribute and is read/written through ``self._c`` on every call:
``PoiseCoordinator.async_bootstrap`` REBINDS it (``self._active_issues =
{...}``) when it re-adopts the entry's issues after a restart, so a set object
snapshotted here would silently decouple at that point.  It is also pinned as
adapter-owned by ``tests/integration/test_phase6b_state_move.py``.  The
siblings ``_save_failures`` / ``_tick_failures`` stay coordinator-owned for the
same reason: their only writers (``_note_save_result`` and
``_async_update_data``) remain in the coordinator.

TRANSITIONAL COORDINATOR BACKREFERENCE.  ``self._c`` is a documented
transition form (same rule as ``TickOrchestrator``): it carries
``_active_issues``, ``_entry_id``, ``zone_name`` and the config attributes the
moved bodies read verbatim (``_trv_ext_temp``, ``_actuator``) plus the one
write those bodies perform (``_trv_ext_temp = None``).  A later step narrows
it; nothing here may rely on it growing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from ..const import DOMAIN
from ..devices.model_fixes import (
    ext_temp_number_is_implausible,
)
from ..runtime.tick_result import HealthUpdate
from .input_reader import InputReader

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids the import cycle
    from ..coordinator import PoiseCoordinator


class HealthReporter:
    """Owns the repair-issue surface; one instance per ``PoiseCoordinator``.

    Constructed in ``PoiseCoordinator.__init__`` after the ``InputReader`` and
    before the ``TickOrchestrator`` (which receives ``emit`` as its health
    checkpoint callable), so every collaborator handed over already exists.
    """

    __slots__ = ("_c", "_hass", "_log", "_reader")

    def __init__(
        self,
        coordinator: PoiseCoordinator,
        *,
        hass: HomeAssistant,
        logger: logging.Logger,
        input_reader: InputReader,
    ) -> None:
        # Transitional backreference for ``_active_issues``, ``_entry_id``,
        # ``zone_name`` and the config attributes — see the module docstring.
        self._c = coordinator
        self._hass = hass
        # The coordinator module's own logger: the channel
        # ``custom_components.poise.coordinator`` is behaviour, so it is
        # injected rather than created here.
        self._log = logger
        self._reader = input_reader

    def issue(
        self,
        issue_id: str,
        active: bool,
        *,
        translation_key: str,
        placeholders: dict[str, str] | None = None,
    ) -> None:
        """Raise/clear a Home Assistant repair issue on transitions (ADR-0012)."""
        if active and issue_id not in self._c._active_issues:
            self._c._active_issues.add(issue_id)
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=translation_key,
                translation_placeholders=placeholders or {},
            )
        elif not active and issue_id in self._c._active_issues:
            self._c._active_issues.discard(issue_id)
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
                    issue_id=f"heating_failure_{self._c._entry_id}",
                    active=failed,
                    translation_key="heating_failure",
                    placeholders={"zone": self._c.zone_name},
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
                    issue_id=f"cooling_failure_{self._c._entry_id}",
                    active=failed,
                    translation_key="cooling_failure",
                    placeholders={"zone": self._c.zone_name},
                ),
            )
        )

    def notify_convergence(self, active: bool) -> None:
        """Surface persistent write non-convergence as a repair issue (C.8).

        Raised while the watchdog escalates (the actuator keeps ignoring our
        setpoint/mode commands), cleared when a command finally lands —
        transition-only like every other issue. Runs as a synchronous
        checkpoint emission right after the setpoint segment.
        """
        self.emit(
            (
                HealthUpdate(
                    issue_id=f"actuator_not_converging_{self._c._entry_id}",
                    active=active,
                    translation_key="actuator_not_converging",
                    placeholders={"zone": self._c.zone_name},
                ),
            )
        )

    async def validate_configured_ext_temp(self) -> None:
        """Vet the *configured* external-temp number once (not per tick).

        A value the user picked EXPLICITLY via CONF_TRV_EXTERNAL_TEMP is trusted
        unless it shows a POSITIVE non-temperature signal (a non-temperature
        device_class or unit, e.g. a valve's "%") — so a legitimately
        renamed/localised temperature input is NOT dropped on upgrade. On a real
        mismatch: stop feeding it AND hand the TRV's sensor source back to
        internal, or the device would keep regulating against a now-frozen
        external value; then raise a repair issue. When plausible or unset,
        clear it. A registry miss must never block setup.
        """
        issue_id = f"external_temp_implausible_{self._c._entry_id}"
        entity_id = self._c._trv_ext_temp
        if not entity_id:
            self.issue(issue_id, False, translation_key="external_temp_implausible")
            return
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
            return
        if not implausible:
            self.issue(issue_id, False, translation_key="external_temp_implausible")
            return
        # Implausible: never feed it, and hand the TRV sensor source back to
        # internal so the device does not regulate against a frozen value.
        self._c._trv_ext_temp = None
        try:
            # Documented write-gate exception: this restore deliberately
            # DELEGATES to __init__.py's lifecycle helper (shared with entry
            # teardown and the config_flow park) instead of the tick executor
            # — a one-shot setup-time write with its own blocking semantics,
            # not a tick effect. The write-boundary gate's __init__.py
            # exception covers its service calls.
            from .. import _restore_trv_internal

            await _restore_trv_internal(self._hass, self._c._actuator)
        except Exception:  # noqa: BLE001 - best-effort restore must not block setup
            self._log.debug(
                "Poise: TRV sensor-source restore after ext-temp reject failed",
                exc_info=True,
            )
        self.issue(
            issue_id,
            True,
            translation_key="external_temp_implausible",
            placeholders={"entity": entity_id, "name": self._c.zone_name},
        )
