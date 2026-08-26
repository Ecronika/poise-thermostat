"""Actuator hand-back lifecycle: park + TRV sensor-source restore (HA glue).

One implementation for every place Poise gives an actuator back — room
delete/disable (``__init__._park_room_actuator``), the reconfigure actuator
swap (``config_flow._park_replaced_actuator``) and the ext-temp invalidation
(``ha.health_reporter``). Extracted per review 2026-08-19 P1: the two park
copies had already drifted — the reconfigure path clamped the setback up to
the device's ``min_temp`` (so a high-min heat pump / split AC does not reject
a sub-min setpoint and silently stay on the old comfort value) while the
delete/disable path did not. The state read, the ``resolve_park_command``
call and the execution live HERE so that clamp cannot fork again; the POLICY
differences stay at the callers (the ``has_actuated`` store gate on
delete/disable, the climate-mode source: Store on delete/disable per AR-13,
live runtime on reconfigure).

The same extraction removes the backward imports into the package root:
``config_flow`` and ``health_reporter`` used to pull ``_execute_park`` /
``_restore_trv_internal`` out of ``__init__.py``, making the composition
root double as the utility layer. Now all three consumers import DOWN into
this module.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from ..const import FROST_FLOOR_C
from ..control.calibration import snap_offset
from ..control.lifecycle import ParkPlan, resolve_park_command
from ..devices.model_fixes import is_external_sensor_select
from .input_reader import CalibrationMeta, read_calibration_meta

_LOGGER = logging.getLogger(__name__)

# AR-24 precedent (`__init__` boiler OFF, `hub_coordinator` boiler actions,
# both 10 s): a blocking service call at a lifecycle position must be bounded,
# because a hung number integration would otherwise freeze exactly the paths
# that cannot afford it — the coordinator's reconfigure handoff port awaits
# the restore INSIDE the tick lock (a hang would stall the zone's tick loop),
# and the config-flow/teardown callers would hang the dialog or the entry
# removal. Same magnitude as the boiler constant; a dedicated name because
# this module must not import the hub.
_CALIBRATION_RESTORE_TIMEOUT_S = 10.0


class CalibrationRestoreResult(Enum):
    """Outcome of the D3 lifecycle restore (P1.5, review Rev. 2.3 point 3)."""

    RESTORED = "restored"  # device REPORTS the restore_target (state-confirmed)
    GONE = "gone"  # entity structurally removed — nothing an offset acts on
    FAILED = "failed"  # unreadable / dispatch error / read-back not at target


async def restore_trv_calibration(
    hass: HomeAssistant, *, entity_id: str, baseline: float
) -> CalibrationRestoreResult:
    """D3 lifecycle restore: blocking write + FRESH read-back.

    ``blocking=True`` only makes service errors synchronously visible (F15) —
    the D3 confirmation is the read-back afterwards: when the entity reports
    ``restore_target ± step/2`` it is restored. No polling: a slow device
    yields a conservative FAILED, and the next attempt recognizes
    already_at_target immediately. Registry AND state both gone -> GONE.
    The target is the SNAPPED baseline (never a blanket 0.0, D3): a baseline
    outside the entity's current grid restores clipped, best-possible.
    """
    meta = read_calibration_meta(hass, entity_id)  # P1.1 tri-state, shared
    if meta == "gone":
        return CalibrationRestoreResult.GONE
    if not isinstance(meta, CalibrationMeta):  # "unreadable" -> fail-closed
        return CalibrationRestoreResult.FAILED
    restore_target = snap_offset(
        baseline, step=meta.step, min_value=meta.lo, max_value=meta.hi
    )
    if abs(meta.reported - restore_target) <= meta.step / 2 + 1e-9:
        return CalibrationRestoreResult.RESTORED  # already_at_target
    try:
        # AR-24: bound the blocking write (see _CALIBRATION_RESTORE_TIMEOUT_S)
        # — a TimeoutError lands in the same boundary as any dispatch error
        # and maps onto the existing fail-closed semantics: FAILED, ownership
        # kept, form error on reconfigure / warning on teardown.
        async with asyncio.timeout(_CALIBRATION_RESTORE_TIMEOUT_S):
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": restore_target},
                blocking=True,
            )
    except Exception:  # noqa: BLE001 - any dispatch error is a FAILED restore
        _LOGGER.exception("Poise: calibration restore failed for %s", entity_id)
        return CalibrationRestoreResult.FAILED
    # FRESH re-read after the write — no cached meta: only the device
    # actually showing the target counts as restored (D3, review point 2).
    meta_after = read_calibration_meta(hass, entity_id)
    if (
        isinstance(meta_after, CalibrationMeta)
        and abs(meta_after.reported - restore_target) <= meta_after.step / 2 + 1e-9
    ):
        return CalibrationRestoreResult.RESTORED
    return CalibrationRestoreResult.FAILED


async def resolve_restore(
    hass: HomeAssistant, *, entity_id: object, baseline: object
) -> CalibrationRestoreResult:
    """The ONE corrupt-shape rule in front of the restore (P1.5b review).

    A persisted ownership pair whose entity is missing/empty or whose
    baseline is not a number is structurally ``GONE`` — the commit stamps
    both together, so such a shape can only be store corruption, and there is
    nothing a restore could act on (same rule segment H applies). A valid
    pair delegates to :func:`restore_trv_calibration`. Shared by the
    coordinator handoff port, the config flow's unloaded store path and the
    entry teardown, so the rule cannot fork; the FAILED/GONE POLICY (form
    error vs. WARN vs. teardown log) stays with each caller.
    """
    if not isinstance(baseline, (int, float)) or not (
        isinstance(entity_id, str) and entity_id
    ):
        return CalibrationRestoreResult.GONE
    return await restore_trv_calibration(
        hass, entity_id=entity_id, baseline=float(baseline)
    )


async def park_actuator(
    hass: HomeAssistant,
    actuator: str,
    *,
    climate_mode: str,
    setback_setpoint: float,
) -> None:
    """Park ``actuator`` in a capability-appropriate end state and restore a
    TRV sensor source to internal (F3/F6/AR-12).

    Reads the device state itself (hvac modes AND ``min_temp``) so every
    caller gets the ``device_min`` clamp of ``resolve_park_command``; the
    caller supplies only policy: the live climate mode and the setback level.
    """
    st = hass.states.get(actuator)
    modes = (
        [str(m) for m in (st.attributes.get("hvac_modes") or [])]
        if st is not None
        else []
    )
    device_min = st.attributes.get("min_temp") if st is not None else None
    plan = resolve_park_command(
        is_valve=actuator.startswith("number."),
        hvac_modes=modes,
        heats_for_zone="heat" in modes and climate_mode != "cool_only",
        setback_setpoint=setback_setpoint,
        floor=FROST_FLOOR_C,
        device_min=float(device_min) if device_min is not None else None,
    )
    await execute_park(hass, actuator, plan)
    await restore_trv_internal(hass, actuator)


async def execute_park(
    hass: HomeAssistant, actuator: str, plan: ParkPlan | None
) -> None:
    """Perform the resolved park command on hand-back (review F3/F27).

    Blocking on every call (AR-17/F27) so an execution error surfaces instead
    of being lost as a fire-and-forget background task, and ``set_hvac_mode``
    is awaited BEFORE ``set_temperature`` so a device that only accepts a
    setpoint in its target mode honours it. Expected execution errors are
    caught and logged, not silently swallowed.
    """
    if plan is None:
        return
    try:
        if plan.kind == "valve":
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": actuator, "value": plan.valve_value},
                blocking=True,
            )
            return
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": actuator, "hvac_mode": plan.hvac_mode},
            blocking=True,
        )
        if plan.setpoint is not None:
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": actuator, "temperature": plan.setpoint},
                blocking=True,
            )
    except (HomeAssistantError, ValueError):
        _LOGGER.exception("Poise: actuator park on hand-back failed")


async def restore_trv_internal(hass: HomeAssistant, actuator: str) -> None:
    """Flip a TRV sensor-source select back to 'internal' so a handed-back zone
    no longer regulates the device against a now-frozen external feed (review F6).

    Only touches a select the repo's own classifier recognises as a sensor-source
    switch (``is_external_sensor_select`` — must expose BOTH 'external' and
    'internal', AR-18) and skips one already 'internal' (idempotent, no needless
    write).
    """
    try:
        reg = er.async_get(hass)
        ent = reg.async_get(actuator)
        if ent is None or ent.device_id is None:
            return
        for dev_ent in er.async_entries_for_device(reg, ent.device_id):
            if dev_ent.domain != "select":
                continue
            st = hass.states.get(dev_ent.entity_id)
            if st is None:
                continue
            options = st.attributes.get("options") or []
            # AR-18: only a genuine internal/external sensor-source select.
            if not is_external_sensor_select(dev_ent.entity_id, options):
                continue
            # AR-18: already internal -> nothing to do (idempotent, no thrash).
            if st.state == "internal":
                continue
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": dev_ent.entity_id, "option": "internal"},
                blocking=False,
            )
    except Exception:  # noqa: BLE001 - sensor-source restore is best-effort
        _LOGGER.exception("Poise: TRV sensor-source restore failed")
