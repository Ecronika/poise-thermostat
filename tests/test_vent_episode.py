"""ADR-0074 episode state machine — phases, exemptions, and the inversion."""

from __future__ import annotations

from custom_components.poise.comfort.vent_episode import (
    IDLE_ALL_GOOD,
    IDLE_COOLDOWN,
    IDLE_FABRIC_HEATED,
    IDLE_NO_DATA,
    IDLE_OUTSIDE_NOT_DRIER,
    PHASE_COOLDOWN,
    PHASE_IDLE,
    PHASE_REQUESTED,
    PHASE_STOP_REQUESTED,
    PHASE_VENTILATING,
    REASON_AIRING_DONE,
    WINDOW_CLOSED,
    WINDOW_LIKELY_OPEN,
    WINDOW_OPEN,
    WINDOW_SOURCE_BYPASS,
    WINDOW_SOURCE_CONTACT,
    WINDOW_SOURCE_SLOPE,
    WINDOW_UNKNOWN,
    EpisodeConfig,
    EpisodeResult,
    EpisodeState,
    episode_step,
    idle_cause,
    oracle_flags,
    oracle_window_open,
)
from custom_components.poise.comfort.ventilation import ventilation_advise

_CFG = EpisodeConfig()


def _step(state: EpisodeState, **kw: object) -> EpisodeResult:
    base: dict[str, object] = {
        "action": "idle",
        "reason": "no_gain",
        "level": "ok",
        "window": WINDOW_CLOSED,
        "dt_min": 1.0,
    }
    base.update(kw)
    return episode_step(state, **base)  # type: ignore[arg-type]


# --- the defect class this module exists for --------------------------------


def test_the_window_contact_can_never_invert_the_advice() -> None:
    """ADR-0066 N6/N9 in one sentence: only ``ventilating`` can end.

    The rule table may well produce ``close/mold_guard`` for a tick whose
    physical conditions were already true with the window shut. Before the
    phase existed, that answer reached the user the moment the contact moved.
    """
    s = _step(
        EpisodeState(), action="open", reason="moisture_protect", level="warn"
    ).state
    assert s.phase == PHASE_REQUESTED
    r = _step(
        s, action="open", reason="moisture_protect", level="warn", window=WINDOW_OPEN
    )
    assert (r.state.phase, r.action) == (PHASE_VENTILATING, "open")
    again = _step(
        r.state,
        action="open",
        reason="moisture_protect",
        level="warn",
        window=WINDOW_OPEN,
    )
    assert (again.action, again.reason) == ("open", "moisture_protect")


def test_a_protection_abort_still_ends_a_running_episode() -> None:
    """The stand-down is not a blanket immunity — the fabric still wins."""
    s = EpisodeState(
        phase=PHASE_VENTILATING, reason="moisture_out", owner="moisture_out"
    )
    r = _step(s, action="close", reason="mold_guard", level="warn", window=WINDOW_OPEN)
    assert (r.state.phase, r.action, r.reason) == (
        PHASE_STOP_REQUESTED,
        "close",
        "mold_guard",
    )
    assert r.state.emergency
    assert r.prompt


# --- the ordinary life cycle -------------------------------------------------


def test_full_cycle_request_ventilate_stop_cooldown() -> None:
    st = EpisodeState()
    r = _step(st, action="open", reason="moisture_out", level="ok")
    assert (r.state.phase, r.action, r.prompt) == (PHASE_REQUESTED, "open", True)
    r = _step(
        r.state, action="open", reason="moisture_out", level="ok", window=WINDOW_OPEN
    )
    assert r.state.phase == PHASE_VENTILATING
    r = _step(
        r.state, action="close", reason="target_reached", level="ok", window=WINDOW_OPEN
    )
    assert (r.state.phase, r.action, r.prompt) == (PHASE_STOP_REQUESTED, "close", True)
    assert not r.state.emergency
    r = _step(
        r.state, action="idle", reason="no_gain", level="ok", window=WINDOW_CLOSED
    )
    assert (r.state.phase, r.action, r.idle_cause) == (
        PHASE_COOLDOWN,
        "idle",
        IDLE_COOLDOWN,
    )
    assert r.state.cooldown_for_min == _CFG.cooldown_min


def test_an_already_open_window_is_not_asked_to_open() -> None:
    r = _step(
        EpisodeState(), action="open", reason="co2", level="ok", window=WINDOW_OPEN
    )
    assert (r.state.phase, r.prompt) == (PHASE_VENTILATING, False)


def test_a_foreign_open_window_can_still_be_asked_to_close() -> None:
    r = _step(
        EpisodeState(),
        action="close",
        reason="thermal_floor",
        level="warn",
        window=WINDOW_OPEN,
    )
    assert (r.state.phase, r.action, r.state.emergency) == (
        PHASE_STOP_REQUESTED,
        "close",
        True,
    )


def test_a_withdrawn_request_costs_no_cooldown() -> None:
    s = EpisodeState(phase=PHASE_REQUESTED, reason="co2", owner="co2", phase_min=3.0)
    r = _step(s, action="idle", reason="no_gain", level="ok")
    assert r.state.phase == PHASE_IDLE


def test_the_reason_may_change_inside_one_episode() -> None:
    s = EpisodeState(
        phase=PHASE_VENTILATING, reason="moisture_out", owner="moisture_out"
    )
    r = _step(s, action="open", reason="co2", level="ok", window=WINDOW_OPEN)
    assert (r.state.phase, r.reason) == (PHASE_VENTILATING, "co2")


