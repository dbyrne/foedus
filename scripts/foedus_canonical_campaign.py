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
from foedus.agents.llm.campaign_memory import IdentityContext  # noqa: E402
from foedus.presets import ruleset_v1            # noqa: E402
from foedus.scoring import compute_match_result  # noqa: E402

from foedus_llm_diplomat_run import (            # noqa: E402
    run_one_llm_game,
    render_transcript,
    _env_flag,
    _env_int,
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


def _read_jsonl_rows(path: Path) -> list[dict]:
    """Parse a JSONL file into rows, failing LOUD + CLEAR on a torn final line.
    A crash can leave a partial (non-JSON) last line; silently counting it as a
    completed game would corrupt a resume (wrong `completed`, then a broken
    append), so refuse with an actionable message rather than a raw traceback."""
    rows = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as ex:
            raise SystemExit(
                f"{path.name}: line {i} is not valid JSON ({ex}). A crash likely "
                f"left a partial line; remove the trailing partial line and "
                f"re-run --resume.")
    return rows


def _resume_state(out_dir: Path, completed_rows: list, persistent: dict,
                  llm_entrants: list, entrant_identities: list, rating) -> None:
    """Restore in-RAM state a crashed match lost: each entrant's cross-game
    memory (matched by stable identity since seats rotate) and the OpenSkill
    ratings (replayed from the completed sweep rows, in order)."""
    from foedus.agents.llm.campaign_memory import GameRecord

    completed = len(completed_rows)
    # Restore cross-game memory from the newest completed game that actually has
    # per-seat memory files. Normally that's game completed-1, but a crash can
    # land AFTER a game's sweep row is flushed but BEFORE its memory files are
    # written (they trail behind an extra self-note LLM call); fall back to the
    # newest earlier game that has them (memory is cumulative, so an earlier
    # snapshot is a correct—if slightly staler—restore) instead of silently
    # resuming with zero cross-game memory.
    by_identity: dict[str, list] = {}
    mem_game = None
    for g in range(completed - 1, -1, -1):
        files = list(out_dir.glob(f"campaign_memory_game{g}_seat*.json"))
        if files:
            mem_game = g
            for p in files:
                d = json.loads(p.read_text())
                by_identity[d.get("entrant_identity")] = d.get("records", [])
            break
    if completed > 0 and mem_game is None:
        print("[resume] WARNING: no campaign_memory_game*_seat*.json found for "
              f"{completed} completed game(s); resuming with EMPTY cross-game "
              "memory.", file=sys.stderr)
    elif mem_game is not None and mem_game != completed - 1:
        print(f"[resume] note: newest persisted memory is game {mem_game} (not "
              f"{completed - 1}); self-notes for games {mem_game + 1}.."
              f"{completed - 1} were not written before the crash.",
              file=sys.stderr)
    for e in llm_entrants:
        recs = [GameRecord.from_dict(r)
                for r in by_identity.get(entrant_identities[e], [])]
        persistent[e].load_campaign_records(recs)

    if rating is not None:
        from foedus.eval.ruleset import ranks_from_record
        from foedus.scoring import MatchResult
        for row in completed_rows:
            mr = MatchResult(rank=ranks_from_record(row), payout={},
                             final_scores={}, detente=False, solo_winner=None)
            rating.update(mr, identities=row["agents"])


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
    p.add_argument("--entrants", default="Delta,Echo,Foxtrot",
                   help="Comma-separated stable NEUTRAL handles for the LLM "
                        "entrants (3 by default). These are what opponents see + "
                        "the OpenSkill identities (Ruleset v1.1, identity-keyed).")
    p.add_argument("--freerider", default="DishonestCooperator",
                   help="Heuristic CLASS name for the house freerider seat "
                        "(what run_one_llm_game instantiates).")
    p.add_argument("--freerider-identity", default="Golf",
                   help="NEUTRAL arena handle for the freerider — nothing hinting "
                        "at its nature. Agents + OpenSkill see only this handle; "
                        "the handle->role map is recorded operator-side only.")
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
    p.add_argument("--max-turns", type=int, default=None,
                   help="TEST/REPRO ONLY: override the ruleset_v1 preset's "
                        "max_turns (12). A real match omits this.")
    p.add_argument("--seed-rng", type=int, default=None,
                   help="Seed the CSPRNG used to draw game seeds (TEST/REPRO "
                        "ONLY — a real match omits this for a true CSPRNG draw).")
    p.add_argument("--dry-run", action="store_true",
                   help="Emit the sealed manifest + per-game seating plan and "
                        "exit WITHOUT running any game (no LLM calls).")
    p.add_argument("--resume", action="store_true",
                   help="Resume a crashed match in --out-dir: reload the sealed "
                        "secret + each entrant's persisted cross-game memory and "
                        "continue from the first unfinished game (same seeds).")
    return p


def main(argv: list[str] | None = None, *, agent_factory=None) -> int:
    args = build_parser().parse_args(argv)

    entrant_llm = [e.strip() for e in args.entrants.split(",") if e.strip()]
    if not entrant_llm:
        build_parser().error("--entrants parsed to no identities")
    # Roster: LLM entrants first (indices 0..k-1), freerider last.
    entrant_identities = entrant_llm + [args.freerider_identity]
    # Handles double as OpenSkill identities, so duplicates would silently merge
    # two entrants into one rating — reject them.
    if len(set(entrant_identities)) != len(entrant_identities):
        build_parser().error(
            f"entrant/freerider handles must be unique, got {entrant_identities}")
    freerider_entrants = {len(entrant_llm)}  # the single trailing freerider seat
    num_seats = len(entrant_identities)
    rotate = not args.no_rotation

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = ruleset_v1(num_players=num_seats)
    archetype = cfg.archetype
    max_turns = args.max_turns if args.max_turns is not None else cfg.max_turns
    map_radius = cfg.map_radius

    # --- §7.5 commit: seal (or reload a crashed match's sealed secret) -------
    secret_path = out_dir / "seed_manifest.secret.json"
    sweep_path = out_dir / "sweep.jsonl"
    completed = 0
    completed_rows: list = []
    resuming = args.resume and not args.dry_run
    if resuming:
        # Fail LOUD rather than silently re-seal + truncate a sealed match: a
        # --resume that can't find the operator-private secret + the sweep it
        # resumes must NOT fall through to a fresh seal (that would overwrite the
        # published commitment and clobber completed, real-cost games).
        missing = [p.name for p in (secret_path, sweep_path) if not p.exists()]
        if missing:
            build_parser().error(
                "--resume: required file(s) missing: " + ", ".join(missing) +
                " — refusing to re-seal / overwrite a sealed match.")
        secret = json.loads(secret_path.read_text())
        # Everything folded into the seed commitment (match_id) or the identity
        # keys (entrants, rotation) must match the sealed match, else the resume
        # would silently fork it: a different match_id yields a different commit
        # (a commit-reveal audit break that verify() still self-certifies), and
        # different entrants/rotation change the OpenSkill identities + seatings
        # mid-match. (`None` = an older secret that didn't record the field.)
        mismatch = []
        if secret.get("match_id") != args.match_id:
            mismatch.append(f"match_id {args.match_id!r} != sealed "
                            f"{secret.get('match_id')!r}")
        if secret.get("num_games") != args.num_games:
            mismatch.append(f"num_games {args.num_games} != sealed "
                            f"{secret.get('num_games')}")
        if secret.get("entrant_identities") not in (None, entrant_identities):
            mismatch.append(f"entrants {entrant_identities} != sealed "
                            f"{secret.get('entrant_identities')}")
        if secret.get("rotation") not in (None, rotate):
            mismatch.append(f"rotation {rotate} != sealed "
                            f"{secret.get('rotation')}")
        if mismatch:
            build_parser().error(
                "--resume: does not match the sealed match: " + "; ".join(mismatch))
        seeds = secret["seeds"]
        nonce = secret["nonce"]
        sealed = campaign.SeedManifest(
            match_id=args.match_id, num_games=args.num_games,
            domain=campaign.DOMAIN,
            commit=campaign.seed_commitment(args.match_id, seeds, nonce))
        completed_rows = _read_jsonl_rows(sweep_path)
        completed = len(completed_rows)
    else:
        rng = random.Random(args.seed_rng) if args.seed_rng is not None else None
        sealed, seeds, nonce = campaign.seal(args.match_id, args.num_games, rng=rng)
        (out_dir / "seed_manifest.sealed.json").write_text(
            json.dumps(sealed.to_dict(), indent=2)
        )
        # CRASH RECOVERY: persist the sealed secret (seeds + nonce + the identity
        # config that keys memory/ratings) to disk NOW, before any game runs, so
        # a crash before reveal loses neither the commit-reveal (the nonce) nor
        # the ability to resume the exact same match. Operator-private until
        # reveal (it becomes seed_manifest.revealed.json at match end).
        secret_path.write_text(json.dumps(
            {"match_id": args.match_id, "num_games": args.num_games,
             "entrant_identities": entrant_identities, "rotation": rotate,
             "seeds": seeds, "nonce": nonce}, indent=2))

    # --- per-game seating plan (audit + dry-run) -----------------------------
    seatings = [
        campaign.plan_seating(g, entrant_identities, freerider_entrants,
                              rotate=rotate)
        for g in range(args.num_games)
    ]
    freerider_handles = [entrant_identities[e] for e in sorted(freerider_entrants)]
    plan = {
        "match_id": args.match_id,
        "num_games": args.num_games,
        "num_seats": num_seats,
        "rotation": rotate,
        "entrant_identities": entrant_identities,
        "freerider_entrants": sorted(freerider_entrants),
        # operator-only (never shown to agents): which neutral handle is the
        # freerider house anchor, and each handle's true role.
        "freerider_handles": freerider_handles,
        "freerider_class": args.freerider,
        "handle_roles": {
            entrant_identities[e]: ("freerider" if e in freerider_entrants
                                    else "llm-entrant")
            for e in range(num_seats)
        },
        "board": {"num_players": num_seats, "max_turns": max_turns,
                  "map_radius": map_radius, "archetype": archetype.value,
                  "detente_threshold": cfg.detente_threshold},
        # Durably records the concurrency setting a sealed match ran under —
        # read at seal/plan time (pre-game-0), same source
        # (FOEDUS_PARALLEL_SEATS / FOEDUS_PARALLEL_SEATS_WORKERS) the
        # hot-swap integration point in docs/design/2026-07-05-parallel-seat-
        # calls.md uses to drive run_one_llm_game. Avoids a post-hoc "was
        # this WORKERS=2 or WORKERS=3?" audit question.
        "parallel_seats": {
            "enabled": _env_flag("FOEDUS_PARALLEL_SEATS"),
            "workers": _env_int("FOEDUS_PARALLEL_SEATS_WORKERS"),
        },
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

    if agent_factory is not None:
        factory = agent_factory  # test injection (StubLLMClient-backed agents)
    else:
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

    if resuming:
        _resume_state(out_dir, completed_rows, persistent, llm_entrants,
                      entrant_identities, rating)
        # Seed the whole-match accumulators from the completed games on disk so
        # run_summary.json reports true whole-match totals, not just the resume
        # leg. (sweep wall_clock_s = per-game engine compute; telemetry carries
        # the decision + parse-fail counts.)
        for row in completed_rows:
            per_game_wall.append(float(row.get("wall_clock_s") or 0.0))
        for trow in _read_jsonl_rows(out_dir / "telemetry.jsonl"):
            total_decisions += trow.get("n_decisions", 0) or 0
            total_fell_back += trow.get("parse_fail_count", 0) or 0
        print(f"[resume] {completed}/{args.num_games} games already done; "
              f"reloaded memory + ratings; continuing from game {completed}.")

    open_mode = "a" if resuming else "w"
    with (out_dir / "sweep.jsonl").open(open_mode) as sweep_f, \
         (out_dir / "telemetry.jsonl").open(open_mode) as telemetry_f:
        for g in range(completed, args.num_games):
            gs = seatings[g]
            seed = seeds[g]
            # clear within-game caches on every reused agent (memory kept)
            for e in llm_entrants:
                persistent[e].reset_for_new_game()

            agents_by_seat = {
                seat: persistent[gs.seat_to_entrant[seat]] for seat in gs.llm_seats
            }
            # Ruleset v1.1: give each reused agent this game's identity context
            # (its own stable handle + the full seat->handle legend) so prompts
            # show opponents by handle and cross-game memory keys on the handle.
            seat_to_handle = {s: gs.identity_by_seat[s] for s in range(num_seats)}
            for seat in gs.llm_seats:
                agents_by_seat[seat].set_identity_context(
                    IdentityContext(my_handle=gs.identity_by_seat[seat],
                                    seat_to_handle=dict(seat_to_handle)))

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

            # Relabel seats with stable entrant identities (neutral handles):
            # distinct OpenSkill identities for every seat incl. the freerider's
            # handle "Golf". The scorecard finds the freerider via the operator-
            # side freerider_handles in campaign_plan.json (never by class name,
            # which is deliberately not exposed to agents).
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
    if not campaign.verify(revealed):
        raise RuntimeError("seed manifest failed self-verification")
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

    # Engine compute = sum of per-game wall. Resume-safe by construction: a
    # multi-hour reboot gap in the middle must not inflate it, and a resumed
    # process's match_start covers only its own leg. per_game_wall + the totals
    # are seeded from disk on resume (above), so this is the true whole-match
    # figure. The live-process elapsed is reported separately (not persisted).
    match_compute = sum(per_game_wall)
    live_elapsed = time.time() - match_start
    n = len(per_game_wall) or 1
    rate = (total_fell_back / total_decisions) if total_decisions else 0.0
    summary = {
        "match_id": args.match_id,
        "num_games": args.num_games,
        "match_wall_clock_s": round(match_compute, 1),
        "mean_game_wall_clock_s": round(match_compute / n, 1),
        "per_game_wall_clock_s": [round(x, 1) for x in per_game_wall],
        "total_decisions": total_decisions,
        "total_fell_back": total_fell_back,
        "parse_fail_rate": round(rate, 4),
        "seed_commitment": sealed.commit,
        "resumed": resuming,
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nmatch engine-compute: {match_compute/3600:.2f}h "
          f"({summary['mean_game_wall_clock_s']/60:.1f}m/game mean)"
          + (f"  [this process leg: {live_elapsed/3600:.2f}h]" if resuming else ""))
    print(f"overall parse-fail: {total_fell_back}/{total_decisions} ({rate:.1%})")
    print(f"seeds revealed -> seed_manifest.revealed.json (verify OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
