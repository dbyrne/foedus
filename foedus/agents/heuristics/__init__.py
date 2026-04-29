"""Heuristic agents for foedus."""

from __future__ import annotations

from foedus.agents.heuristics.aggressive import Aggressive
from foedus.agents.heuristics.anti_leader import AntiLeader
from foedus.agents.heuristics.bandwagon import Bandwagon
from foedus.agents.heuristics.conservative_builder import ConservativeBuilder
from foedus.agents.heuristics.cooperator import Cooperator
from foedus.agents.heuristics.defensive import Defensive
from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.agents.heuristics.opportunistic_betrayer import OpportunisticBetrayer
from foedus.agents.heuristics.random_agent import RandomAgent
from foedus.agents.heuristics.sycophant import Sycophant
from foedus.agents.heuristics.tit_for_tat import TitForTat

__all__ = [
    "Aggressive", "AntiLeader", "Bandwagon", "ConservativeBuilder",
    "Cooperator", "Defensive", "Greedy", "GreedyHold",
    "OpportunisticBetrayer", "RandomAgent", "Sycophant", "TitForTat",
]

ROSTER = {
    "Random": RandomAgent,
    "Greedy": Greedy,
    "GreedyHold": GreedyHold,
    "Defensive": Defensive,
    "Aggressive": Aggressive,
    "AntiLeader": AntiLeader,
    "Bandwagon": Bandwagon,
    "ConservativeBuilder": ConservativeBuilder,
    "Cooperator": Cooperator,
    "Sycophant": Sycophant,
    "OpportunisticBetrayer": OpportunisticBetrayer,
    "TitForTat": TitForTat,
}
