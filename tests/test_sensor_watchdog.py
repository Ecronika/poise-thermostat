from __future__ import annotations

from custom_components.poise.safety.sensor_watchdog import (
    is_frozen,
    sensor_source_handback_due,
    sensor_source_handback_target,
    unavailable_safe_engaged,
)


def test_fresh_change_is_not_frozen() -> None:
    assert is_frozen(60.0, 1800.0) is False


def test_old_change_is_frozen() -> None:
    assert is_frozen(1800.0, 1800.0) is True
    assert is_frozen(3600.0, 1800.0) is True


def test_unknown_age_is_not_frozen() -> None:
    assert is_frozen(None, 1800.0) is False


def test_unavailable_safe_engaged() -> None:
    assert unavailable_safe_engaged(None, 600.0) is False  # not currently lost
    assert unavailable_safe_engaged(120.0, 600.0) is False  # brief drop-out tolerated
    assert unavailable_safe_engaged(600.0, 600.0) is True  # sustained -> safe state
    assert unavailable_safe_engaged(1200.0, 600.0) is True
    assert unavailable_safe_engaged(1200.0, 0.0) is False  # threshold 0 disables


def test_nonpositive_threshold_disables() -> None:
    assert is_frozen(99999.0, 0.0) is False


def test_heat_source_detector() -> None:
    from custom_components.poise.safety.sensor_watchdog import sensor_at_heat_source

    # identified + implausibly short tau -> flagged
    assert sensor_at_heat_source(0.5, identified=True, min_plausible_tau_h=1.0) is True
    # plausible room time constant -> fine
    assert sensor_at_heat_source(6.0, identified=True, min_plausible_tau_h=1.0) is False
    # not identified -> never judge (avoid false positives during learning)
    assert (
        sensor_at_heat_source(0.4, identified=False, min_plausible_tau_h=1.0) is False
    )
    # boundary: exactly at threshold is not flagged
    assert sensor_at_heat_source(1.0, identified=True, min_plausible_tau_h=1.0) is False


def test_valve_stuck_detection() -> None:
    from custom_components.poise.safety.sensor_watchdog import valve_stuck

    assert valve_stuck(325.0) is False  # healthy TRVZB closing-step count
    assert valve_stuck(0.0) is True  # not calibrated / jammed
    assert valve_stuck(5.0, min_steps=10.0) is True
    assert valve_stuck(None) is False  # no telemetry -> not stuck


def test_sensor_age_seconds_from_last_changed() -> None:
    from datetime import datetime, timedelta

    from custom_components.poise.safety.sensor_watchdog import sensor_age_seconds

    now = datetime(2026, 1, 1, 12, 0, 0)
    changed = now - timedelta(hours=3)
    assert sensor_age_seconds(now, changed) == 3 * 3600.0


def test_should_learn_gates_on_window_and_frozen() -> None:
    # M13/F1: learning runs only with a trustworthy signal; window OR frozen pauses it.
    from custom_components.poise.safety.sensor_watchdog import should_learn

    assert should_learn(window_open=False, frozen=False) is True
    assert should_learn(window_open=True, frozen=False) is False
    assert should_learn(window_open=False, frozen=True) is False  # frozen -> no learn
    assert should_learn(window_open=True, frozen=True) is False
    # R3: a confirmed heating failure (boiler off, valve open) also pauses learning
    # so a flat curve under u_h~1 cannot drive beta_h to its bound. The default
    # keeps every existing two-argument call site behaviour-identical.
    assert should_learn(window_open=False, frozen=False, heating_failed=True) is False
    assert should_learn(window_open=False, frozen=False, heating_failed=False) is True
    # C.8: the cooling pendant — a flat curve under u_c~1 (dead compressor,
    # blocked airflow) would drive beta_c toward its bound the same way, so a
    # latched cooling failure pauses learning too. Defaulted for old call sites.
    assert should_learn(window_open=False, frozen=False, cooling_failed=True) is False
    assert should_learn(window_open=False, frozen=False, cooling_failed=False) is True


def test_frozen_safe_target_is_the_health_floor() -> None:
    from custom_components.poise.safety.sensor_watchdog import frozen_safe_target

    # no mould floor -> frost protection
    assert frozen_safe_target(7.0, None) == 7.0
    # mould floor higher than frost -> it wins (fails toward warmth, C3)
    assert frozen_safe_target(7.0, 14.5) == 14.5
    # never below frost
    assert frozen_safe_target(7.0, 5.0) == 7.0


def test_sensor_source_handback_due_releases_a_claimed_external_select() -> None:
    assert sensor_source_handback_due(select_state="external", feed_owned=True) is True


def test_sensor_source_handback_due_never_touches_a_foreign_select() -> None:
    # Not our feed -> never release, whatever the select says (the return path
    # would not re-claim it either).
    assert (
        sensor_source_handback_due(select_state="external", feed_owned=False) is False
    )


def test_sensor_source_handback_due_is_idempotent_and_write_safe() -> None:
    # Already internal -> nothing to do; no select discovered / device offline
    # -> nothing writable.
    assert sensor_source_handback_due(select_state="internal", feed_owned=True) is False
    assert sensor_source_handback_due(select_state=None, feed_owned=True) is False
    assert (
        sensor_source_handback_due(select_state="unavailable", feed_owned=True) is False
    )


# ---------------------------------------------------------------------------
# sensor_source_handback_target -- the decision node lifted out of
# ``ha/phase_actuate`` (the dispatch stayed there). What is tested here is the
# TRANSLATION of ownership evidence into a target, not the predicate above.
# ---------------------------------------------------------------------------


def test_handback_target_names_the_select_for_a_configured_feed() -> None:
    assert (
        sensor_source_handback_target(
            select_entity_id="select.trv_sensor_source",
            select_state="external",
            configured_feed="number.trv_ext_temp",
            last_fed=None,
        )
        == "select.trv_sensor_source"
    )


def test_handback_target_accepts_an_auto_detected_feed_we_actually_drove() -> None:
    # No configured target, but we fed this device in this run -> ours.
    assert (
        sensor_source_handback_target(
            select_entity_id="select.trv_sensor_source",
            select_state="external",
            configured_feed=None,
            last_fed="number.trv_ext_temp",
        )
        == "select.trv_sensor_source"
    )


def test_handback_target_is_none_without_ownership_evidence() -> None:
    # A restart INSIDE an outage loses the transient ``last_fed`` -> no
    # handback, rather than releasing a select that may be someone else's.
    assert (
        sensor_source_handback_target(
            select_entity_id="select.trv_sensor_source",
            select_state="external",
            configured_feed=None,
            last_fed=None,
        )
        is None
    )


def test_handback_target_is_none_when_no_select_was_discovered() -> None:
    assert (
        sensor_source_handback_target(
            select_entity_id=None,
            select_state="external",
            configured_feed="number.trv_ext_temp",
            last_fed=None,
        )
        is None
    )


def test_handback_target_is_none_once_the_select_is_internal() -> None:
    assert (
        sensor_source_handback_target(
            select_entity_id="select.trv_sensor_source",
            select_state="internal",
            configured_feed="number.trv_ext_temp",
            last_fed=None,
        )
        is None
    )
