"""Heuristic press behavior — Bundle 3.

The heuristic baseline picks ALLY toward the active opponent with the
closest supply count (ties broken by lower pid), NEUTRAL toward all
others, no intents, no chat. See spec
docs/superpowers/specs/2026-04-28-press-driver-design.md.
"""

from __future__ import annotations

from foedus.agents.heuristic import HeuristicAgent
from foedus.core import (
    Archetype,
    GameConfig,
    GameState,
    NodeType,
    Stance,
)
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def _state_with_supply_counts(supply_counts: dict[int, int]) -> GameState:
    """Build a GameState where each player owns exactly `supply_counts[p]`
    supply nodes. Uses a real generated map; ownership is overwritten
    directly to hit the target counts.
    """
    n_players = len(supply_counts)
    cfg = GameConfig(num_players=n_players, max_turns=5, seed=42,
                     archetype=Archetype.UNIFORM)
    m = generate_map(n_players, seed=42, archetype=Archetype.UNIFORM)
    s = initial_state(cfg, m)
    # Reset all ownership to None, then assign the first N supply nodes
    # of each player to that player.
    new_owner = dict.fromkeys(s.ownership.keys(), None)
    supply_nodes = sorted(
        n for n, t in m.node_types.items()
        if t in (NodeType.HOME, NodeType.SUPPLY)
    )
    cursor = 0
    for p, count in supply_counts.items():
        for _ in range(count):
            assert cursor < len(supply_nodes), (
                f"Not enough supplies for required counts: "
                f"need {sum(supply_counts.values())}, "
                f"have {len(supply_nodes)}"
            )
            new_owner[supply_nodes[cursor]] = p
            cursor += 1
    return GameState(
        turn=s.turn, map=s.map, units=s.units, ownership=new_owner,
        scores=s.scores, eliminated=s.eliminated,
        next_unit_id=s.next_unit_id, config=s.config, log=s.log,
    )


def test_choose_press_allies_closest_supply_count() -> None:
    """ALLY toward the opponent whose supply count is nearest mine."""
    # Supplies: p0=3, p1=2, p2=5, p3=5. p0 (me) is closest to p1 (diff=1).
    s = _state_with_supply_counts({0: 3, 1: 2, 2: 5, 3: 5})
    press = HeuristicAgent().choose_press(s, 0)
    assert press.stance == {1: Stance.ALLY}
    assert press.intents == []


def test_choose_press_tiebreaks_by_lower_pid() -> None:
    """Tie on |distance|: lower pid wins."""
    # Supplies: p0=4, p1=2, p2=6, p3=1. From p0's view both p1 and p2
    # are exactly 2 away; tie-break picks p1 (lower pid).
    s = _state_with_supply_counts({0: 4, 1: 2, 2: 6, 3: 1})
    press = HeuristicAgent().choose_press(s, 0)
    assert press.stance == {1: Stance.ALLY}


def test_choose_press_empty_when_no_active_opponents() -> None:
    """If the player has no surviving opponents, return empty press."""
    s = _state_with_supply_counts({0: 4, 1: 2})
    s = GameState(
        turn=s.turn, map=s.map, units=s.units, ownership=s.ownership,
        scores=s.scores, eliminated={1},  # only p0 active
        next_unit_id=s.next_unit_id, config=s.config, log=s.log,
    )
    press = HeuristicAgent().choose_press(s, 0)
    assert press.stance == {}
    assert press.intents == []


def test_choose_press_skips_eliminated_opponents() -> None:
    """Eliminated opponents are not eligible for ALLY targeting even if
    their supply count would be closest."""
    s = _state_with_supply_counts({0: 5, 1: 5, 2: 1, 3: 1})
    s = GameState(
        turn=s.turn, map=s.map, units=s.units, ownership=s.ownership,
        scores=s.scores, eliminated={1},  # p1 closest but eliminated
        next_unit_id=s.next_unit_id, config=s.config, log=s.log,
    )
    press = HeuristicAgent().choose_press(s, 0)
    # p1 eliminated; closest active opponent is now p2 or p3 (tie); pid 2 wins.
    assert press.stance == {2: Stance.ALLY}


def test_chat_drafts_returns_empty_list() -> None:
    """Heuristics never chat."""
    s = _state_with_supply_counts({0: 1, 1: 1})
    drafts = HeuristicAgent().chat_drafts(s, 0)
    assert drafts == []
