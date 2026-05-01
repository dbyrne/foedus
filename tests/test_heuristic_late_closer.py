"""Tests for LateCloser heuristic agent."""

from __future__ import annotations

from dataclasses import replace

import pytest

from foedus.agents.heuristics.late_closer import LateCloser
from foedus.core import (
    BetrayalObservation,
    GameState,
    Hold,
    Intent,
    Move,
    NodeType,
    Press,
    Stance,
    Support,
    Unit,
)
from foedus.press import finalize_round, signal_done, submit_press_tokens
from tests.helpers import build_state_with_units, line_map, make_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _supply_map_state():
    """4 nodes in a line: 0-1-2-3.
    Node 0: HOME P0 (unit 0 here)
    Node 1: SUPPLY (unowned)
    Node 2: SUPPLY (unowned, adjacent to 1 and 3)
    Node 3: HOME P1 (unit 1 here)
    """
    m = line_map(4)
    # line_map already sets endpoints as HOME, interior as SUPPLY.
    # Unit 0 owned by player 0 at node 0; Unit 1 owned by player 1 at node 3.
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 3)], num_players=2, max_turns=20)
    return s


# ---------------------------------------------------------------------------
# Test 1: pinned Support when ally intent is visible
# ---------------------------------------------------------------------------

def test_late_closer_emits_pinned_support_when_ally_intent_visible():
    """P1 has submitted an intent: unit 1 moves to supply node 1.
    P0's unit 0 is at node 0, adjacent to node 1.
    Expect P0 to emit Support(target=1, require_dest=1).
    """
    s = _supply_map_state()
    # Node 1 is a supply; it's adjacent to node 0 (P0's unit location).
    # Simulate P1 having submitted press with intent to move unit 1 to node 2
    # (node 2 is a supply adjacent to node 3 where unit 1 lives).
    # For P0's adjacency: we need unit 0 (at node 0) adjacent to dest.
    # Node 1 is adjacent to node 0. So we need P1 to declare intent to move
    # unit 1 to node 1. Unit 1 is at node 3; node 1 is not adjacent to node 3.
    # So let's use a different layout: put ally unit adjacent to the supply.
    #
    # Simpler layout: 3 nodes 0-1-2.
    # P0 unit at node 0, P1 unit at node 2. Node 1 is supply.
    # P1 declares intent: unit at 2 moves to 1. P0 adjacent to 1.
    # P0 should emit Support(target=P1_unit, require_dest=1).
    from tests.helpers import make_state
    from foedus.core import Map, GameConfig

    # 3-node line: 0-1-2
    coords = {0: (0, 0), 1: (1, 0), 2: (2, 0)}
    edges = {0: frozenset({1}), 1: frozenset({0, 2}), 2: frozenset({1})}
    node_types = {0: NodeType.HOME, 1: NodeType.SUPPLY, 2: NodeType.HOME}
    m = make_state(
        Map(coords=coords, edges=edges, node_types=node_types,
            home_assignments={0: 0, 2: 1}),
        [Unit(0, 0, 0), Unit(1, 1, 2)],
        num_players=2, max_turns=20,
    )
    state = m

    # P1 submits intent: unit 1 moves to node 1 (supply)
    intent = Intent(unit_id=1, declared_order=Move(dest=1), visible_to=None)
    press = Press(stance={0: Stance.ALLY}, intents=[intent])
    state.round_press_pending[1] = press

    agent = LateCloser()
    orders = agent.choose_orders(state, player=0)

    # Unit 0 (at node 0) is adjacent to node 1 and should issue pinned support.
    assert 0 in orders
    order = orders[0]
    assert isinstance(order, Support), f"Expected Support, got {order}"
    assert order.target == 1
    assert order.require_dest == 1


# ---------------------------------------------------------------------------
# Test 2: falls back to Greedy (Move) without visible intents
# ---------------------------------------------------------------------------

