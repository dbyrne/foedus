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

from foedus.agents.llm.parse import extract_json_with_recovery


def _orders_dict(raw_response: str) -> dict | None:
    """Parse a decision's raw_response the same way the diplomat / the rest
    of the eval tooling does (foedus.eval.punishment_metrics._extract):
    real responses are always markdown-fenced (```json ... ```), never bare
    JSON, so a bare json.loads silently fails on every real record."""
    try:
        data, _ = extract_json_with_recovery(raw_response or "")
    except Exception:  # noqa: BLE001 - untrusted logged text, never crash a report
        return None
    orders = data.get("orders") if isinstance(data, dict) else None
    return orders if isinstance(orders, dict) else None


def orders_parse_coverage(decisions: list[dict]) -> tuple[int, int]:
    """(parsed, total) among this seat's orders-phase records the LIVE
    harness itself did NOT flag as a fallback -- how many `raw_response`
    values yield a usable orders dict via `_orders_dict`, out of how many
    orders-phase records exist where `fell_back` isn't True.

    `fell_back=True` records are excluded from both counts. Note this is a
    broader category than "genuinely unparseable JSON": `parse_orders_response`
    (foedus/agents/llm/parse.py) sets it on ANY per-order issue -- an
    illegal Move/Support, an unknown unit id, or merely needing the label
    sanitizer -- not only on a totally malformed response. Empirically (all
    552 real orders-phase records across the sealed corpora as of this
    writing) most `fell_back=True` records DO still parse fine via
    `_orders_dict`; excluding them anyway is conservative rather than
    precise -- it shrinks the denominator to "records the harness didn't
    flag for ANY reason" rather than "records that are valid JSON," which
    costs a little coverage signal but never causes a false positive here.
    The one case this exclusion could theoretically hide -- a record with
    `fell_back=False` that `_orders_dict` still can't parse (e.g. valid JSON
    whose `"orders"` key is absent entirely: `parse_orders_response` treats
    that as `{}`/no-op, but `_orders_dict` returns None) -- occurred 0/552
    times in the real corpora checked; if it starts occurring, the 95%
    threshold in `assert_coverage` is what would catch it, same as any
    other coverage gap.

    A corpus-level caller (scripts/foedus_haiku_probe_report.py) sums this
    across every seat/game and feeds the totals into
    `foedus.eval._coverage.assert_coverage` -- this function itself stays a
    plain counter and never raises, so a single bad record (or an
    intentionally tiny/partial test fixture) doesn't trip anything here;
    only a real corpus-wide coverage gap should fail loudly, at the boundary
    that actually owns "is this a corpus worth trusting."
    """
    orders_recs = [
        r for r in decisions
        if r.get("phase") == "orders" and not r.get("fell_back")
    ]
    parsed = sum(
        1 for r in orders_recs
        if _orders_dict(r.get("raw_response") or "") is not None
    )
    return parsed, len(orders_recs)


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
                "game_index": (rec.get("facts") or {}).get("game_index"),
                "entrant_identity": identity,
                "self_note": note,
            })
    return sorted(notes, key=lambda n: (n["game_index"] is None, n["game_index"]))
