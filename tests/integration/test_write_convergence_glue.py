"""Write-convergence watchdog glue (review C.8): counter fold in the tick,
telemetry keys and the ``actuator_not_converging`` repair issue.

These drive the real write path with a mocked (never-echoing) actuator — the
mock services record calls but never move ``climate.trv``'s state, which IS
the silent "device never applies our commands" condition the watchdog exists
for. Escalation timing (count + minimum elapsed) is pure-tested in
``tests/test_write_convergence.py``; here the seeded-threshold tests pin the
emission position instead of faking 10 minutes of clock.

CI-only: needs a modern HA runtime (see conftest); the sandbox HA skips this dir.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.poise.const import (
    CONF_ACTUATOR,
    CONF_CATEGORY,
    CONF_CLIMATE_MODE,
    CONF_COMFORT_BASE,
    CONF_COMFORT_WEIGHT,
    CONF_CONTROLS_BOILER,
    CONF_NAME,
    CONF_OPERATIVE_INPUT,
    CONF_OPTIMAL_START,
    CONF_SETBACK_DELTA,
    CONF_TEMP_SENSOR,
    CONF_WINDOW_SENSOR,
    DOMAIN,
)
from custom_components.poise.safety.write_convergence import (
    CONV_FAIL_NUDGES,
    CONV_FAIL_WRITES,
)


def _room_data(**extra: Any) -> dict[str, Any]:
    return {
        CONF_NAME: "Test Room",
        CONF_TEMP_SENSOR: "sensor.room_temp",
        CONF_ACTUATOR: "climate.trv",
        CONF_WINDOW_SENSOR: "binary_sensor.window",
        CONF_CATEGORY: "II",
        CONF_COMFORT_BASE: 21.0,
        CONF_CLIMATE_MODE: "auto",
        CONF_COMFORT_WEIGHT: 70,
        CONF_SETBACK_DELTA: 3.0,
        CONF_OPTIMAL_START: True,
        CONF_OPERATIVE_INPUT: False,
        CONF_CONTROLS_BOILER: False,
        **extra,
    }


def _states(hass: HomeAssistant, *, room: float, sp: float, hvac: str = "heat") -> None:
    hass.states.async_set(
        "sensor.room_temp",
        str(room),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})
    hass.states.async_set(
        "climate.trv",
        hvac,
        {
            "hvac_modes": ["heat", "off", "auto"],
            "temperature": sp,
            "current_temperature": room,
            "target_temp_step": 0.5,
            "min_temp": 5.0,
            "max_temp": 30,
        },
    )


async def _setup(hass: HomeAssistant, *, data: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="climate.trv", data=data, title="Test Room"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _refresh(hass: HomeAssistant, coord: Any, n: int = 1) -> None:
    for _ in range(n):
        await coord.async_refresh()
        await hass.async_block_till_done()


_JITTER = iter(range(1, 100))


def _touch(hass: HomeAssistant, *, sp: float, hvac: str = "heat") -> None:
    """Refresh the actuator state WITHOUT moving its setpoint/mode.

    The watchdog only accepts evidence from a state that updated after our
    last command (poll-latency guard); a real silent-ignoring device keeps
    reporting (temperature jitter) with the OLD setpoint — modelled here by
    bumping ``current_temperature`` one hundredth per call.
    """
    hass.states.async_set(
        "climate.trv",
        hvac,
        {
            "hvac_modes": ["heat", "off", "auto"],
            "temperature": sp,
            "current_temperature": 19.0 + next(_JITTER) / 100.0,
            "target_temp_step": 0.5,
            "min_temp": 5.0,
            "max_temp": 30,
        },
    )


async def test_unconverged_reasserts_are_counted_and_exported(
    hass: HomeAssistant,
) -> None:
    """A never-echoing device (mocked service, state pinned at 20.0 while the
    commanded target is 21+) increments ``sp_diverged_writes`` per re-assert
    and the counter is exported in ``coordinator.data``."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    # Tick 1: no prior command -> no evidence, write dispatched. Ticks 2+3:
    # the device keeps REPORTING (touch = fresh state) but still shows 20.0
    # while last_written is the snapped target -> divergent re-asserts.
    await _refresh(hass, coord)
    for _ in range(2):
        _touch(hass, sp=20.0)
        await _refresh(hass, coord)
    assert coord.data["sp_diverged_writes"] >= 2
    assert coord.data["mode_diverged_nudges"] == 0


