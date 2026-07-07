"""Pure config-entry reconcile helper for the reconfigure flow (review V7)."""

from __future__ import annotations

from collections.abc import Collection, Mapping
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


def reconcile_reconfigure(
    user_input: Mapping[str, Any],
    old_data: Mapping[str, Any],
    old_options: Mapping[str, Any],
    tuning_keys: Collection[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a shrunk room reconfigure into ``(new_data, new_options)``.

    The reconfigure form now owns only structural + sensor + installation fields, so
    it full-replaces ``data``. Two things must survive the shrink:
      * options-only tuning the form doesn't touch (``kept``), and
      * tuning an older/fresh entry stored in ``data`` (``carried`` into options),
        so a comfort setting is never silently dropped.
    A live option value wins over a carried data value (edited more recently).
    """
    new_data = dict(user_input)
    kept = {k: v for k, v in old_options.items() if k not in user_input}
    carried = {
        k: v
        for k, v in old_data.items()
        if k not in user_input and k in tuning_keys and k not in kept
    }
    return new_data, {**carried, **kept}
