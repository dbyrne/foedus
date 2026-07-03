# Reciprocation-memory experiment — does memory let a local LLM table resist the freerider?

**Status:** in progress (branch `feature/M-foedus-llm-memory-experiment`)
**Author:** coder dispatch (M-foedus-llm-memory-experiment)

## The result this tests

Gate-B probe (PR #35 harness): 3 LLM seats (qwen2.5:14b via Ollama) vs. one
`DishonestCooperator` freerider lost 4/4 games ~2×. Mechanism from transcripts:
the seats start suspicious (turn-1 two-of-three flag the freerider `hostile`),
then the freerider's costless, unwavering ALLY-to-everyone declaration wears
them down — by mid-game all three flip to `ally` and actively `Support` the
freerider's units. The agent has **no memory**: each turn it re-derives its read
from a board where the freerider looks loyal, and the turn-1 suspicion
evaporates.

## Hypothesis (falsifiable)

The failure is (at least partly) a **memory/architecture** gap, not purely model
weakness. A compact, factual, per-opponent **reciprocation record** carried in
the seat prompt — the persistence of who has declared ally toward it, and its own
cumulative cooperation cost — lets the table hold its suspicion and collapses the
freerider's dominance.

## What already exists (do not duplicate)

- The engine (C2 / PR #31) computes a **public reciprocation standing** —
  `given / received / standing / freeride_debt` over a rolling
  `reciprocation_window` (4 turns) — and `render.py` **already renders it** in the
  negotiation prompt. The freerider's `given` is 0, yet the table still allied.
- `render_common` already renders BETRAYAL / PACT-BREACH ledgers and the public
  REPUTATION tally.
- `public_stance_matrix` in the fog view carries **last round only** — the engine
  does not accumulate any per-turn declared-stance history.

So the reciprocation *standing* is already on the board. The gap this experiment
fills is **memory a single fogged view cannot contain**:
1. the **persistence** of an opponent's declared stance *toward this seat* across
   all turns (a single view shows only the last round), and
2. this seat's **own cumulative Support** given to each opponent (its own orders
   are not in any view at all).

## Fog-legality wall (why the ledger is agent-side memory, not new engine state)

- `SupportRound.gave` / `.received` are `frozenset[PlayerId]` — the engine records
  **no pairwise** "who supported whom" attribution anywhere.
- `visible_state_for` exposes **no executed-order / support data**; no heuristic
  declares Support *intents* (Cooperator/TrustfulCooperator declare only Move
  intents), so `your_inbound_intents` cannot separate a freerider from an honest
  ally either.

Therefore a **directed** "p3 supported *your* units 0 times" (executed) is **not
fog-legally observable** without an engine change, which is out of scope. The
ledger instead carries only quantities a seat can legitimately observe from its
**own fogged views over time**, accumulated agent-side (fog-safe by construction).

## Design

### 1. Reciprocation memory (`foedus/agents/llm/memory.py`)

`ReciprocationMemory` — per-`LLMDiplomat`-instance (one seat, one game; resets each
game — cross-game memory is out of scope). Accumulates, per opponent `p`, from the
seat's own fogged views + its own submitted orders:

- `ally_toward_me` / `turns_observed` — each turn, read `public_stance_matrix`
  (public → fog-legal) and record `p`'s declared stance toward this seat.
- `turns_i_supported_them` — each orders turn, if this seat issued ≥1 `Support`
  whose target unit is owned by `p`, record it (own action → fog-legal).
- `my_prior_stances[p]` — the stances THIS seat declared toward `p` on prior turns
  (own outbound press → fog-legal). Directly counters the "forgets its own turn-1
  read" mechanism.

Idempotent per turn (keyed by `state.turn`).

### 2. Render (`render.py`, gated toggle, default OFF)

`render_negotiation_prompt(..., recip_memory=None)`. When `recip_memory is None`
the prompt is **byte-identical** to today (back-compat). When provided, a
`RECIPROCATION RECORD` block is appended after the existing public standing block.

**Neutrality (experiment integrity — hard requirement):** factual counts only. One
neutral framing sentence naming what the section is. No advice, judgment, or
leading language — asserted by a denylist test (`exploit`, `beware`, `punish`,
`freerid`, `betray`, `should`, `consider`, `reward`, `trust`, `distrust`, ...).
The stance words `ally/neutral/hostile` are the game's own vocabulary, not
judgment.

Sample (freerider = p3). All three stance counts are surfaced symmetrically
(no single-lens emphasis):
```
RECIPROCATION RECORD (your own observations across prior turns; declared stances
you received and Support you have given — from your fogged views only):
  p1: declared toward you across 7 observed turns — ally 7, neutral 0, hostile 0; you gave Support to their units on 2 turns; your prior stances toward them: neutral, ...
  p3: declared toward you across 7 observed turns — ally 7, neutral 0, hostile 0; you gave Support to their units on 7 turns; your prior stances toward them: hostile, hostile, neutral, ally, ally, ...
```

**Ownership for the "you gave Support" count comes from the seat's own fogged
`visible_units`** (not omniscient state), so a legal Support of a unit outside
fog (2-hop move-support geometry) is never attributed to any owner — the seat
only credits support to units it could actually see.

### 3. Toggle

`FOEDUS_LLM_RECIP_LEDGER` (env: `1/true/yes/on`) and/or `LLMDiplomat(recip_ledger=...)`
constructor arg (arg overrides env). Both arms are the **same code, one toggle
apart**. Harness gains `--recip-ledger` which sets the env var (mirrors the
existing `--backend`/`--model` env pattern; keeps the no-arg factory).

### 4. Metrics extractor (`foedus/eval/memory_metrics.py` + `scripts/foedus_memory_metrics.py`)

From a run out-dir, per-game + aggregate scorecard, all from self-contained JSON:
- **margin / winner** — from `sweep.jsonl` (`final_scores`, `agents`, `llm_seats`);
  freerider seat(s) = seats whose agent name matches `--freerider`
  (default `DishonestCooperator`).
- **subsidy** — LLM `Support` orders whose target is a freerider unit: from
  `decisions_*.jsonl`, order target from `extract_json(raw)["orders"]`, target
  owner from the decision's own prompt `VISIBLE UNITS` section.
- **stance-toward-freerider trajectory** — per turn, how many LLM seats declare
  the freerider hostile/neutral/ally: from `decisions_*.jsonl` negotiate records,
  `extract_json(raw)["press"]["stance"]` (state-free).
- **parse-fail per seat** — from `telemetry.jsonl`.

Colorblind-safe output (David is red/green colorblind): labels/symbols, no
red-vs-green-only status.

## Falsifiable bar (honest verdict either way)

- **Primary:** in Arm B the freerider no longer wins the majority of games, OR its
  mean score margin over the LLM average shrinks ≥50% vs Arm A.
- **Mechanism:** subsidy drops AND sustained-hostile stance toward the freerider
  rises. A primary pass with unchanged mechanism metrics is flagged as suspicious.
- No prompt-iteration to force a pass — one neutral design, one paired run.

## Explicitly out

Cross-game memory (follow-up), any strong-model/API arm, engine/mechanic changes.
