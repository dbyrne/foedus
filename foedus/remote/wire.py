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
    }


def deserialize_map(data: dict[str, Any]) -> Map:
    return Map(
        coords={int(n): tuple(c) for n, c in data["coords"].items()},
        edges={int(n): frozenset(e) for n, e in data["edges"].items()},
        node_types={int(n): NodeType(t) for n, t in data["node_types"].items()},
        home_assignments={int(n): p for n, p in data["home_assignments"].items()},
    )


def serialize_config(c: GameConfig) -> dict[str, Any]:
    return {
        "num_players": c.num_players,
        "max_turns": c.max_turns,
        "fog_radius": c.fog_radius,
        "build_period": c.build_period,
        "detente_threshold": c.detente_threshold,
        "seed": c.seed,
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
        # `log` deliberately omitted (grows unbounded; not strategic).
        # Press v0 fields (press_history, chat_history, betrayals, phase, and
        # round-in-progress scratch) are also omitted from this minimal wire
        # format — they're not needed for `choose_orders`. Add when a client
        # (e.g. foedus-godot) needs them.
    }


def deserialize_state(data: dict[str, Any]) -> GameState:
    # Accept either canonical "mutual_ally_streak" or legacy "peace_streak"
    # for forward-compat with older serialized blobs.
    streak = data.get("mutual_ally_streak", data.get("peace_streak", 0))
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
