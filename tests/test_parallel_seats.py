"""Parallel per-phase seat calls (M-foedus-parallel-seat-calls).

Within a turn's phase every seat answers from the SAME prior-turn public
snapshot (Diplomacy simultaneous secret orders), so the per-seat LLM calls
are informationally independent and may run CONCURRENTLY. This module pins
down the whole-review correctness contract:

1. OBSERVATIONAL EQUIVALENCE -- `play_game(..., parallel_seats=True)` must
   produce byte-identical game outcomes AND byte-identical per-seat decision
   logs vs the sequential default, given the same seeds + same scripted seat
   decisions. The decision log records each call's rendered *prompt*, so a
   parallel-vs-sequential prompt divergence (e.g. a fog leak where one seat's
   in-progress press bled into another's snapshot) would surface here.
2. REAL CONCURRENCY -- parallel mode must actually run the per-phase seat
   calls at the same time (proven with a barrier that only releases when all
   seats are inside their call simultaneously), not silently serialize.
3. SHARED-STATE / RNG SAFETY -- agents that do NOT opt in (heuristics) are
   never pre-warmed, so they are invoked exactly as today (no double call, no
   extra RNG draw, no reordering). Bounded concurrency is honored.

Dev is deliberately against the deterministic StubLLMClient (no real
`claude -p`) so these tests never contend for the live subscription.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from foedus.agents.llm.client import StubLLMClient
from foedus.agents.llm.diplomat import LLMDiplomat
from foedus.core import GameConfig, Move, Press
from foedus.legal import legal_orders_for_unit
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import initial_state

import foedus_llm_diplomat_run as harness


# --------------------------------------------------------------------------
# Scripted-stub helpers -- a per-seat StubLLMClient is consumed in identical
# order under parallel and sequential mode (parallelization is ACROSS seats;
# a given seat's own client is only ever touched by that seat's own thread,
# one call at a time: negotiate -> orders -> negotiate -> ...). So a scripted
# game is deterministic in BOTH modes, which is exactly what makes a
# sequential-vs-parallel diff meaningful.
# --------------------------------------------------------------------------


def _negotiate_json(seat: int, num_players: int) -> str:
    """A stance-only negotiate response (no intents/pacts -> parse_fail=0,
    and no unit-id guessing). Stance varies by seat so press_history and the
    cross-turn fogged view carry real content."""
    others = [p for p in range(num_players) if p != seat]
    stance = {str(others[0]): "ally"}
    if len(others) > 1:
        stance[str(others[1])] = "hostile"
    return json.dumps(
        {"press": {"stance": stance, "intents": []},
         "pacts": {"propose": [], "accept": []}}
    )


def _hold_orders_json() -> str:
    """Empty orders -> every owned unit Holds (documented shorthand, NOT a
    fallback per parse_orders_response)."""
    return json.dumps({"orders": {}})


def _scripted_responses(seat: int, num_players: int, max_turns: int) -> list[str]:
    # [negotiate, orders] per turn; a couple extra pairs in case the game
    # runs the full turn budget (StubLLMClient only raises when it runs OUT).
    pair = [_negotiate_json(seat, num_players), _hold_orders_json()]
    return pair * (max_turns + 2)


def _dispatch_factory(seats: list[int], responses_by_seat: dict[int, list[str]]):
    """`llm_agent_factory` takes no args, so hand each seat its own scripted
    client by dispatching in ascending seat order (run_one_llm_game builds
    per-seat agents in that order -- pinned by test_llm_diplomat_multiseat)."""
    order = iter(sorted(seats))

    def factory():
        s = next(order)
        return LLMDiplomat(client=StubLLMClient(list(responses_by_seat[s])))
    return factory


def _serialize_log(log: list[dict]) -> list[str]:
    # Match the harness's own persistence granularity (json.dumps(..., default=str))
    # so dataclasses inside `parsed` compare structurally.
    return [json.dumps(r, default=str, sort_keys=True) for r in log]


def _run_harness(seats, heuristics, seed, max_turns, *, parallel_seats):
    responses = {s: _scripted_responses(s, len(seats) + len(heuristics), max_turns)
                 for s in seats}
    return harness.run_one_llm_game(
        game_id=0, seed=seed, llm_seats=seats, heuristic_names=heuristics,
        max_turns=max_turns, llm_agent_factory=_dispatch_factory(seats, responses),
        parallel_seats=parallel_seats,
    )


# --------------------------------------------------------------------------
# 1. Observational equivalence -- THE correctness test.
# --------------------------------------------------------------------------


def test_parallel_matches_sequential_outcomes_and_decision_logs() -> None:
    seats = [0, 1, 2]
    heuristics: list[str] = []  # all-LLM table: maximum concurrency, zero heuristic RNG
    seed, max_turns = 7, 4

    seq_sweep, seq_tel, _seq_final, seq_agents = _run_harness(
        seats, heuristics, seed, max_turns, parallel_seats=False)
    par_sweep, par_tel, _par_final, par_agents = _run_harness(
        seats, heuristics, seed, max_turns, parallel_seats=True)

    assert par_sweep == seq_sweep
    assert par_tel == seq_tel
    # Per-seat decision logs must match byte-for-byte, INCLUDING the rendered
    # prompt -- a parallel snapshot that leaked another seat's in-progress
    # press would render a different negotiate prompt and fail here.
    for s in seats:
        assert _serialize_log(par_agents[s].decision_log) == \
            _serialize_log(seq_agents[s].decision_log), f"seat {s} log diverged"
    # Sanity: the game actually made decisions and parsed cleanly.
    assert seq_tel["n_decisions"] > 0
    assert seq_tel["parse_fail_count"] == 0


def _issues_a_move(agents: dict) -> bool:
    for ag in agents.values():
        for rec in ag.decision_log:
            if rec["phase"] == "orders":
                if any(isinstance(o, Move) for o in rec["parsed"].values()):
                    return True
    return False


def test_parallel_matches_sequential_with_movement() -> None:
    """Stronger variant: seats issue real legal Move orders on turn 0, so the
    resolution engine processes movement (not a vacuous all-Hold game) -- and
    the parallel run must still match the sequential run exactly."""
    seats = [0, 1, 2]
    num_players = 3
    seed, max_turns = 11, 3

    # Reconstruct the exact initial state run_one_llm_game builds, to script a
    # real legal move per seat (legality is checked at turn-0 order time,
    # which reads this same pre-move state).
    cfg = GameConfig(num_players=num_players, max_turns=max_turns, seed=seed,
                     archetype=harness.Archetype.CONTINENTAL_SWEEP, map_radius=2)
    m = generate_map(num_players, seed=seed, archetype=cfg.archetype,
                     map_radius=cfg.map_radius)
    state = initial_state(cfg, m)

    def _first_move_order(seat: int):
        for u in state.units.values():
            if u.owner != seat:
                continue
            for o in legal_orders_for_unit(state, u.id):
                if isinstance(o, Move):
                    return {str(u.id): {"type": "Move", "dest": o.dest}}
        return {}

    responses: dict[int, list[str]] = {}
    for s in seats:
        turn0 = [_negotiate_json(s, num_players),
                 json.dumps({"orders": _first_move_order(s)})]
        rest = [_negotiate_json(s, num_players), _hold_orders_json()] * (max_turns + 1)
        responses[s] = turn0 + rest

    def run(parallel: bool):
        return harness.run_one_llm_game(
            game_id=0, seed=seed, llm_seats=seats, heuristic_names=[],
            max_turns=max_turns,
            llm_agent_factory=_dispatch_factory(seats, responses),
            parallel_seats=parallel,
        )

    seq_sweep, seq_tel, _sf, seq_agents = run(False)
    par_sweep, par_tel, _pf, par_agents = run(True)

    assert par_sweep == seq_sweep
    assert par_tel == seq_tel
    for s in seats:
        assert _serialize_log(par_agents[s].decision_log) == \
            _serialize_log(seq_agents[s].decision_log)
    # Real Move orders were issued (resolution exercised movement, not just Holds).
    assert _issues_a_move(seq_agents)
    assert seq_tel["parse_fail_count"] == 0


# --------------------------------------------------------------------------
# 2. Real concurrency -- barrier proof at the play_game level.
# --------------------------------------------------------------------------


class _BarrierSeat:
    """Opt-in seat whose per-phase compute blocks on a shared Barrier: it only
    releases when EVERY seat is inside its call at once. If play_game ran the
    pre-warm serially, the first seat would wait alone and the barrier would
    time out (BrokenBarrierError) -- so a passing game proves true concurrency.

    Caches per (turn, player) exactly like LLMDiplomat, so the sequential
    pass that follows the pre-warm hits the cache and never re-blocks.
    """

    supports_parallel_prewarm = True

    def __init__(self, barrier: threading.Barrier) -> None:
        self._barrier = barrier
        self._neg: dict = {}
        self._ord: dict = {}

    def _compute_neg(self, state, player):
        key = (state.turn, player)
        if key not in self._neg:
            self._barrier.wait()
            self._neg[key] = Press(stance={}, intents=[])
        return self._neg[key]

    def _compute_ord(self, state, player):
        key = (state.turn, player)
        if key not in self._ord:
            self._barrier.wait()
            self._ord[key] = {}
        return self._ord[key]

    def prewarm_phase(self, state, player, phase) -> None:
        if phase == "negotiate":
            self._compute_neg(state, player)
        elif phase == "orders":
            self._compute_ord(state, player)
        else:
            raise ValueError(phase)

    def choose_press(self, state, player):
        return self._compute_neg(state, player)

    def choose_orders(self, state, player):
        return self._compute_ord(state, player)

    def chat_drafts(self, state, player):
        return []


def test_parallel_actually_runs_seats_concurrently() -> None:
    barrier = threading.Barrier(2, timeout=10)
    agents = {0: _BarrierSeat(barrier), 1: _BarrierSeat(barrier)}
    cfg = GameConfig(num_players=2, max_turns=3, seed=1, map_radius=2)
    final = play_game(agents, config=cfg, parallel_seats=True)
    assert final.is_terminal()  # completed -> the barrier released every phase


# --------------------------------------------------------------------------
# 3. Default OFF is byte-identical.
# --------------------------------------------------------------------------


def test_parallel_seats_defaults_off() -> None:
    seats = [0, 1, 2]
    seed, max_turns = 5, 3
    default = _run_harness(seats, [], seed, max_turns, parallel_seats=False)
    # A game run WITHOUT the flag at all must equal one with parallel_seats=False.
    responses = {s: _scripted_responses(s, 3, max_turns) for s in seats}
    explicit_off = harness.run_one_llm_game(
        game_id=0, seed=seed, llm_seats=seats, heuristic_names=[],
        max_turns=max_turns, llm_agent_factory=_dispatch_factory(seats, responses),
    )
    assert explicit_off[0] == default[0]  # sweep
    assert explicit_off[1] == default[1]  # telemetry


# --------------------------------------------------------------------------
# 4. Shared-state / RNG safety: non-opt-in agents are never pre-warmed.
# --------------------------------------------------------------------------


class _CountingSeat:
    """A NON-opt-in agent (no supports_parallel_prewarm). play_game must call
    its methods exactly as today -- once per phase per turn, never pre-warmed
    off-thread -- so an RNG-consuming heuristic keeps its draw order."""

    def __init__(self) -> None:
        self.press_calls = 0
        self.orders_calls = 0

    def choose_press(self, state, player):
        self.press_calls += 1
        return Press(stance={}, intents=[])

    def choose_orders(self, state, player):
        self.orders_calls += 1
        return {}

    def chat_drafts(self, state, player):
        return []


def test_non_optin_agents_are_never_prewarmed() -> None:
    agents = {0: _CountingSeat(), 1: _CountingSeat()}
    max_turns = 3
    cfg = GameConfig(num_players=2, max_turns=max_turns, seed=2, map_radius=2)
    final = play_game(agents, config=cfg, parallel_seats=True)
    # Exactly one choose_press + one choose_orders per surviving turn: no
    # pre-warm double-call. (Game ends at max_turns with all-Hold -> no
    # elimination, so both seats act every turn.)
    for a in agents.values():
        assert a.press_calls == final.turn
        assert a.orders_calls == final.turn


# --------------------------------------------------------------------------
# 5. Bounded concurrency (max_workers) -- the hot-swap "2 not 3" knob.
# --------------------------------------------------------------------------


class _ConcurrencyMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._gate = threading.Event()
        self.active = 0
        self.max_active = 0

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        # Briefly hold so overlapping calls actually coincide in time.
        self._gate.wait(0.05)

    def exit(self) -> None:
        with self._lock:
            self.active -= 1


class _MonitoredSeat:
    supports_parallel_prewarm = True

    def __init__(self, monitor: _ConcurrencyMonitor) -> None:
        self._m = monitor
        self._neg: dict = {}
        self._ord: dict = {}

    def _compute(self, cache, state, player, value):
        key = (state.turn, player)
        if key not in cache:
            self._m.enter()
            try:
                cache[key] = value
            finally:
                self._m.exit()
        return cache[key]

    def prewarm_phase(self, state, player, phase) -> None:
        if phase == "negotiate":
            self._compute(self._neg, state, player, Press(stance={}, intents=[]))
        else:
            self._compute(self._ord, state, player, {})

    def choose_press(self, state, player):
        return self._compute(self._neg, state, player, Press(stance={}, intents=[]))

    def choose_orders(self, state, player):
        return self._compute(self._ord, state, player, {})

    def chat_drafts(self, state, player):
        return []


def test_max_workers_bounds_concurrency() -> None:
    mon = _ConcurrencyMonitor()
    agents = {i: _MonitoredSeat(mon) for i in range(3)}
    cfg = GameConfig(num_players=3, max_turns=1, seed=3, map_radius=2)
    play_game(agents, config=cfg, parallel_seats=True, max_workers=1)
    assert mon.max_active == 1  # serialized by the bound, despite 3 opt-in seats


def test_default_max_workers_allows_all_seats_concurrent() -> None:
    mon = _ConcurrencyMonitor()
    agents = {i: _MonitoredSeat(mon) for i in range(3)}
    cfg = GameConfig(num_players=3, max_turns=1, seed=3, map_radius=2)
    play_game(agents, config=cfg, parallel_seats=True)  # default bound = #opt-in seats
    assert mon.max_active == 3


# --------------------------------------------------------------------------
# 6. Harness flag plumbing (env + kwarg).
# --------------------------------------------------------------------------


def _spy_parallel_flag(monkeypatch):
    """Wrap harness.play_game to capture the parallel_seats value it receives
    (still runs the real game), so plumbing is tested precisely rather than via
    outcome-equality (which holds whether or not the flag is wired)."""
    captured: dict = {}
    real = harness.play_game

    def spy(*args, **kwargs):
        captured["parallel_seats"] = kwargs.get("parallel_seats")
        return real(*args, **kwargs)

    monkeypatch.setattr(harness, "play_game", spy)
    return captured


def _run_short(seats, **kw):
    responses = {s: _scripted_responses(s, len(seats), 2) for s in seats}
    harness.run_one_llm_game(
        game_id=0, seed=9, llm_seats=seats, heuristic_names=[], max_turns=2,
        llm_agent_factory=_dispatch_factory(seats, responses), **kw,
    )


def test_run_one_llm_game_reads_env_flag(monkeypatch) -> None:
    """run_one_llm_game with parallel_seats unset (None) honors
    FOEDUS_PARALLEL_SEATS -- the seamless hot-swap integration point (the
    canonical campaign script sets the env var; its call site is unchanged)."""
    captured = _spy_parallel_flag(monkeypatch)

    monkeypatch.setenv("FOEDUS_PARALLEL_SEATS", "1")
    _run_short([0, 1])
    assert captured["parallel_seats"] is True  # env on -> parallel

    monkeypatch.delenv("FOEDUS_PARALLEL_SEATS")
    _run_short([0, 1])
    assert captured["parallel_seats"] is False  # unset -> off (default)


def test_explicit_kwarg_overrides_env(monkeypatch) -> None:
    captured = _spy_parallel_flag(monkeypatch)
    monkeypatch.setenv("FOEDUS_PARALLEL_SEATS", "1")
    _run_short([0, 1], parallel_seats=False)  # explicit False beats env=1
    assert captured["parallel_seats"] is False
    _run_short([0, 1], parallel_seats=True)
    assert captured["parallel_seats"] is True


def test_llm_diplomat_opts_into_prewarm() -> None:
    """LLMDiplomat must expose the opt-in marker + an idempotent prewarm hook
    that populates its cache without a second LLM call or duplicate log."""
    responses = [_negotiate_json(0, 2), _hold_orders_json()]
    agent = LLMDiplomat(client=StubLLMClient(responses))
    assert getattr(agent, "supports_parallel_prewarm", False) is True

    cfg = GameConfig(num_players=2, max_turns=1, seed=4, map_radius=2)
    m = generate_map(2, seed=4, map_radius=2)
    state = initial_state(cfg, m)

    agent.prewarm_phase(state, 0, "negotiate")
    assert len(agent.decision_log) == 1  # one negotiate call logged
    # The subsequent choose_* calls hit the warm cache: no new LLM call/log.
    agent.choose_press(state, 0)
    agent.choose_pacts(state, 0)
    agent.accept_pacts(state, 0)
    assert len(agent.decision_log) == 1
