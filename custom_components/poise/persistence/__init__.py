"""Persistence codec for the coordinator refactoring (plan phase 3).

``codec`` is the single owner of the store payload format: encoding the
zone state into the persisted dict and decoding it back in independently
robust sections (partial recovery — a corrupt learned-model section must
never cost the user-intent keys). ``migrations`` holds the explicit
legacy-format upgrades (e.g. the bare-EKF v0 store).

Pure stdlib + poise pure modules only — no Home Assistant imports; the
coordinator (HA adapter) owns store I/O and the ``ConfigEntryNotReady``
lifecycle decision. See docs/Konzepte/2026-07-18_Refactoring-Plan_coordinator.md.
"""
