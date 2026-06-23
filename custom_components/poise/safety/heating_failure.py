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
        self._failed = False

    @property
    def failed(self) -> bool:
        return self._failed

    def update(
        self, *, now_h: float, room: float, setpoint: float, heating: bool
    ) -> bool:
        """Return True while a heating failure is active."""
        demand = heating and (setpoint - room) >= self._cmd_delta
        if not demand:
            self._start = None
            self._failed = False
            return False
        if self._start is None:
            self._start = (now_h, room)
            return self._failed
        start_h, room0 = self._start
        if (now_h - start_h) >= self._delay_h:
            # Sliding (tumbling) window (review F5, VTherm pattern): evaluate the
            # rise over the LAST window, then re-arm so a failure that begins
            # mid-episode is still caught — not just the first window after demand.
            self._failed = (room - room0) < self._min_rise
            self._start = (now_h, room)
        return self._failed
