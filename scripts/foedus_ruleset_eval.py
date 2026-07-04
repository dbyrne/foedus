"""Ruleset-v1 empirical-design harness — orchestration.

Runs the cheap heuristic sweeps that back the standard competition format
(docs/design/2026-07-04-ruleset-v1.md):

  Phase 1  format grid   seats {4,5,6} x turns {8,12,15} x radius {1,2}
                         -> discrimination index, ladder-recovery fidelity,
                            adjacent-pair separation, detente/elim/length.
  Phase 2  convergence   how many games until an S-entrant match's OpenSkill
                         standings sort the ladder correctly (>=95% of
                         shuffled replays), per seat count.
  Phase 3  detente       ALLY-heavy roster across turn lengths, to show the
                         format's (small) effect on detente rate vs the
                         (dominant) roster effect.

No LLM calls. Distinct-seat sampling gives every seat a unique rating
identity (models a real match; avoids the duplicate-identity path). Reuses
`run_one_game` from foedus_sim_sweep — no engine logic is duplicated, and
foedus/rating.py and foedus/resolve.py are untouched.

Usage:
    python scripts/foedus_ruleset_eval.py --out docs/design/2026-07-04-ruleset-v1-evidence
    python scripts/foedus_ruleset_eval.py --quick   # fast smoke
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import statistics as _stats

from foedus.core import Archetype
from foedus.eval.ruleset import (
    LADDER,
    MID_LADDER,
    convergence_curve,
    detente_rate,
    discrimination_index,
    distinct_seats,
    elimination_rate,
    kendall_tau,
    mean_turns,
    min_adjacent_separation,
    ranks_from_record,
    rate_records,
    separated_adjacent_pairs,
)
from foedus_sim_sweep import run_one_game


def _mean_std(xs):
    xs = list(xs)
    return {
        "mean": _stats.fmean(xs),
        "std": _stats.pstdev(xs) if len(xs) > 1 else 0.0,
        "seeds": xs,
    }

ARCH = Archetype.CONTINENTAL_SWEEP
# Engine-default detente threshold (4 + num_players); measures how often
# detente actually fires rather than disabling it.
PEACE = 0

SEAT_COUNTS = [4, 5, 6]
TURN_LENGTHS = [8, 12, 15]
RADII = [1, 2]

# Fixed match rosters (S distinct entrants spanning the ladder) for the
# convergence phase — a match is a campaign of recurring opponents.
MATCH_ROSTERS = {
    4: ["Defensive", "Sycophant", "Aggressive", "DishonestCooperator"],
    5: ["Defensive", "Random", "Sycophant", "Aggressive", "DishonestCooperator"],
    6: list(LADDER),
}

# Ally-inclined roster for the detente-sensitivity probe.
ALLY_ROSTER = ["Cooperator", "TrustfulCooperator", "DishonestCooperator",
               "Sycophant"]

# Candidate pool the six-rung LADDER was selected from (doc §2). Kept here so
# the ladder choice is reproducible, not a throwaway calibration.
CALIB_CANDIDATES = [
    "Defensive", "ConservativeBuilder", "Random", "Greedy", "Aggressive",
    "Sycophant", "Bandwagon", "TitForTat", "GreedyHold",
    "DishonestCooperator", "AntiLeader", "OpportunisticBetrayer",
]


def _task(t):
    return run_one_game(*t)


def _play(roster, num_players, turns, radius, n, seed, workers,
          distinct=True, rng_seed=0):
    """Run n games; return their records. distinct=True -> unique seats."""
    rng = random.Random(rng_seed)
    tasks = []
    for g in range(n):
        seed_g = seed + g
        if distinct:
            seats = distinct_seats(roster, num_players, rng)
        else:
            seats = [rng.choice(roster) for _ in range(num_players)]
        tasks.append((g, seed_g, seats, turns, ARCH, num_players, radius,
                      PEACE, None))
    if workers == 1:
        return [_task(t) for t in tasks]
    ctx = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        return list(pool.map(_task, tasks, chunksize=max(1, n // (workers * 4))))


def _ladder_order(names):
    """The subset of LADDER present in `names`, weak->strong reversed to
    strong->weak (best-first) so it lines up with leaderboard ordering."""
    strong_first = list(reversed(LADDER))
    return [n for n in strong_first if n in set(names)]


def _format_metrics(recs):
    """Per-batch metrics for one format's game records."""
    rs = rate_records(recs)
    ratings = {n: (r.mu, r.sigma) for n, r in rs.all_ratings().items()}
    observed = [n for n, _ in rs.leaderboard()]
    mid = {n: ratings[n] for n in MID_LADDER if n in ratings}
    return {
        "ratings": ratings, "observed": observed,
        # Full D is tail-dominated (floor vs ceiling); mid-D over the
        # competitive band and the tightest adjacent gap are what reveal
        # whether a format separates *close* skill. See doc §6.3.
        "D_full": discrimination_index(ratings),
        "D_mid": discrimination_index(mid),
        "min_adj_sep": min_adjacent_separation(observed, ratings),
        "sep_pairs": separated_adjacent_pairs(observed, ratings),
        "recovery_tau": kendall_tau(_ladder_order(LADDER), observed),
        "detente_rate": detente_rate(recs),
        "elim_rate": elimination_rate(recs),
        "mean_turns": mean_turns(recs),
    }


