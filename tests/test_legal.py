"""Tests for legal_orders_for_unit."""

from __future__ import annotations

from foedus.core import (
    Hold,
    Move,
    Support,
    Unit,
)
from foedus.legal import legal_orders_for_unit

from tests.helpers import line_map, make_state, triangle_map


def test_hold_always_first() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 1)])
    legal = legal_orders_for_unit(s, 0)
    assert legal[0] == Hold()


def test_moves_to_all_adjacent_neighbors() -> None:
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 2)])  # node 2 has neighbors 1 and 3
    legal = legal_orders_for_unit(s, 0)
    moves = [o for o in legal if isinstance(o, Move)]
    assert sorted(o.dest for o in moves) == [1, 3]


def test_no_moves_for_isolated_node() -> None:
    m = line_map(1)  # single node, no neighbors
    s = make_state(m, [Unit(0, 0, 0)], num_players=1)
    legal = legal_orders_for_unit(s, 0)
    assert legal == [Hold()]


def test_support_hold_for_each_adjacent_unit() -> None:
    m = line_map(5)
    # u0 at 1 has neighbors 0 and 2. Place units at 0 and 2 (adjacent to u0).
    s = make_state(m, [
        Unit(0, 0, 1),
        Unit(1, 1, 0),
        Unit(2, 1, 2),
    ])
    legal = legal_orders_for_unit(s, 0)
    support_targets = sorted(o.target for o in legal if isinstance(o, Support))
    assert support_targets == [1, 2]


def test_no_support_hold_for_distant_unit() -> None:
    m = line_map(5)
    # u0 at 0; u1 at 4 is not adjacent and shares no neighbors with 0.
    # line_map(5): 0-1-2-3-4. neighbors(0)={1}, neighbors(4)={3}.
    # 3 not in {1}, so u1 is not reachable.
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 0, 4)])
    legal = legal_orders_for_unit(s, 0)
    support_targets = [o.target for o in legal if isinstance(o, Support)]
    assert 1 not in support_targets


def test_support_move_combos() -> None:
    m = line_map(5)
    # u0 at 2 (supporter), u1 at 0. u0 can support u1 (reactive Support).
    # neighbors(2)={1,3}, neighbors(0)={1}. 1 in {1,3} so Support(target=1) valid.
    s = make_state(m, [Unit(0, 0, 2), Unit(1, 0, 0)])
    legal = legal_orders_for_unit(s, 0)
    assert Support(target=1) in legal


def test_no_support_move_attack_on_own_unit() -> None:
    """Reactive Support has no dest filter — own-unit dislodge is irrelevant at enumeration."""
    m = line_map(5)
    # u0 at 2 (p0 supporter). u1 at 0 (p0). u2 at 1 (p0).
    # Under reactive enumeration, Support(target=1) is still valid (u1 is reachable).
    # Support(target=2) is also valid (u2 at 1 is adjacent to 2).
    s = make_state(m, [
        Unit(0, 0, 2),
        Unit(1, 0, 0),
        Unit(2, 0, 1),
    ], num_players=1)
    legal = legal_orders_for_unit(s, 0)
    # Both other units are reachable; verify Support entries exist.
    support_targets = sorted(o.target for o in legal if isinstance(o, Support))
    assert 1 in support_targets
    assert 2 in support_targets


def test_support_move_attack_on_enemy_allowed() -> None:
    """Enumerating support for attack on enemy unit is fine."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 2),
        Unit(1, 0, 0),
        Unit(2, 1, 1),  # enemy
    ])
    legal = legal_orders_for_unit(s, 0)
    assert Support(target=1) in legal


def test_deterministic_order() -> None:
    """Output is in stable order so seeded random sampling is reproducible."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 2), Unit(1, 0, 1), Unit(2, 0, 3)])
    a = legal_orders_for_unit(s, 0)
    b = legal_orders_for_unit(s, 0)
    assert a == b
