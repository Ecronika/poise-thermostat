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
    it full-replaces ``data``. Three things must survive the shrink:
      * structural ``data`` keys the form does not render (controls_boiler,
        declared_power, flow_temp, source_policy) — carried back into ``data`` as-is,
      * options-only tuning the form doesn't touch (``kept``), and
      * tuning an older/fresh entry stored in ``data`` (``carried`` into options),
        so a comfort setting is never silently dropped.
    A live option value wins over a carried data value (edited more recently).
    """
    new_data = dict(user_input)
    # Structural data keys the shrunk form doesn't render would be lost on the full
    # data replace. They are not tuning, so carry them back into data unchanged
    # rather than letting them migrate to options.
    new_data.update(
        {
            k: v
            for k, v in old_data.items()
            if k not in user_input and k not in tuning_keys
        }
    )
    kept = {k: v for k, v in old_options.items() if k not in user_input}
    carried = {
        k: v
        for k, v in old_data.items()
        if k not in user_input and k in tuning_keys and k not in kept
    }
    return new_data, {**carried, **kept}