async def test_settled_device_resets_the_counter(hass: HomeAssistant) -> None:
    """The device finally reporting (about) the commanded value clears the
    episode — a re-quantise within one step must count as converged."""
    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    await _refresh(hass, coord)
    for _ in range(2):
        _touch(hass, sp=20.0)
        await _refresh(hass, coord)
    assert coord.data["sp_diverged_writes"] >= 2
    assert set_temp, "expected setpoint writes"
    written = set_temp[-1].data["temperature"]
    _states(hass, room=19.0, sp=written)  # device echoes the command
    await _refresh(hass, coord)
    assert coord.data["sp_diverged_writes"] == 0


async def test_identical_mode_renudges_are_counted(hass: HomeAssistant) -> None:
    """A device pinned in ``auto`` while Poise wants ``heat`` is re-nudged
    every tick; the identical re-nudges count as mode divergence."""
    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0, hvac="auto")
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    # Tick 1 commands heat (fresh, no evidence); ticks 2..4 re-nudge the
    # already-commanded mode against a device that keeps reporting (touch)
    # but never leaves ``auto``.
    await _refresh(hass, coord)
    for _ in range(3):
        _touch(hass, sp=20.0, hvac="auto")
        await _refresh(hass, coord)
    assert coord.data["mode_diverged_nudges"] >= 2


async def test_escalation_emits_repair_issue_and_recovery_clears_it(
    hass: HomeAssistant,
) -> None:
    """At threshold the tick emits ``actuator_not_converging``; a converged
    tick clears it (transition-only semantics). Thresholds are seeded — the
    count/elapsed arithmetic is pure-tested."""
    from homeassistant.helpers import issue_registry as ir

    set_temp = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    reg = ir.async_get(hass)
    issue_id = f"actuator_not_converging_{coord._entry_id}"

    wd = coord.runtime.safety.convergence
    wd.sp_diverged_writes = CONV_FAIL_WRITES
    wd.sp_diverged_since = coord.runtime.clock.monotonic() - 100_000.0
    await _refresh(hass, coord)
    assert reg.async_get_issue(DOMAIN, issue_id) is not None

    assert set_temp, "expected setpoint writes"
    _states(hass, room=19.0, sp=set_temp[-1].data["temperature"])
    await _refresh(hass, coord)
    assert reg.async_get_issue(DOMAIN, issue_id) is None


async def test_notify_convergence_is_a_translated_repair_issue(
    hass: HomeAssistant,
) -> None:
    """Mirror of the heating-failure P2-8 pin: the notify wrapper raises and
    clears the translated issue synchronously."""
    from homeassistant.helpers import issue_registry as ir

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    reg = ir.async_get(hass)
    issue_id = f"actuator_not_converging_{coord._entry_id}"

    coord._notify_convergence(True)
    assert reg.async_get_issue(DOMAIN, issue_id) is not None
    coord._notify_convergence(False)
    assert reg.async_get_issue(DOMAIN, issue_id) is None


def _requantise(hass: HomeAssistant, *, written: float, room: float) -> float:
    """Let the device take what its REAL 0.5 K grid can represent.

    The field case in one line: the entity declares ``target_temp_step: 0.1``
    (a ``customize`` override), the hardware moves in 0.5 K. Poise snaps to the
    declared grid, the device lands up to 0.25 K away, and the ADR-0012 write
    deadband (0.2 K) sees a difference forever.
    """
    settled = round(written * 2.0) / 2.0
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off", "auto"],
            "temperature": settled,
            "current_temperature": room,
            "target_temp_step": 0.1,  # the LIE this whole ADR is about
            "min_temp": 5.0,
            "max_temp": 30,
        },
    )
    return settled


async def test_a_requantising_device_is_not_rewritten_every_tick(
    hass: HomeAssistant,
) -> None:
    """ADR-0072 end to end: the loop terminates in the REAL tick.

    ``tests/test_write_economy.py`` proves the gates terminate, but it composes
    the pure functions by hand. What it cannot see is whether the shipped tick
    still REACHES them with the right arguments — observe computes the
    verdicts, the gate consumes them, the commit stamps the episode anchor. A
    refactor that disconnected any one of those three would leave every unit
    test green and put 1440 writes a day back on the wire. That is the gap this
    test exists for, and the reason it lives at the glue layer.

    Deliberately does NOT pin WHICH gate holds the write back — M2's
    idempotence proof needs a settled episode and 90 s of clock this harness
    does not advance, so here it is M4's rate limit that closes it. Both are
    pinned per-condition in the pure suite; the property at this layer is that
    the tick as assembled stops writing, and that the silence is counted.
    """
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    coord.set_override(21.3)  # deliberately off the device's real 0.5 K grid
    set_temp = async_mock_service(hass, "climate", "set_temperature")

    settled: float | None = None
    for _ in range(20):
        await _refresh(hass, coord)
        if set_temp:
            settled = _requantise(
                hass, written=float(set_temp[-1].data["temperature"]), room=19.0
            )

    # Non-vacuity: the device must actually have re-quantised away from the
    # commanded value, or this is a test of a well-behaved thermostat.
    assert set_temp, "expected at least the first write"
    written = float(set_temp[-1].data["temperature"])
    assert settled is not None and abs(written - settled) >= 0.2, (
        f"commanded {written}, device settled at {settled} — no re-quantisation, "
        "so this scenario does not reproduce the field case"
    )
    assert len(set_temp) <= 3, (
        f"{len(set_temp)} writes in 20 ticks — the re-assert loop is back in "
        "the assembled tick even though the pure gates terminate"
    )
    # ... and the silence is observable rather than merely absent (M2/M3 §7).
    assert coord.data["reasserts_suppressed"] > 0
    assert coord.data["declared_step"] == 0.1


