from __future__ import annotations

from custom_components.poise.safety.heating_failure import HeatingFailureDetector


def test_no_failure_when_room_rises() -> None:
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, heating=True)
    # 40 min later the room has risen 1 °C -> healthy
    healthy = det.update(now_h=40.0 / 60.0, room=19.0, setpoint=21.0, heating=True)
    assert healthy is False


def test_failure_when_room_stays_flat_under_demand() -> None:
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, heating=True)
    assert det.update(now_h=40.0 / 60.0, room=18.0, setpoint=21.0, heating=True) is True
    assert det.failed


def test_no_failure_before_the_delay() -> None:
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, heating=True)
    early = det.update(now_h=10.0 / 60.0, room=18.0, setpoint=21.0, heating=True)
    assert early is False


def test_demand_release_resets_state() -> None:
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, heating=True)
    det.update(now_h=40.0 / 60.0, room=18.0, setpoint=21.0, heating=True)  # failed
    assert det.update(now_h=0.8, room=18.0, setpoint=18.0, heating=False) is False
    assert not det.failed


def test_small_command_delta_is_not_a_demand() -> None:
    det = HeatingFailureDetector()
    # setpoint only 0.5 °C above room -> not a strong heating demand
    assert det.update(now_h=0.0, room=20.5, setpoint=21.0, heating=True) is False
    assert det.update(now_h=1.0, room=20.5, setpoint=21.0, heating=True) is False
