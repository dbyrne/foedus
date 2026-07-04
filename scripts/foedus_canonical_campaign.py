"""Canonical ruleset-v1 campaign orchestrator.

Runs the ratified standard-format match (docs/design/2026-07-04-ruleset-v1.md)
by composing the pure match-protocol helpers in ``foedus.eval.campaign`` around
the existing single-game LLM harness (``scripts/foedus_llm_diplomat_run.py``,
untouched). Layers on top of ``--campaign`` what the format needs and the base
runner lacks:

  * **§7.4 cyclic seat rotation** — the roster (3 LLM entrants + 1 house
    freerider) rotates through the four seats; game ``k`` seats entrant ``e`` at
    ``(e + k) mod n``. Persistent per-entrant agents carry their cross-game
    memory with them as they move seats.
  * **§7.5 commit-reveal seeds** — a sealed SHA-256 seed manifest is written
    before any game is played and revealed (with the seeds + nonce) after.
  * **per-entrant identity** — each entrant (including the freerider house
    anchor) gets a stable identity, so OpenSkill rates entrants individually
    instead of collapsing every LLM seat into one ``"LLMDiplomat"`` rating.
  * **durable archival** — sweep / telemetry / per-seat decision-logs /
    transcripts / campaign-memory + self-notes / the seed manifest are all
    written under ``--out-dir`` in the format the scorecard + gym pipeline
    consume.

Engine and single-game harness are untouched; this is a driver.

Example (the canonical 8-game ruleset-v1 match):

    FOEDUS_LLM_CLI_TIMEOUT=300 PYTHONPATH=. python3 scripts/foedus_canonical_campaign.py \
        --match-id canonical-v1-2026-07-04 --num-games 8 \
        --backend claude-cli --model sonnet \
        --out-dir docs/research/2026-07-04-canonical-campaign-v1/run

    # standings + scorecard afterwards:
    PYTHONPATH=. python3 scripts/foedus_compute_ratings.py <out-dir>/sweep.jsonl
    PYTHONPATH=. python3 scripts/foedus_canonical_scorecard.py --out-dir <out-dir>
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

# Make the sibling single-game harness importable regardless of how this script
# is launched (its dir is sys.path[0] under `python3 scripts/...`, but be
# explicit so `uv run` / `-m` invocations work too).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from foedus.core import Archetype               # noqa: E402
from foedus.eval import campaign                 # noqa: E402
from foedus.presets import ruleset_v1            # noqa: E402
from foedus.scoring import compute_match_result  # noqa: E402

from foedus_llm_diplomat_run import (            # noqa: E402
    run_one_llm_game,
    render_transcript,
)

# Rating is an optional extra; import lazily so --dry-run works without it.
try:
    from foedus.rating import RatingSystem
except Exception:  # pragma: no cover - only hit when openskill missing
    RatingSystem = None


def _write_campaign_memory(out_dir: Path, agent, game_id: int, seat: int,
                           identity: str) -> None:
    """Persist one seat's cross-game memory (all records + verbatim self-notes)
    after a campaign game — cumulative, and tagged with the stable entrant
    identity so the rotated-seat archive stays auditable."""
    payload = {
        "game_index": game_id,
        "seat": seat,
        "entrant_identity": identity,
        "records": [r.to_dict() for r in agent.campaign_records()],
    }
    (out_dir / f"campaign_memory_game{game_id}_seat{seat}.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--match-id", required=True,
                   help="Stable match identifier; domain-separates the seed "
                        "commitment and labels the archive.")
    p.add_argument("--num-games", type=int, default=8,
                   help="Games in the match (default 8 = two 4-seat rotation "
                        "cycles).")
    p.add_argument("--out-dir", required=True,
                   help="Durable output directory (committed with the PR).")
    p.add_argument("--entrants", default="Sonnet-Alpha,Sonnet-Bravo,Sonnet-Charlie",
                   help="Comma-separated stable identities for the LLM entrants "
                        "(3 by default).")
    p.add_argument("--freerider", default="DishonestCooperator",
                   help="Heuristic class name for the house freerider seat.")
    p.add_argument("--freerider-identity", default="DishonestCooperator",
                   help="Rating/archive identity for the freerider (kept equal "
                        "to the class name so the scorecard finds it by name).")
    p.add_argument("--backend", default="claude-cli",
                   help="FOEDUS_LLM_BACKEND for the LLM seats.")
    p.add_argument("--model", default="sonnet", help="FOEDUS_LLM_MODEL.")
    p.add_argument("--cli-timeout", type=float, default=None,
                   help="FOEDUS_LLM_CLI_TIMEOUT seconds (default: client's 300).")
    p.add_argument("--no-rotation", action="store_true",
                   help="Pin entrants to fixed seats (disables §7.4 rotation). "
                        "For the memory-vs-rotation control arm only.")
    p.add_argument("--no-recip-ledger", action="store_true",
                   help="Disable the reciprocation-ledger scaffold (default ON).")
    p.add_argument("--no-campaign-memory", action="store_true",
                   help="Disable cross-game memory (default ON).")
    p.add_argument("--transcripts", type=int, default=None,
                   help="Number of games to render to markdown (default: all).")
    p.add_argument("--seed-rng", type=int, default=None,
                   help="Seed the CSPRNG used to draw game seeds (TEST/REPRO "
                        "ONLY — a real match omits this for a true CSPRNG draw).")
    p.add_argument("--dry-run", action="store_true",
                   help="Emit the sealed manifest + per-game seating plan and "
                        "exit WITHOUT running any game (no LLM calls).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    entrant_llm = [e.strip() for e in args.entrants.split(",") if e.strip()]
    if not entrant_llm:
        build_parser().error("--entrants parsed to no identities")
    # Roster: LLM entrants first (indices 0..k-1), freerider last.
    entrant_identities = entrant_llm + [args.freerider_identity]
    freerider_entrants = {len(entrant_llm)}  # the single trailing freerider seat
    num_seats = len(entrant_identities)
    rotate = not args.no_rotation

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = ruleset_v1(num_players=num_seats)
    archetype = cfg.archetype
    max_turns = cfg.max_turns
    map_radius = cfg.map_radius

    # --- §7.5 commit: draw + seal the seed list, publish before any game -----
    rng = random.Random(args.seed_rng) if args.seed_rng is not None else None
    sealed, seeds, nonce = campaign.seal(args.match_id, args.num_games, rng=rng)
    (out_dir / "seed_manifest.sealed.json").write_text(
        json.dumps(sealed.to_dict(), indent=2)
    )

    # --- per-game seating plan (audit + dry-run) -----------------------------
    seatings = [
        campaign.plan_seating(g, entrant_identities, freerider_entrants,
                              rotate=rotate)
        for g in range(args.num_games)
    ]
    plan = {
        "match_id": args.match_id,
        "num_games": args.num_games,
        "num_seats": num_seats,
        "rotation": rotate,
        "entrant_identities": entrant_identities,
        "freerider_entrants": sorted(freerider_entrants),
        "board": {"num_players": num_seats, "max_turns": max_turns,
                  "map_radius": map_radius, "archetype": archetype.value,
                  "detente_threshold": cfg.detente_threshold},
        "seatings": [
            {"game_index": s.game_index,
             "seat_to_entrant": s.seat_to_entrant,
             "identity_by_seat": s.identity_by_seat,
             "llm_seats": s.llm_seats,
             "freerider_seats": s.freerider_seats}
            for s in seatings
        ],
    }
    (out_dir / "campaign_plan.json").write_text(json.dumps(plan, indent=2))

    print(f"=== canonical ruleset-v1 campaign: {args.match_id} ===")
    print(f"seats={num_seats} turns={max_turns} radius={map_radius} "
          f"archetype={archetype.value} detente={cfg.detente_threshold} "
          f"rotation={'ON' if rotate else 'OFF'}")
    print(f"entrants={entrant_identities}  freerider_seat(entrant)="
          f"{sorted(freerider_entrants)}")
    print(f"seed commitment (published pre-match): {sealed.commit}")
    print(f"games={args.num_games}  out-dir={out_dir}")

    if args.dry_run:
        print("\n[dry-run] wrote seed_manifest.sealed.json + campaign_plan.json; "
              "no games run.")
        return 0

    # --- environment for the LLM seats (mirrors foedus_llm_diplomat_run) -----
    os.environ["FOEDUS_LLM_BACKEND"] = args.backend
    os.environ["FOEDUS_LLM_MODEL"] = args.model
    if args.cli_timeout is not None:
        os.environ["FOEDUS_LLM_CLI_TIMEOUT"] = str(args.cli_timeout)
    if not args.no_recip_ledger:
        os.environ["FOEDUS_LLM_RECIP_LEDGER"] = "1"
    if not args.no_campaign_memory:
        os.environ["FOEDUS_LLM_CAMPAIGN"] = "1"

    from foedus.agents.llm.diplomat import LLMDiplomat  # noqa: E402
    factory = LLMDiplomat

    # Persistent per-entrant LLM agents (index by entrant, NOT seat, so memory
    # travels with the entrant across rotated seats). Freerider is a stateless
    # heuristic re-instantiated inside run_one_llm_game each game.
    llm_entrants = [e for e in range(num_seats) if e not in freerider_entrants]
    persistent = {e: factory() for e in llm_entrants}

    rating = RatingSystem() if RatingSystem is not None else None
    transcripts = args.transcripts if args.transcripts is not None else args.num_games

    match_start = time.time()
    per_game_wall: list[float] = []
    total_decisions = 0
    total_fell_back = 0

    with (out_dir / "sweep.jsonl").open("w") as sweep_f, \
         (out_dir / "telemetry.jsonl").open("w") as telemetry_f:
        for g in range(args.num_games):
            gs = seatings[g]
            seed = seeds[g]
            # clear within-game caches on every reused agent (memory kept)
            for e in llm_entrants:
                persistent[e].reset_for_new_game()

            agents_by_seat = {
                seat: persistent[gs.seat_to_entrant[seat]] for seat in gs.llm_seats
            }

            t0 = time.time()
            sweep, telemetry, final_state, _ = run_one_llm_game(
                g, seed,
                llm_seats=gs.llm_seats,
                heuristic_names=[args.freerider],
                max_turns=max_turns,
                archetype=archetype,
                map_radius=map_radius,
                llm_agent_factory=factory,
                agents_by_seat=agents_by_seat,
            )
            dt = time.time() - t0
            per_game_wall.append(dt)

            # Relabel seats with stable entrant identities: distinct OpenSkill
            # identities for the LLM seats, freerider kept as its class name so
            # the scorecard still finds it by name.
            sweep["agents"] = list(gs.identity_by_seat)
            sweep["game_index"] = g
            sweep["seed"] = seed
            sweep["rotation"] = rotate
            sweep["seat_to_entrant"] = gs.seat_to_entrant
            sweep["identity_by_seat"] = gs.identity_by_seat
            sweep["llm_seats"] = gs.llm_seats
            sweep["freerider_seats"] = gs.freerider_seats
            sweep["wall_clock_s"] = round(dt, 1)
            sweep_f.write(json.dumps(sweep, default=str) + "\n")
            sweep_f.flush()

            telemetry["game_index"] = g
            telemetry["identity_by_seat"] = gs.identity_by_seat
            telemetry_f.write(json.dumps(telemetry, default=str) + "\n")
            telemetry_f.flush()
            total_decisions += telemetry["n_decisions"]
            total_fell_back += telemetry["parse_fail_count"]

            # per-seat decision logs (LLM seats only; freerider makes no calls)
            for seat in gs.llm_seats:
                agent = agents_by_seat[seat]
                with (out_dir / f"decisions_game{g}_seat{seat}.jsonl").open("w") as df:
                    for record in agent.decision_log:
                        df.write(json.dumps(record, default=str) + "\n")

            if g < transcripts:
                (out_dir / f"transcript_game{g}.md").write_text(
                    render_transcript(final_state, llm_seat=gs.llm_seats[0],
                                      llm_seats=gs.llm_seats)
                )

            # OpenSkill update from this game's competition ranks + identities
            if rating is not None:
                mr = compute_match_result(final_state)
                rating.update(mr, identities=list(gs.identity_by_seat))

            # cross-game memory: self-note (one extra LLM call/seat) + persist
            if not args.no_campaign_memory:
                for seat in gs.llm_seats:
                    agent = agents_by_seat[seat]
                    agent.finalize_game(final_state, seat, seed=seed, game_index=g)
                    _write_campaign_memory(out_dir, agent, g, seat,
                                           gs.identity_by_seat[seat])

            pf = telemetry["parse_fail_count"]
            nd = telemetry["n_decisions"]
            fr_seat = gs.freerider_seats[0]
            print(f"game {g}: {dt/60:.1f}m turns={sweep['total_turns']} "
                  f"freerider@seat{fr_seat} scores={sweep['final_scores']} "
                  f"parse_fail={pf}/{nd} "
                  f"[running mean {sum(per_game_wall)/len(per_game_wall)/60:.1f}m/game]")

    # --- §7.5 reveal: publish seeds + nonce; verify the commitment holds -----
    revealed = campaign.revealed_manifest(sealed, seeds, nonce)
    assert campaign.verify(revealed), "seed manifest failed self-verification"
    (out_dir / "seed_manifest.revealed.json").write_text(
        json.dumps(revealed.to_dict(), indent=2)
    )

    # --- standings ------------------------------------------------------------
    if rating is not None:
        board = [
            {"identity": ident, "mu": round(r.mu, 3), "sigma": round(r.sigma, 3),
             "conservative": round(r.conservative, 3)}
            for ident, r in rating.leaderboard()
        ]
        (out_dir / "standings.json").write_text(json.dumps(
            {"match_id": args.match_id, "num_games": args.num_games,
             "rating": "OpenSkill PlackettLuce, mu-3sigma", "standings": board},
            indent=2))
        print("\n=== OpenSkill standings (conservative mu-3sigma) ===")
        for row in board:
            print(f"  {row['identity']:<22} mu={row['mu']:.2f} "
                  f"sigma={row['sigma']:.2f} cons={row['conservative']:.2f}")

    match_wall = time.time() - match_start
    rate = (total_fell_back / total_decisions) if total_decisions else 0.0
    summary = {
        "match_id": args.match_id,
        "num_games": args.num_games,
        "match_wall_clock_s": round(match_wall, 1),
        "mean_game_wall_clock_s": round(sum(per_game_wall) / len(per_game_wall), 1),
        "per_game_wall_clock_s": [round(x, 1) for x in per_game_wall],
        "total_decisions": total_decisions,
        "total_fell_back": total_fell_back,
        "parse_fail_rate": round(rate, 4),
        "seed_commitment": sealed.commit,
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nmatch wall-clock: {match_wall/3600:.2f}h "
          f"({summary['mean_game_wall_clock_s']/60:.1f}m/game mean)")
    print(f"overall parse-fail: {total_fell_back}/{total_decisions} ({rate:.1%})")
    print(f"seeds revealed -> seed_manifest.revealed.json (verify OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
