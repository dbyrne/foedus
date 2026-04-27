"""Resolution algorithm: contested moves, supports, cuts, cycles, head-to-heads."""

from __future__ import annotations

from foedus.core import (
    Hold,
    Move,
    SupportHold,
    SupportMove,
    Unit,
)
from foedus.resolve import resolve_turn

from tests.helpers import line_map, make_state, triangle_map


def test_bounce_on_equal_strength() -> None:
    """Two unsupported units in a head-to-head bounce — both stay put."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 2),
        Unit(1, 1, 3),
    ])
    out = resolve_turn(s, {
        0: {0: Move(dest=3)},
        1: {1: Move(dest=2)},
    })
    assert out.units[0].location == 2
    assert out.units[1].location == 3


def test_supported_attack_dislodges() -> None:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 2),
        Unit(2, 1, 1),
    ])
    out = resolve_turn(s, {
        0: {0: Move(dest=1), 1: SupportMove(target=0, target_dest=1)},
        1: {2: Hold()},
    })
    assert out.units[0].location == 1
    assert 2 not in out.units  # dislodged


def test_support_cut_by_attack() -> None:
    """A support is cut by an attack on the supporter from elsewhere."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 2),
        Unit(2, 1, 1),
        Unit(3, 1, 3),
    ])
    out = resolve_turn(s, {
        0: {0: Move(dest=1), 1: SupportMove(target=0, target_dest=1)},
        1: {2: Hold(), 3: Move(dest=2)},
    })
    # u3's attack on u1 cuts u1's support. u0 attacks u2 with strength 1 vs 1, bounces.
    assert out.units[0].location == 0
    assert out.units[1].location == 2
    assert out.units[2].location == 1
    assert out.units[3].location == 3


def test_chain_of_moves_succeeds() -> None:
    """A->B, B->C, C->D, D->E should all succeed (each defender vacates)."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 1),
        Unit(2, 0, 2),
        Unit(3, 0, 3),
    ], num_players=1)
    out = resolve_turn(s, {
        0: {0: Move(dest=1), 1: Move(dest=2), 2: Move(dest=3), 3: Move(dest=4)},
    })
    assert out.units[0].location == 1
    assert out.units[1].location == 2
    assert out.units[2].location == 3
    assert out.units[3].location == 4


def test_circular_swap_succeeds() -> None:
    """3-cycle of moves: all three units rotate."""
    m = triangle_map()
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 1),
        Unit(2, 2, 2),
    ], num_players=3)
    out = resolve_turn(s, {
        0: {0: Move(dest=1)},
        1: {1: Move(dest=2)},
        2: {2: Move(dest=0)},
    })
    assert out.units[0].location == 1
    assert out.units[1].location == 2
    assert out.units[2].location == 0


def test_head_to_head_with_support_wins() -> None:
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 1),
        Unit(1, 1, 2),
        Unit(2, 0, 3),
    ])
    out = resolve_turn(s, {
        0: {0: Move(dest=2), 2: SupportMove(target=0, target_dest=2)},
        1: {1: Move(dest=1)},
    })
    # u0 strength 2, u1 strength 1. u0 dislodges u1 in head-to-head.
    assert out.units[0].location == 2
    assert 1 not in out.units


def test_three_way_tie_all_bounce() -> None:
    """Three attackers all targeting the same destination with equal strength all fail."""
    m = triangle_map()
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 1),
        # Player 2 is at node 2, doesn't move; we want u0 and u1 to attack node 2.
        Unit(2, 2, 2),
    ], num_players=3)
    out = resolve_turn(s, {
        0: {0: Move(dest=2)},
        1: {1: Move(dest=2)},
        2: {2: Hold()},
    })
    # Tie at top → all attackers bounce. Defender stays.
    assert out.units[0].location == 0
    assert out.units[1].location == 1
    assert out.units[2].location == 2


def test_same_owner_attack_cannot_dislodge() -> None:
    """Rule X: cannot dislodge own unit, even with foreign support."""
    m = line_map(5)
    # u0 (p0) at 0 attacks u1 (p0) at 1. u2 (p1) at 2 supports u0's attack.
    # Even though strength is 2 vs 1, u0 cannot dislodge own teammate.
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 1),
        Unit(2, 1, 2),
    ])
    out = resolve_turn(s, {
        0: {0: Move(dest=1), 1: Hold()},
        1: {2: SupportMove(target=0, target_dest=1)},
    })
    assert out.units[0].location == 0
    assert out.units[1].location == 1


def test_attack_from_supported_dest_does_not_cut() -> None:
    """SupportMove(target_dest=X): attack on supporter from X does NOT cut the support."""
    m = line_map(4)
    # u0 (p0) at 0 attacks 1. u1 (p0) at 2 supports the move to 1.
    # u2 (p1) at 1 attacks 2 (the supporter's location), but u2 is at 1 = target_dest.
    # That attack should NOT cut u1's support.
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 2),
        Unit(2, 1, 1),
    ])
    out = resolve_turn(s, {
        0: {0: Move(dest=1), 1: SupportMove(target=0, target_dest=1)},
        1: {2: Move(dest=2)},
    })
    # u1's support holds (not cut). u0 strength 2 vs u2 strength 1 (in head-to-head-ish:
    # u0->1, u2->2, NOT a head-to-head because u0's destination is 1 and u2's is 2,
    # not the swap relationship). u0 attacks u2's location 1 with str 2; u2 has moved
    # away (or tries to). If u2's move to 2 fails (blocked by u1 holding), u2 bounces
    # back to 1, then u0's str 2 dislodges u2's str 1.
    assert out.units[0].location == 1
    assert 2 not in out.units  # u2 dislodged
    assert out.units[1].location == 2


def test_same_owner_attack_does_not_cut_support() -> None:
    """A unit's support isn't cut by an attack from its own ally."""
    m = line_map(5)
    # u0 (p0) at 0 attacks 1. u1 (p0) at 2 supports.
    # u2 (p0) at 3 'attacks' u1 at 2 (own ally) — same-owner attacks don't cut.
    # Defender at 1 is u3 (p1).
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 2),
        Unit(2, 0, 3),
        Unit(3, 1, 1),
    ])
    out = resolve_turn(s, {
        0: {0: Move(dest=1), 1: SupportMove(target=0, target_dest=1), 2: Move(dest=2)},
        1: {3: Hold()},
    })
    # u2's same-owner move into u1's location should NOT cut u1's support.
    # u0 should still have strength 2 → dislodge u3.
    assert out.units[0].location == 1
    assert 3 not in out.units


def test_attacker_loses_to_supported_defender() -> None:
    """Defender with supports holds against unsupported attacker."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 1, 0),
        Unit(1, 0, 1),
        Unit(2, 0, 2),
    ])
    out = resolve_turn(s, {
        1: {0: Move(dest=1)},
        0: {1: Hold(), 2: SupportHold(target=1)},
    })
    # u0 attacks with str 1, u1 holds with str 2. u0 bounces.
    assert out.units[0].location == 0
    assert out.units[1].location == 1