def phase0_calibration(games, turns, radius, workers):
    """Reproduce the ladder selection: rate the candidate pool at the base
    format and report OpenSkill mu/sigma + mean placement + win-rate, so the
    six-rung LADDER is an auditable choice (doc §2)."""
    from collections import defaultdict
    recs = _play(CALIB_CANDIDATES, 4, turns, radius, games, seed=500_000,
                 workers=workers)
    rs = rate_records(recs)
    placements = defaultdict(list)
    wins = defaultdict(int)
    appearances = defaultdict(int)
    for rec in recs:
        rank = ranks_from_record(rec)
        winners = set(rec["winners"])
        for i, name in enumerate(rec["agents"]):
            placements[name].append(rank[i])
            appearances[name] += 1
            if i in winners:
                wins[name] += 1
    out = {"turns": turns, "radius": radius, "games": games, "rungs": {}}
    for name, r in rs.leaderboard():
        out["rungs"][name] = {
            "mu": r.mu, "sigma": r.sigma,
            "mean_rank": _stats.fmean(placements[name]),
            "win_rate": wins[name] / appearances[name],
            "in_ladder": name in LADDER,
        }
    print("  calibration ordering (strong->weak): "
          + ", ".join(f"{n}{'*' if n in LADDER else ''}"
                      for n, _ in rs.leaderboard()), file=sys.stderr)
    return out


def phase1_grid(games, seeds, workers):
    rows = []
    for radius in RADII:
        for turns in TURN_LENGTHS:
            for seats in SEAT_COUNTS:
                t0 = time.time()
                # Independent seed batches give a real CI on the metrics
                # rather than a single point estimate (doc §3, I1).
                per_seed = []
                pooled = []
                for s in range(seeds):
                    recs = _play(LADDER, seats, turns, radius, games,
                                 seed=1_000_000 + s * 250_000, workers=workers,
                                 rng_seed=s)
                    per_seed.append(_format_metrics(recs))
                    pooled.extend(recs)
                pool = _format_metrics(pooled)  # tighter sigma for display
                keys = ["D_full", "D_mid", "min_adj_sep", "recovery_tau",
                        "detente_rate", "elim_rate", "mean_turns", "sep_pairs"]
                agg = {k: _mean_std(m[k] for m in per_seed) for k in keys}
                rows.append({
                    "seats": seats, "turns": turns, "radius": radius,
                    "games_per_seed": games, "seeds": seeds,
                    **agg,
                    "max_sep_pairs": len(pool["observed"]) - 1,
                    # pooled ratings/order for the ladder-separation display
                    "ratings": {n: {"mu": mu, "sigma": sig}
                                for n, (mu, sig) in pool["ratings"].items()},
                    "order": pool["observed"],
                    "secs": round(time.time() - t0, 1),
                })
                r = rows[-1]
                print(f"  s{seats} t{turns} r{radius}: "
                      f"Dfull={agg['D_full']['mean']:.2f}"
                      f"±{agg['D_full']['std']:.2f} "
                      f"Dmid={agg['D_mid']['mean']:.2f}"
                      f"±{agg['D_mid']['std']:.2f} "
                      f"minGap={agg['min_adj_sep']['mean']:.2f} "
                      f"tau={agg['recovery_tau']['mean']:+.2f} "
                      f"elim={agg['elim_rate']['mean']:.1%} "
                      f"({r['secs']}s)", file=sys.stderr)
    return rows


