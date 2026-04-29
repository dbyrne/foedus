"""Tests for the seat-permutation helper in the depth-eval orchestrator."""
import sys
from pathlib import Path

# The orchestrator is a script, not a module; import it as one for testing.
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))

import foedus_depth_eval as orch  # noqa: E402


def test_unique_perms_all_same():
    perms = orch._unique_seat_permutations(("A", "A", "A", "A"))
    assert perms == [("A", "A", "A", "A")]


def test_unique_perms_one_distinct():
    """1 X + 3 Y → 4 unique perms (X at each of 4 seats)."""
    perms = orch._unique_seat_permutations(("X", "Y", "Y", "Y"))
    assert len(perms) == 4
    # Each seat 0..3 should host X exactly once.
    x_positions = sorted(p.index("X") for p in perms)
    assert x_positions == [0, 1, 2, 3]


def test_unique_perms_two_pairs():
    """2 A + 2 B → C(4,2) = 6 unique perms."""
    perms = orch._unique_seat_permutations(("A", "A", "B", "B"))
    assert len(perms) == 6


def test_unique_perms_all_distinct():
    """4 distinct → 24 unique perms."""
    perms = orch._unique_seat_permutations(("A", "B", "C", "D"))
    assert len(perms) == 24


def test_unique_perms_deterministic_order():
    """Sorted output for reproducibility."""
    p1 = orch._unique_seat_permutations(("X", "Y", "Y", "Y"))
    p2 = orch._unique_seat_permutations(("X", "Y", "Y", "Y"))
    assert p1 == p2
    assert p1 == sorted(p1)
