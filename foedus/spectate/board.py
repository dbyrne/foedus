"""Per-turn declared-orders + support-classification frames from LLM seats'
decision logs, for the replay theater (View 2).

Stances/declared intents for ALL seats (LLM and heuristic alike) come from
the transcript (see transcript.py) -- render_transcript walks state.press_
history, which every agent populates. Actual submitted ORDERS are only
recoverable for LLM seats (their decision log's "orders"-phase raw_response);
a heuristic/freerider seat's real orders are never logged anywhere (the
engine's resolution log is intentionally not persisted -- see CLAUDE.md),
so the freerider's moves stay opaque here just as they do to the LLM table
itself. This module fills in that orders/subsidy layer on top of the
transcript's stance/intent layer; it does not replace it.

Reuses foedus.eval.memory_metrics (the existing subsidy/coordination
extractor) rather than re-parsing raw_response JSON from scratch.
"""

from __future__ import annotations

from foedus.agents.llm.parse import coerce_id, extract_json_with_recovery
from foedus.eval.memory_metrics import (
    parse_visible_owners,
    supports_targeting_freerider,
    supports_targeting_llm_seats,
)


def _parse_orders(raw_response: str) -> dict:
    try:
        data, _ = extract_json_with_recovery(raw_response or "")
    except Exception:  # noqa: BLE001 - untrusted logged text, never crash a report
        return {}
    if not isinstance(data, dict):
        return {}
    orders = data.get("orders")
    return orders if isinstance(orders, dict) else {}


def _classify_support_targets(
    orders: dict, owners: dict[int, int], fr_set: set[int], llm_set: set[int], seat: int
) -> dict[str, str]:
    """Per-order (not just per-turn-aggregate) classification of each
    Support order's target ownership, so the replay UI can badge each one
    individually rather than only showing a turn-level count."""
    out: dict[str, str] = {}
    for uid, od in orders.items():
        if not (isinstance(od, dict) and od.get("type") == "Support"):
            continue
        target = coerce_id(od.get("target"))
        owner = owners.get(target) if target is not None else None
        if owner in fr_set:
            out[uid] = "freerider"
        elif owner == seat:
            out[uid] = "self"
        elif owner is not None and owner in llm_set:
            out[uid] = "llm"
        else:
            out[uid] = "unknown"
    return out


def build_turn_frames(
    decisions_by_seat: dict[int, list[dict]],
    freerider_seats: list[int],
    llm_seats: list[int],
) -> list[dict]:
    """One frame per turn: {"turn", "orders": {seat: {...}}, "fell_back":
    {seat: bool}, "subsidy": int, "llm_llm_supports": int, "support_targets":
    {seat: {unit_id_str: "freerider"|"llm"|"self"|"unknown"}}}, sorted by
    turn. support_targets classifies EACH Support order individually (the
    subsidy/llm_llm_supports ints are just its aggregate counts) so the
    replay UI can badge a specific order, not only show a turn-level total."""
    fr_set = set(freerider_seats)
    llm_set = set(llm_seats)
    frames_by_turn: dict[int, dict] = {}

    for seat, records in decisions_by_seat.items():
        for rec in records:
            if rec.get("phase") != "orders":
                continue
            turn = rec.get("turn")
            frame = frames_by_turn.setdefault(turn, {
                "turn": turn, "orders": {}, "fell_back": {},
                "subsidy": 0, "llm_llm_supports": 0, "support_targets": {},
            })
            raw = rec.get("raw_response", "")
            orders = _parse_orders(raw)
            frame["orders"][seat] = orders
            frame["fell_back"][seat] = bool(rec.get("fell_back"))
            owners = parse_visible_owners(rec.get("prompt", {}).get("user", ""), seat)
            frame["subsidy"] += supports_targeting_freerider(raw, owners, fr_set)
            frame["llm_llm_supports"] += supports_targeting_llm_seats(
                raw, owners, llm_set, seat
            )
            frame["support_targets"][seat] = _classify_support_targets(
                orders, owners, fr_set, llm_set, seat
            )

    return [frames_by_turn[t] for t in sorted(frames_by_turn)]
