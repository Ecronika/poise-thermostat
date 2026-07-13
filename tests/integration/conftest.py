"""HA-runtime integration tests for the glue layer (review Ü1/E4).

These exercise the *actual* actuating path under a real Home Assistant runtime
via ``pytest-homeassistant-custom-component``: the config flow, entity
setup/unload, the ``ConfigEntryNotReady`` guard, and one coordinator tick
including the write to the configured actuator. They complement the pure-core
suite, which never imports Home Assistant.

They require a modern HA (>= 2024.4, for ``ConfigFlowResult``). The sandbox
Python 3.10 caps HA at 2023.7, so when that API is absent we skip this whole
directory at *collection* time rather than fail — keeping the HA-free gate
(ruff/mypy/pytest on the pure core) completely unaffected.

Run them (CI, or locally on Python >= 3.12):

    pip install -r requirements-test.txt
    pytest tests/integration -o asyncio_mode=auto
"""

from __future__ import annotations

try:  # HA must be new enough for the 2024.x+ APIs this integration uses
    from homeassistant.config_entries import ConfigFlowResult  # noqa: F401

    _HA_MODERN = True
except ImportError:  # pragma: no cover - only on the too-old sandbox HA
    _HA_MODERN = False

# Skip the whole directory unless a modern HA is importable.
collect_ignore_glob = [] if _HA_MODERN else ["test_*.py"]


if _HA_MODERN:
    from datetime import timedelta

    import homeassistant.util.dt as dt_util
    import pytest
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    @pytest.fixture(autouse=True)
    def _auto_enable_custom_integrations(
        enable_custom_integrations: object,
    ) -> object:
        """Let Home Assistant discover ``custom_components/poise`` per test."""
        yield

    @pytest.fixture(autouse=True)
    async def _flush_delayed_store_writes(hass: HomeAssistant) -> object:
        """Drain HA-core Store delayed writes before the lingering-timer check.

        The config-entry and registry Stores persist via a delayed ``call_later``
        write; under coverage instrumentation the loop runs slowly enough that the
        timer is still pending when pytest-hacc's teardown asserts no lingering
        timers, flaking ``test_config_flow`` with "Lingering timer …
        ``Store._async_schedule_callback_delayed_write``" (review B-neu-2). Poise's
        own store writes are synchronous (``async_save``); the culprit is HA core.
        Advancing past the write delay — but under the 60 s coordinator interval,
        so no extra tick fires — drains those writes deterministically.
        """
        yield
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
        await hass.async_block_till_done()
