"""Tests for GameState.last_turn_score_delta (Phase 0a, F1 — income ledger).

The income ledger needs to tell an agent "you scored +N last turn" and that
number must be provably identical to what the engine actually computed, not
a separate re-derivation that could drift. `last_turn_score_delta` is set by
_resolve_orders (the single scoring computation in resolve.py) as
new_scores - old_scores, so it's true by construction for the base tiered
scoring + bonuses. finalize_round applies one more score adjustment
(stagnation cost) on top of _resolve_orders' output, so it must fold that
delta in too — the second test below is the one that actually exercises
that seam.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import Hold, Move, Press, Support, Unit
from foedus.press import finalize_round, signal_done, submit_press_tokens
from foedus.resolve import initial_state, resolve_turn

from tests.helpers import line_map, make_state, simple_two_player_state


def test_initial_state_has_empty_score_delta() -> None:
    s = simple_two_player_state()
    assert s.last_turn_score_delta == {}


def test_resolve_turn_score_delta_reflects_home_income() -> None:
    """Two homes, both players Hold — each nets +1 (home value 1)."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    s2 = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s2.last_turn_score_delta == {0: 1.0, 1: 1.0}
    assert s2.scores == {0: 1.0, 1: 1.0}


def test_resolve_turn_score_delta_matches_actual_score_change_over_two_turns() -> None:
    """Delta on turn 2 reflects only that turn's change, not the cumulative total."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.scores == {0: 1.0, 1: 1.0}
    s2 = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s2.last_turn_score_delta == {0: 1.0, 1: 1.0}
    assert s2.scores == {0: 2.0, 1: 2.0}


def test_finalize_round_score_delta_includes_stagnation_cost() -> None:
    """finalize_round applies stagnation cost AFTER _resolve_orders' base
    scoring; the delta must reflect the combined effect, matching
    s2.scores - original scores exactly."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    s = replace(s, config=replace(s.config, stagnation_cost=1.0))
    for p in (0, 1):
        s = submit_press_tokens(s, p, Press(stance={}, intents=[]))
        s = signal_done(s, p)
    s2 = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # +1 home income, -1 stagnation (all-Hold) => net 0 for both.
    assert s2.last_turn_score_delta == {0: 0.0, 1: 0.0}
    assert s2.scores == {0: 0.0, 1: 0.0}


def test_finalize_round_score_delta_matches_actual_delta_with_dislodgement_and_support() -> None:
    """Code review finding: the delta must be verified against a scenario
    that actually exercises combat + cross-player support, not just Holds
    — that's where score components beyond tiered income (combat_reward,
    supporter_combat_reward) come from, and where a naive re-derivation of
    "last turn's score" would be most likely to drift from resolve.py's
    actual computation.

    Scenario (line_map(5): 0(H,p0)-1$-2$-3$-4(H,p1)):
      p0: home unit at n0 (Hold); attacker unit at n1 -> Move(dest=2).
      p1: home unit at n4 (Hold); supporter unit at n3 -> Support(target=attacker).
      p2: defender unit at n2 (Hold, unsupported).
    p0's attacker (str 1) + p1's cross-player support (+1) = str 2 beats
    p2's unsupported hold (str 1) -> p2 dislodged, n2 captured by p0
    immediately (Mechanic A rule (a), no Hold-through-next-turn needed).

    Expected per-player totals (all nodes value 1, default combat_reward=
    supporter_combat_reward=1.0, FOEDUS_ALLIANCE_BONUS=3). The alliance bonus
    now fires on any cross-player support of a supply capture (the aid-spend
    gate was deleted), and the MOVER passes the reciprocation gate here
    because it has taken no ally support in the window (received==0):
      p0: {n0 home, n1 retained, n2 fresh capture} = 3 tiered + combat 1.0
          + alliance-mover 3.0 = 7.0
      p1: {n4 home, n3 supporter's unit} = 2 tiered + supporter 1.0
          + alliance-supporter 3.0 = 6.0
      p2: dislodged, owns nothing = 0.0 (eliminated for future turns, but
          this turn's own delta is still well-defined)
    """
    m = line_map(5)
    u0 = Unit(0, 0, 0)   # p0 home
    u1 = Unit(1, 1, 4)   # p1 home
    u2 = Unit(2, 2, 2)   # p2 defender
    u3 = Unit(3, 0, 1)   # p0 attacker
    u4 = Unit(4, 1, 3)   # p1 supporter
    s = make_state(m, [u0, u1, u2, u3, u4], num_players=3)
    before = dict(s.scores)
    for p in range(3):
        s = submit_press_tokens(s, p, Press(stance={}, intents=[]))
        s = signal_done(s, p)
    orders = {
        0: {3: Move(dest=2)},
        1: {4: Support(target=3)},
        2: {},
    }
    s2 = finalize_round(s, orders)

    assert s2.scores == {0: 7.0, 1: 6.0, 2: 0.0}
    assert s2.last_turn_score_delta == {0: 7.0, 1: 6.0, 2: 0.0}
    for p in range(3):
        assert s2.last_turn_score_delta[p] == s2.scores.get(p, 0.0) - before.get(p, 0.0)


def test_initial_state_from_resolve_has_empty_score_delta() -> None:
    from foedus.core import GameConfig
    from foedus.mapgen import generate_map

    cfg = GameConfig(num_players=2, map_radius=2, seed=7)
    m = generate_map(cfg.num_players, seed=cfg.seed)
    s = initial_state(cfg, m)
    assert s.last_turn_score_delta == {}
