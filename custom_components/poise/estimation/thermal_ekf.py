"""Mode-gated Extended Kalman Filter for the 1R1C building model (ADR-0002/0009).

State (per-hour units):  x = [T, alpha, beta_h, beta_c, beta_s, beta_o]
  T       room air temperature           [°C]
  alpha   = U/C, inverse time constant    [1/h]   (tau = 1/alpha)
  beta_h  heating responsivity            [°C/h per unit power]
  beta_c  cooling responsivity            [°C/h per unit power]
  beta_s  solar responsivity              [°C/h per normalised q_solar]
  beta_o  occupancy responsivity          [°C/h per normalised q_occ]

Continuous model:  dT/dt = -alpha·T + (alpha·T_out + R),
  R = beta_h·u_h - beta_c·u_c + beta_s·q_solar + beta_o·q_occ
Discretised with the analytic zero-order-hold solution (not naive Euler).

Robustness (ADR-0009): mode-gated process noise (only observable parameters are
inflated -> no alpha<->beta oscillation), 4-sigma outlier soft-reject, hard
parameter bounds, Joseph-form covariance update, PSD floor, recovery on load.
Pure stdlib (no numpy) per ADR-0022.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# ---- state indices ---------------------------------------------------------
_T, _A, _BH, _BC, _BS, _BO = range(6)
_N = 6

# ---- tuning (ADR-0009, per-hour units) -------------------------------------
_R: float = 0.04  # measurement noise variance (~0.2 °C std)
_Q = (0.01, 0.0005, 0.005, 0.005, 0.002, 0.002)  # process noise per step
_ANOMALY_SIGMA: float = 4.0
_ANOMALY_INFLATE: float = 100.0
_PSD_FLOOR: float = 1e-10

# defaults & bounds
_DEFAULTS = (21.0, 0.15, 3.0, 4.0, 0.5, 0.3)
_LOWER = (-50.0, 0.005, 0.1, 0.1, 0.0, 0.0)
_UPPER = (60.0, 2.0, 200.0, 300.0, 50.0, 20.0)

_P0 = (1.0, 0.01, 1.0, 1.0, 0.5, 0.5)  # initial covariance diagonal

EKF_VERSION: int = 1

Matrix = list[list[float]]


def _identity() -> Matrix:
    return [[1.0 if i == j else 0.0 for j in range(_N)] for i in range(_N)]


def _matmul(a: Matrix, b: Matrix) -> Matrix:
    out = [[0.0] * _N for _ in range(_N)]
    for i in range(_N):
        ai = a[i]
        for k in range(_N):
            aik = ai[k]
            if aik == 0.0:
                continue
            bk = b[k]
            oi = out[i]
            for j in range(_N):
                oi[j] += aik * bk[j]
    return out


def _transpose(a: Matrix) -> Matrix:
    return [[a[j][i] for j in range(_N)] for i in range(_N)]


@dataclass(frozen=True, slots=True)
class ThermalModel:
    """Frozen snapshot of the learned model consumed by the optimizer (ADR-0002)."""

    alpha: float
    beta_h: float
    beta_c: float
    beta_s: float
    beta_o: float

    def predict(
        self,
        t_air: float,
        dt_h: float,
        t_out: float,
        u_h: float = 0.0,
        u_c: float = 0.0,
        q_solar: float = 0.0,
        q_occ: float = 0.0,
    ) -> float:
        """Zero-order-hold one-step temperature prediction [°C]. Stateless."""
        ex = math.exp(-self.alpha * dt_h)
        drive = (
            self.beta_h * u_h
            - self.beta_c * u_c
            + self.beta_s * q_solar
            + self.beta_o * q_occ
        )
        t_eq = t_out + drive / self.alpha
        return t_eq + (t_air - t_eq) * ex


class ThermalEKF:
    """Augmented-state EKF; sole source of the thermal model (ADR-0002)."""

    def __init__(self, x: list[float] | None = None) -> None:
        self.x: list[float] = list(x) if x is not None else list(_DEFAULTS)
        self.p: Matrix = [
            [(_P0[i] if i == j else 0.0) for j in range(_N)] for i in range(_N)
        ]
        self.n_updates: int = 0
        self.n_heating: int = 0
        self.n_cooling: int = 0

    # -- prediction ----------------------------------------------------------
    def predict(
        self,
        dt_h: float,
        t_out: float,
        u_h: float = 0.0,
        u_c: float = 0.0,
        q_solar: float = 0.0,
        q_occ: float = 0.0,
    ) -> None:
        t, alpha = self.x[_T], self.x[_A]
        ex = math.exp(-alpha * dt_h)
        drive = (
            self.x[_BH] * u_h
            - self.x[_BC] * u_c
            + self.x[_BS] * q_solar
            + self.x[_BO] * q_occ
        )
        t_eq = t_out + drive / alpha

        # Jacobian F (identity for the random-walk parameters)
        f = _identity()
        f[_T][_T] = ex
        f[_T][_A] = (-drive / (alpha * alpha)) * (1.0 - ex) + dt_h * ex * (t_eq - t)
        f[_T][_BH] = (1.0 - ex) * u_h / alpha
        f[_T][_BC] = -(1.0 - ex) * u_c / alpha
        f[_T][_BS] = (1.0 - ex) * q_solar / alpha
        f[_T][_BO] = (1.0 - ex) * q_occ / alpha

        # state: T advances analytically, parameters are constant
        self.x[_T] = t_eq + (t - t_eq) * ex

        # covariance: P = F P F^T + Q (Q mode-gated to observable params)
        self.p = _matmul(_matmul(f, self.p), _transpose(f))
        self.p[_T][_T] += _Q[_T]
        self.p[_A][_A] += _Q[_A]
        if u_h > 0.0:
            self.p[_BH][_BH] += _Q[_BH]
        if u_c > 0.0:
            self.p[_BC][_BC] += _Q[_BC]
        if q_solar > 0.0:
            self.p[_BS][_BS] += _Q[_BS]
        if q_occ > 0.0:
            self.p[_BO][_BO] += _Q[_BO]
        self._enforce_psd()

    # -- measurement update --------------------------------------------------
    def update(self, z_temp: float) -> None:
        innovation = z_temp - self.x[_T]
        s = self.p[_T][_T] + _R
        r_eff = _R
        if innovation * innovation > (_ANOMALY_SIGMA**2) * s:
            # outlier: inflate R so the correction is capped at anomaly_sigma
            # worth of movement, regardless of the spike magnitude (Mahalanobis
            # clip). Bounds parameter drift from a single bad reading (ADR-0009).
            r_eff = max(
                _R * _ANOMALY_INFLATE,
                innovation * innovation / (_ANOMALY_SIGMA**2) - self.p[_T][_T],
            )
            s = self.p[_T][_T] + r_eff

        k = [self.p[i][_T] / s for i in range(_N)]  # Kalman gain (measurement = T)
        for i in range(_N):
            self.x[i] += k[i] * innovation

        # Joseph form: P = (I-KH) P (I-KH)^T + K r_eff K^T, with H = e_T
        a = _identity()
        for i in range(_N):
            a[i][_T] -= k[i]
        self.p = _matmul(_matmul(a, self.p), _transpose(a))
        for i in range(_N):
            ki = k[i]
            for j in range(_N):
                self.p[i][j] += ki * r_eff * k[j]

        self._clamp()
        self._enforce_psd()
        self.n_updates += 1

    # -- helpers -------------------------------------------------------------
    def _clamp(self) -> None:
        for i in range(_N):
            self.x[i] = min(max(self.x[i], _LOWER[i]), _UPPER[i])

    def _enforce_psd(self) -> None:
        for i in range(_N):
            for j in range(i + 1, _N):
                avg = 0.5 * (self.p[i][j] + self.p[j][i])
                self.p[i][j] = self.p[j][i] = avg
            if self.p[i][i] < _PSD_FLOOR:
                self.p[i][i] = _PSD_FLOOR

    # -- outputs -------------------------------------------------------------
    def get_model(self) -> ThermalModel:
        return ThermalModel(
            alpha=self.x[_A],
            beta_h=self.x[_BH],
            beta_c=self.x[_BC],
            beta_s=self.x[_BS],
            beta_o=self.x[_BO],
        )

    @property
    def tau_hours(self) -> float:
        return 1.0 / self.x[_A]

    @property
    def temperature_std(self) -> float:
        return math.sqrt(self.p[_T][_T])

    @property
    def confidence(self) -> float:
        return min(1.0, max(0.0, 1.0 - self.temperature_std))

    # -- persistence (ADR-0007) ---------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "ekf_version": EKF_VERSION,
            "x": list(self.x),
            "p": [row[:] for row in self.p],
            "n_updates": self.n_updates,
            "n_heating": self.n_heating,
            "n_cooling": self.n_cooling,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThermalEKF:
        ekf = cls(list(data["x"]))
        ekf.p = [list(row) for row in data["p"]]
        ekf.n_updates = int(data.get("n_updates", 0))
        ekf.n_heating = int(data.get("n_heating", 0))
        ekf.n_cooling = int(data.get("n_cooling", 0))
        # recovery: a parameter pegged at its bound on load is unreliable ->
        # reset RC parameters to defaults but keep the observation counters so
        # the maturity gates stay satisfied while it re-learns (ADR-0007/0009).
        if ekf.x[_A] >= _UPPER[_A] * 0.99 or ekf.x[_A] <= _LOWER[_A] * 1.01:
            for i in (_A, _BH, _BC, _BS, _BO):
                ekf.x[i] = _DEFAULTS[i]
                ekf.p[i][i] = _P0[i]
        ekf._clamp()
        ekf._enforce_psd()
        return ekf
