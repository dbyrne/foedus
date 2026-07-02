# Reciprocity model (Candidate 2) — validation sweep

**Source:** 4×10,000-game sweeps on the `feature/M-foedus-reciprocity-model-impl`
branch (this PR, with the post-code-review **unit-scoped harm attribution**),
all 21 heuristics (the 19-agent roster + the two new probes `Reciprocator` and
`MinimalReciprocator`), random 4-seat pairings, seed 0. Design doc:
`janus/docs/superpowers/specs/2026-07-02-foedus-reciprocity-model-design.md`.
Baseline for comparison: `docs/research/2026-07-02-post-0b-arena-fitness-sweep.md`
(the pre-redesign F6 numbers).

**Headline (honest):** harm-typing is a **clean win** — it shrank the penalty
that used to fine honest cooperators ~10× harder than the betrayer down to
**<0.4% of score** (Cooperator −4.84 → −0.155, a **31× reduction**), keeps
`Sycophant` crushed, and keeps `GreedyHold` dethroned. But the
**reciprocation-gated alliance bonus does NOT dethrone the free-rider**:
`DishonestCooperator` stays top-tier and the gate-gaming probe
`MinimalReciprocator` is #1 (Arm A) / #2 (Arm C). Two of five falsifiable checks
pass, one is a negligible near-miss, two fail on the free-rider residual. The
free-rider's edge is quiet `GreedyHold` expansion + costless `ALLY` declarations,
**not** the alliance bonus, so gating the bonus can't reach it — the design's own
§3 out-of-scope caveat, now confirmed. Closing it is the separate design pass
**`M-foedus-freerider-close-design`** (preliminary levers below).

## Methodology

Four arms, 10,000 games each, seed 0 (shared RNG ⇒ A/B are a paired before/after
on the penalty). `continental_sweep`, `max_turns=15`, 4 players. Penalty
defaults `intent_breach_penalty=1.0`, `pact_breach_penalty=1.0` (both now 1.0).

| Arm | Config | Purpose |
|---|---|---|
| **A** | `map_radius=2`, penalties **on** | Primary measurement |
| **B** | Same as A, penalties **off** (`--intent-breach-penalty 0 --pact-breach-penalty 0`) | Isolates the penalty (paired with A) |
| **C** | Same as A but `map_radius=3` | Default-radius comparison |
| **D** | Same as A but `--peace-threshold 0` (engine default détente) | Détente-rate measurement |

Reproducing:
```sh
PYTHONPATH=. python scripts/foedus_sim_sweep.py --num-games 10000 --max-turns 15 \
  --archetype continental_sweep --map-radius 2 --num-players 4 --workers 10 --seed 0 \
  --out A.jsonl
# Arm B: add --intent-breach-penalty 0 --pact-breach-penalty 0
# Arm C: --map-radius 3 ;  Arm D: --peace-threshold 0
PYTHONPATH=. python scripts/foedus_compute_ratings.py A.jsonl
```

## Leaderboards (conservative rating, `mu − 3σ`)

| Rank | Arm A (r2) | mu−3σ | Arm C (r3) | mu−3σ |
|---|---|---|---|---|
| 1 | **MinimalReciprocator** | 31.25 | **DishonestCooperator** | 36.80 |
| 2 | TitForTat | 29.85 | **MinimalReciprocator** | 35.40 |
| 3 | **DishonestCooperator** | 29.79 | Reciprocator | 34.44 |
| 4 | ValueGreedy | 29.73 | ValueGreedy | 34.20 |
| 5 | GreedyHold | 29.07 | GreedyHold | 33.86 |
| 6 | Reciprocator | 28.94 | Cooperator | 33.28 |
| 7 | Cooperator | 27.81 | Patron | 33.03 |
| 15 / 19 | **Sycophant** | (mid-low) | **Sycophant** | (near last) |

Baseline (pre-redesign) had `DishonestCooperator` #1 in both arms (34.96 / 40.13).

## The five falsifiable checks

| # | Check | Result | Numbers |
|---|---|---|---|
| 1 | `DishonestCooperator` falls to **≥ rank 4** in both arms | **FAIL** | #3 in Arm A, **#1 in Arm C** |
| 2 | `\|Δ_Cooperator\|` < `\|Δ_OpportunisticBetrayer\|` (penalty on−off) | **FAIL (negligible near-miss)** | Coop 0.155 > Betrayer 0.032 — ordering NOT reversed, but every penalty is now <0.4% of score (31× smaller than baseline 4.84) |
| 3 | `GreedyHold` stays dethroned (rank ≥ 4) | **PASS** | #5 in both arms |
| 4 | No new heuristic opens a > 2 mu−3σ dominant gap; `MinimalReciprocator` below genuine cooperators | **FAIL (mixed)** | No dominant gap (top-gap 1.40 both arms, < 2) ✓, but `MinimalReciprocator` is **#1 / #2**, *above* `Reciprocator`/`Cooperator` ✗ |
| 5 | `Sycophant` stays crushed | **PASS** | #15 / #19 (near last) |

**Prediction #2 detail — Δ = score(penalties off) − score(penalties on), 10k paired:**

| Heuristic | ON (A) | OFF (B) | Δ (this PR) | Δ (old F6) |
|---|---|---|---|---|
| Cooperator | 44.829 | 44.984 | **0.155** | 4.84 |
| TrustfulCooperator | 44.734 | 44.877 | 0.143 | 6.78 |
| Reciprocator | 45.102 | 45.235 | 0.133 | — |
| OpportunisticBetrayer | 33.201 | 33.233 | **0.032** | 3.33 |
| Sycophant | 28.553 | 28.719 | 0.167 | 22.51 |
| DishonestCooperator | 47.596 | 47.596 | 0.000 | 0.000 |
| MinimalReciprocator | 48.339 | 48.413 | 0.074 | — |

