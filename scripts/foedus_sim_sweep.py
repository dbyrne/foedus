"""Bulk simulation harness — runs N foedus games with random heuristic
pairings and emits one JSONL line per game.

Usage:
    PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
        --num-games 5000 --max-turns 15

Spec: docs/superpowers/specs/2026-04-29-sim-sweep-design.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from foedus.agents.heuristics import ROSTER
from foedus.core import (
    Archetype, GameConfig, Hold, Move, SupportHold, SupportMove,
)
from foedus.mapgen import generate_map
from foedus.press import (
    finalize_round, signal_chat_done, signal_done, submit_press_tokens,
)
from foedus.resolve import initial_state


ORDER_TYPE_NAMES = {
    Hold: "Hold", Move: "Move",
    SupportHold: "SupportHold", SupportMove: "SupportMove",
}


def _order_type_name(order):
    return ORDER_TYPE_NAMES.get(type(order), "Unknown")


def run_one_game(game_id: int, seed: int, agent_names: list[str],
                 max_turns: int, archetype: Archetype,
                 num_players: int, map_radius: int = 3,
                 peace_threshold: int = 99) -> dict:
    """Run a single game, return the per-game JSONL record.

    `peace_threshold` defaults to 99 (effectively disabled) so games
    play to max_turns by default. Pass 0 to use the engine's default
    table-size-scaled threshold (`4 + num_players`), or any positive
    int to set explicitly. Set to 0 when measuring how often détente
    fires in the heuristic roster.
    """
    cfg_kwargs = dict(
        num_players=num_players, max_turns=max_turns, seed=seed,
        archetype=archetype, map_radius=map_radius,
    )
    if peace_threshold == 0:
        # 0 means "use engine default" (table-size-scaled).
        pass
    else:
        cfg_kwargs["peace_threshold"] = peace_threshold
    cfg = GameConfig(**cfg_kwargs)
    m = generate_map(num_players, seed=seed,
                     archetype=archetype, map_radius=cfg.map_radius)
    state = initial_state(cfg, m)

    agents = []
    for i, name in enumerate(agent_names):
        if name == "Random":
            agents.append(ROSTER[name](seed=seed * 1000 + i))
        else:
            agents.append(ROSTER[name]())

    supply_per_turn: dict[int, list[int]] = {}
    score_per_turn: dict[int, list[float]] = {}
    order_counts: Counter = Counter()
    dislodgement_count = 0

    while not state.is_terminal():
        survivors = [
            p for p in range(num_players) if p not in state.eliminated
        ]
        # Press round.
        for p in survivors:
            press = agents[p].choose_press(state, p)
            state = submit_press_tokens(state, p, press)
            state = signal_chat_done(state, p)
            state = signal_done(state, p)
        # Collect orders.
        orders = {p: agents[p].choose_orders(state, p) for p in survivors}
        # Count order types.
        for p_orders in orders.values():
            for order in p_orders.values():
                order_counts[_order_type_name(order)] += 1
        # Finalize.
        prev_units = dict(state.units)
        state = finalize_round(state, orders)
        # Count unit losses: units in prev_units NOT in new state.units.
        # Note: this conflates true dislodgements with units lost to player
        # elimination (which removes all of an eliminated player's units in
        # one step). Analyzers should treat this as "units lost / turn" not
        # "strict dislodgements".
        for uid in prev_units:
            if uid not in state.units:
                dislodgement_count += 1
        # Snapshot.
        supply_per_turn[state.turn] = [
            state.supply_count(p) for p in range(num_players)
        ]
        score_per_turn[state.turn] = [
            state.scores.get(p, 0.0) for p in range(num_players)
        ]

    return {
        "game_id": game_id,
        "seed": seed,
        "agents": agent_names,
        "max_turns_reached": max_turns,
        "total_turns": state.turn,
        "is_terminal": state.is_terminal(),
        "winners": state.winners(),
        "final_scores": [state.scores.get(p, 0.0)
                         for p in range(num_players)],
        "supply_counts_per_turn": {str(k): v for k, v in supply_per_turn.items()},
        "score_per_turn": {str(k): v for k, v in score_per_turn.items()},
        "order_type_counts": dict(order_counts),
        "dislodgement_count": dislodgement_count,
        "betrayal_count_per_player": [
            len(state.betrayals.get(p, []))
            for p in range(num_players)
        ],
        "detente_reached": state.detente_reached,
        "eliminated": sorted(state.eliminated),
    }


def _run_game_task(args_tuple):
    """Worker entrypoint: unpack and call run_one_game.

    Top-level (not a closure) so it pickles cleanly across processes.
    """
    return run_one_game(*args_tuple)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-games", type=int, default=5000)
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--archetype", default="continental_sweep")
    parser.add_argument("--num-players", type=int, default=4)
    parser.add_argument("--map-radius", type=int, default=3,
                        help="hex map radius (3 = ~37 nodes; 4 = ~61; "
                             "5 = ~91)")
    parser.add_argument("--peace-threshold", type=int, default=99,
                        help="détente collective-victory threshold "
                             "(consecutive mutual-ALLY turns required). "
                             "Default 99 disables détente. Pass 0 to use "
                             "the engine default (4 + num_players).")
    parser.add_argument("--roster", default="",
                        help="comma-separated heuristic names; default: all")
    parser.add_argument("--seats", default="",
                        help="comma-separated agent names, exactly one per "
                             "seat (length must equal --num-players). When "
                             "set, this fixed assignment is used for every "
                             "game and --roster is ignored. Use to stress "
                             "specific matchups (e.g. 'TitForTat,Sycophant,"
                             "Sycophant,Sycophant').")
    parser.add_argument("--out", default="")
    parser.add_argument("--workers", type=int, default=1,
                        help="parallel worker processes (default 1; "
                             "0 = os.cpu_count())")
    args = parser.parse_args()

    archetype = Archetype(args.archetype)
    fixed_seats: list[str] | None = None
    if args.seats:
        fixed_seats = args.seats.split(",")
        if len(fixed_seats) != args.num_players:
            print(f"ERR: --seats has {len(fixed_seats)} entries but "
                  f"--num-players is {args.num_players}", file=sys.stderr)
            return 1
        for n in fixed_seats:
            if n not in ROSTER:
                print(f"ERR: unknown heuristic {n!r}", file=sys.stderr)
                return 1
        roster_names = fixed_seats
    else:
        roster_names = (args.roster.split(",") if args.roster
                        else list(ROSTER.keys()))
        for n in roster_names:
            if n not in ROSTER:
                print(f"ERR: unknown heuristic {n!r}", file=sys.stderr)
                return 1

    out_path = Path(args.out) if args.out else \
        Path(f"/tmp/foedus_sim_sweep_{int(time.time())}.jsonl")

    # Pairings are decided up-front from a single seeded RNG so the
    # parallel and serial paths produce identical assignments for the
    # same --seed-offset. Each game's gameplay seed is independent of
    # worker scheduling order.
    rng = random.Random(args.seed_offset)
    tasks = []
    for game_id in range(args.num_games):
        seed = args.seed_offset + game_id
        if fixed_seats is not None:
            agent_names = list(fixed_seats)
        else:
            agent_names = [rng.choice(roster_names)
                           for _ in range(args.num_players)]
        tasks.append((game_id, seed, agent_names, args.max_turns,
                      archetype, args.num_players, args.map_radius,
                      args.peace_threshold))

    workers = args.workers if args.workers > 0 else (os.cpu_count() or 1)
    t0 = time.time()
    if workers == 1:
        # Serial fast-path: avoids ProcessPool overhead for small sweeps.
        with out_path.open("w") as f:
            for i, task in enumerate(tasks):
                record = _run_game_task(task)
                f.write(json.dumps(record) + "\n")
                if (i + 1) % 100 == 0:
                    elapsed = time.time() - t0
                    rate = (i + 1) / elapsed
                    print(f"[{i+1}/{args.num_games}] {elapsed:.1f}s "
                          f"({rate:.1f} games/s)", file=sys.stderr)
    else:
        # Parallel path: chunk for throughput, write results as they
        # arrive (order is by completion, not game_id — game_id is in
        # the record so analyzers can sort if needed).
        chunksize = max(1, len(tasks) // (workers * 8))
        completed = 0
        with out_path.open("w") as f, \
                ProcessPoolExecutor(max_workers=workers) as pool:
            for record in pool.map(_run_game_task, tasks,
                                   chunksize=chunksize):
                f.write(json.dumps(record) + "\n")
                completed += 1
                if completed % 500 == 0:
                    elapsed = time.time() - t0
                    rate = completed / elapsed
                    print(f"[{completed}/{args.num_games}] {elapsed:.1f}s "
                          f"({rate:.1f} games/s, {workers} workers)",
                          file=sys.stderr)

    elapsed = time.time() - t0
    rate = args.num_games / elapsed if elapsed > 0 else 0.0
    print(f"Wrote {args.num_games} games to {out_path} in {elapsed:.1f}s "
          f"({rate:.1f} games/s, {workers} workers)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
