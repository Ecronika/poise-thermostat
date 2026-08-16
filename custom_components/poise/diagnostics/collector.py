"""The one broad error boundary for pure outcome/savings diagnostics.

``DiagnosticsCollector.safe_collect()`` IS the outcome-diagnostics boundary of
``ReportPhase._stage_outcome_diag``: defaults init + one ``try`` around the six
state folds (HDH + outcome session/stats, CA/PPD regulation quality, tier-2
activation stepping, tier-2 solver inputs, reference offset, tau settle) and
the assembly, + the swallowing DEBUG log.  Pulling the state updates OUT of the
boundary is not behaviour-equivalently implementable: the folds sit INSIDE it,
so an exception in fold N leaves ``outcome_diag`` on the defaults (key shrink),
skips folds N+1… and freezes the metrics until the next healthy tick — folds
behind their own boundaries would either throw the tick (currently swallowed)
or degrade differently.  That stays the deferred candidate **F-OUTFOLD**.  Plan
O.6 did the part that IS equivalent: the folds became ``ReportPhase._fold_*``
methods called from inside the very same ``collect_fn``, in unchanged text
order (state mutated in place, assembly via ``shadows.build_outcome_diag``).

Never computes ``tpi_duty``, the lifecycle fold or ``_pi.acc`` — each of
those owns its own shadow-segment boundary in ``_stage_shadow_domain``
(ADR-0065).

The logger is injected (the channel is behaviour) — the coordinator passes its
own ``_LOGGER`` so the swallow record keeps the
``custom_components.poise.coordinator`` channel with identical
text/level/``exc_info``.  Hass-free, mypy --strict, py310-clean; measured by
the PURE coverage gate (``tests/test_phase8_shadows.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable


class DiagnosticsCollector:
    """Thin boundary wrapper: run ``collect_fn``, degrade to ``defaults``."""

    __slots__ = ("_logger",)

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def safe_collect(
        self,
        collect_fn: Callable[[], dict[str, Any]],
        defaults: dict[str, Any],
    ) -> dict[str, Any]:
        """The one broad boundary (diagnostic only; never raises).

        ``defaults`` is a fresh per-call dict that is never mutated, only
        returned as-is on failure — the replace-on-success semantics.
        """
        try:
            return collect_fn()
        except Exception:  # noqa: BLE001 - diagnostics must never break control
            self._logger.debug(
                "Poise outcome/savings diagnostics failed", exc_info=True
            )
            return defaults
