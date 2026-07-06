"""Resolve the tri-state adaptive-cool config into an effective on/off (ADR-0008).

``adaptive_cool`` moved from a boolean to a tri-state selector ``auto | on | off``
(default ``auto``). ``auto`` follows the actuator's cooling capability — a
cool-capable device turns the adaptive summer edge on, a heat-only device leaves
it off. Existing entries stored a plain boolean; those are honoured unchanged
(``True`` -> on, ``False`` -> off), so the upgrade is zero-regression. Pure and
HA-free (ADR-0005), so the resolution is unit-tested.
"""

from __future__ import annotations

_ON = frozenset({"on", "true", "1", "yes"})
_OFF = frozenset({"off", "false", "0", "no"})


def adaptive_cool_mode(value: object) -> str:
    """Canonical mode (``"auto"`` / ``"on"`` / ``"off"``) from a stored value.

    Accepts the new string selector value and the legacy boolean. Anything
    unrecognised falls back to ``"auto"`` (the default).
    """
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _ON:
            return "on"
        if v in _OFF:
            return "off"
        if v == "auto":
            return "auto"
    return "auto"


def resolve_adaptive_cool(value: object, *, can_cool: bool) -> bool:
    """Effective on/off for the adaptive summer cooling edge.

    ``on`` -> ``True``, ``off`` -> ``False``, ``auto`` -> the actuator's cooling
    capability (so a heat-only device never widens a cooling edge it cannot use).
    """
    mode = adaptive_cool_mode(value)
    if mode == "on":
        return True
    if mode == "off":
        return False
    return can_cool
