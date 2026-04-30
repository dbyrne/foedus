"""Round-trip serialization for the foedus wire protocol."""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    AidSpend,
    DoneCleared,
    GameConfig,
    Hold,
    Intent,
    IntentRevised,
    Move,
    Support,
    SupportLapsed,
    Unit,
)
from foedus.mapgen import generate_map
from foedus.remote.wire import (
    WIRE_PROTOCOL_VERSION,
    deserialize_aid_spend,
    deserialize_done_cleared,
    deserialize_intent,
    deserialize_intent_revised,
    deserialize_map,
    deserialize_order,
    deserialize_orders,
    deserialize_state,
    deserialize_support_lapsed,
    serialize_aid_spend,
    serialize_done_cleared,
    serialize_intent,
    serialize_intent_revised,
    serialize_map,
    serialize_order,
    serialize_orders,
    serialize_state,
    serialize_support_lapsed,
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


def test_support_roundtrip_no_dest() -> None:
    o = Support(target=3)
    assert deserialize_order(serialize_order(o)) == o


def test_support_roundtrip_with_dest() -> None:
    o = Support(target=2, require_dest=7)
    assert deserialize_order(serialize_order(o)) == o


def test_orders_dict_roundtrip() -> None:
    orders = {
        0: Hold(),
        1: Move(dest=5),
        2: Support(target=0),
        3: Support(target=1, require_dest=5),
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


# --- Task 11: new event types + version ---


def test_wire_protocol_version() -> None:
    assert WIRE_PROTOCOL_VERSION == 3


def test_support_lapsed_roundtrip() -> None:
    ev = SupportLapsed(turn=2, supporter=5, target=3, reason="pin_mismatch")
    assert deserialize_support_lapsed(serialize_support_lapsed(ev)) == ev


def test_intent_roundtrip() -> None:
    intent = Intent(unit_id=1, declared_order=Support(target=3), visible_to=frozenset({0, 2}))
    assert deserialize_intent(serialize_intent(intent)) == intent


def test_intent_roundtrip_public() -> None:
    intent = Intent(unit_id=2, declared_order=Move(dest=4), visible_to=None)
    assert deserialize_intent(serialize_intent(intent)) == intent


def test_intent_revised_roundtrip() -> None:
    intent = Intent(unit_id=1, declared_order=Support(target=3), visible_to=frozenset({0}))
    ev = IntentRevised(turn=1, player=0, intent=intent, previous=None, visible_to=frozenset({0}))
    assert deserialize_intent_revised(serialize_intent_revised(ev)) == ev


def test_intent_revised_retraction_roundtrip() -> None:
    prev = Intent(unit_id=1, declared_order=Hold(), visible_to=None)
    ev = IntentRevised(turn=2, player=1, intent=None, previous=prev, visible_to=None)
    assert deserialize_intent_revised(serialize_intent_revised(ev)) == ev


def test_done_cleared_roundtrip() -> None:
    ev = DoneCleared(turn=3, player=0, source_player=1, source_unit=7)
    assert deserialize_done_cleared(serialize_done_cleared(ev)) == ev


def test_state_roundtrip_with_new_event_lists() -> None:
    """support_lapses, intent_revisions, done_clears all round-trip via GameState."""
    from dataclasses import replace as dc_replace
    cfg = GameConfig(num_players=3, seed=42, max_turns=20)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    intent = Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)
    s = dc_replace(
        s,
        support_lapses=[SupportLapsed(turn=1, supporter=0, target=1, reason="geometry_break")],
        intent_revisions=[
            IntentRevised(turn=1, player=0, intent=intent, previous=None, visible_to=None)
        ],
        done_clears=[DoneCleared(turn=1, player=2, source_player=0, source_unit=0)],
    )
    blob = serialize_state(s)
    s2 = deserialize_state(blob)
    assert s2.support_lapses == s.support_lapses
    assert s2.intent_revisions == s.intent_revisions
    assert s2.done_clears == s.done_clears
    assert blob.get("wire_version") == 3


def test_state_roundtrip_without_new_event_lists_defaults_empty() -> None:
    """Pre-Task-11 blobs (no event list keys) deserialize cleanly with empty lists."""
    cfg = GameConfig(num_players=2, seed=1, max_turns=5)
    m = generate_map(2, seed=1)
    s = initial_state(cfg, m)
    blob = serialize_state(s)
    blob.pop("support_lapses", None)
    blob.pop("intent_revisions", None)
    blob.pop("done_clears", None)
    s2 = deserialize_state(blob)
    assert s2.support_lapses == []
    assert s2.intent_revisions == []
    assert s2.done_clears == []
