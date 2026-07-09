# Parallel per-phase seat calls (~3× wall-clock cut for LLM matches)

**Status:** shipped · **Milestone:** M-foedus-parallel-seat-calls · **Default:** OFF
· **Base:** rebased onto Ruleset v1.1 `main` (composes with the identity/campaign
memory diplomat; equivalence re-proven with both active — see below)

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

**Engine-purity invariant (CLAUDE.md).** "Don't introduce async, threads, or
implicit timers into the engine" targets the pure state-transition functions
(`press.py`, `resolve.py`, `fog.py`, `core.py`) — all of which this change
leaves byte-for-byte untouched. The `ThreadPoolExecutor` lives only in the
**driver** (`foedus/loop.py`'s `play_game`), wraps only *agent-side* compute
(the seat's own LLM call), is **off by default**, and never touches engine RNG
or state folding — consistent with the invariant's intent that the engine itself
remain a deterministic, single-threaded pure function of its inputs.

### Per-call isolation for concurrent `claude -p` (`ClaudeCLIClient`)

Overlapping seats each shell out to `claude -p`. Two concurrent invocations must
not collide on any shared per-process resource, so every `complete()` call is
made self-contained:

- **Unique cwd per call.** Each call runs in a freshly-created temp dir (a unique
  subdir of the neutral base, removed after the call), never a shared `/tmp`.
  The CLI keys its project state on cwd (`~/.claude/projects/<slug>/`); a shared
  cwd would let two concurrent calls race that directory. (This also *strengthens*
  the pre-existing "never the repo" neutrality guarantee — the dir is empty and
  unique.)
- **Unique session id per call** (the "client id"). Each call passes a fresh
  `--session-id <uuid4>`, so no two concurrent invocations share a session
  identity even though `--no-session-persistence` is also set.
- **Per-call subscription-auth strip.** `_subprocess_env()` (which strips
  `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / Bedrock+Vertex routing so the
  credit-less API key never shadows the claude.ai OAuth) is recomputed **per
  call** — nothing is memoized on the shared client — so subscription auth holds
  on every concurrent path.

None of this perturbs a seat's *answer*: with `--safe-mode` (no CLAUDE.md
discovery) the response depends only on the system+user prompt and model, not on
cwd or session id. So per-call isolation is invisible to the equivalence proof
(which runs against a deterministic stub) and simply makes real concurrency safe.

## Correctness guarantees

- **Observational equivalence** — proven by tests asserting identical
  sweep/telemetry **and** per-seat decision logs (including the rendered
  *prompt* text, so a fog-leak-induced prompt divergence would fail), for an
  all-Hold game, a movement game, and a real-heuristic-roster game.
- **Equivalence with the Ruleset v1.1 diplomat (identity + campaign active)** —
  `test_parallel_matches_sequential_with_identity_and_campaign_active` re-proves
  byte-identical outcomes + decision logs against the *real* v1.1 diplomat:
  `set_identity_context` set, a campaign record loaded (so PRIOR GAMES renders),
  and the reciprocation ledger ON. Because `prewarm_phase` now warms the v1.1
  `_negotiate`/`choose_orders` (which read `self._identity` and *mutate*
  `self._memory`), the test also compares each seat's accumulated reciprocation
  state directly, and — since the ledger renders into each later turn's prompt —
  any divergence in that accumulation surfaces in the decision-log diff too. The
  key invariant that makes this hold: `self._identity` and `self._campaign_memory`
  are read-only during a turn (set once per game before the turns), and
  `self._memory` is per-*instance* (per-seat), touched only by that seat's own
  thread — so cross-seat concurrency never races it.
- **RNG-order invariant (protects the sealed seed).** Reproducibility depends on
  the engine consuming its seeded RNG in a fixed order; parallelism must not
  perturb that order. It cannot, because **there is no RNG on the seat-call
  path**. Seats are pure functions of a read-only snapshot — the prewarm pool
  only decides *when* each (slow) seat call runs, never *whether* or in what
  order the engine draws randomness. The engine's RNG is consumed solely inside
  `finalize_round`, which runs **once per turn, single-threaded, after every
  seat's orders are already gathered** into the orders dict — a point the pool
  has fully joined before. Non-opt-in agents (heuristics, which *may* draw RNG)
  are never pre-warmed, so their invocation order is byte-identical to the
  sequential default. Hence same seed ⇒ same engine randomness ⇒ same result,
  under `WORKERS=1` or `WORKERS=2+`.
- **Shared-state isolation** — all `GameState` accessors are read-only,
  `Map`/`Press`/`Intent` are frozen, and there is no lazy memoization
  (`cached_property`/`lru_cache`/`object.__setattr__`) on the path, so
  concurrent snapshot reads are race-free. Each seat writes only its own
  disjoint cache / decision log / reciprocation memory (one `LLMDiplomat`
  instance per seat — `_prewarm_seats` raises if the same instance **or the same
  underlying `_client` object** is registered for multiple seats, rather than
  silently racing its client buffers / cache / log; because a shared client is
  rejected, a single client is never called concurrently, so its `_argv_logged`
  one-shot flag is never raced either). The
  `claude -p` subprocesses are isolated per call (unique cwd + session id + a
  per-call auth-stripped env — see *Per-call isolation* above). Per-seat
  decision-log *files* are written by the harness single-threaded, after the
  game. Proven by `test_concurrent_calls_are_fully_isolated` (N genuinely
  overlapping calls each get a distinct cwd + session id + stripped env) and the
  `play_game`-level barrier test.

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

## Wall-clock + contention measurement

### Hermetic (deterministic, in the test suite)

`test_parallel_seats_cuts_wall_clock_with_identical_outcomes` runs a full game
each way with a deterministic latency-simulating client (fixed scripted
responses + a per-call sleep standing in for `claude -p`). Outcomes are
**byte-identical** between sequential and parallel (same responses); only
wall-clock differs. A 3-seat, 3-turn, 0.20 s/call run measured
**sequential 3.61 s → parallel 1.22 s = 2.97× speedup** — i.e. the ideal ~3×
for 3 concurrent seats, with zero outcome change. (The committed test asserts a
very loose >1.4× so it proves overlap without flaking under CI load.)

### Real `claude -p` (full game each way)

One full real game each way, same seed (0), 3 LLM seats (sonnet), 2 turns
(12 `claude -p` calls/arm), subscription auth:

| Arm | Wall-clock | Decisions | parse-fail | CLI timeouts/errors | Final scores |
|-----|-----------:|----------:|-----------:|--------------------:|--------------|
| Sequential (`WORKERS=1`) | 232.1 s | 12 | 0 | 0 | {0:4, 1:3, 2:2} |
| Parallel (`WORKERS=3`)   |  91.5 s | 12 | 0 | 0 | {0:4, 1:3, 2:2} |

**2.54× wall-clock cut; contention/timeout delta = 0** (parse-fail 0→0, CLI
timeouts/errors 0→0 at full 3-way concurrency). The final outcome happened to
match exactly here, but that is *not* the determinism guarantee (see the note
below). The 2.54× is a little under the hermetic ~3× because real 3-way
concurrency adds mild per-call latency (shared subscription throughput) — but it
adds **zero** parse-fail / timeout regression, so no need to throttle to
`WORKERS=2` for this table size. Per-call temp dirs: 0 leaked after the run
(cleanup held under real concurrency).

Prior tiny smoke (historical, 3 short calls/arm during a live campaign):
sequential 9.6 s → concurrent 2.6 s = **3.62× speedup, +0 parse-fail delta, no
per-call latency increase** at 3-way concurrency.

**Note on "identical outcomes" for the real arm.** Live `claude -p` sampling is
non-deterministic, so two independent real games are *not* expected to be
byte-identical — the byte-identical determinism guarantee is proven hermetically
above (deterministic backend). The real arm measures the two things a stub
cannot: actual wall-clock and *transport-level contention* (does 3-way
concurrency raise the parse-fail / CLI-timeout rate?). If a real run shows
contention, drop `FOEDUS_PARALLEL_SEATS_WORKERS` to 2 (proven to bound
concurrency by `test_max_workers_bounds_concurrency`).
