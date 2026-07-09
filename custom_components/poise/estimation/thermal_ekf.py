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

# ---- tuning (ADR-0009) -----------------------------------------------------
_R: float = 0.04  # measurement noise variance (~0.2 °C std)
# process noise per *nominal* tick; predict() scales it by dt_h / _NOMINAL_DT_H so
# a longer or shorter step injects proportionally more or less noise (review F7).
_Q = (0.01, 0.0005, 0.005, 0.005, 0.002, 0.002)
_NOMINAL_DT_H: float = 1.0 / 60.0  # 60 s reference tick for the Q scaling above
_ANOMALY_SIGMA: float = 4.0
_ANOMALY_INFLATE: float = 100.0
_PSD_FLOOR: float = 1e-10

# Identifiability (ADR-0024)
_ALPHA_REF: float = 0.15  # reference alpha for drift damping
_IDLE_GATE: int = 60  # idle observations before the model is trusted
_ACTIVE_GATE: int = 20  # heating/cooling observations before trusted
_RECOVERY_PEG_COUNT: int = 50  # consecutive pegged updates -> runtime reset

# defaults & bounds
_DEFAULTS = (21.0, 0.15, 3.0, 4.0, 0.5, 0.3)
_LOWER = (-50.0, 0.005, 0.1, 0.1, 0.0, 0.0)
_UPPER = (60.0, 2.0, 200.0, 300.0, 50.0, 20.0)

