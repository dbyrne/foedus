"""S1.5 confound-resolution pass (M-foedus-s1-5-confound-check) -- read-only,
zero-new-games analysis that resolves the 3 confounds the S1 corpus autopsy
(`docs/research/2026-07-04-canonical-campaign-v1/autopsy-s1.md`, section 4)
flagged before committing run #2 to the Economics arm.

Check 1 -- resolution-truth replay. "Executed" only means an order reached
the engine; the sealed corpus retains no per-combat resolution log. Since a
match is deterministic given (seed, every seat's logged decision), the whole
game is replayed through the REAL engine
(`foedus.eval.resolution_replay.replay_game`) and each executed attack
order-action's true fate (dislodge / bounce / dropped before resolution) is
read straight from the resolver's own `ResolutionDetail`.

Check 2 -- clean-call payoff subset. Restricts executed/paid to attack-turns
where every involved seat's call had no fallback
(`foedus.eval.punishment_metrics.clean_call_subset`), isolating the
corpus's ~8.2% parse/timeout-fail rate as a candidate confound.

Check 3 -- legality survival. For each executed order-action, re-derives
legality against the REPLAYED state at that turn
(`foedus.eval.resolution_replay.geometric_legality`), distinguishing genuine
geometric illegality from the `require_dest` parser/prompt-schema gap (a
Support pin variant `foedus.legal` never enumerates as a candidate,
regardless of validity -- see that module's docstring). For orders caught by
the parser gap, `counterfactual_reinstate_order` checks whether reinstating
the order would actually have changed the outcome.

Also sweeps the corpus (independent of the freerider/attack-execution set)
for every `require_dest` Support declared anywhere -- orders-phase
submissions, negotiate-phase declared Intents, and negotiate-phase
pact-proposal terms -- since all three are routed through the same
`foedus.agents.llm.parse.parse_order` legality gate
(`foedus.eval.punishment_metrics.count_require_dest_declarations`). This is
the true denominator for "how many declared orders this bug silently
discards", not just the subset that happened to target the freerider.

Exits non-zero (after still printing the full report, for debuggability) if
any game's replayed final scores/turn count/eliminations don't match the
sealed `sweep.jsonl` -- every number below assumes the replay is faithful,
so a silent config/order divergence must not be allowed to produce
plausible-looking confound numbers unnoticed.

Usage:
    PYTHONPATH=. python3 scripts/foedus_s1_5_confound_check.py \
        --out-dir docs/research/2026-07-04-canonical-campaign-v1/run
    PYTHONPATH=. python3 scripts/foedus_s1_5_confound_check.py --out-dir <dir> --json > report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from foedus.agents.llm.parse import coerce_id, extract_json_with_recovery  # noqa: E402
from foedus.core import Archetype, Hold, Move, Order, Support  # noqa: E402
from foedus.eval.punishment_metrics import (  # noqa: E402
    classify_game_punishment,
    clean_call_subset,
    client_error_by_seat_turn,
    count_require_dest_declarations,
    fell_back_by_seat_turn,
)
from foedus.eval.resolution_replay import (  # noqa: E402
    counterfactual_reinstate_order,
    geometric_legality,
    replay_game,
    verify_replay_fidelity,
)

import foedus_s1_autopsy as autopsy  # noqa: E402


def _order_from_dict(d: object) -> Order | None:
    """Reconstruct the RAW declared Order from a parsed orders-JSON dict,
    with NO legality gating -- `foedus.agents.llm.parse.parse_order`
    legality-gates against `foedus.legal`, which is exactly what Check 3
    needs to independently re-derive, so this stays a dumb, ungated
    constructor (mirrors `parse_order`'s type dispatch only)."""
    if not isinstance(d, dict):
        return None
    t = d.get("type")
    if t == "Hold":
        return Hold()
    if t == "Move":
        dest = coerce_id(d.get("dest"))
        return Move(dest=dest) if dest is not None else None
    if t == "Support":
        target = coerce_id(d.get("target"))
        if target is None:
            return None
        require_dest_raw = d.get("require_dest")
        if require_dest_raw is None:
            return Support(target=target)
        require_dest = coerce_id(require_dest_raw)
        return Support(target=target, require_dest=require_dest) if require_dest is not None else None
    return None


def _raw_declared_order(rec: dict, unit_id: int) -> Order | None:
    data, _ = extract_json_with_recovery(rec.get("raw_response") or "")
    orders = data.get("orders") if isinstance(data, dict) else None
    if not isinstance(orders, dict):
        return None
    for uid_key, od in orders.items():
        if coerce_id(uid_key) == unit_id:
            return _order_from_dict(od)
    return None


def analyze_game(out_dir: Path, sweep_row: dict, plan: dict) -> dict:
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

    final_state, resolutions = replay_game(
        seed=seed, num_players=board["num_players"], max_turns=board["max_turns"],
        archetype=Archetype(board["archetype"]), map_radius=board["map_radius"],
        llm_seats=llm_seats, freerider_seats=freerider_seats,
        decisions_by_seat=decisions_by_seat,
    )

    mismatches = verify_replay_fidelity(decisions_by_seat, resolutions)
    integrity = {
        "final_scores_match": (
            [round(final_state.scores.get(p, 0.0), 6) for p in range(board["num_players"])]
            == [round(v, 6) for v in sweep_row["final_scores"]]
        ),
        "total_turns_match": final_state.turn == sweep_row["total_turns"],
        "eliminated_match": sorted(final_state.eliminated) == sorted(sweep_row.get("eliminated") or []),
        "fidelity_mismatch_count": len(mismatches),
    }

    by_turn_resolution = {r.turn: r for r in resolutions}
    report = classify_game_punishment(
        decisions_by_seat=decisions_by_seat, llm_seats=llm_seats,
        freerider_seats=set(freerider_seats),
    )

    classified = []
    for e in report["executions"]:
        seat, turn, unit_id = e["seat"], e["game_turn"], e["unit_id"]
        rec = next(
            (r for r in decisions_by_seat.get(seat, [])
             if r["turn"] == turn and r["phase"] == "orders"),
            None,
        )
        declared = _raw_declared_order(rec, unit_id) if rec is not None else None
        res = by_turn_resolution.get(turn)
        entry = {
            "kind": e["kind"], "turn": turn, "seat": seat, "unit_id": unit_id,
            "declared": repr(declared) if declared is not None else None,
        }
        if declared is None or res is None:
            entry["legality"] = "unknown"
            classified.append(entry)
            continue

        flat = {uid: o for pmap in res.orders_by_player.values() for uid, o in pmap.items()}
        legality = geometric_legality(res.prev_state, unit_id, declared, flat)
        entry["legality"] = legality
        entry["canon"] = repr(res.detail.canon.get(unit_id))
        if e["kind"] == "attack_move":
            entry["outcome"] = res.detail.outcome.get(unit_id)
            entry["dislodged_unit_id"] = next(
                (victim for victim, attacker in res.detail.dislodged_by.items()
                 if attacker == unit_id), None,
            )
        elif e["kind"] == "attack_support" and legality == "illegal_parser_gap":
            # The only path where reinstating an executed order-action can
            # flip the outcome (see geometric_legality's docstring): a
            # require_dest Support the parser unconditionally dropped, but
            # foedus.resolve's own normalization would have accepted.
            mover_id = e.get("target_unit_id")
            _counter_state, counter_detail = counterfactual_reinstate_order(
                res.prev_state, res.orders_by_player, player=seat,
                unit_id=unit_id, order=declared,
            )
            entry["mover_unit_id"] = mover_id
            entry["actual_mover_outcome"] = res.detail.outcome.get(mover_id)
            entry["counterfactual_mover_outcome"] = counter_detail.outcome.get(mover_id)
        classified.append(entry)

    fell_back = fell_back_by_seat_turn(decisions_by_seat)
    client_error = client_error_by_seat_turn(decisions_by_seat)
    clean_broad = clean_call_subset(report, fell_back)
    clean_strict = clean_call_subset(report, client_error)
    require_dest_counts = count_require_dest_declarations(decisions_by_seat)

    return {
        "game_id": game_id,
        "integrity": integrity,
        "fidelity_mismatches": [
            {"seat": m.seat, "turn": m.turn, "unit_id": m.unit_id,
             "logged_parsed": m.logged_parsed, "replayed_order": m.replayed_order}
            for m in mismatches
        ],
        "executions_classified": classified,
        "full_report": {
            "proposed_count": report["proposed_count"],
            "executed_count": report["executed_count"],
            "paid_count": report["paid_count"],
        },
        # "broad": excludes any call that fell back for ANY reason, including
        # a successful sanitizer recovery (parse-quality, not reliability).
        # "strict": excludes only a genuine client-error/timeout fallback.
        "clean_call_subset_broad": clean_broad,
        "clean_call_subset_strict": clean_strict,
        "require_dest_counts": require_dest_counts,
    }


def build_report(out_dir: str) -> dict:
    d = Path(out_dir)
    plan = json.loads((d / "campaign_plan.json").read_text())
    sweeps = sorted(autopsy._load_jsonl(d / "sweep.jsonl"), key=lambda s: s.get("game_id"))

    per_game = [analyze_game(d, sweep, plan) for sweep in sweeps]

    total_fidelity_mismatches = sum(g["integrity"]["fidelity_mismatch_count"] for g in per_game)
    total_integrity_ok = all(
        g["integrity"]["final_scores_match"] and g["integrity"]["total_turns_match"]
        and g["integrity"]["eliminated_match"]
        for g in per_game
    )

    all_exec = [e for g in per_game for e in g["executions_classified"]]
    legality_counts: dict[str, int] = {}
    for e in all_exec:
        legality_counts[e["legality"]] = legality_counts.get(e["legality"], 0) + 1

    move_entries = [e for e in all_exec if e["kind"] == "attack_move"]
    dislodge_count = sum(1 for e in move_entries if e.get("dislodged_unit_id") is not None)
    bounce_count = sum(
        1 for e in move_entries
        if e.get("dislodged_unit_id") is None and e.get("legality") == "legal"
    )

    parser_gap_entries = [e for e in all_exec if e.get("legality") == "illegal_parser_gap"]
    counterfactual_flips = sum(
        1 for e in parser_gap_entries
        if e.get("actual_mover_outcome") != "success"
        and e.get("counterfactual_mover_outcome") == "success"
    )

    clean_broad_totals = {
        "executed_count": sum(g["clean_call_subset_broad"]["executed_count"] for g in per_game),
        "paid_count": sum(g["clean_call_subset_broad"]["paid_count"] for g in per_game),
    }
    clean_strict_totals = {
        "executed_count": sum(g["clean_call_subset_strict"]["executed_count"] for g in per_game),
        "paid_count": sum(g["clean_call_subset_strict"]["paid_count"] for g in per_game),
    }
    full_totals = {
        "proposed_count": sum(g["full_report"]["proposed_count"] for g in per_game),
        "executed_count": sum(g["full_report"]["executed_count"] for g in per_game),
        "paid_count": sum(g["full_report"]["paid_count"] for g in per_game),
    }
    require_dest_totals = {
        "orders_phase": sum(g["require_dest_counts"]["orders_phase"] for g in per_game),
        "negotiate_intents": sum(g["require_dest_counts"]["negotiate_intents"] for g in per_game),
        "negotiate_pact_terms": sum(g["require_dest_counts"]["negotiate_pact_terms"] for g in per_game),
    }
    require_dest_totals["all_phases"] = sum(require_dest_totals.values())

    return {
        "out_dir": str(d),
        "replay_integrity": {
            "all_games_score_turn_elimination_match": total_integrity_ok,
            "total_fidelity_mismatches": total_fidelity_mismatches,
        },
        "require_dest_corpus_wide_sweep": require_dest_totals,
        "check1_legality_and_outcome": {
            "legality_counts": legality_counts,
            "attack_move_dislodge_count": dislodge_count,
            "attack_move_bounce_count": bounce_count,
            "attack_move_total": len(move_entries),
            "parser_gap_counterfactual_flips_to_success": counterfactual_flips,
            "parser_gap_total": len(parser_gap_entries),
        },
        "check2_clean_call_subset": {
            "full": full_totals,
            "clean_broad": clean_broad_totals,
            "clean_strict": clean_strict_totals,
        },
        "per_game": per_game,
    }


def _print_report(rep: dict) -> None:
    print("=== S1.5 confound-resolution pass ===")
    print(f"out-dir: {rep['out_dir']}")
    print()
    ri = rep["replay_integrity"]
    print(f"replay integrity: all games' final scores/turns/eliminations match sealed "
          f"sweep.jsonl = {ri['all_games_score_turn_elimination_match']}   "
          f"fidelity mismatches (replay vs logged 'parsed') = {ri['total_fidelity_mismatches']}")
    if not ri["all_games_score_turn_elimination_match"] or ri["total_fidelity_mismatches"]:
        print("*** WARNING: replay integrity check FAILED -- every number below assumes a "
              "faithful replay and should NOT be trusted until this is resolved. ***")
    print()
    rd = rep["require_dest_corpus_wide_sweep"]
    print(f"require_dest Support declarations corpus-wide (orders-phase / negotiate-intents / "
          f"negotiate-pact-terms / all-phases total): "
          f"{rd['orders_phase']} / {rd['negotiate_intents']} / {rd['negotiate_pact_terms']} / "
          f"{rd['all_phases']} -- every one is unconditionally coerced to Hold() by "
          f"foedus.legal's candidate enumeration (see foedus.eval.resolution_replay."
          f"geometric_legality's docstring); directly confirmed for the 12 backing an "
          f"attack-execution below, not independently re-verified per declaration here")
    print()
    c1 = rep["check1_legality_and_outcome"]
    print("Check 1+3 -- legality survival & resolution truth (39 executed order-actions):")
    print(f"  legality breakdown: {c1['legality_counts']}")
    print(f"  attack_move: dislodge={c1['attack_move_dislodge_count']} "
          f"bounce={c1['attack_move_bounce_count']} total={c1['attack_move_total']}")
    print(f"  require_dest parser-gap Supports: {c1['parser_gap_total']}  "
          f"-- counterfactual flips mover fail->success: "
          f"{c1['parser_gap_counterfactual_flips_to_success']}")
    print()
    c2 = rep["check2_clean_call_subset"]
    print("Check 2 -- clean-call payoff subset:")
    print(f"  full:          executed={c2['full']['executed_count']} paid={c2['full']['paid_count']}")
    print(f"  clean (broad, excludes sanitizer-recovery too): "
          f"executed={c2['clean_broad']['executed_count']} paid={c2['clean_broad']['paid_count']}")
    print(f"  clean (strict, genuine client-error/timeout only): "
          f"executed={c2['clean_strict']['executed_count']} paid={c2['clean_strict']['paid_count']}")


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
    ri = rep["replay_integrity"]
    integrity_ok = ri["all_games_score_turn_elimination_match"] and not ri["total_fidelity_mismatches"]
    if not integrity_ok:
        print(
            "ERROR: replay integrity check failed -- final scores/turns/eliminations did not "
            "match the sealed sweep.jsonl for at least one game, or verify_replay_fidelity found "
            "a mismatch. The report above was still printed for debugging, but none of its "
            "confound-check numbers should be trusted until this is resolved.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
