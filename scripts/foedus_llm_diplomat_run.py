"""LLM-diplomat run harness — plays N foedus games with one LLMDiplomat
seat against a chosen heuristic roster, single-process.

For each game emits a sweep-compatible JSONL record (feeds
`foedus_compute_ratings.py` unchanged) and a telemetry sidecar record
(betrayals, pact breaches, public reputation, decision-log parse-fail
count). Optionally renders one or more games to a human-readable
markdown transcript.

Usage:
    PYTHONPATH=. python3 scripts/foedus_llm_diplomat_run.py \
        --num-games 3 --max-turns 15 --heuristics GreedyHold,Cooperator,TitForTat \
        --out-dir runs/llm_diplomat

Spec: see the M-foedus-llm-diplomat coder brief (First Light, slice 1),
adapting janus/docs/superpowers/specs/2026-07-01-llm-diplomat-foedus-v0-design.md
§4.4 for the current arena (pacts, reputation, retreats).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from foedus.agents.heuristics import ROSTER
from foedus.agents.llm.diplomat import LLMDiplomat
from foedus.core import (
    Archetype, GameConfig, GameState, Hold, Move, PlayerId, ReputationTally,
    Support,
)
from foedus.mapgen import generate_map
from foedus.render_common import order_to_str
from foedus.loop import play_game
from foedus.resolve import initial_state


def _order_to_dict(order) -> dict:
    if isinstance(order, Hold):
        return {"type": "Hold"}
    if isinstance(order, Move):
        return {"type": "Move", "dest": order.dest}
    if isinstance(order, Support):
        d: dict = {"type": "Support", "target": order.target}
        if order.require_dest is not None:
            d["require_dest"] = order.require_dest
        return d
    return {"type": "Unknown"}


def _betrayal_to_dict(obs) -> dict:
    return {
        "turn": obs.turn,
        "betrayer": obs.betrayer,
        "unit_id": obs.intent.unit_id,
        "declared_order": _order_to_dict(obs.intent.declared_order),
        "actual_order": _order_to_dict(obs.actual_order),
    }


def _pact_breach_to_dict(b) -> dict:
    return {
        "turn": b.turn,
        "pact_id": b.pact_id,
        "breacher": b.breacher,
        "unit_id": b.term.unit_id,
        "declared_order": _order_to_dict(b.term.declared_order),
        "actual_order": _order_to_dict(b.actual_order),
    }


def run_one_llm_game(
    game_id: int,
    seed: int,
    *,
    llm_seat: int = 0,
    heuristic_names: list[str] | None = None,
    max_turns: int = 15,
    archetype: Archetype = Archetype.CONTINENTAL_SWEEP,
    map_radius: int = 2,
    llm_agent_factory=LLMDiplomat,
    config_overrides: dict | None = None,
) -> tuple[dict, dict, GameState, LLMDiplomat]:
    """Run one game (1 LLMDiplomat seat vs the given heuristic roster).

    Returns (sweep_record, telemetry_record, final_state, llm_agent).
    """
    heuristic_names = list(heuristic_names or ["GreedyHold", "GreedyHold", "GreedyHold"])
    num_players = 1 + len(heuristic_names)
    if not (0 <= llm_seat < num_players):
        raise ValueError(
            f"llm_seat={llm_seat} out of range for num_players={num_players}"
        )

    agent_names: list[str] = []
    h_iter = iter(heuristic_names)
    for i in range(num_players):
        agent_names.append("LLMDiplomat" if i == llm_seat else next(h_iter))

    cfg_kwargs: dict = dict(
        num_players=num_players, max_turns=max_turns, seed=seed,
        archetype=archetype, map_radius=map_radius,
    )
    if config_overrides:
        cfg_kwargs.update(config_overrides)
    cfg = GameConfig(**cfg_kwargs)
    m = generate_map(num_players, seed=seed, archetype=cfg.archetype,
                     map_radius=cfg.map_radius)
    state = initial_state(cfg, m)

    llm_agent = llm_agent_factory()
    agents: dict[PlayerId, object] = {}
    for i, name in enumerate(agent_names):
        agents[i] = llm_agent if i == llm_seat else ROSTER[name]()

    final = play_game(agents, state=state)

    sweep = {
        "game_id": game_id,
        "seed": seed,
        "agents": agent_names,
        "llm_seat": llm_seat,
        "total_turns": final.turn,
        "final_scores": [final.scores.get(p, 0.0) for p in range(num_players)],
        "eliminated": sorted(final.eliminated),
        "winners": final.winners(),
        "detente_reached": final.detente_reached,
    }

    parse_fail_count = sum(1 for r in llm_agent.decision_log if r["fell_back"])
    telemetry = {
        "game_id": game_id,
        "llm_seat": llm_seat,
        "betrayals": {
            p: [_betrayal_to_dict(o) for o in obs]
            for p, obs in final.betrayals.items()
        },
        "pact_breaches": {
            p: [_pact_breach_to_dict(b) for b in breaches]
            for p, breaches in final.pact_breaches.items()
        },
        "reputation": {
            p: {"intent_breaches": r.intent_breaches,
                "pact_breaches": r.pact_breaches, "total": r.total}
            for p, r in final.reputation.items()
        },
        "n_decisions": len(llm_agent.decision_log),
        "parse_fail_count": parse_fail_count,
    }

    return sweep, telemetry, final, llm_agent


def render_transcript(state: GameState, llm_seat: int) -> str:
    """Human-readable per-turn transcript: stances, declared intents,
    betrayals, pact breaches, final reputation -- the "read the
    scheming" artifact."""
    lines = [f"# Foedus LLM Diplomat transcript — LLM seat {llm_seat}", ""]
    lines.append(f"Final scores: {dict(state.final_scores())}")
    lines.append(f"Eliminated: {sorted(state.eliminated)}")
    lines.append(f"Winners: {state.winners()}")
    lines.append(f"Détente reached: {state.detente_reached}")
    lines.append("")

    for turn_idx, press_by_player in enumerate(state.press_history):
        lines.append(f"## Turn {turn_idx + 1}")
        for p, press in sorted(press_by_player.items()):
            stance_s = ", ".join(
                f"p{t}={s.value}" for t, s in sorted(press.stance.items())
            ) or "(none)"
            lines.append(f"- p{p} stance: {stance_s}")
            for it in press.intents:
                vis = "public" if it.visible_to is None else sorted(it.visible_to)
                lines.append(
                    f"  - declared u{it.unit_id} -> "
                    f"{order_to_str(it.declared_order)} (visible_to={vis})"
                )
        lines.append("")

    lines.append("## Betrayals observed")
    any_betrayal = False
    seen: set[tuple] = set()
    for _observer, obs_list in sorted(state.betrayals.items()):
        for obs in obs_list:
            # `betrayals` is keyed by OBSERVER -- a public intent fans the
            # same underlying breach out to every survivor. Dedupe by the
            # breach's own identity for a one-line-per-breach summary.
            key = (obs.turn, obs.betrayer, obs.intent.unit_id)
            if key in seen:
                continue
            seen.add(key)
            any_betrayal = True
            lines.append(
                f"- turn {obs.turn}: p{obs.betrayer} declared "
                f"u{obs.intent.unit_id} -> {order_to_str(obs.intent.declared_order)}, "
                f"actually {order_to_str(obs.actual_order)}"
            )
    if not any_betrayal:
        lines.append("(none)")
    lines.append("")

    lines.append("## Pact breaches observed")
    any_breach = False
    seen_pact: set[tuple] = set()
    for _observer, breach_list in sorted(state.pact_breaches.items()):
        for b in breach_list:
            key = (b.turn, b.pact_id, b.breacher)
            if key in seen_pact:
                continue
            seen_pact.add(key)
            any_breach = True
            lines.append(
                f"- turn {b.turn}: p{b.breacher} broke pact #{b.pact_id} "
                f"(pledged u{b.term.unit_id} -> "
                f"{order_to_str(b.term.declared_order)}, actually "
                f"{order_to_str(b.actual_order)})"
            )
    if not any_breach:
        lines.append("(none)")
    lines.append("")

    lines.append("## Final reputation (public)")
    survivors = sorted(
        p for p in range(state.config.num_players) if p not in state.eliminated
    )
    for p in survivors:
        r = state.reputation.get(p, ReputationTally())
        lines.append(
            f"- p{p}: {r.intent_breaches} intent / {r.pact_breaches} pact / "
            f"{r.total} total"
        )

    return "\n".join(lines)


