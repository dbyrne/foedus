"""Foedus depth eval — repeatable battery over the agent roster.

Spec: docs/superpowers/specs/2026-04-29-depth-eval-framework-design.md

Usage:
    PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
        --output docs/research/depth/2026-04-29-bundle4.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))

from foedus.agents.heuristics import ROSTER
from foedus.eval.bootstrap import bootstrap_ci_mean
from foedus.eval.metrics import (
    rankings_from_records, engagement_from_records,
    pairwise_winrate_from_records, probe_score_diff, probe_per_game_diffs,
)
from foedus.eval.probes import PROBES, Probe
from foedus.eval.render import render_markdown


def _git_info(repo_root: Path) -> tuple[str, str]:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, text=True,
        ).strip()
    except Exception:
        sha = "unknown"
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root, text=True,
        ).strip()
    except Exception:
        branch = "unknown"
    return sha, branch


def _run_sweep(
    repo_root: Path,
    out_jsonl: Path,
    *,
    num_games: int,
    seed: int,
    seats: tuple[str, ...] | None,
    max_turns: int,
    map_radius: int,
    workers: int,
) -> list[dict]:
    """Invoke foedus_sim_sweep.py as a subprocess; return parsed records.

    Uses the original flag names: --out and --seed-offset.
    """
    cmd = [
        sys.executable, "scripts/foedus_sim_sweep.py",
        "--num-games", str(num_games),
        "--max-turns", str(max_turns),
        "--seed-offset", str(seed),
        "--workers", str(workers),
        "--out", str(out_jsonl),
        "--map-radius", str(map_radius),
    ]
    if seats:
        cmd += ["--seats", ",".join(seats)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    proc = subprocess.run(
        cmd, cwd=repo_root, env=env, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"sweep failed: cmd={cmd}\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
        )
    records = []
    for line in out_jsonl.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _filter_valid_probes(probes: list[Probe]) -> list[Probe]:
    valid = []
    for p in probes:
        missing = [s for s in p.seats if s not in ROSTER]
        if missing:
            print(f"[depth-eval] skipping probe {p.name}: "
                  f"unknown seats {missing}", file=sys.stderr)
            continue
        valid.append(p)
    return valid


def _select_probes(names_csv: str) -> list[Probe]:
    if names_csv == "all":
        return list(PROBES)
    wanted = {n.strip() for n in names_csv.split(",") if n.strip()}
    by_name = {p.name: p for p in PROBES}
    out = []
    for n in wanted:
        if n not in by_name:
            print(f"[depth-eval] unknown probe: {n}", file=sys.stderr)
            continue
        out.append(by_name[n])
    return out


def _run_one_probe(probe_args):
    """Worker entrypoint — runs one probe sweep and returns records."""
    (repo_root, probe, n, seed, max_turns, map_radius, workers) = probe_args
    with tempfile.NamedTemporaryFile(
        suffix=".jsonl", delete=False, dir=repo_root
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        records = _run_sweep(
            repo_root, tmp_path,
            num_games=n, seed=seed, seats=probe.seats,
            max_turns=max_turns, map_radius=map_radius,
            workers=workers,
        )
        return probe.name, records
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n-tier1", type=int, default=2000)
    parser.add_argument("--n-tier2", type=int, default=500)
    parser.add_argument("--probes", default="all")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--bootstrap-n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reseed", action="store_true")
    parser.add_argument("--map-radius", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()

    repo_root = _HERE.parents[1]
    seed = (int.from_bytes(os.urandom(4), "big") if args.reseed
            else args.seed)
    sha, branch = _git_info(repo_root)

    # ---- Tier 1: random pool sweep ----
    print(f"[depth-eval] Tier 1: {args.n_tier1} random-pool games "
          f"(seed={seed})", file=sys.stderr)
    with tempfile.NamedTemporaryFile(
        suffix=".jsonl", delete=False, dir=repo_root
    ) as tmp:
        t1_path = Path(tmp.name)
    try:
        t1_records = _run_sweep(
            repo_root, t1_path,
            num_games=args.n_tier1, seed=seed, seats=None,
            max_turns=args.max_turns, map_radius=args.map_radius,
            workers=args.workers,
        )
    finally:
        try:
            t1_path.unlink()
        except FileNotFoundError:
            pass

    rankings = rankings_from_records(t1_records)
    engagement = engagement_from_records(t1_records)
    pairwise = pairwise_winrate_from_records(t1_records)

    if args.bootstrap:
        for row in rankings:
            row["ci95"] = list(bootstrap_ci_mean(
                row["scores"], n_resamples=args.bootstrap_n,
                seed=seed,
            ))
    else:
        for row in rankings:
            row["ci95"] = None
    for row in rankings:
        del row["scores"]

    # ---- Tier 2: fixed-seat probes ----
    probes = _filter_valid_probes(_select_probes(args.probes))
    print(f"[depth-eval] Tier 2: {len(probes)} probes × "
          f"{args.n_tier2} games", file=sys.stderr)

    probe_args_list = [
        (repo_root, p, args.n_tier2, seed,
         args.max_turns, args.map_radius, 1)
        for p in probes
    ]
    probe_results: dict[str, list[dict]] = {}
    if probe_args_list:
        max_parallel = (args.workers or os.cpu_count() or 1)
        max_parallel = min(max_parallel, len(probe_args_list))
        with ProcessPoolExecutor(max_workers=max_parallel) as ex:
            futures = {ex.submit(_run_one_probe, pa): pa[1].name
                       for pa in probe_args_list}
            for f in as_completed(futures):
                name, records = f.result()
                probe_results[name] = records

    tier2_out = []
    for p in probes:
        recs = probe_results.get(p.name, [])
        diff = probe_score_diff(recs, p.subject_index)
        ci = None
        if args.bootstrap and recs:
            ci = list(bootstrap_ci_mean(
                probe_per_game_diffs(recs, p.subject_index),
                n_resamples=args.bootstrap_n,
                seed=seed,
            ))
        tier2_out.append({
            "name": p.name,
            "description": p.description,
            "seats": list(p.seats),
            "subject_index": p.subject_index,
            "n": len(recs),
            "score_diff": diff,
            "ci95": ci,
            "engagement": engagement_from_records(recs),
        })

    artifact = {
        "run_id": args.output.stem,
        "git_sha": sha,
        "git_branch": branch,
        "timestamp": dt.datetime.now(dt.timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "players": args.players,
            "map_radius": args.map_radius,
            "max_turns": args.max_turns,
        },
        "stat_rigor": "bootstrap" if args.bootstrap else "point",
        "n_bootstrap_resamples": args.bootstrap_n if args.bootstrap else None,
        "tier1_random_pool": {
            "n_games": len(t1_records),
            "seed": seed,
            "rankings": rankings,
            "pairwise_winrate": pairwise,
            "engagement": engagement,
        },
        "tier2_probes": tier2_out,
        "tier3_knob_sweep": None,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n")
    md_path = args.output.with_suffix(".md")
    md_path.write_text(render_markdown(artifact))

    print(f"[depth-eval] wrote {args.output}", file=sys.stderr)
    print(f"[depth-eval] wrote {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
