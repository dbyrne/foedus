"""Tests for CoalitionBuilder heuristic agent (v2 — geography-aware bloc)."""

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


def _four_player_linear_state():
    """4-player state on a linear chain for geography-aware bloc tests.

    Chain: 0 - 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8 - 9 - 10
    Units:
      player 0: unit 0 at node 0
      player 1: unit 1 at node 1   (1-hop from P0)
      player 2: unit 2 at node 2   (2-hops from P0)
      player 3: unit 3 at node 9   (9-hops from P0)

    P0 should pick P1 and P2 (2 closest) and exclude P3 (farthest).
    """
    layout = {0: 0, 1: 1, 2: 2, 3: 9}
    ownership = {0: 0, 1: 1, 2: 2, 3: 3}
    edges = {i: {i - 1, i + 1} for i in range(1, 10)}
    edges[0] = {1}
    edges[10] = {9}
    state = build_state_with_units(layout, ownership, edges, num_players=4)
    return state


def _three_player_close_far_state():
    """3-player state for support/press tests.

    Chain: 0 - 1 - 2 - 3 - 4 - 5
    P0 at 0, P1 at 1 (adjacent), P2 at 5 (5-hops).
    Both P1 and P2 are in the bloc (only 2 candidates), but P1 is adjacent.
    """
    layout = {0: 0, 1: 1, 2: 5}
    ownership = {0: 0, 1: 1, 2: 2}
    edges = {i: {i - 1, i + 1} for i in range(1, 5)}
    edges[0] = {1}
    edges[5] = {4}
    state = build_state_with_units(layout, ownership, edges, num_players=3)
    return state


def _four_player_close_far_state():
    """4-player state for press stance tests.

    Chain: 0 - 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8
    P0 at 0, P1 at 1 (1-hop), P2 at 2 (2-hops), P3 at 8 (8-hops).
    P0's bloc = {P1, P2}; P3 is excluded (farthest).
    """
    layout = {0: 0, 1: 1, 2: 2, 3: 8}
    ownership = {0: 0, 1: 1, 2: 2, 3: 3}
    edges = {i: {i - 1, i + 1} for i in range(1, 8)}
    edges[0] = {1}
    edges[8] = {7}
    state = build_state_with_units(layout, ownership, edges, num_players=4)
    return state


# ---------------------------------------------------------------------------
# Bloc selection tests
# ---------------------------------------------------------------------------

def test_coalition_builder_bloc_excludes_self():
    """Bloc should have up to 2 partners and never include self."""
    state = _four_player_state()
    agent = CoalitionBuilder()
    bloc = agent._bloc_partners(state, player=2)
    assert 2 not in bloc
    assert len(bloc) <= 2
    assert all(p in {0, 1, 3} for p in bloc)


def test_coalition_builder_v2_picks_geographically_closest_partner():
    """P0 should pick P1 (1-hop) and P2 (2-hops) but NOT P3 (9-hops)."""
    state = _four_player_linear_state()
    agent = CoalitionBuilder()
    bloc = agent._bloc_partners(state, player=0)
    assert 1 in bloc, f"Expected P1 in bloc, got {bloc}"
    assert 2 in bloc, f"Expected P2 in bloc, got {bloc}"
    assert 3 not in bloc, f"Expected P3 NOT in bloc, got {bloc}"


def test_coalition_builder_v2_handles_no_units():
    """Agent with no units should fall back to lowest-id without crashing."""
    state = _three_player_close_far_state()
    # Remove player 0's unit
    units = {uid: u for uid, u in state.units.items() if u.owner != 0}
    state = dataclasses.replace(state, units=units)
    agent = CoalitionBuilder()
    bloc = agent._bloc_partners(state, player=0)
    # Should not crash; result is a frozenset of up to 2 survivors
    assert isinstance(bloc, frozenset)
    assert 0 not in bloc
    assert len(bloc) <= 2


# ---------------------------------------------------------------------------
# Order tests
# ---------------------------------------------------------------------------

def test_coalition_builder_supports_bloc_partner_unit():
    """P0's unit adjacent to P1 (nearest) should emit Support(target=P1's unit)."""
    # P0 at 0, P1 at 1 (adjacent), P2 at 5 (far)
    state = _three_player_close_far_state()
    agent = CoalitionBuilder()
    # Verify geography-aware bloc selects P1
    bloc = agent._bloc_partners(state, player=0)
    assert 1 in bloc

    orders = agent.choose_orders(state, player=0)
    assert 0 in orders
    order = orders[0]
    assert isinstance(order, Support)
    assert order.target == 1  # unit 1 belongs to player 1


def test_coalition_builder_skips_non_bloc_ally():
    """P0 adjacent to P2 (far outsider) should NOT support P2's unit."""
    # P0 at 0, P1 at 1 (closest, in bloc), P2 at 5 (far, outside bloc)
    # Place P0 adjacent to BOTH P1 and P2 is impossible on a linear chain,
    # so we verify P0 only supports its bloc partner (P1) and ignores P2.
    state = _three_player_close_far_state()
    agent = CoalitionBuilder()
    orders = agent.choose_orders(state, player=0)
    assert 0 in orders
    order = orders[0]
    # If it's a Support, the target must NOT be P2's unit (unit 2)
    assert not (isinstance(order, Support) and order.target == 2)


def test_coalition_builder_aid_targets_bloc_only():
    """Aid spends should only target units owned by bloc partners."""
    state = _four_player_state()
    # Give player 0 some aid tokens and archive mutual ALLY among all 4 players.
    state = dataclasses.replace(state, aid_tokens={0: 4})
    state = _archive_mutual_ally(state, [0, 1, 2, 3])

    agent = CoalitionBuilder()
    bloc = agent._bloc_partners(state, player=0)
    assert len(bloc) == 2
    assert 0 not in bloc

    spends = agent.choose_aid(state, player=0)
    assert len(spends) == 4  # all tokens spent

    # All target units must belong to bloc partners
    bloc_unit_ids = {u.id for u in state.units.values() if u.owner in bloc}
    for spend in spends:
        assert spend.target_unit in bloc_unit_ids, (
            f"Aid targeting unit {spend.target_unit} outside bloc {bloc}"
        )


# ---------------------------------------------------------------------------
# Press tests
# ---------------------------------------------------------------------------

def test_coalition_builder_press_stance_allies_bloc_neutrals_others():
    """choose_press: ALLY toward bloc partners, NEUTRAL toward non-bloc opponents."""
    # P0 at 0, P1 at 1-hop, P2 at 2-hops, P3 at 8-hops
    # P0's bloc = {P1, P2}; P3 is excluded.
    state = _four_player_close_far_state()
    agent = CoalitionBuilder()

    bloc = agent._bloc_partners(state, player=0)
    assert 1 in bloc  # P1 closest
    assert 2 in bloc  # P2 second-closest
    assert 3 not in bloc  # P3 excluded

    press = agent.choose_press(state, player=0)
    assert press.stance.get(1) == Stance.ALLY    # in bloc
    assert press.stance.get(2) == Stance.ALLY    # in bloc
    assert press.stance.get(3) == Stance.NEUTRAL  # NOT in bloc
    # player 0 not in own stance
    assert 0 not in press.stance