def main(argv: list[str] | None = None, llm_agent_factory=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run N foedus games with an LLMDiplomat seat vs a heuristic roster."
    )
    parser.add_argument("--num-games", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--seed-offset", "--seed", type=int, default=0,
                        dest="seed_offset")
    parser.add_argument("--llm-seat", type=int, default=0)
    parser.add_argument("--heuristics", type=str,
                        default="GreedyHold,Cooperator,TitForTat",
                        help="Comma-separated heuristic names for the non-LLM seats.")
    parser.add_argument("--archetype", type=str, default="continental_sweep")
    parser.add_argument("--map-radius", type=int, default=2)
    parser.add_argument("--out-dir", type=str, default="runs/llm_diplomat")
    parser.add_argument("--backend", type=str, default=None,
                        help="Sets FOEDUS_LLM_BACKEND for this run (ollama|claude).")
    parser.add_argument("--model", type=str, default=None,
                        help="Sets FOEDUS_LLM_MODEL for this run.")
    parser.add_argument("--transcripts", type=int, default=1,
                        help="Number of games (from the start) to also render "
                             "as a human-readable markdown transcript.")
    args = parser.parse_args(argv)

    if args.backend:
        os.environ["FOEDUS_LLM_BACKEND"] = args.backend
    if args.model:
        os.environ["FOEDUS_LLM_MODEL"] = args.model

    factory = llm_agent_factory or LLMDiplomat
    heuristic_names = [h.strip() for h in args.heuristics.split(",") if h.strip()]
    archetype = Archetype(args.archetype)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_decisions = 0
    total_fell_back = 0

    with (out_dir / "sweep.jsonl").open("w") as sweep_f, \
         (out_dir / "telemetry.jsonl").open("w") as telemetry_f:
        for i in range(args.num_games):
            game_id = i
            seed = args.seed_offset + i
            sweep, telemetry, final_state, agent = run_one_llm_game(
                game_id, seed, llm_seat=args.llm_seat,
                heuristic_names=heuristic_names, max_turns=args.max_turns,
                archetype=archetype, map_radius=args.map_radius,
                llm_agent_factory=factory,
            )
            sweep_f.write(json.dumps(sweep) + "\n")
            telemetry_f.write(json.dumps(telemetry) + "\n")
            total_decisions += telemetry["n_decisions"]
            total_fell_back += telemetry["parse_fail_count"]

            if i < args.transcripts:
                (out_dir / f"transcript_game{game_id}.md").write_text(
                    render_transcript(final_state, args.llm_seat)
                )

            print(
                f"game {game_id}: turns={sweep['total_turns']} "
                f"scores={sweep['final_scores']} "
                f"parse_fail={telemetry['parse_fail_count']}/{telemetry['n_decisions']}"
            )

    rate = (total_fell_back / total_decisions) if total_decisions else 0.0
    print(f"\n{args.num_games} game(s) written to {out_dir}")
    print(f"overall parse-fail rate: {total_fell_back}/{total_decisions} ({rate:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
