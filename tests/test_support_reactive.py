"""Reactive Support order normalization."""
from foedus.core import Hold, Move, Support
from foedus.resolve import _normalize
from tests.helpers import build_state_with_units


def _adjacent_two_player_state():
    """u0 (P0) at node 0, u1 (P1) at node 1; nodes 0/1/2 fully connected."""
    return build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )


def test_support_adapts_to_target_move():
    s = _adjacent_two_player_state()
    orders = {0: Support(target=1), 1: Move(dest=2)}
    canon_u0 = _normalize(s, 0, Support(target=1), orders)
    assert canon_u0 == Support(target=1)


def test_support_adapts_to_target_hold():
    s = _adjacent_two_player_state()
    orders = {0: Support(target=1), 1: Hold()}
    canon_u0 = _normalize(s, 0, Support(target=1), orders)
    assert canon_u0 == Support(target=1)


def test_support_geometry_break_on_target_move():
    """u0 supports u1; u1 moves to a node u0 is NOT adjacent to."""
    s = build_state_with_units(
        layout={0: 0, 1: 1},
        ownership={0: 0, 1: 1},
        edges={0: {1}, 1: {0, 2}, 2: {1}},  # u0 only adjacent to node 1
        num_players=2,
    )
    orders = {0: Support(target=1), 1: Move(dest=2)}
    canon_u0 = _normalize(s, 0, Support(target=1), orders)
    assert canon_u0 == Hold()


def test_support_pin_satisfied():
    s = _adjacent_two_player_state()
    orders = {0: Support(target=1, require_dest=2), 1: Move(dest=2)}
    canon_u0 = _normalize(s, 0, Support(target=1, require_dest=2), orders)
    assert canon_u0 == Support(target=1, require_dest=2)


def test_support_pin_mismatch_normalizes_to_hold():
    """u0 pins on dest=2; u1 actually moves to dest=0 (a different node)."""
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},  # extra unit so node 0 is reachable from u1
        ownership={0: 0, 1: 1, 2: 0},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )
    orders = {
        0: Support(target=1, require_dest=2),
        1: Move(dest=0),  # not the pinned destination
        2: Hold(),
    }
    canon_u0 = _normalize(s, 0, Support(target=1, require_dest=2), orders)
    assert canon_u0 == Hold()


def test_support_self_dislodge_blocked():
    """u0 supports u1's attack on a node where P0 has another unit."""
    # u0 (P0) at 0, u1 (P1) at 1, u2 (P0) at 2. u1 moves to 2; u0 supports.
    # The support would dislodge P0's own unit -> normalize to Hold.
    s = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2},
        ownership={0: 0, 1: 1, 2: 0},
        edges={0: {1, 2}, 1: {0, 2}, 2: {0, 1}},
        num_players=2,
    )
    orders = {0: Support(target=1), 1: Move(dest=2), 2: Hold()}
    canon_u0 = _normalize(s, 0, Support(target=1), orders)
    assert canon_u0 == Hold()
