from __future__ import annotations

from custom_components.poise.control.optimal_start import (
    advise,
    heatup_minutes,
)
from custom_components.poise.estimation.thermal_ekf import ThermalModel

# Strong heater: t_eq = t_out + beta_h/alpha = 5 + 4/0.15 = 31.7 C >> target.
_STRONG = ThermalModel(alpha=0.15, beta_h=4.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)
# Weak heater: t_eq = 5 + 1/0.15 = 11.7 C, below a 21 C target.
_WEAK = ThermalModel(alpha=0.15, beta_h=1.0, beta_c=0.0, beta_s=0.0, beta_o=0.0)


def test_already_warm_needs_no_lead() -> None:
    assert heatup_minutes(_STRONG, room=21.5, target=21.0, t_out=5.0) == 0.0


def test_reachable_returns_positive_lead() -> None:
    lead = heatup_minutes(_STRONG, room=18.0, target=21.0, t_out=5.0)
    assert lead is not None and lead > 0.0


def test_colder_room_needs_more_lead() -> None:
    warm = heatup_minutes(_STRONG, room=19.5, target=21.0, t_out=5.0)
    cold = heatup_minutes(_STRONG, room=17.0, target=21.0, t_out=5.0)
    assert warm is not None and cold is not None
    assert cold > warm


def test_colder_outdoor_needs_more_lead() -> None:
    mild = heatup_minutes(_STRONG, room=18.0, target=21.0, t_out=10.0)
    harsh = heatup_minutes(_STRONG, room=18.0, target=21.0, t_out=2.0)
    assert mild is not None and harsh is not None
    assert harsh > mild


def test_weak_heater_cannot_reach_target() -> None:
    assert heatup_minutes(_WEAK, room=18.0, target=21.0, t_out=5.0) is None


def test_beyond_horizon_is_unreachable() -> None:
    out = heatup_minutes(
        _STRONG, room=18.0, target=21.0, t_out=5.0, max_lead_h=0.1
    )
    assert out is None


def test_advise_starts_when_deadline_within_lead() -> None:
    a = advise(_STRONG, room=18.0, target=21.0, t_out=5.0, minutes_to_comfort=30.0)
    assert a.reachable
    assert a.lead_minutes > 30.0
    assert a.start_now


def test_advise_waits_when_deadline_far() -> None:
    a = advise(_STRONG, room=18.0, target=21.0, t_out=5.0, minutes_to_comfort=300.0)
    assert a.reachable
    assert not a.start_now


def test_advise_unreachable_does_best_effort() -> None:
    a = advise(_WEAK, room=18.0, target=21.0, t_out=5.0, minutes_to_comfort=10.0)
    assert not a.reachable
    assert a.start_now  # heat early so we arrive as warm as possible
