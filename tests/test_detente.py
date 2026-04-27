"""Tests for the détente collective-victory condition.

If `peace_threshold` consecutive turns pass with zero dislodgements, the game
ends in a shared peace and all surviving players win.
"""

from __future__ import annotations

from foedus.core import (
    Hold,
    Move,
    SupportMove,
    Unit,
)
from foedus.resolve import resolve_turn

from tests.helpers import line_map, make_state


def test_peace_streak_starts_at_zero() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)])
    assert s.peace_streak == 0


def test_peace_streak_increments_on_quiet_turn() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   peace_threshold=99)
    s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.peace_streak == 1
    s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.peace_streak == 2


def test_peace_streak_resets_on_dislodgement() -> None:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 2),  # supporter
        Unit(2, 1, 1),  # defender
    ], num_players=2, peace_threshold=99)
    # Turn 1: everyone holds → streak should rise to 1.
    s = resolve_turn(s, {0: {0: Hold(), 1: Hold()}, 1: {2: Hold()}})
    assert s.peace_streak == 1
    # Turn 2: u0 dislodges u2 with u1's support → streak resets.
    s = resolve_turn(s, {
        0: {0: Move(dest=1), 1: SupportMove(target=0, target_dest=1)},
        1: {2: Hold()},
    })
    assert s.peace_streak == 0


def test_detente_terminates_game_at_threshold() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   max_turns=100, peace_threshold=3)
    for _ in range(2):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
        assert not s.is_terminal()
    s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.is_terminal()
    assert s.detente_reached


def test_detente_winners_includes_all_survivors() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   max_turns=100, peace_threshold=2)
    for _ in range(2):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.detente_reached
    assert s.winners() == [0, 1]
    assert s.winner is None  # collective, not solo


def test_detente_disabled_with_threshold_zero() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)], num_players=2,
                   max_turns=100, peace_threshold=0)
    for _ in range(20):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    # Streak still increments but never triggers terminal.
    assert s.peace_streak == 20
    assert not s.detente_reached
    assert not s.is_terminal()


def test_detente_excludes_eliminated_player() -> None:
    """A player eliminated before peace was reached doesn't share the victory."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2,
                   max_turns=100, peace_threshold=3)
    # Player 1 starts with no units and no supply (helper only assigned p0's home).
    # First turn: p1 gets eliminated, but no DISLODGEMENT happens, so streak grows.
    s = resolve_turn(s, {0: {0: Hold()}})
    assert 1 in s.eliminated
    assert s.peace_streak == 1
    # Continue holding. Now only p0 is active; détente requires >1 survivor,
    # so the game terminates as last-standing.
    s = resolve_turn(s, {0: {0: Hold()}})
    s = resolve_turn(s, {0: {0: Hold()}})
    assert s.is_terminal()
    assert not s.detente_reached  # solo player → not collective
    assert s.winner == 0


def test_detente_does_not_trigger_with_one_player() -> None:
    """One-player games never trigger détente even if peace_streak grows."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 1)], num_players=1, peace_threshold=2)
    s = resolve_turn(s, {0: {0: Hold()}})
    s = resolve_turn(s, {0: {0: Hold()}})
    assert not s.detente_reached
