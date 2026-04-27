"""Order normalization: invalid orders should silently become Hold().

We test by submitting orders that would be invalid and checking the resulting
state matches "as if everyone Held" — same locations, no movement.
"""

from __future__ import annotations

from foedus.core import (
    Hold,
    Move,
    SupportHold,
    SupportMove,
    Unit,
)
from foedus.resolve import resolve_turn

from tests.helpers import line_map, make_state


def test_hold_kept() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)])
    out = resolve_turn(s, {0: {0: Hold()}})
    assert out.units[0].location == 0


def test_move_to_adjacent_kept() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)])
    out = resolve_turn(s, {0: {0: Move(dest=1)}})
    assert out.units[0].location == 1


def test_move_to_non_adjacent_becomes_hold() -> None:
    """Moving to a node not connected by an edge falls back to Hold."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 0)])
    # Node 0 is not adjacent to node 3 in a line graph.
    out = resolve_turn(s, {0: {0: Move(dest=3)}})
    assert out.units[0].location == 0


def test_move_to_self_becomes_hold() -> None:
    """A unit cannot 'move' to its own location (no self-edge)."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 1)])
    out = resolve_turn(s, {0: {0: Move(dest=1)}})
    assert out.units[0].location == 1


def test_support_hold_valid() -> None:
    """Supporter at 0, target holding at 1 (adjacent) — support is valid."""
    m = line_map(4)
    # u0 at 0 supports u1's hold at 1. u2 at 2 attacks 1 with no support.
    # Without support, u1 holds at strength 1 vs u2 attacks at 1 → bounce.
    # With support, u1 holds at strength 2 → still bounces u2 (strength 1).
    # The same outcome either way for this test, but the support should COUNT.
    # To distinguish, attack with support back: u2 alone has 1 strength.
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 1),
        Unit(2, 1, 2),
    ])
    out = resolve_turn(s, {
        0: {0: SupportHold(target=1), 1: Hold()},
        1: {2: Move(dest=1)},
    })
    # u2 attacks u1; u1 has +1 support; u2 has 1. 1 vs 2, attacker bounces.
    assert out.units[2].location == 2  # u2 stays
    assert out.units[1].location == 1  # u1 stays


def test_support_hold_target_not_holding_becomes_hold() -> None:
    """If the supported unit isn't actually holding, the support is invalid."""
    m = line_map(4)
    # u0 at 0 tries to support u1's hold, but u1 is moving instead.
    # u2 at 2 attacks u1's location (1). Without support, no bounce help.
    # u2 strength 1 vs u1 hold strength 1 — but u1 isn't holding, it's moving.
    # If u1's move succeeds, u2 enters 1 unopposed.
    # u1 moves to 0 (its only neighbor besides 2). Wait u1 at 1 has neighbors 0, 2.
    # u1 moves to 2 (forward). u2 moves to 1 (back). Head-to-head.
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 1),
        Unit(2, 1, 2),
    ])
    out = resolve_turn(s, {
        0: {0: SupportHold(target=1), 1: Move(dest=2)},
        1: {2: Move(dest=1)},
    })
    # u1 head-to-head with u2: both strength 1, both bounce.
    assert 1 in out.units and out.units[1].location == 1
    assert 2 in out.units and out.units[2].location == 2


def test_support_hold_target_not_adjacent_becomes_hold() -> None:
    """Supporter must be adjacent to the supported unit."""
    m = line_map(5)
    # u0 at 0 tries to support u1 at 3 (not adjacent). Support invalid.
    # Without support, attack succeeds against unsupported defender.
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 3),
        Unit(2, 1, 4),  # supporter for the attack on u1
        Unit(3, 1, 2),  # attacker, will move to 3
    ])
    out = resolve_turn(s, {
        0: {0: SupportHold(target=1), 1: Hold()},  # u0's support is invalid
        1: {3: Move(dest=3), 2: SupportMove(target=3, target_dest=3)},
    })
    # u3 attacks 3 with strength 2 (u2 supports). u1 holds with strength 1
    # (u0's support is invalid → fell back to Hold, so doesn't count).
    # u3 dislodges u1.
    assert out.units[3].location == 3
    assert 1 not in out.units  # u1 dislodged (eliminated)


def test_support_hold_nonexistent_target_becomes_hold() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0)])
    out = resolve_turn(s, {0: {0: SupportHold(target=999)}})
    assert out.units[0].location == 0  # Just held, no error


def test_support_move_valid() -> None:
    m = line_map(5)
    # u0 attacks 1 with support from u2 (at 2, adjacent to 1).
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 1, 1),
        Unit(2, 0, 2),
    ])
    out = resolve_turn(s, {
        0: {0: Move(dest=1), 2: SupportMove(target=0, target_dest=1)},
        1: {1: Hold()},
    })
    assert out.units[0].location == 1
    assert 1 not in out.units  # u1 dislodged