def test_manual_close_ends_the_episode_early() -> None:
    s = EpisodeState(
        phase=PHASE_VENTILATING, reason="moisture_out", owner="moisture_out"
    )
    r = _step(s, action="open", reason="moisture_out", level="ok", window=WINDOW_CLOSED)
    assert r.state.phase == PHASE_COOLDOWN
    assert r.state.cooldown_for_min == _CFG.cooldown_manual_min
    assert r.state.cooldown_scope == ""  # an abort quiets everything


# --- v2a: a new opening reason cancels an ordinary stop ----------------------


def test_a_new_open_reason_cancels_an_ordinary_stop_request() -> None:
    """Review 2026-09-17: ``close -> new CO2 -> still close`` was a dead end.

    "Reasons may change" has to hold across the stop request too, otherwise the
    machine asks to close a window it would ask to reopen one tick later.
    """
    s = EpisodeState(
        phase=PHASE_STOP_REQUESTED, reason="target_reached", owner="moisture_out"
    )
    r = _step(s, action="open", reason="co2", level="ok", window=WINDOW_OPEN)
    assert (r.state.phase, r.action, r.reason) == (PHASE_VENTILATING, "open", "co2")


def test_an_emergency_stop_is_never_overruled_by_a_new_open_reason() -> None:
    s = EpisodeState(
        phase=PHASE_STOP_REQUESTED, reason="mold_guard", owner="", emergency=True
    )
    r = _step(s, action="open", reason="co2", level="ok", window=WINDOW_OPEN)
    assert (r.state.phase, r.action) == (PHASE_STOP_REQUESTED, "close")


# --- v2a: no state without an exit ------------------------------------------


def test_an_unobservable_stop_times_out_into_the_protection_cooldown() -> None:
    """The contact-less exit — and it leaves through the quiet time.

    Releasing straight into watching would recreate the abort/reopen cycle the
    emergency cooldown exists to prevent: we never learned whether the window
    was closed at all.
    """
    s = EpisodeState(phase=PHASE_STOP_REQUESTED, reason="thermal_floor", emergency=True)
    r = _step(
        s,
        action="idle",
        reason="no_gain",
        level="ok",
        window=WINDOW_UNKNOWN,
        dt_min=2.0,
    )
    assert r.state.phase == PHASE_STOP_REQUESTED  # dwell, not one tick
    while r.state.phase == PHASE_STOP_REQUESTED:
        r = _step(
            r.state,
            action="idle",
            reason="no_gain",
            level="ok",
            window=WINDOW_UNKNOWN,
            dt_min=2.0,
        )
    assert r.state.phase == PHASE_COOLDOWN
    assert (r.state.cooldown_for_min, r.state.cooldown_scope) == (
        _CFG.cooldown_emergency_min,
        "",
    )
    again = _step(
        r.state, action="open", reason="co2", level="ok", window=WINDOW_UNKNOWN
    )
    assert again.state.phase == PHASE_COOLDOWN


def test_a_known_open_window_keeps_the_close_standing() -> None:
    """Knowledge beats the timer: a contact that says OPEN never expires.

    The timeout is for the case Poise cannot observe, not for the case it can.
    """
    s = EpisodeState(
        phase=PHASE_STOP_REQUESTED, reason="target_reached", owner="moisture_out"
    )
    r = _step(
        s, action="idle", reason="no_gain", level="ok", window=WINDOW_OPEN, dt_min=5.0
    )
    for _ in range(30):
        r = _step(
            r.state,
            action="idle",
            reason="no_gain",
            level="ok",
            window=WINDOW_OPEN,
            dt_min=5.0,
        )
        assert r.action == "close"
    assert r.state.phase == PHASE_STOP_REQUESTED
    done = _step(
        r.state, action="idle", reason="no_gain", level="ok", window=WINDOW_CLOSED
    )
    assert done.state.phase == PHASE_COOLDOWN


def test_a_current_close_beats_a_request_the_user_is_just_following() -> None:
    """The critical v2a finding: ``REQUESTED`` read the contact before the rat.

    CO2 asks for a window; while the user opens it the thermal floor binds.
    Acting on a minute-old request must never publish ``open`` over a
    protection close that is true right now.
    """
    req = _step(EpisodeState(), action="open", reason="co2", level="ok").state
    assert req.phase == PHASE_REQUESTED
    r = _step(
        req, action="close", reason="thermal_floor", level="warn", window=WINDOW_OPEN
    )
    assert (r.state.phase, r.action, r.reason) == (
        PHASE_STOP_REQUESTED,
        "close",
        "thermal_floor",
    )
    assert r.state.emergency and r.prompt


def test_a_request_may_only_end_silently_when_the_window_is_known_shut() -> None:
    """The v2a blocker, and the test that used to pin the wrong answer.

    A request whose cause disappears may vanish without a word only when the
    contact PROVES nobody acted on it. Open or unknown, the user may well have
    followed the advice — and in a contact-less zone we can never prove
    otherwise, which is the case this whole module was built for.
    """
    req = _step(
        EpisodeState(), action="open", reason="moisture_protect", level="warn"
    ).state
    shut = _step(req, action="idle", reason="no_gain", level="ok", window=WINDOW_CLOSED)
    assert (shut.state.phase, shut.action) == (PHASE_IDLE, "idle")

    for w in (WINDOW_OPEN, WINDOW_LIKELY_OPEN, WINDOW_UNKNOWN):
        r = _step(req, action="idle", reason="no_gain", level="ok", window=w)
        assert (r.state.phase, r.action, r.reason) == (
            PHASE_STOP_REQUESTED,
            "close",
            REASON_AIRING_DONE,
        ), f"stilles Ende bei {w}"
        assert r.prompt and not r.state.emergency


