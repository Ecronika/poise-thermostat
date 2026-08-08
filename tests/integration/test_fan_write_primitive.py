"""CI tests for the ADR-0068 U3 ``set_fan_mode`` primitive + sequence.

Mirrors the pinned aspects of ``test_phase5a_executor.py`` /
``test_phase5b_sequences.py`` for the new fan channel: exact payload with
``blocking=False``, own-context tagging (attempt state — the id reports even
when the dispatch throws), the boundary log record and the report shape.
"""

from __future__ import annotations

import logging

import pytest
from homeassistant.core import HomeAssistant

from custom_components.poise.ha.actuator_executor import ActuatorExecutor

AC = "climate.ac"


@pytest.fixture
def executor(hass: HomeAssistant) -> ActuatorExecutor:
    return ActuatorExecutor(
        hass, logger=logging.getLogger("custom_components.poise.coordinator")
    )


async def test_set_fan_mode_dispatches_exact_payload_blocking_false(
    hass: HomeAssistant, executor: ActuatorExecutor
) -> None:
    calls = []
    hass.services.async_register("climate", "set_fan_mode", calls.append)
    await executor.set_fan_mode(AC, "low")
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert dict(calls[0].data) == {"entity_id": AC, "fan_mode": "low"}


async def test_run_fan_write_success_reports_and_tags(
    hass: HomeAssistant, executor: ActuatorExecutor
) -> None:
    calls = []
    hass.services.async_register("climate", "set_fan_mode", calls.append)
    report = await executor.run_fan_write(AC, "low", fan_changed=True)
    await hass.async_block_till_done()
    (execution,) = report.executions
    assert execution.effect_id == "fan_write"
    assert execution.attempted is True
    assert execution.success is True
    assert execution.context_id == calls[0].context.id
    assert execution.commanded_mode == "low"
    assert execution.fan_changed is True
    assert execution.commanded_value is None
    assert execution.pre_write_value is None


async def test_run_fan_write_failure_keeps_attempt_state_and_logs(
    hass: HomeAssistant,
    executor: ActuatorExecutor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No handler registered -> synchronous ServiceNotFound; the boundary
    # swallows, logs on the coordinator channel and keeps the context id.
    with caplog.at_level(logging.ERROR, logger="custom_components.poise.coordinator"):
        report = await executor.run_fan_write(AC, "high", fan_changed=False)
    (execution,) = report.executions
    assert execution.attempted is True
    assert execution.success is False
    assert execution.context_id is not None
    records = [
        r
        for r in caplog.records
        if r.name == "custom_components.poise.coordinator"
        and "set_fan_mode(high) failed" in r.getMessage()
    ]
    assert records and records[0].levelno == logging.ERROR
    assert records[0].exc_info is not None
