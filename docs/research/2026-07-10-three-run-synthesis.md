# Three-run synthesis — does a Sonnet table contain a scripted freerider?

**Status:** repo-facing synthesis, doc-only. Zero new games; every number below
traces to a document, PR, or committed artifact merged to `main` before this
doc was written.
**Date:** 2026-07-10.
**Sources** (read the originals for full detail — this doc summarizes and
cross-references, it does not replace them):

| # | Doc | What it is |
|---|---|---|
| 1 | `docs/research/2026-07-04-canonical-campaign-v1/results.md` | Run #1 — 8-game canonical campaign, Sonnet, buggy engine |
| 1a | `docs/research/2026-07-04-canonical-campaign-v1/autopsy-s1.md` (PR #45) | Corpus autopsy of run #1 — punishment-conversion pipeline |
| 1b | `docs/research/2026-07-04-canonical-campaign-v1/autopsy-s1-5-confounds.md` (PR #46) | Confound-resolution pass — finds the parser bug |
| 2 | PR #47 (`scripts/foedus_require_dest_fix_validation.py`) | The fix + its before/after validation on the sealed run #1 corpus |
| 3 | `docs/research/2026-07-09-haiku-fitness-probe/probe-report.md` (PR #48) | 2-game Haiku fitness probe, fixed engine — model-selection step |
| 4 | `docs/research/2026-07-10-canonical-haiku-rerun/results.md` (PR #49) | 8-game canonical re-run, Haiku, fixed engine |
| 5 | `docs/research/2026-07-10-canonical-sonnet-arm/results.md` (PR #50) | 4-game contingency arm, Sonnet, fixed engine — the three-way table |

---

## 1. The question

Pre-registered in the original canonical-campaign spec: **can an LLM table
detect and contain a scripted freerider through coordinated punishment, or
does it keep subsidizing (or simply fail to dethrone) a persistent
defector?** The freerider (`DishonestCooperator`, house handle **Golf**) is a
fixed, non-adaptive exploiter — it delegates to plain `GreedyHold` and never
self-supports (source 1a §1.3) — seated alongside three LLM entrants (Delta /
Echo / Foxtrot) at a 4-seat, 12-turn Ruleset-v1 table with seat rotation,
cross-game memory, and commit-reveal sealed seeds. All three sealed runs
below share this format, board preset (`continental_sweep`), and freerider.

## 2. The bug story

**Run #1** (8 games, all 3 LLM seats Sonnet) published a headline **NULL on
defector-containment**: the table behaviorally withdrew from Golf (subsidy
0.75→0.00/game front-to-back-half) and closed ranks with itself (coalition
6.0→13.75/game), but the outcome measures that actually define containment
moved the wrong way — Golf's margin against the LLM mean rose (−0.34→+5.58)
and it won *more* of the later games (1→2), finishing 3/8 outright wins (tied
for most in the field) and 2nd of 4 on the OpenSkill leaderboard (source 1
§7–§8).

A follow-up autopsy (source 1a) traced this to the **punishment-conversion
pipeline**: across the campaign, 32 punishment-pipeline actions against Golf
were proposed (declared attack-move intents, attack-backing Support intents,
and attack-bearing pact-proposal terms — source 1a §0) and 39 order-actions
executed against it, but only **1** produced an observable income drop
(source 1a §1; expressed as a rate, 2.6%, in source 5 §5). The autopsy ruled
out awareness (Golf was plainly visible in both zero-engagement games) and
commitment (all 17 declared attack-move intents converted to a matching
submitted order) as the bottleneck, and recommended an "Economics" fix —
arguing the payoff structure under-rewards the supporting unit.

**Before that fix shipped**, a confound-resolution pass (source 1b) resolved
all three confounds it had flagged, using a turn-by-turn replay of the sealed
corpus through the real engine (`foedus.eval.resolution_replay`), verified to
reproduce all 8 games' final scores, turns, and eliminations exactly with
zero mismatches against the original logged orders (source 1b §0):

- **Check 1 (ground-truth replay) corrected the S1 headline itself.** The
  real dislodge count was **2**, not 1 — the score-delta proxy missed a
  final-turn dislodge with no next-turn prompt to observe it in (source 1b
  §1).
- **Check 2: infra reliability was not the driver.** Restricting to a strict
  clean subset (34 of 39 executions, 87% coverage, excluding only genuine
  transport/timeout failures) left the conversion rate unchanged (source 1b
  §2).
- **Check 3: the real bottleneck was a parser/legality bug, not economics.**
  `foedus.legal.legal_orders_for_unit` never enumerates the `require_dest`
  ("pin") variant of `Support` — by design, per its own docstring, as an
  opt-in refinement — but `foedus.agents.llm.parse.parse_order` legality-gated
  every submitted order by membership in exactly that candidate list. So
  **any `Support(target=T, require_dest=D)` order was unconditionally coerced
  to `Hold()`**, even though `foedus.resolve`'s own normalization would have
  accepted it and the prompt schema documented the field. A corpus-wide sweep
  found **67 declaration-events** silently discarded this way (29
  orders-phase submissions / 28 negotiate-phase intents / 10 pact-proposal
  terms), of which **12** backed an attack on Golf specifically — **0 of the
  12 were geometrically illegal** — and counterfactually reinstating them
  (holding every other unit's order fixed) flipped the paired attacker from
  `fail` to `success` in **9 of 12** cases (source 1b §3).

**PR #47** shipped the fix (accept a `require_dest` pin iff its bare
`Support(target=T)` and the implied `Move(dest=D)` are both legal candidates
— matching what `_normalize` already accepted, without loosening
`legal_orders_for_unit`'s enumeration itself). Its own before/after
validation script re-ran the fixed parser against the exact replayed state
each of the 12 attack-backing pins saw and reproduced source 1b's numbers
exactly: **all 12 accepted post-fix, 9/12 mover flips, the 3 non-flips being
ordinary support-cuts unrelated to the parser** (source 2). Direct,
independent confirmation later reconfirmed the mechanism from raw decision
logs rather than autopsy tooling: run #1's own logged parsed orders contain
**zero** pinned Supports anywhere (structurally impossible pre-fix), versus
**40** in the Haiku re-run and **32** in the Sonnet arm — both post-fix runs
(source 5 §5).

**Honest framing.** Run #1's null was an instrument artifact: the engine
being measured was silently discarding a material share of the table's own
coordination attempts before they ever reached the resolver. Run #1 remains
archived, unmodified, as the confounded record of the bug it exposed — not
as the campaign's answer to the containment question (source 4 §1).

## 3. The 2×2

The design is a 2×2 (engine × model) with one cell never run — Haiku was
only introduced *after* the fix, as a cost-saving measure for the re-run, so
there was no reason to burn budget re-running the known-buggy engine on a
second model:

| | **buggy engine** (pre-PR #47) | **fixed engine** (post-PR #47) |
|---|---|---|
| **Sonnet** (high coordination) | Run #1 — 8 games (source 1) | Sonnet arm — 4 games (source 5) |
| **Haiku** (low coordination) | *not run* — no reason to, once the bug was understood | Haiku re-run — 8 games (source 4) |

The model-selection step in between: a 2-game, non-sealed **Haiku fitness
probe** on the fixed engine (source 3) — asking whether Haiku could stand in
for Sonnet on the mechanical axis (parse-fail) without producing degenerate
play, to decide which model to burn the 8-game re-run budget on. It cleared
decisively on the mechanical axis (0/144 parse-fail vs. Sonnet's 8.2%
baseline) and "not degenerate, but thin" on coordination (2/24 Support orders
cross-player, 2/72 pact proposals, correct freerider identification in every
self-note) — verdict **HAIKU FIT**. The probe's own verdict section is
explicit that this was a live judgment call, not a clean threshold-clear: "a
reader could reasonably read it as BORDERLINE rather than FIT" if weighting
the thin coordination evidence more heavily (source 3, "Verdict").

### Three-way outcome comparison (source 5 §4, the canonical citation)

| metric | run #1 (Sonnet, buggy) | Haiku re-run (fixed) | **Sonnet arm (fixed)** |
|---|---:|---:|---:|
| games | 8 | 8 | 4 |
| freerider win-rate | 3/8 (37.5%) | 1/8 (12.5%) | **0/4 (0%)** |
| freerider mean margin vs. LLM mean | +2.62 | +0.83 | **−13.25** |
| freerider OpenSkill conservative (μ−3σ) | 3.06 (2nd of 4) | 4.58 (2nd of 4) | **−5.48 (4th of 4, last)** |
| freerider avg finishing rank | 2.500 (3rd of 4) | 2.500 (tied-worst) | **3.750 (worst, clear margin)** |
| LLM↔LLM cross-player Supports/game ("coalition") | 9.88 (79 total) | 0.25 (2 total) | **7.75 (31 total)** |
| parse-fail rate | 8.16% (47/576) | 1.04% (6/576) | 1.40% (4/286) |
| match wall-clock | 15.36 h (115.2 m/game) | 5.62 h (42.2 m/game) | 3.00 h (45.0 m/game) |

*Note on labels:* run #1's own `results.md` calls the LLM↔LLM Support metric
"coalition"; the two later runs' comparison tables call the identical metric
"LLM↔LLM cross-player supports/game" — same definition (a Support order whose
target is another LLM seat's unit), different label per source. This doc uses
the fuller label except where quoting a source table verbatim.

### Punishment-conversion pipeline, three-way (source 5 §5)

| | proposed | executed | paid | executed→paid |
|---|---:|---:|---:|---:|
| run #1 (Sonnet, buggy) | 32 | 39 | 1 | 2.6% |
| Haiku re-run (fixed) | 20 | 21 | 2 | 9.5% |
| **Sonnet arm (fixed)** | 5 | 9 | 2 | **22.2%** |

The rate looks monotonic (2.6%→9.5%→22.2%), but every source explicitly
flags this as **suggestive, not conclusive** — the "paid" counts behind it
are 1, 2, and 2 events. At that base rate a single game's outcome swings the
percentage by double digits; this is one data point consistent with a
dose-response relationship, not a demonstration of one (source 5 §5, source 4
§5).

## 4. The result

**Decisive containment appears in exactly one cell: high-coordination
(Sonnet) × fixed engine.** The Sonnet arm is qualitatively different from
both prior runs, where Golf held 2nd of 4 on the leaderboard in *both*: here
Golf finishes **last of 4**, **0 of 4 wins**, mean margin **−13.25**, and
holds the **strictly lowest raw final score in every one of the four games**
(source 5 §3 — game-by-game: g0 Golf 23 of {27,37,34,23}; g1 Golf 20 of
{20,31,35,42}; g2 Golf 21 of {47,21,32,32}; g3 Golf 23 of {28,38,23,37}). Its
avg finishing rank (3.750) is the worst of any identity in any of the three
runs to date.

Two of the four games ended in an actual **elimination**, not just a scoring
loss. In game 2, **Golf itself was eliminated outright** (`sweep.jsonl`
`eliminated: [1]`) around turns 8–9 — the same turns as this run's only two
"paid" punishment events — the single most decisive containment event in the
corpus (source 5 §3), and, since neither run #1 nor the Haiku re-run reports
any elimination at all, the single most decisive containment event across
all three runs to date (PR #50 body). (Game 3's elimination was Echo, an LLM
entrant, not Golf — a table dynamic unrelated to punishing the freerider.)

The Haiku re-run, by contrast, is a **null-ish** result on the same fixed
engine: two outcome measures moved in the containment direction (win-rate,
margin) but OpenSkill conservative and average finishing rank did not — Golf
is "statistically no less entrenched in 2nd place than it was in run #1"
(source 4 §4), and the fix's own effect is confounded by a near-total absence
of the coordination mechanism it targets (§6 below).

## 5. The caveats — load-bearing, not footnotes

Copied forward from the Sonnet arm's own framing (source 5 §6–§7), because
diluting them would misstate what this data supports:

- **Attribution is not clean.** Two of the Sonnet arm's four games (g0, g3)
  show **zero** punishment-pipeline activity (proposed = executed = paid =
  0) — no coordinated attack-backing Support was even declared against Golf —
  and **Golf still finished last or second-to-last in both of them** (rank 4
  in g0, rank 3 in g3). Containment in this run cannot be cleanly attributed
  to the specific coordinated-Support mechanism S1.5 is about; in half the
  games, Golf lost badly with the punishment pipeline never firing at all.
- **A rival channel: individual dominance.** Foxtrot won 3 of 4 games with a
  conservative OpenSkill score (10.29) more than 7 points clear of the next
  entrant. Golf's last place is equally consistent with "one entrant played
  excellently and pushed everyone else down" as with "the table coordinated
  to punish the freerider" — at n=4 with one identity this dominant, the run
  cannot distinguish the two.
- **Tiny paid-event bases.** 1, 2, and 2 "paid" events across the three runs
  respectively — the executed→paid trend (§3) is not a demonstrated
  dose-response relationship.
- **n is small and getting smaller.** 8, 8, then 4 games — the Sonnet arm has
  *less* statistical power than either baseline even though its effect size
  is larger. σ ≈ 7.6–8.0 has barely moved from OpenSkill's prior at n=4:
  Golf's rating gap is a clear 2.2σ from top-rated Foxtrot but only 0.8σ from
  Echo — the rating system itself does not call this a decisive separation
  from the full field, only from the strongest player (source 5 §7).
- **One map archetype** (`continental_sweep`) across all three runs.
- **A scripted, non-adaptive freerider.** `DishonestCooperator` is a fixed
  exploiter (plain `GreedyHold`, never self-supports) — not an adversary that
  reacts to being punished. Containment findings here say nothing about
  whether a freerider that adapts its strategy would be contained the same
  way.
- **"Paid" remains an outcome-level proxy**, not a per-combat resolution
  trace, throughout every run in this synthesis (source 1a §0; carried
  forward unchanged in sources 4 and 5).

## 6. The independent finding — coordination as a model-capability axis

Orthogonal to the containment question, the three runs together establish
something the roadmap didn't set out to measure directly: **cross-player
coordination volume is strongly model-dependent, not just table- or
engine-dependent.** LLM↔LLM Supports collapsed from Sonnet's range straight
to near-zero under Haiku, on the *identical* fixed engine and format:

| | LLM↔LLM Supports total | per game | vs. Haiku |
|---|---:|---:|---:|
| run #1 (Sonnet, buggy engine) | 79 | 9.88 | ~40× |
| Haiku re-run (fixed engine) | 2 | 0.25 | 1× (baseline) |
| Sonnet arm (fixed engine) | 31 | 7.75 | ~31× |

Both Sonnet runs land in the same high-coordination range regardless of
engine bug status; Haiku collapses to near-zero regardless of the parser fix
being present. This is why the Haiku re-run's fixed-engine test of the
punishment pipeline was underpowered: "the exact mechanism S1.5 flagged as
bottlenecked by the engine bug barely fired in this match" (source 4 §6), and
the Sonnet arm exists specifically because a low-coordination table cannot
exercise a coordination-dependent mechanism, independent of any engine
question.

**What this means going forward:**

- **For the arena/leaderboard thesis:** the social layer this project is
  built to test (alliance formation, coordinated punishment, betrayal
  tracking) is itself gated by model capability. A weaker model doesn't just
  play worse — it may barely engage the mechanism being measured at all,
  which changes what a "null result" on that model's table can be read to
  mean.
- **For gym-corpus selection** (`M-foedus-gym-pipeline-v0`): the
  cross-player-coordination signal this project wants an NN to eventually
  learn from is concentrated in Sonnet games, not Haiku games. A training
  corpus built from cost-cheaper Haiku runs would be systematically thin on
  exactly the behavior the two-tier (strategic NN + press-layer) design is
  meant to capture.

## 7. Open questions

- **An attribution study.** §5's dominant confound (Foxtrot's individual
  strength vs. the coordination mechanism specifically) could be isolated by
  a design that varies coordination while holding table skill fixed — e.g.
  mirror-model seats, or enough additional Sonnet-arm games to accumulate
  independent "paid" events for analysis apart from overall table quality
  (flagged as out-of-scope for the 4-game cost cap in source 5 §7).
- **An adaptive freerider.** Every run to date uses the same scripted,
  non-reactive `DishonestCooperator`. Whether a freerider that adjusts
  strategy in response to observed hostility would still be contained by a
  coordinating Sonnet table is untested.
- **Whether an Economics change is still warranted.** The original S1
  autopsy's recommendation (reward the supporting unit, not just the mover,
  on a successful coordinated dislodge) predates the parser-fix finding.
  S1.5 explicitly deferred this: "Only then decide whether a further
  Economics change ... is still warranted on top of the fix — the original
  Economics hypothesis may still hold and may still be worth pursuing for
  run #2, but it should be measured against a corpus where coordinated
  Support orders actually reach the engine" (source 1b §4). That
  measurement now exists (the Sonnet arm); whether it changes the answer is
  not addressed in any of the five sources and remains open.

## 8. Methods appendix

**Seals.** All three sealed campaigns (run #1, Haiku re-run, Sonnet arm) used
commit-reveal SHA-256 seed sealing — the commitment published before game 0,
seeds and nonce revealed only after the match, `campaign.verify()`
recomputing the commitment from the reveal. All three verified:

| run | commitment (short) |
|---|---|
| run #1 | `115b9931…de2b` |
| Haiku re-run | `786e2fc4…04ace` |
| Sonnet arm | `d4f9a014…b7ff8` |

**Two-reviewer + independent audit gate.** Starting with the Haiku fitness
probe (PR #48 body) and continuing through the Haiku re-run (PR #49 body) and
Sonnet arm (PR #50 body), every results doc was independently re-derived from
raw committed artifacts by two separate reviewer agents (Sonnet + Opus)
before merge, with the dispatching session (Nova) notified for a further
independent audit and none of the three self-merged. This gate caught real
issues, not just rubber-stamped: PR #48's first draft had a markdown-fence
parsing bug that silently zeroed a degeneracy metric ("zero all-Hold turns"
was a parser artifact, not a verified finding) and a factually wrong
coordination anecdote, both caught and fixed pre-merge (PR #48 body; source 3
itself documents the correction inline). PR #50's reviewers found the results
doc hadn't disclosed two in-run eliminations, which changed the "worst in 3
of 4 games" framing to what's reported in §4–§5 above (PR #50 body). PR #47
(the fix itself) predates this formalized two-reviewer gate and instead used
TDD RED→GREEN tests plus a full-suite run (1274 passed, one known
pre-existing unrelated failure) as its verification path (source 2).

**Coverage-guarded analysis.** `foedus.eval._coverage.assert_coverage` raises
`CoverageError` if an analysis tool reads zero records, parses zero of its
target corpus, or drops below 95% read/parse coverage — added after the PR
#48 incident above, and retrofitted to every corpus-reading eval tool used in
this synthesis (`foedus_s1_autopsy.py`, `foedus_s1_5_confound_check.py`,
`foedus_require_dest_fix_validation.py`, `foedus_canonical_scorecard.py`,
`foedus.eval.resolution_replay.ReplayAgent`), verified to reproduce every
existing sealed-corpus number unchanged.

**Denominators, collected** (every rate cited above, numerator/denominator
explicit):

| figure | numerator / denominator | source |
|---|---|---|
| run #1 parse-fail | 47 / 576 = 8.16% (source 1 §7.4 rounds this 8.2%) | source 4 §4 / source 5 §4 |
| Haiku re-run parse-fail | 6 / 576 = 1.04% | source 4 §7 |
| Sonnet arm parse-fail | 4 / 286 = 1.40% | source 5 §8 |
| Haiku probe parse-fail | 0 / 144 = 0.0% | source 3 |
| run #1 executed→paid | 1 / 39 = 2.6% | source 5 §5 |
| Haiku re-run executed→paid | 2 / 21 = 9.5% | source 5 §5 |
| Sonnet arm executed→paid | 2 / 9 = 22.2% | source 5 §5 |
| require_dest declaration-events, corpus-wide (run #1) | 67 total (29 orders / 28 intents / 10 pact-terms) | source 1b §3 |
| require_dest attack-backing pins, run #1 | 12 of 67 | source 1b §3 |
| counterfactual flips | 9 of 12 | source 1b §3; source 2 |
| ground-truth dislodges, run #1 (replay) | 2 of 25 attack-moves (8%) → 11 of 25 counterfactual (44%) | source 1b §3 |
| pin-Support usage, run #1 / Haiku re-run / Sonnet arm | 0/413 / 40/185 / 32/233 parsed Support orders | source 5 §5 |
| LLM↔LLM Supports, run #1 / Haiku re-run / Sonnet arm | 79/8 / 2/8 / 31/4 games | source 5 §4; source 4 §5 |

Every quantitative figure in §1–§7 above is either quoted directly from one
of the five numbered source documents or is a trivial arithmetic derivation
from numbers they report (e.g. ratios, percentage differences) — none is a
new measurement. A handful of process/methods claims (the two-reviewer gate
in §8, the elimination-disclosure catch, the "across all three runs" framing
in §4) are additionally cited to the underlying PR bodies (#47–#50) — all
merged, publicly readable via `gh pr view <n>`, and the primary source for
those specific claims, which the five numbered docs don't themselves cover.
