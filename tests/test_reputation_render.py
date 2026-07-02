"""Tests for F6 REPUTATION rendering in foedus.render_common.

Mirrors tests/test_pact_render.py's structure for the F5 pact-breach ledger.
"""

from __future__ import annotations

from foedus.core import Hold, Intent, Move, Press, ReputationTally, Unit
from foedus.press import finalize_round, signal_done, submit_press_tokens
from foedus.render_common import render_reputation

from tests.helpers import line_map, make_state


def _state():
    m = line_map(3)
    return make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)


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
    s = _state()
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    s2 = _finalize_with_press(
        s, {0: Press(stance={}, intents=[intent])},
        {0: {0: Hold()}, 1: {1: Hold()}},
    )
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
