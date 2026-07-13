"""Override / preset modes with timed auto-revert (ADR-0042).

Modes are an **offset on the user's comfort base**, never a free temperature:
the constraint solver therefore still clamps every mode to the norm floors/cap
(frost/mould/ASR), so no preset can break the norm — the key difference from
competitors that store free per-preset temperatures. A manual setpoint override
auto-reverts after a window so it never sticks indefinitely (community VT#1875).
Pure and unit-tested; the coordinator owns the state and applies the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OverrideMode(str, Enum):  # noqa: UP042 — explicit str+Enum, StrEnum-equivalent
    """Comfort preset. Values match HA's PRESET_* so the frontend translates them."""

    NONE = "none"
    ECO = "eco"
    COMFORT = "comfort"
    BOOST = "boost"
    AWAY = "away"


@dataclass(frozen=True, slots=True)
class OverrideConfig:
    eco_offset: float = 2.0  # K below base (energy saving)
    boost_offset: float = 1.5  # K above base (quick warm-up)
    away_offset: float = 4.0  # K below base (absence setback)
    manual_revert_h: float = 2.0  # manual setpoint auto-reverts after this many hours


_DEFAULT = OverrideConfig()


def mode_comfort_base(
    mode: OverrideMode, base: float, cfg: OverrideConfig = _DEFAULT
) -> float:
    """Effective comfort base for a preset — an offset on ``base``, not a free
    temperature, so the solver still enforces the norm envelope (ADR-0042)."""
    if mode is OverrideMode.ECO:
        return base - cfg.eco_offset
    if mode is OverrideMode.AWAY:
        return base - cfg.away_offset
    if mode is OverrideMode.BOOST:
        return base + cfg.boost_offset
    return base  # NONE / COMFORT keep the user's base


def manual_override_expired(
    set_at: float, now: float, cfg: OverrideConfig = _DEFAULT
) -> bool:
    """True once a manual setpoint override has outlived its auto-revert window.

    Addresses the most-requested override behaviour (VT#1875): a manual change
    must revert to the schedule/preset instead of holding the room high forever.
    ``set_at``/``now`` must share one clock; the coordinator passes a persisted
    *wall-clock* timestamp so a restored hold expires on real elapsed time and
    cannot outlive a restart (review C5).
    """
    return (now - set_at) >= cfg.manual_revert_h * 3600.0


# ---------------------------------------------------------------------------
# ADR-0059: manual-override lifecycle — the expiry is announced at set-time.
#
# These three functions are the *pure* state logic behind ADR-0059 §1/§2: the
# coordinator (HA glue) owns the wall-clock, the persistence and the actual
# delete; it calls these to decide *when* a hold or Boost ends. The policy
# identifiers below are the literal values of ``const.OVERRIDE_POLICY_*`` (kept
# inline so this module stays import-free and standalone-testable, ADR-0011).
# ---------------------------------------------------------------------------


def resolve_hold_expiry(
    *,
    policy: str,
    set_at: float,
    timer_h: float,
    max_h: float,
    minutes_to_switchpoint: float | None,
) -> float | None:
    """Wall-clock expiry of a manual hold, computed **at set time** (ADR-0059 §3/§4).

    The expiry is announced up front — the Card shows "gilt bis …" the instant
    the user intervenes (ADR-0059 §4) — instead of being recomputed each tick,
    so a hold restored after a restart expires on real elapsed wall-clock time
    (Review-C5 pattern). ``set_at`` and the caller's ``now`` share one clock.

    Return policy (ADR-0059 §1; values mirror ``const.OVERRIDE_POLICY_*``):

    * ``"permanent"`` — deliberate opt-in (ecobee/holiday class); never
      auto-expires, so this returns ``None``.
    * ``"timer"`` — fixed duration (today's ADR-0042 behaviour, and the default
      when there is no comfort schedule): ``set_at + timer_h * 3600``.
    * ``"schedule"`` — ends **value-independently** at the next switchpoint given
      by ``minutes_to_switchpoint`` (tado-16475 class: end at the *time*, never
      at a temperature delta). With no upcoming switchpoint the "schedule without
      a schedule" fallback uses the timer duration. The result is always capped
      by ``max_h`` (the ``override_max_h`` net for long window-less stretches).

    Any unrecognised policy is treated as ``"timer"`` (safe fallback).
    """
    if policy == "permanent":  # const.OVERRIDE_POLICY_PERMANENT
        return None
    if policy == "schedule":  # const.OVERRIDE_POLICY_SCHEDULE
        # Next switchpoint when we have one, else the "schedule without a
        # schedule" timer fallback (ADR-0059 §1); expiry is value-independent.
        base = (
            set_at + minutes_to_switchpoint * 60.0
            if minutes_to_switchpoint is not None and minutes_to_switchpoint > 0
            else set_at + timer_h * 3600.0
        )
        return min(base, set_at + max_h * 3600.0)  # override_max_h safety cap
    # "timer" and every unknown policy -> fixed duration.
    return set_at + timer_h * 3600.0


