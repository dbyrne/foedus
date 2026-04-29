"""Bundle 4 — combat reward tests (D4 + supporter extension).

- combat_reward to attacker per successful dislodgement
- supporter_combat_reward to each uncut cross-player supporter
- Cut supporters get nothing; same-owner supports get nothing (no double-dip)
- Failed attacks (bounces) reward nobody
- Knobs default 1.0 each; setting 0 disables
"""

from __future__ import annotations

import os
from dataclasses import replace

from foedus.core import GameConfig, Hold, Map, Move, NodeType, SupportMove, Unit
from foedus.resolve import resolve_turn

from tests.helpers import line_map, make_state


def _diamond() -> Map:
    """Four nodes in a diamond:
            1
           / \\
          0   3
           \\ /
            2
    All four mutually adjacent except 0-3 and 1-2 (the diagonals are cut).
    Actually for support-cut tests we want richer adjacency. Use:
            1 (HOME for p0)
           /|\\
          0 | 3 (HOME for p1)
           \\|/
            2 (SUPPLY)
    where 1 and 3 each border 0, 2; 0 and 3 border each other through 2.
    """
    coords = {0: (0, 0), 1: (1, 0), 2: (1, -1), 3: (2, 0)}
    edges = {
        0: frozenset({1, 2}),
        1: frozenset({0, 2, 3}),
        2: frozenset({0, 1, 3}),
        3: frozenset({1, 2}),
    }
    types = {0: NodeType.HOME, 1: NodeType.SUPPLY,
             2: NodeType.SUPPLY, 3: NodeType.HOME}
    homes = {0: 0, 3: 1}
    return Map(coords=coords, edges=edges, node_types=types,
               home_assignments=homes)


def test_attacker_gets_combat_reward_on_dislodgement() -> None:
    """Attacker score increases by combat_reward per dislodgement.

    Setup: line_map(3). p0 at 0 (home), p1 at 1 (supply). p0 attacks node 1
    with leverage bonus +2 to ensure dislodgement.
    """
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1)],
                   num_players=2, max_turns=99)
    s = replace(s, aid_given={(0, 1): 4})  # leverage_bonus = 2 → str 3 vs 1
    pre_p0 = s.scores[0]
    s_after = resolve_turn(s, {0: {0: Move(dest=1)}, 1: {1: Hold()}})
    # Verify dislodgement happened.
    assert 1 not in s_after.units
    # Score delta breakdown for p0:
    #   - supply_count after: home (0) + node 1 (now owned via rule a) = 2
    #   - combat_reward: +1
    delta = s_after.scores[0] - pre_p0
    assert delta == 3.0


