"""Analyzer — reads JSONL sim sweep output, emits depth-metrics report.

Usage:
    PYTHONPATH=. python3 scripts/foedus_sim_analyze.py path/to/sweep.jsonl

Outputs a markdown report to stdout.

Spec: docs/superpowers/specs/2026-04-29-sim-sweep-design.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_records(paths: list[Path]) -> list[dict]:
    out = []
    for p in paths:
        with p.open() as f:
            for line in f:
                out.append(json.loads(line))
    return out


def per_heuristic_scores(records: list[dict]) -> dict[str, list[float]]:
    """Return {heuristic_name: [final_score for each game-instance]}."""
    out = defaultdict(list)
    for r in records:
        for player_idx, name in enumerate(r["agents"]):
            out[name].append(r["final_scores"][player_idx])
    return out


def per_pairing_winrate(records: list[dict]) -> dict[tuple[str, str], float]:
    """Return {(A, B): fraction of games where A scored higher than B}."""
    pair_counts: dict[tuple[str, str], list[int]] = defaultdict(
        lambda: [0, 0])  # [A_wins, total]
    for r in records:
        agents = r["agents"]
        scores = r["final_scores"]
        for i, name_i in enumerate(agents):
            for j, name_j in enumerate(agents):
                if i == j:
                    continue
                pair_counts[(name_i, name_j)][1] += 1
                if scores[i] > scores[j]:
                    pair_counts[(name_i, name_j)][0] += 1
    return {k: (v[0] / v[1] if v[1] > 0 else 0.0)
            for k, v in pair_counts.items()}


def lead_change_count(record: dict) -> int:
    """Count unique-leader changes across the game's score history."""
    score_per_turn = record["score_per_turn"]
    sorted_turns = sorted(int(k) for k in score_per_turn.keys())
    last_leader = None
    changes = 0
    for t in sorted_turns:
        scores = score_per_turn[str(t)]
        max_score = max(scores)
        leaders = [i for i, s in enumerate(scores) if s == max_score]
        leader = leaders[0] if len(leaders) == 1 else None
        if leader != last_leader:
            changes += 1
        last_leader = leader
    return changes


def order_type_distribution(records: list[dict]) -> dict[str, float]:
    total = Counter()
    for r in records:
        total.update(r["order_type_counts"])
    grand_total = sum(total.values())
    return {k: v / grand_total for k, v in total.items()} if grand_total else {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+",
                        help="One or more JSONL files from foedus_sim_sweep.py")
    args = parser.parse_args()
    paths = [Path(p) for p in args.paths]
    records = load_records(paths)
    n_games = len(records)
    print(f"# Bundle 7 — Sim Sweep Analysis\n")
    print(f"**Total games analyzed:** {n_games}\n")

    # Per-heuristic mean / median / stddev.
    print("## Per-heuristic final score (across all game-instances)\n")
    print("| Heuristic | n games | mean | median | stddev | min | max |")
    print("|---|---|---|---|---|---|---|")
    scores = per_heuristic_scores(records)
    for name in sorted(scores.keys()):
        s = scores[name]
        stdev = statistics.stdev(s) if len(s) > 1 else 0.0
        print(f"| {name} | {len(s)} | "
              f"{statistics.mean(s):.2f} | {statistics.median(s):.2f} | "
              f"{stdev:.2f} | "
              f"{min(s):.0f} | {max(s):.0f} |")
    print()

    # Pairing win-rate matrix.
    print("## Pairing win-rate matrix (row vs column)\n")
    print("Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).\n")
    names = sorted(scores.keys())
    print("| | " + " | ".join(names) + " |")
    print("|---" + "|---" * len(names) + "|")
    winrate = per_pairing_winrate(records)
    for r in names:
        row = [f"**{r}**"]
        for c in names:
            if r == c:
                row.append("—")
            else:
                wr = winrate.get((r, c), 0.0)
                row.append(f"{wr:.2f}")
        print("| " + " | ".join(row) + " |")
    print()

    # Lead-change frequency.
    leads_per_game = [lead_change_count(r) for r in records]
    print(f"## Lead-change frequency\n")
    print(f"Mean lead changes per game: **{statistics.mean(leads_per_game):.2f}**\n")
    print(f"Median: {statistics.median(leads_per_game):.0f}, "
          f"max: {max(leads_per_game)}, "
          f"games with 0 changes: {sum(1 for x in leads_per_game if x == 0)}\n")

    # Order-type distribution.
    print(f"## Order-type distribution (across all games × all players × all turns)\n")
    od = order_type_distribution(records)
    for ot in ("Hold", "Move", "SupportHold", "SupportMove"):
        print(f"- **{ot}:** {od.get(ot, 0.0):.1%}")
    print()

    # Dislodgement rate.
    dislodge_per_game = [r["dislodgement_count"] for r in records]
    print(f"## Dislodgement rate\n")
    print(f"Mean dislodgements per game: **{statistics.mean(dislodge_per_game):.2f}**\n")
    print(f"Games with at least one dislodgement: "
          f"{sum(1 for x in dislodge_per_game if x > 0)} of {n_games}\n")

    # Betrayer success vs TitForTat.
    print(f"## Betrayer success vs TitForTat\n")
    print("When Betrayer X and TitForTat appear in the same game, "
          "average score difference (X − TitForTat):\n")
    for betrayer in ("Sycophant", "OpportunisticBetrayer"):
        diffs = []
        for r in records:
            ag = r["agents"]
            scores_ = r["final_scores"]
            if betrayer in ag and "TitForTat" in ag:
                b_idx = ag.index(betrayer)
                t_idx = ag.index("TitForTat")
                diffs.append(scores_[b_idx] - scores_[t_idx])
        if diffs:
            mean_diff = statistics.mean(diffs)
            sign = "+" if mean_diff > 0 else ""
            print(f"- **{betrayer}** vs TitForTat (n={len(diffs)}): "
                  f"{sign}{mean_diff:.2f} "
                  f"({'betrayer profits' if mean_diff > 0 else 'TitForTat punishes' if mean_diff < 0 else 'wash'})")
        else:
            print(f"- **{betrayer}**: no co-occurrence games found")
    print()

    # Score gap winner vs 2nd.
    gaps = []
    for r in records:
        scores_ = sorted(r["final_scores"], reverse=True)
        gaps.append(scores_[0] - scores_[1])
    print(f"## Winner vs 2nd-place score gap\n")
    print(f"Mean gap: {statistics.mean(gaps):.2f}, "
          f"median: {statistics.median(gaps):.0f}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