def test_the_bathroom_without_a_contact_is_told_to_stop() -> None:
    """The field shape: advice followed, slope blind, humidity spent.

    Before this, the episode simply evaporated and left a window open with no
    word from Poise.
    """
    r = _step(EpisodeState(), action="open", reason="moisture_protect", level="warn")
    assert r.state.phase == PHASE_REQUESTED
    for _ in range(3):
        r = _step(
            r.state,
            action="open",
            reason="moisture_protect",
            level="warn",
            window=WINDOW_UNKNOWN,
        )
        assert r.state.phase == PHASE_REQUESTED  # the table cannot see the open window
    r = _step(
        r.state, action="idle", reason="no_gain", level="ok", window=WINDOW_UNKNOWN
    )
    assert (r.action, r.reason) == ("close", REASON_AIRING_DONE)


def test_the_episode_token_makes_no_physical_claim() -> None:
    """``airing_done`` is the FSM's own word, never ``target_reached``.

    The cause may have vanished through lost data or a change of occupancy;
    claiming a goal was reached would be a statement about physics that this
    module is not entitled to make.
    """
    req = _step(EpisodeState(), action="open", reason="co2", level="ok").state
    r = _step(req, action="idle", reason="no_data", level="ok", window=WINDOW_UNKNOWN)
    assert r.reason == REASON_AIRING_DONE != "target_reached"


def test_a_cooldown_silences_the_doorbell_not_a_standing_close() -> None:
    """Same rule as everywhere else: quiet time is anti-spam, not censorship."""
    cd = EpisodeState(phase=PHASE_COOLDOWN, phase_min=1.0, cooldown_for_min=45.0)
    r = _step(cd, action="close", reason="too_dry", level="warn", window=WINDOW_OPEN)
    assert (r.state.phase, r.action, r.prompt) == (PHASE_COOLDOWN, "close", False)
    # ... while a comfort OPEN stays gagged, which is what the cooldown is for
    q = _step(cd, action="open", reason="co2", level="ok")
    assert (q.state.phase, q.action) == (PHASE_COOLDOWN, "idle")


def test_a_flapping_all_clear_does_not_release_a_standing_stop() -> None:
    s = EpisodeState(phase=PHASE_STOP_REQUESTED, reason="mold_guard", emergency=True)
    r = _step(
        s,
        action="idle",
        reason="no_gain",
        level="ok",
        window=WINDOW_UNKNOWN,
        dt_min=4.0,
    )
    r = _step(
        r.state,
        action="close",
        reason="mold_guard",
        level="warn",
        window=WINDOW_UNKNOWN,
    )
    assert r.state.unknown_dwell_min == 0.0
    assert r.state.phase == PHASE_STOP_REQUESTED


def test_open_mold_risk_does_not_prove_an_all_clear() -> None:
    """``mold_risk`` wins ABOVE the close rules, so it proves nothing.

    Naming the ambiguity here is the honest half of the single-winner
    interface: the evaluation layer of ADR-0074 is what removes it.
    """
    s = EpisodeState(phase=PHASE_STOP_REQUESTED, reason="thermal_floor", emergency=True)
    r = _step(
        s,
        action="open",
        reason="mold_risk",
        level="alert",
        window=WINDOW_UNKNOWN,
        dt_min=9.0,
    )
    assert (r.state.phase, r.state.unknown_dwell_min) == (PHASE_STOP_REQUESTED, 0.0)


# --- v2a: discourage survives -------------------------------------------------


def test_discourage_is_published_verbatim_in_every_quiet_phase() -> None:
    """ADR-0066 rule 2's "better not open" is a user state, not an idle."""
    r = _step(EpisodeState(), action="discourage", reason="too_dry", level="warn")
    assert (r.action, r.reason, r.level) == ("discourage", "too_dry", "warn")
    withdrawn = _step(
        EpisodeState(phase=PHASE_REQUESTED, reason="co2", owner="co2"),
        action="discourage",
        reason="too_dry",
        level="warn",
    )
    assert (withdrawn.state.phase, withdrawn.action) == (PHASE_IDLE, "discourage")
    cd = _step(
        EpisodeState(phase=PHASE_COOLDOWN, cooldown_for_min=30.0),
        action="discourage",
        reason="too_dry",
        level="warn",
    )
    assert cd.action == "discourage"


def test_discourage_survives_the_tick_an_episode_ends_on() -> None:
    """Found by the state-space soak, not by a hand-written case.

    Every phase change reported a plain ``idle``, so a window closing while the
    room was already too dry swallowed the "better not open" hint at exactly
    the moment it became actionable.
    """
    v = EpisodeState(
        phase=PHASE_VENTILATING, reason="moisture_out", owner="moisture_out"
    )
    ended = _step(
        v, action="discourage", reason="too_dry", level="warn", window=WINDOW_CLOSED
    )
    assert (ended.state.phase, ended.action, ended.reason) == (
        PHASE_COOLDOWN,
        "discourage",
        "too_dry",
    )
    stopped = _step(
        EpisodeState(phase=PHASE_STOP_REQUESTED, reason="target_reached", owner="co2"),
        action="discourage",
        reason="too_dry",
        level="warn",
        window=WINDOW_CLOSED,
    )
    assert stopped.action == "discourage"


