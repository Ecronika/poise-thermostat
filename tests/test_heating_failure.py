from __future__ import annotations

from custom_components.poise.safety.heating_failure import (
    HeatingFailureDetector,
    actuator_running,
    failure_notification_action,
)


def test_no_failure_when_room_rises() -> None:
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, running=True)
    healthy = det.update(now_h=40.0 / 60.0, room=19.0, setpoint=21.0, running=True)
    assert healthy is False


def test_failure_when_room_stays_flat_under_demand() -> None:
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, running=True)
    assert det.update(now_h=40.0 / 60.0, room=18.0, setpoint=21.0, running=True) is True
    assert det.failed


def test_no_failure_before_the_delay() -> None:
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, running=True)
    early = det.update(now_h=10.0 / 60.0, room=18.0, setpoint=21.0, running=True)
    assert early is False


def test_no_failure_when_device_not_running() -> None:
    # C6: the detector keys on the actuator's real running state, not intent.
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, running=False)
    assert (
        det.update(now_h=40.0 / 60.0, room=18.0, setpoint=21.0, running=False) is False
    )


def test_failure_latches_until_recovery_window() -> None:
    # C6: a single no-demand tick (running-state flicker) must NOT clear the
    # latch; recovery is only declared after a full window without demand.
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=21.0, running=True)
    assert det.update(now_h=40.0 / 60.0, room=18.0, setpoint=21.0, running=True) is True
    assert det.update(now_h=0.75, room=18.0, setpoint=18.0, running=False) is True
    assert det.failed  # still latched after one no-demand tick
    cleared = det.update(
        now_h=0.75 + 40.0 / 60.0, room=18.0, setpoint=18.0, running=False
    )
    assert cleared is False
    assert not det.failed


def test_small_command_delta_is_not_a_demand() -> None:
    det = HeatingFailureDetector()
    assert det.update(now_h=0.0, room=20.5, setpoint=21.0, running=True) is False
    assert det.update(now_h=1.0, room=20.5, setpoint=21.0, running=True) is False


def test_failure_starting_mid_episode_is_caught() -> None:
    # F5: a long episode that rose early then STALLS must be flagged by a later window.
    det = HeatingFailureDetector()
    det.update(now_h=0.0, room=18.0, setpoint=22.0, running=True)
    assert det.update(now_h=0.6, room=19.0, setpoint=22.0, running=True) is False
    failed = det.update(now_h=1.2, room=19.0, setpoint=22.0, running=True)
    assert failed is True


def test_actuator_running_prefers_real_state() -> None:
    # C6: real hvac_action wins; fall back to intent only when unreported.
    assert actuator_running("heating", fallback=False) is True
    assert actuator_running("idle", fallback=True) is False
    assert actuator_running(None, fallback=True) is True
    assert actuator_running(None, fallback=False) is False


def test_failure_notification_edges() -> None:
    assert failure_notification_action(failed=True, already_notified=False) == "create"
    assert failure_notification_action(failed=True, already_notified=True) is None
    assert failure_notification_action(failed=False, already_notified=True) == "dismiss"
    assert failure_notification_action(failed=False, already_notified=False) is None
