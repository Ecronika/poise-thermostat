"""Heating-failure detection (ThermoSmart method, ADR-0012).

If the room is commanded well above its temperature for a sustained period but
does not actually warm up, a heating failure (closed valve, empty radiator,
boiler off) is flagged. Pure and testable; the coordinator turns the flag into
a persistent notification with auto-clear on recovery.
"""

from __future__ import annotations

DEFAULT_DELAY_H: float = 35.0 / 60.0  # 35 minutes
DEFAULT_CMD_DELTA: float = 2.0  # setpoint must exceed room by this to count
DEFAULT_MIN_RISE: float = 0.2  # °C the room must gain over the delay


def actuator_running(hvac_action: str | None, *, fallback: bool) -> bool:
    """The actuator's *real* heating state, not just our intent (review C6).

    When the device reports ``hvac_action`` (e.g. a TRVZB's running_state) we use
    it, so the detector sees the true "device heating but room flat" condition;
    otherwise we fall back to our heat intent. Pure, unit-tested.
    """
    if hvac_action is None:
        return fallback
    return str(hvac_action) == "heating"


class HeatingFailureDetector:
    def __init__(
        self,
        *,
        delay_h: float = DEFAULT_DELAY_H,
        cmd_delta: float = DEFAULT_CMD_DELTA,
        min_rise: float = DEFAULT_MIN_RISE,
    ) -> None:
        self._delay_h = delay_h
        self._cmd_delta = cmd_delta
        self._min_rise = min_rise
        self._start: tuple[float, float] | None = None  # (time_h, room_at_start)
        self._clear_start: float | None = None  # when no-demand began (latch, C6)
        self._failed = False

    @property
    def failed(self) -> bool:
        return self._failed

    def update(
        self, *, now_h: float, room: float, setpoint: float, running: bool
    ) -> bool:
        """Return True while a heating failure is active.

        ``running`` is the actuator's real heating state (not just intent, C6).
        A detected failure *latches*: a single no-demand tick (an intermittent
        running-state flicker, or the room briefly within band) does not clear
        it — recovery is only declared after a confirmed rise, or after demand
        has been absent for a full window, so an ongoing failure can't be masked.
        """
        demand = running and (setpoint - room) >= self._cmd_delta
        if not demand:
            if self._clear_start is None:
                self._clear_start = now_h
            elif (now_h - self._clear_start) >= self._delay_h:
                self._failed = False
                self._start = None
                self._clear_start = None
            return self._failed
        self._clear_start = None
        if self._start is None:
            self._start = (now_h, room)
            return self._failed
        start_h, room0 = self._start
        if (now_h - start_h) >= self._delay_h:
            # Sliding (tumbling) window (review F5, VTherm pattern): evaluate the
            # rise over the LAST window, then re-arm so a failure that begins
            # mid-episode is caught. Set on no-rise; clear on a confirmed rise.
            self._failed = (room - room0) < self._min_rise
            self._start = (now_h, room)
        return self._failed


def failure_notification_action(failed: bool, already_notified: bool) -> str | None:
    """Edge-triggered notification action for a heating failure.

    Returns ``"create"`` on a newly detected failure, ``"dismiss"`` when it
    clears, else ``None`` (no change). Extracted from the coordinator so the
    rising/falling-edge logic is unit-tested without a HA runtime (review M13).
    """
    if failed and not already_notified:
        return "create"
    if not failed and already_notified:
        return "dismiss"
    return None