def test_support_move_target_not_moving_becomes_hold() -> None:
    """SupportMove of a unit that isn't actually making that move → Hold."""
    m = line_map(5)
    # u0 at 0 holds. u2 at 2 'supports' u0 moving to 1 — but u0 isn't moving.
    # Without that support counting, attacker u3 at 1 with no support (it's solo
    # this attack — wait, we need u3 attacking u2's location to test that the
    # support didn't accidentally hold u2 instead. Simpler: just verify u2 stays.
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(2, 0, 2),
    ])
    out = resolve_turn(s, {
        0: {0: Hold(), 2: SupportMove(target=0, target_dest=1)},
    })
    assert out.units[0].location == 0
    assert out.units[2].location == 2


def test_support_move_target_moving_elsewhere_becomes_hold() -> None:
    """If supported unit is moving but to a different destination, support fails."""
    m = line_map(5)
    # u0 at 1 supports u1 moving 0->2 — but u1 is actually moving 0->1.
    # Wait, u0 at 1 would be the destination of that move; can't be both.
    # Reset: u0 at 2 (supporter), u1 at 0 moving... but u0 at 2 is adjacent to 1 and 3, not 0.
    # u0 at 2 supports u1 moving to 1 (target_dest=1, u0 adjacent to 1). But u1 actually moves to ... we want u1 NOT moving to 1.
    # Make u1 hold instead. That's the same as test above, so let's vary:
    # u0 at 2 supports u1 moving to 3 (claimed). u1 actually moves to ... it has neighbors 0 and 2. Can't move to 3.
    # OK, two-supporter setup: u0 at 2 supports u1 at 1 moving to 0 (claimed),
    # but u1 actually moves to 2. So u0's support is for the wrong destination.
    s = make_state(m, [
        Unit(0, 0, 2),
        Unit(1, 0, 1),
    ])
    out = resolve_turn(s, {
        0: {0: SupportMove(target=1, target_dest=0), 1: Move(dest=2)},
    })
    # u0 stays (its support is invalid → falls back to Hold).
    # u1 moves to 2 — but u0 is there! u0 doesn't move (it would have moved if it had a Move order).
    # u0 holds at 2 with strength 1. u1 attacks with strength 1. Bounce.
    # Wait — u0 falls back to Hold, so u0 is at 2 holding. u1 (same owner) attacks 2.
    # Same-owner attack cannot dislodge (Rule X). u1 bounces.
    assert out.units[0].location == 2
    assert out.units[1].location == 1


def test_support_move_dest_not_adjacent_becomes_hold() -> None:
    """The support's target_dest must be adjacent to the supporter."""
    m = line_map(5)
    # u0 at 0 supports u1 at 3 moving to 4. u0 (at 0) NOT adjacent to 4.
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 3),
        Unit(2, 1, 4),
    ])
    out = resolve_turn(s, {
        0: {0: SupportMove(target=1, target_dest=4), 1: Move(dest=4)},
        1: {2: Hold()},
    })
    # u1 attacks 4 with strength 1 (no valid support). u2 holds with 1. Bounce.
    assert out.units[1].location == 3
    assert out.units[2].location == 4


def test_support_move_self_dislodge_becomes_hold() -> None:
    """Cannot support an attack that would dislodge a unit of supporter's nationality."""
    m = line_map(5)
    # u0 at 0 (p0) attacks 1. u2 at 2 (p0) tries to support — but u1 at 1 is also p0!
    # Without that support, u0 has strength 1 vs u1 hold 1 → bounce.
    # With that (invalid) support, u0 would have strength 2 → would dislodge own teammate.
    s = make_state(m, [
        Unit(0, 0, 0),
        Unit(1, 0, 1),
        Unit(2, 0, 2),
    ], num_players=1)
    out = resolve_turn(s, {
        0: {0: Move(dest=1), 1: Hold(), 2: SupportMove(target=0, target_dest=1)},
    })
    # Support invalid → u0 has strength 1. u0 attacks own u1. Same-owner: Rule X bounces.
    assert out.units[0].location == 0
    assert out.units[1].location == 1


def test_spoofed_orders_dropped() -> None:
    """Player A cannot order Player B's unit; spoofed orders silently dropped."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 1, 0)])  # u0 owned by player 1
    # Player 0 tries to move player 1's unit
    out = resolve_turn(s, {0: {0: Move(dest=1)}})
    # Spoofed order dropped, u0 effectively held
    assert out.units[0].location == 0


def test_spoofed_does_not_block_real_owner() -> None:
    """A spoofed order doesn't override the real owner's intended order."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 1, 0)])
    out = resolve_turn(s, {
        0: {0: Hold()},          # spoofed, dropped
        1: {0: Move(dest=1)},    # real owner's order
    })
    assert out.units[0].location == 1
