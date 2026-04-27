"""Lightweight Diplomacy-inspired multi-agent strategy game.

A sandbox for training neural networks in a search-resistant multi-agent setting.
"""

from foedus.agents.base import Agent
from foedus.agents.heuristic import HeuristicAgent
from foedus.agents.random_agent import RandomAgent
from foedus.core import (
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
from foedus.fog import visible_state_for
from foedus.legal import legal_orders_for_unit
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import initial_state, resolve_turn
from foedus.scoring import MatchResult, compute_match_result

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "GameConfig",
    "GameState",
    "HeuristicAgent",
    "Hold",
    "Map",
    "MatchResult",
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
    "compute_match_result",
    "generate_map",
    "initial_state",
    "legal_orders_for_unit",
    "play_game",
    "resolve_turn",
    "visible_state_for",
]
