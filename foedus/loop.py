"""Game-loop helper: drive a complete game from a dict of agents to terminal state."""

from __future__ import annotations

from foedus.agents.base import Agent
from foedus.core import GameConfig, GameState, Order, PlayerId, UnitId
from foedus.mapgen import generate_map
from foedus.resolve import initial_state, resolve_turn


def play_game(
    agents: dict[PlayerId, Agent],
    config: GameConfig | None = None,
    state: GameState | None = None,
) -> GameState:
    """Play a complete game and return the final GameState.

    Provide either `state` (a starting GameState to continue from) or `config`
    (a fresh map will be generated from `config.seed`). At least one required.
    """
    if state is None:
        if config is None:
            raise ValueError("either `state` or `config` must be provided")
        m = generate_map(config.num_players, seed=config.seed)
        state = initial_state(config, m)

    while not state.is_terminal():
        orders_by_player: dict[PlayerId, dict[UnitId, Order]] = {}
        for player_id, agent in agents.items():
            if player_id in state.eliminated:
                continue
            orders_by_player[player_id] = agent.choose_orders(state, player_id)
        state = resolve_turn(state, orders_by_player)

    return state