def test_a_quiet_world_always_returns_the_machine_to_idle() -> None:
    """No phase without a finite or event-driven exit (soak invariant 1)."""
    for seed in (
        EpisodeState(phase=PHASE_REQUESTED, reason="mold_risk", owner="mold_risk"),
        EpisodeState(phase=PHASE_VENTILATING, reason="co2", owner="co2"),
        EpisodeState(phase=PHASE_STOP_REQUESTED, reason="mold_guard", emergency=True),
        EpisodeState(phase=PHASE_COOLDOWN, cooldown_for_min=45.0),
    ):
        cur = seed
        for _ in range(400):
            cur = _step(
                cur, action="idle", reason="no_gain", level="ok", window=WINDOW_UNKNOWN
            ).state
            if cur.phase == PHASE_IDLE:
                break
        assert cur.phase == PHASE_IDLE, f"kein Ausgang aus {seed.phase}"


def test_too_dry_is_a_warning_not_an_emergency() -> None:
    """7 g/m3 / 35 % RH is the ordinary dryness line, not a hazard."""
    s = EpisodeState(phase=PHASE_VENTILATING, reason="co2", owner="co2")
    r = _step(s, action="close", reason="too_dry", level="warn", window=WINDOW_OPEN)
    assert (r.state.phase, r.state.emergency) == (PHASE_STOP_REQUESTED, False)


# --- v2a: prompt and action are independent ----------------------------------


def test_a_spent_prompt_budget_silences_the_doorbell_not_the_truth() -> None:
    """The card must keep saying "close" while the window is still open."""
    r = _step(
        EpisodeState(),
        action="close",
        reason="target_reached",
        level="ok",
        window=WINDOW_OPEN,
    )
    seen = 0
    for _ in range(40):
        r = _step(
            r.state,
            action="close",
            reason="target_reached",
            level="ok",
            window=WINDOW_OPEN,
            dt_min=2.0,
        )
        seen += int(r.prompt)
        assert r.action == "close", "the truth must not follow the doorbell"
    assert (
        seen == _CFG.max_prompts_per_phase - 1
    )  # the opening ask is the first of them


def test_prompt_budget_counts_the_opening_ask() -> None:
    def prompts(reason: str) -> int:
        r = _step(EpisodeState(), action="open", reason=reason, level="ok")
        n = int(r.prompt)
        for _ in range(200):
            r = _step(r.state, action="open", reason=reason, level="ok", dt_min=1.0)
            n += int(r.prompt)
            if r.state.phase != PHASE_REQUESTED:
                break
        return n

    assert prompts("co2") == _CFG.max_prompts_per_phase
    assert prompts("mold_risk") == _CFG.max_prompts_per_phase_protection


# --- the protection exemptions ----------------------------------------------


def test_a_comfort_request_expires_but_a_protection_request_does_not() -> None:
    comfort = EpisodeState(
        phase=PHASE_REQUESTED, reason="co2", owner="co2", phase_min=_CFG.request_ttl_min
    )
    r = _step(comfort, action="open", reason="co2", level="ok")
    assert r.state.phase == PHASE_COOLDOWN
    assert r.state.cooldown_for_min == _CFG.cooldown_expired_min

    guard = EpisodeState(
        phase=PHASE_REQUESTED, reason="mold_risk", owner="mold_risk", phase_min=600.0
    )
    r = _step(guard, action="open", reason="mold_risk", level="alert")
    assert (r.state.phase, r.action) == (PHASE_REQUESTED, "open")


def test_cooldown_gags_comfort_but_never_building_protection() -> None:
    cd = EpisodeState(phase=PHASE_COOLDOWN, phase_min=1.0, cooldown_for_min=45.0)
    quiet = _step(cd, action="open", reason="co2", level="ok")
    assert (quiet.state.phase, quiet.action) == (PHASE_COOLDOWN, "idle")
    loud = _step(cd, action="open", reason="moisture_protect", level="warn")
    assert (loud.state.phase, loud.action) == (PHASE_REQUESTED, "open")
    abort = _step(
        cd, action="close", reason="mold_guard", level="warn", window=WINDOW_OPEN
    )
    assert (abort.state.phase, abort.action) == (PHASE_STOP_REQUESTED, "close")


def test_a_reached_goal_only_rests_its_own_reason() -> None:
    """Anti-chatter for the reason that just finished — not a blanket gag."""
    s = EpisodeState(
        phase=PHASE_STOP_REQUESTED, reason="target_reached", owner="moisture_out"
    )
    r = _step(s, action="idle", reason="no_gain", level="ok", window=WINDOW_CLOSED)
    assert (r.state.phase, r.state.cooldown_scope) == (PHASE_COOLDOWN, "moisture_out")
    same = _step(r.state, action="open", reason="moisture_out", level="ok")
    assert same.state.phase == PHASE_COOLDOWN  # its own reason waits
    other = _step(r.state, action="open", reason="co2", level="ok")
    assert (other.state.phase, other.reason) == (PHASE_REQUESTED, "co2")


def test_an_aborted_episode_earns_the_blanket_quiet_time() -> None:
    s = EpisodeState(
        phase=PHASE_STOP_REQUESTED,
        reason="mold_guard",
        owner="moisture_out",
        emergency=True,
    )
    r = _step(
        s, action="close", reason="mold_guard", level="warn", window=WINDOW_CLOSED
    )
    assert (r.state.cooldown_for_min, r.state.cooldown_scope) == (
        _CFG.cooldown_emergency_min,
        "",
    )


