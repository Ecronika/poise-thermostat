"""Explicit legacy-format migrations for the persisted zone store (phase 3).

v0 ("bare EKF"): the earliest Poise builds persisted ``ThermalEKF.to_dict()``
directly as the store payload.  Today's coordinator classifies ANY
non-``None`` store that is not a dict WITH an ``"ekf"`` key as this format
(``codec.decode`` returns ``kind == "legacy_bare_ekf"``) — including a dict
store that carries user-intent keys but no ``ekf`` key: those keys are
deliberately unreachable on this path (bound phase-0 finding 2, pinned by
``test_store_without_ekf_key_is_legacy_branch``).

Pure — no Home Assistant import.
"""

from __future__ import annotations

from typing import Any, cast

from ..estimation.thermal_ekf import ThermalEKF


def migrate_v0_bare_ekf(raw: object) -> ThermalEKF:
    """Parse a legacy v0 store as a bare ``ThermalEKF`` dict — exact today's
    semantics of ``self._ekf = ThermalEKF.from_dict(data)``.

    Deliberately does NOT catch: "corrupt -> fresh" stays with the CALLER
    (today: the coordinator's broad restore boundary logs
    "failed to restore learned model; starting fresh").  Garbage *values*
    inside a dict are recovered by ``ThermalEKF.from_dict`` itself (fresh
    model, no raise — including a dict without any EKF fields); only a
    structurally throwing payload (e.g. a list, which has no ``.get``)
    propagates.
    """
    # The cast is deliberate: today's coordinator feeds whatever the store
    # returned straight into ``from_dict`` — a non-dict raising
    # (AttributeError) into the caller's recovery boundary is pinned
    # behaviour, so no isinstance narrowing here.
    return ThermalEKF.from_dict(cast("dict[str, Any]", raw))
