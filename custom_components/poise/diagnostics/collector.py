"""The one broad error boundary for pure outcome/savings diagnostics.

``DiagnosticsCollector.safe_collect()`` IS the coordinator's second finalize
boundary: defaults init + one ``try`` around the five state folds (HDH, outcome
session/stats, CA regulation quality, reference offset, tau settle) and the
assembly, + the swallowing DEBUG log.  Pulling the state updates out first is
NOT behaviour-equivalently implementable here: the folds sit INSIDE the
boundary, so an exception in fold N leaves ``outcome_diag`` on the defaults
(key shrink), skips folds N+1… and freezes the metrics until the next healthy
tick — extracted folds would either throw the tick (currently swallowed) or
degrade differently.  The extraction is therefore a deferred candidate
(**F-OUTFOLD**); until then the coordinator passes a ``collect_fn`` that runs
folds + assembly in text order (mutations on the runtime state in place, pure
assembly via ``diagnostics.shadows.build_outcome_diag``).

Never computes ``tpi_duty``, the lifecycle fold or ``_pi.acc`` — those live in
the FIRST (legacy shadow) boundary of ``finalize_tick``.

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
