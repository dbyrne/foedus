"""Tests for compute_match_result: ranks, payouts, and end-state handling."""

from __future__ import annotations

import math

import pytest

from foedus.core import Hold, Unit
from foedus.resolve import resolve_turn
from foedus.scoring import (
    SCORE_POOL_FRACTION,
    SURVIVAL_BONUS_FRACTION,
    compute_match_result,
)

from tests.helpers import line_map, make_state


def _almost_sum_to_one(payout: dict) -> bool:
    return math.isclose(sum(payout.values()), 1.0, abs_tol=1e-9)


def test_raises_on_non_terminal() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)],
                   num_players=2, max_turns=10)
    with pytest.raises(ValueError):
        compute_match_result(s)


def test_solo_winner_takes_pot() -> None:
    """Last player standing receives the entire payout."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=2, max_turns=10)
    s.eliminated.add(1)
    result = compute_match_result(s)
    assert result.solo_winner == 0
    assert result.payout[0] == 1.0
    assert result.payout[1] == 0.0
    assert _almost_sum_to_one(result.payout)


def test_score_payout_4_players_no_eliminations() -> None:
    """SS + survival bonus over 4 surviving players with diverse scores."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)],
                   num_players=4, max_turns=1, turn=1)
    s.scores = {0: 100.0, 1: 90.0, 2: 50.0, 3: 30.0}
    result = compute_match_result(s)

    # Hand-verified expected shares (sum-of-squares + 20% flat):
    # SS total = 10000 + 8100 + 2500 + 900 = 21500
    # flat share = 0.20 / 4 = 0.05
    # score share = 0.80 * sq[p] / 21500
    expected = {
        0: 0.05 + 0.80 * 10000 / 21500,
        1: 0.05 + 0.80 * 8100 / 21500,
        2: 0.05 + 0.80 * 2500 / 21500,
        3: 0.05 + 0.80 * 900 / 21500,
    }
    for p in range(4):
        assert math.isclose(result.payout[p], expected[p], rel_tol=1e-9)
    assert _almost_sum_to_one(result.payout)


def test_score_payout_descending_by_score() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=4, max_turns=1, turn=1)
    s.scores = {0: 100.0, 1: 90.0, 2: 50.0, 3: 30.0}
    result = compute_match_result(s)
    assert result.payout[0] > result.payout[1] > result.payout[2] > result.payout[3]


def test_score_payout_survival_bonus_floor() -> None:
    """A surviving player with score 0 still gets the flat survival share."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=4, max_turns=1, turn=1)
    s.scores = {0: 100.0, 1: 0.0, 2: 0.0, 3: 0.0}
    result = compute_match_result(s)
    # P1, P2, P3 each get exactly 0.20 / 4 = 0.05 (their only share).
    expected_floor = SURVIVAL_BONUS_FRACTION / 4
    for p in (1, 2, 3):
        assert math.isclose(result.payout[p], expected_floor, rel_tol=1e-9)
    # P0 gets flat + entire score pool
    assert math.isclose(result.payout[0],
                        expected_floor + SCORE_POOL_FRACTION, rel_tol=1e-9)


def test_score_payout_all_zero_scores_equal_split() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=4, max_turns=1, turn=1)
    s.scores = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
    result = compute_match_result(s)
    for p in range(4):
        assert math.isclose(result.payout[p], 0.25, rel_tol=1e-9)


def test_score_payout_eliminated_get_zero() -> None:
    """Eliminated players receive 0; survivors absorb their share."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=4, max_turns=1, turn=1)
    s.scores = {0: 100.0, 1: 50.0, 2: 30.0, 3: 0.0}
    s.eliminated.update({2, 3})
    result = compute_match_result(s)
    assert result.payout[2] == 0.0
    assert result.payout[3] == 0.0
    assert _almost_sum_to_one(result.payout)


def test_detente_payout_proportional_to_score() -> None:
    """Détente payouts are linearly proportional to score (less steep than SS)."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)],
                   num_players=2, max_turns=100, peace_threshold=2)
    for _ in range(2):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.detente_reached
    s.scores = {0: 100.0, 1: 90.0}
    result = compute_match_result(s)
    total = 100 + 90
    assert math.isclose(result.payout[0], 100 / total, rel_tol=1e-9)
    assert math.isclose(result.payout[1], 90 / total, rel_tol=1e-9)
    assert result.detente
    # Confirm linear (not SS) shape: leader gets less than SS would give.
    # SS share would be 100²/(100²+90²) ≈ 0.552; linear is 100/190 ≈ 0.526.
    assert result.payout[0] < 100**2 / (100**2 + 90**2)


def test_detente_payout_all_zero_equal_split() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)],
                   num_players=2, max_turns=100, peace_threshold=2)
    for _ in range(2):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    s.scores = {0: 0.0, 1: 0.0}
    result = compute_match_result(s)
    assert math.isclose(result.payout[0], 0.5, rel_tol=1e-9)
    assert math.isclose(result.payout[1], 0.5, rel_tol=1e-9)


def test_detente_eliminated_excluded() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)],
                   num_players=4, max_turns=100, peace_threshold=2)
    for _ in range(2):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.detente_reached
    # Mark p2 and p3 as eliminated post-hoc
    s.scores = {0: 60.0, 1: 40.0, 2: 100.0, 3: 999.0}
    s.eliminated.update({2, 3})
    result = compute_match_result(s)
    assert result.payout[2] == 0.0
    assert result.payout[3] == 0.0
    assert math.isclose(result.payout[0] + result.payout[1], 1.0, rel_tol=1e-9)
    # Among survivors: 60:40 split
    assert math.isclose(result.payout[0], 0.6, rel_tol=1e-9)
    assert math.isclose(result.payout[1], 0.4, rel_tol=1e-9)


def test_ranks_strict_descending() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=4, max_turns=1, turn=1)
    s.scores = {0: 50.0, 1: 30.0, 2: 20.0, 3: 10.0}
    result = compute_match_result(s)
    assert result.rank == {0: 1, 1: 2, 2: 3, 3: 4}


def test_ranks_with_ties() -> None:
    """Standard competition ranking: ties share rank, next rank gets the gap."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=4, max_turns=1, turn=1)
    s.scores = {0: 50.0, 1: 50.0, 2: 30.0, 3: 10.0}
    result = compute_match_result(s)
    assert result.rank[0] == 1
    assert result.rank[1] == 1
    assert result.rank[2] == 3
    assert result.rank[3] == 4


def test_ranks_eliminated_get_worst_rank() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=4, max_turns=1, turn=1)
    s.scores = {0: 50.0, 1: 30.0, 2: 0.0, 3: 0.0}
    s.eliminated.update({2, 3})
    result = compute_match_result(s)
    assert result.rank[0] == 1
    assert result.rank[1] == 2
    assert result.rank[2] == 3  # tied at the back
    assert result.rank[3] == 3


def test_solo_winner_ranks() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=4, max_turns=10)
    s.eliminated.update({1, 2, 3})
    result = compute_match_result(s)
    assert result.rank[0] == 1
    assert result.rank[1] == result.rank[2] == result.rank[3] == 2
    assert result.solo_winner == 0
