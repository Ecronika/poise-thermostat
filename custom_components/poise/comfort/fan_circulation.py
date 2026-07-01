"""Idle-/occupied fan recirculation decision (ADR-0053), shadow-first.

When a split-AC reaches setpoint and coasts in the dead-band it often shuts its
indoor fan off; in an *occupied* room the air then stratifies (warm / CO2-rich
pockets near the floor, an unrepresentative sensor). This pure helper decides
whether to hold the fan at its lowest non-off stage for gentle recirculation —
destratification and comfort ONLY, never CO2/IAQ control (lowering CO2 needs
fresh air, not recirculation; ADR-0048). Low speed only (ASHRAE 55: <=0.25 m/s
in the occupied zone — mix without draught).

Opt-in and gated: it returns ``fan_low`` only when the feature is enabled
(``policy == "fan_only_low"``), the device can recirculate, the window is closed
(ADR-0041 has precedence), no active heat/cool/dry call is running (the fan
follows the active mode then), the zone is idle in the dead-band, AND the room
is occupied — or, without a presence entity, the presence-less "always low in
idle" opt-in is set. Everything else is ``none``.
"""

from __future__ import annotations

from dataclasses import dataclass

FAN_ONLY_LOW = "fan_only_low"


@dataclass(frozen=True, slots=True)
class FanCirculation:
    action: str  # "fan_low" | "none"
    reason: str


def fan_circulation(
    *,
    occupied: bool | None,
    in_deadband: bool,
    active_mode: str,
    window_open: bool,
    can_recirculate: bool,
    policy: str,
    presence_optin: bool = False,
) -> FanCirculation:
    """Decide the idle recirculation fan action (ADR-0053). See module docstring."""
    if policy != FAN_ONLY_LOW:
        return FanCirculation("none", "disabled")
    if not can_recirculate:
        return FanCirculation("none", "no_fan_capability")
    if window_open:  # ADR-0041 precedence
        return FanCirculation("none", "window_open")
    if active_mode in ("heat", "cool", "dry"):  # fan follows the active call
        return FanCirculation("none", "active_mode")
    if not in_deadband:
        return FanCirculation("none", "not_idle")
    if occupied is True:
        return FanCirculation("fan_low", "occupied_idle")
    if occupied is None and presence_optin:
        return FanCirculation("fan_low", "idle_no_presence_optin")
    return FanCirculation("none", "unoccupied_or_no_presence")
