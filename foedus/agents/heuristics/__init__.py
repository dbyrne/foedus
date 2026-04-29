"""Heuristic agents for foedus.

Each heuristic is a single-purpose strategy implementation. They share
the foedus.agents.base.Agent Protocol (choose_orders, choose_press,
chat_drafts).

The roster is intentionally diverse so bulk simulation sweeps can
measure rock-paper-scissors dynamics, betrayal teeth, and other
depth-indicator metrics.
"""

from __future__ import annotations

from foedus.agents.heuristics.conservative_builder import ConservativeBuilder
from foedus.agents.heuristics.defensive import Defensive
from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.agents.heuristics.random_agent import RandomAgent

__all__ = [
    "ConservativeBuilder",
    "Defensive",
    "Greedy",
    "GreedyHold",
    "RandomAgent",
]

ROSTER = {
    "Random": RandomAgent,
    "Greedy": Greedy,
    "GreedyHold": GreedyHold,
    "Defensive": Defensive,
    "ConservativeBuilder": ConservativeBuilder,
}
