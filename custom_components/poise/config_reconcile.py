"""Pure config-entry reconcile helper for the reconfigure flow (review V7)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def reconfigure_options(
    user_input: Mapping[str, Any], old_options: Mapping[str, Any]
) -> dict[str, Any]:
    """The options to keep after a room reconfigure fully replaces ``data``.

    The coordinator reads ``{**entry.data, **entry.options}`` — options win. So any
    key the reconfigure form now writes into ``data`` must be dropped from
    ``options``, or the stale option value would permanently shadow the new data
    value (the Options<->Data divergence, incl. climate_mode; review V7). Options-
    only tuning the reconfigure schema does not own (outdoor lockouts, tariff) is
    kept so it survives a reconfigure.
    """
    return {k: v for k, v in old_options.items() if k not in user_input}
