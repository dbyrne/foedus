"""Tests for the consensus-mutual-ALLY evaluation that drives détente."""

from __future__ import annotations

from foedus.core import GameState, Press, Stance, Unit
from foedus.press import _all_pairs_mutual_ally

from tests.helpers import line_map, make_state


def _state_with_locked_press(press_by_player: dict[int, Press],
                             num_players: int = 3) -> GameState:
    m = line_map(7)
    s = make_state(m, [Unit(i, i, i) for i in range(num_players)],
                   num_players=num_players)
    s.round_press_pending.update(press_by_player)
    return s


def test_all_neutral_is_not_consensus() -> None:
    s = _state_with_locked_press({
        0: Press(stance={}, intents=[]),
        1: Press(stance={}, intents=[]),
        2: Press(stance={}, intents=[]),
    })
    assert _all_pairs_mutual_ally(s) is False


def test_all_pairs_ally_is_consensus() -> None:
    s = _state_with_locked_press({
        0: Press(stance={1: Stance.ALLY, 2: Stance.ALLY}, intents=[]),
        1: Press(stance={0: Stance.ALLY, 2: Stance.ALLY}, intents=[]),
        2: Press(stance={0: Stance.ALLY, 1: Stance.ALLY}, intents=[]),
    })
    assert _all_pairs_mutual_ally(s) is True


def test_one_unilateral_hostile_breaks_consensus() -> None:
    s = _state_with_locked_press({
        0: Press(stance={1: Stance.ALLY, 2: Stance.HOSTILE}, intents=[]),
        1: Press(stance={0: Stance.ALLY, 2: Stance.ALLY}, intents=[]),
        2: Press(stance={0: Stance.ALLY, 1: Stance.ALLY}, intents=[]),
    })
    assert _all_pairs_mutual_ally(s) is False


def test_eliminated_players_excluded_from_matrix() -> None:
    s = _state_with_locked_press({
        0: Press(stance={1: Stance.ALLY}, intents=[]),
        1: Press(stance={0: Stance.ALLY}, intents=[]),
    }, num_players=3)
    s.eliminated.add(2)
    assert _all_pairs_mutual_ally(s) is True


def test_single_survivor_is_not_consensus() -> None:
    s = _state_with_locked_press({
        0: Press(stance={}, intents=[]),
    }, num_players=3)
    s.eliminated.update({1, 2})
    assert _all_pairs_mutual_ally(s) is False
