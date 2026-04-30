"""Round-trip serialization for the foedus wire protocol."""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    AidSpend,
    GameConfig,
    Hold,
    Move,
    SupportHold,
    SupportMove,
    Unit,
)
from foedus.mapgen import generate_map
from foedus.remote.wire import (
    deserialize_aid_spend,
    deserialize_map,
    deserialize_order,
    deserialize_orders,
    deserialize_state,
    serialize_aid_spend,
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
    assert s2.config.detente_threshold == cfg.detente_threshold


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


def test_chat_done_roundtrips() -> None:
    """Bundle 6: chat_done is preserved across (de)serialize."""
    from foedus.press import signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 2)

    blob = serialize_state(s)
    assert sorted(blob["chat_done"]) == [0, 2]

    s2 = deserialize_state(blob)
    assert s2.chat_done == {0, 2}


def test_deserialize_state_without_chat_done_defaults_empty() -> None:
    """Backward-compat: blobs from older clients (no chat_done key)
    deserialize cleanly with an empty chat_done."""
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    blob = serialize_state(s)
    # Simulate a pre-Bundle-6 blob by removing the new key.
    blob.pop("chat_done", None)
    s2 = deserialize_state(blob)
    assert s2.chat_done == set()


def test_aid_spend_roundtrip() -> None:
    """AidSpend serialize/deserialize preserves target_unit."""
    spend = AidSpend(target_unit=7)
    blob = serialize_aid_spend(spend)
    out = deserialize_aid_spend(blob)
    assert out == spend


def test_state_roundtrip_with_bundle4_fields() -> None:
    """aid_tokens, aid_given, round_aid_pending all round-trip."""
    cfg = GameConfig(num_players=3, seed=42, max_turns=20)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s = replace(
        s,
        aid_tokens={0: 4, 1: 2, 2: 0},
        aid_given={(0, 1): 5, (1, 0): 2, (2, 0): 1},
        round_aid_pending={
            0: [AidSpend(target_unit=1)],
        },
    )
    blob = serialize_state(s)
    s2 = deserialize_state(blob)
    assert s2.aid_tokens == s.aid_tokens
    assert s2.aid_given == s.aid_given
    assert s2.round_aid_pending == s.round_aid_pending


def test_deserialize_state_without_bundle4_fields_defaults_empty() -> None:
    """Backward-compat: pre-Bundle-4 blobs deserialize cleanly with
    empty aid_tokens / aid_given / round_aid_pending.
    """
    cfg = GameConfig(num_players=2, seed=1, max_turns=5)
    m = generate_map(2, seed=1)
    s = initial_state(cfg, m)
    blob = serialize_state(s)
    blob.pop("aid_tokens", None)
    blob.pop("aid_given", None)
    blob.pop("round_aid_pending", None)
    s2 = deserialize_state(blob)
    assert s2.aid_tokens == {}
    assert s2.aid_given == {}
    assert s2.round_aid_pending == {}


def test_map_roundtrip_with_supply_values() -> None:
    """Bundle 5b (C3): supply_values round-trips through serialize_map."""
    m = generate_map(4, seed=42)
    m = replace(m, supply_values={k: 2 for k in list(m.coords.keys())[:3]})
    out = deserialize_map(serialize_map(m))
    assert out.supply_values == m.supply_values


def test_map_deserialize_without_supply_values_defaults_empty() -> None:
    """Pre-Bundle-5b blobs (no supply_values key) deserialize cleanly."""
    m = generate_map(4, seed=42)
    blob = serialize_map(m)
    blob.pop("supply_values", None)
    out = deserialize_map(blob)
    assert out.supply_values == {}
