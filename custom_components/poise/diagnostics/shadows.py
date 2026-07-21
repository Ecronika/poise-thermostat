"""Pure composition wrappers for the diagnostics shadows.

Every evaluation *kernel* is already a pure function in its established module
(``predict_peak_operative``/``shading_target_position`` in
``control/cover_shading.py``, ``evaluate_shadow`` in ``control/mpc_shadow.py``,
``evaluate_thermal_shadow`` in ``multi/shadow.py``, the comfort indices in
``comfort/*``, the outcome/savings folds in ``control``/``estimation``).  This
module therefore holds only COMPOSITION: the argument preparation and dict
assemblies the coordinator's finalize/climate segments performed inline.  The
*call sites* — and with them both LEGACY error domains (the ONE shadow ``try``
in ``finalize_tick``, the ONE climate-band ``try`` in ``_stage_climate_band``)
— stay in the coordinator until F-TPI/F-LIFECYCLE/F-PIACC/F-HUMSHADOW.

PATCH SURFACES: the finalize domain dispatches ``predict_peak_operative``,
``evaluate_shadow``, ``evaluate_tpi_shadow``, ``evaluate_pi_shadow`` and the
``_lifecycle`` module alias via COORDINATOR module globals — integration tests
patch them there (``test_phase0_fault_shadow_domain`` patches
``coordinator.predict_peak_operative``).  Every composition that moved such a
call therefore takes it as a ``*_fn`` parameter which the coordinator resolves
from its own module globals at call time; nothing here binds those names at
import time.  The kernels no test patches on the coordinator (comfort indices,
``rh_high_for_category``, ``settle_confidence``, ``compensated_setpoint``) are
imported directly.

Error-path residual: ``evaluate_cover_shadow`` fuses the peak forecast +
shading decision + binding classification into one call, so a raise in
``shading_target_position_fn`` AFTER a successful peak forecast leaves the
caller's peak default in place.  ``shading_target_position`` is total for every
finite or NaN float input (only comparisons, ``abs``, ``min`` and ``int()`` on
the literal ``0.0``/finite products; a NaN peak falls through to the "hold"
branch) — the sole raising input is a ``+inf`` peak (``int(inf)`` →
``OverflowError``), which requires a degenerate ``+inf``-producing EKF model
while identified.  The window is therefore practically unreachable; recorded
here instead of splitting the mandated composition.

Hass-free, mypy --strict, py310-clean; measured by the PURE coverage gate
(``tests/test_phase8_shadows.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from ..comfort.fan_circulation import FAN_ONLY_LOW, fan_circulation
from ..comfort.fan_cooling import fan_cool_setpoint, fan_velocity
from ..comfort.free_running import free_running_widen
from ..comfort.humidity import rh_high_for_category
from ..comfort.pmv import pmv_ppd, seasonal_clo
from ..control.reference_offset import compensated_setpoint
from ..estimation.tau_settle import settle_confidence
from ..multi.discovery import EntitySnapshot
from ..multi.resolvers import ThermalDemand

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ..comfort.en16798 import Category
    from ..comfort.humidity import HumidityDecision
    from ..comfort.thermal_shock import AdaptiveCool
    from ..control.hdh_savings import HdhConfig, HdhSavings
    from ..control.mpc_shadow import MpcShadow
    from ..control.outcome_scoring import OutcomeStats
    from ..control.pi_shadow import PiShadow
    from ..control.reference_offset import OffsetEstimate
    from ..control.regulation_quality import RegulationQuality
    from ..control.tpi_shadow import TpiShadow
    from ..estimation.tau_settle import TauSettle
    from ..estimation.thermal_ekf import ThermalModel
    from ..multi.lifecycle import DeviceLifecycle, LifecyclePolicy
    from ..multi.model import Direction
    from ..multi.resolvers import DeviceRuntime
    from ..multi.shadow import ThermalShadow


class PredictPeakOperativeFn(Protocol):
    """Call shape of ``control.cover_shading.predict_peak_operative``."""

    def __call__(
        self,
        t_now: float,
        t_out: float,
        q_series: list[float],
        *,
        alpha: float,
        beta_s: float,
        dt_h: float,
        confident: bool,
    ) -> float: ...


class ShadingTargetPositionFn(Protocol):
    """Call shape of ``control.cover_shading.shading_target_position``."""

    def __call__(
        self,
        *,
        peak: float,
        t_upper: float,
        current_position: float,
        oriented_q: float,
    ) -> tuple[int, str]: ...


class EvaluateThermalShadowFn(Protocol):
    """Call shape of ``multi.shadow.evaluate_thermal_shadow``."""

    def __call__(
        self,
        snapshot: EntitySnapshot,
        demand: ThermalDemand,
        *,
        runtime: DeviceRuntime | None,
    ) -> ThermalShadow: ...


def neutral_shadow_objs(lifecycle_health: str) -> dict[str, Any]:
    """The neutral shadow fallback for a shadow-domain failure.

    Deliberately WITHOUT the ``compressor_gate_would_block`` /
    ``compressor_mode_hold_remaining`` keys: on a shadow-domain failure the
    published available key set SHRINKS by exactly those two keys.
    ``lifecycle_health`` is the pre-tick lifecycle's health — the fold is
    skipped on the degraded path, so the pre-fault value survives
    (pinned by test_phase0_fault_shadow_domain).
    """
    return {
        "pi_active": False,
        "pi_setpoint": None,
        "pi_offset": None,
        "multi_active_source": None,
        "multi_reason": "shadow_error",
        "multi_severity": "info",
        "multi_blocked": [],
        "multi_min_off_remaining": 0,
        "multi_device_health": lifecycle_health,
        "tpi_active": False,
        "tpi_duty": None,
        "tpi_valve_percent": None,
        "mpc_active": False,
        "mpc_power": None,
        "mpc_weight": None,
        "mpc_setpoint": None,
        "mpc_regime": "hold",
    }


def evaluate_cover_shadow(
    *,
    operative: float,
    t_out_eff: float,
    q_solar: float,
    cool_sp: float,
    heat_sp: float,
    mold_min: float | None,
    model: ThermalModel,
    identified: bool,
    temperature_std: float,
    predict_peak_operative_fn: PredictPeakOperativeFn,
    shading_target_position_fn: ShadingTargetPositionFn,
) -> tuple[float, int, str, str]:
    """Predictive solar-shading shadow (ADR-0043) + binding classification.

    Forecasts the peak operative temperature (Tier-2 linear while the EKF is
    not identified, e.g. summer) and what a cover *would* do — diagnostic
    only, no cover is moved.  Returns ``(peak, position, reason, binding)``.
    The two kernels arrive as ``*_fn`` parameters resolved by the coordinator
    from its module globals at call time (``predict_peak_operative`` is the
    patched fault-injection surface).
    """
    peak = predict_peak_operative_fn(
        operative,
        t_out_eff,
        [q_solar] * 36,
        alpha=model.alpha,
        beta_s=model.beta_s,
        dt_h=5.0 / 60.0,
        confident=identified and temperature_std < 0.5,
    )
    pos, reason = shading_target_position_fn(
        peak=peak,
        t_upper=cool_sp,
        current_position=0.0,
        oriented_q=q_solar,
    )
    binding = "mold" if mold_min and mold_min >= heat_sp else "en16798"
    return peak, pos, reason, binding


def capped_elapsed_min(last_mono: float | None, now: float, tick_min: float) -> float:
    """Real elapsed minutes since ``last_mono``, capped at two ticks.

    Event-driven refreshes book < 60 s, not a flat tick; the cap keeps a masked
    gap at ~2 ticks instead of silently over/under-crediting the
    HDH/outcome/CA/offset/tau folds.  First observation (``last_mono is None``)
    books exactly one tick.  The anchors themselves stay owned by the caller.
    """
    if last_mono is not None:
        elapsed = (now - last_mono) / 60.0
        return min(max(elapsed, 0.0), 2.0 * tick_min)
    return tick_min


def evaluate_multi_shadow(
    *,
    entity_id: str,
    hvac_modes: Iterable[object],
    available: bool,
    direction: Direction | None,
    target: float | None,
    runtime: DeviceRuntime,
    evaluate_thermal_shadow_fn: EvaluateThermalShadowFn,
) -> ThermalShadow:
    """Thermal-arbitration shadow (ADR-0046): transient ZoneDevice.

    Builds the ``EntitySnapshot``/``ThermalDemand`` inputs and dispatches the
    kernel via ``*_fn`` (the coordinator resolves ``evaluate_thermal_shadow``
    from its globals at call time).  Runs INSIDE the legacy shadow domain,
    after the lifecycle fold.
    """
    return evaluate_thermal_shadow_fn(
        EntitySnapshot(
            entity_id=entity_id,
            domain="climate",
            hvac_modes=tuple(str(m) for m in hvac_modes),
            available=available,
        ),
        ThermalDemand(direction, target),
        runtime=runtime,
    )


def assemble_shadow_objs(
    *,
    pi: PiShadow,
    multi_shadow: ThermalShadow,
    tpi: TpiShadow,
    shadow: MpcShadow,
    lifecycle: DeviceLifecycle,
    now_wall: float,
    multi_policy: LifecyclePolicy,
    comp_pol: LifecyclePolicy,
    comp_block: str | None,
    min_off_remaining_fn: Callable[[DeviceLifecycle, float, LifecyclePolicy], float],
    mode_hold_remaining_fn: Callable[[DeviceLifecycle, float, LifecyclePolicy], float],
) -> dict[str, Any]:
    """The healthy-path ``shadow_objs`` assembly (19 keys).

    Superset of :func:`neutral_shadow_objs` plus the two ``compressor_gate_*``
    keys.  ``lifecycle`` is the freshly folded ``DeviceLifecycle``; the two
    remaining-time kernels arrive as ``*_fn`` parameters so the coordinator
    keeps dispatching them through its ``_lifecycle`` module-global alias at
    call time.
    """
    return {
        "pi_active": pi.active,
        "pi_setpoint": pi.setpoint,
        "pi_offset": pi.offset,
        "multi_active_source": multi_shadow.active_source,
        "multi_reason": multi_shadow.reason,
        "multi_severity": multi_shadow.severity,
        "multi_blocked": list(multi_shadow.blocked),
        "multi_min_off_remaining": round(
            min_off_remaining_fn(lifecycle, now_wall, multi_policy)
        ),
        "multi_device_health": lifecycle.health,
        "compressor_gate_would_block": comp_block or "",
        "compressor_mode_hold_remaining": round(
            mode_hold_remaining_fn(lifecycle, now_wall, comp_pol)
        ),
        "tpi_active": tpi.active,
        "tpi_duty": tpi.duty,
        "tpi_valve_percent": tpi.valve_percent,
        "mpc_active": shadow.active,
        "mpc_power": shadow.power,
        "mpc_weight": shadow.weight,
        "mpc_setpoint": shadow.setpoint,
        "mpc_regime": shadow.regime,
    }


def compose_climate_band(
    *,
    heat_sp: float,
    cool_sp: float,
    room: float,
    room_decide: float,
    t_rm_eff: float,
    t_mrt: float,
    rh: float | None,
    eff_cool: float,
    mode: str,
    window_open: bool,
    occupied: bool,
    presence_level: str,
    absent_min: float,
    home_present: bool | None,
    category: Category,
    cool_hard_cap: float,
    cool_ac: AdaptiveCool | None,
    hum: HumidityDecision,
    abs_humidity_gkg: float | None,
    hvac_modes: list[str],
    has_fan_modes: bool,
    fan_mode: str | None,
    hvac_action: str | None,
) -> dict[str, object]:
    """Pure climate-band shadow composition + ``climate_diag`` assembly.

    The free-running (ADR-0023 §1), idle-recirculation fan (ADR-0053),
    elevated-air-speed cool setpoint (ASHRAE 55) and PMV/PPD (ADR-0054,
    ISO 7730) shadows over the *effective* (raised) cool band, plus the
    assembled diagnostics dict.  The humidity decision itself (and the
    ``_dry_active`` latch) stays LIVE in the coordinator's
    ``_stage_climate_band``; this composition is called INSIDE that same single
    ``try``, so a failure anywhere still degrades the whole ``climate_diag``
    together (until F-HUMSHADOW).

    ``fan_velocity`` estimates the occupied-zone air speed from the actuator's
    real fan state (still air unless the indoor fan actually moves air) — feeds
    the fan-CE + PMV SHADOW only; the write path keeps the 0.1 baseline.  No
    presence entity yet for the fan preview → the presence-less opt-in path
    with the policy forced on.
    """
    # ADR-0023 §1 free-running widening (shadow): the EN adaptive band
    # widens the dead-band only while the room floats in the fixed band.
    fr = free_running_widen(
        heat_op=heat_sp,
        cool_op=cool_sp,
        room=room_decide,
        t_rm=t_rm_eff,
        category=category,
    )
    # ADR-0053 idle-recirculation SHADOW (preview, no writes).
    can_recirc = "fan_only" in hvac_modes or has_fan_modes
    fan = fan_circulation(
        occupied=occupied,
        in_deadband=heat_sp <= room_decide <= eff_cool,
        active_mode=mode,
        window_open=window_open,
        can_recirculate=can_recirc,
        policy=FAN_ONLY_LOW,
        presence_optin=True,
    )
    # Elevated air speed (ASHRAE 55) SHADOW.
    fan_v = fan_velocity(
        fan_mode=fan_mode, hvac_action=hvac_action, can_recirculate=can_recirc
    )
    fan_cool_sp, fan_ce = fan_cool_setpoint(
        cool_sp=eff_cool,
        air_speed=fan_v,
        fan_running=can_recirc,
        upper_cap=cool_hard_cap,
    )
    # ADR-0054 SHADOW: ISO 7730 PMV/PPD — humidity and the (estimated) fan
    # velocity finally enter the comfort evaluation; diagnostic only.
    pmv = pmv_ppd(
        t_air=room,
        t_mrt=t_mrt if t_mrt is not None else room,
        rh=rh if rh is not None else 50.0,
        velocity=fan_v,
        clo=seasonal_clo(t_rm_eff),
    )
    return {
        "cool_sp_eff": cool_ac.cool_sp_eff if cool_ac else cool_sp,
        "cool_sp_active": round(eff_cool, 1),
        "cool_raised": cool_ac.raised if cool_ac else False,
        "cool_raise_reason": cool_ac.reason if cool_ac else "n/a",
        "en_cool_upper": cool_ac.en_upper if cool_ac else 0.0,
        "humidity_action": hum.action,
        "dry_active": hum.dry_active,
        "humidity_reason": hum.reason,
        "abs_humidity_gkg": (
            round(abs_humidity_gkg, 1) if abs_humidity_gkg is not None else None
        ),
        "rh_high_used": rh_high_for_category(category),
        "fr_active": fr.active,
        "fr_heat_sp": round(fr.heat_op, 1),
        "fr_cool_sp": round(fr.cool_op, 1),
        "fr_adaptive_lower": round(fr.adaptive_lower, 1),
        "fr_adaptive_upper": round(fr.adaptive_upper, 1),
        "fan_circ_shadow": fan.action,
        "fan_ce_k": fan_ce,
        "fan_cool_sp_shadow": fan_cool_sp,
        "fan_velocity_ms": round(fan_v, 2),
        "fan_circ_reason": fan.reason,
        "occupied": occupied,
        "presence_level": presence_level,
        "room_absent_min": round(absent_min, 1),
        "home_present": home_present,
        "pmv": pmv.pmv,
        "ppd": pmv.ppd,
        "pmv_category": pmv.category,
    }


def build_outcome_diag(
    *,
    outcome_stats: OutcomeStats,
    hdh: HdhSavings,
    hdh_cfg: HdhConfig,
    regq: RegulationQuality,
    ref_offset: OffsetEstimate | None,
    ref_conditioning: bool,
    tau_settle: TauSettle | None,
    eff_cool: float,
) -> dict[str, Any]:
    """The healthy-path ``outcome_diag`` assembly over freshly folded state.

    Pure read-only assembly (ADR-0044/0045/0055/0056) — the state folds
    themselves stay with the caller inside the one
    ``DiagnosticsCollector.safe_collect`` boundary, in order.
    """
    rep = hdh.report(hdh_cfg)
    return {
        "outcome_last_score": outcome_stats.last_score,
        "outcome_ts_avg": outcome_stats.ts_avg,
        "outcome_obs_avg": outcome_stats.obs_avg,
        "outcome_n": outcome_stats.ts_n + outcome_stats.obs_n,
        "savings_kwh_month": rep["kwh"],
        "savings_eur_month": rep["eur"],
        "savings_pct": rep["pct"],
        "ca_deviation_k": round(regq.deviation_k, 3),
        "ca_time_in_band": regq.time_in_band_pct,
        "ca_cycles_per_h": round(regq.cycles_per_hour, 2),
        "ca_minutes": round(regq.minutes, 0),
        "ref_offset": (round(ref_offset.offset, 2) if ref_offset is not None else None),
        "ref_offset_dev": (
            round(ref_offset.deviation, 2) if ref_offset is not None else None
        ),
        "ref_offset_trusted": (ref_offset.trusted if ref_offset is not None else None),
        "ref_offset_conditioning": ref_conditioning,
        "tau_confidence": round(settle_confidence(tau_settle), 3),
        "tau_settled": (tau_settle.settled if tau_settle is not None else None),
        "tau_settle_minutes": (
            round(tau_settle.minutes, 0) if tau_settle is not None else None
        ),
        "cool_sp_compensated": (
            compensated_setpoint(eff_cool, ref_offset, enabled=True)
            if ref_offset is not None
            else None
        ),
    }
