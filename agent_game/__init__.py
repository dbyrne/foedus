"""Lightweight Diplomacy-inspired multi-agent strategy game.

A sandbox for training neural networks in a search-resistant multi-agent setting.
"""

from agent_game.agents.base import Agent
from agent_game.agents.random_agent import RandomAgent
from agent_game.core import (
    GameConfig,
    GameState,
    Hold,
    Map,
    Move,
    NodeId,
    NodeType,
    Order,
    PlayerId,
    SupportHold,
    SupportMove,
    Unit,
    UnitId,
)
from agent_game.fog import visible_state_for
from agent_game.legal import legal_orders_for_unit
from agent_game.loop import play_game
from agent_game.mapgen import generate_map
from agent_game.resolve import initial_state, resolve_turn

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "GameConfig",
    "GameState",
    "Hold",
    "Map",
    "Move",
    "NodeId",
    "NodeType",
    "Order",
    "PlayerId",
    "RandomAgent",
    "SupportHold",
    "SupportMove",
    "Unit",
    "UnitId",
    "generate_map",
    "initial_state",
    "legal_orders_for_unit",
    "play_game",
    "resolve_turn",
    "visible_state_for",
]
