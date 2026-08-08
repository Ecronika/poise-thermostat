"""ADR-0050 mode-arbitration seam — one HVAC mode per tick (pure)."""

from __future__ import annotations

from custom_components.poise.comfort.mode_seam import mode_arbitration


def test_dry_replaces_idle_when_humid_and_capable() -> None:
    assert (
        mode_arbitration(base_mode="idle", humidity_action="dry", dry_ok=True) == "dry"
    )


def test_idle_stays_when_not_dry_capable() -> None:
    # capability-gated: a heat-only TRV (dry_ok False) is a no-op
    assert (
        mode_arbitration(base_mode="idle", humidity_action="dry", dry_ok=False)
        == "idle"
    )


def test_idle_stays_when_humidity_not_dry() -> None:
    for action in ("idle", "dry_guard", "cool"):
        assert (
            mode_arbitration(base_mode="idle", humidity_action=action, dry_ok=True)
            == "idle"
        )


def test_temperature_and_safety_modes_never_overridden() -> None:
    # heat / cool / off / manual keep precedence over active drying
    for base in ("heat", "cool", "off", "manual"):
        assert (
            mode_arbitration(base_mode=base, humidity_action="dry", dry_ok=True) == base
        )


# --- ADR-0068 U5: the ONE deliberate invariant change ------------------------


def test_fan_first_intercepts_exactly_a_normal_cool() -> None:
    # The second, explicitly gated escape hatch (Rev. 4): a NORMAL cool may
    # be intercepted to the compressor-free first stage.
    assert (
        mode_arbitration(
            base_mode="cool", humidity_action="idle", dry_ok=True, fan_first=True
        )
        == "fan_only"
    )
    # Every other base mode is untouchable by fan_first — including the
    # idle->dry hatch (dry keeps its own precedence over the fan stage).
    for base in ("heat", "off", "manual", "idle"):
        assert (
            mode_arbitration(
                base_mode=base, humidity_action="idle", dry_ok=True, fan_first=True
            )
            == base
        )
    assert (
        mode_arbitration(
            base_mode="idle", humidity_action="dry", dry_ok=True, fan_first=True
        )
        == "dry"
    )


def test_fan_first_defaults_off_and_changes_nothing() -> None:
    # Safe migration shape: without the flag the seam is byte-identical.
    for base in ("heat", "cool", "off", "manual", "idle"):
        assert (
            mode_arbitration(base_mode=base, humidity_action="idle", dry_ok=True)
            == base
        )
