"""Heuristic agents for foedus."""

from __future__ import annotations

from foedus.agents.heuristics.aggressive import Aggressive
from foedus.agents.heuristics.anti_leader import AntiLeader
from foedus.agents.heuristics.bandwagon import Bandwagon
from foedus.agents.heuristics.conservative_builder import ConservativeBuilder
from foedus.agents.heuristics.coalition_builder import CoalitionBuilder
from foedus.agents.heuristics.cooperator import Cooperator
from foedus.agents.heuristics.opportunist import Opportunist
from foedus.agents.heuristics.defensive import Defensive
from foedus.agents.heuristics.dishonest_cooperator import DishonestCooperator
from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.agents.heuristics.late_closer import LateCloser
from foedus.agents.heuristics.opportunistic_betrayer import OpportunisticBetrayer
from foedus.agents.heuristics.patron import Patron
from foedus.agents.heuristics.random_agent import RandomAgent
from foedus.agents.heuristics.sycophant import Sycophant
from foedus.agents.heuristics.tit_for_tat import TitForTat
from foedus.agents.heuristics.trustful_cooperator import TrustfulCooperator
from foedus.agents.heuristics.value_greedy import ValueGreedy

__all__ = [
    "Aggressive", "AntiLeader", "Bandwagon", "CoalitionBuilder",
    "ConservativeBuilder", "Cooperator", "Defensive", "DishonestCooperator",
    "Greedy", "GreedyHold", "LateCloser", "Opportunist",
    "OpportunisticBetrayer", "Patron", "RandomAgent",
    "Sycophant", "TitForTat", "TrustfulCooperator", "ValueGreedy",
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
    "CoalitionBuilder": CoalitionBuilder,
    "Cooperator": Cooperator,
    "DishonestCooperator": DishonestCooperator,
    "LateCloser": LateCloser,
    "Sycophant": Sycophant,
    "Opportunist": Opportunist,
    "OpportunisticBetrayer": OpportunisticBetrayer,
    "TitForTat": TitForTat,
    "TrustfulCooperator": TrustfulCooperator,
    "Patron": Patron,
    "ValueGreedy": ValueGreedy,
}
