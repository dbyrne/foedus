"""Round-trip tests for press tokens through the full round lifecycle."""

from __future__ import annotations

from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Intent,
    Move,
    Phase,
    Press,
    Stance,
)
from foedus.mapgen import generate_map
from foedus.press import (
    advance_turn,
    finalize_round,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import initial_state


def _fresh(num_players: int = 3) -> GameState:
    cfg = GameConfig(num_players=num_players, seed=42, max_turns=99)
    m = generate_map(num_players, seed=42)
    return initial_state(cfg, m)


def test_stance_archives_to_press_history() -> None:
    s = _fresh(num_players=2)
    p0 = Press(stance={1: Stance.ALLY}, intents={})
    p1 = Press(stance={0: Stance.HOSTILE}, intents={})
    s = submit_press_tokens(s, 0, p0)
    s = submit_press_tokens(s, 1, p1)
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.press_history[-1][0] == p0
    assert s.press_history[-1][1] == p1


def test_intent_archives_per_recipient() -> None:
    s = _fresh(num_players=2)
    intent = Intent(unit_id=0, declared_order=Hold())
    p = Press(stance={}, intents={1: [intent]})
    s = submit_press_tokens(s, 0, p)
    s = submit_press_tokens(s, 1, Press(stance={}, intents={}))
    s = signal_done(s, 0)
    s = signal_done(s, 1)
    s = finalize_round(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.press_history[-1][0].intents[1][0] == intent


def test_revision_before_done_overwrites_pending() -> None:
    s = _fresh(num_players=2)
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents={}))
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents={}))
    assert s.round_press_pending[0].stance == {1: Stance.ALLY}


def test_revision_after_done_silently_dropped() -> None:
    s = _fresh(num_players=2)
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents={}))
    s = signal_done(s, 0)
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents={}))
    assert s.round_press_pending[0].stance == {1: Stance.ALLY}


def test_empty_press_via_advance_turn_archives_empty_press() -> None:
    s = _fresh(num_players=2)
    s = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.press_history[-1][0] == Press(stance={}, intents={})
    assert s.press_history[-1][1] == Press(stance={}, intents={})


def test_returning_to_negotiation_phase_after_finalize() -> None:
    s = _fresh(num_players=2)
    s = advance_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.phase == Phase.NEGOTIATION
