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
    DoneCleared,
    GameConfig,
    GameState,
    Hold,
    Intent,
    IntentRevised,
    Map,
    Move,
    NodeType,
    Order,
    Support,
    SupportLapsed,
    Unit,
)

WIRE_PROTOCOL_VERSION = 3


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
        # Task 11: new event lists from the alliance/support/intent redesign.
        "support_lapses": [serialize_support_lapsed(e) for e in state.support_lapses],
        "intent_revisions": [serialize_intent_revised(e) for e in state.intent_revisions],
        "done_clears": [serialize_done_cleared(e) for e in state.done_clears],
        "wire_version": WIRE_PROTOCOL_VERSION,
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
        support_lapses=[
            deserialize_support_lapsed(e)
            for e in (data.get("support_lapses") or [])
        ],
        intent_revisions=[
            deserialize_intent_revised(e)
            for e in (data.get("intent_revisions") or [])
        ],
        done_clears=[
            deserialize_done_cleared(e)
            for e in (data.get("done_clears") or [])
        ],
    )


# --- Order ---


def serialize_order(o: Order) -> dict[str, Any]:
    if isinstance(o, Hold):
        return {"type": "Hold"}
    if isinstance(o, Move):
        return {"type": "Move", "dest": o.dest}
    if isinstance(o, Support):
        d: dict[str, Any] = {"type": "Support", "target": o.target}
        if o.require_dest is not None:
            d["require_dest"] = o.require_dest
        return d
    raise ValueError(f"unknown Order subclass: {type(o).__name__}")


def deserialize_order(data: dict[str, Any]) -> Order:
    t = data["type"]
    if t == "Hold":
        return Hold()
    if t == "Move":
        return Move(dest=data["dest"])
    if t == "Support":
        return Support(
            target=data["target"],
            require_dest=data.get("require_dest"),
        )
    raise ValueError(f"unknown Order type: {t!r}")


def serialize_orders(orders: dict) -> dict[str, dict[str, Any]]:
    """Convenience: dict[UnitId, Order] -> dict[str, dict]."""
    return {str(uid): serialize_order(o) for uid, o in orders.items()}


def deserialize_orders(data: dict[str, dict[str, Any]]) -> dict:
    return {int(uid): deserialize_order(od) for uid, od in data.items()}


def serialize_aid_spend(s: AidSpend) -> dict[str, Any]:
    """Bundle 4: encode an AidSpend (target_unit) as JSON."""
    return {
        "target_unit": s.target_unit,
    }


def deserialize_aid_spend(data: dict[str, Any]) -> AidSpend:
    return AidSpend(
        target_unit=int(data["target_unit"]),
    )


def serialize_intent(intent: Intent) -> dict[str, Any]:
    """Encode an Intent as JSON."""
    return {
        "unit_id": intent.unit_id,
        "declared_order": serialize_order(intent.declared_order),
        "visible_to": sorted(intent.visible_to) if intent.visible_to is not None else None,
    }


def deserialize_intent(data: dict[str, Any]) -> Intent:
    """Parse a JSON intent payload into a domain `Intent` object.

    Schema:
      {"unit_id": <int>, "declared_order": <order>, "visible_to": null | [<pid>, ...]}

    Used by the press server's /commit endpoint and by orchestrator
    scripts that read intents from JSON. Reuses `deserialize_order`
    for the inner declared_order.
    """
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


# --- New event types (Task 11) ---


def serialize_intent_revised(ev: IntentRevised) -> dict[str, Any]:
    return {
        "turn": ev.turn,
        "player": ev.player,
        "intent": serialize_intent(ev.intent) if ev.intent is not None else None,
        "previous": serialize_intent(ev.previous) if ev.previous is not None else None,
        "visible_to": sorted(ev.visible_to) if ev.visible_to is not None else None,
    }


def deserialize_intent_revised(data: dict[str, Any]) -> IntentRevised:
    vt_raw = data.get("visible_to")
    return IntentRevised(
        turn=int(data["turn"]),
        player=int(data["player"]),
        intent=deserialize_intent(data["intent"]) if data.get("intent") is not None else None,
        previous=deserialize_intent(data["previous"]) if data.get("previous") is not None else None,
        visible_to=frozenset(int(x) for x in vt_raw) if vt_raw is not None else None,
    )


def serialize_support_lapsed(ev: SupportLapsed) -> dict[str, Any]:
    return {
        "turn": ev.turn,
        "supporter": ev.supporter,
        "target": ev.target,
        "reason": ev.reason,
    }


def deserialize_support_lapsed(data: dict[str, Any]) -> SupportLapsed:
    return SupportLapsed(
        turn=int(data["turn"]),
        supporter=int(data["supporter"]),
        target=int(data["target"]),
        reason=data["reason"],
    )


def serialize_done_cleared(ev: DoneCleared) -> dict[str, Any]:
    return {
        "turn": ev.turn,
        "player": ev.player,
        "source_player": ev.source_player,
        "source_unit": ev.source_unit,
    }


def deserialize_done_cleared(data: dict[str, Any]) -> DoneCleared:
    return DoneCleared(
        turn=int(data["turn"]),
        player=int(data["player"]),
        source_player=int(data["source_player"]),
        source_unit=int(data["source_unit"]),
    )
