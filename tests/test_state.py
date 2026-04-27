"""Tests for GameState accessors: winner, final_scores."""

from __future__ import annotations

from foedus.core import Unit

from tests.helpers import line_map, make_state


def test_winner_none_when_not_terminal() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2, max_turns=10)
    assert s.winner is None


def test_winner_when_only_one_active_player() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, max_turns=10)
    s.eliminated.add(1)
    assert s.winner == 0


def test_winner_by_score() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2, max_turns=1, turn=1)
    s.scores[0] = 5.0
    s.scores[1] = 3.0
    assert s.is_terminal()
    assert s.winner == 0


def test_winner_none_on_tie() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2, max_turns=1, turn=1)
    s.scores[0] = 5.0
    s.scores[1] = 5.0
    assert s.is_terminal()
    assert s.winner is None


def test_final_scores_sorted_descending() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=4)
    s.scores[0] = 1.0
    s.scores[1] = 5.0
    s.scores[2] = 3.0
    s.scores[3] = 4.0
    ordered = s.final_scores()
    assert [p for p, _ in ordered] == [1, 3, 2, 0]
    assert [score for _, score in ordered] == [5.0, 4.0, 3.0, 1.0]
