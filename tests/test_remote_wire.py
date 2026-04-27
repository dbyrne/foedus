"""Round-trip serialization for the foedus wire protocol."""

from __future__ import annotations

from foedus.core import (
    GameConfig,
    Hold,
    Move,
    SupportHold,
    SupportMove,
    Unit,
)
from foedus.mapgen import generate_map
from foedus.remote.wire import (
    deserialize_map,
    deserialize_order,
    deserialize_orders,
    deserialize_state,
    serialize_map,
    serialize_order,
    serialize_orders,
    serialize_state,
)
from foedus.resolve import initial_state


def test_map_roundtrip() -> None:
    m = generate_map(4, seed=42)
    m2 = deserialize_map(serialize_map(m))
    assert m2.coords == m.coords
    assert m2.edges == m.edges
    assert m2.node_types == m.node_types
    assert m2.home_assignments == m.home_assignments


def test_state_roundtrip_initial() -> None:
    cfg = GameConfig(num_players=4, seed=42, max_turns=20)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    s2 = deserialize_state(serialize_state(s))
    assert s2.turn == s.turn
    assert {uid: (u.owner, u.location) for uid, u in s2.units.items()} == \
           {uid: (u.owner, u.location) for uid, u in s.units.items()}
    assert s2.ownership == s.ownership
    assert s2.scores == s.scores
    assert s2.eliminated == s.eliminated
    assert s2.next_unit_id == s.next_unit_id
    assert s2.config.num_players == cfg.num_players
    assert s2.config.peace_threshold == cfg.peace_threshold


def test_state_does_not_transmit_log() -> None:
    """Log is intentionally omitted to keep wire payloads bounded."""
    cfg = GameConfig(num_players=2, seed=1, max_turns=5)
    m = generate_map(2, seed=1)
    s = initial_state(cfg, m)
    s.log.extend(["a", "b", "c"])
    blob = serialize_state(s)
    assert "log" not in blob
    s2 = deserialize_state(blob)
    assert s2.log == []


def test_hold_roundtrip() -> None:
    o = Hold()
    assert deserialize_order(serialize_order(o)) == o


def test_move_roundtrip() -> None:
    o = Move(dest=5)
    assert deserialize_order(serialize_order(o)) == o


def test_support_hold_roundtrip() -> None:
    o = SupportHold(target=3)
    assert deserialize_order(serialize_order(o)) == o


def test_support_move_roundtrip() -> None:
    o = SupportMove(target=2, target_dest=7)
    assert deserialize_order(serialize_order(o)) == o


def test_orders_dict_roundtrip() -> None:
    orders = {
        0: Hold(),
        1: Move(dest=5),
        2: SupportHold(target=0),
        3: SupportMove(target=1, target_dest=5),
    }
    assert deserialize_orders(serialize_orders(orders)) == orders


def test_unknown_order_type_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        deserialize_order({"type": "Magic", "x": 1})
