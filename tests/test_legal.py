"""Tests for legal_orders_for_unit."""

from __future__ import annotations

from foedus.core import (
    Hold,
    Move,
    SupportHold,
    SupportMove,
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
    sh_targets = sorted(o.target for o in legal if isinstance(o, SupportHold))
    assert sh_targets == [1, 2]


def test_no_support_hold_for_distant_unit() -> None:
    m = line_map(5)
    # u0 at 0; u1 at 4 is not adjacent.
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 0, 4)])
    legal = legal_orders_for_unit(s, 0)
    sh_targets = [o.target for o in legal if isinstance(o, SupportHold)]
    assert 1 not in sh_targets


def test_support_move_combos() -> None:
    m = line_map(5)
    # u0 at 2 (supporter), u1 at 0. u0 can support u1 moving to 1
    # (target_dest=1, adjacent to both u0 and u1).
    s = make_state(m, [Unit(0, 0, 2), Unit(1, 0, 0)])
    legal = legal_orders_for_unit(s, 0)
    sm = [o for o in legal if isinstance(o, SupportMove)]
    assert SupportMove(target=1, target_dest=1) in sm


def test_no_support_move_attack_on_own_unit() -> None:
    """Cannot enumerate support for an attack that would dislodge own teammate."""
    m = line_map(5)
    # u0 at 2 (p0 supporter). u1 at 0 (p0 attacker). u2 at 1 (p0 defender).
    # u0 cannot support u1's move to 1 (would dislodge own u2).
    s = make_state(m, [
        Unit(0, 0, 2),
        Unit(1, 0, 0),
        Unit(2, 0, 1),
    ], num_players=1)
    legal = legal_orders_for_unit(s, 0)
    bad = SupportMove(target=1, target_dest=1)
    assert bad not in legal


def test_support_move_attack_on_enemy_allowed() -> None:
    """Enumerating support for attack on enemy unit is fine."""
    m = line_map(5)
    s = make_state(m, [
        Unit(0, 0, 2),
        Unit(1, 0, 0),
        Unit(2, 1, 1),  # enemy
    ])
    legal = legal_orders_for_unit(s, 0)
    expected = SupportMove(target=1, target_dest=1)
    assert expected in legal


def test_deterministic_order() -> None:
    """Output is in stable order so seeded random sampling is reproducible."""
    m = line_map(5)
    s = make_state(m, [Unit(0, 0, 2), Unit(1, 0, 1), Unit(2, 0, 3)])
    a = legal_orders_for_unit(s, 0)
    b = legal_orders_for_unit(s, 0)
    assert a == b
