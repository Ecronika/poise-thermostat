"""Generic, capability-detected device adaptations (ADR-0015, devices/model_fixes).

No model names: every guard keys off detected entities/attributes, so the same
logic works for any thermostat that happens to expose these features (the Aqara
E1 SRTS-A01 is merely one example). Three protective guards + one actuator
extension:

  1. neutralise a device-internal weekly schedule that would fight the controller
  2. surface a device valve/fault alarm (and feed it into heating-failure)
  3. surface a low battery on the actuator/sensor device
  4. feed the fused room temperature to a TRV external-temperature input, so a
     thermostat calibratable to an external sensor regulates against the true
     room temperature.

This module holds the *pure* classifiers/thresholds; the registry lookups,
service calls and repair issues live in the coordinator (HA glue).
"""

from __future__ import annotations

LOW_BATTERY_PCT: float = 15.0


def is_low_battery(level: float | None, threshold: float = LOW_BATTERY_PCT) -> bool:
    """True when a battery percentage is at or below the warning threshold."""
    return level is not None and level <= threshold


def looks_like_internal_schedule(entity_id: str) -> bool:
    """A switch that toggles the device's own weekly schedule (fights control)."""
    return entity_id.startswith("switch.") and "schedule" in entity_id.lower()


def looks_like_fault_alarm(entity_id: str) -> bool:
    """A binary_sensor reporting a valve/installation fault or alarm."""
    name = entity_id.lower()
    return entity_id.startswith("binary_sensor.") and any(
        token in name for token in ("valve_alarm", "fault", "problem", "alarm")
    )


def looks_like_external_temp_number(
    entity_id: str, device_class: str | None = None
) -> bool:
    """A number entity that injects an external temperature into the thermostat.

    Keyed on the entity_id containing "external" (pavax-verified naming), optional
    temperature device_class. Generic across integrations/devices.
    """
    if not entity_id.startswith("number.") or "external" not in entity_id.lower():
        return False
    return device_class in (None, "temperature")


_TEMPERATURE_UNITS: frozenset[str] = frozenset({"°C", "°F", "K"})


def ext_temp_number_is_implausible(
    entity_id: str, device_class: str | None, unit: str | None
) -> bool:
    """True only when a *configured* external-temp number shows a POSITIVE
    non-temperature signal: a non-temperature ``device_class`` or a
    non-temperature ``unit_of_measurement`` (e.g. a valve's "%").

    Unlike :func:`looks_like_external_temp_number` (a strict, name-based screen
    fit for scanning auto-detected siblings), this trusts a value the user
    picked EXPLICITLY: absence of metadata — or a temperature device_class/unit —
    is accepted, and only an affirmative "this is not a temperature" rejects it.
    That avoids disabling a legitimately renamed/localised temperature input on
    upgrade, while still catching a mis-picked valve-position/level number.
    """
    if not entity_id.startswith("number."):
        return True
    if device_class is not None and device_class != "temperature":
        return True
    return unit is not None and unit not in _TEMPERATURE_UNITS


def is_external_sensor_select(entity_id: str, options: object) -> bool:
    """A select that switches the thermostat between its internal/external sensor.

    Keyed on the option list containing "external" (pavax-verified), not on names.
    """
    if not entity_id.startswith("select."):
        return False
    opts = options if isinstance(options, (list, tuple)) else ()
    return "external" in opts and "internal" in opts


def looks_like_valve_steps(entity_id: str) -> str | None:
    """Classify a valve motor step-counter sensor: "closing" / "idle" / None.

    The Sonoff TRVZB reports ``closing_steps`` (steps to fully close) and
    ``idle_steps`` (no-load calibration steps) — generic valve-health telemetry.
    """
    if not entity_id.startswith("sensor."):
        return None
    k = entity_id.lower()
    if "closing_steps" in k:
        return "closing"
    if "idle_steps" in k:
        return "idle"
    return None
