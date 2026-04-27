"""Tests for the new détente trigger anchored on mutual-ALLY consensus."""

from __future__ import annotations

from foedus.core import GameState, Hold, Press, Stance, Unit
from foedus.press import (
    advance_turn,
    finalize_round,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import resolve_turn

from tests.helpers import line_map, make_state


def _two_player_state(detente_threshold: int = 3) -> GameState:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   max_turns=100)
    s.config.detente_threshold = detente_threshold
    return s


def _all_ally_press_for(num_players: int) -> dict[int, Press]:
    return {
        i: Press(
            stance={j: Stance.ALLY for j in range(num_players) if j != i},
            intents={},
        )
        for i in range(num_players)
    }


def _run_round_with_press(state, press, orders):
    s = state
    for p, pr in press.items():
        s = submit_press_tokens(s, p, pr)
    for p in press:
        s = signal_done(s, p)
    return finalize_round(s, orders)


def test_detente_triggers_on_consensus_ally_streak() -> None:
    s = _two_player_state(detente_threshold=3)
    press = _all_ally_press_for(2)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    for _ in range(2):
        s = _run_round_with_press(s, press, orders)
        assert not s.is_terminal()
    s = _run_round_with_press(s, press, orders)
    assert s.detente_reached
    assert s.is_terminal()


def test_streak_resets_when_one_player_neutral() -> None:
    s = _two_player_state(detente_threshold=3)
    press_neutral_one = {
        0: Press(stance={1: Stance.NEUTRAL}, intents={}),
        1: Press(stance={0: Stance.ALLY}, intents={}),
    }
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s = _run_round_with_press(s, press_neutral_one, orders)
    assert s.mutual_ally_streak == 0


def test_old_passive_attractor_no_longer_triggers_detente() -> None:
    """The empirical bug: random-vs-random previously ended in détente at
    turn 5 because peace_streak fired on inaction. With the re-anchor,
    all-Hold rounds with empty press should NOT trigger."""
    s = _two_player_state(detente_threshold=3)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    for _ in range(10):
        s = advance_turn(s, orders)
    assert not s.detente_reached
    assert s.mutual_ally_streak == 0


def test_detente_disabled_with_threshold_zero() -> None:
    s = _two_player_state(detente_threshold=0)
    press = _all_ally_press_for(2)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    for _ in range(20):
        s = _run_round_with_press(s, press, orders)
    assert not s.detente_reached
    assert not s.is_terminal()


def test_detente_winners_includes_all_survivors() -> None:
    s = _two_player_state(detente_threshold=2)
    press = _all_ally_press_for(2)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    for _ in range(2):
        s = _run_round_with_press(s, press, orders)
    assert s.detente_reached
    assert s.winners() == [0, 1]
    assert s.winner is None


def test_streak_continues_through_elimination_when_remaining_still_ally() -> None:
    """If a player is eliminated but the remaining survivors still all-ALLY,
    the streak doesn't reset — it just shrinks the matrix and continues."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0), Unit(1, 1, 4), Unit(2, 2, 2),
    ], num_players=3, max_turns=100)
    s.config.detente_threshold = 3
    press_3 = _all_ally_press_for(3)
    orders_3 = {0: {0: Hold()}, 1: {1: Hold()}, 2: {2: Hold()}}
    s = _run_round_with_press(s, press_3, orders_3)
    assert s.mutual_ally_streak == 1
    s.eliminated.add(2)
    press_2 = _all_ally_press_for(2)
    s = _run_round_with_press(s, press_2,
                              {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.mutual_ally_streak == 2