def test_late_closer_falls_back_to_greedy_without_visible_intents():
    """No other player has submitted press; expect a Move toward unowned supply."""
    s = _supply_map_state()
    # P0's unit 0 is at node 0. Adjacent supply is node 1 (unowned).
    agent = LateCloser()
    orders = agent.choose_orders(s, player=0)

    assert 0 in orders
    order = orders[0]
    # Greedy will Move toward nearest unowned supply (node 1).
    assert isinstance(order, Move), f"Expected Move fallback, got {order}"


# ---------------------------------------------------------------------------
# Test 3: declared intents are deliberately deceptive
# ---------------------------------------------------------------------------

def test_late_closer_declares_deceptive_intents():
    """choose_press should return intents whose declared Move destination differs
    from what choose_orders would choose for the same unit.

    Layout: star graph. Central node 10 (P0's unit) connects to:
      - node 11: SUPPLY (many onward supply neighbors → Greedy picks this)
      - node 12: PLAIN  (no further supplies → "worst" neighbor)
      - node 13: SUPPLY (one onward supply neighbor)
    Node 11 also connects to nodes 14 and 15 (both SUPPLY, unowned).
    This gives node 11 a higher "onward supply" count than node 12/13,
    so Greedy moves to 11 but worst_neighbor picks 12.
    """
    from foedus.core import Map, GameConfig

    coords = {n: (n, 0) for n in range(16)}
    edges = {
        10: frozenset({11, 12, 13}),
        11: frozenset({10, 14, 15}),
        12: frozenset({10}),
        13: frozenset({10}),
        14: frozenset({11}),
        15: frozenset({11}),
        # Enemy home far away
        99: frozenset(),
    }
    # Fill missing nodes
    for n in range(16):
        edges.setdefault(n, frozenset())
    node_types = {n: NodeType.PLAIN for n in range(16)}
    node_types[10] = NodeType.HOME   # P0 home
    node_types[11] = NodeType.SUPPLY
    node_types[13] = NodeType.SUPPLY
    node_types[14] = NodeType.SUPPLY
    node_types[15] = NodeType.SUPPLY
    # P1 home somewhere disconnected
    node_types.setdefault(0, NodeType.HOME)

    home_assignments = {10: 0, 0: 1}
    all_nodes = set(range(16)) | {0}
    coords = {n: (n, 0) for n in all_nodes}
    edge_map = {n: frozenset(edges.get(n, set())) for n in all_nodes}
    nt = {n: node_types.get(n, NodeType.PLAIN) for n in all_nodes}

    from foedus.core import Map
    m = Map(coords=coords, edges=edge_map, node_types=nt,
            home_assignments=home_assignments)
    s = make_state(m, [Unit(0, 0, 10), Unit(1, 1, 0)], num_players=2, max_turns=20)

    agent = LateCloser()
    press = agent.choose_press(s, player=0)
    orders = agent.choose_orders(s, player=0)

    unit0_intents = [i for i in press.intents if i.unit_id == 0]
    assert unit0_intents, "Expected at least one declared intent for unit 0"

    actual_order = orders.get(0)
    declared_dest = unit0_intents[0].declared_order.dest
    # Greedy should move to 11 (richest neighbor); worst_neighbor is 12 (PLAIN, no supplies).
    assert isinstance(actual_order, Move), f"Expected Move, got {actual_order}"
    assert declared_dest != actual_order.dest, (
        f"Deceptive intent dest {declared_dest} should differ from actual "
        f"order dest {actual_order.dest}"
    )


# ---------------------------------------------------------------------------
# Test 4: aid spends on visible ally Move to supply with mutual-ALLY history
# ---------------------------------------------------------------------------

