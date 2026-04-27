"""Tests for round-lifecycle engine functions in foedus/press.py."""

from __future__ import annotations

from foedus.core import GameConfig, GameState, Hold, Intent, Phase, Press, Stance
from foedus.mapgen import generate_map
from foedus.press import submit_press_tokens
from foedus.resolve import initial_state


def _fresh_state(num_players: int = 3) -> GameState:
    cfg = GameConfig(num_players=num_players, seed=42)
    m = generate_map(num_players, seed=42)
    return initial_state(cfg, m)


def test_submit_press_tokens_records_pending() -> None:
    s = _fresh_state()
    p = Press(stance={1: Stance.ALLY}, intents={})
    s = submit_press_tokens(s, 0, p)
    assert s.round_press_pending[0] == p


def test_submit_press_tokens_overwrites_on_revision() -> None:
    s = _fresh_state()
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents={}))
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents={}))
    assert s.round_press_pending[0].stance == {1: Stance.ALLY}


def test_submit_press_tokens_rejects_after_done() -> None:
    s = _fresh_state()
    s = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents={}))
    s.round_done.add(0)  # simulate signal_done; we'll test it separately
    s2 = submit_press_tokens(s, 0, Press(stance={1: Stance.HOSTILE}, intents={}))
    # Submission silently dropped, pending press unchanged.
    assert s2.round_press_pending[0].stance == {1: Stance.ALLY}


def test_submit_press_tokens_rejects_when_phase_not_negotiation() -> None:
    s = _fresh_state()
    s.phase = Phase.ORDERS
    s2 = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents={}))
    assert 0 not in s2.round_press_pending


def test_submit_press_tokens_rejects_eliminated_player() -> None:
    s = _fresh_state()
    s.eliminated.add(0)
    s2 = submit_press_tokens(s, 0, Press(stance={1: Stance.ALLY}, intents={}))
    assert 0 not in s2.round_press_pending


def test_submit_press_tokens_drops_intents_for_non_owned_units() -> None:
    s = _fresh_state(3)
    # Player 0 owns one unit; trying to declare an intent about another player's
    # unit should be silently dropped on submit.
    other_unit_id = next(u.id for u in s.units.values() if u.owner != 0)
    p = Press(
        stance={},
        intents={1: [Intent(unit_id=other_unit_id, declared_order=Hold())]},
    )
    s = submit_press_tokens(s, 0, p)
    # The full Press is recorded but the offending intent is dropped on submit.
    assert s.round_press_pending[0].intents.get(1, []) == []


from foedus.press import signal_done


def test_signal_done_marks_player() -> None:
    s = _fresh_state()
    s = signal_done(s, 0)
    assert 0 in s.round_done


def test_signal_done_is_idempotent() -> None:
    s = _fresh_state()
    s = signal_done(s, 0)
    s = signal_done(s, 0)
    assert s.round_done == {0}


def test_signal_done_rejects_eliminated() -> None:
    s = _fresh_state()
    s.eliminated.add(0)
    s = signal_done(s, 0)
    assert 0 not in s.round_done


def test_signal_done_rejects_outside_negotiation_phase() -> None:
    s = _fresh_state()
    s.phase = Phase.ORDERS
    s = signal_done(s, 0)
    assert 0 not in s.round_done
