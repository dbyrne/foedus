# Cross-game memory — does a Sonnet table LEARN to coordinate across games? (2026-07-03)

Paired with `docs/plans/2026-07-03-crossgame-memory.md`. Follow-up to the strong-model coordination
probe (`docs/research/2026-07-03-strong-model-coordination-probe.md`, PR #37).

## The question (the earned rung)
PR #37 proved a capability gradient: Sonnet seats + the neutral reciprocation ledger dethrone the
DishonestCooperator freerider 3-of-4 (subsidy −78%, first-ever LLM↔LLM mutual-support coalitions),
where a naive 14b table lost 4/4. **The one loss (seed 3) is the residual failure mode: coordination
never FORMED** — zero Support declarations by anyone all game, atomized play, freerider blowout.
Every game there started from a blank slate.

**Does compact memory of PRIOR GAMES teach the table to coordinate — do atomized losses become
coalitions next game?** This is exactly the recurring-opponent setting a public leaderboard arena
creates, so the memory format built here becomes part of the standard entrant scaffold.

## Design (pre-declared; no iteration after data started)
- **Arm A (baseline)** — PR #37's four *independent* games (fresh agents each game), seeds 0–3.
  Reused, not re-run.
- **Arm B (campaign)** — the SAME seeds 0→1→2→3 played SEQUENTIALLY by *persistent* agents carrying
  cross-game memory (harness-computed neutral per-game facts + each agent's own ≤80-word self-note,
  stored verbatim and prepended next game, capped to the last 3 games).

Both arms: 8 turns, map-radius 1, `--llm-seats 0,1,2 --heuristics DishonestCooperator --recip-ledger
--backend claude-cli --model sonnet`, **CLI timeout pinned 180s** (Arm B pinned to Arm A's handicap
for a clean pairing; the new default is 300s going forward). Freerider = seat 3 in every game.

## New metric (first-class, applied identically to both arms)
**LLM↔LLM supports** — Support orders whose target unit belongs to *another LLM seat* (coalition
formation). PR #37 saw this only qualitatively; here it is measured. Computed from decision logs, so
Arm A is scored retroactively with the same extractor.

## Falsifiable bar (pre-declared)
- **Primary (learning signal)**: across campaign games 2–4 (seeds 1,2,3), LLM↔LLM supports/game
  EXCEED the Arm A mean (**0.75**), AND the freerider wins ≤1 of games 2–4. Special attention to
  seed 3 (Arm A's atomized blowout).
- **Mechanism**: subsidy stays ≤ Arm A's (**1.50/game** — no seduction regression), and the
  self-notes visibly reference non-reciprocation / coordination (legible, not coincidental learning).
- **Anti-patterns, reported honestly**: game-1 ≈ games-2-4 (flat) → memory didn't teach; subsidy
  RISES → memory hurt. No re-runs, no prompt tweaks after start.

## Arm A (baseline) — final, re-scored with the new extractor
Freerider wins **1/4** (seed 3); mean margin **+3.58**; mean subsidy **1.50/game**; mean **LLM↔LLM
supports 0.75/game**; parse-fail 21.8% (18% of that was 180s-timeout forced Holds, not true parse
failure — see PR #37).

| seed | freerider | LLM mean | margin | outcome | subsidy | LLM↔LLM supports |
|---|---|---|---|---|---|---|
| 0 | 15.0 | 12.7 | +2.3 | LLM held | 0 | **2** |
| 1 | 15.0 | 14.3 | +0.7 | LLM held | 3 | **0** |
| 2 | 12.0 | 14.0 | −2.0 | LLM held | 3 | **1** |
| 3 | 23.0 | 9.7 | +13.3 | **freerider WON** | 0 | **0** |

Note the coordination signal tracks the outcome: the seed-3 blowout had **zero** LLM↔LLM supports
(atomized), consistent with PR #37's "coordination never formed" reading.

## Arm B (campaign) — final
One sequential campaign, seeds 0→1→2→3, persistent agents, ~4.7h wall-clock. Freerider **wins 0/4**;
mean margin **−0.83**; mean subsidy **1.25/game**; mean **LLM↔LLM supports 1.75/game**; parse-fail
24.5% (timeout-inclusive, pinned 180s — comparable to Arm A's 21.8%).

Per game, Arm B with same-seed Arm A in parentheses (freerider = p3):

| game | seed | scores p0/p1/p2/**FR** | margin B (A) | subsidy B (A) | LLM↔LLM B (A) | outcome |
|---|---|---|---|---|---|---|
| 1 | 0 *(blank slate)* | 15/14/8/**8** | −4.3 (+2.3) | 0 (0) | 1 (2) | LLM held |
| 2 | 1 | 10/13/22/**15** | +0.0 (+0.7) | 2 (3) | 0 (0) | LLM held |
| 3 | 2 | 16/13/12/**9** | −4.7 (−2.0) | 0 (3) | **3 (1)** | LLM held |
| 4 | 3 | 13/8/22/**20** | +5.7 (**+13.3, FR WON**) | 3 (0) | **3 (0)** | **LLM held** |

Aggregate:

| metric | Arm A (independent) | **Arm B (campaign)** |
|---|---|---|
| freerider wins | 1/4 | **0/4** |
| mean margin (FR − LLM mean) | +3.58 | **−0.83** |
| mean subsidy / game | 1.50 | **1.25** |
| mean LLM↔LLM supports / game | 0.75 | **1.75** |
| parse-fail (timeout-inclusive) | 21.8% | 24.5% |

### The headline — seed 3 (Arm A's atomized blowout → an Arm B coalition hold)
In **Arm A** seed 3, *no seat declared a single Support all game* — atomized play, and the freerider
out-expanded three disorganized neighbors to a **win** (23 vs 8–11, margin +13.3), zero coordination.

In **Arm B** seed 3, the same seeds/map — but the agents carried three games of records + notes
(*"p3 declared ally every turn but never reciprocated Support"*, *"don't let p3 snowball unopposed"*).
The freerider was **held to 2nd** (p2 won 22, freerider 20), and a real **mutual-support coalition
formed** (LLM↔LLM supports 3 vs Arm A's 0). From the negotiation logs, turns 7–8:

```
turn 7  p0: toward-FR=hostile allies=p2  hostile=p3 | u1 -> Support(u4=p2) [coalition]
turn 8  p0: toward-FR=hostile allies=p2  hostile=p3 | u1 -> Support(u4=p2) [coalition]
        p2: toward-FR=hostile allies=p0  hostile=p3 | u4 -> Support(u1=p0) [coalition]   <- reciprocal
```

p0↔p2 built a reciprocal support block and turned hostile on the freerider — the exact coordination
the blank-slate table never formed here. (Honest nuance: p1 defected the *other* way, staying allied
to the freerider and even backing its unit — so it was a **p0+p2 bloc, not a whole-table shun**, and
that split is why seed-3 subsidy rose to 3.)

### The self-notes are legible and acted upon (the qualitative payoff)
Every seat, every game, wrote a coherent ≤80-word note naming non-reciprocation and coordination.
Stored verbatim (neutrality-exempt), prepended next game. Verbatim samples:

> **seat 2, after game 1 (seed 0), carried into seed 1:** *"…p3 declared ally toward me all 7 turns
> but no actual Support ever materialized either way - watch for empty alliance signaling, don't rely
> on declared allies without concrete Support exchange. p0 and p1 never engaged with me at all -
> likely formed their own bloc. Next game: … don't let p0/p1 snowball unopposed, consider testing
> p3's reliability with small Support commitment before trusting fully."*

> **seat 0, after game 3 (seed 2), carried into the decisive seed 3:** *"Won last game (16 pts, rank
> 1). P3 declared ally every single turn (7/7) but I never reciprocated with Support - worth
> exploiting again, they seem consistently … too trusting. … Consider actually reciprocating P3's
> loyalty next time to lock in a stronger alliance early."*

> **seat 0, after the decisive seed 3:** *"…p3 declared ally every turn but never reciprocated
> Support despite me giving it twice - likely exploiting my goodwill while quietly building toward the
> win. … Next time: don't give free Support without reciprocal pacts; watch p3's 'ally' talk as cheap
> signaling, and pressure p2 early since they scale well unchecked."*

## Verdict vs the pre-declared bar

**Primary (learning signal): PASS.** Across campaign games 2–4 (seeds 1,2,3), LLM↔LLM supports/game =
(0, 3, 3) → **mean 2.0, well above the Arm A mean of 0.75**, AND the freerider wins **0** of games
2–4 (≤ 1). Special attention to seed 3: Arm A's signature atomized blowout became an Arm-B coalition
hold with coordination forming where it never had — **memory fixed the atomized loss.**

**Mechanism: mostly clean.**
- **No seduction regression overall**: mean subsidy 1.25 ≤ Arm A's 1.50. (Caveat: seed 3's hold came
  *with* elevated subsidy — 3 vs Arm A's 0 — because p1 kept feeding the freerider while p0+p2 formed
  the counter-coalition. The win came by out-competing + partial-coalition, not a clean whole-table
  shun. This matches PR #37's "out-competes more than it punishes.")
- **Legible learning**: the self-notes visibly reference non-reciprocation and coordination and the
  later-seed coordination uptick (seeds 2,3: 3,3 vs Arm A 1,0) tracks them — not coincidental.

**Honest anti-pattern checks.**
- *Flat?* No. The coordination signal is concentrated in the later campaign games (seeds 2,3), which
  carry the most accumulated notes; the same seeds in blank-slate Arm A produced 1 and 0. **But note
  the control:** game 1 (seed 0) is a blank slate in *both* arms, and there Arm B actually beat the
  freerider by more than Arm A (−4.3 vs +2.3) with *fewer* LLM↔LLM supports (1 vs 2) — pure run
  variance (sonnet is stochastic on the radius-1 map). So the improvement is **not** uniform, and not
  all of it is attributable to memory. The clean, memory-attributable signal is the same-seed A→B
  delta on the later games (seed 2: subsidy 3→0, LLM↔LLM 1→3; seed 3: FR-won→held, LLM↔LLM 0→3).
- *Subsidy rose?* No, at the arm level (1.25 ≤ 1.50). Only seed 3 rose, via p1's defection.
- *Heterogeneous learning.* The notes are not a uniform "shun p3." The freerider's clean reputation
  (DishonestCooperator never trips a breach) genuinely confuses the read: some seats concluded *"p3
  seems consistently friendly/reliable, worth actually engaging"* while others concluded *"cheap
  signaling, don't give free Support."* The table's coordination emerged from a subset (p0+p2 in seed
  3), not a consensus — a faithful picture of in-context social learning, not a clean policy.

**Honest call: PASS — a stronger result than PR #37's directional pass.** The freerider goes from
1/4 wins to **0/4**; coordination more than doubles (0.75 → 1.75 LLM↔LLM supports/game); and the one
seed the blank-slate table *lost* to an atomized blowout becomes a coalition hold. What cross-game
memory does **not** yet produce is a *clean* or *whole-table* anti-freerider policy — the learning is
legible but heterogeneous, coalitions are partial, and one seed's hold still leaked subsidy.

## Reproduce
```
FOEDUS_LLM_CLI_TIMEOUT=180 uv run --extra llm python scripts/foedus_llm_diplomat_run.py \
  --num-games 4 --max-turns 8 --seed-offset 0 \
  --llm-seats 0,1,2 --heuristics DishonestCooperator --map-radius 1 \
  --recip-ledger --campaign --backend claude-cli --model sonnet --transcripts 4 --out-dir <dir>
# score (LLM<->LLM supports first-class); run over the Arm A out-dir too for the paired numbers:
uv run --extra dev python scripts/foedus_memory_metrics.py --out-dir <dir>
```

## Follow-ups
- The timeout handicap is now opt-in: default 300s going forward (`FOEDUS_LLM_CLI_TIMEOUT`) kills the
  ~18–24% forced-Hold parse-fail; a 300s re-run would measure memory without the handicap.
- Whole-table coordination is still not reliable — an explicit-shunning probe, or seeding the note
  with a pact-first prompt, could test whether the partial coalition can be made a consensus.
- Longer campaigns (>4 games) would test whether the coordination compounds or plateaus.
