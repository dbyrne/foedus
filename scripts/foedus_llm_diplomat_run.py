"""LLM-diplomat run harness — plays N foedus games with one or more
LLMDiplomat seats against a chosen heuristic roster, single-process.

For each game emits a sweep-compatible JSONL record (feeds
`foedus_compute_ratings.py` unchanged for single-LLM-seat runs; NOTE for
multi-seat runs every LLM seat is listed under the identity "LLMDiplomat",
so foedus_compute_ratings.py's per-identity ratings collapse those seats
together -- read per-seat outcomes from sweep `final_scores`/`llm_seats`,
not the ratings), a telemetry sidecar record
(betrayals, pact breaches, public reputation, decision-log parse-fail
count -- aggregate and per-LLM-seat), and a per-decision JSONL log
(turn/phase/prompt/raw_response/parsed/fell_back/n_coerced for every LLM
call -- see LLMDiplomat._log) so a parse regression is diagnosable from a
specific prompt+response, not just an aggregate count. Optionally renders
one or more games to a human-readable markdown transcript.

Usage:
    PYTHONPATH=. python3 scripts/foedus_llm_diplomat_run.py \
        --num-games 3 --max-turns 15 --heuristics GreedyHold,Cooperator,TitForTat \
        --out-dir runs/llm_diplomat

    # Multi-seat: the slice-2 coordination probe roster -- does a table of
    # LLM agents detect + coordinate against a freerider?
    PYTHONPATH=. python3 scripts/foedus_llm_diplomat_run.py \
        --num-games 3 --max-turns 15 \
        --llm-seats 0,1,2 --heuristics DishonestCooperator \
        --out-dir runs/llm_diplomat_probe

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
    llm_seats: list[int] | None = None,
    heuristic_names: list[str] | None = None,
    max_turns: int = 15,
    archetype: Archetype = Archetype.CONTINENTAL_SWEEP,
    map_radius: int = 2,
    llm_agent_factory=LLMDiplomat,
    config_overrides: dict | None = None,
):
    """Run one game with one or more LLMDiplomat seats vs the given
    heuristic roster.

    `llm_seats` drives multiple LLM seats at once -- e.g. the slice-2
    coordination probe roster (does an LLM table detect + coordinate
    against a freerider):

        run_one_llm_game(0, 1, llm_seats=[0, 1, 2],
                          heuristic_names=["DishonestCooperator"])

    gives 3 LLMDiplomat seats + 1 scripted freerider. Omit `llm_seats` and
    use the single-seat `llm_seat` kwarg for the historical behavior
    (back-compat). Each LLM seat gets its own `llm_agent_factory()`
    instance -- LLMDiplomat's per-(turn,player) caches make sharing one
    instance across seats collision-safe, but its decision log and
    FOEDUS_LLM_LOG_DIR file are per-instance, so one-instance-per-seat is
    what keeps a seat's records cleanly separated without post-hoc
    filtering.

    Returns (sweep_record, telemetry_record, final_state, agent) when
    exactly one LLM seat is in play (the historical single-seat shape,
    `agent` being that seat's LLMDiplomat), else (sweep_record,
    telemetry_record, final_state, agents_by_seat) where agents_by_seat
    is a dict[int, LLMDiplomat] keyed by seat.
    """
    seats = sorted(llm_seats) if llm_seats is not None else [llm_seat]
    if not seats:
        raise ValueError("llm_seats must be non-empty")
    if len(set(seats)) != len(seats):
        raise ValueError(f"llm_seats contains duplicate seat(s): {seats}")

    # NB: distinguish an EXPLICIT empty list (a legitimate all-LLM roster:
    # zero heuristic seats) from "not passed" -- `heuristic_names or [...]`
    # would treat [] as falsy and silently pad the game with 3 phantom
    # GreedyHold seats, mis-sizing an all-LLM table (caught in review).
    heuristic_names = (
        list(heuristic_names)
        if heuristic_names is not None
        else ["GreedyHold", "GreedyHold", "GreedyHold"]
    )
    num_players = len(seats) + len(heuristic_names)
    for s in seats:
        if not (0 <= s < num_players):
            raise ValueError(
                f"llm_seat {s} out of range for num_players={num_players}"
            )

    seat_set = set(seats)
    agent_names: list[str] = []
    h_iter = iter(heuristic_names)
    for i in range(num_players):
        agent_names.append("LLMDiplomat" if i in seat_set else next(h_iter))

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

    agents_by_seat: dict[int, LLMDiplomat] = {s: llm_agent_factory() for s in seats}
    agents: dict[PlayerId, object] = {}
    for i, name in enumerate(agent_names):
        agents[i] = agents_by_seat[i] if i in seat_set else ROSTER[name]()

    final = play_game(agents, state=state)

    sweep = {
        "game_id": game_id,
        "seed": seed,
        "agents": agent_names,
        "llm_seat": seats[0],
        "llm_seats": seats,
        "total_turns": final.turn,
        "final_scores": [final.scores.get(p, 0.0) for p in range(num_players)],
        "eliminated": sorted(final.eliminated),
        "winners": final.winners(),
        "detente_reached": final.detente_reached,
    }

    per_seat_telemetry: dict[int, dict] = {}
    total_decisions = 0
    total_fell_back = 0
    for s in seats:
        agent = agents_by_seat[s]
        n = len(agent.decision_log)
        fails = sum(1 for r in agent.decision_log if r["fell_back"])
        per_seat_telemetry[s] = {"n_decisions": n, "parse_fail_count": fails}
        total_decisions += n
        total_fell_back += fails

    telemetry = {
        "game_id": game_id,
        "llm_seat": seats[0],
        "llm_seats": seats,
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
        "n_decisions": total_decisions,
        "parse_fail_count": total_fell_back,
        "per_seat": per_seat_telemetry,
    }

    if len(seats) == 1:
        return sweep, telemetry, final, agents_by_seat[seats[0]]
    return sweep, telemetry, final, agents_by_seat


def render_transcript(
    state: GameState, llm_seat: int, llm_seats: list[int] | None = None
) -> str:
    """Human-readable per-turn transcript: stances, declared intents,
    betrayals, pact breaches, final reputation -- the "read the
    scheming" artifact. Renders all seats regardless of which are
    LLM-driven; `llm_seat`/`llm_seats` only label the header."""
    seats = sorted(llm_seats) if llm_seats is not None else [llm_seat]
    seats_label = ", ".join(str(s) for s in seats)
    plural = "s" if len(seats) != 1 else ""
    lines = [f"# Foedus LLM Diplomat transcript — LLM seat{plural} {seats_label}", ""]
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
        description="Run N foedus games with one or more LLMDiplomat seats vs a "
                     "heuristic roster.\n\n"
                     "Multi-seat probe roster example (slice-2 coordination probe -- "
                     "does an LLM table detect + coordinate against a freerider):\n"
                     "    --llm-seats 0,1,2 --heuristics DishonestCooperator\n"
                     "gives 3 LLMDiplomat seats + 1 scripted DishonestCooperator "
                     "freerider.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--num-games", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--seed-offset", "--seed", type=int, default=0,
                        dest="seed_offset")
    parser.add_argument("--llm-seat", type=int, default=0,
                        help="Single LLM seat index. Ignored if --llm-seats is given.")
    parser.add_argument("--llm-seats", type=str, default=None,
                        help="Comma-separated LLM seat indices, e.g. '0,1,2' -- "
                             "drives multiple LLMDiplomat seats at once. Overrides "
                             "--llm-seat.")
    parser.add_argument("--heuristics", type=str,
                        default="GreedyHold,Cooperator,TitForTat",
                        help="Comma-separated heuristic names for the non-LLM seats. "
                             "A single name fills every non-LLM seat when "
                             "--num-players is given (otherwise its count must equal "
                             "the number of non-LLM seats).")
    parser.add_argument("--num-players", type=int, default=None,
                        help="Total seat count. Omit to infer as len(llm_seats) + "
                             "len(heuristics). Needed only when --heuristics gives "
                             "one name that should fill more than one non-LLM seat.")
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
    parser.add_argument("--recip-ledger", action="store_true",
                        help="Enable the reciprocation-memory arm: sets "
                             "FOEDUS_LLM_RECIP_LEDGER=1 so each LLMDiplomat seat "
                             "carries the agent-side reciprocation record in its "
                             "negotiation prompt. Default OFF (baseline arm).")
    args = parser.parse_args(argv)

    if args.backend:
        os.environ["FOEDUS_LLM_BACKEND"] = args.backend
    if args.model:
        os.environ["FOEDUS_LLM_MODEL"] = args.model
    if args.recip_ledger:
        os.environ["FOEDUS_LLM_RECIP_LEDGER"] = "1"

    factory = llm_agent_factory or LLMDiplomat
    archetype = Archetype(args.archetype)

    if args.llm_seats:
        llm_seats = [int(x.strip()) for x in args.llm_seats.split(",") if x.strip()]
        if not llm_seats:
            parser.error("--llm-seats parsed to no seats; give e.g. '0,1,2'")
    else:
        llm_seats = [args.llm_seat]
    if len(set(llm_seats)) != len(llm_seats):
        parser.error(f"--llm-seats contains duplicate seat(s): {llm_seats}")

    heuristic_name_list = [h.strip() for h in args.heuristics.split(",") if h.strip()]
    if args.num_players is not None:
        n_heuristic_seats = args.num_players - len(llm_seats)
        if n_heuristic_seats < 0:
            parser.error(
                f"--num-players {args.num_players} is smaller than the "
                f"{len(llm_seats)} seat(s) in --llm-seats"
            )
        if len(heuristic_name_list) == 1:
            heuristic_names = heuristic_name_list * n_heuristic_seats
        elif len(heuristic_name_list) == n_heuristic_seats:
            heuristic_names = heuristic_name_list
        else:
            parser.error(
                f"--heuristics gives {len(heuristic_name_list)} name(s) but "
                f"{n_heuristic_seats} non-LLM seat(s) are needed for --num-players "
                f"{args.num_players} with {len(llm_seats)} LLM seat(s); pass exactly "
                f"1 name to fill all non-LLM seats, or exactly {n_heuristic_seats} "
                f"names."
            )
    else:
        heuristic_names = heuristic_name_list

    num_players = len(llm_seats) + len(heuristic_names)
    for s in llm_seats:
        if not (0 <= s < num_players):
            parser.error(
                f"--llm-seats seat {s} out of range for num_players={num_players} "
                f"({len(llm_seats)} llm seat(s) + {len(heuristic_names)} heuristic "
                f"seat(s))"
            )

    is_multi = len(llm_seats) > 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_decisions = 0
    total_fell_back = 0
    per_seat_totals: dict[int, dict[str, int]] = {
        s: {"n_decisions": 0, "parse_fail_count": 0} for s in llm_seats
    }

    with (out_dir / "sweep.jsonl").open("w") as sweep_f, \
         (out_dir / "telemetry.jsonl").open("w") as telemetry_f:
        for i in range(args.num_games):
            game_id = i
            seed = args.seed_offset + i
            sweep, telemetry, final_state, result = run_one_llm_game(
                game_id, seed, llm_seats=llm_seats,
                heuristic_names=heuristic_names, max_turns=args.max_turns,
                archetype=archetype, map_radius=args.map_radius,
                llm_agent_factory=factory,
            )
            sweep_f.write(json.dumps(sweep) + "\n")
            telemetry_f.write(json.dumps(telemetry) + "\n")
            total_decisions += telemetry["n_decisions"]
            total_fell_back += telemetry["parse_fail_count"]
            for s in llm_seats:
                seat_t = telemetry["per_seat"][s]
                per_seat_totals[s]["n_decisions"] += seat_t["n_decisions"]
                per_seat_totals[s]["parse_fail_count"] += seat_t["parse_fail_count"]

            agents_by_seat = result if is_multi else {llm_seats[0]: result}
            if is_multi:
                for s in llm_seats:
                    agent = agents_by_seat[s]
                    with (out_dir / f"decisions_game{game_id}_seat{s}.jsonl").open(
                        "w"
                    ) as decisions_f:
                        for record in agent.decision_log:
                            decisions_f.write(json.dumps(record, default=str) + "\n")
            else:
                agent = agents_by_seat[llm_seats[0]]
                with (out_dir / f"decisions_game{game_id}.jsonl").open("w") as decisions_f:
                    for record in agent.decision_log:
                        decisions_f.write(json.dumps(record, default=str) + "\n")

            if i < args.transcripts:
                (out_dir / f"transcript_game{game_id}.md").write_text(
                    render_transcript(
                        final_state, llm_seat=llm_seats[0], llm_seats=llm_seats
                    )
                )

            per_seat_str = ""
            if is_multi:
                per_seat_str = " [" + ", ".join(
                    f"seat{s}={telemetry['per_seat'][s]['parse_fail_count']}/"
                    f"{telemetry['per_seat'][s]['n_decisions']}"
                    for s in llm_seats
                ) + "]"
            print(
                f"game {game_id}: turns={sweep['total_turns']} "
                f"scores={sweep['final_scores']} "
                f"parse_fail={telemetry['parse_fail_count']}/{telemetry['n_decisions']}"
                f"{per_seat_str}"
            )

    rate = (total_fell_back / total_decisions) if total_decisions else 0.0
    print(f"\n{args.num_games} game(s) written to {out_dir}")
    print(f"overall parse-fail rate: {total_fell_back}/{total_decisions} ({rate:.1%})")
    if is_multi:
        for s in llm_seats:
            t = per_seat_totals[s]
            r = (t["parse_fail_count"] / t["n_decisions"]) if t["n_decisions"] else 0.0
            print(
                f"  seat {s} parse-fail rate: "
                f"{t['parse_fail_count']}/{t['n_decisions']} ({r:.1%})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
