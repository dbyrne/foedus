"""Tests for CoalitionBuilder heuristic agent."""

from __future__ import annotations

import dataclasses

import pytest

from foedus.agents.heuristics.coalition_builder import CoalitionBuilder
from foedus.core import (
    AidSpend,
    Hold,
    Move,
    Press,
    Stance,
    Support,
    Unit,
)
from tests.helpers import build_state_with_units, make_state, triangle_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _four_player_state():
    """4-player state on a small graph.

    Nodes 0-7; units for each player:
      player 0: unit 0 at node 0
      player 1: unit 1 at node 2
      player 2: unit 2 at node 4
      player 3: unit 3 at node 6

    Edges form two adjacent pairs per player so there's adjacency to check.
    """
    layout = {0: 0, 1: 2, 2: 4, 3: 6}
    ownership = {0: 0, 1: 1, 2: 2, 3: 3}
    edges = {
        0: {1, 2},
        1: {0, 3},
        2: {0, 3, 4},
        3: {1, 2, 5},
        4: {2, 5, 6},
        5: {3, 4, 7},
        6: {4, 7},
        7: {5, 6},
    }
    state = build_state_with_units(layout, ownership, edges, num_players=4)
    return state


def _archive_mutual_ally(state, players):
    """Append a fake press_history entry with mutual ALLY among all named players."""
    entry = {}
    for p in players:
        stance = {q: Stance.ALLY for q in players if q != p}
        entry[p] = Press(stance=stance, intents=[])
    new_history = list(state.press_history) + [entry]
    return dataclasses.replace(state, press_history=new_history)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_coalition_builder_bloc_excludes_self():
    """4-player state, player=2. Bloc should be {0, 1} (2 lowest-id non-self)."""
    state = _four_player_state()
    agent = CoalitionBuilder()
    bloc = agent._bloc_partners(state, player=2)
    assert bloc == frozenset({0, 1})


def test_coalition_builder_bloc_player3():
    """4-player state, player=3. Bloc should be {0, 1}."""
    state = _four_player_state()
    agent = CoalitionBuilder()
    bloc = agent._bloc_partners(state, player=3)
    assert bloc == frozenset({0, 1})


def test_coalition_builder_supports_bloc_partner_unit():
    """Own unit adjacent to a bloc partner's unit should emit Support(target=partner_unit)."""
    # player=2, bloc={0,1}. Place unit 2 (player 2) at node 2 (adjacent to node 0
    # where player 0's unit 0 lives, which is in bloc).
    layout = {0: 0, 1: 5, 2: 1}  # unit 0 (p0) at 0, unit 1 (p1) at 5, unit 2 (p2) at 1
    ownership = {0: 0, 1: 1, 2: 2}
    edges = {
        0: {1, 2},
        1: {0, 3},
        2: {0, 3},
        3: {1, 2, 4},
        4: {3, 5},
        5: {4},
    }
    state = build_state_with_units(layout, ownership, edges, num_players=3)
    agent = CoalitionBuilder()
    # player=2, bloc = {0,1} (lowest-id non-self survivors)
    orders = agent.choose_orders(state, player=2)
    # unit 2 at node 1 is adjacent to node 0 (unit 0 of player 0, a bloc member)
    assert 2 in orders
    order = orders[2]
    assert isinstance(order, Support)
    assert order.target == 0  # unit 0 belongs to player 0 (in bloc)


def test_coalition_builder_skips_non_bloc_ally():
    """Own unit adjacent to non-bloc player's unit should NOT emit Support for them."""
    # player=3, bloc={0,1}. Only unit adjacent to player=2's unit (not in bloc).
    layout = {0: 0, 1: 2, 2: 4, 3: 3}
    ownership = {0: 0, 1: 1, 2: 2, 3: 3}
    edges = {
        0: {1},
        1: {0, 2},
        2: {1, 3},
        3: {2, 4},
        4: {3},
    }
    state = build_state_with_units(layout, ownership, edges, num_players=4)
    agent = CoalitionBuilder()
    # player=3, bloc={0,1}. Unit 3 at node 3, adjacent to node 2 (player 2, NOT in bloc)
    # and node 4 (empty). No bloc units in range → should fall back to GreedyHold.
    orders = agent.choose_orders(state, player=3)
    assert 3 in orders
    # Should NOT be a Support targeting player 2's unit (unit 2)
    order = orders[3]
    assert not (isinstance(order, Support) and order.target == 2)


def test_coalition_builder_aid_targets_bloc_only():
    """Aid spends should only target units owned by bloc partners."""
    state = _four_player_state()
    # Give player 0 some aid tokens and archive mutual ALLY among all 4 players.
    state = dataclasses.replace(state, aid_tokens={0: 4})
    state = _archive_mutual_ally(state, [0, 1, 2, 3])

    agent = CoalitionBuilder()
    # player=0, bloc={1,2}
    bloc = agent._bloc_partners(state, player=0)
    assert bloc == frozenset({1, 2})

    spends = agent.choose_aid(state, player=0)
    assert len(spends) == 4  # all tokens spent

    # All target units must belong to bloc partners {1, 2}
    bloc_unit_ids = {u.id for u in state.units.values() if u.owner in bloc}
    for spend in spends:
        assert spend.target_unit in bloc_unit_ids, (
            f"Aid targeting unit {spend.target_unit} outside bloc {bloc}"
        )


def test_coalition_builder_press_stance_allies_bloc_neutrals_others():
    """choose_press: ALLY toward bloc partners, NEUTRAL toward non-bloc opponents."""
    state = _four_player_state()
    agent = CoalitionBuilder()

    # player=1, bloc={0,2} (lowest-id non-self non-eliminated)
    press = agent.choose_press(state, player=1)
    bloc = agent._bloc_partners(state, player=1)
    assert bloc == frozenset({0, 2})

    assert press.stance.get(0) == Stance.ALLY   # in bloc
    assert press.stance.get(2) == Stance.ALLY   # in bloc
    assert press.stance.get(3) == Stance.NEUTRAL  # NOT in bloc
    # player 1 not in own stance
    assert 1 not in press.stance
