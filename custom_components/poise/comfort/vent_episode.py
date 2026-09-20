"""Ventilation EPISODE state machine: what the user is asked to do, and when.

ADR-0074. ``ventilation.py`` answers one question per tick — which reason
carries right now — and it stays the single owner of that answer. This module
answers the second question the user actually experiences: is this a request
that has not been acted on yet, a running airing, or a request to close?

The separation is the point. "An airing episode of ours is running" used to be
reconstructed each tick from the previous tick's reason token plus the window
contact, and every corner of that reconstruction had to be patched separately
(ADR-0066 N6, N7, N9). Here it is a stored phase, so the class of defect
where one tick produces opposite advice depending on the window contact
cannot arise: **the window contact alone never inverts the physical advice.**
An episode ends only through an explicit transition — a detected manual
closing is one of them, and a legitimate one.

The published physics is untouched — this module never re-derives a rule, it
only decides what the rule table's answer means in the current phase.

Pure and await-free: no I/O, no device, no clock. Elapsed time arrives as
``dt_min`` from the caller, the same convention as ``ewma_step``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

# --- Reason classes (§3) -------------------------------------------
# Building protection is exempt from every user-comfort mechanism below: its
# request never expires, a cooldown never suppresses it, and its prompts come
# from the larger protection budget rather than the small comfort one.
# ADR-0050 draws the same line for the occupancy gate; this is that line on
# the UX rail.
PROTECTION_OPEN: Final[tuple[str, ...]] = ("mold_risk", "moisture_protect")
# ``too_dry`` is deliberately NOT here. It fires at 7 g/m3 or 35 % RH — the
# ordinary dryness warning, not a hazard. A genuinely critical dryness stop
# belongs on the stricter ``dry_alert_gm3`` line and is a precedence decision
# for the rule table, not for this module (§"offen").
PROTECTION_CLOSE: Final[tuple[str, ...]] = ("mold_guard", "thermal_floor")
COMFORT_OPEN: Final[tuple[str, ...]] = ("moisture_out", "co2", "heat_out")

# The one token this module owns. Every other reason it publishes comes from
# the rule table verbatim; this one says something the table cannot: "the
# airing this axis asked for has no reason left, and we do not know that the
# window is shut". It deliberately does NOT claim ``target_reached`` — the
# cause may have vanished through lost data or a change of occupancy, and
# claiming a goal was reached would be a physics statement the FSM cannot
# make. The card has to learn it (ADR-0074, Schritt 8).
REASON_AIRING_DONE: Final = "airing_done"

# --- Window signal ----------------------------------------------------------
# Five values, not a boolean: a zone without a contact is not "closed", it is
# unknown, and an inferred state is not a measured one. The distinction is
# user-visible (the card's window legend).
WINDOW_OPEN: Final = "open"
WINDOW_CLOSED: Final = "closed"
WINDOW_LIKELY_OPEN: Final = "likely_open"
WINDOW_LIKELY_CLOSED: Final = "likely_closed"
WINDOW_UNKNOWN: Final = "unknown"

_OPENISH: Final = (WINDOW_OPEN, WINDOW_LIKELY_OPEN)
_CLOSEDISH: Final = (WINDOW_CLOSED, WINDOW_LIKELY_CLOSED)

# Where the reading came from. It decides how much the reading PROVES, which
# is not the same as what it says (ADR-0041):
#   * a contact reports both directions by measurement;
#   * the slope estimator DETECTS an opening from the temperature drop, but it
#     returns to "closed" on its own maximum-duration reset — that return is a
#     timeout, never an observed closing;
#   * a user bypass forces the control-side window signal to "closed" as an
#     escape hatch. That is an instruction, not an observation.
# So: an open-ish reading from any source is evidence; a closed-ish reading is
# evidence only from a contact.
WINDOW_SOURCE_CONTACT: Final = "contact"
WINDOW_SOURCE_SLOPE: Final = "slope"
WINDOW_SOURCE_BYPASS: Final = "bypass"
WINDOW_SOURCE_NONE: Final = "none"

_PROVES_CLOSED: Final = (WINDOW_SOURCE_CONTACT,)


# --- Phases -----------------------------------------------------------------
PHASE_IDLE: Final = "idle"
PHASE_REQUESTED: Final = "requested"
PHASE_VENTILATING: Final = "ventilating"
PHASE_STOP_REQUESTED: Final = "stop_requested"
PHASE_COOLDOWN: Final = "cooldown"

# --- Why nothing is happening (§6) ---------------------------------
# One terminal state in the flow chart hid four different situations, and the
# 2026-09-14 bathroom finding is what that costs: high humidity, no advice, and
# no way for the user to tell "fine" from "blocked".
IDLE_ALL_GOOD: Final = "all_good"
IDLE_OUTSIDE_NOT_DRIER: Final = "outside_not_drier"
IDLE_FABRIC_HEATED: Final = "fabric_heated"
IDLE_NO_DATA: Final = "no_data"
IDLE_COOLDOWN: Final = "cooldown"

DEFAULT_REQUEST_TTL_MIN: float = 15.0
DEFAULT_REMINDER_EVERY_MIN: float = 7.0
# Prompts per PROMPTING PHASE, the opening ask included — a request and a
# later stop request each get their own budget. One budget for the whole
# episode would let two open reminders eat every close reminder that follows.
DEFAULT_MAX_PROMPTS_PER_PHASE: int = 2
DEFAULT_MAX_PROMPTS_PER_PHASE_PROTECTION: int = 6
# ... and a ceiling over the WHOLE episode, because the per-phase budget alone
# is defeated by re-entry: a reason that flickers across its threshold walks
# ventilating -> stop_requested -> ventilating and starts a fresh phase budget
# every time. Measured on a reason toggling each tick: ten prompts in
# twenty-one ticks. The rule table's own entry/exit thresholds are where that
# flicker belongs; until one exists for every reason, this is the backstop.
DEFAULT_MAX_PROMPTS_PER_EPISODE: int = 4
DEFAULT_MAX_PROMPTS_PER_EPISODE_PROTECTION: int = 10
# Beyond this a window reading is treated as unobservable rather than current.
DEFAULT_WINDOW_STALE_AFTER_MIN: float = 30.0
DEFAULT_COOLDOWN_MIN: float = 10.0
DEFAULT_COOLDOWN_MANUAL_MIN: float = 10.0
DEFAULT_COOLDOWN_EXPIRED_MIN: float = 20.0
DEFAULT_COOLDOWN_EMERGENCY_MIN: float = 45.0
# How long an UNOBSERVABLE stop request is held before it times out. Not a
# hazard timer and not an all-clear: with no contact the rule table cannot
# report a hazard at all (see ``resolver_quiet``), so this is the admission
# that we cannot find out, and it ends in the protection cooldown.
DEFAULT_UNKNOWN_STOP_RELEASE_MIN: float = 5.0
# A restart or a stalled coordinator must not age the machine by hours in one
# step; the same capped-gap rule the regulation-quality minutes use.
DEFAULT_MAX_TICK_MIN: float = 10.0


@dataclass(frozen=True, slots=True)
class EpisodeConfig:
    request_ttl_min: float = DEFAULT_REQUEST_TTL_MIN
    reminder_every_min: float = DEFAULT_REMINDER_EVERY_MIN
    max_prompts_per_phase: int = DEFAULT_MAX_PROMPTS_PER_PHASE
    max_prompts_per_phase_protection: int = DEFAULT_MAX_PROMPTS_PER_PHASE_PROTECTION
    max_prompts_per_episode: int = DEFAULT_MAX_PROMPTS_PER_EPISODE
    max_prompts_per_episode_protection: int = DEFAULT_MAX_PROMPTS_PER_EPISODE_PROTECTION
    window_stale_after_min: float = DEFAULT_WINDOW_STALE_AFTER_MIN
    cooldown_min: float = DEFAULT_COOLDOWN_MIN
    cooldown_manual_min: float = DEFAULT_COOLDOWN_MANUAL_MIN
    cooldown_expired_min: float = DEFAULT_COOLDOWN_EXPIRED_MIN
    cooldown_emergency_min: float = DEFAULT_COOLDOWN_EMERGENCY_MIN
    unknown_stop_release_min: float = DEFAULT_UNKNOWN_STOP_RELEASE_MIN
    max_tick_min: float = DEFAULT_MAX_TICK_MIN


_DEFAULT_CFG = EpisodeConfig()


def effective_window(
    state: str,
    *,
    source: str = WINDOW_SOURCE_CONTACT,
    age_min: float | None = None,
    cfg: EpisodeConfig | None = None,
) -> str:
    """What the reading is worth, as opposed to what it says.

    A stale reading and a closed-ish reading that nobody measured both come
    out as ``unknown`` — the machine then treats the window as unobservable,
    which is the honest state and the one with the careful exits.

    ``age_min`` is the age of the READING: how long ago the source last
    produced this value, i.e. data freshness. It is NOT the time since the
    window last changed — a contact that reports every minute is fresh after
    an hour of standing open.

    This is the single normalisation for the whole seam: the same result must
    be handed to ``episode_step`` AND, through ``oracle_window_open``, to the
    rule table. Normalising twice, or only once, is how the two layers come to
    believe different things about one window.
    """
    conf = cfg if cfg is not None else _DEFAULT_CFG
    if state == WINDOW_UNKNOWN:
        return WINDOW_UNKNOWN
    if age_min is not None and age_min > conf.window_stale_after_min:
        return WINDOW_UNKNOWN
    if state in _CLOSEDISH and source not in _PROVES_CLOSED:
        return WINDOW_UNKNOWN
    return state


@dataclass(frozen=True, slots=True)
class EpisodeState:
    """Everything the machine remembers between ticks. Persisted per zone."""

    phase: str = PHASE_IDLE
    reason: str = ""  # the reason currently published
    level: str = "ok"  # severity of the PUBLISHED advice, stored with it
    # A stable identity for one airing, from the first ask to the end of its
    # cooldown. Phases come and go inside it; the notification ceiling and the
    # opening evidence belong to the episode, not to a phase.
    episode_id: int = 0
    episode_prompts: int = 0
    # Which budget this EPISODE draws on. Sticky and one-way: once building
    # protection has spoken, the larger allowance holds for the rest of the
    # episode. Deriving it from the current token instead let a protection
    # episode's spend be measured against the small comfort ceiling the
    # moment its reason handed over to a plain all-clear.
    protected: bool = False
    # An OPEN-ish reading was actually observed in this episode. Without it the
    # machine never claims an airing is under way.
    opened_seen: bool = False
    # Escalations announced in this episode. At most one, because the latch
    # makes every later protection close a continuation rather than a step up.
    escalations: int = 0
    # ``prompts`` counts within the CURRENT prompting phase and resets on each
    # phase change; see ``max_prompts_per_phase``.
    # The OPEN reason CARRYING the episode right now — it follows a reason
    # change on purpose, because ``oracle_flags`` has to hand the rule table
    # the hysteresis anchor of the reason that is actually holding the window.
    # Not an immutable origin.
    owner: str = ""
    phase_min: float = 0.0
    prompts: int = 0  # prompts already sent for this episode
    unknown_dwell_min: float = 0.0  # time a stop has stood on an UNKNOWN contact
    # The evidence THIS phase was entered on was inferred rather than
    # measured. A statement about the entry, not about the current tick —
    # ``EpisodeResult.window_seen`` carries what is observed right now. The
    # card needs both: "Lüften vermutlich begonnen" plus the live status.
    entry_inferred: bool = False
    emergency: bool = False  # the stop came from a protection abort (latched)
    cooldown_for_min: float = 0.0
    # "" means the cooldown blocks every comfort reason; a token means it
    # blocks only that one. A finished humidity episode must not swallow an
    # independent CO2 demand two minutes later.
    cooldown_scope: str = ""
    # The open reason that was STILL valid when the episode ended (Schritt 4C:
    # "verbleibende Gruende merken"). A window closed by hand at 1400 ppm ends
    # the episode but not the demand, and the cooldown that follows is
    # deliberately silent - so without this field the user sees an unexplained
    # gap and the machine looks like it forgot. Only ever set while the phase
    # is COOLDOWN; it is a note about the quiet time, not an episode memory.
    pending_reason: str = ""


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    """The user-visible outcome of one tick.

    ``action`` is the TRUTH and ``prompt`` is the doorbell. They are
    independent on purpose: once the prompt budget is spent the machine goes
    quiet, but a window that should be closed keeps saying so on the card.
    """

    state: EpisodeState
    action: str  # "idle" | "open" | "close" | "discourage"
    reason: str  # an ADR-0066 token, or the FSM-owned ``airing_done``
    level: str  # "ok" | "warn" | "alert"
    prompt: bool
    idle_cause: str  # only meaningful while action == "idle"
    # What the machine actually believed about the window this tick, after
    # ``effective_window`` discounted a stale or unproven reading. The card
    # shows THIS, not the raw contact — otherwise "closed" would mean two
    # different things depending on where it came from.
    window_seen: str = WINDOW_UNKNOWN
    # Non-empty only during a cooldown: the reason that will be advised again
    # once the quiet time is over. It explains an ``idle/cooldown`` that the
    # user would otherwise read as "Poise dropped it".
    pending_reason: str = ""


def is_protection(reason: str) -> bool:
    """Building protection: exempt from the TTL and the cooldown, and it draws
    on the larger protection prompt budget instead of the comfort one — not
    exempt from a budget, just given a bigger one."""
    return reason in PROTECTION_OPEN or reason in PROTECTION_CLOSE


def oracle_window_open(window: str) -> bool:
    """The boolean ``ventilation_advise`` still takes.

    **Integration contract:** the caller MUST pass the value
    ``effective_window()`` returned, the same one handed to ``episode_step``.
    Feeding the raw contact here and the normalised one to the machine lets
    the two layers disagree about the same window — a stale reading would be
    "open" to the rule table and "unknown" to the episode.

    An inferred open counts as open: the physics of an open window does not
    depend on how we learned about it. ``unknown`` maps to False, which is the
    known gap — the rule table's close rules all require ``window_open``, so a
    contact-less zone still cannot reach them. Decoupling those predicates
    touches the rule table and is therefore out of this package.
    """
    return window in _OPENISH


def oracle_flags(state: EpisodeState) -> dict[str, bool]:
    """The ``prev_*`` inputs of ``ventilation_advise``, derived from the phase.

    ADR-0066 N6/N6b/N9 built these from the previous tick's published reason,
    which is why "is an episode of ours running" and "was this the reason we
    published" could drift apart. Here they are one read of one stored phase.
    """
    running = state.phase in (PHASE_REQUESTED, PHASE_VENTILATING)
    owner = state.owner
    return {
        "prev_advice_active": running,
        "prev_moisture_airing": running and owner in ("moisture_out", "mold_risk"),
        "prev_moisture_protect": running and owner == "moisture_protect",
        "prev_heat_out": running and owner == "heat_out",
    }


def idle_cause(
    *,
    reason: str,
    cool_edge_protected: bool,
    room_over_safe: bool,
    outside_drier: bool,
) -> str:
    """Name the reason NOTHING is being advised (§6).

    Derived from the same inputs the rules read, so it cannot disagree with
    them, and deliberately NOT a new token inside ``ventilation.py`` — that
    module's vocabulary is a pinned display contract.
    """
    if reason == "no_data":
        return IDLE_NO_DATA
    if room_over_safe and cool_edge_protected:
        # ADR-0066 N9: heat is already defending the fabric, so airing would
        # work against that defence. The user sees high humidity and no
        # advice; without this they read it as a miss.
        return IDLE_FABRIC_HEATED
    if room_over_safe and not outside_drier:
        return IDLE_OUTSIDE_NOT_DRIER
    return IDLE_ALL_GOOD


def _cooldown_len(cfg: EpisodeConfig, cause: str) -> float:
    if cause == "emergency":
        return cfg.cooldown_emergency_min
    if cause == "expired":
        return cfg.cooldown_expired_min
    if cause == "manual":
        return cfg.cooldown_manual_min
    return cfg.cooldown_min


def episode_protected(state: EpisodeState) -> bool:
    """Does this episode draw on the protection budget? One-way, and sticky."""
    return (
        state.protected
        or state.emergency
        or is_protection(state.reason)
        or is_protection(state.owner)
    )


def _prompt_cap(state: EpisodeState, cfg: EpisodeConfig) -> int:
    return (
        cfg.max_prompts_per_phase_protection
        if episode_protected(state)
        else cfg.max_prompts_per_phase
    )


def _episode_cap(state: EpisodeState, cfg: EpisodeConfig) -> int:
    return (
        cfg.max_prompts_per_episode_protection
        if episode_protected(state)
        else cfg.max_prompts_per_episode
    )


def _prompt_due(state: EpisodeState, cfg: EpisodeConfig) -> bool:
    if state.episode_prompts >= _episode_cap(state, cfg):
        return False
    if state.prompts >= _prompt_cap(state, cfg):
        return False
    return state.phase_min >= state.prompts * cfg.reminder_every_min


def _spend(state: EpisodeState) -> EpisodeState:
    """One prompt leaves the phase quota AND the episode ceiling."""
    return replace(
        state, prompts=state.prompts + 1, episode_prompts=state.episode_prompts + 1
    )


def _enter(state: EpisodeState, phase: str, **kw: object) -> EpisodeState:
    """Enter a phase.

    ``entry_inferred`` resets unless the caller sets it again: it describes
    THIS phase's evidence, and an inferred opening must not stick to a later
    resting state that the card would then label "vermutlich".
    """
    fields: dict[str, object] = {
        "phase": phase,
        "phase_min": 0.0,
        "unknown_dwell_min": 0.0,
        "entry_inferred": False,
    }
    fields.update(kw)
    return replace(state, **fields)  # type: ignore[arg-type]


def episode_step(  # noqa: PLR0911, PLR0912, PLR0915 - a transition table
    state: EpisodeState,
    *,
    action: str,
    reason: str,
    level: str,
    window: str,
    dt_min: float,
    window_source: str = WINDOW_SOURCE_CONTACT,
    window_age_min: float | None = None,
    cool_edge_protected: bool = False,
    room_over_safe: bool = False,
    outside_drier: bool = False,
    cfg: EpisodeConfig = _DEFAULT_CFG,
) -> EpisodeResult:
    """Advance the machine by one tick.

    ``action``/``reason``/``level`` are the verbatim output of
    ``ventilation_advise``; ``window`` plus ``window_source``/``window_age_min``
    are what is known about the window, which is not the same as what the
    contact entity says (see ``effective_window``).
    """
    step = min(max(dt_min, 0.0), cfg.max_tick_min)
    st = replace(state, phase_min=state.phase_min + step)
    seen = effective_window(
        window, source=window_source, age_min=window_age_min, cfg=cfg
    )
    openish = seen in _OPENISH
    closedish = seen in _CLOSEDISH
    inferred_open = seen == WINDOW_LIKELY_OPEN
    wants_open = action == "open"
    protection_abort = action == "close" and reason in PROTECTION_CLOSE
    # UNOBSERVABLE, not absent. Every close rule in the table requires
    # ``window_open``, and an unknown contact is handed to it as False — so
    # with no contact the resolver CANNOT report a hazard, whatever the walls
    # are doing. The timeout below is therefore an epistemic exit ("we cannot
    # find out"), not an all-clear, which is why it ends in a cooldown.
    #
    # The one thing a single-winner answer would genuinely prove: ``idle`` sits
    # at the bottom of the waterfall, and ``discourage``/``too_dry`` outranks
    # only ``mold_guard`` — NOT ``thermal_floor``, which the table checks after
    # it. So no single token proves both protection closes absent. Supplying
    # that proof is what the evaluation layer is for.
    resolver_quiet = action in ("idle", "discourage") or (
        wants_open and reason != "mold_risk"
    )
    if openish:
        st = replace(st, opened_seen=True)
    if st.phase != PHASE_IDLE and (is_protection(reason) or st.emergency):
        st = replace(st, protected=True)

    def out(
        s: EpisodeState, a: str, r: str, lv: str, prompt: bool = False
    ) -> EpisodeResult:
        cause = ""
        if a == "idle":
            cause = (
                IDLE_COOLDOWN
                if s.phase == PHASE_COOLDOWN
                else idle_cause(
                    reason=r,
                    cool_edge_protected=cool_edge_protected,
                    room_over_safe=room_over_safe,
                    outside_drier=outside_drier,
                )
            )
        return EpisodeResult(s, a, r, lv, prompt, cause, seen, s.pending_reason)

    def quiet(s: EpisodeState) -> EpisodeResult:
        """Publish the resolver's own non-episode verdict, verbatim.

        ``discourage`` ("better not open, the room is already dry") is a real
        user-facing state of ADR-0066 rule 2. It must survive every phase that
        has nothing else to say — including the tick an episode ENDS on, which
        is exactly where the first draft dropped it.
        """
        if action == "discourage":
            return out(s, "discourage", reason, level)
        return out(s, "idle", reason, "ok")

    def begin(s: EpisodeState, phase: str, **kw: object) -> EpisodeState:
        """Start a NEW episode: fresh identity, fresh ceiling, no evidence."""
        return _enter(
            s,
            phase,
            episode_id=s.episode_id + 1,
            episode_prompts=0,
            escalations=0,
            protected=is_protection(reason),
            opened_seen=openish,
            pending_reason="",
            **kw,
        )

    def ask(s: EpisodeState) -> tuple[EpisodeState, bool]:
        """The opening prompt of a phase — it counts in BOTH budgets.

        Letting a phase entry prompt for free is what defeated the per-phase
        quota: a reason flickering across its threshold re-enters the phase
        and rings again, forever. The episode ceiling only works if every
        prompt passes through here.
        """
        if s.episode_prompts >= _episode_cap(s, cfg) or _prompt_cap(s, cfg) < 1:
            # Not sent, so not counted — ``prompts`` means "already rung".
            return s, False
        return replace(s, prompts=1, episode_prompts=s.episode_prompts + 1), True

    def stop(s: EpisodeState, *, why: str, emergency: bool, lv: str) -> EpisodeState:
        """Ask for the airing to end, inside the SAME episode."""
        return _enter(
            s,
            PHASE_STOP_REQUESTED,
            reason=why,
            level=lv,
            emergency=emergency,
            # ``unknown`` is not an inference — it is the absence of one.
            entry_inferred=inferred_open,
        )

    def settle(s: EpisodeState, cause: str, scope: str) -> EpisodeState:
        """End the episode into the quiet time — carrying what is left over.

        An episode ends for its own reasons (the window was shut by hand, the
        request ran out); whether the AIR still needs changing is a separate
        question, and the resolver answers it on this very tick. If it still
        says "open", that demand outlives the episode and the cooldown merely
        postpones it, so it is written down rather than dropped.
        """
        return _enter(
            s,
            PHASE_COOLDOWN,
            prompts=0,
            emergency=False,
            cooldown_for_min=_cooldown_len(cfg, cause),
            cooldown_scope=scope,
            pending_reason=reason if wants_open else "",
        )

    # --- COOLDOWN: the quiet time after an episode ---------------------------
    if st.phase == PHASE_COOLDOWN:
        scope_free = bool(st.cooldown_scope) and reason != st.cooldown_scope
        # Remembered, not preserved: the note tracks the resolver instead of
        # outliving it. Announcing a demand that has since been met would be
        # the one failure mode this field can produce, and it is the same
        # discipline the module applies everywhere else — the rule table owns
        # the physics, this module owns only what it MEANS right now.
        st = replace(st, pending_reason=reason if wants_open else "")
        if (
            (wants_open and reason in PROTECTION_OPEN)
            or protection_abort
            or (wants_open and scope_free)
            or st.phase_min >= st.cooldown_for_min
        ):
            st = _enter(
                st,
                PHASE_IDLE,
                reason="",
                owner="",
                level="ok",
                prompts=0,
                episode_prompts=0,
                protected=False,
                emergency=False,
                cooldown_scope="",
                cooldown_for_min=0.0,
                pending_reason="",
            )
        elif action == "close":
            # Consistent with the rule the whole module runs on: a cooldown is
            # anti-spam, so it silences the doorbell, never the truth. A
            # window that should be closed keeps saying so on the card, and a
            # protection close has already broken out above.
            return out(st, "close", reason, level)
        else:
            return quiet(st)

    # --- IDLE: watching ------------------------------------------------------
    if st.phase == PHASE_IDLE:
        if wants_open:
            # A window that is ALREADY open needs no request — the user is
            # doing the right thing and only needs to be told when to stop.
            if openish:
                st = begin(
                    st,
                    PHASE_VENTILATING,
                    reason=reason,
                    owner=reason,
                    level=level,
                    prompts=0,
                    entry_inferred=inferred_open,
                )
                return out(st, "open", reason, level)
            st, due = ask(
                begin(
                    st,
                    PHASE_REQUESTED,
                    reason=reason,
                    owner=reason,
                    level=level,
                    entry_inferred=False,
                )
            )
            return out(st, "open", reason, level, prompt=due)
        if action == "close" and openish:
            # Opened without us asking, and now there is a reason to close.
            st, due = ask(
                begin(
                    st,
                    PHASE_STOP_REQUESTED,
                    reason=reason,
                    owner="",
                    level=level,
                    emergency=protection_abort,
                    entry_inferred=inferred_open,
                )
            )
            return out(st, "close", reason, level, prompt=due)
        return quiet(st)

    # --- REQUESTED: we asked, the window has not moved -----------------------
    if st.phase == PHASE_REQUESTED:
        if openish:
            # The CURRENT answer decides, not the request that is being acted
            # on. A user following a minute-old "please open" must never
            # overrule a protection close that has meanwhile become true.
            if wants_open:
                st = _enter(
                    st,
                    PHASE_VENTILATING,
                    reason=reason,
                    owner=reason,
                    level=level,
                    entry_inferred=inferred_open,
                    prompts=0,
                )
                return out(st, "open", reason, level)
            if action == "close":
                st, due = ask(
                    stop(st, why=reason, emergency=protection_abort, lv=level)
                )
                return out(st, "close", reason, level, prompt=due)
            # Opened, and the cause is already gone: we KNOW a window was
            # opened on our advice, so the episode gets its explicit end.
            st, due = ask(stop(st, why=REASON_AIRING_DONE, emergency=False, lv="ok"))
            return out(st, "close", REASON_AIRING_DONE, "ok", prompt=due)
        if not wants_open:
            # The cause is gone. Whether that ends the story depends on what
            # we KNOW about the window, and only one answer is safe to end
            # silently: a measured "shut".
            if closedish:
                st = _enter(st, PHASE_IDLE, reason="", owner="", level="ok", prompts=0)
                return quiet(st)
            st, due = ask(stop(st, why=REASON_AIRING_DONE, emergency=False, lv="ok"))
            return out(st, "close", REASON_AIRING_DONE, "ok", prompt=due)
        st = replace(st, reason=reason, owner=reason, level=level)
        if (
            closedish
            and st.phase_min >= cfg.request_ttl_min
            and not is_protection(st.owner)
        ):
            # A COMFORT request expires only against a window KNOWN to be
            # shut — then it demonstrably was not acted on. Where the contact
            # cannot say, the request STANDS: the reason still holds, so
            # advising an end would be wrong, and forgetting the request would
            # lose the ending the user is owed once the reason does go away.
            # What runs out there is the prompt budget, not the request.
            st = settle(st, "expired", "")
            return quiet(st)
        due = _prompt_due(st, cfg)
        if due:
            st = _spend(st)
        return out(st, "open", st.reason, level, prompt=due)

    # --- VENTILATING: the window is open and a reason still holds ------------
    if st.phase == PHASE_VENTILATING:
        if closedish:
            st = settle(st, "manual", "")
            return quiet(st)
        if wants_open:
            # Reasons may change inside one episode (humidity spent, CO2 still
            # high): the episode continues under the new reason.
            return out(
                replace(st, reason=reason, owner=reason, level=level),
                "open",
                reason,
                level,
            )
        # An explicit CLOSE keeps its own reason; anything else — the cause
        # simply gone, or gone WITH the data — ends on the neutral episode
        # token. "Schließen / keine Daten" is not a reason a user can act on,
        # and REQUESTED has always answered this the same way.
        why = reason if action == "close" else REASON_AIRING_DONE
        lv = level if action == "close" else "ok"
        st, due = ask(stop(st, why=why, emergency=protection_abort, lv=lv))
        return out(st, "close", why, lv, prompt=due)

    # --- STOP_REQUESTED: please close ---------------------------------------
    if closedish:
        # A goal reached normally rests ITS OWN reason; an aborted or an
        # unconfirmed one earns the blanket quiet time.
        emergency = st.emergency
        st = settle(
            st,
            "emergency" if emergency else "regular",
            "" if emergency else st.owner,
        )
        return quiet(st)
    if wants_open and not st.emergency:
        # A new valid opening reason cancels an ordinary stop request — but
        # only where a window was actually seen open. Without that evidence
        # the machine has no airing to resume and asks again instead.
        if openish:
            st = _enter(
                st,
                PHASE_VENTILATING,
                reason=reason,
                owner=reason,
                level=level,
                prompts=0,
                entry_inferred=inferred_open,
            )
            return out(st, "open", reason, level)
        st, due = ask(
            _enter(
                st,
                PHASE_REQUESTED,
                reason=reason,
                owner=reason,
                level=level,
                entry_inferred=False,
            )
        )
        return out(st, "open", reason, level, prompt=due)
    if seen == WINDOW_UNKNOWN and resolver_quiet:
        # Only here. A contact that says OPEN is knowledge, and a standing
        # "please close" must not expire against knowledge — that would be the
        # doorbell silencing the truth, which is the very coupling this module
        # removes. A closed contact is handled above.
        st = replace(st, unknown_dwell_min=st.unknown_dwell_min + step)
        if st.unknown_dwell_min >= cfg.unknown_stop_release_min:
            # The episode leaves through a COOLDOWN, never straight into
            # watching: we do not know whether the window was ever closed, so
            # a quiet time is what keeps this from becoming an abort/reopen
            # cycle. Both lengths are the blanket kind — nothing here was
            # confirmed, so nothing may be scoped to one reason.
            st = settle(st, "emergency" if st.emergency else "expired", "")
            return quiet(st)
    else:
        st = replace(st, unknown_dwell_min=0.0)
    escalated = False
    if action == "close":
        escalated = protection_abort and not st.emergency
        # A LATCHED protection stop keeps its own reason and severity. An
        # ordinary close — ``target_reached``, ``cooled_off``, ``too_dry`` —
        # may not overwrite them: the latch would stay set while the message
        # said something harmless, which is the worst of both. Only another
        # protection close updates a latched one.
        if protection_abort or not st.emergency:
            st = replace(st, reason=reason, level=level)
        st = replace(st, emergency=st.emergency or protection_abort)
    # An ESCALATION is an EVENT, not a reminder, and therefore outside both
    # reminder quotas — waiting for the clock would delay a fabric warning by
    # minutes. It is bounded by the latch instead: once ``emergency`` is set,
    # every later protection close is a continuation, not a step up, so an
    # episode announces at most one. The contract in one line: quotas govern
    # REMINDERS, an escalation always announces once.
    if escalated:
        return out(
            replace(st, escalations=st.escalations + 1),
            "close",
            st.reason,
            st.level,
            prompt=True,
        )
    due = _prompt_due(st, cfg)
    if due:
        st = _spend(st)
    # The budget is spent but the truth is unchanged: still "close", just
    # silent. This is the separation the reminder cap used to break. The
    # severity comes from the STORED advice, so a latched protection stop
    # never inherits the "ok" of whatever the resolver happens to say now.
    return out(st, "close", st.reason, st.level, prompt=due)
