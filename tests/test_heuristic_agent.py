"""Tests for HeuristicAgent.

Two layers:
1. Unit tests of the strategy itself — moves toward unowned supply, holds
   when blocked, returns legal orders.
2. A statistical validation tournament: HeuristicAgent should reliably
   beat RandomAgent over many games.
"""

from __future__ import annotations

from foedus.agents.base import Agent
from foedus.agents.heuristic import HeuristicAgent
from foedus.agents.random_agent import RandomAgent
from foedus.core import GameConfig, Hold, Move, Unit
from foedus.legal import legal_orders_for_unit
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import initial_state
from foedus.scoring import compute_match_result

from tests.helpers import line_map, make_state


def test_heuristic_implements_protocol() -> None:
    assert isinstance(HeuristicAgent(), Agent)


def test_heuristic_only_orders_own_units() -> None:
    cfg = GameConfig(num_players=4, seed=42, max_turns=10, peace_threshold=99)
    m = generate_map(4, seed=42)
    state = initial_state(cfg, m)
    orders = HeuristicAgent().choose_orders(state, player=0)
    own = {u.id for u in state.units.values() if u.owner == 0}
    assert set(orders.keys()) == own


def test_heuristic_returns_legal_orders() -> None:
    cfg = GameConfig(num_players=4, seed=42, max_turns=10, peace_threshold=99)
    m = generate_map(4, seed=42)
    state = initial_state(cfg, m)
    orders = HeuristicAgent().choose_orders(state, player=0)
    for unit_id, order in orders.items():
        assert order in legal_orders_for_unit(state, unit_id)


def test_heuristic_moves_toward_adjacent_supply() -> None:
    """On a line map with adjacent unowned supply, the agent should move into it."""
    m = line_map(5)  # 0-1-2-3-4; nodes 1-3 are SUPPLY (interior)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, peace_threshold=0)
    orders = HeuristicAgent().choose_orders(s, player=0)
    # Node 0 owned by p0; node 1 is unowned SUPPLY adjacent to u0.
    assert orders[0] == Move(dest=1)


def test_heuristic_steps_toward_distant_supply() -> None:
    """When target supply is several hops away, the agent should advance one step."""
    m = line_map(5)
    # Place unit at node 0; pretend everything between is owned by us so the
    # nearest unowned supply is at node 4 (which is HOME, but counts as supply).
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, peace_threshold=0)
    s.ownership[1] = 0  # 'we' own node 1 already
    s.ownership[2] = 0
    s.ownership[3] = 0
    # Now nearest unowned supply should be node 4. u0 should step to node 1.
    orders = HeuristicAgent().choose_orders(s, player=0)
    assert orders[0] == Move(dest=1)


def test_heuristic_holds_with_no_target() -> None:
    """If there's no unowned supply reachable, agent holds."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, peace_threshold=0)
    # We already own everything reachable.
    s.ownership[1] = 0
    s.ownership[2] = 0
    orders = HeuristicAgent().choose_orders(s, player=0)
    assert orders[0] == Hold()


def test_heuristic_does_not_dislodge_own_unit() -> None:
    """If the next step toward target is occupied by own unit, agent holds."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 1),  # own unit blocking the path
    ], num_players=2, peace_threshold=0)
    s.ownership[1] = 0
    # Nearest unowned supply for u0 is node 2 (via node 1, blocked by u1).
    orders = HeuristicAgent().choose_orders(s, player=0)
    assert orders[0] == Hold()


def test_heuristic_returns_empty_for_player_with_no_units() -> None:
    cfg = GameConfig(num_players=2, seed=1, max_turns=5)
    m = generate_map(2, seed=1)
    state = initial_state(cfg, m)
    # Eliminate all of player 1's units.
    state.units = {uid: u for uid, u in state.units.items() if u.owner != 1}
    orders = HeuristicAgent().choose_orders(state, player=1)
    assert orders == {}


# --- statistical: HeuristicAgent should beat RandomAgent reliably ---


def test_heuristic_beats_random_in_score_aggregate() -> None:
    """Across 8 games, heuristic should outscore random in aggregate.

    Single games can swing on the random agent's lucky moves, so we
    aggregate across multiple seeds. The bar is loose intentionally —
    we want a reliable signal, not a fragile one.
    """
    heuristic_total = 0.0
    random_total = 0.0
    for seed in range(8):
        cfg = GameConfig(num_players=4, seed=seed, max_turns=15,
                         peace_threshold=99)
        agents = {
            0: HeuristicAgent(),
            1: RandomAgent(seed=seed * 100 + 1),
            2: RandomAgent(seed=seed * 100 + 2),
            3: RandomAgent(seed=seed * 100 + 3),
        }
        final = play_game(agents, config=cfg)
        heuristic_total += final.scores[0]
        random_total += (final.scores[1] + final.scores[2] + final.scores[3]) / 3
    assert heuristic_total > random_total, \
        f"heuristic_total={heuristic_total} not > random_avg={random_total}"


def test_heuristic_match_result_payout_advantage() -> None:
    """Across 8 games, heuristic should accrue more payout share than the
    random average. Validates the scoring layer end-to-end with a real agent.
    """
    heuristic_payout = 0.0
    random_payout_sum = 0.0
    for seed in range(8):
        cfg = GameConfig(num_players=4, seed=seed, max_turns=15,
                         peace_threshold=99)
        agents = {
            0: HeuristicAgent(),
            1: RandomAgent(seed=seed * 100 + 1),
            2: RandomAgent(seed=seed * 100 + 2),
            3: RandomAgent(seed=seed * 100 + 3),
        }
        final = play_game(agents, config=cfg)
        match = compute_match_result(final)
        heuristic_payout += match.payout[0]
        random_payout_sum += match.payout[1] + match.payout[2] + match.payout[3]
    random_avg = random_payout_sum / 3
    assert heuristic_payout > random_avg, \
        f"heuristic_payout={heuristic_payout} not > random_avg={random_avg}"
