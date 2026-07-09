"""Game-loop helper: drive a complete game from a dict of agents to terminal state."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from foedus.agents.base import Agent
from foedus.core import GameConfig, GameState, Order, PlayerId, UnitId
from foedus.mapgen import generate_map
from foedus.press import (
    accept_pact,
    finalize_round,
    propose_pact,
    record_chat_message,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import initial_state

OnTurnResolved = Callable[[GameState, "dict[PlayerId, dict[UnitId, Order]]", GameState], None]


def _prewarm_seats(
    agents: dict[PlayerId, Agent],
    state: GameState,
    phase: str,
    max_workers: int | None,
) -> None:
    """Concurrently pre-compute the `phase` decision ("negotiate"/"orders") for
    every opt-in seat from the current read-only `state` snapshot.

    Within a phase all seats answer from the SAME snapshot (Diplomacy's
    simultaneous secret orders): the negotiate view derives from
    press_history[-1] (last COMPLETED round) plus the seat's OWN pending press,
    never another seat's same-turn submission, and the orders pass reads a state
    that is not mutated between seats. So these per-seat calls are
    informationally independent and their results are identical whether computed
    from this snapshot or inline in the sequential passes below -- this only
    changes WHEN each seat's (slow, e.g. `claude -p`) call happens, never the
    order in which submit_press_tokens / finalize_round fold the results into
    state. The engine stays single-threaded.

    Only agents advertising `supports_parallel_prewarm` are touched; their
    per-(turn, player) caches make `prewarm_phase` idempotent, so the sequential
    pass returns the warmed value with no second call / duplicate log. Non-
    opt-in agents (heuristics) are never pre-warmed, keeping their invocation
    order -- and any RNG they draw -- byte-identical to the sequential default.
    """
    targets = [
        (pid, agent)
        for pid, agent in agents.items()
        if pid not in state.eliminated
        and getattr(agent, "supports_parallel_prewarm", False)
    ]
    if len(targets) <= 1:
        # 0 or 1 opt-in seat: nothing to overlap -- a pool would only add
        # latency. Compute inline, still populating the cache.
        for pid, agent in targets:
            agent.prewarm_phase(state, pid, phase)
        return
    # Concurrency requires each seat to own DISTINCT mutable state: two seats
    # sharing one agent instance -- OR two distinct instances sharing one
    # underlying LLM client (LLMDiplomat accepts an injected `client=`) -- would
    # race that state (client buffers like StubLLMClient.pop/.calls.append,
    # caches, decision_log) across threads. The shipped harness always builds one
    # instance AND one client per seat (make_client_from_env per seat), so this
    # fails loud only on future misuse rather than silently corrupting a run.
    if len({id(agent) for _, agent in targets}) != len(targets):
        raise ValueError(
            "parallel_seats requires a distinct agent instance per seat: the "
            "same object is registered for multiple seats, which would race "
            "its client/cache/decision_log under concurrency"
        )
    client_ids = [
        id(client)
        for _, agent in targets
        if (client := getattr(agent, "_client", None)) is not None
    ]
    if len(set(client_ids)) != len(client_ids):
        raise ValueError(
            "parallel_seats requires a distinct LLM client per seat: two seats "
            "share one client object, which would race its mutable buffers "
            "under concurrency (build one client per seat, e.g. via "
            "make_client_from_env)"
        )
    # Default the bound to one worker per opt-in seat. On a single-subscription
    # host a large fan-out can raise contention -- pass max_workers (e.g. 2) to
    # throttle it without changing outcomes (see FOEDUS_PARALLEL_SEATS_WORKERS).
    workers = max_workers if (max_workers and max_workers > 0) else len(targets)
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="foedus-seat"
    ) as pool:
        futures = [
            pool.submit(agent.prewarm_phase, state, pid, phase)
            for pid, agent in targets
        ]
        # Barrier: wait for all, re-raising the first submitted future's
        # exception. NB not literally identical to a sequential raise: the pool
        # joins (shutdown(wait=True)), so the OTHER seats' prewarm side effects
        # have already completed before this propagates. Benign for the intended
        # agents -- LLMDiplomat._complete isolates transport/parse failures and
        # never raises here -- and either way the game aborts.
        for fut in futures:
            fut.result()


def play_game(
    agents: dict[PlayerId, Agent],
    config: GameConfig | None = None,
    state: GameState | None = None,
    on_turn_resolved: OnTurnResolved | None = None,
    *,
    parallel_seats: bool = False,
    max_workers: int | None = None,
) -> GameState:
    """Play a complete game and return the final GameState.

    Drives each turn through the full Press v0 round flow:
    submit press tokens (from agent.choose_press),
    optionally record chat (from agent.chat_drafts),
    signal done for all survivors,
    finalize_round with the orders from agent.choose_orders.

    `on_turn_resolved`, if given, is called after each turn's finalize_round
    as `on_turn_resolved(prev_state, orders_by_player, new_state)` -- an
    optional observation hook (e.g. spectator streaming) with no effect on
    engine behavior. Default None keeps the loop byte-identical.

    `parallel_seats` (default False -> byte-identical to today): when True, the
    per-phase decisions of opt-in seats (those advertising
    `supports_parallel_prewarm`, e.g. LLMDiplomat, whose per-turn LLM call
    dominates wall-clock) are pre-computed CONCURRENTLY from a single read-only
    snapshot before each sequential pass, then the passes run unchanged against
    the warmed caches. `max_workers` bounds the concurrency (default = number of
    opt-in seats). This changes only WHEN seat calls happen; the engine's
    state folding stays single-threaded and outcomes are unchanged (see
    `_prewarm_seats`).
    """
    if state is None:
        if config is None:
            raise ValueError("either `state` or `config` must be provided")
        m = generate_map(
            config.num_players,
            seed=config.seed,
            archetype=config.archetype,
            map_radius=config.map_radius,
        )
        state = initial_state(config, m)

    while not state.is_terminal():
        # 1. Press phase: each survivor submits press, may emit chat, signals done.
        # First pass: collect press from all players in a coherent same-turn
        # snapshot (so cross-support/pact hooks can read everyone's intents).
        if parallel_seats:
            # Warm the negotiate decision for every opt-in seat from THIS
            # top-of-turn snapshot (before any submit_press_tokens mutation),
            # concurrently. The sequential passes below then hit the cache.
            _prewarm_seats(agents, state, "negotiate", max_workers)
        for player_id, agent in agents.items():
            if player_id in state.eliminated:
                continue
            press = agent.choose_press(state, player_id)
            state = submit_press_tokens(state, player_id, press)
        # F5: pact-proposal pass. Run BEFORE any acceptance so a player can
        # accept a same-round proposal (choose_pacts is optional —
        # hasattr-guarded to keep the Agent protocol minimal).
        for player_id, agent in agents.items():
            if player_id in state.eliminated:
                continue
            if not hasattr(agent, "choose_pacts"):
                continue
            for prop in agent.choose_pacts(state, player_id):
                state = propose_pact(
                    state, player_id, prop.counterparty, prop.terms
                )
        # Second pass: chat + pact acceptances + done.
        for player_id, agent in agents.items():
            if player_id in state.eliminated:
                continue
            for draft in agent.chat_drafts(state, player_id):
                state = record_chat_message(state, player_id, draft)
            if hasattr(agent, "accept_pacts"):
                for pact_id in agent.accept_pacts(state, player_id):
                    state = accept_pact(state, pact_id, player_id)
            state = signal_done(state, player_id)

        # 2. Orders phase: collect orders from each survivor.
        if parallel_seats:
            # Negotiation has closed; the orders pass reads this state unchanged
            # between seats, so warming all seats' orders from it concurrently is
            # exactly equivalent to the sequential fan-out below.
            _prewarm_seats(agents, state, "orders", max_workers)
        orders_by_player: dict[PlayerId, dict[UnitId, Order]] = {}
        for player_id, agent in agents.items():
            if player_id in state.eliminated:
                continue
            orders_by_player[player_id] = agent.choose_orders(state, player_id)

        # 3. Finalize: locks press, runs resolution, archives, returns next-turn state.
        prev_state = state
        state = finalize_round(state, orders_by_player)
        if on_turn_resolved is not None:
            on_turn_resolved(prev_state, orders_by_player, state)

    return state
