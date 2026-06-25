"""Outcome scoring — does Poise's control actually add value? (ADR-0044).

A self-validation score per heating session (ThermoSmart *method*, re-implemented
from the verified formula in `Mikasmarthome/ThermoSmart` `learning_engine.py`):
reached (40%) + speed (35%) + accuracy (25%), times a **reliability discount**
that devalues sessions where strong sun or mild outdoor weather did the heating
for free. Each session is tagged ``"ts"`` (Poise actively controlled) vs
``"obs"`` (observed only) so the two populations can be compared — a real A/B of
whether the controller helps. The only field-unique self-validation feature
(concept Feat 3). Pure and unit-tested; the coordinator runs the lifecycle and
persists the running stats. q_solar is Poise's normalised solar in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ScoreConfig:
    w_reached: float = 0.40
    w_speed: float = 0.35
    w_accuracy: float = 0.25
    overshoot_scale: float = 2.0  # accuracy = 1 - overshoot/this
    # reliability discount (free heat -> less reliable); q_solar is normalised [0,1]
    solar_floor: float = 0.60
    solar_knee: float = 0.4  # ~400 W/m2 normalised
    solar_range: float = 2.0
    warm_floor: float = 0.70
    warm_knee: float = 15.0  # degC outdoor
    warm_range: float = 25.0
    # difficulty correctors make the SPEED score lenient in hard weather
    cold_outdoor: float = -5.0
    cold_factor: float = 1.40
    wind_thr: float = 10.0
    wind_factor: float = 1.25
    humid_thr: float = 80.0
    humid_factor: float = 1.10
    rain_factor: float = 1.10
    neutral_speed: float = 0.6  # when no expectation is available
    min_expected: float = 5.0
    # session lifecycle thresholds
    reach_delta: float = 0.5
    start_delta: float = 0.5
    timeout_min: float = 90.0
    min_session_min: float = 3.0


_DEFAULT = ScoreConfig()


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def reached_score(
    reason: str, start_temp: float, end_temp: float, peak_temp: float, target: float
) -> float:
    """1.0 if the target was reached, else the fraction of the gap that closed."""
    delta_total = target - start_temp
    if delta_total <= 0.0 or reason == "reached":
        return 1.0
    ref = peak_temp if reason == "interrupt" else end_temp
    return _clamp01((ref - start_temp) / delta_total)


def speed_score(
    minutes_taken: float,
    expected_minutes: float,
    *,
    outdoor: float = 10.0,
    wind: float = 0.0,
    humidity: float = 0.0,
    rain: bool = False,
    cfg: ScoreConfig = _DEFAULT,
) -> float:
    """Difficulty-adjusted time-to-target score (lenient in hard weather)."""
    if expected_minutes <= cfg.min_expected:
        return cfg.neutral_speed
    difficulty = 1.0
    if outdoor < cfg.cold_outdoor:
        difficulty *= cfg.cold_factor
    if wind > cfg.wind_thr:
        difficulty *= cfg.wind_factor
    if humidity > cfg.humid_thr:
        difficulty *= cfg.humid_factor
    if rain:
        difficulty *= cfg.rain_factor
    ratio = minutes_taken / (expected_minutes * difficulty)
    if ratio <= 1.0:
        return 1.0
    if ratio <= 2.0:
        return 1.0 - (ratio - 1.0) * 0.7
    return max(0.05, 0.3 - (ratio - 2.0) * 0.1)


def accuracy_score(
    peak_temp: float, target: float, cfg: ScoreConfig = _DEFAULT
) -> float:
    """1.0 minus the overshoot above target (scaled); floored at 0."""
    overshoot = max(0.0, peak_temp - target)
    return max(0.0, 1.0 - overshoot / cfg.overshoot_scale)


def env_discount(q_solar: float, outdoor: float, cfg: ScoreConfig = _DEFAULT) -> float:
    """Reliability discount: strong sun / mild outdoor devalues a 'win' (free heat)."""
    sd = (
        max(cfg.solar_floor, 1.0 - (q_solar - cfg.solar_knee) / cfg.solar_range)
        if q_solar > cfg.solar_knee
        else 1.0
    )
    wd = (
        max(cfg.warm_floor, 1.0 - (outdoor - cfg.warm_knee) / cfg.warm_range)
        if outdoor > cfg.warm_knee
        else 1.0
    )
    return sd * wd


def outcome_score(
    *,
    reason: str,
    start_temp: float,
    end_temp: float,
    peak_temp: float,
    target: float,
    minutes_taken: float,
    expected_minutes: float,
    q_solar: float = 0.0,
    outdoor: float = 10.0,
    wind: float = 0.0,
    humidity: float = 0.0,
    rain: bool = False,
    cfg: ScoreConfig = _DEFAULT,
) -> float:
    """Composite 0..1 outcome score for one finished session (3 dp)."""
    r = reached_score(reason, start_temp, end_temp, peak_temp, target)
    s = speed_score(
        minutes_taken,
        expected_minutes,
        outdoor=outdoor,
        wind=wind,
        humidity=humidity,
        rain=rain,
        cfg=cfg,
    )
    a = accuracy_score(peak_temp, target, cfg)
    raw = cfg.w_reached * r + cfg.w_speed * s + cfg.w_accuracy * a
    return round(_clamp01(raw * env_discount(q_solar, outdoor, cfg)), 3)


def session_end_reason(
    temp: float,
    target: float,
    elapsed_min: float,
    heating: bool,
    cfg: ScoreConfig = _DEFAULT,
) -> str | None:
    """Why (if at all) an open heating session ends this tick."""
    if (target - temp) <= cfg.reach_delta:
        return "reached"
    if elapsed_min >= cfg.timeout_min:
        return "timeout"
    if not heating:
        return "interrupt"
    return None


@dataclass(frozen=True, slots=True)
class OutcomeStats:
    """Running mean outcome score per controller tag (ts vs obs A/B)."""

    ts_sum: float = 0.0
    ts_n: int = 0
    obs_sum: float = 0.0
    obs_n: int = 0
    last_score: float | None = None

    def observe(self, score: float, controller: str) -> OutcomeStats:
        if controller == "obs":
            return OutcomeStats(
                self.ts_sum, self.ts_n, self.obs_sum + score, self.obs_n + 1, score
            )
        return OutcomeStats(
            self.ts_sum + score, self.ts_n + 1, self.obs_sum, self.obs_n, score
        )

    @property
    def ts_avg(self) -> float | None:
        return round(self.ts_sum / self.ts_n, 3) if self.ts_n else None

    @property
    def obs_avg(self) -> float | None:
        return round(self.obs_sum / self.obs_n, 3) if self.obs_n else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_sum": self.ts_sum,
            "ts_n": self.ts_n,
            "obs_sum": self.obs_sum,
            "obs_n": self.obs_n,
            "last_score": self.last_score,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OutcomeStats:
        return cls(
            ts_sum=float(d.get("ts_sum", 0.0)),
            ts_n=int(d.get("ts_n", 0)),
            obs_sum=float(d.get("obs_sum", 0.0)),
            obs_n=int(d.get("obs_n", 0)),
            last_score=d.get("last_score"),
        )
