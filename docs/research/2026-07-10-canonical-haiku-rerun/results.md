# Canonical re-run (Haiku, 8 games) — results + honest verdict

**Status:** PRE-REGISTERED (criteria fixed before the run, see the dispatch
spec + `campaign_plan.json`); results + verdict filled in after the match. No
prompt tweaks, no re-runs after the seeds were revealed.
**Date:** 2026-07-10
**Archive:** this directory (see `README.md` for layout + seed verification).
**Harness:** `scripts/foedus_canonical_campaign.py` (+ `foedus.eval.campaign`),
`scripts/foedus_canonical_scorecard.py`, `scripts/foedus_s1_autopsy.py`
(coverage-guarded — `foedus.eval._coverage.assert_coverage`, PR #48). Board
preset: `foedus.presets.ruleset_v1`.

---

## 1. Supersession note

Run #1 (`docs/research/2026-07-04-canonical-campaign-v1/`) published a NULL
verdict on defector-containment: "a Sonnet table does not reliably dethrone
the freerider." **That verdict is superseded, not by new data contradicting
it, but because the engine it was measured on had a bug.** S1.5's
corpus-autopsy pass (`autopsy-s1-5-confounds.md`, PR #46) found that
`foedus.legal.legal_orders_for_unit` never enumerated `require_dest` ("pin")
Support variants, so `parse_order`'s legality gate silently coerced every
geometrically-valid pin Support to `Hold()` before it ever reached
`resolve.py` — **12 attack-backing coordinated Supports in run #1's own
corpus never reached the resolver**, and a counterfactual replay showed 9 of
those 12 would have flipped their paired attacker from `fail` to `success`
had they landed (PR #47 fixed the parser gap). Run #1's low executed→paid
conversion rate was measured on an engine that was silently discarding a
material fraction of the table's actual coordination attempts. **Run #1
remains archived, unmodified — it is now the confounded-null record of the
bug it exposed, not the campaign's answer to the containment question.**

This run repeats the same format on `main` **after** PR #47, so `require_dest`
Supports now reach the resolver. It uses **Haiku**, not Sonnet, for all three
LLM seats — David's call per PR #48's fitness probe (0/144 parse-fail on
Haiku, cost-minimizing "probe FIT first" decision, Sonnet arm reserved for if
this comes back null-ish; see §6). **This is therefore the first clean read
of the punishment-conversion pipeline on the fixed engine — but it is not a
controlled A/B against run #1**: model, seeds, and (as it turns out,
dramatically) the LLM table's own coordination volume all differ too. §5
addresses this directly.

## 2. Format

| Knob | Value |
|---|---|
| Seats / turns / radius | 4 / 12 / 2 (`continental_sweep`, détente threshold 8) |
| Toggles | reciprocation ledger ON · campaign memory ON · retreats OFF · LLM timeout 300 s |
| Roster | 3 **Haiku** entrants (`claude-cli --model haiku`) + 1 `DishonestCooperator` house freerider |
| Concurrency | `FOEDUS_PARALLEL_SEATS_WORKERS=3` (all 3 LLM seats concurrent) — David's pre-seal spec amendment 2026-07-10, recorded in `campaign_plan.json`'s `parallel_seats` field; proven observationally-equivalent to sequential by PR #43 |
| Seat rotation | cyclic Latin square (§7.4); the freerider rotates like everyone else |
| Seeds | commit-reveal, SHA-256 sealed before / revealed after (§7.5) — commitment `786e2fc4…04ace` published before game 0 |
| Rating | OpenSkill (Plackett-Luce), one identity per entrant, conservative μ − 3σ |
| Games | **8** (two full rotation cycles) |
| Handles | Delta / Echo / Foxtrot (LLM entrants) · **Golf** (freerider house anchor) |

## 3. Primary question (pre-registered)

> Does the LLM table contain the freerider once its coordinated Supports
> actually reach the resolver?

**Standings (OpenSkill, conservative μ−3σ):**

| identity | mu | sigma | conservative (μ−3σ) | avg finishing rank | wins |
|---|---:|---:|---:|---:|---:|
| Echo | 26.46 | 7.23 | 4.78 | 2.375 | 1 |
| **Golf (freerider)** | 26.18 | 7.20 | **4.58** | 2.500 | 1 |
| Foxtrot | 23.56 | 7.11 | 2.24 | 2.375 | 2 |
| Delta | 23.31 | 7.12 | 1.97 | 2.500 | 2 |

*Avg finishing rank uses `foedus.scoring._compute_ranks` — the engine's own
standard-competition ranking, where tied final scores share a rank (e.g. game
0's Delta/Golf tie at 38 each both count as rank 1, not an arbitrary 1/2
split). See §8 to regenerate.*

**No — not decisively.** Golf still lands **2nd of 4** on the leaderboard,
0.20 conservative points behind the top LLM entrant (Echo) and ahead of two of
the three LLM entrants. Its per-game win-rate dropped (3/8 → 1/8, see §4), and
by average finishing rank it **ties Delta for worst** (2.500, vs. Echo/Foxtrot
tied at 2.375) — the table did not let it dominate, but it also did not fall
alone to the bottom of the standings. With σ ≈ 7.2 still large relative to the
≈2.8-point conservative-score spread across all four identities at n = 8
games, none of these differences are statistically decisive; treat the
leaderboard order as directional, not conclusive.

## 4. Outcome-level comparison vs. run #1

| metric | run #1 (Sonnet, buggy engine) | this run (Haiku, fixed engine) |
|---|---:|---:|
| freerider win-rate | 3/8 (37.5%) | 1/8 (12.5%) |
| freerider mean margin (vs LLM mean) | +2.62 | +0.83 |
| freerider OpenSkill conservative | 3.06 (2nd of 4) | 4.58 (2nd of 4) |
| freerider avg finishing rank | 2.500 (3rd of 4; only Delta worse) | 2.500 (tied Delta for worst) |
| parse-fail rate | 8.16% (47/576) | 1.04% (6/576) |
| match wall-clock | 15.36 h (115.2 m/game) | 5.62 h (42.2 m/game) |

Win-rate and mean margin moved in the "containment improved" direction.
OpenSkill conservative and average finishing rank did **not** — Golf is
statistically no less entrenched in 2nd place than it was in run #1. Wall-clock
dropped by more than the ~2.5× `WORKERS=3` design-doc measurement alone would
predict, consistent with Haiku's shorter per-call latency on top of the
concurrency win (not decomposed here — not needed for the containment
question).

## 5. Punishment-conversion pipeline (the S1 metric run #1 was built around)

Using the same coverage-guarded tool (`foedus_s1_autopsy.py`) against both
run dirs:

| | proposed | executed | paid | executed→paid |
|---|---:|---:|---:|---:|
| run #1 (Sonnet, buggy engine) | 32 | 39 | 1 | 2.6% |
| this run (Haiku, fixed engine) | 20 | 21 | 2 | 9.5% |

`executed` exceeding `proposed` is not an arithmetic error: a single declared
intent can back multiple executed order-actions (e.g. a Move *and* a Support
of it, or the same attack resubmitted on a later turn without a fresh
declared intent) — see run #1's `autopsy-s1.md` §0 for the exact per-event
counting rules; this run's own per-game breakdown (`autopsy-s1.json`) shows
both directions across the 8 games (e.g. g2: 3 proposed/2 executed; g7: 3
proposed/5 executed).

The conversion rate roughly tripled — but off a base of 1 vs. 2 "paid" events
total across 8 games each. This is **suggestive, not conclusive**: two data
points do not establish a rate, and "paid" is an outcome-level proxy (Golf's
public score dropping near an execution), not a per-combat resolution trace
(see run #1's `autopsy-s1.md` §0 for the full caveat — it applies unchanged
here).

**The confound that matters most:** LLM↔LLM coordinated Supports — the
mechanism the whole S1/S1.5 line of inquiry is about — collapsed from **79
total (9.875/game) in run #1 to 2 total (0.25/game) in this run.** Haiku's
"thin-but-real coordination" (PR #48's own characterization) means this table
barely attempted the coordinated-Support pattern S1.5 was concerned with in
the first place. The tripled conversion rate cannot be cleanly attributed to
"the fix now lets coordinated Supports land" when coordinated Supports
themselves were nearly absent — a weaker, model-driven explanation (Haiku
tables generate less overall order volume / less contested combat, so what
little lands is less contested) is equally consistent with this data and this
run cannot distinguish between them.

## 6. Verdict

**Headline: still NULL on decisive containment, with the primary mechanism
under-tested.** The freerider is not dethroned — it holds 2nd on the
leaderboard in both runs, essentially unchanged in OpenSkill terms. Two
outcome measures did move in the containment direction (win-rate, mean
margin) and the punishment-conversion rate roughly tripled, but every one of
those improvements is confounded by the model swap (Sonnet → Haiku) and, more
importantly, by a **~40× collapse in the LLM table's own coordination
volume** — the exact mechanism S1.5 flagged as bottlenecked by the engine
bug barely fired in this match, so this run cannot cleanly credit or
exonerate the `require_dest` fix on the containment question. What it
*does* establish cleanly: the fix itself works as designed (§7), the match
ran clean and fast (§4), and Haiku's low coordination rate is now a directly
measured, pre-registered fact rather than an inference from the 2-game
fitness probe.

**Recommendation: run the Sonnet arm.** The roadmap pre-registered this
contingency ("Sonnet arm only if null-ish") before the match — this result
qualifies. A Sonnet table on the fixed engine is the only way to test the
original S1.5 question (does coordinated punishment work once it reaches the
resolver?) with the coordination volume high enough for the punishment
pipeline to be meaningfully exercised. Not launched here — outside this
dispatch's 8-game cost cap; flagged for Nova/David to decide.

**Caveats.** n = 8 games, one map archetype, a single *scripted*
`DishonestCooperator` (fixed exploiter, not adaptive). σ ≈ 7.2 leaves the
whole leaderboard statistically close. "Paid" is an outcome-level score-drop
proxy, not a resolution trace (§5). This run and run #1 differ in model,
seeds, and (it turns out) coordination volume — it is a fresh, clean data
point on the fixed engine, not a controlled isolation of the engine fix's
effect.

## 7. Engine + seal integrity

- **Resolver invariant: HELD.** `foedus_verify_invariant.py --pairings 20`:
  1,872 per-turn one-unit-per-node checks across the 8 actual game seeds ×
  20 random heuristic pairings each, zero violations.
- **Seal: verified.** Commitment `786e2fc4421cc385ae9dfbef8181d4ee27bb2f0ce4a5bfb3238ead9ecff04ace`
  published before game 0 (confirmed `sweep.jsonl` was empty at seal time);
  `seed_manifest.revealed.json` reproduces it; `seeds_match_sweep=True`.
- **Coverage guardrails:** `foedus_canonical_scorecard.py` and
  `foedus_s1_autopsy.py` both ran clean (no `CoverageError`) against all 576
  decision records across 8 games / 24 decision-log files.
- **Parse-fail:** 6/576 (1.04%), all 3 entrants ≤ 3 fallbacks each.
- **Decisions:** 576 total — exactly matches the roadmap's pre-registered
  "~576 haiku calls" estimate.

## 8. Reproducing

All commands below assume cwd = repo root.

```sh
OUT=docs/research/2026-07-10-canonical-haiku-rerun/run

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

# scorecard + trajectory + parse-fail split + standings
PYTHONPATH=. python3 scripts/foedus_canonical_scorecard.py --out-dir "$OUT"

# independent OpenSkill recompute
PYTHONPATH=. python3 scripts/foedus_compute_ratings.py "$OUT/sweep.jsonl"

# punishment-conversion pipeline (this run and run #1, for the §5 comparison)
PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py --out-dir "$OUT"
PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py \
    --out-dir docs/research/2026-07-04-canonical-campaign-v1/run

# resolver invariant + seed-manifest check
PYTHONPATH=. python3 scripts/foedus_verify_invariant.py --out-dir "$OUT" --pairings 20

# avg finishing rank (§3/§4) -- engine's own _compute_ranks convention,
# ties share a rank; not emitted by any of the scripts above
PYTHONPATH=. python3 - <<PY
import json
from collections import defaultdict
from foedus.scoring import _compute_ranks
ranks_by = defaultdict(list)
for line in open("$OUT/sweep.jsonl"):
    r = json.loads(line)
    scores = {i: r["final_scores"][i] for i in range(4)}
    survivors = [p for p in range(4) if p not in set(r.get("eliminated") or [])]
    for seat, rank in _compute_ranks(scores, survivors, 4).items():
        ranks_by[r["agents"][seat]].append(rank)
for identity, ranks in ranks_by.items():
    print(f"{identity:<10} avg_rank={sum(ranks)/len(ranks):.3f}  ranks={ranks}")
PY
```
