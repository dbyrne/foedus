"""Validate the require_dest ("pin") Support legality fix against the sealed
S1.5 corpus (M-foedus-require-dest-legality-fix) -- READ-ONLY, zero new games,
zero LLM calls.

S1.5 (autopsy-s1-5-confounds.md, Check 3) proved that 12 geometrically-valid
`require_dest` Support orders backing an attack on the freerider were silently
coerced to Hold() by `foedus.agents.llm.parse.parse_order`'s legality gate --
`foedus.legal.legal_orders_for_unit` never enumerates pin variants, so the
`order in legal` membership check dropped every one, even though
`foedus.resolve._normalize` accepts them. That confound gated the clean
canonical re-run.

This script re-derives, from the sealed corpus, the decisive before/after of
the fix: for each of those 12 attack-backing pin Supports it re-runs the NOW
FIXED `parse_order` against the exact replayed state that decision saw, and
shows the order now parses as a legal `Support(target=T, require_dest=D)`
(reaches the resolver) instead of being coerced to Hold. It cross-checks each
against `_normalize_with_reason` (the resolver's own acceptance) and against
`counterfactual_reinstate_order` (whether the paired mover flips fail->success
once the order reaches the resolver), reproducing S1.5's 9-of-12 flip figure.

The replay itself deliberately still reproduces the CORPUS-ERA gate (pins ->
Hold) so the sealed run is reconstructed faithfully (see
`foedus.eval.resolution_replay._reapply_corpus_era_pin_gate`); the fix's effect
is measured here at the parser boundary + via the counterfactual, NOT by
letting the replay reinstate orders. This is why the numbers here match S1.5's
counterfactual exactly rather than shifting.

Usage:
    PYTHONPATH=. python3 scripts/foedus_require_dest_fix_validation.py \
        --out-dir docs/research/2026-07-04-canonical-campaign-v1/run
    PYTHONPATH=. python3 scripts/foedus_require_dest_fix_validation.py \
        --out-dir <dir> --json > validation.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from foedus.core import Archetype, Support  # noqa: E402
from foedus.eval._coverage import assert_coverage  # noqa: E402
from foedus.eval.punishment_metrics import classify_game_punishment  # noqa: E402
from foedus.eval.resolution_replay import (  # noqa: E402
    counterfactual_reinstate_order,
    geometric_legality,
    replay_game,
)
from foedus.legal import legal_orders_for_unit  # noqa: E402
from foedus.agents.llm.parse import parse_order  # noqa: E402
from foedus.resolve import _normalize_with_reason  # noqa: E402

import foedus_s1_autopsy as autopsy  # noqa: E402
from foedus_s1_5_confound_check import _raw_declared_order  # noqa: E402


def _order_to_dict(order) -> dict:
    """The parse_order INPUT dict for a declared Support pin -- what the model
    emitted and what parse_order must now accept (mirrors render.py's schema)."""
    if isinstance(order, Support):
        d = {"type": "Support", "target": order.target}
        if order.require_dest is not None:
            d["require_dest"] = order.require_dest
        return d
    raise ValueError(f"not a Support: {order!r}")


def analyze_game(out_dir: Path, sweep_row: dict, plan: dict) -> list[dict]:
    game_id = sweep_row["game_id"]
    seed = sweep_row["seed"]
    agent_names = sweep_row["agents"]
    llm_seats = list(sweep_row["llm_seats"])
    board = plan["board"]
    freerider_handles = set(plan.get("freerider_handles") or ["DishonestCooperator"])
    freerider_class = plan.get("freerider_class", "DishonestCooperator")
    freerider_seats = {
        i: freerider_class for i, name in enumerate(agent_names) if name in freerider_handles
    }

    decisions_by_seat = autopsy._load_decisions(out_dir, game_id, llm_seats)
    total_records = sum(len(v) for v in decisions_by_seat.values())
    assert_coverage(total_records, total_records,
                     f"require_dest fix validation game {game_id}: decision records read")
    _final_state, resolutions = replay_game(
        seed=seed, num_players=board["num_players"], max_turns=board["max_turns"],
        archetype=Archetype(board["archetype"]), map_radius=board["map_radius"],
        llm_seats=llm_seats, freerider_seats=freerider_seats,
        decisions_by_seat=decisions_by_seat,
    )
    by_turn = {r.turn: r for r in resolutions}
    report = classify_game_punishment(
        decisions_by_seat=decisions_by_seat, llm_seats=llm_seats,
        freerider_seats=set(freerider_seats),
    )

    rows: list[dict] = []
    for e in report["executions"]:
        if e["kind"] != "attack_support":
            continue
        seat, turn, unit_id = e["seat"], e["game_turn"], e["unit_id"]
        rec = next(
            (r for r in decisions_by_seat.get(seat, [])
             if r["turn"] == turn and r["phase"] == "orders"),
            None,
        )
        declared = _raw_declared_order(rec, unit_id) if rec is not None else None
        res = by_turn.get(turn)
        if declared is None or res is None:
            continue
        if not (isinstance(declared, Support) and declared.require_dest is not None):
            continue

        flat = {uid: o for pmap in res.orders_by_player.values() for uid, o in pmap.items()}
        legality = geometric_legality(res.prev_state, unit_id, declared, flat)
        if legality != "illegal_parser_gap":
            continue

        # BEFORE: the corpus-era gate (pin not a candidate -> coerced to Hold).
        legal = legal_orders_for_unit(res.prev_state, unit_id)
        before_in_candidate_list = declared in legal  # False, by construction

        # AFTER: the FIXED parser, on the exact dict the model emitted.
        order_dict = _order_to_dict(declared)
        after_order, after_was_legal = parse_order(order_dict, legal)

        # Cross-check: the resolver's own acceptance for this pin, and the
        # counterfactual mover flip once the order reaches the resolver.
        canon, reason = _normalize_with_reason(res.prev_state, unit_id, declared, flat)
        resolver_accepts = isinstance(canon, Support)

        mover_id = e.get("target_unit_id")
        _cs, counter_detail = counterfactual_reinstate_order(
            res.prev_state, res.orders_by_player, player=seat,
            unit_id=unit_id, order=declared,
        )
        actual_mover = res.detail.outcome.get(mover_id)
        counter_mover = counter_detail.outcome.get(mover_id)

        rows.append({
            "game_id": game_id, "turn": turn, "seat": seat, "unit_id": unit_id,
            "declared": repr(declared),
            "before_in_candidate_list": before_in_candidate_list,
            "before_parse": "Hold() (was_legal=False)",
            "after_parse": f"{after_order!r} (was_legal={after_was_legal})",
            "after_accepted": after_was_legal and after_order == declared,
            "resolver_accepts": resolver_accepts,
            "resolver_reason": reason,
            "mover_unit_id": mover_id,
            "actual_mover_outcome": actual_mover,
            "counterfactual_mover_outcome": counter_mover,
            "mover_flips_to_success": actual_mover != "success" and counter_mover == "success",
        })
    return rows


def build_report(out_dir: str) -> dict:
    d = Path(out_dir)
    plan = json.loads((d / "campaign_plan.json").read_text())
    sweeps = sorted(autopsy._load_jsonl(d / "sweep.jsonl"), key=lambda s: s.get("game_id"))
    rows = [r for sweep in sweeps for r in analyze_game(d, sweep, plan)]
    return {
        "out_dir": str(d),
        "attack_backing_pin_supports": rows,
        "totals": {
            "count": len(rows),
            "after_accepted": sum(1 for r in rows if r["after_accepted"]),
            "resolver_accepts": sum(1 for r in rows if r["resolver_accepts"]),
            "before_in_candidate_list": sum(1 for r in rows if r["before_in_candidate_list"]),
            "mover_flips_to_success": sum(1 for r in rows if r["mover_flips_to_success"]),
        },
    }


def _print_report(rep: dict) -> None:
    rows = rep["attack_backing_pin_supports"]
    t = rep["totals"]
    print("=== require_dest fix validation (12 attack-backing pin Supports) ===")
    print(f"out-dir: {rep['out_dir']}")
    print()
    hdr = f"{'game':>4} {'turn':>4} {'seat':>4} {'unit':>4}  {'before':>16}  {'after (fixed parse_order)':>34}  {'mover':>5}  flip"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        flip = "fail->success" if r["mover_flips_to_success"] else \
            (f"{r['actual_mover_outcome']}->{r['counterfactual_mover_outcome']}")
        print(f"{r['game_id']:>4} {r['turn']:>4} {r['seat']:>4} {r['unit_id']:>4}  "
              f"{'dropped->Hold':>16}  {r['after_parse']:>34}  "
              f"{str(r['mover_unit_id']):>5}  {flip}")
    print()
    print(f"total attack-backing pin Supports: {t['count']}")
    print(f"  before fix -- in candidate list (reach resolver): {t['before_in_candidate_list']} "
          f"(all coerced to Hold)")
    print(f"  after fix  -- accepted by parse_order (reach resolver): {t['after_accepted']}")
    print(f"  resolver (_normalize) accepts: {t['resolver_accepts']}")
    print(f"  paired mover flips fail->success (counterfactual): {t['mover_flips_to_success']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    rep = build_report(args.out_dir)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        _print_report(rep)
    t = rep["totals"]
    # The decisive assertions: every attack-backing pin was dropped before
    # (0 in the candidate list) and is now accepted by the fixed parser and by
    # the resolver; the counterfactual flip count reproduces S1.5's 9-of-12.
    ok = (
        t["count"] == 12
        and t["before_in_candidate_list"] == 0
        and t["after_accepted"] == 12
        and t["resolver_accepts"] == 12
        and t["mover_flips_to_success"] == 9
    )
    if not ok:
        print(
            "ERROR: validation did not reproduce the S1.5 expectation "
            "(12 dropped->accepted, 9/12 mover flips). Do NOT rationalize a "
            "mismatch -- investigate.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
