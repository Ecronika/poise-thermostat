"""Pure diagnostics package (refactoring plan, phase 8 — plan section 2).

Home of the hass-free diagnostics building blocks: composition wrappers for
the shadow evaluations (``shadows``) and the one broad error boundary for the
pure outcome/savings diagnostics (``collector``).  The evaluation *kernels*
(MPC/PI/TPI/thermal shadows, comfort indices, outcome scoring, …) stay in
their established ``control``/``comfort``/``estimation``/``multi`` modules —
this package only composes them; the two LEGACY error domains (plan finding
11) remain marked ``try`` blocks in the coordinator until phase 10.

This package replaces the former ``diagnostics.py`` module: a regular package
shadows a same-named sibling module, and Home Assistant resolves the
config-entry diagnostics platform as ``custom_components.poise.diagnostics``
(``Integration.platforms_exists`` accepts the bare ``diagnostics`` directory
too).  The platform hook therefore moved verbatim into ``entry.py`` and is
re-exported here so both HA's ``getattr(platform, ...)`` lookup and the
existing ``from custom_components.poise.diagnostics import
async_get_config_entry_diagnostics`` imports keep working unchanged.
"""

from .entry import async_get_config_entry_diagnostics

__all__ = ["async_get_config_entry_diagnostics"]
