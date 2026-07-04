"""Tests for foedus.eval.ruleset — the ruleset-v1 empirical-design harness.

These cover the pure, deterministic helpers used to turn sim-sweep game
records into the discrimination / rating-convergence evidence that backs
docs/design/2026-07-04-ruleset-v1.md. The game-running orchestration in
scripts/foedus_ruleset_eval.py is exercised by a fast integration run, not
unit-tested here.
"""

from __future__ import annotations

import random

import pytest

from foedus.eval.ruleset import (
    LADDER,
    MID_LADDER,
    convergence_curve,
    discrimination_index,
    distinct_seats,
    elimination_rate,
    detente_rate,
    kendall_tau,
    mean_turns,
    min_adjacent_separation,
    ranks_from_record,
    rate_records,
    separated_adjacent_pairs,
)


# --- the ladder itself ---------------------------------------------------

def test_ladder_is_six_distinct_heuristics_including_dishonest_cooperator():
    assert len(LADDER) == 6
    assert len(set(LADDER)) == 6
    # DishonestCooperator is a required freerider probe per the brief.
    assert "DishonestCooperator" in LADDER


def test_ladder_names_are_all_real_roster_heuristics():
    from foedus.agents.heuristics import ROSTER
    for name in LADDER:
        assert name in ROSTER


def test_mid_ladder_is_the_competitive_band_without_floor_or_ceiling():
    # The full discrimination index is dominated by the trivially-separable
    # floor and ceiling; MID_LADDER is the competitive band used to measure
    # discrimination that actually matters (doc §6.3).
    assert MID_LADDER == LADDER[1:-1]
    assert "Defensive" not in MID_LADDER            # floor dropped
    assert "DishonestCooperator" not in MID_LADDER  # ceiling dropped
    assert len(MID_LADDER) == 4


# --- distinct-seat sampling (models unique-identity real matches) --------

def test_distinct_seats_returns_requested_count_all_distinct():
    rng = random.Random(0)
    seats = distinct_seats(LADDER, 4, rng)
    assert len(seats) == 4
    assert len(set(seats)) == 4
    assert set(seats) <= set(LADDER)


def test_distinct_seats_uses_full_roster_when_count_equals_size():
    rng = random.Random(1)
    seats = distinct_seats(LADDER, 6, rng)
    assert sorted(seats) == sorted(LADDER)


def test_distinct_seats_rejects_more_players_than_roster():
    rng = random.Random(2)
    with pytest.raises(ValueError):
        distinct_seats(LADDER, 7, rng)


def test_distinct_seats_is_deterministic_for_a_seed():
    a = distinct_seats(LADDER, 5, random.Random(42))
    b = distinct_seats(LADDER, 5, random.Random(42))
    assert a == b


# --- rank extraction from a sweep record ---------------------------------

def test_ranks_from_record_competition_ranks_with_ties():
    rec = {"final_scores": [10.0, 5.0, 5.0, 1.0], "eliminated": []}
    # 10 -> 1st; the two 5s share 2nd; 1 -> 4th (competition "1,2,2,4").
    assert ranks_from_record(rec) == {0: 1, 1: 2, 2: 2, 3: 4}


def test_ranks_from_record_eliminated_share_worst_rank():
    rec = {"final_scores": [10.0, 5.0, 4.0, 0.0], "eliminated": [3]}
    # survivors ranked 1,2,3; the eliminated seat shares the worst rank
    # (n_survivors + 1 = 4).
    assert ranks_from_record(rec) == {0: 1, 1: 2, 2: 3, 3: 4}


# --- Kendall tau between two orderings (permutations of same items) -------

def test_kendall_tau_identical_orderings_is_one():
    assert kendall_tau(["a", "b", "c", "d"], ["a", "b", "c", "d"]) == 1.0


def test_kendall_tau_reversed_orderings_is_minus_one():
    assert kendall_tau(["a", "b", "c", "d"], ["d", "c", "b", "a"]) == -1.0


def test_kendall_tau_single_adjacent_swap():
    # 4 items -> 6 pairs; one adjacent swap flips exactly one pair.
    tau = kendall_tau(["a", "b", "c", "d"], ["b", "a", "c", "d"])
    assert tau == pytest.approx((5 - 1) / 6)


# --- discrimination index + adjacent separation --------------------------

def test_discrimination_index_is_spread_over_noise():
    # population stdev of [1, 3] is 1.0; mean sigma is 1.0 -> index 1.0.
    ratings = {"a": (1.0, 1.0), "b": (3.0, 1.0)}
    assert discrimination_index(ratings) == pytest.approx(1.0)


def test_discrimination_index_zero_when_no_spread():
    ratings = {"a": (5.0, 2.0), "b": (5.0, 2.0), "c": (5.0, 2.0)}
    assert discrimination_index(ratings) == pytest.approx(0.0)


def test_separated_adjacent_pairs_counts_gaps_beyond_combined_sigma():
    order = ["a", "b", "c"]
    ratings = {"a": (30.0, 1.0), "b": (25.0, 1.0), "c": (24.5, 1.0)}
    # a-b gap 5 > 2 (separated); b-c gap 0.5 < 2 (not).
    assert separated_adjacent_pairs(order, ratings) == 1


def test_min_adjacent_separation_is_the_tightest_gap_in_sigma_units():
    order = ["a", "b", "c"]
    ratings = {"a": (30.0, 1.0), "b": (25.0, 1.0), "c": (24.5, 1.0)}
    # gaps in combined-sigma units: (30-25)/2 = 2.5, (25-24.5)/2 = 0.25.
    assert min_adjacent_separation(order, ratings) == pytest.approx(0.25)


# --- game-level aggregate metrics ----------------------------------------

def test_detente_and_elimination_and_length_aggregates():
    records = [
        {"detente_reached": True, "eliminated": [], "total_turns": 8},
        {"detente_reached": False, "eliminated": [2], "total_turns": 12},
        {"detente_reached": False, "eliminated": [], "total_turns": 10},
        {"detente_reached": False, "eliminated": [1, 3], "total_turns": 6},
    ]
    assert detente_rate(records) == pytest.approx(0.25)
    assert elimination_rate(records) == pytest.approx(0.5)
    assert mean_turns(records) == pytest.approx(9.0)


# --- rating a set of records ---------------------------------------------

def test_rate_records_orders_a_dominant_agent_on_top():
    # "strong" always scores highest, "weak" always lowest.
    records = [
        {"agents": ["strong", "mid", "weak"],
         "final_scores": [9.0, 5.0, 1.0], "eliminated": [],
         "detente_reached": False}
        for _ in range(20)
    ]
    rs = rate_records(records)
    board = [name for name, _ in rs.leaderboard()]
    assert board == ["strong", "mid", "weak"]


# --- convergence curve ----------------------------------------------------

def test_convergence_curve_recovers_perfectly_separable_ladder():
    reference = ["strong", "mid", "weak"]
    records = [
        {"agents": ["strong", "mid", "weak"],
         "final_scores": [9.0, 5.0, 1.0], "eliminated": [],
         "detente_reached": False}
        for _ in range(50)
    ]
    curve = convergence_curve(
        records, reference, game_counts=[5, 50], shuffles=10,
        tau_threshold=0.9, seed=0,
    )
    # Perfectly separable -> correct ordering recovered in every replica,
    # and uncertainty shrinks as more games accrue.
    assert curve[50]["frac_correct"] == pytest.approx(1.0)
    assert curve[5]["frac_correct"] == pytest.approx(1.0)
    assert curve[50]["mean_sigma"] < curve[5]["mean_sigma"]
