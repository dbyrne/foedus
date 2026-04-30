"""Compute OpenSkill (TrueSkill-family) ratings from sim-sweep output.

Reads one or more sweep JSONL files (from `foedus_sim_sweep.py`),
replays each game's final ranks through `foedus.rating.RatingSystem`,
and prints the leaderboard sorted by conservative rating
(`mu - 3·sigma`).

Usage:
    PYTHONPATH=. python scripts/foedus_compute_ratings.py path/to/sweep.jsonl [...]

Optional `--metrics-out` writes the leaderboard to a `metrics.yaml` in
castra's benchmarks schema (`pip install castra`); use this when you
want `castra exp compare` to show mu / sigma / conservative deltas
across sweeps. Soft dep — the script runs without castra if the flag
isn't passed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path


def _ranks_from_scores(
    final_scores: list[float], eliminated: list[int],
) -> dict[int, int]:
    """Compute per-seat ranks from raw final_scores, with eliminated seats
    sharing the worst rank (n_survivors + 1).

    Ties are competition-ranked: seats with the same score get the same
    rank; the next distinct score skips the appropriate count (1, 2, 2, 4
    style). Matches `compute_match_result`'s convention.
    """
    n = len(final_scores)
    survivors = [i for i in range(n) if i not in eliminated]
    eliminated_set = set(eliminated)

    survivors_sorted = sorted(survivors, key=lambda i: -final_scores[i])
    rank: dict[int, int] = {}
    cur_rank = 1
    last_score: float | None = None
    survivors_seen = 0
    for seat in survivors_sorted:
        score = final_scores[seat]
        survivors_seen += 1
        if last_score is None or score < last_score:
            cur_rank = survivors_seen
            last_score = score
        rank[seat] = cur_rank

    worst = survivors_seen + 1 if survivors_seen else 1
    for seat in eliminated_set:
        rank[seat] = worst
    return rank


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="+", type=Path,
                   help="Sweep JSONL file(s) to process.")
    p.add_argument("--metrics-out", default=None,
                   help="Optional metrics.yaml path (castra benchmarks schema). "
                        "Requires `pip install castra`.")
    args = p.parse_args(argv)

    from foedus.rating import RatingSystem
    from foedus.scoring import MatchResult

    rs = RatingSystem()
    n_games = 0
    n_skipped = 0
    seat_appearances: dict[str, int] = {}

    for path in args.paths:
        with path.open() as f:
            for line in f:
                rec = json.loads(line)
                agents = rec["agents"]
                final_scores = rec["final_scores"]
                eliminated = rec.get("eliminated", [])
                if len(agents) != len(final_scores):
                    n_skipped += 1
                    continue

                rank = _ranks_from_scores(final_scores, eliminated)
                payout: dict[int, float] = {}  # OpenSkill ignores payout
                fs: dict[int, float] = {
                    i: float(s) for i, s in enumerate(final_scores)
                }
                survivors_n = sum(
                    1 for i in range(len(final_scores)) if i not in eliminated
                )
                solo_winner = (
                    next(iter(i for i in range(len(final_scores))
                              if i not in eliminated))
                    if survivors_n == 1 else None
                )
                match = MatchResult(
                    rank=rank, payout=payout, final_scores=fs,
                    detente=bool(rec.get("detente_reached", False)),
                    solo_winner=solo_winner,
                )
                rs.update(match, identities=list(agents))
                for name in agents:
                    seat_appearances[name] = seat_appearances.get(name, 0) + 1
                n_games += 1

    print(f"processed {n_games} games "
          f"({n_skipped} skipped) from {len(args.paths)} file(s)")
    print()

    leaderboard = rs.leaderboard()
    name_w = max(len(str(n)) for n, _ in leaderboard)
    print(f"  {'agent':<{name_w}}  {'mu':>7}  {'sigma':>7}  "
          f"{'mu-3*sigma':>11}  {'games':>6}")
    print(f"  {'-' * name_w}  {'-' * 7}  {'-' * 7}  "
          f"{'-' * 11}  {'-' * 6}")
    for name, rating in leaderboard:
        appearances = seat_appearances.get(name, 0)
        print(f"  {str(name):<{name_w}}  {rating.mu:7.3f}  {rating.sigma:7.3f}"
              f"  {rating.conservative:11.3f}  {appearances:>6}")

    if args.metrics_out:
        try:
            from castra.metrics import MetricsRecord
        except ImportError:
            print("error: --metrics-out requires `pip install castra`",
                  file=sys.stderr)
            return 1
        metrics: dict[str, float] = {
            "num_games": float(n_games),
            "num_agents": float(len(leaderboard)),
        }
        for name, rating in leaderboard:
            safe = str(name).replace(" ", "_")
            metrics[f"mu/{safe}"] = float(rating.mu)
            metrics[f"sigma/{safe}"] = float(rating.sigma)
            metrics[f"conservative/{safe}"] = float(rating.conservative)
        metadata: dict = {
            "tool": "foedus_compute_ratings",
            "rating_model": "OpenSkill PlackettLuce",
            "input_paths": [str(p) for p in args.paths],
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        rec = MetricsRecord(metrics=metrics, metadata=metadata)
        rec.to_yaml(Path(args.metrics_out))
        print()
        print(f"  metrics.yaml -> {args.metrics_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
