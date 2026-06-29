"""Tier-1 review fixes: C-3ctrl coercion guard + F-1 stateless PI shadow."""

from __future__ import annotations

from typing import Any

from custom_components.poise.control.hub_aggregate import zone_request_from_data
from custom_components.poise.control.pi import PiCompensator
from custom_components.poise.control.pi_shadow import evaluate_pi_shadow


def _zr(data: dict[str, Any]):
    return zone_request_from_data(
        "z",
        data,
        controls_boiler=True,
        declared_power=None,
        compressor_group=None,
        flow_temp_request=None,
        source_pref=None,
        mono_ts=0.0,
    )


# --- C-3ctrl: a bad sensor string must not abort the ZoneRequest build ------


def test_unavailable_strings_do_not_abort_zone_request() -> None:
    zr = _zr({"current_temperature": "unavailable", "heat_sp": "unknown"})
    assert zr.frost_active is False
    assert zr.comfort_gap == 0.0
    assert zr.heat_demand == 0.0


def test_numeric_values_still_work() -> None:
    zr = _zr({"current_temperature": 19.0, "heat_sp": 21.0, "heating": True})
    assert zr.comfort_gap == 2.0
    assert zr.frost_active is False
    assert zr.heat_demand == 1.0


def test_unavailable_tpi_duty_falls_back_to_heating() -> None:
    zr = _zr(
        {
            "current_temperature": 19.0,
            "heat_sp": 21.0,
            "heating": True,
            "tpi_duty": "unavailable",
        }
    )
    assert zr.heat_demand == 1.0  # fallback, not a crash


# --- F-1: PI shadow is side-effect-free + the k_ext term is alive ----------


def test_pi_shadow_does_not_mutate_compensator() -> None:
    c = PiCompensator()
    s1 = evaluate_pi_shadow(
        c, applies=True, target=21.0, room=20.0, external=5.0, dt_h=1.0
    )
    s2 = evaluate_pi_shadow(
        c, applies=True, target=21.0, room=20.0, external=5.0, dt_h=1.0
    )
    assert c.acc == 0.0  # integrator untouched by the shadow
    assert s1 == s2  # re-evaluation is pure
    assert s1.next_acc is not None and s1.next_acc > 0.0


def test_pi_shadow_external_feed_forward_alive() -> None:
    c = PiCompensator()
    # dt_h=0 isolates the k_ext term; error is 0 (room==target)
    same = evaluate_pi_shadow(
        c, applies=True, target=21.0, room=21.0, external=21.0, dt_h=0.0
    )
    cold = evaluate_pi_shadow(
        c, applies=True, target=21.0, room=21.0, external=0.0, dt_h=0.0
    )
    assert same.offset == 0.0
    assert (
        cold.offset is not None and cold.offset > same.offset
    )  # colder out -> push up


def test_pi_shadow_inactive_on_valve_device() -> None:
    c = PiCompensator()
    s = evaluate_pi_shadow(c, applies=False, target=21.0, room=20.0, external=5.0)
    assert s.active is False and s.setpoint is None


def test_compensate_still_advances_integrator() -> None:
    c = PiCompensator()
    c.compensate(21.0, 20.0, 5.0, dt_h=1.0)
    assert c.acc > 0.0  # the live path still accumulates
