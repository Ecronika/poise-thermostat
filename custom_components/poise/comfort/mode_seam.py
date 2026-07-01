"""One-HVAC-mode-per-tick arbitration seam (ADR-0050 + ADR-0023).

Folds the humidity decision (ADR-0050) into the temperature/window decision so
exactly ONE mode is commanded per tick: temperature and safety are primary —
``heat`` / ``cool`` / ``off`` / ``manual`` are never overridden — and active
``dry`` wins ONLY when the temperature is idle (room in the dead-band) and the
humidity decision calls for drying on a dry-capable, non-locked-out device.
cool-first is already encoded in ``humidity_decide`` (too_warm -> cool), so when
cooling, ``cool`` is the base mode and it stays (cooling also dehumidifies).
This is the coherent Temp×humidity×outdoor composition ADR-0050/0051 require.
Pure; unit-tested; capability-gated (``dry_ok`` False -> a no-op).
"""

from __future__ import annotations


def mode_arbitration(*, base_mode: str, humidity_action: str, dry_ok: bool) -> str:
    """Return the single HVAC mode to command this tick.

    ``base_mode`` is the temperature/window/override decision (``heat`` /
    ``cool`` / ``idle`` / ``off`` / ``manual``). ``dry`` replaces ONLY ``idle``
    when ``humidity_action == "dry"`` and ``dry_ok`` (the caller's
    ``can_dry AND not window AND not locked-out``). All other base modes pass
    through unchanged — temperature and safety keep precedence.
    """
    if base_mode == "idle" and humidity_action == "dry" and dry_ok:
        return "dry"
    return base_mode
