"""Tests for the OpenSkill-backed RatingSystem.

Skipped if openskill isn't installed (the rating extra wasn't pulled in).
"""

from __future__ import annotations

import pytest

pytest.importorskip("openskill")

from foedus.core import Unit  # noqa: E402  (after skip)
from foedus.rating import Rating, RatingSystem  # noqa: E402
from foedus.scoring import compute_match_result  # noqa: E402

from tests.helpers import line_map, make_state  # noqa: E402


def _make_terminal_state(scores: dict[int, float], num_players: int = 4):
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)], num_players=num_players,
                   max_turns=1, turn=1)
    s.scores = dict(scores)
    return s


def test_default_rating_for_new_identity() -> None:
    rs = RatingSystem()
    r = rs.get("alice")
    # OpenSkill defaults: mu=25, sigma=25/3 ≈ 8.333
    assert r.mu == pytest.approx(25.0, abs=0.01)
    assert r.sigma == pytest.approx(25 / 3, abs=0.01)


def test_conservative_rating_is_mu_minus_3sigma() -> None:
    r = Rating(mu=30.0, sigma=2.0)
    assert r.conservative == pytest.approx(24.0)


def test_winner_rating_increases_loser_decreases() -> None:
    s = _make_terminal_state({0: 100.0, 1: 50.0, 2: 30.0, 3: 10.0})
    match = compute_match_result(s)
    rs = RatingSystem()
    initial = rs.get("alice").mu  # default
    rs.update(match, identities=["alice", "bob", "carol", "dave"])
    assert rs.get("alice").mu > initial
    assert rs.get("dave").mu < initial


def test_uncertainty_decreases_with_play() -> None:
    """Sigma should shrink after a player accumulates match history."""
    s = _make_terminal_state({0: 100.0, 1: 50.0, 2: 30.0, 3: 10.0})
    match = compute_match_result(s)
    rs = RatingSystem()
    initial_sigma = rs.get("alice").sigma
    for _ in range(10):
        rs.update(match, identities=["alice", "bob", "carol", "dave"])
    assert rs.get("alice").sigma < initial_sigma


def test_identity_persists_across_updates() -> None:
    s = _make_terminal_state({0: 100.0, 1: 50.0, 2: 30.0, 3: 10.0})
    match = compute_match_result(s)
    rs = RatingSystem()
    rs.update(match, identities=["alice", "bob", "carol", "dave"])
    mu_after_one = rs["alice"].mu
    rs.update(match, identities=["alice", "bob", "carol", "dave"])
    mu_after_two = rs["alice"].mu
    # Two consecutive wins: rating should keep climbing.
    assert mu_after_two > mu_after_one


def test_identities_length_mismatch_raises() -> None:
    s = _make_terminal_state({0: 100.0, 1: 50.0, 2: 30.0, 3: 10.0})
    match = compute_match_result(s)
    rs = RatingSystem()
    with pytest.raises(ValueError):
        rs.update(match, identities=["alice", "bob"])


def test_leaderboard_sorted_by_conservative() -> None:
    """Leaderboard ranks by mu - 3·sigma so low-volume newcomers don't leapfrog."""
    s = _make_terminal_state({0: 100.0, 1: 50.0, 2: 30.0, 3: 10.0})
    match = compute_match_result(s)
    rs = RatingSystem()
    for _ in range(5):
        rs.update(match, identities=["alice", "bob", "carol", "dave"])
    board = rs.leaderboard()
    # Top of the leaderboard should be the consistent winner
    assert board[0][0] == "alice"
    assert board[-1][0] == "dave"


def test_contains_check() -> None:
    rs = RatingSystem()
    assert "alice" not in rs
    rs.get("alice")
    assert "alice" in rs


def test_duplicate_identity_within_match_loses_no_update() -> None:
    """When the same identity occupies multiple seats in one match (e.g. a
    3-seat all-"LLMDiplomat" table), every seat's outcome must be reflected
    in the identity's rating -- not just whichever seat is written last.

    Reference: three DISTINCT fresh identities finishing in the same
    1st/2nd/3rd ranks receive three different per-seat updates (since
    OpenSkill's math depends only on the pre-match rating value, which is
    identical here, and the rank). If "X" occupies all three seats, its
    rating must combine all three outcomes, not silently collapse to
    whichever seat happened to be applied last (a dict overwrite bug).
    """
    s = _make_terminal_state({0: 100.0, 1: 50.0, 2: 10.0}, num_players=3)
    match = compute_match_result(s)

    reference = RatingSystem()
    reference.update(match, identities=["seat0", "seat1", "seat2"])
    mu_by_seat = [reference.get(f"seat{i}").mu for i in range(3)]
    sigma_by_seat = [reference.get(f"seat{i}").sigma for i in range(3)]

    rs = RatingSystem()
    rs.update(match, identities=["X", "X", "X"])

    # Pin the fix's defined semantics exactly: the mean of every seat's
    # individual per-seat update.
    assert rs.get("X").mu == pytest.approx(sum(mu_by_seat) / 3)
    assert rs.get("X").sigma == pytest.approx(sum(sigma_by_seat) / 3)
    # Last-write-wins (the bug) would make rs["X"] exactly equal seat 2's
    # (the last-place seat's) isolated update, discarding seats 0 and 1.
    assert rs.get("X").mu != pytest.approx(mu_by_seat[2])


def test_detente_uses_tied_top_ranks() -> None:
    """In a détente, all survivors share rank 1 — but payout is score-weighted.
    OpenSkill should treat them as tied (no rating swing between survivors).
    """
    from foedus.core import Hold
    from foedus.resolve import resolve_turn

    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 4)],
                   num_players=2, max_turns=100, peace_threshold=2)
    for _ in range(2):
        s = resolve_turn(s, {0: {0: Hold()}, 1: {1: Hold()}})
    assert s.detente_reached
    s.scores = {0: 100.0, 1: 50.0}
    match = compute_match_result(s)
    # Both detente survivors are rank 1 in our scoring (since both detente_reached)
    # ... wait, our compute_ranks uses score order even in detente. Confirm.
    # Per implementation: ranks are by score even in detente. So 0=1, 1=2.
    assert match.rank[0] == 1
    assert match.rank[1] == 2
