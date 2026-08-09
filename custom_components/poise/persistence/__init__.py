"""Storage-format codec and legacy migrations for one Poise zone.

``codec`` is the single owner of the store payload format: encoding the
zone state into the persisted dict and decoding it back in independently
robust sections (partial recovery — a corrupt learned-model section must
never cost the user-intent keys). ``migrations`` holds the explicit
legacy-format upgrades (e.g. the bare-EKF v0 store).

Pure stdlib + poise pure modules only — no Home Assistant imports; the
coordinator (HA adapter) owns store I/O and the ``ConfigEntryNotReady``
lifecycle decision.
"""
