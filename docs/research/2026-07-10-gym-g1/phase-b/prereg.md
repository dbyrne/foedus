# G1 Phase B — pre-registration (sealed, seed-paired trained-vs-base eval)

**Status:** committed BEFORE game 0. This document + the sealed seed commitment
are the pre-registration of a scientific claim; nothing below is changed after
the campaign starts (stay-plain mid-sealed-campaign).

**Seed commitment (published pre-match):**
`c5a25b271e1e4843766011ef82dcef526b18dd179036cdc4c87259c890019072`
(SHA-256, domain `foedus-ruleset-v1`, match-id `phaseb-gym-g1-2026-07-10`; see
`run/seed_manifest.sealed.json`). Seeds + nonce are sealed on disk
(`run/seed_manifest.secret.json`, operator-private) and revealed post-campaign
to `run/seed_manifest.revealed.json`, where `foedus.eval.campaign.verify()`
recomputes the commitment. The commit that adds THIS file (with no seeds) is the
timestamped "commitment published before any game" record.

## The claim under test

Distilling the 12 high-coordination Sonnet games (Phase A) into a local 3B
entrant produces a model that:

- **B1 — beats its own base:** `foedus-entrant-v1` (trained) outperforms
  `foedus-base-v1` (untrained Qwen2.5-3B, IDENTICAL q4_K_M serve path) in the
  MODEL seat, on FRESH sealed games (the memorization test — Phase A's low train
  loss + 716-example corpus make overfitting plausible; only fresh-game play
  adjudicates it).
- **B2 — helps contain the freerider:** a table containing the trained entrant
  holds the scripted freerider (Golf) to a worse outcome than the same table
  with the base model.

**$0 API.** Every MODEL seat is an `LLMDiplomat` wired to an explicitly
constructed local `OllamaClient` (`/api/chat` @ `localhost:11434`); the
anthropic / claude-cli backends are unreachable from the runner. Anchors + Golf
are scripted heuristics. No API-backed seat exists anywhere in this campaign.

## Design — ONE seed-paired campaign, both questions

**Table = 4 seats:** `[MODEL, Golf-freerider, anchorA, anchorB]`.

| Role | Agent | Notes |
|---|---|---|
| MODEL | `LLMDiplomat` ∈ {`foedus-entrant-v1:latest`, `foedus-base-v1:latest`} | the variable under test; both q4_K_M, same base weights, only LoRA differs |
| Golf (freerider) | `DishonestCooperator` heuristic | neutral arena handle "Golf"; declares ally + publishes its Moves so genuine cooperators support its attacks, but never reciprocates (pure GreedyHold orders) |
| anchorA | `Cooperator` heuristic | genuine always-ally cross-supporter — the exploitable "victim surface" Golf is designed to feed on; its presence makes containment meaningful |
| anchorB | `TitForTat` heuristic | reciprocity-conditional — punishes defection; a natural coordination partner for the MODEL and a check on Golf |

All three heuristics are **deterministic** given `(seed, player, node)` (their
only tie-break randomness, `shuffled_neighbors`, is seed-keyed — verified in
`foedus/agents/heuristics/_tiebreak.py`). The engine's only RNG
(`foedus/resolve.py`) is likewise seed-derived. So a seed fixes the entire game
**except** the MODEL seat's LLM output.

**Board:** Ruleset-v1 (`docs/design/2026-07-04-ruleset-v1.md`) — 4 players,
`max_turns=12`, `archetype=continental_sweep`, `map_radius=2`,
`detente_threshold=8`.

**Seed-pairing (load-bearing).** For each of **N = 20 sealed seeds** the game is
run **twice**: `MODEL=trained`, then `MODEL=base`, under byte-identical starting
conditions. Before game 0 the initial board of every seed is fingerprinted (a
canonical SHA-256 over map graph + units + config, `foedus.eval.phaseb.
board_fingerprint`) and sealed into `run/phaseb_plan.json`. Every arm re-derives
its board and **asserts** the fingerprint equals the sealed one; a post-run
pass re-asserts both arms of every pair share one fingerprint + one seat layout.
A mismatch aborts the run loudly rather than contaminating the claim. Each game
uses a FRESH `LLMDiplomat` (no cross-game memory, no reciprocation ledger) — the
unit of analysis is a single (seed, arm) game; nothing leaks between pairs.

**Seat rotation.** `model_seat = seed_index % 4`, so over N=20 seeds the MODEL
seat occupies each of the 4 positions exactly 5 times (5 full cyclic rotations —
perfectly seat-balanced). The remaining 3 seats are filled, in ascending seat
index, by `[Golf, Cooperator, TitForTat]` (so Golf always takes the lowest-index
non-MODEL seat). Golf's absolute seat therefore co-varies with the rotation, but
**every B2 comparison is paired within a seed** — Golf sits in the SAME seat in
both arms of a pair — so the paired delta is unaffected; only cross-seed
absolute levels absorb the seat variation. (Caveat recorded below.)

**Scale + wall-clock.** 40 games total. Timing probe (one throwaway pair, full
12 turns, real ollama): ~0.3 min/game engine-compute. Budget generously for
slow boards / ollama contention: expected total **~10–30 min**; **operational
cap = 3 h** — if the run exceeds it, something is wrong (investigate, do not
blindly continue). Each MODEL seat makes ~2 LLM calls/turn (≤24 calls/game).

## Metrics (all denominated "N of M"; coverage-guarded)