def test_cooldown_expires_on_its_own() -> None:
    cd = EpisodeState(phase=PHASE_COOLDOWN, phase_min=9.5, cooldown_for_min=10.0)
    r = _step(cd, action="idle", reason="no_gain", level="ok")
    assert r.state.phase == PHASE_IDLE


# --- window signal ------------------------------------------------------------


def test_inferred_open_is_marked_but_acts_as_open() -> None:
    r = _step(
        EpisodeState(),
        action="open",
        reason="moisture_out",
        level="ok",
        window=WINDOW_LIKELY_OPEN,
    )
    assert (r.state.phase, r.state.entry_inferred) == (PHASE_VENTILATING, True)
    assert oracle_window_open(WINDOW_LIKELY_OPEN)
    assert not oracle_window_open(WINDOW_UNKNOWN)


def test_unknown_window_neither_opens_nor_closes_an_episode() -> None:
    s = EpisodeState(phase=PHASE_REQUESTED, reason="moisture_out", owner="moisture_out")
    r = _step(
        s, action="open", reason="moisture_out", level="ok", window=WINDOW_UNKNOWN
    )
    assert r.state.phase == PHASE_REQUESTED
    v = EpisodeState(
        phase=PHASE_VENTILATING, reason="moisture_out", owner="moisture_out"
    )
    r2 = _step(
        v, action="open", reason="moisture_out", level="ok", window=WINDOW_UNKNOWN
    )
    assert r2.state.phase == PHASE_VENTILATING


# --- the four silences --------------------------------------------------------


def test_idle_cause_separates_the_four_silences() -> None:
    assert (
        idle_cause(
            reason="no_data",
            cool_edge_protected=False,
            room_over_safe=False,
            outside_drier=False,
        )
        == IDLE_NO_DATA
    )
    assert (
        idle_cause(
            reason="no_gain",
            cool_edge_protected=True,
            room_over_safe=True,
            outside_drier=True,
        )
        == IDLE_FABRIC_HEATED
    )
    assert (
        idle_cause(
            reason="no_gain",
            cool_edge_protected=False,
            room_over_safe=True,
            outside_drier=False,
        )
        == IDLE_OUTSIDE_NOT_DRIER
    )
    assert (
        idle_cause(
            reason="no_gain",
            cool_edge_protected=False,
            room_over_safe=False,
            outside_drier=True,
        )
        == IDLE_ALL_GOOD
    )


def test_idle_result_carries_the_cause() -> None:
    r = episode_step(
        EpisodeState(),
        action="idle",
        reason="no_gain",
        level="ok",
        window=WINDOW_CLOSED,
        dt_min=1.0,
        cool_edge_protected=True,
        room_over_safe=True,
    )
    assert (r.action, r.idle_cause) == ("idle", IDLE_FABRIC_HEATED)


# --- the bridge back into the rule table --------------------------------------


def test_oracle_flags_come_from_the_phase_not_from_the_last_token() -> None:
    running = EpisodeState(
        phase=PHASE_VENTILATING, reason="target_reached", owner="moisture_protect"
    )
    f = oracle_flags(running)
    assert f["prev_advice_active"] and f["prev_moisture_protect"]
    assert not f["prev_moisture_airing"]
    done = EpisodeState(phase=PHASE_COOLDOWN, owner="moisture_protect")
    assert not any(oracle_flags(done).values())


def test_dt_is_capped_so_a_restart_gap_cannot_age_the_machine() -> None:
    s = EpisodeState(phase=PHASE_REQUESTED, reason="co2", owner="co2")
    r = _step(s, action="open", reason="co2", level="ok", dt_min=10_000.0)
    assert r.state.phase_min == _CFG.max_tick_min


# --- end to end against the real rule table -----------------------------------

_BEDROOM: dict[str, object] = {
    "w_in_gm3": 12.0,
    "w_out_gm3": 8.3,
    "rh_pct": 66.0,
    "room_c": 22.0,
    "cool_edge_c": 22.0,
    "t_out_c": 12.0,
    "surface_rh_pct": 79.0,
    "rh_max_safe_pct": 62.8,
    "surface_rh_mean_pct": 67.26,
    "surface_needs_warmer": True,
    "cool_edge_protected": False,
    "occupied": True,
    "cool_capable": False,
    "fan_capable": False,
    "mold_floor_binding": False,
    "mold_capped": False,
    "room_at_thermal_floor": False,
    "co2_ppm": None,
}


def _drive(state: EpisodeState, window: str) -> EpisodeResult:
    kw = dict(_BEDROOM)
    kw["window_open"] = oracle_window_open(window)
    kw.update(oracle_flags(state))
    a = ventilation_advise(**kw)  # type: ignore[arg-type]
    return episode_step(
        state,
        action=a.action,
        reason=a.reason,
        level=a.level,
        window=window,
        dt_min=1.0,
        cool_edge_protected=bool(_BEDROOM["cool_edge_protected"]),
        room_over_safe=True,
        outside_drier=True,
    )


def test_live_bedroom_2026_09_14_runs_through_without_inverting() -> None:
    """The field case, driven through both layers as the seam will drive them."""
    r = _drive(EpisodeState(), WINDOW_CLOSED)
    assert (r.state.phase, r.action, r.reason) == (
        PHASE_REQUESTED,
        "open",
        "moisture_protect",
    )
    r = _drive(r.state, WINDOW_OPEN)
    assert (r.state.phase, r.action) == (PHASE_VENTILATING, "open")
    for _ in range(5):
        r = _drive(r.state, WINDOW_OPEN)
        assert r.action == "open", f"episode inverted: {r.action}/{r.reason}"
    r = _drive(r.state, WINDOW_CLOSED)
    assert r.state.phase == PHASE_COOLDOWN


