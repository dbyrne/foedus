# G2 Phase A — constrained decoding built + validated (gate report)

**Roadmap item:** `G-foedus-g2-mechfit-control`. **Branch:** `feature/M-foedus-gym-g2`
(worktree off `origin/main` = `3c522ef`). **Status: G2a complete — STOPPED at the
gate. No PR, no merge, G2b not started.** Entirely local Ollama (0.31.1), $0 API.

## What was built

1. **`OllamaClient` `format` param** (`foedus/agents/llm/client.py`) — optional
   JSON-schema constrained decoding on `/api/chat`. Off by default: with no
   schema the request payload is byte-identical to before (no `format` key),
   so every existing caller is unaffected (unit-tested). Schema can be set
   per-instance or per-call (per-call wins) — the per-call form is what lets
   one client serve both phases' schemas.
2. **Per-phase decision schemas** (`foedus/agents/llm/schema.py`) —
   `negotiation_decision_schema()` (press.stance/intents + pacts.propose/accept)
   and `orders_decision_schema()` (orders map), derived from what `render.py`
   asks the model to emit and what `parse.py` accepts. Structure forced
   (skeleton keys, closed enums `ally|neutral|hostile` and `Hold|Move|Support`,
   the geometry field each order type requires); all strategic values free
   (which unit/dest/target/stance/counterparty, how many intents/pacts). Id
   fields admit int OR string because `parse.coerce_id` does — and the corpus
   really contains both (20 orders-phase targets are `"u<n>"` strings).
3. **Validation** — `tests/test_llm_schema.py` (corpus acceptance +
   structure-forced/values-free contract), `tests/test_llm_client.py`
   additions (format threading + no-change-for-existing-callers),
   `tests/smoke/test_llm_schema_ollama_smoke.py` (opt-in live check), and
   `scripts/foedus_g2_constraint_probe.py` (the denominated live probe below,
   full JSON in `constraint_probe.json`).

## Gate metrics (all denominated)

### 1. Schema acceptance over the G1 SFT corpus — **716 of 716**

Every real teacher decision validates: negotiate **411/411**, orders
**305/305**. The schema rejects no legal decision (coverage-guarded unit test,
runs in CI). During derivation the int-or-string id shape was the one trap: an
integer-only id schema would have silently rejected 20 legal orders decisions.

### 2. Base-repair — structural fallback, constrained vs unconstrained

*Part A, controlled replay: 40 identical corpus prompts per phase per model;
`decision_valid` = raw output yields a schema-valid full decision via the
parser's own extractor.*

| model | condition | negotiate | orders |
|---|---|---|---|
| foedus-base-v1 | unconstrained | 2/40 (5.0%) | 10/40 (25.0%) |
| foedus-base-v1 | **constrained** | **40/40 (100%)** | **40/40 (100%)** |
| foedus-entrant-v1 | unconstrained | 40/40 (100%) | 40/40 (100%) |
| foedus-entrant-v1 | constrained | 40/40 (100%) | 40/40 (100%) |

*Part B, real games (4 games × 8 turns per condition, 64 decisions each),
G1-comparable `fell_back` plus decomposition:*

| model / condition | parse-fallback (G1 metric) | struct-invalid | residual illegal (of schema-valid) | per-order illegal |
|---|---|---|---|---|
| base unconstrained | 31/64 (48.4%) | 58/64 (90.6%) | 2/6 | 31/37 (83.8%) |
| **base constrained** | 11/64 (17.2%) | **0/64 (0.0%)** | 11/64 (17.2%) | 3/35 (8.6%) |
| entrant unconstrained | 12/64 (18.8%) | 0/64 (0.0%) | 12/64 (18.8%) | 8/47 (17.0%) |
| **entrant constrained** | 12/64 (18.8%) | **0/64 (0.0%)** | 12/64 (18.8%) | 7/39 (17.9%) |

Sanity anchors: base-unconstrained parse-fallback 48.4% reproduces G1's
campaign 51.3% (234/456); the entrant's ~18.8% matches G1's 25.7% ballpark.
Note `struct_invalid` (90.6%) exceeds `parse_fb` (48.4%) unconstrained because
`parse.py`'s lenient recovery salvages many schema-invalid fragments without
flagging `fell_back` — the two lenses are reported side by side, never summed.

### 3. Residual semantic illegality — the confound decomposition

Under constraint, 100% of both models' decisions are structurally valid, so
ALL remaining fallback is semantic (schema-valid JSON, geometrically-illegal
move, coerced by the parser):

- **base constrained: 11/64 decisions (17.2%); 3/35 emitted orders (8.6%)**
- **entrant constrained: 12/64 decisions (18.8%); 7/39 emitted orders (17.9%)**

## Gate call: **JSON confound CLEANLY REMOVED — proceed-able to G2b**

1. **Structural fallback → 0** for both arms (base 90.6% → 0.0% on 64 real-game
   decisions; 80/80 controlled replays valid). The G1 mechanical channel —
   base turns collapsing to Hold because it cannot emit the format — is gone.
2. **The residual is small and, critically, COMPARABLE across arms** (17.2% vs
   18.8% per decision — near parity; per-order the base is actually *lower*,
   8.6% vs 17.9%). Neither arm gets a mechanical subsidy: whatever placement
   gap survives a constrained B1 is strategy (or its absence), not fluency.
3. The constraint does **not distort the trained arm**: entrant constrained ≈
   entrant unconstrained on every metric (18.8% = 18.8%), so G2b's trained arm
   plays the same game it played in G1.

Caveats for the G2b pre-reg: residual-illegality parity is from n=64 decisions
per cell (probe-sized, seeds 1000–1003, vs 3 GreedyHold) — G2b should re-report
it, denominated, over the sealed campaign; and the campaign self-note call (if
ever enabled) must stay UNCONSTRAINED (free text), which the phase-dispatch
wrapper already honors.

**Reproduce:** `python scripts/foedus_g2_constraint_probe.py --n-structural 40
--n-games 4 --max-turns 8 --out .../constraint_probe.json` (full JSON alongside
this report); unit tests: `pytest tests/test_llm_schema.py tests/test_llm_client.py`.
