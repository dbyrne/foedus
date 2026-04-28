"""Game-loop helper: drive a complete game from a dict of agents to terminal state."""

from __future__ import annotations

from foedus.agents.base import Agent
from foedus.core import GameConfig, GameState, Order, PlayerId, UnitId
from foedus.mapgen import generate_map
from foedus.press import (
    finalize_round,
    record_chat_message,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import initial_state


def play_game(
    agents: dict[PlayerId, Agent],
    config: GameConfig | None = None,
    state: GameState | None = None,
) -> GameState:
    """Play a complete game and return the final GameState.

    Drives each turn through the full Press v0 round flow:
    submit press tokens (from agent.choose_press),
    optionally record chat (from agent.chat_drafts),
    signal done for all survivors,
    finalize_round with the orders from agent.choose_orders.
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
        for player_id, agent in agents.items():
            if player_id in state.eliminated:
                continue
            press = agent.choose_press(state, player_id)
            state = submit_press_tokens(state, player_id, press)
            for draft in agent.chat_drafts(state, player_id):
                state = record_chat_message(state, player_id, draft)
            state = signal_done(state, player_id)

        # 2. Orders phase: collect orders from each survivor.
        orders_by_player: dict[PlayerId, dict[UnitId, Order]] = {}
        for player_id, agent in agents.items():
            if player_id in state.eliminated:
                continue
            orders_by_player[player_id] = agent.choose_orders(state, player_id)

        # 3. Finalize: locks press, runs resolution, archives, returns next-turn state.
        state = finalize_round(state, orders_by_player)

    return state
