"""Tests for metric aggregation from sweep JSONL records."""
import pytest
from foedus.eval.metrics import (
    rankings_from_records,
    engagement_from_records,
    pairwise_winrate_from_records,
    probe_score_diff,
)


def _make_record(agents, scores, **engagement):
    """Synthetic sweep record."""
    base = {
        "agents": list(agents),
        "final_scores": list(scores),
        "dislodgement_count": 0,
        "aid_spends_count": 0,
        "alliance_bonuses_fired": 0,
        "combat_rewards_fired": 0,
        "supporter_rewards_fired": 0,
        "leverage_bonuses_fired": 0,
        "betrayals_observed": 0,
        "detente_streak_resets": 0,
        "order_type_counts": {},
    }
    base.update(engagement)
    return base


def test_rankings_simple_two_games():
    recs = [
        _make_record(["A", "B", "C", "D"], [10, 5, 3, 2]),
        _make_record(["A", "B", "X", "Y"], [4, 8, 1, 1]),
    ]
    r = rankings_from_records(recs)
    by_name = {row["agent"]: row for row in r}
    assert by_name["A"]["mean_score"] == pytest.approx(7.0)
    assert by_name["A"]["n_appearances"] == 2
    assert by_name["B"]["mean_score"] == pytest.approx(6.5)


def test_engagement_means():
    recs = [
        _make_record(["A","B","C","D"], [1,1,1,1],
                     dislodgement_count=2, aid_spends_count=4),
        _make_record(["A","B","C","D"], [1,1,1,1],
                     dislodgement_count=0, aid_spends_count=10),
    ]
    e = engagement_from_records(recs)
    assert e["dislodgements_per_game"] == pytest.approx(1.0)
    assert e["aid_spends_per_game"] == pytest.approx(7.0)


def test_pairwise_winrate_score_rank():
    """A beats B if score[A] > score[B] in same game."""
    recs = [
        _make_record(["A", "B", "C", "D"], [10, 5, 3, 2]),  # A>B>C>D
        _make_record(["A", "B", "C", "D"], [1, 9, 3, 2]),   # B>C>D>A
    ]
    m = pairwise_winrate_from_records(recs)
    assert m["matrix"][m["row_agents"].index("A")][m["col_agents"].index("B")] == pytest.approx(0.5)
    assert m["matrix"][m["row_agents"].index("B")][m["col_agents"].index("A")] == pytest.approx(0.5)


def test_probe_score_diff_subject_vs_others():
    recs = [
        _make_record(
            ["DishonestCooperator", "Cooperator", "Cooperator", "Cooperator"],
            [20, 10, 8, 12],
        ),
    ]
    diff = probe_score_diff(recs, subject_index=0)
    assert diff == pytest.approx(10.0)


def test_probe_score_diff_by_agent_works_with_permutation():
    """Agent-class identification handles permuted seat assignments.

    Same DC-vs-3-Coop scenario, but DC is at different seats per game.
    The diff should still be 10.0 since the subject's score is always
    the same relative to the others'.
    """
    recs = [
        _make_record(
            ["DishonestCooperator", "Cooperator", "Cooperator", "Cooperator"],
            [20, 10, 8, 12],  # DC=20, others mean=10
        ),
        _make_record(
            ["Cooperator", "DishonestCooperator", "Cooperator", "Cooperator"],
            [10, 20, 8, 12],  # DC=20, others mean=10
        ),
    ]
    diff = probe_score_diff(recs, subject_agent="DishonestCooperator")
    assert diff == pytest.approx(10.0)


def test_probe_score_diff_by_agent_handles_duplicate_subject_seats():
    """When the subject class occupies multiple seats (e.g. 2 TC + 2 Patron),
    the diff is mean(subject seats) - mean(other seats)."""
    recs = [
        _make_record(
            ["TrustfulCooperator", "TrustfulCooperator", "Patron", "Patron"],
            [80, 70, 50, 40],  # TC mean=75, Patron mean=45
        ),
    ]
    diff = probe_score_diff(recs, subject_agent="TrustfulCooperator")
    assert diff == pytest.approx(30.0)


def test_probe_score_diff_by_agent_skips_all_same():
    """When every seat is the subject, no contrast group → empty diff list."""
    recs = [
        _make_record(
            ["Cooperator"] * 4, [70, 71, 72, 73],
        ),
    ]
    diff = probe_score_diff(recs, subject_agent="Cooperator")
    assert diff == 0.0  # no comparison possible