Read from `run/sweep.jsonl` (one banked row per (seed, arm), each carrying
`final_scores`, `winners`, `eliminated`, `detente_reached`, `model_seat`,
`golf_seat`, `role_by_seat`, `n_decisions`, `parse_fail_count`,
`board_fingerprint`). The analysis (`scripts/foedus_phaseb_analysis.py`, also in
this commit) asserts it parsed all 2·N banked rows before reporting (via
`foedus.eval._coverage.assert_coverage`) and prints every denominator.

Placement = standard competition rank (1 = best; ties share; eliminated share
the worst rank), computed by `foedus.eval.phaseb.competition_ranks` — a
standalone reimplementation cross-checked in tests against the engine's own
`foedus.scoring._compute_ranks`.

## Pre-registered verdict rules

Both questions use a **two-sided exact binomial sign test** over the N paired
per-seed deltas (ties dropped; the test's effective n is the count of non-zero
pairs), α = 0.05. Convention: a **positive** delta = "trained arm is better on
that seed".

### B1 — beats-own-base (MODEL seat, trained vs base)

- **PRIMARY:** paired MODEL **placement** delta = `rank(base) − rank(trained)`
  per seed (positive ⇒ trained placed better). Sign test.
- **Corroborating (must not contradict a positive verdict):** paired MODEL
  **final-score** delta = `score(trained) − score(base)` (sign test); MODEL
  **win/tie rate** (MODEL ∈ `winners()`), trained vs base.
- **Descriptive secondary:** OpenSkill μ−3σ over the 40 games treating
  trained-MODEL and base-MODEL as two identities (anchors + Golf shared). Not
  paired ⇒ corroborating only, never the verdict.

**Verdict (applied exactly as written):**
- **B1 = REAL (distillation beats base)** iff the PRIMARY sign test p < 0.05
  with trained favored (more positive than negative pairs).
- **B1 = SUGGESTIVE** iff 0.05 ≤ p < 0.20 with trained favored in the majority
  of non-zero pairs (reported as *not significant, leans positive*).
- **B1 = NULL** iff neither direction is significant and pairs are ~balanced.
- **B1 = BASE-BETTER** iff the sign test is significant in the base direction.

### B2 — containment (Golf, trained-field vs base-field)

- **PRIMARY:** paired **Golf final-score** delta = `score_golf(base_field) −
  score_golf(trained_field)` per seed (positive ⇒ the trained field held Golf to
  a LOWER score = better containment). Sign test.
- **Corroborating:** Golf **placement** (paired; better containment ⇒ higher
  rank number for Golf in the trained field), Golf **win/tie rate**, Golf
  **elimination rate**, trained-field vs base-field.
- **Attribution signal (reported, not a gate):** anchor (Cooperator + TitForTat)
  mean score trained-field vs base-field. If anchors do *better* in the trained
  field, containment leans toward *coordination / protection*; if only the MODEL
  gains while anchors are flat, it leans toward the MODEL merely being a stronger
  *rival* denying Golf supplies.

**Verdict:** identical 4-way structure as B1 (REAL / SUGGESTIVE / NULL /
BASE-CONTAINS-BETTER) on the PRIMARY Golf-score sign test.

## Honest caveats (load-bearing — recorded now, repeated in results)

1. **Small n, one archetype.** N=20 paired seeds on a single Ruleset-v1 board
   family (continental_sweep, radius 2, 4 seats, 12 turns). No claim beyond this
   board distribution.
2. **One scripted archetype of freerider** (`DishonestCooperator`). Containment
   of ONE exploiter type; not "contains freeriders" in general.
3. **Local q4_K_M quant, single training config.** LoRA r16/α32, 3 epochs, all
   LLM seats (not winners-only), no LR sweep, no assistant-masking (deliberately
   deferred G1 levers). A null here says *retrain differently*, not *distillation
   can't work*.
4. **The memorization framing IS the test.** Fresh sealed seeds never appear in
   the corpus; a trained win here is evidence *against* pure memorization, a
   trained loss is evidence the corpus over-fit.
5. **Mechanical-fitness confound for B1.** Phase A measured trained parse-fail
   ~4.2% vs a higher base rate (the timing probe showed base 33% on one board).
   Parse-fails degrade to safe Holds, so part of any B1 advantage may be the
   trained model simply emitting valid JSON more often (coherent play), not
   superior *strategy*. We report per-arm MODEL parse-fail so a reviewer can
   weigh how much of B1 is mechanical vs strategic. This is a real product of
   distillation, but it is an honest attribution boundary, not a disqualifier.
6. **B2 attribution (rival-vs-coordination).** As above — a stronger rival denies
   Golf supplies without any coordinated containment. The anchor-score signal
   partially disentangles it but cannot fully settle it at this n / one board
   family (same caveat family as the Sonnet arm).
7. **LLM stochasticity.** `OllamaClient` uses ollama defaults (no fixed
   temperature/seed), so a given (seed, arm) game is not bit-reproducible in the
   MODEL seat. The PAIRING controls the board + opponents; model stochasticity is
   noise averaged over the N pairs by the sign test. Boards ARE reproducible
   (fingerprinted); MODEL text is not.

## Ops

- Detached launch (`setsid`, log + PID), guarded `@reboot` autoresume (removed
  after completion), crash-resume banked-only (`--resume`). New out dir
  `docs/research/2026-07-10-gym-g1/phase-b/run/` (all prior sealed run dirs
  READ-ONLY). `.nexus-mcp.json` untouched.
- **Gate:** two independent reviewers on results honesty → no self-merge →
  Nova independent audit → merge is Nova/David's. Nova notified at (a) seal
  published + launch, and (b) completion + results ready.
