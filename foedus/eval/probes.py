"""Canonical probe battery for depth eval.

Each Probe is a fixed-seat scenario. The framework runs each probe with
n=500 games (overrideable) and reports a score_diff plus engagement
counters.

Adding a probe = adding a Probe(...) entry to PROBES.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Probe:
    name: str
    """Stable identifier; used as JSON key."""
    seats: tuple[str, str, str, str]
    """Heuristic class names, one per seat. Must match keys in
    foedus.agents.heuristics.ROSTER."""
    subject_index: int
    """Which seat is the 'subject' for score_diff calculation. The
    diff is mean(scores[subject]) - mean(mean(scores[~subject]))."""
    description: str
    """One-line human description, rendered into the report."""
    config_override: dict[str, Any] = field(default_factory=dict)
    """Optional per-probe config knob overrides."""


PROBES: list[Probe] = [
    Probe(
        name="freerider_canary",
        seats=("DishonestCooperator", "Cooperator", "Cooperator", "Cooperator"),
        subject_index=0,
        description="Canary: does the freerider beat the cooperators?",
    ),
    Probe(
        name="coalition_pressure",
        seats=("GreedyHold", "AntiLeader", "AntiLeader", "AntiLeader"),
        subject_index=0,
        description="Can a coordinated coalition pressure the leader?",
    ),
    Probe(
        name="detente_lying",
        seats=("Sycophant", "Sycophant", "Sycophant", "Sycophant"),
        subject_index=0,
        description="Détente-by-lying: do all-Sycophants close peace despite breaking intents?",
    ),
    Probe(
        name="mutual_coop",
        seats=("Cooperator", "Cooperator", "Cooperator", "Cooperator"),
        subject_index=0,
        description="Do honest cooperators cooperate without an exploiter present?",
    ),
    Probe(
        name="altruism_punished",
        seats=("Cooperator", "GreedyHold", "GreedyHold", "GreedyHold"),
        subject_index=0,
        description="Cost of being the only cooperator.",
    ),
    Probe(
        name="pure_expansion",
        seats=("GreedyHold", "GreedyHold", "GreedyHold", "GreedyHold"),
        subject_index=0,
        description="Score-victory baseline; engagement floor.",
    ),
    Probe(
        name="noise_floor",
        seats=("RandomAgent", "GreedyHold", "GreedyHold", "GreedyHold"),
        subject_index=0,
        description="Sanity floor: GH should beat noise.",
    ),
    Probe(
        name="aid_asymmetry",
        seats=("TrustfulCooperator", "TrustfulCooperator", "Patron", "Patron"),
        subject_index=0,
        description="Bundle 4: pay-fairly vs subsidize-then-defect.",
    ),
]
