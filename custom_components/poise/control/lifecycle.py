"""Pure lifecycle/teardown resolvers (2026-07-08 adversarial review: F1/F3/F4/F12).

HA-free (ADR-0005/0011): the coordinator/glue reads device state and performs
the service calls; every *decision* about which safe / park / off state to
command lives here so the hardware-affecting logic is unit-tested, not
0%-covered in the glue.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SafeStatePlan:
    """What to command after a sustained room-sensor loss (review F1)."""

    hvac_mode: str  # "heat" | "off"
    setpoint: float | None  # None on the off path
    write_mode: bool  # send set_hvac_mode?
    write_setpoint: bool  # send set_temperature?


def resolve_safe_state(
    *,
    hvac_modes: list[str],
    device_state: str | None,
    device_setpoint: float | None,
    device_min: float | None,
    floor: float,
) -> SafeStatePlan | None:
    """The safe state after a sustained room-sensor loss (review F1).

    A heat-capable actuator holds the frost/mould floor in heat (fail toward
    warmth), clamped up to the device ``min_temp`` so a high-min AC does not
    thrash on the echo it cannot honour; a cool-only actuator is commanded off
    (it must never cool the room to the floor).

    The mode nudge and the setpoint write are decided INDEPENDENTLY, and each is
    skipped only when the device already matches — so a device in ``cool`` /
    ``auto`` / ``off`` actually receives the ``set_hvac_mode('heat')`` it needs
    (the review-F1 bug: the old idempotency check required ``state == 'heat'`` and
    could never fire the mode for a multi-mode device). Returns ``None`` when
    nothing needs to change.
    """
    if "heat" in hvac_modes:
        target = floor if device_min is None else max(floor, device_min)
        write_mode = device_state != "heat"
        write_setpoint = device_setpoint is None or abs(device_setpoint - target) > 1e-6
        if not write_mode and not write_setpoint:
            return None
        return SafeStatePlan("heat", target, write_mode, write_setpoint)
    # cool-only / no heat capability: never cool toward the floor -> off
    if device_state not in ("off", "unavailable", None):
        return SafeStatePlan("off", None, True, False)
    return None


@dataclass(frozen=True, slots=True)
class ParkPlan:
    """The end state to leave an actuator in when a room entry is deleted (F3)."""

    kind: str  # "climate" | "valve"
    hvac_mode: str | None  # "heat" | "off" for climate; None for a valve
    setpoint: float | None  # climate heat setback; None otherwise
    valve_value: float | None  # 0.0 for a valve; None otherwise


def resolve_park_command(
    *,
    is_valve: bool,
    hvac_modes: list[str],
    heats_for_zone: bool,
    setback_setpoint: float | None,
    floor: float,
    device_min: float | None = None,
) -> ParkPlan | None:
    """Capability-dependent park state on room-entry deletion (review F3).

    Never a blanket ``off``:

    * a writable valve ``number`` -> closed (0 %); a valve without a controller
      must not stay open (frost duty then lives at the system level).
    * a self-regulating heater the zone relies on -> ``heat`` at the user's
      setback level (``comfort_base - setback_delta``), floored at the
      frost/mould floor, so the device keeps itself warm autonomously — no
      unattended full-heat, no frost/mould risk, no "Poise turned the heating
      off" cold surprise after a mere reconfigure.
    * a cool-only / reversible device with no heating duty -> ``off`` (the risk
      here is unattended cooling).

    Also flips a TRV sensor source back to internal at the call site (review F6).
    """
    if is_valve:
        return ParkPlan("valve", None, None, 0.0)
    if heats_for_zone and "heat" in hvac_modes:
        sp = floor if setback_setpoint is None else max(floor, setback_setpoint)
        # AR-10: clamp up to the device min so a high-min heater (heat pump / split
        # AC) does not silently reject a sub-min setback and stay on the old comfort
        # setpoint — symmetric with resolve_safe_state.
        if device_min is not None:
            sp = max(sp, device_min)
        return ParkPlan("climate", "heat", round(sp, 1), None)
    return ParkPlan("climate", "off", None, None)


def resolve_hub_unload_off(
    *,
    was_actuating: bool,
    disabled: bool,
    still_actuating: bool,
    target_changed: bool = False,
) -> bool:
    """Fire the boiler OFF on hub unload only at a genuine hand-over (F4/F12/AR-01).

    True iff Poise was actuating the boiler AND control is being relinquished —
    the entry is being disabled, the reconfigured data no longer wires actuation
    (ON+OFF), OR the reconfigure points the boiler at a DIFFERENT target
    (``target_changed``) so the OLD boiler must be handed back rather than left
    running. A plain reload onto the SAME target keeps hands off, and a hub that
    was only ever shadow-only never fires an OFF it never commanded. When
    ``target_changed`` fires the OFF, the caller must send it to the OLD action.
    """
    return was_actuating and (disabled or not still_actuating or target_changed)
