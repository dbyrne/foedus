# Attribution study (8 games, fresh per-game identities) — results + honest verdict

**Status:** PRE-REGISTERED (design + A1/A2/A3 decision rules + explicit
thresholds committed in `018b156` BEFORE game 0, together with the sealed
seed commitment; see `README.md`). Results below apply those rules
mechanically. No prompt tweaks, no re-runs after the seeds were revealed.
**Date:** 2026-07-11
**Archive:** this directory (`run/` for all raw artifacts; `scorecard.json` /
`autopsy-s1.json` are the tools' `--json` outputs kept for re-derivation).
**Harness:** `scripts/foedus_canonical_campaign.py --fresh-identities`
(orchestration-level control, engine untouched at `main` = `ba01d6f`),
`scripts/foedus_canonical_scorecard.py`, `scripts/foedus_s1_autopsy.py`
(coverage-guarded). Board preset: `foedus.presets.ruleset_v1`.

---

## 1. Headline

**A1 = VANISHES.** With fresh per-game identities — everything else
identical to the Sonnet arm — the freerider containment **disappeared**:
Golf won 2 of 8 games, finished with a mean margin of −0.67 (vs the Sonnet
arm's −13.25), an average finishing rank of 2.375 (*better* than both prior
8-game runs' 2.500), and was never eliminated. Per the pre-registered
downgrade framing (README §3), the 2×2's positive cell is downgraded:
**the Sonnet arm's containment required cross-game persistence — it was not
produced by within-game table coordination alone.** This is a steering
result for the arena thesis, reported plainly.

The kicker: this table coordinated MORE than any run to date (11.0 LLM↔LLM
supports/game — above run #1's 9.88 and the Sonnet arm's 7.75) and still did
not contain Golf. Within-game coordination volume, by itself, does not
punish the freerider.

## 2. A1 (primary) — the pre-registered classification, applied mechanically

Pre-registered metrics (defined in README §3, same tools as prior arms):

| metric | value | PERSISTS needs | VANISHES needs |
|---|---:|---|---|
| Golf wins (`aggregate.freerider_wins`) | **2/8** | ≤ 1 ✗ | ≥ 3 ✗ |
| Golf mean margin (`aggregate.mean_margin`) | **−0.67** | ≤ −5.0 ✗ | ≥ 0.0 ✗ |
| Golf avg finishing rank (`_compute_ranks`) | **2.375** | ≥ 3.25 ✗ | ≤ 2.75 ✓ |

PERSISTS requires all three conjuncts — fails. VANISHES requires any one
disjunct — **the rank disjunct fires** (2.375 ≤ 2.75, squarely back in the
uncontained regime of runs #1 and Haiku, both 2.500). **A1 = VANISHES.**

Golf's per-game record (seeds from `seed_manifest.revealed.json`, ranks via
`foedus.scoring._compute_ranks`; **zero eliminations in any game**, so no
rank-convention effects this run):

| game | Golf seat | Golf score | table scores | Golf rank | Golf margin | winner (margin vs runner-up) |
|---:|---:|---:|---|---:|---:|---|
| 0 | 3 | 32 | 35, 40, 23, 32 | 3 | −0.7 | Bravo (+5) |
| 1 | 0 | 38 | 38, 34, 31, 26 | **1** | **+7.7** | **Golf** (+4) |
| 2 | 1 | 35 | 30, 35, 34, 27 | **1** | **+4.7** | **Golf** (+1) |
| 3 | 2 | 32 | 47, 21, 32, 39 | 3 | −3.7 | Oscar (+8) |
| 4 | 3 | 32 | 37, 34, 33, 32 | 4 | −2.7 | Quebec (+3) |
| 5 | 0 | 32 | 32, 27, 36, 31 | 2 | +0.7 | Uniform (+4) |
| 6 | 1 | 23 | 42, 23, 40, 23 | 3 | −12.0 | Yankee (+2) |
| 7 | 2 | 34 | 33, 24, 34, 43 | 2 | +0.7 | Zulu (+9) |

OpenSkill footnote (descriptive only, per the pre-registered caveat): Golf
tops the conservative leaderboard (μ−3σ = 4.13, 1st of 25 identities) — but
that is largely a σ artifact: Golf played 8 rated games while every fresh
identity played exactly 1, so Golf's σ (7.16) is the only one that shrank.
The outcome-level metrics above carry the verdict, as pre-registered.

## 3. Four-way comparison

| metric | run #1 (Sonnet, buggy engine) | Haiku re-run (fixed) | Sonnet arm (fixed) | **this study (fixed, fresh IDs)** |
|---|---:|---:|---:|---:|
| games | 8 | 8 | 4 | 8 |
| freerider win-rate | 3/8 (37.5%) | 1/8 (12.5%) | 0/4 (0%) | **2/8 (25%)** |
| freerider mean margin | +2.62 | +0.83 | −13.25 | **−0.67** |
| freerider avg finishing rank | 2.500 | 2.500 | 3.750 | **2.375** |
| freerider OpenSkill cons. | 3.06 (2nd/4) | 4.58 (2nd/4) | −5.48 (last/4) | 4.13 (1st/25 — σ artifact, §2) |
| eliminations (any) | — | — | 2 (incl. Golf ×1) | **0** |
| LLM↔LLM supports/game | 9.88 | 0.25 | 7.75 | **11.00** |
| subsidy to freerider/game | 0.38 | 0.25 | 1.00 | **1.88** |
| pipeline proposed→executed→paid | 32→39→1 (2.6%) | 20→21→2 (9.5%) | 5→9→2 (22.2%) | **20→20→1 (5.0%)** |
| pinned Supports/game | 0.0 | 5.0 | 8.0 | **5.25** (42 of 551 parsed) |
| parse-fail rate | 8.16% | 1.04% | 1.40% | **1.74%** (10/576; 9 timeouts, 1 true-parse) |
| wall-clock/game | 115.2 m | 42.2 m | 45.0 m | 46.0 m |

Two reads jump out beyond A1 itself:

1. **The executed→paid "monotonic trend" is broken.** The Sonnet arm noted a
   suggestive 2.6% → 9.5% → 22.2% conversion sequence and flagged it as
   fragile (paid counts of 1–2). This run lands at 5.0% (1 paid event in 20
   executions) with the *highest* coordination volume yet — confirming the
   fragility warning. Paid punishment remains a rare event everywhere.
2. **Fresh tables subsidize the freerider the most** (1.88 supports/game vs
   0.38/0.25/1.00). The Sonnet arm's first-half→second-half subsidy drop
   (2.0 → 0.0, to zero) was read as "learning to punish"; this run's
   half-split is 2.0 → 1.75 — a decline **far weaker** than the Sonnet
   arm's, with each fresh table starting naive and most of the feeding
   intact in the second half (game 1: subsidy 4 and Golf **won**; game 4:
   subsidy 5). Exploratory observation, not a pre-registered test.

## 4. A2 (mechanism) — punishment-pipeline linkage

Pipeline per game (`foedus_s1_autopsy.py`, coverage-guarded; totals
20 proposed / 20 executed / 1 paid):

| game | proposed | executed | paid | pipeline-active | Golf margin |
|---:|---:|---:|---:|:--:|---:|
| 0 | 3 | 3 | 0 | yes | −0.7 |
| 1 | 0 | 0 | 0 | no | +7.7 |
| 2 | 0 | 2 | 0 | yes | +4.7 |
| 3 | 0 | 0 | 0 | no | −3.7 |
| 4 | 0 | 0 | 0 | no | −2.7 |
| 5 | 10 | 8 | 0 | yes | +0.7 |
| 6 | 1 | 1 | 0 | yes | −12.0 |
| 7 | 6 | 6 | 1 | yes | +0.7 |

- **Coordination-channel rule: NOT satisfied.** The pre-registered rule
  required A1 ∈ {PERSISTS, WEAKENS} as its first conjunct; A1 = VANISHES,
  so the study finds **no evidence that within-game coordinated punishment
  contains this freerider**. (For completeness: the split itself — both
  cells ≥ 3 games, so evidence-grade per the pre-registration — runs
  active −1.33 vs inactive +0.44 mean Golf margin. The *direction* matches
  "pipeline games hit Golf harder," but the magnitude is small, Golf **won**
  a pipeline-active game (g2), and the active-cell mean is dominated by g6's
  −12.0, a game with only ONE pipeline event.)
- **Rival-channel (per-game, emergent) direction: mixed.** Pre-registered
  Spearman signs over 8 games: winner-vs-table-mean dominance vs Golf margin
  = **−0.49** (more dominant winner ↔ worse Golf outcome — the rival-channel
  sign, and it holds at −0.49 when the two Golf-won games are excluded);
  winner-vs-runner-up dominance = −0.03 (no signal; +0.52 excluding Golf's
  wins). Directional reads only, as pre-registered — no significance claims
  at n = 8.

Honest summary for A2: with containment gone, the "which within-game channel
contained Golf?" question is largely moot — **nothing contained Golf here.**
The informative fact is the conjunction: highest-ever coordination volume
(11.0 supports/game) + functioning pipeline plumbing (20 executions, 1 paid)
+ no containment.

## 5. A3 (descriptive) — dominance distribution: was "a Foxtrot" inevitable?

Per-game winner margins:

| | winner − runner-up (per game) | mean | winner − table mean, mean |
|---|---|---:|---:|
| Sonnet arm (4 g, Foxtrot won 3) | 3, 7, 15, 1 | 6.5 | 9.3 |
| this study (8 g, 7 distinct winners) | 5, 4, 1, 8, 3, 4, 2, 9 | 4.5 | 7.0 |

Fresh-identity games still produce clear per-game winners — sometimes at
Foxtrot-like scale (g3: +12.25 over table mean; g6: +10.0) — but dominance
is a bit shallower on average and far less concentrated: **7 distinct
winners in 8 games** (Bravo, Golf ×2, Oscar, Quebec, Uniform, Yankee,
Zulu). Identity-level concentration is impossible by construction only for
the 24 single-game LLM identities; **Golf — the one identity that plays all
8 games — is exempt from that constraint, and is in fact the run's only
repeat winner.** That irony cuts the same way as A1: the sole persistent
identity at this table is its most frequent winner, which reinforces, not
weakens, the VANISHES reading — **per-game emergent dominance did not
translate into freerider containment** (twice the "dominant winner" *was*
the freerider). A persistent Foxtrot was not inevitable: it was a product
of the persistent-identity design.

## 6. Verdict

**The Sonnet arm's freerider containment was NOT table-level within-game
coordination. It required cross-game persistence.** This study removed
exactly one thing — persistent identities (cross-game memory/ledger
accumulation and the possibility of a persistent dominant player) — and the
containment result reverted to the uncontained regime of the pre-Sonnet-arm
runs (in fact Golf's best avg rank of any canonical run), despite the
highest within-game coordination volume ever recorded in this arena.

Per the pre-registered framing: the 2×2's positive cell is **downgraded to
"containment required a persistently dominant entrant."** The rival channel
survives as the leading explanation for the Sonnet arm; the pure
within-game-coordination channel is dead.

**What this study cannot separate (load-bearing caveat):** the control
removed *all* persistence-dependent channels at once. "A persistent rival
(Foxtrot) individually beat Golf down" and "persistent tables *learn*
across games to stop subsidizing / start punishing Golf" are both consistent
with PERSISTS-there + VANISHES-here. The subsidy pattern (§3, point 2) is
exploratory evidence that cross-game learning is at least part of the
story — distinguishing the two would need a design that keeps cross-game
memory but rotates which entrant accumulates it (or an explicit
anti-dominance handicap), outside this dispatch's cost cap.

**Caveats.** n = 8 games, one map archetype (`continental_sweep`), a single
*scripted* `DishonestCooperator` (fixed exploiter, not adaptive); cross-run
comparisons ride on different seeds; the four runs differ in n (8/8/4/8);
Golf's leaderboard position here is σ-inflated (§2); "paid" remains an
outcome-level score-drop proxy (run #1's `autopsy-s1.md` §0 definition);
A2/A3 associations are directional reads at n = 8, pre-registered as such.
The A1 verdict is threshold-crisp on the rank disjunct but note honestly:
wins (2) and margin (−0.67) individually landed *between* the PERSISTS and
VANISHES cut-points — the overall picture is "containment gone," not "Golf
dominant."

## 7. Corpus banking (secondary deliverable)

All 24 per-seat decision logs (`run/decisions_game{g}_seat{s}.jsonl`; 576
decisions, prompt + raw_response + parsed + fell_back + n_coerced) are
banked in the standard gym-compatible format — 8 more high-coordination
fixed-engine Sonnet games available to extend the gym corpus (12 → 20
games). No training work in this milestone. Note for corpus users: these
seats have EMPTY cross-game memory by design (every game is a "game 0"),
which is itself a useful contrast slice against the Sonnet arm's
memory-bearing games.

## 8. Engine + seal integrity

- **Seal: verified.** Commitment
  `86c4b7fe29ef411cd17c251818f12dfe9ceb89075bff6a8ae64508373cba8615`
  committed to git in `018b156` BEFORE game 0 (seal-first flow, README §5);
  `seed_manifest.revealed.json` reproduces it via `campaign.verify()` and
  `foedus_verify_invariant.py` confirms `seeds_match_sweep=True`.
- **Resolver invariant: HELD.** `foedus_verify_invariant.py --pairings 20`:
  1,872 per-turn one-unit-per-node checks across the 8 actual game seeds ×
  20 heuristic pairings, zero violations.
- **Coverage guardrails:** `foedus_canonical_scorecard.py` and
  `foedus_s1_autopsy.py` ran clean (no `CoverageError`) against all 576
  decision records across 8 games / 24 decision-log files.
- **Fresh-identity audit:** all 24 `campaign_memory_game*_seat*.json` files
  contain exactly **1** record each — direct on-disk proof that no
  cross-game memory accumulated on any seat. 24 unique LLM handles, none
  reused across games, none colliding with Delta/Echo/Foxtrot/Golf.
- **Parse-fail:** 10/576 (1.74%) — 9 CLI timeouts + 1 true parse failure,
  within the range of the prior fixed-engine runs (1.0–1.4%).
- **Decisions:** 576 = the pre-registered estimate (8×3×12×2) exactly; no
  eliminations, so no seat lost decision pairs.
- **Run legs:** single launch leg, rc=0, 6h10m (`timing.log`).
  `run_summary.json.resumed = true` reflects the pre-registered seal-first
  launch flow (seal committed pre-game-0, live run enters via the
  unit-tested resume-from-zero path), NOT a crash. The guarded `@reboot`
  autoresume was installed before launch, never fired, and was removed
  post-completion.

## 9. Reproducing

All commands below assume cwd = repo root.

```sh
OUT=docs/research/2026-07-11-attribution-study/run

# verify the seal
PYTHONPATH=. python3 - <<PY
import json
from foedus.eval import campaign
m = campaign.SeedManifest.from_dict(
    json.load(open("$OUT/seed_manifest.revealed.json")))
sealed = json.load(open("$OUT/seed_manifest.sealed.json"))
assert m.commit == sealed["commit"]
assert campaign.verify(m)
print("OK:", m.seeds)
PY

# scorecard (wins, margin, subsidy, supports, parse-fail, standings)
PYTHONPATH=. python3 scripts/foedus_canonical_scorecard.py --out-dir "$OUT"

# punishment pipeline (A2)
PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py --out-dir "$OUT"

# independent OpenSkill recompute
PYTHONPATH=. python3 scripts/foedus_compute_ratings.py "$OUT/sweep.jsonl"

# pin-Support usage (§3)
grep -oh 'Support(target=[0-9]*, require_dest=[A-Za-z0-9]*)' "$OUT"/decisions_game*_seat*.jsonl | wc -l
grep -oh 'Support(target=[0-9]*, require_dest=[0-9]\+)' "$OUT"/decisions_game*_seat*.jsonl | wc -l

# resolver invariant + seeds-match-sweep
PYTHONPATH=. python3 scripts/foedus_verify_invariant.py --out-dir "$OUT" --pairings 20

# Golf avg finishing rank + per-game ranks (A1) — engine's own convention
PYTHONPATH=. python3 - <<PY
import json
from foedus.scoring import _compute_ranks
ranks = []
for line in open("$OUT/sweep.jsonl"):
    r = json.loads(line)
    scores = {i: r["final_scores"][i] for i in range(4)}
    survivors = [p for p in range(4) if p not in set(r.get("eliminated") or [])]
    ranks.append(_compute_ranks(scores, survivors, 4)[r["agents"].index("Golf")])
print("Golf ranks:", ranks, "avg:", sum(ranks)/len(ranks))
PY

# fresh-identity audit: every memory file holds exactly one record
PYTHONPATH=. python3 - <<PY
import glob, json
counts = {len(json.load(open(f))["records"])
          for f in glob.glob("$OUT/campaign_memory_game*_seat*.json")}
assert counts == {1}, counts
print("OK: 24 memory files, 1 record each — no cross-game accumulation")
PY
```