def test_combat_reward_disabled_with_zero() -> None:
    """combat_reward=0 disables both attacker and supporter rewards."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1)],
                   num_players=2, max_turns=99)
    s = replace(s, aid_given={(0, 1): 4},
                config=replace(s.config, combat_reward=0.0,
                               supporter_combat_reward=0.0))
    pre = s.scores[0]
    s_after = resolve_turn(s, {0: {0: Move(dest=1)}, 1: {1: Hold()}})
    delta = s_after.scores[0] - pre
    # supply scoring only: home (0) + node 1 = 2.
    assert delta == 2.0


def test_supporter_reward_for_cross_player_support() -> None:
    """Cross-player SupportMove supporter gets +supporter_combat_reward
    per dislodgement. Independent of alliance bonus.
    """
    m = _diamond()
    # u0(p0) at 0, u1(p1) at 1 (target — p0's HOME, occupied by p1!),
    # u2(p2) at 3 (p1's home, occupied by p2).
    # That's pretty messy. Simpler: 3 players, target is the node 2 SUPPLY.
    # u0(p0) at 0, u1(p1) at 2 (sitting on supply), u2(p2) at 3.
    # u0 attacks node 2; u2 SupportMoves(0, 2) from node 3 (adjacent to 2).
    # str: u0 + u2_support = 2 vs u1 hold = 1 → dislodge.
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2), Unit(2, 2, 3)],
                   num_players=3, max_turns=99)
    # Disable alliance bonus to isolate supporter reward.
    os.environ["FOEDUS_ALLIANCE_BONUS"] = "0"
    try:
        pre_p2 = s.scores[2]
        s_after = resolve_turn(s, {
            0: {0: Move(dest=2)},
            1: {1: Hold()},
            2: {2: SupportMove(target=0, target_dest=2)},
        })
        # u1 dislodged.
        assert 1 not in s_after.units
        # Compute p2's expected score:
        # - p2 starts at node 3 (which is HOME for p1, so p1 owned at start).
        #   Wait: home_assignments[3] = 1, but unit at 3 is u2(p2). make_state's
        #   precedence: home seeds first, then unit-location overrides.
        # - So initial ownership[3] = 2 (unit override).
        # - End of turn: u2 stays at 3 (SupportMove is non-Move). Rule b:
        #   start owner of HOME 3 = 2 (from unit override). End occupant
        #   u2(p2). Same player → ownership[3] = 2.
        # - p2 supply_count = 1 (home node 3 owned by p2).
        # - +1 supply scoring + 1 supporter_combat_reward = +2.
        delta_p2 = s_after.scores[2] - pre_p2
        assert delta_p2 == 2.0
    finally:
        os.environ.pop("FOEDUS_ALLIANCE_BONUS", None)


def test_failed_attack_no_combat_reward() -> None:
    """Bounced attack yields no combat reward (only supply scoring)."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1)],
                   num_players=2, max_turns=99)
    # No leverage; both unit strength 1; attack bounces.
    pre = s.scores[0]
    s_after = resolve_turn(s, {0: {0: Move(dest=1)}, 1: {1: Hold()}})
    # u1 still alive.
    assert 1 in s_after.units
    delta = s_after.scores[0] - pre
    # P0 owns home (0) + node 1 (where u0 stayed). Plain? No, line_map(3)
    # has nodes 0, 2 as HOME and node 1 as SUPPLY. Node 1 stays p1 (rule b
    # would flip if u1's owner-start matches end; u1 at 1 throughout =>
    # ownership[1] = 1). So p0 only owns home = 1 supply.
    assert delta == 1.0


def test_same_owner_support_no_supporter_reward() -> None:
    """Same-owner SupportMove does NOT trigger supporter_combat_reward
    (no double-dip — the attacker's player already got combat_reward).
    """
    # 2-player diamond. p0 has u0 at 0 + u1 at 1; p1 has u2 at 2 (target).
    # u0 SupportMoves u1's attack on 2 (u0 is at 0, adjacent to 2).
    m = _diamond()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 0, 1), Unit(2, 1, 2)],
                   num_players=2, max_turns=99)
    pre_p0 = s.scores[0]
    s_after = resolve_turn(s, {
        0: {0: SupportMove(target=1, target_dest=2), 1: Move(dest=2)},
        1: {2: Hold()},
    })
    # Verify: u2 dislodged.
    assert 2 not in s_after.units
    delta_p0 = s_after.scores[0] - pre_p0
    # Expected for p0:
    # - Supplies owned at end: home (0) + node 1 (rule b: u0 stayed) + node 2 (rule a: dislodged)
    #   = 3 supply scoring.
    # - combat_reward: +1 (u1's attack succeeded as a Move)
    # - supporter_combat_reward: 0 (u0's SupportMove was same-owner — skipped)
    # - Total: +4.
    # Plus u1 was at node 1 originally (SUPPLY). u1 moved to 2. Node 1 end-of-turn
    # has no unit. Rule b: start owner of node 1 was 0 (u1 there), end occupant
    # none — rule b doesn't fire. So node 1 stays owned by 0 (carried).
    assert delta_p0 == 4.0


def test_supporter_reward_disabled_with_zero() -> None:
    """supporter_combat_reward=0 disables supporter bonus while combat_reward stays."""
    m = _diamond()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2), Unit(2, 2, 3)],
                   num_players=3, max_turns=99)
    s = replace(s, config=replace(s.config, supporter_combat_reward=0.0))
    os.environ["FOEDUS_ALLIANCE_BONUS"] = "0"
    try:
        pre_p2 = s.scores[2]
        s_after = resolve_turn(s, {
            0: {0: Move(dest=2)},
            1: {1: Hold()},
            2: {2: SupportMove(target=0, target_dest=2)},
        })
        assert 1 not in s_after.units
        # P2 owns home node 3 only → 1 supply scoring + 0 supporter reward = 1.
        delta_p2 = s_after.scores[2] - pre_p2
        assert delta_p2 == 1.0
    finally:
        os.environ.pop("FOEDUS_ALLIANCE_BONUS", None)