async def test_notify_quantization_survives_a_device_that_declares_no_step(
    hass: HomeAssistant,
) -> None:
    """M3 (2026-09-12 plan): the CLEARING path is the hot path, and it must not
    raise.

    ``notify_quantization`` runs on every tick of every zone, and on a normal
    device both of its numbers are absent — no advice to give, and often no
    declared step to name. Formatting those placeholders blind raised a
    ``TypeError`` inside a health emission, which does not fail one issue: it
    aborts the whole tick and leaves the config entry in SETUP_RETRY. This test
    exists because that shipped once.

    The sibling ``test_notify_convergence_is_a_translated_repair_issue`` above
    pins the raise/clear pair; this one pins that the ABSENT case is rendered
    rather than formatted.
    """
    from homeassistant.helpers import issue_registry as ir

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    reg = ir.async_get(hass)
    issue_id = f"declared_step_mismatch_{coord._entry_id}"

    # Nothing to say, and nothing declared — the all-absent case.
    coord._notify_quantization(None, declared_step=None)
    assert reg.async_get_issue(DOMAIN, issue_id) is None
    # Raise it with both numbers, then clear it again while the declaration is
    # gone (an actuator that went unavailable between the two ticks).
    coord._notify_quantization(0.2, declared_step=0.1)
    assert reg.async_get_issue(DOMAIN, issue_id) is not None
    coord._notify_quantization(None, declared_step=None)
    assert reg.async_get_issue(DOMAIN, issue_id) is None


async def test_own_context_clamp_settle_counts_as_divergence(
    hass: HomeAssistant,
) -> None:
    """Own-context clamp coverage (adversarial-review Befund 2): a device
    that clamps our write to an unannounced internal limit and reports the
    settle under OUR service context is re-baselined by the adoption logic —
    the settle beyond one tolerance of the command must still count as
    divergence evidence instead of reading as convergence, and it must NOT
    be adopted as a manual hold."""
    from homeassistant.core import Context

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data

    await _refresh(hass, coord)  # first write dispatched
    for _ in range(3):
        ctx_id = coord.runtime.external.last_sp_ctx_id
        assert ctx_id is not None, "expected a stamped setpoint write context"
        # The device clamps to 16.0 and the push integration reports the
        # settle under OUR service context — the explicitly modelled class.
        hass.states.async_set(
            "climate.trv",
            "heat",
            {
                "hvac_modes": ["heat", "off", "auto"],
                "temperature": 16.0,
                "current_temperature": 19.0 + next(_JITTER) / 100.0,
                "target_temp_step": 0.5,
                "min_temp": 5.0,
                "max_temp": 30,
            },
            context=Context(id=ctx_id),
        )
        await _refresh(hass, coord)

    assert coord.data["sp_diverged_writes"] >= 2
    assert coord.data["override_active"] is False  # settle never adopted


