"""Degeneracy flags + self-note extraction for the Haiku fitness probe
(M-foedus-haiku-fitness-probe).

Supplements the parse-fail / subsidy / coalition metrics already produced by
``foedus.eval.memory_metrics.scorecard`` and ``foedus.eval.punishment_metrics``
-- this module covers only what neither of those already computes: whether a
seat degenerates into all-Hold or state-blind repeated orders, and pulling
the model's own verbatim cross-game self-notes for quoting.
"""

from __future__ import annotations

import json
from pathlib import Path


def _orders_dict(raw_response: str) -> dict | None:
    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return None
    orders = data.get("orders") if isinstance(data, dict) else None
    return orders if isinstance(orders, dict) else None


def is_all_hold(orders: dict) -> bool:
    """True if every declared order is a Hold, or none were declared at all
    (an empty submission silently defaults every unit to Hold)."""
    if not orders:
        return True
    return all(
        isinstance(o, dict) and o.get("type") == "Hold" for o in orders.values()
    )


def all_hold_turns(decisions: list[dict]) -> list[int]:
    """Turn numbers where this seat's orders-phase submission was all-Hold."""
    turns = []
    for rec in decisions:
        if rec.get("phase") != "orders":
            continue
        orders = _orders_dict(rec.get("raw_response") or "")
        if orders is None:
            continue
        if is_all_hold(orders):
            turns.append(rec["turn"])
    return sorted(turns)


def repeated_identical_order_runs(
    decisions: list[dict], min_repeat: int = 3
) -> list[list[int]]:
    """Runs of >= min_repeat consecutive turn numbers where the orders-phase
    submission is byte-for-byte the same dict -- a degeneracy flag regardless
    of what changed on the board meanwhile. A gap in turn numbers, or an
    unparseable submission, breaks a run."""
    orders_turns = sorted(
        (rec["turn"], _orders_dict(rec.get("raw_response") or ""))
        for rec in decisions
        if rec.get("phase") == "orders"
    )
    runs: list[list[int]] = []
    current: list[int] = []
    prev_orders = None
    prev_turn = None
    for turn, orders in orders_turns:
        chains = (
            orders is not None
            and prev_orders is not None
            and orders == prev_orders
            and prev_turn is not None
            and turn == prev_turn + 1
        )
        if chains:
            if not current:
                current = [prev_turn]
            current.append(turn)
        else:
            if len(current) >= min_repeat:
                runs.append(current)
            current = []
        prev_orders = orders
        prev_turn = turn
    if len(current) >= min_repeat:
        runs.append(current)
    return runs


def self_notes_for_identity(out_dir: str | Path, identity: str) -> list[dict]:
    """Read every campaign_memory_game*_seat*.json under out_dir belonging to
    `identity` and return [{game_index, entrant_identity, self_note}] sorted
    by game. Each game's memory file is cumulative (it carries every prior
    game's record too), so only the highest-numbered game file is read."""
    out = Path(out_dir)
    latest_by_game: dict[int, Path] = {}
    for path in out.glob("campaign_memory_game*_seat*.json"):
        data = json.loads(path.read_text())
        if data.get("entrant_identity") != identity:
            continue
        game_index = data.get("game_index")
        if game_index is not None:
            latest_by_game[game_index] = path

    if not latest_by_game:
        return []

    newest = latest_by_game[max(latest_by_game)]
    data = json.loads(newest.read_text())
    notes = []
    for rec in data.get("records", []):
        note = rec.get("self_note")
        if note:
            notes.append({
                "game_index": rec.get("game_index"),
                "entrant_identity": identity,
                "self_note": note,
            })
    return sorted(notes, key=lambda n: n["game_index"])
