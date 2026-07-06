# Parallel per-phase seat calls (~3× wall-clock cut for LLM matches)

**Status:** shipped · **Milestone:** M-foedus-parallel-seat-calls · **Default:** OFF

## Motivation

An LLM game's wall-clock is dominated by the per-seat `claude -p` calls: each
`LLMDiplomat` seat makes **2 LLM calls per turn** — a *negotiate* call (press
phase) and an *orders* call (orders phase) — each ~90–120s. With 3 LLM seats
that is ~6 sequential calls/turn. Run each phase's seat calls concurrently and
those ~6 calls collapse to ~2 concurrent rounds → **~3× wall-clock cut** with
**no change to game logic, RNG consumption, or resolution** — only *when* the
calls happen.

## The key observation (why it is safe)

Within a phase, every seat answers from the **same prior-turn public snapshot**
(Diplomacy's simultaneous secret orders), so the per-seat calls are
informationally independent:

- **Negotiate.** `visible_state_for` (`foedus/fog.py`) derives every
  press-facing field (`public_stance_matrix`, `your_inbound_intents`,
  `your_outbound_press`) from `state.press_history[-1]` — the *last completed*
  round — and exposes only the seat's **own** in-progress press
  (`your_pending_press = round_press_pending.get(player)`). It never reads
  another seat's same-turn `round_press_pending`. In `play_game`'s press pass
  `submit_press_tokens` mutates `state` between seats, but that mutation only
  adds *other* seats' pending press — which the fogged view of seat N ignores.
  `render_negotiation_prompt` reads only `view` + invariant `state` fields
  (`units`, `turn`, `map`), none of which `submit_press_tokens` touches. So a
  seat's negotiate decision is identical whether computed from the pre-phase
  snapshot or inline in the sequential pass.
- **Orders.** The orders pass collects results into a dict and does **not**
  mutate `state` between seats (`finalize_round` runs once, after). Every seat
  reads the same state → trivially independent.

Therefore pre-computing all seats' decisions concurrently from one snapshot,
then folding them into `state` in the **unchanged sequential order**, is
observationally identical to computing them inline.

## Design

The join point is `LLMDiplomat`'s existing per-`(turn, player)` negotiate/orders
caches — the natural place to warm a decision off-thread.

- **`LLMDiplomat`** advertises `supports_parallel_prewarm = True` and exposes an
  idempotent `prewarm_phase(state, player, phase)` that runs exactly the cached
  compute (`_negotiate` / `choose_orders`). Because the compute is cached per
  `(turn, player)`, the sequential pass that follows returns the warmed value
  with **no second LLM call, no duplicate decision-log entry, and no repeated
  reciprocation-memory observation** (`observe_view`/`observe_orders` run only
  on cache miss). The negotiate cache also backs `choose_pacts`/`accept_pacts`.
- **`play_game`** (`foedus/loop.py`) gains `parallel_seats` (default `False` →
  byte-identical) and `max_workers`. When on, `_prewarm_seats` runs
  `prewarm_phase` concurrently (a bounded `ThreadPoolExecutor` over the blocking
  subprocess calls) for every opt-in, non-eliminated seat — from the
  top-of-turn snapshot before the press pass, and from the post-negotiation
  state before the orders pass. `max_workers` defaults to the number of opt-in
  seats. Agents without the marker (heuristics) are **never** pre-warmed, so
  their invocation order — and any RNG they draw — is byte-identical to today.
  0/1 opt-in seat takes an inline branch (no pool).

The engine (`press.py`, `resolve.py`) stays single-threaded: concurrency only
changes when each seat's decision is computed, never the order in which
`submit_press_tokens` / `finalize_round` fold results into `state`.

## Correctness guarantees

- **Observational equivalence** — proven by tests asserting identical
  sweep/telemetry **and** per-seat decision logs (including the rendered
  *prompt* text, so a fog-leak-induced prompt divergence would fail), for both
  an all-Hold game and a movement game.
- **Seed / RNG safety (protects the sealed seed)** — there is no RNG on the
  seat-call path; the engine RNG is consumed only at `finalize_round`,
  single-threaded, after all orders are gathered. Non-opt-in agents are never
  pre-warmed, so RNG draw order is unchanged.
- **Shared-state isolation** — all 13 `GameState` methods are read-only,
  `Map`/`Press`/`Intent` are frozen, and there is no lazy memoization
  (`cached_property`/`lru_cache`/`object.__setattr__`) on the path, so
  concurrent snapshot reads are race-free. Each seat writes only its own
  disjoint cache / decision log / reciprocation memory (one `LLMDiplomat`
  instance per seat is the default). Per-seat decision-log *files* are written
  by the harness single-threaded, after the game.

## Hot-swap integration point (for the live canonical campaign)

`run_one_llm_game` resolves the flag as **explicit-kwarg > `FOEDUS_PARALLEL_SEATS`
env > default-off**, and the worker bound from `FOEDUS_PARALLEL_SEATS_WORKERS`.
The sibling canonical-campaign script calls `run_one_llm_game(...)` **without**
the new kwarg, so it inherits the behavior purely from the environment:

```
# at a game boundary of the live run:
export FOEDUS_PARALLEL_SEATS=1
# optional, if 3-way subscription contention worsens parse-fail/timeout:
export FOEDUS_PARALLEL_SEATS_WORKERS=2
# resume -> remaining games run ~3x faster; seeds still drive the engine,
# so the sealed-seed determinism is preserved.
```

No campaign-script code change is required. CLI equivalents:
`--parallel-seats` / `--parallel-seats-workers N`.

## Contention measurement (tiny real smoke)

A 3-call-per-arm `claude -p` smoke (short prompt, sonnet), run while the live
campaign was mid-game: sequential 9.6s wall (3/3 parse-ok, 0 errors);
concurrent 2.6s wall (3/3 parse-ok, 0 errors) → **3.62× speedup, +0 parse-fail
delta, no per-call latency increase** at 3-way concurrency. This measures
transport-level contention (the concurrency-specific risk) and was clean; a
larger batch outside the live window would be needed for a statistically
confident *parse-quality* delta on full-length prompts. If a larger run shows
contention, drop `FOEDUS_PARALLEL_SEATS_WORKERS` to 2.
