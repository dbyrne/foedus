"""Reciprocation-memory experiment scorecard.

Reads a run out-dir written by scripts/foedus_llm_diplomat_run.py and prints a
per-game + aggregate scorecard: freerider margin over the mean LLM score, winner
per game, the subsidy metric (LLM Support orders targeting a freerider unit), the
per-turn stance-toward-freerider trajectory, and per-seat parse-fail.

Compare two arms (baseline vs. memory) by pointing --out-dir at each run and
reading the two aggregates side by side; pass --json for machine output.

Usage:
    PYTHONPATH=. python3 scripts/foedus_memory_metrics.py \
        --out-dir runs/arm_a_baseline
    PYTHONPATH=. python3 scripts/foedus_memory_metrics.py \
        --out-dir runs/arm_b_memory --freerider DishonestCooperator --json

Output uses labels/symbols rather than colour (colourblind-safe).
"""

from __future__ import annotations

import argparse
import json
import sys

from foedus.eval.memory_metrics import scorecard


def _fmt_traj(trajectory: list[dict]) -> str:
    # e.g. "t0[H2 N0 A0]  t1[H1 N0 A1]" — hostile/neutral/ally counts per turn.
    parts = []
    for t in trajectory:
        parts.append(
            f"t{t['turn']}[H{t['hostile']} N{t['neutral']} A{t['ally']}"
            + (f" ?{t['unknown']}" if t.get("unknown") else "")
            + "]"
        )
    return "  ".join(parts)


def _print_report(agg: dict, label: str) -> None:
    print(f"=== reciprocation-memory scorecard: {label} ===")
    print(
        f"games: {agg['n_games']}   "
        f"freerider wins: {agg['freerider_wins']}/{agg['n_games']} "
        f"(win-rate {agg['freerider_win_rate']:.0%})"
    )
    print(
        f"mean margin (freerider - LLM mean): {agg['mean_margin']:+.2f}   "
        f"mean subsidy/game: {agg['mean_subsidy_per_game']:.2f}   "
        f"mean LLM<->LLM supports/game: "
        f"{agg.get('mean_llm_llm_supports_per_game', 0.0):.2f}   "
        f"parse-fail: {agg['parse_fail_rate']:.1%}"
    )
    print()
    print("per game:")
    for g in agg["per_game"]:
        outcome = (
            "freerider WON" if g["freerider_won"] else "LLM table held"
        )
        print(
            f"  game {g['game_id']} (seed {g['seed']}): "
            f"freerider {g['freerider_score']:.1f} vs LLM mean "
            f"{g['llm_mean_score']:.1f} (margin {g['margin']:+.1f})  "
            f"[{outcome}]  subsidy={g['subsidy']}  "
            f"LLM<->LLM supports={g.get('llm_llm_supports', 0)}"
        )
        print(f"      stance-toward-freerider: {_fmt_traj(g['stance_trajectory'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True,
                        help="Run out-dir (contains sweep.jsonl, telemetry.jsonl, "
                             "decisions_*.jsonl).")
    parser.add_argument("--freerider", default="DishonestCooperator",
                        help="Comma-separated heuristic name(s) treated as the "
                             "freerider seat(s).")
    parser.add_argument("--label", default=None,
                        help="Label for the report header (defaults to --out-dir).")
    parser.add_argument("--json", action="store_true",
                        help="Emit the aggregate scorecard as JSON instead of text.")
    args = parser.parse_args(argv)

    freerider_names = {n.strip() for n in args.freerider.split(",") if n.strip()}
    agg = scorecard(args.out_dir, freerider_names)

    if args.json:
        print(json.dumps(agg, indent=2))
    else:
        _print_report(agg, args.label or args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
