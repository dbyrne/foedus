"""G1 Phase B — seed-paired trained-vs-base eval orchestrator.

Runs ONE commit-reveal-sealed, seed-paired campaign that answers both Phase B
questions (see ``docs/research/2026-07-10-gym-g1/phase-b/prereg.md``):

  * **B1** — does ``foedus-entrant-v1`` (distilled) beat its own untrained base
    ``foedus-base-v1`` in the MODEL seat?
  * **B2** — does a table containing the trained entrant contain the scripted
    freerider (Golf) better than the same table with the base model?

Table = 4 seats: ``[MODEL, Golf-freerider, anchorA, anchorB]``. For each sealed
seed the game is run **twice** — ``MODEL=trained`` then ``MODEL=base`` — under
byte-identical conditions (same board, same seat layout, same scripted
opponents); the ONLY variable is the model weights in the MODEL seat. The MODEL
seat rotates by seed (``seed_index % num_seats``) to control for position.

Design guarantees:

  * **$0 API.** Each MODEL seat is an ``LLMDiplomat`` driven by an explicitly
    constructed :class:`OllamaClient` (local ``/api/chat``) — the anthropic /
    claude-cli backends are never reachable from this script. Anchors + the
    freerider are scripted heuristics.
  * **Seed-paired fairness is load-bearing.** Before game 0 the initial board
    of every seed is fingerprinted (a canonical hash of map + units + config)
    and sealed into ``phaseb_plan.json``; every arm re-derives its board and
    **asserts** the fingerprint matches, so a silently mis-paired game aborts
    loudly instead of contaminating the claim.
  * **Independent games.** Each game gets a FRESH ``LLMDiplomat`` (no cross-game
    memory, no reciprocation ledger) — the unit of analysis is a single (seed,
    arm) game, so nothing leaks between pairs or across seeds.
  * **Sealed + crash-resumable.** Reuses the ruleset-v1 commit-reveal seal
    (``foedus.eval.campaign``). Each game is banked to ``sweep.jsonl`` as it
    finishes; ``--resume`` continues banked-only (a torn trailing line is
    dropped and its game re-run).

Reuses the untouched single-game harness ``run_one_llm_game`` and the sealing
helpers in ``foedus.eval.campaign``; this is a driver only (no engine change).

Example (seal only, then run detached):

    PYTHONPATH=. python3 scripts/foedus_phaseb_paired_eval.py \
        --match-id phaseb-gym-g1-2026-07-10 --num-seeds 12 \
        --out-dir docs/research/2026-07-10-gym-g1/phase-b/run --dry-run
    # ... commit the sealed commitment + prereg ...
    PYTHONPATH=. python3 scripts/foedus_phaseb_paired_eval.py \
        --match-id phaseb-gym-g1-2026-07-10 --num-seeds 12 \
        --out-dir docs/research/2026-07-10-gym-g1/phase-b/run --resume
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from foedus.core import Archetype, GameConfig            # noqa: E402
from foedus.mapgen import generate_map                    # noqa: E402
from foedus.resolve import initial_state                  # noqa: E402
from foedus.eval import campaign                          # noqa: E402
from foedus.eval.phaseb import (                          # noqa: E402
    board_fingerprint,
    plan_paired_seating,
)

from foedus_llm_diplomat_run import (                     # noqa: E402
    run_one_llm_game,
    render_transcript,
)

ARMS = ("trained", "base")  # deterministic per-seed run order


def _build_cfg(seed: int, *, num_seats: int, max_turns: int,
               archetype: Archetype, map_radius: int) -> GameConfig:
    return GameConfig(num_players=num_seats, max_turns=max_turns, seed=seed,
                      archetype=archetype, map_radius=map_radius)


def _expected_fingerprint(seed: int, *, num_seats: int, max_turns: int,
                          archetype: Archetype, map_radius: int) -> str:
    cfg = _build_cfg(seed, num_seats=num_seats, max_turns=max_turns,
                     archetype=archetype, map_radius=map_radius)
    m = generate_map(num_seats, seed=seed, archetype=cfg.archetype,
                     map_radius=cfg.map_radius)
    return board_fingerprint(initial_state(cfg, m))


def _read_banked_rows(path: Path) -> list[dict]:
    """Parse banked sweep rows; DROP a torn trailing line (crash mid-write) and
    re-run that game, but HARD-FAIL on a non-trailing corrupt line (real
    corruption a resume must not paper over)."""
    if not path.exists():
        return []
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    rows: list[dict] = []
    for i, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                print(f"[resume] WARNING: dropping torn trailing line {i + 1} of "
                      f"{path.name} (a crash mid-write); its game will re-run.",
                      file=sys.stderr)
                break
            raise SystemExit(
                f"{path.name}: line {i + 1} is not valid JSON and is NOT the last "
                f"line — refusing to resume over corruption.")
    return rows


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--match-id", required=True,
                   help="Stable match id; domain-separates the seed commitment.")
    p.add_argument("--num-seeds", type=int, default=8,
                   help="Number of sealed seeds (paired games = 2 * num_seeds).")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--trained-model", default="foedus-entrant-v1:latest")
    p.add_argument("--base-model", default="foedus-base-v1:latest")
    p.add_argument("--freerider", default="DishonestCooperator",
                   help="Heuristic CLASS for the Golf freerider seat.")
    p.add_argument("--anchors", default="Cooperator,TitForTat",
                   help="Comma-separated heuristic CLASSES for the two anchor "
                        "seats.")
    p.add_argument("--max-turns", type=int, default=12,
                   help="Ruleset-v1 default is 12.")
    p.add_argument("--archetype", default="continental_sweep")
    p.add_argument("--map-radius", type=int, default=2)
    p.add_argument("--ollama-timeout", type=float, default=180.0)
    p.add_argument("--ollama-host", default=None)
    p.add_argument("--transcripts", type=int, default=1,
                   help="Render the first N seeds' pairs to markdown (audit).")
    p.add_argument("--seed-rng", type=int, default=None,
                   help="TEST/REPRO ONLY: seed the seed-draw RNG (a real match "
                        "omits this for a true CSPRNG draw).")
    p.add_argument("--dry-run", action="store_true",
                   help="Seal + write plan/secret + print the commitment; run NO "
                        "game.")
    p.add_argument("--resume", action="store_true",
                   help="Resume a sealed match in --out-dir (banked-only).")
    return p


def _model_for_arm(arm: str, args) -> str:
    return args.trained_model if arm == "trained" else args.base_model


def _make_model_agent(arm: str, args, agent_factory):
    """Construct the MODEL seat's agent. Test injection wins; otherwise an
    LLMDiplomat wired to an EXPLICIT local OllamaClient for this arm's model —
    no API-backed backend is reachable from here."""
    if agent_factory is not None:
        return agent_factory()
    from foedus.agents.llm.client import OllamaClient
    from foedus.agents.llm.diplomat import LLMDiplomat
    client = OllamaClient(model=_model_for_arm(arm, args), host=args.ollama_host,
                          timeout=args.ollama_timeout)
    # recip_ledger / campaign explicitly OFF: independent single games.
    return LLMDiplomat(client=client, recip_ledger=False, campaign=False)


def main(argv: list[str] | None = None, *, agent_factory=None) -> int:
    args = build_parser().parse_args(argv)

    anchors = [a.strip() for a in args.anchors.split(",") if a.strip()]
    if not anchors:
        build_parser().error("--anchors parsed to no classes")
    num_seats = 2 + len(anchors)  # MODEL + Golf + anchors
    archetype = Archetype(args.archetype)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    secret_path = out_dir / "seed_manifest.secret.json"
    sweep_path = out_dir / "sweep.jsonl"
    resuming = args.resume and not args.dry_run

    # --- seal (or reload a sealed match) -------------------------------------
    # Protect the published commitment: once a match is sealed (secret on disk),
    # the ONLY way to run/continue it is --resume. A fresh seal (incl. --dry-run)
    # refuses to overwrite an existing secret, so re-running the seal step can't
    # silently redraw the seeds and break the commitment.
    if secret_path.exists() and not resuming:
        build_parser().error(
            f"a sealed match already exists in {out_dir} "
            "(seed_manifest.secret.json). Use --resume to run/continue it; "
            "seal a NEW match in a fresh --out-dir. Refusing to overwrite the "
            "published commitment.")
    if resuming:
        if not secret_path.exists():
            build_parser().error(
                "--resume: missing seed_manifest.secret.json — nothing sealed to "
                "resume in " + str(out_dir) + ".")
        # sweep.jsonl may not exist yet (first run right after the seal) — that
        # is simply "0 games banked", handled by _read_banked_rows below.
        secret = json.loads(secret_path.read_text())
        for field, want in (("match_id", args.match_id),
                            ("num_seeds", args.num_seeds),
                            ("freerider", args.freerider),
                            ("anchors", anchors),
                            ("trained_model", args.trained_model),
                            ("base_model", args.base_model)):
            if secret.get(field) != want:
                build_parser().error(
                    f"--resume: {field} {want!r} != sealed {secret.get(field)!r}")
        seeds = secret["seeds"]
        nonce = secret["nonce"]
        sealed = campaign.SeedManifest(
            match_id=args.match_id, num_games=args.num_seeds,
            domain=campaign.DOMAIN,
            commit=campaign.seed_commitment(args.match_id, seeds, nonce))
    else:
        rng = random.Random(args.seed_rng) if args.seed_rng is not None else None
        sealed, seeds, nonce = campaign.seal(args.match_id, args.num_seeds, rng=rng)
        (out_dir / "seed_manifest.sealed.json").write_text(
            json.dumps(sealed.to_dict(), indent=2))
        secret_path.write_text(json.dumps({
            "match_id": args.match_id, "num_seeds": args.num_seeds,
            "freerider": args.freerider, "anchors": anchors,
            "trained_model": args.trained_model, "base_model": args.base_model,
            "seeds": seeds, "nonce": nonce,
        }, indent=2))

    # --- per-seed seat plan + sealed board fingerprints ----------------------
    seatings = [plan_paired_seating(i, freerider_class=args.freerider,
                                    anchor_classes=anchors, num_seats=num_seats)
                for i in range(args.num_seeds)]
    expected_fp = {
        i: _expected_fingerprint(seeds[i], num_seats=num_seats,
                                 max_turns=args.max_turns, archetype=archetype,
                                 map_radius=args.map_radius)
        for i in range(args.num_seeds)
    }
    plan = {
        "match_id": args.match_id,
        "num_seeds": args.num_seeds,
        "num_games": 2 * args.num_seeds,
        "num_seats": num_seats,
        "arms": list(ARMS),
        "trained_model": args.trained_model,
        "base_model": args.base_model,
        "freerider_class": args.freerider,
        "golf_handle": "Golf",
        "anchors": anchors,
        "board": {"num_players": num_seats, "max_turns": args.max_turns,
                  "archetype": archetype.value, "map_radius": args.map_radius},
        "seat_rotation": "model_seat = seed_index % num_seats",
        "seatings": [{
            "seed_index": ps.seed_index,
            "model_seat": ps.model_seat,
            "golf_seat": ps.golf_seat,
            "anchor_seats": ps.anchor_seats,
            "role_by_seat": ps.role_by_seat,
            "heuristic_names": ps.heuristic_names,
            "board_fingerprint": expected_fp[ps.seed_index],
        } for ps in seatings],
    }
    (out_dir / "phaseb_plan.json").write_text(json.dumps(plan, indent=2))

    print(f"=== G1 Phase B seed-paired eval: {args.match_id} ===")
    print(f"seats={num_seats} turns={args.max_turns} archetype={archetype.value} "
          f"radius={args.map_radius}")
    print(f"MODEL: trained={args.trained_model}  base={args.base_model}")
    print(f"table roles: MODEL + Golf({args.freerider}) + anchors={anchors}")
    print(f"seed commitment (published pre-match): {sealed.commit}")
    print(f"num_seeds={args.num_seeds}  paired games={2*args.num_seeds}  "
          f"out-dir={out_dir}")

    if args.dry_run:
        print("\n[dry-run] sealed manifest + plan + secret written; no games run.")
        return 0

    # --- run the paired games ------------------------------------------------
    banked = _read_banked_rows(sweep_path)
    done = {(r["seed_index"], r["arm"]) for r in banked}
    # Truncate any torn trailing line by rewriting the clean banked rows.
    with sweep_path.open("w") as f:
        for r in banked:
            f.write(json.dumps(r, default=str) + "\n")

    total_games = 2 * args.num_seeds
    per_game_wall = [float(r.get("wall_clock_s") or 0.0) for r in banked]
    model_decisions = sum(int(r.get("n_decisions") or 0) for r in banked)
    model_fails = sum(int(r.get("parse_fail_count") or 0) for r in banked)
    match_start = time.time()

    telemetry_path = out_dir / "telemetry.jsonl"
    with sweep_path.open("a") as sweep_f, telemetry_path.open("a") as tele_f:
        for i in range(args.num_seeds):
            ps = seatings[i]
            seed = seeds[i]
            for arm in ARMS:
                if (i, arm) in done:
                    continue
                agent = _make_model_agent(arm, args, agent_factory)
                t0 = time.time()
                sweep, telemetry, final_state, _ = run_one_llm_game(
                    i, seed,
                    llm_seats=[ps.model_seat],
                    heuristic_names=ps.heuristic_names,
                    max_turns=args.max_turns,
                    archetype=archetype,
                    map_radius=args.map_radius,
                    agents_by_seat={ps.model_seat: agent},
                )
                dt = time.time() - t0

                # LOAD-BEARING pairing assertion: this arm's board must match the
                # sealed fingerprint for this seed (so trained + base are proven
                # to have played byte-identical starting conditions).
                fp = _expected_fingerprint(
                    seed, num_seats=num_seats, max_turns=args.max_turns,
                    archetype=archetype, map_radius=args.map_radius)
                if fp != expected_fp[i]:
                    raise SystemExit(
                        f"seed_index {i} arm {arm}: board fingerprint {fp} != "
                        f"sealed {expected_fp[i]} — pairing broken, aborting.")

                n_dec = telemetry["n_decisions"]
                n_fail = telemetry["parse_fail_count"]
                # Coverage guard: a game where the MODEL seat made ZERO decisions
                # is broken (not a valid data point) — fail loudly, don't bank it.
                if n_dec < 1:
                    raise SystemExit(
                        f"seed_index {i} arm {arm}: MODEL seat made 0 decisions — "
                        f"broken game, refusing to bank.")

                row = {
                    "seed_index": i,
                    "seed": seed,
                    "arm": arm,
                    "model_tag": _model_for_arm(arm, args),
                    "model_seat": ps.model_seat,
                    "golf_seat": ps.golf_seat,
                    "anchor_seats": ps.anchor_seats,
                    "role_by_seat": ps.role_by_seat,
                    "agents": sweep["agents"],
                    "heuristic_names": ps.heuristic_names,
                    "final_scores": sweep["final_scores"],
                    "winners": sweep["winners"],
                    "eliminated": sweep["eliminated"],
                    "detente_reached": sweep["detente_reached"],
                    "total_turns": sweep["total_turns"],
                    "wall_clock_s": round(dt, 1),
                    "n_decisions": n_dec,
                    "parse_fail_count": n_fail,
                    "board_fingerprint": fp,
                }
                sweep_f.write(json.dumps(row, default=str) + "\n")
                sweep_f.flush()

                telemetry["seed_index"] = i
                telemetry["arm"] = arm
                telemetry["role_by_seat"] = ps.role_by_seat
                tele_f.write(json.dumps(telemetry, default=str) + "\n")
                tele_f.flush()

                if i < args.transcripts:
                    (out_dir / f"transcript_seed{i}_{arm}.md").write_text(
                        render_transcript(final_state, llm_seat=ps.model_seat))

                per_game_wall.append(dt)
                model_decisions += n_dec
                model_fails += n_fail
                done.add((i, arm))
                run_n = len(per_game_wall)
                print(f"seed {i} [{arm:<7}] {dt/60:.1f}m turns={sweep['total_turns']} "
                      f"model@seat{ps.model_seat} scores={sweep['final_scores']} "
                      f"parse_fail={n_fail}/{n_dec} "
                      f"[{run_n}/{total_games} done, "
                      f"mean {sum(per_game_wall)/run_n/60:.1f}m/game]")

    # --- pair-consistency check (every seed has both arms, identical board) --
    all_rows = _read_banked_rows(sweep_path)
    by_seed: dict[int, dict[str, dict]] = {}
    for r in all_rows:
        by_seed.setdefault(r["seed_index"], {})[r["arm"]] = r
    for i in range(args.num_seeds):
        pair = by_seed.get(i, {})
        if set(pair) != set(ARMS):
            raise SystemExit(f"seed_index {i}: incomplete pair {sorted(pair)} — "
                             "expected both arms; re-run --resume.")
        if pair["trained"]["board_fingerprint"] != pair["base"]["board_fingerprint"]:
            raise SystemExit(f"seed_index {i}: arms saw DIFFERENT boards — pairing "
                             "invariant violated.")
        if pair["trained"]["role_by_seat"] != pair["base"]["role_by_seat"]:
            raise SystemExit(f"seed_index {i}: arms had different seat layouts.")

    # --- reveal --------------------------------------------------------------
    revealed = campaign.revealed_manifest(sealed, seeds, nonce)
    if not campaign.verify(revealed):
        raise RuntimeError("seed manifest failed self-verification")
    (out_dir / "seed_manifest.revealed.json").write_text(
        json.dumps(revealed.to_dict(), indent=2))

    match_compute = sum(per_game_wall)
    n = len(per_game_wall) or 1
    rate = (model_fails / model_decisions) if model_decisions else 0.0
    summary = {
        "match_id": args.match_id,
        "num_seeds": args.num_seeds,
        "num_games": total_games,
        "match_wall_clock_s": round(match_compute, 1),
        "mean_game_wall_clock_s": round(match_compute / n, 1),
        "per_game_wall_clock_s": [round(x, 1) for x in per_game_wall],
        "model_total_decisions": model_decisions,
        "model_total_parse_fails": model_fails,
        "model_parse_fail_rate": round(rate, 4),
        "seed_commitment": sealed.commit,
        "resumed": resuming,
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nmatch engine-compute: {match_compute/3600:.2f}h "
          f"({summary['mean_game_wall_clock_s']/60:.1f}m/game mean)")
    print(f"MODEL parse-fail (all arms): {model_fails}/{model_decisions} "
          f"({rate:.1%})")
    print("seeds revealed -> seed_manifest.revealed.json (verify OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