# --- Rev. 5: the second external review, 2026-09-17 --------------------------


def test_an_airing_is_never_claimed_without_an_observed_opening() -> None:
    """R2-B1: ``ventilating`` used to be reachable on a never-seen window.

    A stop request that nobody confirmed, then a fresh reason, and the machine
    declared an airing under way on a contact-less zone. Evidence of an actual
    opening is now a precondition; without it the user is asked again.
    """
    r = _step(
        EpisodeState(), action="open", reason="co2", level="ok", window=WINDOW_UNKNOWN
    )
    r = _step(
        r.state, action="idle", reason="no_gain", level="ok", window=WINDOW_UNKNOWN
    )
    assert r.state.phase == PHASE_STOP_REQUESTED
    r = _step(r.state, action="open", reason="co2", level="ok", window=WINDOW_UNKNOWN)
    assert (r.state.phase, r.state.opened_seen) == (PHASE_REQUESTED, False)
    # ... and with an observation it resumes the airing as before
    seen = _step(r.state, action="open", reason="co2", level="ok", window=WINDOW_OPEN)
    assert (seen.state.phase, seen.state.opened_seen) == (PHASE_VENTILATING, True)


def test_a_request_expires_only_against_a_window_known_to_be_shut() -> None:
    """R2-P1: the TTL used to fire blind, and Rev. 5 then advised an END.

    Three answers again. A shut contact proves the request was not acted on,
    so it may expire. Where the contact cannot say, the request STANDS: its
    reason still holds, so telling the user to stop would be wrong, and
    dropping the request would lose the ending they are owed once the reason
    does go away. What runs out there is the prompt budget, not the request.
    """
    base = EpisodeState(
        phase=PHASE_REQUESTED,
        reason="co2",
        owner="co2",
        episode_id=1,
        phase_min=_CFG.request_ttl_min,
        prompts=2,
        episode_prompts=2,
    )
    shut = _step(base, action="open", reason="co2", level="ok", window=WINDOW_CLOSED)
    assert shut.state.phase == PHASE_COOLDOWN

    blind = _step(base, action="open", reason="co2", level="ok", window=WINDOW_UNKNOWN)
    assert (blind.state.phase, blind.action, blind.reason) == (
        PHASE_REQUESTED,
        "open",
        "co2",
    )
    assert not blind.prompt, "die Klingel ist still, die Anfrage steht"
    # ... and the ending still arrives when the reason finally goes
    done = _step(
        blind.state, action="idle", reason="no_gain", level="ok", window=WINDOW_UNKNOWN
    )
    assert (done.state.phase, done.reason) == (PHASE_STOP_REQUESTED, REASON_AIRING_DONE)

    acted = _step(base, action="open", reason="co2", level="ok", window=WINDOW_OPEN)
    assert acted.state.phase == PHASE_VENTILATING


def test_unknown_is_not_an_inference_and_does_not_stick() -> None:
    """R2-P2: ``entry_inferred`` claimed a guess where there was none, and it
    was never cleared — an old ``likely_open`` still labelled the resting
    state. The field describes the evidence the PHASE was entered on;
    ``window_seen`` carries the current observation.
    """
    standing = EpisodeState(
        phase=PHASE_REQUESTED, reason="co2", owner="co2", episode_id=1
    )
    blind = _step(
        standing, action="idle", reason="no_gain", level="ok", window=WINDOW_UNKNOWN
    )
    assert not blind.state.entry_inferred

    r = _step(
        EpisodeState(),
        action="open",
        reason="co2",
        level="ok",
        window=WINDOW_LIKELY_OPEN,
    )
    assert r.state.entry_inferred
    r = _step(r.state, action="open", reason="co2", level="ok", window=WINDOW_CLOSED)
    assert not r.state.entry_inferred
    r = _step(
        r.state,
        action="idle",
        reason="no_gain",
        level="ok",
        window=WINDOW_CLOSED,
        dt_min=99.0,
    )
    assert (r.state.phase, r.state.entry_inferred) == (PHASE_IDLE, False)


def test_a_new_reason_out_of_a_stop_needs_evidence_too() -> None:
    """R2-P3: ``requested`` means asked, ``ventilating`` means seen."""
    stopped = EpisodeState(
        phase=PHASE_STOP_REQUESTED, reason=REASON_AIRING_DONE, owner="co2", episode_id=1
    )
    blind = _step(
        stopped, action="open", reason="moisture_out", level="ok", window=WINDOW_UNKNOWN
    )
    assert blind.state.phase == PHASE_REQUESTED
    seen = _step(
        stopped, action="open", reason="moisture_out", level="ok", window=WINDOW_OPEN
    )
    assert seen.state.phase == PHASE_VENTILATING


def test_a_flickering_reason_cannot_ring_forever() -> None:
    """R2-B3: ten prompts in twenty-one ticks, measured.

    The per-phase quota is defeated by re-entry — the phase starts over and
    rings again. The ceiling belongs to the episode.
    """
    st = EpisodeState()
    rung = 0
    for i in range(21):
        action, reason = ("open", "co2") if i % 2 == 0 else ("close", "target_reached")
        r = _step(st, action=action, reason=reason, level="ok", window=WINDOW_OPEN)
        rung += int(r.prompt)
        st = r.state
    assert rung <= _CFG.max_prompts_per_episode
    # a genuinely new episode gets its full budget back
    fresh = _step(
        EpisodeState(
            phase=PHASE_COOLDOWN,
            phase_min=99.0,
            cooldown_for_min=10.0,
            episode_prompts=9,
        ),
        action="open",
        reason="co2",
        level="ok",
    )
    assert (fresh.state.phase, fresh.prompt) == (PHASE_REQUESTED, True)


