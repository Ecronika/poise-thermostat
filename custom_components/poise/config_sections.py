"""Pure flatten/nest helpers for the sectioned options flow (ADR-0007/0008).

HA ``section()`` nests the submitted values one level: a form built from sections
returns ``{"comfort": {...}, "schedule": {...}, ...}``. Poise stores options FLAT
(the coordinator reads ``{**entry.data, **entry.options}``), so the options step
flattens on submit and nests the current effective values back for the suggested
values on display. Both are pure and HA-free (ADR-0005), so the round-trip is
unit-tested rather than only exercised live.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def flatten_sections(
    user_input: Mapping[str, Any], section_names: Iterable[str]
) -> dict[str, Any]:
    """Collapse a sectioned submit into a flat options dict.

    A key named in ``section_names`` whose value is a mapping is spread one level
    (its fields lifted to the top); any other key is copied as-is. Field keys
    never collide with section names, so the flat result is unambiguous — the
    stored shape stays flat and the coordinator/merge/reconfigure paths are
    untouched.
    """
    sections = set(section_names)
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in sections and isinstance(value, Mapping):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def nest_by_section(
    values: Mapping[str, Any], section_fields: Mapping[str, Iterable[str]]
) -> dict[str, Any]:
    """Group flat ``values`` into ``{section: {field: value}}`` for the suggested
    values shown on the sectioned form.

    Only fields actually present in ``values`` are carried; a field with no stored
    value is omitted so the schema default fills it (e.g. a never-set latent
    field shows its default). A section with no present fields is omitted.
    """
    nested: dict[str, Any] = {}
    for section, fields in section_fields.items():
        sub = {field: values[field] for field in fields if field in values}
        if sub:
            nested[section] = sub
    return nested
