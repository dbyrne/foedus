# Reciprocation-memory experiment — results

**Date:** 2026-07-03 · **Model:** `qwen2.5:14b-instruct-q4_K_M` (Ollama, local, free)
**Harness:** `scripts/foedus_llm_diplomat_run.py` · **Scorecard:** `scripts/foedus_memory_metrics.py`
**Design/rationale:** `docs/superpowers/specs/2026-07-03-llm-reciprocation-memory-experiment.md`

## Question

Does giving a local-LLM seat a compact, neutral, fog-legal **memory** of who has
declared alliance toward it (and its own cooperation history) let an LLM table
resist a scripted freerider (`DishonestCooperator` — declares ALLY to everyone
every turn, never reciprocates support)? The Gate-B probe found the base agent,
with no memory, re-derives its read each turn and its turn-1 suspicion of the
freerider evaporates.

## Design (paired, same seeds)

Two arms, identical except one toggle:

| | Arm A (baseline) | Arm B (memory) |
|---|---|---|
| ledger | OFF | ON (`--recip-ledger`) |
| games × turns | 6 × 8 | 6 × 8 |
| seats | LLM 0,1,2 + DishonestCooperator (seat 3) | same |
| map-radius | 1 | 1 |
| seeds | 0–5 | 0–5 (same) |

Same seed stream ⇒ identical maps and freerider behaviour across arms; the only
difference is whether each LLM seat's negotiation prompt carried the neutral
`RECIPROCATION RECORD` block. One neutral ledger design, one paired run, no
prompt-iteration. Both arms play ~90% legally (parse-fail 18.4% / 16.9%; Gate-A
holds — the play signal is real, not the httpx-trap artifact).

## Falsifiable bar

- **Primary:** in Arm B the freerider no longer wins the majority of games, OR
  its mean score margin over the LLM average shrinks by ≥50% vs Arm A.
- **Mechanism (must move for a credible positive):** subsidy (LLM Support orders
  targeting a freerider unit) drops, AND sustained-hostile stance toward the
  freerider rises.

## Results

### Aggregate

| metric | Arm A (baseline) | Arm B (memory) | change |
|---|---|---|---|
| freerider win-rate | **3 / 6** (50%) | **3 / 6** (50%) | none |
| mean margin (freerider − LLM mean) | **+7.89** | **+5.39** | **−31.7%** (bar: ≥50%) |
| total subsidy (LLM supports of freerider units) | **41** | **41** | **0%** |
| mean subsidy / game | 6.83 | 6.83 | none |
| ally-toward-freerider declarations (all game·turn·seat) | 87 | 93 | +6 (worse) |
| hostile-toward-freerider declarations | 6 | 8 | +2 (all turns 0–1) |
| parse-fail | 18.4% | 16.9% | — |

### Per game (freerider score vs LLM-mean; margin)

| game (seed) | Arm A | Arm B |
|---|---|---|
| 0 (s0) | 8.0 vs 10.7 (−2.7) · LLM held | 8.0 vs 9.7 (−1.7) · LLM held |
| 1 (s1) | 26.0 vs 13.3 (+12.7) · **freerider WON** | 26.0 vs 12.3 (+13.7) · **freerider WON** |
| 2 (s2) | 28.0 vs 10.7 (+17.3) · **freerider WON** | 30.0 vs 10.7 (+19.3) · **freerider WON** |
| 3 (s3) | 13.0 vs 13.3 (−0.3) · LLM held | 13.0 vs 18.3 (−5.3) · LLM held |
| 4 (s4) | 15.0 vs 9.3 (+5.7) · LLM held (top tie) | 8.0 vs 10.3 (−2.3) · LLM held |
| 5 (s5) | 22.0 vs 7.3 (+14.7) · **freerider WON** | 20.0 vs 11.3 (+8.7) · **freerider WON** |

### Stance-toward-freerider trajectory (does suspicion hold?)

In **both** arms the LLM seats collapse to ALLY toward the freerider by turn ~2
and stay there. Hostility appears only at turns 0–1 (6 declarations in A, 8 in B)
and never returns; there is no *sustained* hostility in either arm. Example
(Arm B, game 1): `t0[H2 N1 A0] → t1[H1 N0 A2] → t2[H0 N1 A2] → t3..t7 mostly A3`.

### The memory was present, salient, and ignored

A real ON-arm ledger, seat 0, turn 7 of game 2 (a game the freerider **won 30**):

```
RECIPROCATION RECORD (your own observations across prior turns; declared stances you received and Support you have given — from your fogged views only):
  p1: declared toward you across 7 observed turns — ally 0, neutral 7, hostile 0; you gave Support to their units on 0 turns; your prior stances toward them: neutral, neutral, neutral, neutral, ally, neutral, neutral.
  p2: declared toward you across 7 observed turns — ally 0, neutral 5, hostile 2; you gave Support to their units on 0 turns; your prior stances toward them: neutral, hostile, hostile, hostile, hostile, hostile, hostile.
  p3: declared toward you across 7 observed turns — ally 7, neutral 0, hostile 0; you gave Support to their units on 1 turns; your prior stances toward them: neutral, ally, ally, ally, ally, ally, ally.
```

The freerider signature is right there — `p3` declared ALLY 7/7 turns and the
seat has reciprocated ally every turn since turn 1 — and the seat **still
declared `ally` toward the freerider that same turn**. The information was
available and factual; the model did not act on it.

## Verdict — NEGATIVE (bar not met), and internally consistent

- **Primary FAIL:** margin shrank 31.7% (< the 50% threshold); win-rate is
  identical (3/6 in both arms, and not a majority in either — note this config,
  `map-radius 1` over 6 games, already showed a weaker freerider than the
  earlier 4-game probe's 4/4, so the win-rate limb is a poor discriminator here;
  the margin limb is the cleaner signal and it did not clear the bar).
- **Mechanism FLAT:** the subsidy is *identical* (41 = 41 supports of freerider
  units), and ally-toward-freerider declarations are, if anything, slightly
  *higher* with the ledger (93 vs 87). Suspicion still evaporates by turn 2.

The margin's ~32% dip is **not mechanistically supported** (with subsidy exactly
unchanged there is no causal path for the memory to have reduced the freerider's
edge), so it is best read as score-variance across 6 games rather than a memory
effect. A primary fail together with flat mechanism metrics is the *consistent*
negative the design anticipated — not a suspicious pass.

## Interpretation (final call to David/Nova)

At `qwen2.5:14b`, a neutral reciprocation ledger did **not** let the table hold
its suspicion or resist the freerider. The hypothesised memory/architecture gap
is, at this model scale, **not** the (sole) lever: the information was made
present, salient, cumulative, and fog-legal — including the seat's own
alliance-declaration flip and its own sunk support — and the model still allied
with and subsidised the freerider. This isolates the failure as (at least
partly) **raw capability** at 14b rather than a pure memory gap, which is exactly
the outcome that **earns the strong-model (subscription-Claude) arm** described
in the roadmap: run the identical paired design with a stronger negotiator and
see whether the same ledger then changes behaviour.

## Explicitly out of scope (follow-ups)

- **Cross-game memory / learning across games** (David's noted interest) — the
  ledger here resets each game by design.
- **Any strong-model / API arm** — this run is local-only, zero API spend. The
  negative result is what earns that next test.
