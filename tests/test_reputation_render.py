"""Tests for F6 REPUTATION rendering in foedus.render_common.

Mirrors tests/test_pact_render.py's structure for the F5 pact-breach ledger.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    GameConfig, GameState, Hold, Intent, Move, Press, ReputationTally, Stance,
    Support, Unit,
)
from foedus.press import finalize_round, signal_done, submit_press_tokens
from foedus.render_common import render_reputation

from tests.helpers import harm_map, line_map, make_state


def _state():
    m = line_map(3)
    return make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)


def _harmful_breach_state() -> GameState:
    """harm_map with p0 poised to stab committed ally p1 (a harm-typed
    breach): p0 declares ALLY->p1 + a Hold intent, then dislodges p1's n1
    unit with Move(u0->n1)+Support(u2)."""
    m = harm_map()
    ownership = {n: None for n in m.nodes}
    for node, player in m.home_assignments.items():
        ownership[node] = player
    ownership[1] = 1
    units = [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)]
    for u in units:
        ownership[u.location] = u.owner
    cfg = GameConfig(num_players=2, max_turns=50, build_period=999,
                     detente_threshold=0)
    return GameState(
        turn=0, map=m, units={u.id: u for u in units}, ownership=ownership,
        scores={0: 0.0, 1: 0.0}, eliminated=set(), next_unit_id=3, config=cfg,
    )


def _stab(s: GameState) -> GameState:
    s = submit_press_tokens(s, 0, Press(
        stance={1: Stance.ALLY},
        intents=[Intent(unit_id=0, declared_order=Hold(), visible_to=None)]))
    s = submit_press_tokens(s, 1, Press(stance={0: Stance.ALLY}, intents=[]))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    return finalize_round(
        s, {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()}})


def _finalize_with_press(state, press_by_player, orders):
    for p in range(state.config.num_players):
        if p in state.eliminated:
            continue
        press = press_by_player.get(p, Press(stance={}, intents=[]))
        state = submit_press_tokens(state, p, press)
        state = signal_done(state, p)
    return finalize_round(state, orders)


def test_render_reputation_all_zero_before_any_breach() -> None:
    s = _state()
    out = render_reputation(s, 0)
    assert "REPUTATION" in out
    assert "p0" in out and "p1" in out
    assert "0 intent" in out


def test_render_reputation_shows_counts_after_breach() -> None:
    s2 = _stab(_harmful_breach_state())
    out = render_reputation(s2, 1)
    assert "p0" in out
    assert "1 intent" in out
    assert "1 total" in out


def test_render_reputation_marks_you() -> None:
    s = _state()
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
    out_as_breacher = render_reputation(s2, 0)
    assert "p0 (you)" in out_as_breacher
    out_as_other = render_reputation(s2, 1)
    assert "p1 (you)" in out_as_other
    assert "p0 (you)" not in out_as_other


def test_render_reputation_excludes_eliminated_players() -> None:
    s = _state()
    s.eliminated.add(1)
    out = render_reputation(s, 0)
    assert "p1" not in out