async def test_clamped_self_regulating_actuator_escalates(
    hass: HomeAssistant,
) -> None:
    """Befund 2 (adversarial review): on a self-regulating actuator (split AC
    -> FAST_AIR -> ADR-0052 §4 throttle) the clamp episode must survive the
    throttled ticks in between. Judging against the adoption baseline let the
    counter oscillate 1->0->1 and never escalate — exactly on the device class
    where unannounced internal limits are most common."""
    from homeassistant.core import Context

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set(
        "sensor.room_temp",
        "19.0",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})
    # can_cool -> FAST_AIR -> self_regulating (regulation throttle active).
    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "cool", "off"],
            "temperature": 20.0,
            "current_temperature": 19.0,
            "target_temp_step": 0.5,
            "min_temp": 5.0,
            "max_temp": 30,
        },
    )
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    await _refresh(hass, coord)

    counts: list[int] = []
    for _ in range(6):
        ctx_id = coord.runtime.external.last_sp_ctx_id
        if ctx_id is not None:
            # The device clamps to its unannounced internal limit and reports
            # the settle under OUR context.
            hass.states.async_set(
                "climate.trv",
                "heat",
                {
                    "hvac_modes": ["heat", "cool", "off"],
                    "temperature": 16.0,
                    "current_temperature": 19.0 + next(_JITTER) / 100.0,
                    "target_temp_step": 0.5,
                    "min_temp": 5.0,
                    "max_temp": 30,
                },
                context=Context(id=ctx_id),
            )
        # Let the ADR-0052 §4 regulation period elapse so the next tick
        # re-asserts (a real self-regulating actuator is written once per
        # period, not per tick).
        if coord.runtime.external.last_sp_write_ts is not None:
            coord.runtime.external.last_sp_write_ts -= 400.0
        await _refresh(hass, coord)
        counts.append(coord.data["sp_diverged_writes"])

    # The episode must GROW across the throttled ticks, never reset to 0.
    assert max(counts) >= 2, counts
    assert counts[-1] >= 2, counts


async def test_late_echo_of_a_superseded_command_is_not_divergence(
    hass: HomeAssistant,
) -> None:
    """C.8f precision: the own-context ring is SHARED across setpoint/mode/fan
    writes, so a late echo of an ALREADY-SUPERSEDED command still reads as
    "our own change". Judging it against the newest command would count a
    healthy but sluggish device (sleepy Zigbee TRV, buffered MQTT) as
    divergent. Only the settle of the NEWEST setpoint command is evidence."""
    from homeassistant.core import Context

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    await _refresh(hass, coord)

    # An OLDER own write (any kind — the ring is shared with mode/fan writes)
    # whose echo is still in flight, while a newer setpoint command already
    # moved the baseline.
    ctx_old = Context()
    ext = coord.runtime.external
    ext.own_write_ctx_ids.append(ctx_old.id)
    ext.last_written_sp = 24.0

    hass.states.async_set(
        "climate.trv",
        "heat",
        {
            "hvac_modes": ["heat", "off", "auto"],
            "temperature": 18.0,  # the superseded command's late echo
            "current_temperature": 19.0 + next(_JITTER) / 100.0,
            "target_temp_step": 0.5,
            "min_temp": 5.0,
            "max_temp": 30,
        },
        context=ctx_old,
    )
    await _refresh(hass, coord)
    assert coord.data["sp_diverged_writes"] == 0


async def test_disabled_zone_clears_escalated_issue(hass: HomeAssistant) -> None:
    """Adversarial-review fix: the disabled/off-hold/rescue path must END the
    episode and CLEAR the issue — without regulation there is no convergence
    claim, and the transition-only issue would otherwise hold forever (also
    covers a store-re-adopted issue after a restart)."""
    from homeassistant.helpers import issue_registry as ir

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0)
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    reg = ir.async_get(hass)
    issue_id = f"actuator_not_converging_{coord._entry_id}"

    wd = coord.runtime.safety.convergence
    wd.sp_diverged_writes = CONV_FAIL_WRITES
    wd.sp_diverged_since = coord.runtime.clock.monotonic() - 100_000.0
    await _refresh(hass, coord)
    assert reg.async_get_issue(DOMAIN, issue_id) is not None

    coord.set_enabled(False)
    await _refresh(hass, coord)
    assert reg.async_get_issue(DOMAIN, issue_id) is None
    assert coord.runtime.safety.convergence.sp_diverged_writes == 0


async def test_mode_escalation_channel_also_emits(hass: HomeAssistant) -> None:
    """The mode channel alone (device never leaves ``auto``) reaches the same
    issue — seeded thresholds, real emission position."""
    from homeassistant.helpers import issue_registry as ir

    async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "set_hvac_mode")
    _states(hass, room=19.0, sp=20.0, hvac="auto")
    entry = await _setup(hass, data=_room_data())
    coord: Any = entry.runtime_data
    reg = ir.async_get(hass)

    wd = coord.runtime.safety.convergence
    wd.mode_diverged_nudges = CONV_FAIL_NUDGES
    wd.mode_diverged_since = coord.runtime.clock.monotonic() - 100_000.0
    await _refresh(hass, coord)
    issue_id = f"actuator_not_converging_{coord._entry_id}"
    assert reg.async_get_issue(DOMAIN, issue_id) is not None