def test_an_escalation_announces_itself_on_the_spot() -> None:
    """R2-B4: waiting for the reminder clock delayed a fabric warning."""
    for phase_min in (2.0, 8.0, 20.0):
        s = EpisodeState(
            phase=PHASE_STOP_REQUESTED,
            reason="target_reached",
            owner="moisture_out",
            prompts=2,
            episode_prompts=2,
            phase_min=phase_min,
            level="ok",
        )
        r = _step(
            s, action="close", reason="thermal_floor", level="warn", window=WINDOW_OPEN
        )
        assert r.prompt, f"stumme Eskalation bei phase_min={phase_min}"
        assert (r.reason, r.level) == ("thermal_floor", "warn")


def test_a_latched_stop_keeps_its_own_severity() -> None:
    """R2-B5: ``close/thermal_floor`` was published at ``level="ok"``.

    The level arrived from whatever the resolver happened to say this tick.
    Action, reason and severity now travel together.
    """
    s = EpisodeState(
        phase=PHASE_STOP_REQUESTED, reason="thermal_floor", level="warn", emergency=True
    )
    r = _step(s, action="open", reason="co2", level="ok", window=WINDOW_OPEN)
    assert (r.action, r.reason, r.level) == ("close", "thermal_floor", "warn")


def test_an_unconfirmed_ending_never_rests_a_single_reason() -> None:
    """R2-B6: code and §5b disagreed about which cooldown this earns."""
    for emergency, expected in (
        (False, _CFG.cooldown_expired_min),
        (True, _CFG.cooldown_emergency_min),
    ):
        s = EpisodeState(
            phase=PHASE_STOP_REQUESTED,
            reason=REASON_AIRING_DONE,
            owner="co2",
            emergency=emergency,
        )
        r = _step(
            s,
            action="idle",
            reason="no_gain",
            level="ok",
            window=WINDOW_UNKNOWN,
            dt_min=6.0,
        )
        assert (r.state.cooldown_for_min, r.state.cooldown_scope) == (expected, "")


def test_only_a_contact_proves_a_window_was_closed() -> None:
    """ADR-0041: the slope estimator RESETS after its maximum duration and a
    bypass FORCES the signal shut. Neither is an observed closing, and taking
    them for one would end an airing that is still running.
    """
    running = EpisodeState(
        phase=PHASE_VENTILATING, reason="co2", owner="co2", opened_seen=True
    )
    proof = _step(
        running,
        action="open",
        reason="co2",
        level="ok",
        window=WINDOW_CLOSED,
        window_source=WINDOW_SOURCE_CONTACT,
    )
    assert (proof.state.phase, proof.window_seen) == (PHASE_COOLDOWN, WINDOW_CLOSED)
    for source in (WINDOW_SOURCE_BYPASS, WINDOW_SOURCE_SLOPE):
        r = _step(
            running,
            action="open",
            reason="co2",
            level="ok",
            window=WINDOW_CLOSED,
            window_source=source,
        )
        assert (r.state.phase, r.window_seen) == (PHASE_VENTILATING, WINDOW_UNKNOWN), (
            source
        )


def test_a_stale_reading_is_not_a_current_one() -> None:
    running = EpisodeState(
        phase=PHASE_VENTILATING, reason="co2", owner="co2", opened_seen=True
    )
    r = _step(
        running,
        action="open",
        reason="co2",
        level="ok",
        window=WINDOW_CLOSED,
        window_source=WINDOW_SOURCE_CONTACT,
        window_age_min=45.0,
    )
    assert (r.state.phase, r.window_seen) == (PHASE_VENTILATING, WINDOW_UNKNOWN)


def test_an_open_reading_is_evidence_from_every_source() -> None:
    """An inferred opening IS an observation — the slope saw a real drop."""
    for source in (WINDOW_SOURCE_CONTACT, WINDOW_SOURCE_SLOPE):
        r = _step(
            EpisodeState(),
            action="open",
            reason="co2",
            level="ok",
            window=WINDOW_LIKELY_OPEN,
            window_source=source,
        )
        assert (r.state.phase, r.state.opened_seen) == (PHASE_VENTILATING, True), source


# --- Rev. 7: der externe Prüfbericht vom 18.09.2026 --------------------------


def test_a_latched_protection_stop_keeps_its_reason_and_severity() -> None:
    """The v2a blocker: an ordinary close overwrote a latched protection one.

    The latch stayed set while the message turned harmless — the worst of both
    worlds, and invisible to the earlier test, which only followed up with an
    OPEN advice.
    """
    latched = _step(
        EpisodeState(),
        action="close",
        reason="thermal_floor",
        level="warn",
        window=WINDOW_OPEN,
    )
    assert latched.state.emergency
    for reason in ("target_reached", "cooled_off", "too_dry"):
        r = _step(
            latched.state, action="close", reason=reason, level="ok", window=WINDOW_OPEN
        )
        assert (r.reason, r.level, r.state.emergency) == (
            "thermal_floor",
            "warn",
            True,
        ), reason
        assert (r.state.reason, r.state.level) == ("thermal_floor", "warn"), reason
    # ... while another protection close DOES update it
    other = _step(
        latched.state,
        action="close",
        reason="mold_guard",
        level="warn",
        window=WINDOW_OPEN,
    )
    assert other.reason == "mold_guard"


