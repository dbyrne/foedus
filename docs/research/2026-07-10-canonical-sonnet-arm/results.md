# Sonnet arm (4 games, fixed engine) — results + honest verdict

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

## 1. Why this run exists

The Haiku re-run (`docs/research/2026-07-10-canonical-haiku-rerun/`, PR #49)
answered "does the `require_dest` fix work" cleanly (yes) but left the
**primary S1.5 question open**: does coordinated punishment convert once it
reaches the resolver? Haiku's table barely attempted cross-player
coordination (2 LLM↔LLM supports total across 8 games, vs run #1's 79), so
the punishment pipeline was almost never exercised. This is the
pre-registered contingency arm: a **Sonnet** table on the same fixed engine,
where run #1 already showed coordination volume is high (~9.9 cross-player
supports/game). David's call: **4 games**, not 8 — Sonnet's coordination
volume means 4 games exercise the punishment pipeline roughly as much as the
entire 8-game Haiku run, at half the cost.

## 2. Format

| Knob | Value |
|---|---|
| Seats / turns / radius | 4 / 12 / 2 (`continental_sweep`, détente threshold 8) |
| Toggles | reciprocation ledger ON · campaign memory ON · retreats OFF · LLM timeout 300 s |
| Roster | 3 **Sonnet** entrants (`claude-cli --model sonnet`) + 1 `DishonestCooperator` house freerider |
| Concurrency | `FOEDUS_PARALLEL_SEATS_WORKERS=3` (all 3 LLM seats concurrent), recorded in `campaign_plan.json`'s `parallel_seats` field (`enabled: true, workers: 3`) |
| Seat rotation | cyclic Latin square (§7.4); the freerider rotates like everyone else |
| Seeds | commit-reveal, SHA-256 sealed before / revealed after (§7.5) — commitment `d4f9a014bc9f56a497263c4bd00084f996a8a2b3ecd83e3f79273b7fe9b7bff8` published before game 0 |
| Rating | OpenSkill (Plackett-Luce), one identity per entrant, conservative μ − 3σ |
| Games | **4** |
| Handles | Delta / Echo / Foxtrot (LLM entrants) · **Golf** (freerider house anchor) |

## 3. Primary question (pre-registered)

> With a high-coordination (Sonnet) table on the fixed engine, does
> coordinated punishment convert, and does the table contain the freerider?

**Standings (OpenSkill, conservative μ−3σ):**

| identity | mu | sigma | conservative (μ−3σ) | avg finishing rank | wins |
|---|---:|---:|---:|---:|---:|
| Foxtrot | 34.12 | 7.95 | **10.29** | 1.250 | 3 |
| Delta | 25.46 | 7.60 | 2.67 | 2.500 | 0 |
| Echo | 23.26 | 7.69 | 0.21 | 2.250 | 1 |
| **Golf (freerider)** | 17.31 | 7.60 | **-5.48** | **3.750** | 0 |

*Avg finishing rank uses `foedus.scoring._compute_ranks` — ties share a rank.
See §8 to regenerate.*

**Containment: yes, decisively. Conversion: not established** — see §5-§6
for why the second half of the question is still open. Golf finishes **last
of 4** on the leaderboard, 5.69 conservative points below the next-lowest
entrant (Echo) and 15.77 below the top-rated Foxtrot. It won **0 of 4**
games, its mean margin against the LLM average is **-13.25**, and it held
the **strictly lowest raw final score in every one of the four games**
(`sweep.jsonl` final_scores — g0: Golf 23 of {27,37,34,23}; g1: Golf 20 of
{20,31,35,42}; g2: Golf 21 of {47,21,32,32}; g3: Golf 23 of {28,38,23,37}).
Its average finishing rank (3.750) is the worst of any identity in any of
the three runs to date (run #1: 2.500, 3rd of 4; Haiku re-run: 2.500, tied
for worst). This is a **qualitatively different result** from both prior
runs, where Golf held 2nd of 4 on the leaderboard.

**Two of the four games ended in an actual elimination, not just a scoring
loss — worth stating plainly rather than leaving implicit in the
standings.** In **game 2, Golf was eliminated outright** (`sweep.jsonl`
`eliminated: [1]`), around turns 8-9 (`autopsy-s1.json`'s
`golf_income_drop_turns: [8, 9]`, `paid_execution_turns: [7, 8]`) — the same
turns as this run's only two "paid" punishment events (§5). This is the
single most decisive containment event in the corpus: the table didn't just
out-score the freerider, it removed it from the board. In **game 3, Echo**
(an LLM entrant) **was eliminated instead** (`eliminated: [0]`, around turn
10 — Echo's decision log stops at turn 10 orders, 22 entries vs. the other
seats' 24). This is why Golf's game-3 rank is 3rd rather than 4th: Golf's
raw score there (23) was still *below* Echo's (28), but
`foedus.scoring._compute_ranks` gives eliminated players the shared worst
rank regardless of score, so the survivor (Golf) automatically outranks the
eliminated player (Echo) — a real engine convention, not a scoring error,
but it means "Golf placed 3rd, not last, in game 3" reflects survival, not
better play, and should not be read as a game where the table went easy on
the freerider.

## 4. Outcome-level comparison — three-way

| metric | run #1 (Sonnet, buggy engine) | Haiku re-run (fixed engine) | **Sonnet arm (fixed engine)** |
|---|---:|---:|---:|
| games | 8 | 8 | 4 |
| freerider win-rate | 3/8 (37.5%) | 1/8 (12.5%) | **0/4 (0%)** |
| freerider mean margin (vs LLM mean) | +2.62 | +0.83 | **-13.25** |
| freerider OpenSkill conservative | 3.06 (2nd of 4) | 4.58 (2nd of 4) | **-5.48 (4th of 4, last)** |
| freerider avg finishing rank | 2.500 (3rd of 4) | 2.500 (tied-worst) | **3.750 (worst, by a clear margin)** |
| LLM↔LLM cross-player supports/game | 9.88 | 0.25 | **7.75** |
| parse-fail rate | 8.16% (47/576) | 1.04% (6/576) | 1.40% (4/286) |
| match wall-clock | 15.36 h (115.2 m/game) | 5.62 h (42.2 m/game) | 3.00 h (45.0 m/game) |

Coordination volume is back to run #1's range (7.75 vs 9.88 supports/game —
both far above Haiku's 0.25), confirming David's pre-run expectation that a
Sonnet table would actually exercise the coordinated-punishment mechanism.
Every containment metric moved sharply in the "table contains the freerider"
direction. The OpenSkill gap is uneven, though: Golf trails Foxtrot by 2.2σ
and Delta by 1.1σ, but only 0.8σ behind Echo — at n = 4 games, σ ≈ 7.6–8.0
has barely shrunk from the rating system's prior, so "Golf vs. Echo" is not
statistically separated even though "Golf vs. Foxtrot" clearly is. The
**raw-score record is unambiguous regardless of σ or rank convention**: Golf
won 0 of 4 games and held the strictly lowest final score of the four
identities in all four games (§3) — a literal fact about the score sheets,
not a modeled inference. Its *rank* record (3.750 avg) is one notch better
than that in game 3 only because of the elimination-rank convention
described in §3, not because it scored better there.

Per-game trajectory (`foedus_canonical_scorecard.py`), 12-turn games,
`continental_sweep` map:

| game | freerider seat | margin | subsidy | coalition | hostility→freerider | Golf rank | eliminated |
|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 3 | -9.7 | 4 | 0 | 0.25 | 4th | — |
| 1 | 0 | -16.0 | 0 | 12 | 0.32 | 4th | — |
| 2 | 1 | -16.0 | 0 | 18 | 0.24 | 4th | **Golf** (~turn 8-9) |
| 3 | 2 | -11.3 | 0 | 1 | 0.23 | 3rd | Echo (~turn 10) |

First-half vs second-half (does the table learn to punish?): subsidy to the
freerider dropped (2.0 → 0.0/game) and coalition activity rose (6.0 → 9.5
supports/game) — both in the "learning to punish" direction. But freerider
margin worsened (-12.8 → -13.7) partly because game 2's elimination pulls
the second half down, and **hostility→freerider moved the wrong way**
(0.287 → 0.232, `foedus_canonical_scorecard.py`-verified) — the one
first-half/second-half signal that does *not* support a "the table is
learning to target Golf more" story. Golf lost every game it played; its
one better-than-4th finish (game 3) is the elimination-convention artifact
described in §3, not a game where it played its way to 3rd.

## 5. Punishment-conversion pipeline (the S1 metric this arm exists to test)

Using the same coverage-guarded tool (`foedus_s1_autopsy.py`) against all
three run dirs:

| | proposed | executed | paid | executed→paid |
|---|---:|---:|---:|---:|
| run #1 (Sonnet, buggy engine) | 32 | 39 | 1 | 2.6% |
| Haiku re-run (fixed engine) | 20 | 21 | 2 | 9.5% |
| **Sonnet arm (fixed engine)** | 5 | 9 | 2 | **22.2%** |

`executed` exceeding `proposed` is not an arithmetic error: a single
declared intent can back multiple executed order-actions (e.g. a Move *and*
a Support of it) — see run #1's `autopsy-s1.md` §0 for the exact per-event
counting rules; this run's own per-game breakdown (`autopsy-s1.json`) shows
this directly in game 2 (3 proposed → 7 executed), which is also the game
where Golf was eliminated (§3-§4) — its `paid_execution_turns: [7, 8]` are
the coordinated attacks that ended Golf's game.

The conversion rate is highest here, and the three runs now form a
monotonic-looking sequence (2.6% → 9.5% → 22.2%) as engine-fix + coordination
volume both move in the "punishment lands" direction. **Treat this as
suggestive, not conclusive**: the "paid" count is 1, 2, and 2 events
respectively — the absolute base rate is still tiny, so a single game's
outcome can swing the rate by double digits. This run does not, by itself,
establish a real dose-response relationship; it is one more data point
consistent with one.

**Pin-Support usage** (`Support(..., require_dest=<node>)` — the exact order
shape PR #47 made reach the resolver), counted directly from each run's
`decisions_game*_seat*.jsonl` parsed-order records:

| | total Support orders parsed | pinned (require_dest set) | pins/game |
|---|---:|---:|---:|
| run #1 (buggy engine, pre-fix) | 413 | **0** | 0.0 |
| Haiku re-run (fixed engine) | 185 | 40 | 5.0 |
| **Sonnet arm (fixed engine)** | 233 | 32 | **8.0** |

Run #1 shows **zero** pinned Supports in its own decision logs — direct,
independent confirmation of S1.5's finding that the pre-fix parser never let
a pin survive into a parsed order at all (not merely "the resolver dropped
it" — the parser itself coerced it away before logging). Both post-fix runs
show pins reaching the parsed-order stage in real volume, and the
higher-coordination Sonnet table uses them at a higher per-game rate (8.0 vs
5.0) — consistent with Sonnet both coordinating more overall and reaching
for the more expressive pin form more often when it does.

## 6. The confound this run does NOT resolve

**Two of the four games (g0, g3) show *zero* punishment-pipeline activity**
(proposed = executed = paid = 0) — no coordinated attack-backing Support was
even declared against Golf — **and Golf still finished last or
second-to-last in both of them** (rank 4 in g0, rank 3 in g3). Golf's
containment in this run cannot be cleanly attributed to the specific
coordinated-punishment mechanism S1.5 is about: in half the games, Golf lost
badly with the punishment pipeline never firing at all. Game 3 makes this
especially concrete: the game's one elimination was **Echo**, an LLM
entrant, not Golf (§3) — a table dynamic entirely unrelated to punishing the
freerider, in the same game Golf happens to record its best (3rd-place,
convention-driven) finish of the run. The more parsimonious read is that a
**strong, generally-coordinating LLM table** (high overall Support volume,
active pact/coalition play — see §4's coalition trajectory) outperforms a
scripted `DishonestCooperator` on both the mechanism this study targets and
on general play quality, and this run cannot cleanly separate the two.

A second, related confound: **Foxtrot individually dominated** (3 of 4 wins,
conservative score 10.29 — more than 7 points clear of the next entrant).
Golf's last-place finish is also consistent with "one entrant played
excellently and pushed everyone else down," including Golf, largely
independent of coordinated punishment specifically. With n = 4 games and one
identity this dominant, this run cannot distinguish "the table coordinates
to punish the freerider" from "one strong player happened to also beat the
freerider" — both are consistent with the same standings.

## 7. Verdict

**Headline: decisive containment, mechanism attribution still open.** Golf
is unambiguously worse off at this table than in either prior run — last
place, 0 wins, largest negative margin of the three runs, and (per §4) a
clear rating gap from the top two entrants though not from Echo. This is the
strongest containment signal collected so far and is consistent with the
pre-run hypothesis that a high-coordination table would better exercise the
punishment pipeline. The punishment-conversion rate (22.2%) is also the
highest of the three runs, continuing a monotonic-looking trend.

**But §6's caveat is load-bearing, not a footnote.** Half this run's games
show Golf losing badly with the S1 punishment mechanism completely inactive,
and one entrant's individual dominance is a live alternative explanation for
the standings. This run demonstrates that **a Sonnet table on the fixed
engine reliably contains this freerider** — the practical, table-level
question — but it does **not** cleanly demonstrate that the specific
coordinated-Support-punishment mechanism is *why*, as distinct from general
table strength and coordination. Answering that would need either more games
(to get enough "paid" events to analyze independently of overall table
quality) or a design that varies coordination while holding table skill
fixed — outside this dispatch's 4-game cost cap.

**Caveats.** n = 4 games (half of both baselines — less statistical power
even though the effect size here is larger), one map archetype
(`continental_sweep`), a single *scripted* `DishonestCooperator` (fixed
exploiter, not adaptive), seeds differ from both prior runs. σ ≈ 7.6–8.0 is
still large in absolute terms and has barely moved from OpenSkill's prior at
n = 4 games: Golf's rating gap is a clear 2.2σ from the top-rated Foxtrot and
a marginal 1.1σ from Delta, but only 0.8σ from Echo — the rating system
itself does **not** call this a decisive separation from the full field, only
from the strongest player. The *outcome* record (0 wins, worst rank in 3 of
4 games, largest negative margin of the three runs) is the stronger and
less-model-dependent evidence for containment here. "Paid" remains an
outcome-level score-drop proxy, not a per-combat resolution trace (see run
#1's `autopsy-s1.md` §0 for the full definition). One entrant's (Foxtrot's)
individual dominance is a live confound for the containment result (§6).

## 8. Engine + seal integrity

- **Resolver invariant: HELD.** `foedus_verify_invariant.py --pairings 20`:
  916 per-turn one-unit-per-node checks across the 4 actual game seeds × 20
  random heuristic pairings each, zero violations.
- **Seal: verified.** Commitment
  `d4f9a014bc9f56a497263c4bd00084f996a8a2b3ecd83e3f79273b7fe9b7bff8` published
  before game 0; `seed_manifest.revealed.json` reproduces it via
  `campaign.verify()`.
- **Coverage guardrails:** `foedus_canonical_scorecard.py` and
  `foedus_s1_autopsy.py` both ran clean (no `CoverageError`) against all 286
  decision records across 4 games / 12 decision-log files.
- **Parse-fail:** 4/286 (1.40%) — Delta 0/96, Echo 2/94, Foxtrot 2/96, all
  well within the fitness-probe range.
- **Decisions:** 286 total (pre-registered estimate: ~288 = 4×3×12×2); the
  2-decision shortfall is exactly Echo's 96→94 count (§3's game-3
  elimination around turn 10 cut off its final negotiation+orders pair).
- **Resume:** not needed — `run_summary.json.resumed = false`, the match
  completed in a single `launch.sh` leg (rc=0). `timing.log`'s wall-clock
  (3h1m) includes `launch.sh`'s one-time `uv` environment setup;
  `run_summary.json`'s `match_wall_clock_s` (3.00h, §4) measures just the
  game loop — both are correct, they measure different spans. A guarded
  `@reboot` autoresume was installed before launch and dry-fire-tested
  against the live run, but never actually invoked; removed post-completion.

## 9. Reproducing

All commands below assume cwd = repo root.

```sh
OUT=docs/research/2026-07-10-canonical-sonnet-arm/run

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

# punishment-conversion pipeline (three-way §5 comparison)
PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py --out-dir "$OUT"
PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py \
    --out-dir docs/research/2026-07-04-canonical-campaign-v1/run
PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py \
    --out-dir docs/research/2026-07-10-canonical-haiku-rerun/run

# pin-Support usage (§5) -- not emitted by any script above
for d in docs/research/2026-07-04-canonical-campaign-v1/run \
         docs/research/2026-07-10-canonical-haiku-rerun/run \
         docs/research/2026-07-10-canonical-sonnet-arm/run; do
  echo "$d"
  grep -oh 'Support(target=[0-9]*, require_dest=[A-Za-z0-9]*)' "$d"/decisions_game*_seat*.jsonl | wc -l
  grep -oh 'Support(target=[0-9]*, require_dest=[0-9]\+)' "$d"/decisions_game*_seat*.jsonl | wc -l
done

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