def test_late_closer_aid_spends_on_visible_ally_move_to_supply():
    """With mutual-ALLY in press_history and a visible Move-on-supply intent,
    LateCloser should emit at least one AidSpend.
    """
    s = _supply_map_state()

    # Give P0 aid tokens.
    s = replace(s, aid_tokens={0: 3})

    # Archive a mutual-ALLY press_history entry.
    hist_entry = {
        0: Press(stance={1: Stance.ALLY}, intents=[]),
        1: Press(stance={0: Stance.ALLY}, intents=[]),
    }
    s = replace(s, press_history=[hist_entry])

    # P1 submits intent to move to supply node 2 (adjacent to node 3 where unit 1 is).
    # Node 2 is a supply (interior of line_map(4)).
    intent = Intent(unit_id=1, declared_order=Move(dest=2), visible_to=None)
    press = Press(stance={0: Stance.ALLY}, intents=[intent])
    s.round_press_pending[1] = press

    agent = LateCloser()
    spends = agent.choose_aid(s, player=0)

    assert len(spends) >= 1, f"Expected at least one AidSpend, got {spends}"
    from foedus.core import AidSpend
    assert all(isinstance(sp, AidSpend) for sp in spends)
    assert spends[0].target_unit == 1


# ---------------------------------------------------------------------------
# Test 5: BetrayalObservation fires for LateCloser's deceptive intents
# ---------------------------------------------------------------------------

def test_late_closer_betrayal_observation_fires():
    """Full round-trip: LateCloser submits deceptive press then plays actual
    (different) orders. finalize_round should record BetrayalObservation.

    Uses the same star layout as test 3 to guarantee the deceptive intent
    destination (worst neighbor = node 12, PLAIN) differs from the actual
    greedy move (node 11, SUPPLY-rich).
    """
    from foedus.core import Map

    all_nodes = set(range(16)) | {0}
    coords = {n: (n, 0) for n in all_nodes}
    edges_raw = {
        10: frozenset({11, 12, 13}),
        11: frozenset({10, 14, 15}),
        12: frozenset({10}),
        13: frozenset({10}),
        14: frozenset({11}),
        15: frozenset({11}),
    }
    edge_map = {n: frozenset(edges_raw.get(n, set())) for n in all_nodes}
    nt = {n: NodeType.PLAIN for n in all_nodes}
    nt[10] = NodeType.HOME
    nt[11] = NodeType.SUPPLY
    nt[13] = NodeType.SUPPLY
    nt[14] = NodeType.SUPPLY
    nt[15] = NodeType.SUPPLY
    nt[0] = NodeType.HOME

    m = Map(coords=coords, edges=edge_map, node_types=nt,
            home_assignments={10: 0, 0: 1})
    s = make_state(m, [Unit(0, 0, 10), Unit(1, 1, 0)], num_players=2, max_turns=20)

    agent = LateCloser()
    press = agent.choose_press(s, player=0)
    actual_orders = agent.choose_orders(s, player=0)

    unit0_intents = [i for i in press.intents if i.unit_id == 0]
    assert unit0_intents, "Star layout should produce a deceptive intent for unit 0"
    actual_0 = actual_orders.get(0)
    declared_dest = unit0_intents[0].declared_order.dest
    assert isinstance(actual_0, Move)
    assert declared_dest != actual_0.dest, "Star layout should produce diverging intent/order"

    # Submit press for P0 (deceptive intents), neutral press for P1, signal done.
    s = submit_press_tokens(s, 0, press)
    s = submit_press_tokens(s, 1, Press(stance={}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)

    p1_orders = {1: Hold()}
    final_state = finalize_round(s, {0: actual_orders, 1: p1_orders})

    # The public intent was declared visible_to=None, so P1 observes the betrayal.
    all_betrayals = [
        obs
        for obs_list in final_state.betrayals.values()
        for obs in obs_list
        if obs.betrayer == 0 and obs.intent.unit_id == 0
    ]
    assert all_betrayals, (
        f"Expected BetrayalObservation for LateCloser's unit 0. "
        f"betrayals dict: {final_state.betrayals}"
    )
