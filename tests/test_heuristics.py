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
    OpportunisticBetrayer,
    RandomAgent,
    Sycophant,
    TitForTat,
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


def test_anti_leader_targets_lowest_pid_on_tie(state_4p):
    """At turn 0 supply counts tie; tie-break should pick the lowest pid
    opponent, which from P0's perspective is player 1."""
    p = AntiLeader().choose_press(state_4p, 0)
    assert p.stance.get(1) == Stance.HOSTILE


def test_aggressive_uses_supportmove_when_paired():
    """When two own units are both adjacent to an enemy unit on a supply,
    Aggressive must produce a (Move, SupportMove) pair, not two solo Moves."""
    from foedus.core import (
        GameConfig, GameState, Map, NodeType, SupportMove, Unit,
    )
    # 4-node line: A - B - C - D. C is a supply with an enemy unit; B and D
    # belong to player 0. A is unowned plain.
    coords = {0: (0, 0), 1: (1, 0), 2: (2, 0), 3: (3, 0)}
    edges = {
        0: frozenset({1}),
        1: frozenset({0, 2}),
        2: frozenset({1, 3}),
        3: frozenset({2}),
    }
    node_types = {
        0: NodeType.PLAIN,
        1: NodeType.PLAIN,
        2: NodeType.SUPPLY,
        3: NodeType.PLAIN,
    }
    m = Map(coords=coords, edges=edges, node_types=node_types,
            home_assignments={})
    cfg = GameConfig(num_players=2, max_turns=5, seed=0)
    units = {
        0: Unit(id=0, owner=0, location=1),  # P0 at B (adj to C)
        1: Unit(id=1, owner=0, location=3),  # P0 at D (adj to C)
        2: Unit(id=2, owner=1, location=2),  # P1 enemy at C (supply)
    }
    state = GameState(
        turn=0, map=m, units=units,
        ownership={0: None, 1: 0, 2: 1, 3: 0},
        scores={0: 0.0, 1: 0.0}, eliminated=set(),
        next_unit_id=3, config=cfg,
    )
    orders = Aggressive().choose_orders(state, 0)
    kinds = {type(orders[uid]).__name__ for uid in (0, 1)}
    assert kinds == {"Move", "SupportMove"}, \
        f"expected one Move + one SupportMove, got {orders}"
    # The SupportMove must target the other unit moving to node 2.
    sm = next(o for o in orders.values() if isinstance(o, SupportMove))
    mv_uid = next(uid for uid, o in orders.items()
                  if not isinstance(o, SupportMove))
    assert sm.target == mv_uid and sm.target_dest == 2


# ------- Sycophant -------

def test_sycophant_orders_all_legal(state_4p):
    _all_orders_legal(Sycophant, state_4p, 0)


def test_sycophant_press_allies_everyone(state_4p):
    p = Sycophant().choose_press(state_4p, 0)
    assert all(s == Stance.ALLY for s in p.stance.values())


def test_sycophant_chat_includes_cooperation_pitch(state_4p):
    drafts = Sycophant().chat_drafts(state_4p, 0)
    assert len(drafts) == 1
    assert "ally" in drafts[0].body.lower() or \
           "cooperate" in drafts[0].body.lower()


# ------- OpportunisticBetrayer -------

def test_opportunistic_betrayer_orders_all_legal(state_4p):
    _all_orders_legal(OpportunisticBetrayer, state_4p, 0)


def test_opportunistic_betrayer_press_includes_intents(state_4p):
    p = OpportunisticBetrayer().choose_press(state_4p, 0)
    assert len(p.intents) >= 1, "should declare at least one Intent"


# ------- TitForTat -------

def test_tit_for_tat_orders_all_legal(state_4p):
    _all_orders_legal(TitForTat, state_4p, 0)


def test_tit_for_tat_starts_ally_toward_all(state_4p):
    """No prior betrayals → all ally."""
    p = TitForTat().choose_press(state_4p, 0)
    assert all(s == Stance.ALLY for s in p.stance.values())


def test_tit_for_tat_retaliates_against_betrayer(state_4p):
    """If state.betrayals[player] has an entry, that betrayer becomes
    HOSTILE."""
    from foedus.core import BetrayalObservation, Hold, Intent
    agent = TitForTat()
    # Inject a fake betrayal: P1 betrayed P0.
    fake_intent = Intent(unit_id=2, declared_order=Hold(),
                         visible_to=None)
    obs = BetrayalObservation(
        turn=0, betrayer=1, intent=fake_intent,
        actual_order=Hold(),
    )
    state_4p.betrayals[0] = [obs]
    p = agent.choose_press(state_4p, 0)
    assert p.stance.get(1) == Stance.HOSTILE
    assert p.stance.get(2) == Stance.ALLY  # Other opponents unchanged
