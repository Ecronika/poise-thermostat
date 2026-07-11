"""Tests for the pure tri-state adaptive-cool resolver (ADR-0008)."""

from __future__ import annotations

from custom_components.poise.adaptive_cool import (
    adaptive_cool_mode,
    resolve_adaptive_cool,
)
from custom_components.poise.const import DEFAULT_ADAPTIVE_COOL


def test_mode_from_legacy_bool() -> None:
    assert adaptive_cool_mode(True) == "on"
    assert adaptive_cool_mode(False) == "off"


def test_mode_from_string() -> None:
    assert adaptive_cool_mode("auto") == "auto"
    assert adaptive_cool_mode("on") == "on"
    assert adaptive_cool_mode("off") == "off"
    assert adaptive_cool_mode("OFF") == "off"  # case-insensitive
    assert adaptive_cool_mode("weird") == "auto"  # unknown -> auto
    assert adaptive_cool_mode(None) == "auto"


def test_resolve_forced_ignores_capability() -> None:
    assert resolve_adaptive_cool("on", can_cool=False) is True
    assert resolve_adaptive_cool("off", can_cool=True) is False
    # a legacy boolean is honoured regardless of capability (zero-regression)
    assert resolve_adaptive_cool(True, can_cool=False) is True
    assert resolve_adaptive_cool(False, can_cool=True) is False


def test_resolve_auto_follows_capability() -> None:
    assert resolve_adaptive_cool("auto", can_cool=True) is True
    assert resolve_adaptive_cool("auto", can_cool=False) is False
    assert resolve_adaptive_cool(None, can_cool=True) is True  # default = auto


def test_default_is_auto_capability_default() -> None:
    """F1-pin: the shipped default is the tri-state ``auto``. The README/doc claim
    ("active by default on cool-capable devices") holds only because the default
    resolves to the device's cooling capability — pinning the const guards the
    doc<->code alignment against a silent default flip to ``off``/``on``."""
    assert DEFAULT_ADAPTIVE_COOL == "auto"
    assert resolve_adaptive_cool(DEFAULT_ADAPTIVE_COOL, can_cool=True) is True
    assert resolve_adaptive_cool(DEFAULT_ADAPTIVE_COOL, can_cool=False) is False
