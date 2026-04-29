"""JSON-serializable encoding of GameState + Order for the HTTP wire protocol.

The challenge: GameState contains a Map with `frozenset` edges, integer-keyed
dicts, and dataclasses. JSON requires string keys and supports a narrow type
set, so we transcribe — int keys become strings, frozensets become sorted
lists, NodeType becomes its `.value`. Round-trips deterministically.

The resolution log is intentionally NOT transmitted: it grows linearly in turn
count, isn't strategic information, and the agent doesn't need it for the
`choose_orders` decision.
"""

from __future__ import annotations

from typing import Any

from foedus.core import (
    AidSpend,
    GameConfig,
    GameState,
    Hold,
    Map,
    Move,
    NodeType,
    Order,
    SupportHold,
    SupportMove,
    Unit,
)


# --- Map / Config ---


def serialize_map(m: Map) -> dict[str, Any]:
    return {
        "coords": {str(n): list(c) for n, c in m.coords.items()},
        "edges": {str(n): sorted(e) for n, e in m.edges.items()},
        "node_types": {str(n): t.value for n, t in m.node_types.items()},
        "home_assignments": {str(n): p for n, p in m.home_assignments.items()},
        # Bundle 5b (C3): only nodes overriding the default value=1 appear.
        "supply_values": {str(n): v for n, v in m.supply_values.items()},
    }


def deserialize_map(data: dict[str, Any]) -> Map:
    return Map(
        coords={int(n): tuple(c) for n, c in data["coords"].items()},
        edges={int(n): frozenset(e) for n, e in data["edges"].items()},
        node_types={int(n): NodeType(t) for n, t in data["node_types"].items()},
        home_assignments={int(n): p for n, p in data["home_assignments"].items()},
        supply_values={
            int(n): int(v)
            for n, v in (data.get("supply_values") or {}).items()
        },
    )


def serialize_config(c: GameConfig) -> dict[str, Any]:
    return {
        "num_players": c.num_players,
        "max_turns": c.max_turns,
        "fog_radius": c.fog_radius,
        "build_period": c.build_period,
        "detente_threshold": c.detente_threshold,
        "seed": c.seed,
        # Bundle 5b (C3): expose the value-distribution knobs so clients
        # can label high-value supplies and engines can re-replay maps.
        "high_value_supply_fraction": c.high_value_supply_fraction,
        "high_value_supply_yield": c.high_value_supply_yield,
    }


def deserialize_config(data: dict[str, Any]) -> GameConfig:
    # Accept either canonical "detente_threshold" or legacy "peace_threshold"
    # for forward-compat with older serialized blobs. GameConfig's __post_init__
    # mirrors them either way.
    return GameConfig(**data)


# --- GameState ---


def serialize_state(state: GameState) -> dict[str, Any]:
    return {
        "turn": state.turn,
        "map": serialize_map(state.map),
        "units": {
            str(uid): {"id": u.id, "owner": u.owner, "location": u.location}
            for uid, u in state.units.items()
        },
        "ownership": {str(n): o for n, o in state.ownership.items()},
        "scores": {str(p): s for p, s in state.scores.items()},
        "eliminated": sorted(state.eliminated),
        "next_unit_id": state.next_unit_id,
        "config": serialize_config(state.config),
        "mutual_ally_streak": state.mutual_ally_streak,
        "chat_done": sorted(state.chat_done),
        # Bundle 4: aid resource + permanent leverage ledger.
        "aid_tokens": {str(p): n for p, n in state.aid_tokens.items()},
        # aid_given keys are (PlayerId, PlayerId) tuples; flatten to "A,B" strings.
        "aid_given": {f"{a},{b}": n
                      for (a, b), n in state.aid_given.items()},
        "round_aid_pending": {
            str(p): [serialize_aid_spend(s) for s in spends]
            for p, spends in state.round_aid_pending.items()
        },
        # `log` deliberately omitted (grows unbounded; not strategic).
        # Press v0 fields (press_history, chat_history, betrayals, phase, and
        # round_press_pending) are also omitted from this minimal wire format
        # — they're not needed for `choose_orders`. Add when a client
        # (e.g. foedus-godot) needs them.
    }


