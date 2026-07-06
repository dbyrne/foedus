"""Confirm the PR #39 resolver invariant across a canonical campaign.

The one-unit-per-node invariant (`tests/test_invariants.py`) is an engine
property of `resolve.py`; it is asserted after every `finalize_round`, not at
runtime. This script confirms it held for the *boards this campaign actually
played*: for each game seed (read from the run's `sweep.jsonl`), it replays the
exact `ruleset_v1` board under many random heuristic pairings and asserts
one-unit-per-node after every resolution. Move-order coverage comes from the
random pairings (the invariant is a resolver-geometry property, order-agnostic
in the sense the PR #39 sweep established); byte-exact LLM order replay is not
needed and is intentionally avoided (a stub response re-parsed against a
divergent state would be an unsound check).

It also verifies the commit-reveal seed manifest if the run has finished.

Usage:
    PYTHONPATH=. python3 scripts/foedus_verify_invariant.py \
        --out-dir docs/research/2026-07-04-canonical-campaign-v1/run [--pairings 20]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

from foedus.agents.heuristics import ROSTER
from foedus.core import GameConfig
from foedus.eval import campaign as campaign_mod
from foedus.mapgen import generate_map
from foedus.presets import ruleset_v1
from foedus.press import finalize_round, signal_done, submit_press_tokens
from foedus.resolve import initial_state

_ROSTER_NAMES = [n for n in ROSTER if n != "Random"]


def _assert_one_unit_per_node(state, seed: int, turn: int) -> None:
    locations = Counter(u.location for u in state.units.values())
    dupes = {node: c for node, c in locations.items() if c > 1}
    if dupes:
        raise AssertionError(
            f"one-unit-per-node VIOLATED at seed={seed} turn={turn}: {dupes}")


def _play_and_check(seed: int, cfg: GameConfig, rng: random.Random) -> int:
    """Play one ruleset_v1 game on `seed` with a random heuristic roster,
    asserting the invariant after every resolution. Returns the turn count."""
    n = cfg.num_players
    agent_names = [rng.choice(_ROSTER_NAMES) for _ in range(n)]
    m = generate_map(n, seed=seed, archetype=cfg.archetype,
                     map_radius=cfg.map_radius)
    state = initial_state(cfg, m)
    agents = [ROSTER[name]() for name in agent_names]
    turn = 0
    while not state.is_terminal():
        for pid in range(n):
            if pid in state.eliminated:
                continue
            state = submit_press_tokens(state, pid,
                                        agents[pid].choose_press(state, pid))
        for pid in range(n):
            if pid in state.eliminated:
                continue
            state = signal_done(state, pid)
        orders = {pid: agents[pid].choose_orders(state, pid)
                  for pid in range(n) if pid not in state.eliminated}
        state = finalize_round(state, orders)
        turn += 1
        _assert_one_unit_per_node(state, seed, turn)
    return turn


def verify(out_dir: str, pairings: int = 20) -> dict:
    d = Path(out_dir)
    seeds = []
    n_players = None
    with (d / "sweep.jsonl").open() as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                seeds.append(row["seed"])
                if n_players is None and row.get("agents"):
                    n_players = len(row["agents"])
    # Seat count comes from the sweep's own seating; minimal fixtures omit
    # 'agents', and the canonical campaign is 4-seat, so fall back to 4.
    n_players = n_players or 4

    checks = 0
    per_seed = []
    for seed in seeds:
        cfg = ruleset_v1(num_players=n_players)
        cfg = GameConfig(num_players=n_players, max_turns=cfg.max_turns,
                         seed=seed, archetype=cfg.archetype,
                         map_radius=cfg.map_radius)
        rng = random.Random(seed)
        turns = 0
        for _ in range(pairings):
            turns += _play_and_check(seed, cfg, rng)
        checks += turns
        per_seed.append({"seed": seed, "pairings": pairings, "turn_checks": turns})

    manifest = None
    mp = d / "seed_manifest.revealed.json"
    if mp.exists():
        m = campaign_mod.SeedManifest.from_dict(json.loads(mp.read_text()))
        manifest = {"revealed": True, "verified": campaign_mod.verify(m),
                    "seeds_match_sweep": (m.seeds == seeds)}

    return {
        "n_seeds": len(seeds),
        "pairings_per_seed": pairings,
        "total_turn_checks": checks,
        "invariant_held": True,   # any violation raises before we get here
        "per_seed": per_seed,
        "seed_manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--pairings", type=int, default=20,
                   help="Random heuristic pairings replayed per campaign board.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        rep = verify(args.out_dir, args.pairings)
    except AssertionError as e:
        print(f"INVARIANT VIOLATED: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"resolver one-unit-per-node invariant HELD across "
              f"{rep['n_seeds']} campaign board(s) x {rep['pairings_per_seed']} "
              f"pairings = {rep['total_turn_checks']} per-turn checks.")
        if rep["seed_manifest"]:
            sm = rep["seed_manifest"]
            print(f"seed manifest: verified={sm['verified']} "
                  f"seeds_match_sweep={sm['seeds_match_sweep']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
