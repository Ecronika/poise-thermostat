from __future__ import annotations

from custom_components.poise.control.pi import PiCompensator


def test_positive_error_raises_setpoint() -> None:
    pi = PiCompensator()
    sp = pi.compensate(target=21.0, room=19.0, external=5.0)
    assert sp > 21.0


def test_integral_accumulates_over_time() -> None:
    pi = PiCompensator()
    first = pi.compensate(21.0, 20.5, 5.0)
    for _ in range(10):
        out = pi.compensate(21.0, 20.5, 5.0)
    assert out > first  # integral keeps pushing


def test_offset_is_bounded() -> None:
    pi = PiCompensator(offset_max=2.0)
    for _ in range(1000):
        sp = pi.compensate(21.0, 5.0, -20.0)  # huge sustained error
    assert sp <= 21.0 + 2.0 + 1e-9


def test_colder_outdoor_raises_setpoint() -> None:
    mild = PiCompensator().compensate(21.0, 21.0, 15.0)
    cold = PiCompensator().compensate(21.0, 21.0, -10.0)
    assert cold > mild


def test_reset_clears_integral() -> None:
    pi = PiCompensator()
    for _ in range(5):
        pi.compensate(21.0, 19.0, 5.0)
    pi.reset()
    after = pi.compensate(21.0, 21.0, 21.0)  # zero error, zero feedforward
    assert after == 21.0