_P0 = (1.0, 0.01, 1.0, 1.0, 0.5, 0.5)  # initial covariance diagonal
_SEED_BH_VAR: float = 25.0  # M4: variance a cold-start beta_h seed is held at

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
        self.n_idle: int = 0
        self.n_heating: int = 0
        self.n_cooling: int = 0
        self._last_mode: str = "idle"
        self._alpha_pegged_count: int = 0
        # ticks the cooling / occupancy inputs were actually excited; beta_c
        # / beta_o are unobservable until these grow (review B1).
        self._n_uc: int = 0
        self._n_qocc: int = 0

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
        if u_h > 0.0:
            self._last_mode = "heating"
        elif u_c > 0.0:
            self._last_mode = "cooling"
        else:
            self._last_mode = "idle"
        if u_c > 0.0:
            self._n_uc += 1
        if q_occ > 0.0:
            self._n_qocc += 1

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
        # F7: scale process noise by step length so variable ticks (a late/missed
        # tick, a restart) inject the right amount; == _Q at the nominal tick.
        q_scale = max(0.0, dt_h) / _NOMINAL_DT_H
        self.p[_T][_T] += _Q[_T] * q_scale
        # damp alpha process noise near low excitation so it is not pulled
        # to its bound when the loss is poorly observable (ADR-0024)
        self.p[_A][_A] += _Q[_A] * q_scale * min(1.0, (alpha / _ALPHA_REF) ** 2)
        if u_h > 0.0:
            self.p[_BH][_BH] += _Q[_BH] * q_scale
        if u_c > 0.0:
            self.p[_BC][_BC] += _Q[_BC] * q_scale
        if q_solar > 0.0:
            self.p[_BS][_BS] += _Q[_BS] * q_scale
        if q_occ > 0.0:
            self.p[_BO][_BO] += _Q[_BO] * q_scale
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
        if self._last_mode == "heating":
            self.n_heating += 1
        elif self._last_mode == "cooling":
            self.n_cooling += 1
        else:
            self.n_idle += 1
        self._runtime_recovery()

    # -- helpers -------------------------------------------------------------
    def _clamp(self) -> None:
        for i in range(_N):
            self.x[i] = min(max(self.x[i], _LOWER[i]), _UPPER[i])

    def _enforce_psd(self) -> None:
        # symmetrise, then floor the diagonal
        for i in range(_N):
            for j in range(i + 1, _N):
                avg = 0.5 * (self.p[i][j] + self.p[j][i])
                self.p[i][j] = self.p[j][i] = avg
            if self.p[i][i] < _PSD_FLOOR:
                self.p[i][i] = _PSD_FLOOR
        # M3: bound each off-diagonal so |corr| <= 1 (every 2x2 principal minor
        # stays >= 0). A positive diagonal alone does not keep P positive
        # semi-definite; this repairs the cheap necessary condition every tick.
        for i in range(_N):
            for j in range(i + 1, _N):
                bound = math.sqrt(self.p[i][i] * self.p[j][j])
                if self.p[i][j] > bound:
                    self.p[i][j] = self.p[j][i] = bound
                elif self.p[i][j] < -bound:
                    self.p[i][j] = self.p[j][i] = -bound

    def _runtime_recovery(self) -> None:
        """Reset alpha if it stays pegged at a bound (low excitation, ADR-0024)."""
        alpha = self.x[_A]
        if alpha <= _LOWER[_A] * 1.01 or alpha >= _UPPER[_A] * 0.99:
            self._alpha_pegged_count += 1
            if self._alpha_pegged_count >= _RECOVERY_PEG_COUNT:
                self.x[_A] = _DEFAULTS[_A]
                self.p[_A][_A] = _P0[_A]
                self._alpha_pegged_count = 0
        else:
            self._alpha_pegged_count = 0

    # -- outputs -------------------------------------------------------------
    def seed_beta_h(self, value: float) -> None:
        """Cold-start prior: set the heating responsivity beta_h (clamped).

        Used once at bootstrap from the seasonless prior when no learned model
        was restored; never during live learning, so it cannot run in parallel
        with the filter (charter G6).
        """
        self.x[_BH] = min(max(value, _LOWER[_BH]), _UPPER[_BH])
        # M4: a cold-start seed is an informed guess, not a measurement — hold it
        # loosely (inflate its variance) so the filter moves off an arbitrary
        # beta_h quickly once real heating data arrives, instead of being biased.
        self.p[_BH][_BH] = max(self.p[_BH][_BH], _SEED_BH_VAR)

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
    def data_factor(self) -> float:
        idle = min(1.0, self.n_idle / _IDLE_GATE)
        active = min(1.0, max(self.n_heating, self.n_cooling) / _ACTIVE_GATE)
        return min(idle, active)

    @property
    def accuracy_factor(self) -> float:
        """Covariance-side confidence in [0, 1]: 1 minus the temperature
        std-dev (so ~1 K of state uncertainty maps to 0), clamped. The heuristic
        companion to the data-driven ``data_factor`` in ``confidence`` (ADR-0024).
        """
        return min(1.0, max(0.0, 1.0 - self.temperature_std))

    @property
    def confidence(self) -> float:
        # identifiability (data) blended with covariance accuracy (ADR-0024)
        data = self.data_factor
        return 0.3 * data + 0.7 * data * self.accuracy_factor

    @property
    def identified(self) -> bool:
        return (
            self.n_idle >= _IDLE_GATE
            and (self.n_heating >= _ACTIVE_GATE or self.n_cooling >= _ACTIVE_GATE)
            and self.temperature_std < 0.5
        )

    @property
    def cooling_identified(self) -> bool:
        """Whether beta_c (cooling responsivity) is trustworthy (review B1).

        beta_c is only observable if the cooling input u_c is actually excited.
        Since v0.133 the coordinator feeds u_c during the cooling season (ADR-0024,
        cool_drive_signal), so this becomes True once n_uc reaches the active gate;
        until then downstream (MPC / optimal-stop / TPI) must not trust beta_c --
        it stays at prior.
        """
        return self.identified and self._n_uc >= _ACTIVE_GATE

    @property
    def occupancy_identified(self) -> bool:
        """Whether beta_o (occupancy gain) is trustworthy (review B1).

        beta_o is never excited in the live wiring (q_occ is not fed), so this
        is False and beta_o stays at its prior -- flagged so it is not trusted.
        """
        return self.identified and self._n_qocc >= _ACTIVE_GATE

    @property
    def learning_phase(self) -> str:
        """Phase consistent with identifiability (not just update count, ADR-0024)."""
        if self.identified:
            return "identified"
        if self.data_factor >= 0.5:
            return "learning"
        if self.n_idle >= 5 or self.n_heating >= 1 or self.n_cooling >= 1:
            return "early"
        return "cold"

    # -- persistence (ADR-0007) ---------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "ekf_version": EKF_VERSION,
            "x": list(self.x),
            "p": [row[:] for row in self.p],
            "n_updates": self.n_updates,
            "n_idle": self.n_idle,
            "n_heating": self.n_heating,
            "n_cooling": self.n_cooling,
            "n_uc": self._n_uc,
            "n_qocc": self._n_qocc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThermalEKF:
        # M8: validate matrix shapes; a malformed x/P recovers with a fresh
        # model (documented corruption-recovery, ADR-0007) rather than loading a
        # P that crashes later in _matmul.
        # F23: an ekf_version *mismatch* is a migration, not corruption. Keep the
        # temperature state and the maturity counters, and fall the RC params
        # back to priors with a re-widened covariance -- exactly as the pegged
        # recovery below does. Discarding the whole model there wiped the
        # observation counters too, resetting hard-won filter maturity.
        try:
            version_ok = int(data.get("ekf_version", 0)) == EKF_VERSION
            x = [float(v) for v in data["x"]]
            p = [[float(v) for v in row] for row in data["p"]]
        except (KeyError, TypeError, ValueError):
            return cls()
        if len(x) != _N or len(p) != _N or any(len(row) != _N for row in p):
            return cls()
        if not all(math.isfinite(v) for v in x) or not all(
            math.isfinite(v) for row in p for v in row
        ):
            return cls()
        ekf = cls(x)
        # trust the stored covariance only within the same version; across a
        # bump keep the fresh P0 diagonal from __init__ (conservative re-widen).
        if version_ok:
            ekf.p = p
        ekf.n_updates = int(data.get("n_updates", 0))
        ekf.n_idle = int(data.get("n_idle", 0))
        ekf.n_heating = int(data.get("n_heating", 0))
        ekf.n_cooling = int(data.get("n_cooling", 0))
        ekf._n_uc = int(data.get("n_uc", 0))
        ekf._n_qocc = int(data.get("n_qocc", 0))
        # recovery: a parameter pegged at its bound on load -- or a model loaded
        # across a version bump -- is unreliable, so reset the RC parameters to
        # defaults but keep the observation counters so the maturity gates stay
        # satisfied while it re-learns (ADR-0007/0009, F23).
        if (
            not version_ok
            or ekf.x[_A] >= _UPPER[_A] * 0.99
            or ekf.x[_A] <= _LOWER[_A] * 1.01
        ):
            for i in (_A, _BH, _BC, _BS, _BO):
                ekf.x[i] = _DEFAULTS[i]
                ekf.p[i][i] = _P0[i]
        ekf._clamp()
        ekf._enforce_psd()
        return ekf
