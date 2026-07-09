"""S1 corpus autopsy (M-foedus-s1-corpus-autopsy) -- punishment-stage
classification over the sealed canonical Ruleset-v1 campaign.

Read-only over `docs/research/2026-07-04-canonical-campaign-v1/run/`: for the
scripted freerider (Golf), classifies -- per game/turn/seat -- whether
punishing it was ever PROPOSED in press, EXECUTED as a real order, and
whether an execution PAID (see `foedus.eval.punishment_metrics` for the exact
classification rules). Also runs the structural-subsidy test: does honest
LLM<->LLM support entanglement (the "coalition" metric already published in
`results.md` / `scorecard.json`) correlate with LESS resistance mounted
against the freerider's expansion (fewer executed attack actions against it)?

This produces the raw counts + citations that `autopsy-s1.md` is built from;
run it to regenerate/verify those numbers rather than hand-copying them.

Usage:
    PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py \
        --out-dir docs/research/2026-07-04-canonical-campaign-v1/run \
        --scorecard docs/research/2026-07-04-canonical-campaign-v1/scorecard.json
    PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py --out-dir <dir> --json > autopsy.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from foedus.eval.punishment_metrics import classify_game_punishment, pearson_correlation


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_decisions(out_dir: Path, game_id: int, llm_seats: list[int]) -> dict[int, list[dict]]:
    by_seat: dict[int, list[dict]] = {}
    for seat in llm_seats:
        path = out_dir / f"decisions_game{game_id}_seat{seat}.jsonl"
        by_seat[seat] = _load_jsonl(path)
    return by_seat


def build_report(out_dir: str, scorecard_path: str | None = None) -> dict:
    d = Path(out_dir)
    plan = json.loads((d / "campaign_plan.json").read_text())
    freerider_handles = set(plan.get("freerider_handles") or ["DishonestCooperator"])
    sweeps = sorted(_load_jsonl(d / "sweep.jsonl"), key=lambda s: s.get("game_id"))

    per_game = []
    for sweep in sweeps:
        gid = sweep.get("game_id")
        agents = sweep.get("agents") or sweep.get("identity_by_seat") or []
        llm_seats = list(sweep.get("llm_seats") or [])
        freerider_seats = {i for i, name in enumerate(agents) if name in freerider_handles}
        decisions = _load_decisions(d, gid, llm_seats)
        report = classify_game_punishment(
            decisions_by_seat=decisions, llm_seats=llm_seats, freerider_seats=freerider_seats)
        per_game.append({
            "game_id": gid,
            "freerider_seat": (sorted(freerider_seats) or [None])[0],
            "identity_by_seat": agents,
            **report,
        })

    totals = {
        "proposed_count": sum(g["proposed_count"] for g in per_game),
        "executed_count": sum(g["executed_count"] for g in per_game),
        "paid_count": sum(g["paid_count"] for g in per_game),
    }

    structural_subsidy = None
    if scorecard_path and Path(scorecard_path).exists():
        sc = json.loads(Path(scorecard_path).read_text())
        traj_by_game = {t["game_id"]: t for t in sc.get("trajectory", [])}
        series = {"coalition": [], "margin": [], "subsidy": [], "hostility": [],
                  "resistance": [], "proposed": []}
        for g in per_game:
            t = traj_by_game.get(g["game_id"])
            if t is None or t.get("stance_hostility_frac") is None:
                continue
            series["coalition"].append(t["llm_llm_supports"])
            series["margin"].append(t["margin"])
            series["subsidy"].append(t["subsidy"])
            series["hostility"].append(t["stance_hostility_frac"])
            series["resistance"].append(g["executed_count"])
            series["proposed"].append(g["proposed_count"])
        structural_subsidy = {
            "n_games": len(series["coalition"]),
            "coalition_per_game": series["coalition"],
            "resistance_per_game": series["resistance"],
            "pearson_r": pearson_correlation(series["coalition"], series["resistance"]),
            "correlations": {
                "coalition_vs_resistance": pearson_correlation(
                    series["coalition"], series["resistance"]),
                "coalition_vs_margin": pearson_correlation(series["coalition"], series["margin"]),
                "coalition_vs_subsidy": pearson_correlation(
                    series["coalition"], series["subsidy"]),
                "hostility_vs_executed": pearson_correlation(
                    series["hostility"], series["resistance"]),
                "hostility_vs_proposed": pearson_correlation(
                    series["hostility"], series["proposed"]),
            },
        }

    return {
        "out_dir": str(d),
        "freerider_handles": sorted(freerider_handles),
        "totals": totals,
        "per_game": per_game,
        "structural_subsidy_test": structural_subsidy,
    }


def _print_report(rep: dict) -> None:
    print("=== S1 corpus autopsy: punishment-stage classification ===")
    print(f"out-dir: {rep['out_dir']}   freerider(s): {', '.join(rep['freerider_handles'])}")
    print()
    print(f"TOTALS across {len(rep['per_game'])} games -- "
          f"proposed: {rep['totals']['proposed_count']}   "
          f"executed: {rep['totals']['executed_count']}   "
          f"paid: {rep['totals']['paid_count']}")
    print()
    print("per game -- proposed / executed / paid (golf income-drop turns):")
    for g in rep["per_game"]:
        print(f"  g{g['game_id']} (freerider seat {g['freerider_seat']}): "
              f"proposed={g['proposed_count']:<3} executed={g['executed_count']:<3} "
              f"paid={g['paid_count']:<3} drop_turns={g['golf_income_drop_turns']}")
        for e in g["executions"]:
            print(f"      executed  turn={e['game_turn']:<3} seat={e['seat']} kind={e['kind']} "
                  f"unit={e.get('unit_id')}"
                  + (f" target={e.get('target_unit_id')}" if "target_unit_id" in e else ""))
        for p in g["proposals"]:
            extra = ""
            if p["kind"] == "attack_pact_proposal":
                extra = (f" counterparty={p['counterparty']} units={p['attacking_units']} "
                         f"coordinated={p['coordinated']}")
            else:
                extra = f" unit={p.get('unit_id')}"
            print(f"      proposed  turn={p['game_turn']:<3} seat={p['seat']} kind={p['kind']}{extra}")
    ss = rep["structural_subsidy_test"]
    if ss:
        print()
        print("structural-subsidy test (coalition vs. resistance-to-freerider, per game):")
        print(f"  coalition (LLM<->LLM supports): {ss['coalition_per_game']}")
        print(f"  resistance (executed attack actions vs freerider): {ss['resistance_per_game']}")
        print()
        print("mechanism-decomposition correlations (n = "
              f"{ss['n_games']} games; descriptive, not confirmatory):")
        for key, label in [
            ("coalition_vs_resistance", "coalition vs. resistance (executed attacks)"),
            ("coalition_vs_margin", "coalition vs. Golf's margin"),
            ("coalition_vs_subsidy", "coalition vs. subsidy"),
            ("hostility_vs_executed", "hostility vs. executed attacks"),
            ("hostility_vs_proposed", "hostility vs. proposed attacks"),
        ]:
            r = ss["correlations"][key]
            print(f"  r({label}): "
                  + (f"{r:.3f}" if r is not None else "n/a (no variance)"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--scorecard", default=None,
                   help="Path to scorecard.json (for the structural-subsidy test); "
                        "omit to skip that section.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    rep = build_report(args.out_dir, args.scorecard)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        _print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
