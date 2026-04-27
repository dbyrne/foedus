"""Tests for intent verification and betrayal observation."""

from __future__ import annotations

from foedus.core import (
    GameState,
    Hold,
    Intent,
    Move,
    Press,
    Unit,
)
from foedus.press import _verify_intents

from tests.helpers import line_map, make_state


def _state_with_press(press_by_player: dict[int, Press]) -> GameState:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
    ], num_players=2)
    s.round_press_pending.update(press_by_player)
    return s


def test_no_betrayal_when_intent_matches_submitted() -> None:
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    press = Press(stance={}, intents=[intent])
    s = _state_with_press({0: press})
    flat = {0: Move(dest=1), 1: Hold()}
    obs = _verify_intents(flat, s)
    assert obs == {}


def test_betrayal_when_submitted_differs_from_declared() -> None:
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    press = Press(stance={}, intents=[intent])
    s = _state_with_press({0: press})
    flat = {0: Hold(), 1: Hold()}
    obs = _verify_intents(flat, s)
    assert 1 in obs
    assert len(obs[1]) == 1
    assert obs[1][0].betrayer == 0
    assert obs[1][0].intent == intent
    assert obs[1][0].actual_order == Hold()


def test_betrayal_only_visible_to_recipient() -> None:
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1}))
    press = Press(stance={}, intents=[intent])
    s = _state_with_press({0: press})
    flat = {0: Hold(), 1: Hold()}
    obs = _verify_intents(flat, s)
    assert 1 in obs and 0 not in obs


def test_no_betrayal_for_unit_not_owned_by_sender() -> None:
    intent = Intent(unit_id=1, declared_order=Move(dest=3),
                    visible_to=frozenset({1}))  # player 1's unit
    press = Press(stance={}, intents=[intent])  # player 0 sending
    s = _state_with_press({0: press})
    flat = {0: Hold(), 1: Hold()}
    obs = _verify_intents(flat, s)
    assert obs == {}


def test_betrayal_uses_raw_input_not_normalized() -> None:
    """Comparison surface is raw flat input. If intent was Hold and raw
    submission was Move(99) (non-adjacent → would normalize to Hold), the
    comparison still yields a betrayal because Move(99) != Hold()."""
    intent = Intent(unit_id=0, declared_order=Hold(),
                    visible_to=frozenset({1}))
    press = Press(stance={}, intents=[intent])
    s = _state_with_press({0: press})
    flat = {0: Move(dest=99), 1: Hold()}
    obs = _verify_intents(flat, s)
    assert 1 in obs


def test_same_intent_to_multiple_recipients_each_observes() -> None:
    # ONE intent visible to both players 1 and 2 - produces an observation
    # for each named recipient.
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1, 2}))
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
        Unit(2, 2, 2),
    ], num_players=3)
    press = Press(stance={}, intents=[intent])
    s.round_press_pending[0] = press
    flat = {0: Hold(), 1: Hold(), 2: Hold()}
    obs = _verify_intents(flat, s)
    assert 1 in obs and 2 in obs
    assert len(obs[1]) == 1 and len(obs[2]) == 1


def test_public_intent_betrayal_observed_by_all_survivors() -> None:
    intent = Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
        Unit(2, 2, 2),
    ], num_players=3)
    s.round_press_pending[0] = Press(stance={}, intents=[intent])
    flat = {0: Hold(), 1: Hold(), 2: Hold()}
    obs = _verify_intents(flat, s)
    # Player 0 (sender) doesn't get observation; players 1 and 2 do.
    assert 0 not in obs
    assert 1 in obs and len(obs[1]) == 1
    assert 2 in obs and len(obs[2]) == 1


def test_group_intent_betrayal_observed_by_all_named() -> None:
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1, 2}))
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
        Unit(2, 2, 2),
        Unit(3, 3, 3),
    ], num_players=4)
    s.round_press_pending[0] = Press(stance={}, intents=[intent])
    flat = {0: Hold(), 1: Hold(), 2: Hold(), 3: Hold()}
    obs = _verify_intents(flat, s)
    # Players 1 and 2 see; player 3 does not (not in visible_to).
    assert 1 in obs and 2 in obs
    assert 3 not in obs


def test_eliminated_player_in_visible_to_excluded_from_betrayal() -> None:
    intent = Intent(unit_id=0, declared_order=Move(dest=1),
                    visible_to=frozenset({1, 2}))
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 4),
        Unit(2, 2, 2),
    ], num_players=3)
    s.eliminated.add(2)  # player 2 eliminated
    s.round_press_pending[0] = Press(stance={}, intents=[intent])
    flat = {0: Hold(), 1: Hold(), 2: Hold()}
    obs = _verify_intents(flat, s)
    # Only player 1 sees (player 2 eliminated).
    assert 1 in obs
    assert 2 not in obs