def phase2_convergence(games, shuffles, turns, radius, workers):
    """Convergence per named scenario: (label, roster, seats, turns, radius).

    Scenarios isolate the two things that drive games-per-match:
    entrant COUNT (4/5/6 well-spread fields) and field SEPARATION (a hard
    4-field with a near-tied pair), plus a turns sensitivity (4-field at 8
    vs `turns`).
    """
    scenarios = [
        (f"4-spread-t{turns}", MATCH_ROSTERS[4], 4, turns, radius),
        (f"5-spread-t{turns}", MATCH_ROSTERS[5], 5, turns, radius),
        (f"6-full-t{turns}", MATCH_ROSTERS[6], 6, turns, radius),
        # Hard 4-field: includes the near-tied Greedy/Sycophant rungs, so
        # it isolates field-separation from seat-count as a convergence driver.
        ("4-hard-tie", ["DishonestCooperator", "Aggressive", "Greedy",
                        "Sycophant"], 4, turns, radius),
        # Turns sensitivity: same spread 4-field at 8 turns.
        ("4-spread-t8", MATCH_ROSTERS[4], 4, 8, radius),
    ]
    out = {}
    game_counts = sorted(set([5, 10, 15, 20, 30, 40, 60, 80, 120, 160,
                              240, min(games, 320), games]))
    game_counts = [g for g in game_counts if g <= games]
    for i, (label, roster, seats, tn, rad) in enumerate(scenarios):
        recs = _play(roster, seats, tn, rad, games,
                     seed=2_000_000 + i * 100_000, workers=workers)
        reference = _ladder_order(roster)
        curve = convergence_curve(recs, reference, game_counts,
                                  shuffles=shuffles, tau_threshold=0.9, seed=7)
        # g95 is a strict all-pairs bar and a noisy first-crossing near
        # threshold; g_tau90 (first g whose MEAN tau stays >= 0.9) is the
        # smoother, more honest convergence statistic (doc §6.5, I2/I3).
        def _first_stable(pred):
            gcs = game_counts
            for i, g in enumerate(gcs):
                if all(pred(curve[gg]) for gg in gcs[i:]):
                    return g
            return None
        g95 = _first_stable(lambda c: c["frac_correct"] >= 0.95)
        g_tau90 = _first_stable(lambda c: c["mean_tau"] >= 0.90)
        out[label] = {
            "roster": roster, "seats": seats, "turns": tn, "radius": rad,
            "reference": reference,
            "game_counts": game_counts,
            "curve": curve,
            "g95": g95,          # first g that stays >=95% perfectly-sorted
            "g_tau90": g_tau90,  # first g whose mean tau stays >= 0.9
        }
        print(f"  convergence {label}: g_tau90={g_tau90} g95={g95} "
              f"(frac@{game_counts[-1]}={curve[game_counts[-1]]['frac_correct']:.2f}, "
              f"tau@{game_counts[-1]}={curve[game_counts[-1]]['mean_tau']:+.2f})",
              file=sys.stderr)
    return out


def phase3_detente(games, workers):
    out = {}
    for turns in TURN_LENGTHS:
        recs = _play(ALLY_ROSTER, 4, turns, 2, games, seed=3_000_000,
                     workers=workers)
        out[turns] = {
            "roster": ALLY_ROSTER,
            "detente_rate": detente_rate(recs),
            "elim_rate": elimination_rate(recs),
            "mean_turns": mean_turns(recs),
        }
        print(f"  detente(ally-roster) t{turns}: "
              f"det={out[turns]['detente_rate']:.1%} "
              f"len={out[turns]['mean_turns']:.1f}", file=sys.stderr)
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="", help="evidence output directory")
    p.add_argument("--calib-games", type=int, default=4000)
    p.add_argument("--grid-games", type=int, default=2000,
                   help="games per seed per format")
    p.add_argument("--grid-seeds", type=int, default=5,
                   help="independent seed batches per format (for CIs)")
    p.add_argument("--conv-games", type=int, default=800)
    p.add_argument("--conv-shuffles", type=int, default=400)
    p.add_argument("--detente-games", type=int, default=1500)
    p.add_argument("--conv-turns", type=int, default=12)
    p.add_argument("--conv-radius", type=int, default=2)
    p.add_argument("--workers", type=int, default=0,
                   help="0 = os.cpu_count()")
    p.add_argument("--quick", action="store_true",
                   help="tiny run to smoke the pipeline")
    p.add_argument("--phases", default="0,1,2,3",
                   help="comma list of phases to run")
    args = p.parse_args(argv)

    if args.quick:
        args.calib_games = 150
        args.grid_games = 100
        args.grid_seeds = 2
        args.conv_games = 120
        args.conv_shuffles = 20
        args.detente_games = 150

    workers = args.workers if args.workers > 0 else (os.cpu_count() or 1)
    phases = set(args.phases.split(","))
    t0 = time.time()
    result = {
        "ladder": LADDER,
        "mid_ladder": MID_LADDER,
        "params": {
            "calib_games": args.calib_games,
            "grid_games_per_seed": args.grid_games,
            "grid_seeds": args.grid_seeds,
            "conv_games": args.conv_games,
            "conv_shuffles": args.conv_shuffles,
            "detente_games": args.detente_games,
            "conv_turns": args.conv_turns, "conv_radius": args.conv_radius,
            "archetype": ARCH.value, "peace_threshold": "engine-default",
        },
    }

    if "0" in phases:
        print("phase 0: calibration", file=sys.stderr)
        result["calibration"] = phase0_calibration(
            args.calib_games, args.conv_turns, args.conv_radius, workers)
    if "1" in phases:
        print("phase 1: format grid", file=sys.stderr)
        result["grid"] = phase1_grid(args.grid_games, args.grid_seeds, workers)
    if "2" in phases:
        print("phase 2: convergence", file=sys.stderr)
        result["convergence"] = phase2_convergence(
            args.conv_games, args.conv_shuffles, args.conv_turns,
            args.conv_radius, workers)
    if "3" in phases:
        print("phase 3: detente sensitivity", file=sys.stderr)
        result["detente"] = phase3_detente(args.detente_games, workers)

    result["elapsed_secs"] = round(time.time() - t0, 1)
    print(f"done in {result['elapsed_secs']}s ({workers} workers)",
          file=sys.stderr)

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "results.json").write_text(json.dumps(result, indent=2))
        print(f"wrote {out_dir/'results.json'}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
