"""Bundle 7 — unit tests for the heuristic roster.

Each heuristic gets verified against a small synthetic state. We check:
- choose_orders returns one Order per owned unit
- All orders are LEGAL (in legal_orders_for_unit's list)
- choose_press returns a Press
- chat_drafts returns a list

Plus heuristic-specific spec checks (e.g. Defensive never moves away from
owned supplies; GreedyHold holds when on unowned supply).
"""

from __future__ import annotations

import pytest

from foedus.agents.heuristics import (
    Aggressive,
    AntiLeader,
    Bandwagon,
    ConservativeBuilder,
    Defensive,
    Greedy,
    GreedyHold,
    RandomAgent,
)
from foedus.core import GameConfig, Hold, Move, Press, Stance, Unit
from foedus.legal import legal_orders_for_unit
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


@pytest.fixture
def state_4p():
    """4-player CONTINENTAL_SWEEP state at turn 0."""
    cfg = GameConfig(num_players=4, max_turns=15, seed=42)
    m = generate_map(4, seed=42)
    return initial_state(cfg, m)


def _all_orders_legal(agent_cls, state, player):
    agent = agent_cls() if agent_cls is not RandomAgent else agent_cls(seed=1)
    orders = agent.choose_orders(state, player)
    owned = [u for u in state.units.values() if u.owner == player]
    assert set(orders.keys()) == {u.id for u in owned}, \
        f"expected one order per owned unit"
    for uid, order in orders.items():
        legal = legal_orders_for_unit(state, uid)
        assert order in legal, \
            f"{agent_cls.__name__} produced illegal order {order} for u{uid}"


# ------- Random + Greedy (existing, regression) -------

def test_random_orders_all_legal(state_4p):
    _all_orders_legal(RandomAgent, state_4p, 0)


def test_greedy_orders_all_legal(state_4p):
    _all_orders_legal(Greedy, state_4p, 0)


def test_greedy_press_returns_press(state_4p):
    p = Greedy().choose_press(state_4p, 0)
    assert isinstance(p, Press)


# ------- GreedyHold -------

def test_greedy_hold_orders_all_legal(state_4p):
    _all_orders_legal(GreedyHold, state_4p, 0)


def test_greedy_hold_holds_on_unowned_supply(state_4p):
    """If a player's unit is on a supply they don't yet own, GreedyHold
    must Hold (to flip via rule b), not Move away."""
    # Place P0's u0 manually onto an unowned supply (using mutation since
    # GameState is mutable for this kind of test setup). Find an unowned
    # supply node.
    from foedus.core import NodeType
    unowned_supplies = [
        n for n, t in state_4p.map.node_types.items()
        if t in (NodeType.SUPPLY, NodeType.HOME)
        and state_4p.ownership.get(n) is None
    ]
    assert unowned_supplies, "test fixture has no unowned supplies"
    target = unowned_supplies[0]
    # Move u0 to target via direct mutation.
    u0 = state_4p.units[0]
    new_unit = Unit(id=u0.id, owner=u0.owner, location=target)
    state_4p.units[0] = new_unit
    orders = GreedyHold().choose_orders(state_4p, 0)
    assert orders[0] == Hold(), \
        f"GreedyHold should Hold on unowned supply, got {orders[0]}"


# ------- Defensive -------

def test_defensive_orders_all_legal(state_4p):
    _all_orders_legal(Defensive, state_4p, 0)


def test_defensive_holds_when_on_supply(state_4p):
    """Defensive on home (a supply) holds — never advances."""
    orders = Defensive().choose_orders(state_4p, 0)
    u0 = state_4p.units[0]
    assert orders[0] == Hold(), \
        f"Defensive should Hold on home, got {orders[0]}"


# ------- ConservativeBuilder -------

def test_conservative_builder_orders_all_legal(state_4p):
    _all_orders_legal(ConservativeBuilder, state_4p, 0)


def test_conservative_builder_holds_on_initial_state(state_4p):
    """At turn 0 each player only has 1 unit at home with adjacent
    supplies. ConservativeBuilder might Move OR Hold — either is
    acceptable. The strict invariant is that it never Moves away from
    owned territory by more than one hop."""
    orders = ConservativeBuilder().choose_orders(state_4p, 0)
    u0 = state_4p.units[0]
    order = orders[0]
    # Either Hold or Move to an adjacent node.
    assert isinstance(order, (Hold, Move))
    if isinstance(order, Move):
        assert order.dest in state_4p.map.neighbors(u0.location), \
            f"ConservativeBuilder moved to non-adjacent node {order.dest}"


# ------- choose_press / chat_drafts smoke tests for new heuristics -------

def test_greedy_hold_press_returns_press(state_4p):
    assert isinstance(GreedyHold().choose_press(state_4p, 0), Press)


def test_greedy_hold_chat_drafts_is_list(state_4p):
    assert GreedyHold().chat_drafts(state_4p, 0) == []


def test_defensive_press_returns_press(state_4p):
    assert isinstance(Defensive().choose_press(state_4p, 0), Press)


def test_defensive_chat_drafts_is_list(state_4p):
    assert Defensive().chat_drafts(state_4p, 0) == []


def test_conservative_builder_press_returns_press(state_4p):
    assert isinstance(ConservativeBuilder().choose_press(state_4p, 0), Press)


def test_conservative_builder_chat_drafts_is_list(state_4p):
    assert ConservativeBuilder().chat_drafts(state_4p, 0) == []


# ------- Aggressive -------

def test_aggressive_orders_all_legal(state_4p):
    _all_orders_legal(Aggressive, state_4p, 0)


def test_aggressive_press_is_hostile(state_4p):
    p = Aggressive().choose_press(state_4p, 0)
    assert all(s == Stance.HOSTILE for s in p.stance.values()), \
        f"Aggressive should declare HOSTILE toward all opponents"


# ------- AntiLeader -------

def test_anti_leader_orders_all_legal(state_4p):
    _all_orders_legal(AntiLeader, state_4p, 0)


def test_anti_leader_press_targets_leader(state_4p):
    """At turn 0 all players have equal supplies; AntiLeader picks the
    lowest-pid opponent (tie-break)."""
    p = AntiLeader().choose_press(state_4p, 0)
    # Should declare HOSTILE toward exactly one opponent.
    assert sum(1 for s in p.stance.values() if s == Stance.HOSTILE) == 1


# ------- Bandwagon -------

def test_bandwagon_orders_all_legal(state_4p):
    _all_orders_legal(Bandwagon, state_4p, 0)


def test_bandwagon_press_allies_everyone(state_4p):
    p = Bandwagon().choose_press(state_4p, 0)
    assert all(s == Stance.ALLY for s in p.stance.values())
    # Should have 3 entries (3 opponents in 4-player game).
    assert len(p.stance) == 3