The strict ordering (`Coop > Betrayer`) is **not** reversed — but every penalty
is now negligible. Harm-typing did exactly its job: it stopped fining
cooperators for *helping* (−4.84 → −0.155, a 31× cut).

### Why #2 doesn't strictly reverse (an honest, non-obvious result)

Two confounds, both real:

1. **`OpportunisticBetrayer` is an *ineffective* betrayer.** Its solo stabs are
   strength-1 Moves into a defended supply (Hold strength 1) → they **bounce**.
   With the aid/leverage strength boost deleted, it can no longer force a
   dislodge alone, so it only harms when a third party happens to cross-support
   it. Its Δ (0.032) is near zero because it rarely *succeeds* at betraying, not
   because it's less malicious. It's a poor baseline for "the betrayer."
2. **The heuristic cooperators are (mildly) two-faced by construction.** They
   declare `ALLY` **to everyone**, then actively cross-support attacks. When such
   a support backs ally A's move that dislodges ally B (also a declared ally),
   *that specific supporting unit's* deviation is a real H1 breach — correctly.
   So cooperators, being *effective* supporters in an ALLY-to-all world, incur a
   tiny but genuine residual the betrayer's bounced stabs don't.

The unit-scoped harm fix (code review) matters here: before it, a *player-level*
harm check flagged **every** deviating unit a cooperator had on any turn it
harmed anyone, inflating Δ_Cooperator to 0.385. Scoping harm to the deviating
unit cut that to 0.155 — the residual is now only the units that *actually*
backed an ally-on-ally dislodge.

## Why the gate does NOT dethrone the free-rider (the core negative result)

The gate **fires** — 0.25 mover-bonus denials/game out of 0.88 bonuses/game
(~28%). It just doesn't matter, because **the alliance bonus is not where
`DishonestCooperator`'s edge comes from.** Tuning `reciprocation_floor` 0.5 → 1.0
and `FOEDUS_ALLIANCE_BONUS` 3 → 8 both leave `MinimalReciprocator`/
`DishonestCooperator` #1/#2. `DishonestCooperator` = `GreedyHold` expansion +
costless `ALLY`-to-all declarations; its advantage over plain `GreedyHold` (#5)
is small and comes from **diplomatic immunity** (stance-sensitive agents don't
attack a declared ally) plus occasional free combat-support — **not** the +3
bonus. `MinimalReciprocator` sits at the very top because one Support per window
occasionally clears the gate at almost no cost, while genuine cooperators spend
unit-actions supporting (a supported capture is worth +3 once; the supporter
unit could instead take a supply worth ~1–2/turn for the rest of the game).

This is the design's own §3 red-team caveat — *"never-ally quiet expansion...
C2 does not claim to fix it"* — now confirmed empirically, with the finding that
`DishonestCooperator` belongs to that same quiet-expansion class.

## Follow-up: closing the free-rider residual (separate design pass)

The residual is being addressed by a separate empirical design pass,
**`M-foedus-freerider-close-design`** (David reviews before any lever ships). It
prototypes levers that reach the *structural* edge the bonus gate can't:

- **Ally-upkeep** — cost blanket `ALLY`-to-all declarations (a per-turn charge
  for each ally, or only for each *unbacked* ally), pricing the diplomatic-
  immunity free-ride.
- **Strength-gate** — gate the combat-**support strength** (not just the +3
  score bonus) on reciprocation, denying free-riders the *borrowed strength*
  that wins their captures.

Preliminary sweeps of these look promising for the free-rider residual. They are
**deliberately kept out of this PR** — this PR is the harm-typing + reciprocation
infrastructure only, so the free-rider lever is decided under its own review gate.

## What harm-typing *did* achieve (the real wins)

1. **The inverted penalty is essentially gone.** Cooperator penalty 4.84 →
   0.155 (<0.4% of score); the machinery no longer fines helping.
2. **`Sycophant` stays crushed** (#15 / #19) via H1 — its declare-Hold-then-
   capture-an-ally's-supply pattern still registers.
3. **`GreedyHold` stays dethroned** (#5 both arms).
4. **A public reciprocation ledger** (`freeride_debt`, standing) now exists for
   the LLM phase to shun free-riders socially — the half of the design the
   heuristic sweep structurally can't test (no heuristic reads it offensively).

## Side effects worth flagging

- **Détente rate rose to 10.34%** (Arm D) from the baseline's 1.0%. Harm-typing
  the détente-streak reset means a peaceful mutual-`ALLY` table that only grabs
  *neutral* land (no harm to any ally) now correctly reaches the collective
  victory instead of being reset by harmless declared-order deviations. Whether
  ~1-in-10 is desirable is a design call.
- **Combat fell:** games with ≥1 dislodgement 25.9% (Arm A) vs baseline 38.7%.
  Deleting the aid/leverage economy removed the +1/+2 combat-strength boosts, so
  fewer attacks reach dislodge threshold (this is also why `OpportunisticBetrayer`
  is now an ineffective betrayer). The alliance bonus fires only 0.88×/game.

## Limitations

All 21 heuristics are fixed-logic and non-adaptive: none sign pacts
(`reputation_pact_breaches` ≡ 0 across all arms), and none read
`reputation`/reciprocation **offensively** (only `TrustfulCooperator` reads the
ledger, and only *defensively* — to prioritise which ally to back). So the sweep
validates only the **mechanical** half (harm-typing changes scores; the gate
withholds bonus income); the **social** half — free-riders getting frozen out
because agents *shun* the public ledger — remains an LLM-phase test.