def test_an_escalation_is_an_event_outside_both_quotas() -> None:
    """Decided contract: quotas govern REMINDERS, an escalation announces once.

    Bounded by the latch, not by a counter: once ``emergency`` is set, every
    later protection close is a continuation, so an episode escalates at most
    once. Reported as prompt 7 against a hard quota of 6 — the quota is fine,
    the escalation simply is not a reminder.
    """
    r = _step(EpisodeState(), action="open", reason="moisture_protect", level="warn")
    r = _step(
        r.state, action="close", reason="target_reached", level="ok", window=WINDOW_OPEN
    )
    for _ in range(35):
        r = _step(
            r.state,
            action="close",
            reason="target_reached",
            level="ok",
            window=WINDOW_OPEN,
        )
    assert r.state.prompts == _CFG.max_prompts_per_phase_protection
    esc = _step(
        r.state,
        action="close",
        reason="thermal_floor",
        level="warn",
        window=WINDOW_OPEN,
    )
    assert esc.prompt and esc.state.escalations == 1
    assert esc.state.prompts == _CFG.max_prompts_per_phase_protection  # quota untouched
    again = _step(
        esc.state,
        action="close",
        reason="thermal_floor",
        level="warn",
        window=WINDOW_OPEN,
    )
    assert not again.prompt and again.state.escalations == 1


def test_a_lost_cause_ends_on_the_episode_token_in_every_phase() -> None:
    """``close/no_data`` is not a reason a user can act on.

    REQUESTED always answered a vanished cause with ``airing_done``;
    VENTILATING published whatever the resolver happened to say, including the
    data-loss token the neutral reason was invented for.
    """
    running = _step(
        EpisodeState(), action="open", reason="co2", level="ok", window=WINDOW_OPEN
    )
    for lost in ("no_data", "no_gain"):
        r = _step(
            running.state, action="idle", reason=lost, level="ok", window=WINDOW_OPEN
        )
        assert (r.action, r.reason) == ("close", REASON_AIRING_DONE), lost
    # an explicit close keeps its own reason
    told = _step(
        running.state,
        action="close",
        reason="target_reached",
        level="ok",
        window=WINDOW_OPEN,
    )
    assert told.reason == "target_reached"


def test_a_zero_quota_sends_nothing_and_claims_nothing() -> None:
    """``ask`` checked only the episode ceiling, and counted a prompt it never
    sent — ``prompts`` means "already rung".
    """
    r = _step(
        EpisodeState(),
        action="open",
        reason="co2",
        level="ok",
        window=WINDOW_UNKNOWN,
        cfg=EpisodeConfig(max_prompts_per_phase=0),
    )
    assert not r.prompt
    assert (r.state.prompts, r.state.episode_prompts) == (0, 0)


# --- Schritt 4C: what is left over when an episode ends ---------------------


def test_a_hand_closed_window_does_not_erase_the_demand_left_behind() -> None:
    """The episode ends, the air does not.

    Closing the window at 1400 ppm ends OUR episode and starts a deliberately
    silent cooldown. Without the note that follows, those ten minutes look
    from the card like Poise dropped the subject.
    """
    airing = _step(
        EpisodeState(), action="open", reason="co2", level="ok", window=WINDOW_OPEN
    )
    assert airing.state.phase == PHASE_VENTILATING
    shut = _step(airing.state, action="open", reason="co2", level="ok")
    assert (shut.state.phase, shut.action) == (PHASE_COOLDOWN, "idle")
    assert shut.idle_cause == IDLE_COOLDOWN
    assert shut.pending_reason == "co2"
    # ... and the note dies with the quiet time, because the demand itself is
    # then advised again rather than remembered.
    back = _step(
        shut.state,
        action="open",
        reason="co2",
        level="ok",
        dt_min=_CFG.cooldown_manual_min,
    )
    assert (back.state.phase, back.action) == (PHASE_REQUESTED, "open")
    assert back.pending_reason == ""


def test_the_remembered_reason_follows_the_resolver_not_the_clock() -> None:
    """A note that outlived its cause would advise airing for air that is
    already fine — the one failure mode this field can produce."""
    shut = _step(
        _step(
            EpisodeState(), action="open", reason="co2", level="ok", window=WINDOW_OPEN
        ).state,
        action="open",
        reason="co2",
        level="ok",
    )
    gone = _step(shut.state, action="idle", reason="no_gain", level="ok")
    assert (gone.state.phase, gone.pending_reason) == (PHASE_COOLDOWN, "")
    moved = _step(gone.state, action="open", reason="heat_out", level="ok")
    assert (moved.state.phase, moved.pending_reason) == (PHASE_COOLDOWN, "heat_out")


def test_an_episode_that_ended_on_its_goal_remembers_nothing() -> None:
    """``close/target_reached`` IS the answer that nothing is left."""
    stopping = _step(
        _step(
            EpisodeState(),
            action="open",
            reason="moisture_out",
            level="ok",
            window=WINDOW_OPEN,
        ).state,
        action="close",
        reason="target_reached",
        level="ok",
        window=WINDOW_OPEN,
    )
    assert stopping.state.phase == PHASE_STOP_REQUESTED
    done = _step(stopping.state, action="close", reason="target_reached", level="ok")
    assert (done.state.phase, done.pending_reason) == (PHASE_COOLDOWN, "")
