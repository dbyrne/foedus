"""Tests for the détente collective-victory condition (v2: stance-anchored).

If `detente_threshold` consecutive turns pass with all-pairs-mutual-ALLY
among surviving players, the game ends in shared peace and all surviving
players win. The old "no dislodgement" attractor is gone — passive play
no longer triggers détente.
"""

from __future__ import annotations

from foedus.core import Hold, Press, Stance, Unit
from foedus.press import (
    advance_turn,
    finalize_round,
    signal_done,
    submit_press_tokens,
)

from tests.helpers import line_map, make_state


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


def test_streak_starts_at_zero() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)])
    assert s.mutual_ally_streak == 0


def test_streak_increments_on_consensus_ally_turn() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   detente_threshold=99)
    press = _all_ally_press_for(2)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s = _run_round_with_press(s, press, orders)
    assert s.mutual_ally_streak == 1
    s = _run_round_with_press(s, press, orders)
    assert s.mutual_ally_streak == 2


def test_streak_resets_when_one_pair_not_ally() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   detente_threshold=99)
    press_ally = _all_ally_press_for(2)
    press_mixed = {
        0: Press(stance={1: Stance.NEUTRAL}, intents={}),
        1: Press(stance={0: Stance.ALLY}, intents={}),
    }
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    s = _run_round_with_press(s, press_ally, orders)
    assert s.mutual_ally_streak == 1
    s = _run_round_with_press(s, press_mixed, orders)
    assert s.mutual_ally_streak == 0


def test_detente_terminates_at_threshold() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   max_turns=100, detente_threshold=3)
    press = _all_ally_press_for(2)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    for _ in range(2):
        s = _run_round_with_press(s, press, orders)
        assert not s.is_terminal()
    s = _run_round_with_press(s, press, orders)
    assert s.is_terminal()
    assert s.detente_reached


def test_detente_winners_includes_all_survivors() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   max_turns=100, detente_threshold=2)
    press = _all_ally_press_for(2)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    for _ in range(2):
        s = _run_round_with_press(s, press, orders)
    assert s.detente_reached
    assert s.winners() == [0, 1]
    assert s.winner is None


def test_detente_disabled_with_threshold_zero() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   max_turns=100, detente_threshold=0)
    press = _all_ally_press_for(2)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    for _ in range(20):
        s = _run_round_with_press(s, press, orders)
    assert not s.detente_reached
    assert not s.is_terminal()


def test_passive_play_does_not_trigger_detente() -> None:
    """The empirical bug from v1: random-vs-random ended in détente at turn 5
    because peace_streak fired on inaction. New semantics: no stance signal,
    no streak progress."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   max_turns=100, detente_threshold=3)
    orders = {0: {0: Hold()}, 1: {1: Hold()}}
    for _ in range(10):
        s = advance_turn(s, orders)
    assert s.mutual_ally_streak == 0
    assert not s.detente_reached


def test_detente_does_not_trigger_with_one_player() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 1)], num_players=1, detente_threshold=2)
    orders = {0: {0: Hold()}}
    for _ in range(3):
        s = advance_turn(s, orders)
    assert not s.detente_reached