def hold_expired(
    *,
    expires_at: float | None,
    now: float,
    presence_changed: bool,
    end_on_presence: bool,
) -> bool:
    """True when a manual hold must end **now** (ADR-0059 §1).

    A hold ends as soon as either trigger fires:

    * a **house-gate presence flip** in *either* direction (home->away or
      away->home; ADR-0058), when ``override_end_on_presence_change`` is on —
      the tado-V3+ "until next automatic change" semantics; or
    * its announced wall-clock expiry has been reached (``now >= expires_at``).

    A ``permanent`` hold carries ``expires_at is None`` and therefore ends
    **only** on the presence trigger, never on elapsed time.
    """
    return (presence_changed and end_on_presence) or (
        expires_at is not None and now >= expires_at
    )


def hold_ends_at_preheat(
    *,
    policy: str,
    preheat_started: bool,
    expiry_is_switchpoint: bool,
    preheat_target: float | None,
    held_value: float,
) -> bool:
    """True when a schedule-hold must end at the optimal-start preheat (ADR-0059 §3).

    A ``schedule``-policy hold whose announced expiry is the next comfort
    switchpoint would otherwise clamp the setpoint through the whole optimal-start
    preheat ramp, so the room only begins warming *at* the comfort switchpoint -- a
    cold block-start. Ending it the moment preheating begins (Danfoss
    ``schedule_with_preheat`` semantics; ADR-0025 physics) lets the identified model
    carry the room to comfort on time; the reason stays ``schedule_point`` (the
    schedule's comfort window ends it, only pulled forward to the preheat).

    Guards:

    * only the **rising edge** of preheating triggers this (``preheat_started``) --
      a hold the user sets *during* an already-running preheat is deliberate and is
      never instantly killed;
    * only ``schedule`` policy -- ``timer``/``permanent`` holds carry a chosen
      duration and are never shortened;
    * only when ``preheat_target`` is **warmer** than the held value -- a hold
      already at/above the target keeps the room warm enough, so it runs to its
      normal switchpoint;
    * ``expiry_is_switchpoint`` gates out schedule holds whose expiry is the timer
      fallback (no schedule) or the ``max_h`` cap, not a real switchpoint.
    """
    return (
        policy == "schedule"
        and preheat_started
        and expiry_is_switchpoint
        and preheat_target is not None
        and preheat_target > held_value
    )


def resolve_boost_expiry(*, set_at: float, boost_duration_min: float) -> float:
    """Wall-clock expiry of a timed Boost preset (ADR-0059 §2).

    Boost is the one preset that carries a duration (``boost_duration_min``,
    default 60 min): it expires at ``set_at + boost_duration_min * 60``, after
    which the coordinator restores the preset frozen when Boost was activated
    (VT#1961 guard). Eco/Comfort/Away stay durationless state choices.
    """
    return set_at + boost_duration_min * 60.0


# ---------------------------------------------------------------------------
# P1-4a: adopt a device-side setpoint change as a manual hold.
#
# When the user turns the TRV wheel (or the vendor app), the actuator reports a
# setpoint Poise did not command; the naive control loop overwrites it within one
# tick. This pure detector decides whether the *reported* setpoint is a genuine
# user change worth adopting as a hold, rather than an echo of Poise's own write.
# It is policy-agnostic: the coordinator (glue) turns an adopted value into a hold
# via ``resolve_hold_expiry`` with the zone's configured policy.
# ---------------------------------------------------------------------------


def detect_external_setpoint(
    *,
    device_sp: float | None,
    last_written_sp: float | None,
    last_write_ts: float | None,
    now: float,
    echo_window_s: float,
    deadband: float,
    prev_device_sp: float | None = None,
) -> float | None:
    """The device-side setpoint Poise should adopt as a manual hold, else ``None``.

    A reported setpoint is a genuine external change only when it differs from what
    Poise last commanded — an *echo* of our own write matches ``last_written_sp``
    and must be ignored. Three guards keep lag, cold-start and a persistent device
    offset from raising a false positive:

    * **No baseline** (``last_written_sp`` or ``last_write_ts`` is ``None``): Poise
      has not established control yet, so it cannot tell an echo from a change —
      return ``None`` and let the normal write path settle the device first.
    * **Echo window**: within ``echo_window_s`` of our own write the device may
      still report its *pre-write* value (Zigbee/poll lag); suppress adoption so
      that lag is never read as a user change.
    * **Stable offset** (``prev_device_sp``): a genuine user action *moves* the
      setpoint this tick. A device that re-quantised, clamped (own min/max) or
      otherwise settled our write at a fixed offset > ``deadband`` reports that
      value unchanged tick-over-tick; without this guard it is re-adopted as a hold
      the moment the echo window lapses — seen live: ending a hold via the card's X
      springs straight back to "manual" (the schedule value the device settled at
      gets re-read as a user change). Require an actual move since the previous
      reading; a settled offset never fires. ``None`` (first observation) skips this
      guard, which is safe because the *no baseline* guard already gates cold start.

    ``last_written_sp`` must be the value Poise actually commanded **after snapping
    to the device step** (what the device settles to), and ``deadband`` at least
    one device step, so a device echoing our command back — possibly re-quantised —
    is never mistaken for a user change. ``now``/``last_write_ts`` share one
    monotonic clock. The returned value is the raw reported setpoint (the caller
    snaps and clamps it to the norm envelope before holding it).
    """
    if device_sp is None or last_written_sp is None or last_write_ts is None:
        return None
    if (now - last_write_ts) < echo_window_s:
        return None
    if round(abs(device_sp - last_written_sp), 3) < deadband:
        return None
    if prev_device_sp is not None and (
        round(abs(device_sp - prev_device_sp), 3) < deadband
    ):
        return None
    return device_sp