def deserialize_state(data: dict[str, Any]) -> GameState:
    # Accept either canonical "mutual_ally_streak" or legacy "peace_streak"
    # for forward-compat with older serialized blobs.
    streak = data.get("mutual_ally_streak", data.get("peace_streak", 0))
    aid_given_raw = data.get("aid_given", {}) or {}
    aid_given: dict[tuple[int, int], int] = {}
    for k, v in aid_given_raw.items():
        a_str, b_str = k.split(",", 1)
        aid_given[(int(a_str), int(b_str))] = int(v)
    aid_tokens = {int(p): int(n)
                  for p, n in (data.get("aid_tokens") or {}).items()}
    round_aid_pending = {
        int(p): [deserialize_aid_spend(s) for s in (spends or [])]
        for p, spends in (data.get("round_aid_pending") or {}).items()
    }
    return GameState(
        turn=data["turn"],
        map=deserialize_map(data["map"]),
        units={
            int(uid): Unit(id=u["id"], owner=u["owner"], location=u["location"])
            for uid, u in data["units"].items()
        },
        ownership={int(n): o for n, o in data["ownership"].items()},
        scores={int(p): s for p, s in data["scores"].items()},
        eliminated=set(data["eliminated"]),
        next_unit_id=data["next_unit_id"],
        config=deserialize_config(data["config"]),
        mutual_ally_streak=streak,
        chat_done=set(data.get("chat_done", [])),
        aid_tokens=aid_tokens,
        aid_given=aid_given,
        round_aid_pending=round_aid_pending,
        log=[],
    )


# --- Order ---


def serialize_order(o: Order) -> dict[str, Any]:
    if isinstance(o, Hold):
        return {"type": "Hold"}
    if isinstance(o, Move):
        return {"type": "Move", "dest": o.dest}
    if isinstance(o, SupportHold):
        return {"type": "SupportHold", "target": o.target}
    if isinstance(o, SupportMove):
        return {
            "type": "SupportMove",
            "target": o.target,
            "target_dest": o.target_dest,
        }
    raise ValueError(f"unknown Order subclass: {type(o).__name__}")


def deserialize_order(data: dict[str, Any]) -> Order:
    t = data["type"]
    if t == "Hold":
        return Hold()
    if t == "Move":
        return Move(dest=data["dest"])
    if t == "SupportHold":
        return SupportHold(target=data["target"])
    if t == "SupportMove":
        return SupportMove(target=data["target"], target_dest=data["target_dest"])
    raise ValueError(f"unknown Order type: {t!r}")


def serialize_orders(orders: dict) -> dict[str, dict[str, Any]]:
    """Convenience: dict[UnitId, Order] -> dict[str, dict]."""
    return {str(uid): serialize_order(o) for uid, o in orders.items()}


def deserialize_orders(data: dict[str, dict[str, Any]]) -> dict:
    return {int(uid): deserialize_order(od) for uid, od in data.items()}


def serialize_aid_spend(s: AidSpend) -> dict[str, Any]:
    """Bundle 4: encode an AidSpend (target_unit + target_order) as JSON."""
    return {
        "target_unit": s.target_unit,
        "target_order": serialize_order(s.target_order),
    }


def deserialize_aid_spend(data: dict[str, Any]) -> AidSpend:
    return AidSpend(
        target_unit=int(data["target_unit"]),
        target_order=deserialize_order(data["target_order"]),
    )


def deserialize_intent(data: dict[str, Any]) -> "Intent":
    """Parse a JSON intent payload into a domain `Intent` object.

    Schema:
      {"unit_id": <int>, "declared_order": <order>, "visible_to": null | [<pid>, ...]}

    Used by the press server's /commit endpoint and by orchestrator
    scripts that read intents from JSON. Reuses `deserialize_order`
    for the inner declared_order.
    """
    from foedus.core import Intent
    unit_id = int(data["unit_id"])
    declared_order = deserialize_order(data["declared_order"])
    vt_raw = data.get("visible_to")
    if vt_raw is None:
        visible_to = None
    else:
        visible_to = frozenset(int(x) for x in vt_raw)
    return Intent(
        unit_id=unit_id,
        declared_order=declared_order,
        visible_to=visible_to,
    )
