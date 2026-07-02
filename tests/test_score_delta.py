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

from foedus.core import Hold, Press, Unit
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


def test_finalize_round_score_delta_matches_actual_delta_with_movement() -> None:
    """Sanity check across a non-trivial finalize_round call: the recorded
    delta always equals the actual before/after score change, regardless of
    which scoring sub-steps fired."""
    s = simple_two_player_state()
    before = dict(s.scores)
    survivors = [p for p in range(s.config.num_players) if p not in s.eliminated]
    for p in survivors:
        s = submit_press_tokens(s, p, Press(stance={}, intents=[]))
        s = signal_done(s, p)
    orders = {p: {u.id: Hold() for u in s.units_of(p)} for p in survivors}
    s2 = finalize_round(s, orders)
    for p in survivors:
        assert s2.last_turn_score_delta[p] == s2.scores.get(p, 0.0) - before.get(p, 0.0)


def test_initial_state_from_resolve_has_empty_score_delta() -> None:
    from foedus.core import GameConfig
    from foedus.mapgen import generate_map

    cfg = GameConfig(num_players=2, map_radius=2, seed=7)
    m = generate_map(cfg.num_players, seed=cfg.seed)
    s = initial_state(cfg, m)
    assert s.last_turn_score_delta == {}
