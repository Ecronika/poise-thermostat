"""The zone's hass-free runtime layer.

``zone_runtime.ZoneRuntime`` owns the long-lived domain state (``state``)
and the pure tick stages; the surrounding modules are its contracts:
input snapshots (``tick_inputs``), tick plans/outcomes and execution
reports (``tick_result``), the parsed zone configuration and its single
parser (``config``) and the listener reaction registry
(``input_registry``).  No Home Assistant import and no I/O anywhere in
this package.
"""
