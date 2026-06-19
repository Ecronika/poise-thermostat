from __future__ import annotations

from custom_components.poise.comfort.corridor import ComfortContext, build_corridor
from custom_components.poise.contracts import Maturity, ThermalState
from custom_components.poise.control.mpc_controller import MpcController


def _state(
    t_air: float,
    *,
    tau: float = 10.0,
    maturity: Maturity = Maturity.MATURE,
    prediction_std: float | None = 0.2,
) -> ThermalState:
    return ThermalState(
        t_air=t_air,
        tau=tau,
        loss_uc=0.0,
        beta_h=2.0,
        beta_c=4.0,
        beta_s=0.0,
        beta_o=0.0,
        q_solar=0.0,
        t_rm=5.0,
        confidence=0.9,
        maturity=maturity,
        t_out=5.0,
        prediction_std=prediction_std,
    )


def _corridor() -> object:
    # EN comfort band at T_rm 15 -> ~23.75, wide enough for the test
    return build_corridor(
        ComfortContext(t_rm=15.0, t_air=18.0, frost_floor=7.0, device_max=30.0)
    )


def test_mature_confident_cold_room_uses_mpc() -> None:
    req = MpcController().evaluate(_state(18.0), _corridor(), "trv")  # type: ignore[arg-type]
    assert req.power is not None and req.power > 0.5
    assert "mpc/w=" in req.reason
    assert req.regime == "heat"


def test_immature_state_falls_back_to_bangbang() -> None:
    req = MpcController().evaluate(
        _state(18.0, maturity=Maturity.COLD), _corridor(), "trv"
    )  # type: ignore[arg-type]
    # weight 0 -> pure bang-bang; cold room -> full power
    assert req.power == 1.0


def test_invalid_model_falls_back_to_bangbang() -> None:
    req = MpcController().evaluate(_state(25.0, tau=0.0), _corridor(), "trv")  # type: ignore[arg-type]
    # tau=0 -> no model; warm room -> bang-bang idles
    assert req.power == 0.0


def test_high_prediction_std_disables_mpc() -> None:
    req = MpcController().evaluate(_state(18.0, prediction_std=0.6), _corridor(), "trv")  # type: ignore[arg-type]
    assert req.power == 1.0  # weight 0 -> bang-bang full power when cold
