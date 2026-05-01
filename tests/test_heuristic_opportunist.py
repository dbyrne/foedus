"""Unit tests for the Opportunist heuristic agent."""

from __future__ import annotations

import pytest

from foedus.agents.heuristics.opportunist import Opportunist
from foedus.core import (
    Hold, Move, Press, Stance, Support, Unit,
)
from foedus.legal import legal_orders_for_unit
from tests.helpers import build_state_with_units


# ---------------------------------------------------------------------------
# Test 1: emits Support when own unit is directly adjacent to an ally unit
# ---------------------------------------------------------------------------

def test_opportunist_emits_support_for_adjacent_ally():
    """Unit 0 (player 0) at node 0; Unit 1 (player 1) at node 1; edge 0-1.
    Unit 0 is adjacent to unit 1 → expect Support(target=1).
    """
    state = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1}, 1: {0}},
        num_players=2,
    )
    agent = Opportunist()
    orders = agent.choose_orders(state, player=0)
    assert 0 in orders
    assert isinstance(orders[0], Support), f"expected Support, got {orders[0]}"
    assert orders[0].target == 1


# ---------------------------------------------------------------------------
# Test 2: emits Support when own unit shares a neighbor with ally unit
# (ally one hop away — supports a potential Move from the ally)
# ---------------------------------------------------------------------------

def test_opportunist_emits_support_for_reachable_ally():
    """Three nodes in a line: 0 - 1 - 2.
    Unit 0 (player 0) at node 0; Unit 1 (player 1) at node 2.
    Node 0 and node 2 both neighbor node 1 → they share a neighbor.
    Opportunist should emit Support(target=1) for unit 0.
    """
    state = build_state_with_units(
        layout={0: 0, 1: 2},
        ownership={0: 0, 1: 1},
        edges={0: {1}, 1: {0, 2}, 2: {1}},
        num_players=2,
    )
    agent = Opportunist()
    orders = agent.choose_orders(state, player=0)
    assert 0 in orders
    assert isinstance(orders[0], Support), f"expected Support, got {orders[0]}"
    assert orders[0].target == 1


# ---------------------------------------------------------------------------
# Test 3: skips freeriders via leverage gate
# ---------------------------------------------------------------------------

def test_opportunist_skips_freeriders_via_leverage_gate():
    """Unit 0 (player 0) at node 0; Unit 1 (player 1) at node 1; edge 0-1.
    Player 0 has given 3 tokens to player 1, who has given 0 back.
    leverage(0, 1) = 3 > 1  →  freerider gate fires, no Support emitted.
    Expected: fallback Hold/Move order, NOT Support.
    """
    state = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1}, 1: {0}},
        num_players=2,
    )
    # Inject a leverage imbalance: player 0 has given 3 tokens to player 1.
    import dataclasses
    state = dataclasses.replace(
        state,
        aid_given={(0, 1): 3},
    )
    assert state.leverage(0, 1) == 3  # sanity
    agent = Opportunist()
    orders = agent.choose_orders(state, player=0)
    assert 0 in orders
    assert not isinstance(orders[0], Support), (
        f"expected fallback (Hold/Move), got Support: {orders[0]}"
    )


# ---------------------------------------------------------------------------
# Test 4: falls back to GreedyHold when no ally is geometrically reachable
# ---------------------------------------------------------------------------

def test_opportunist_falls_back_to_greedyhold_when_no_ally_reachable():
    """Three nodes in a line: 0 - 1 - 2.
    Unit 0 (player 0) at node 0; Unit 1 (player 1) at node 2.
    Node 1 is a SUPPLY node. Edge 0-1 and 1-2 only.
    Unit 0 cannot reach unit 1 geometrically: neighbors(0)={1},
    neighbors(2)={1} → they DO share neighbor 1.

    To force NO reachability, put ally far away without shared neighbors.
    Use 4-node line: 0 - 1 - 2 - 3.  Unit 0 at 0, unit 1 at 3.
    neighbors(0)={1}, neighbors(3)={2}.  Intersection = {} → not reachable.
    """
    state = build_state_with_units(
        layout={0: 0, 1: 3},
        ownership={0: 0, 1: 1},
        edges={0: {1}, 1: {0, 2}, 2: {1, 3}, 3: {2}},
        num_players=2,
    )
    # Verify not legally reachable.
    legal = legal_orders_for_unit(state, 0)
    support_orders = [o for o in legal if isinstance(o, Support)]
    assert not support_orders, "test precondition: unit 0 should have no legal Supports"

    agent = Opportunist()
    orders = agent.choose_orders(state, player=0)
    assert 0 in orders
    assert not isinstance(orders[0], Support), (
        f"expected GreedyHold fallback, got {orders[0]}"
    )
    assert isinstance(orders[0], (Hold, Move))


# ---------------------------------------------------------------------------
# Test 5: press includes ALLY stance toward all opponents + Move intents
# ---------------------------------------------------------------------------

def test_opportunist_press_includes_ally_stance_and_public_intents():
    """Unit 0 (player 0) at node 0. Two supply nodes adjacent.
    Press should declare ALLY toward all opponents AND include a Move intent
    for any unit GreedyHold plans to move.

    We use a 3-node line: 0 (HOME p0) - 1 (SUPPLY, unowned) - 2 (HOME p1).
    Player 0's unit 0 is at node 0. GreedyHold should want to move to node 1
    (adjacent unowned supply).
    """
    from foedus.core import NodeType
    from tests.helpers import make_state, line_map

    m = line_map(3)
    u0 = Unit(id=0, owner=0, location=0)
    u1 = Unit(id=1, owner=1, location=2)
    state = make_state(m, [u0, u1], num_players=2)

    agent = Opportunist()
    press = agent.choose_press(state, player=0)

    assert isinstance(press, Press)
    # Must declare ALLY toward player 1.
    assert press.stance.get(1) == Stance.ALLY, (
        f"expected ALLY toward player 1, got {press.stance.get(1)}"
    )
    # If GreedyHold plans a Move, it must be in intents.
    from foedus.agents.heuristics.greedy_hold import GreedyHold
    gh_orders = GreedyHold().choose_orders(state, player=0)
    planned_moves = {uid for uid, o in gh_orders.items() if isinstance(o, Move)}
    intent_unit_ids = {i.unit_id for i in press.intents}
    # All planned moves should appear as intents.
    assert planned_moves <= intent_unit_ids, (
        f"GreedyHold moves {planned_moves} not all in intents {intent_unit_ids}"
    )
