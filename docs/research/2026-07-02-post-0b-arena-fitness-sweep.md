# Post-0a/0b Arena-Fitness Sweep (falsifiable re-test)

**Source:** 3×10,000-game + 1×10,000-game sweeps on commit `a721c14` (branch
`feature/M-foedus-arena-fitness-sweep`, based on `origin/main` @ `36c9248`,
which includes 0a (conflict preset, combat/supporter rewards, tiered
supplies), F5 (pacts), and F6 (intent/pact breach penalties + public
reputation)). All 19 heuristics, random pairings, 4p. Raw JSONL + rating
leaderboards available on request (not committed — see Reproducing below).

**Why:** the project's own pre-fix 5000-game sweep
(`2026-04-29-depth-and-balance.md`) found GreedyHold dominant, tier-1
heuristics statistically indistinguishable, 91% of games with zero
dislodgements, and betrayal mechanically decorative. A high-taste review
(Fable, `/home/david/janus/docs/superpowers/2026-07-02-foedus-fable-arena-assessment.md`)
flagged that the 0a/0b fixes were **never re-measured at scale** and
proposed exactly this re-test as the falsifiable "is this a real arena now"
check. This is that check.

## Methodology

Four sweep arms, 10,000 games each, all 19 heuristics (`ROSTER` in
`foedus/agents/heuristics/__init__.py`), random 4-seat pairings, seed 0
(same RNG stream ⇒ **identical matchups and maps across arms A/B**, since
pairing assignment depends only on `seed`/`roster`/`num_players`, not on
`map_radius`/penalty config — this makes A vs B a genuine paired
before/after comparison, not just two independent samples):

| Arm | Config | Purpose |
|---|---|---|
| **A** | `conflict_forcing_config`-equivalent: `map_radius=2`, `archetype=continental_sweep`, `max_turns=15`, F6 penalties **ON** (defaults: `intent_breach_penalty=1.0`, `pact_breach_penalty=2.0`) | Primary post-fix measurement |
| **B** | Same as A, F6 penalties **OFF** (`--intent-breach-penalty 0 --pact-breach-penalty 0`) | Isolates F6's causal effect (paired with A) |
| **C** | Same as A but `map_radius=3` (the baseline doc's own radius, current code) | "Default preset" comparison point — same code, old map size |
| **D** | Same as A but `--peace-threshold 0` (engine default, table-scaled) | Détente-rate measurement (A/B/C run with détente structurally disabled at `peace_threshold=99`, matching the baseline doc's own methodology) |

Two small, additive changes to `scripts/foedus_sim_sweep.py` were needed
(TDD, tests in `tests/test_sim_sweep_reputation_counters.py`):
`reputation_intent_breaches_per_player` / `reputation_pact_breaches_per_player`
JSONL fields (breach counts by **committer**, sourced from
`state.reputation` — the existing `betrayal_count_per_player` field is
keyed by **observer/victim** and can't answer "did X actually breach"), and
`--intent-breach-penalty` / `--pact-breach-penalty` CLI overrides (needed
for Arm B).

Reproducing:
```sh
PYTHONPATH=. python scripts/foedus_sim_sweep.py --num-games 10000 --max-turns 15 \
  --archetype continental_sweep --map-radius 2 --num-players 4 --workers 10 --seed 0 \
  --out arm_A.jsonl
# Arm B: add --intent-breach-penalty 0 --pact-breach-penalty 0
# Arm C: --map-radius 3 instead of 2
# Arm D: add --peace-threshold 0
PYTHONPATH=. python scripts/foedus_compute_ratings.py arm_A.jsonl
```
At the observed throughput (~1000-1500 games/s, 10 workers on a 12-core
box) each arm takes under 10 seconds — this sweep is cheap enough to re-run
on every future mechanics change.

## a. Combat: did the conflict preset + combat rewards produce real fighting?

**Yes, dramatically.**

| | Baseline (pre-fix, r3) | Arm A (r2, current) | Arm C (r3, current) |
|---|---|---|---|
| Games with ≥1 dislodgement | 9% | **38.7%** (95% CI 37.8–39.7%) | **44.3%** (95% CI 43.3–45.3%) |
| Mean dislodgements/game | — | 1.35 (CI 1.30–1.40) | 1.76 (CI 1.70–1.81) |
| Games with ≥1 elimination | 0.7% | **15.2%** (CI 14.5–15.9%) | 9.7% (CI 9.1–10.2%) |
| Support-order share of all orders | ~2.8% (SupportMove+SupportHold) | **14.0%** | 10.5% |
| Games tied for 1st place | 12.1% | **0.0%** | — |

Dislodgement rate is up **4-5×** over baseline, elimination rate up
**13-20×**, and cooperative Support orders up **~4-5×**. Note the
counterintuitive direction on map size: **Arm C (r3, the roomier map) shows
*more* dislodgement than Arm A (r2, the tight conflict preset)** — 44.3% vs
38.7% — though Arm A has the higher elimination rate (15.2% vs 9.7%). Read
together: the tighter r2 map produces fewer, more decisive fights (units
have less room to retreat/regroup after a first strike, echoing Fable's
"no-retreat elimination... collapses the midgame" point), while r3 produces
more frequent but less lethal skirmishing. Either way, **the 91%-zero-combat
degenerate state from the baseline sweep is gone** in both configurations —
this is not preset-radius-specific, it's a genuine effect of 0a/0b's
combat/supporter rewards and tiered supply values.

Exact-ties-for-1st collapsing from 12.1% to 0.0% is a side effect of
variable supply values (Bundle 5b, `high_value_supply_fraction=0.20`) —
scores no longer land on identical integer sums as often. Not something 3a
asked about directly, but it corroborates "games are more decisive now."

## b. Betrayal: do the deceptive heuristics actually breach and get penalized?

**Mixed — and the mixed result is the important finding.** 73.2% of games
(CI 72.4–74.1%) now have at least one committed breach (`state.reputation`
non-empty), vs baseline's "only 17.4% of games ever fire a
BetrayalObservation." But breach *volume* by heuristic (mean breaches
committed per game seated, Arm A, n=10,000):

| Heuristic | Breaches/game | Why |
|---|---|---|
| Sycophant | **22.51** | Designed liar: declares Hold, plays Greedy every turn |
| CoalitionBuilder | 20.50 | Declares GreedyHold-planned Move, then reassigns units to bloc-Support |
| Opportunist | 19.00 | Same pattern, tiered pinned/reactive Support targeting |
| LateCloser | 9.17 | Declares Greedy-planned Move, then redirects to avoid duplicate-targeting allies |
| TrustfulCooperator | 6.78 | Declares planned Move, reassigns to ally-Support |
| Cooperator | 4.84 | Same mechanism as TrustfulCooperator |
| OpportunisticBetrayer | 3.33 | **The heuristic F6 was explicitly designed to catch** |
| AntiLeader | 1.96 | — |
| DishonestCooperator | **0.00** | **The freerider exploit — never breaches, see below** |
| (all other 10 heuristics) | 0.00 | Never declare Intents, or declared Intent always matches submitted order |

**The mechanism:** every "helper" heuristic (Cooperator, TrustfulCooperator,
Opportunist, CoalitionBuilder, LateCloser) declares its own
GreedyHold/Greedy-planned Move as a public Intent in `choose_press`, then in
`choose_orders` may **reassign that same unit** to a `Support(...)` order
for an ally instead — a purely cooperative act. `press.py`'s intent
verification only compares "what you declared" against "what you actually
submitted" per unit; it has no notion of *why* the two diverge. A unit
redirected to support a friend registers identically to a unit redirected
to stab an enemy: both are `BetrayalObservation`/reputation-ledger events.
**F6's breach machinery cannot currently distinguish "I broke my word to
help an ally" from "I broke my word to betray someone."** This is worth
verifying by hand for one representative case, which we did: seed=1,
`OpportunisticBetrayer,Defensive,Defensive,Defensive` reliably produces 8
real breaches by the betrayer (confirmed via `state.reputation` directly);
by contrast `Cooperator`'s and `CoalitionBuilder`'s breach counts move in
lockstep with how aggressively their support-reassignment logic overrides
declared plans, not with any deceptive intent in the code.

**DishonestCooperator — the heuristic literally named after Fable's flagged
exploit, and the project's own documented `KNOWN EXPLOIT` in `resolve.py` —
never breaches at all.** It declares its planned GreedyHold Move as an
Intent and then *always plays exactly that Move* (never reciprocates
Support to anyone). Its dishonesty is about the ALLY *stance* and the
implicit promise of reciprocation, not about a specific declared Intent —
so there is nothing for `_verify_intents`/`_verify_pacts` to ever catch.
Confirmed directly: DishonestCooperator's mean score is **bit-for-bit
identical between Arm A (penalties on) and Arm B (penalties off)**
(49.585 in both, see §e) — the F6 machinery has literally zero purchase on
it.

## c. Détente rate — was it a degenerate attractor?

**No — it's rare, not degenerate.** Arms A/B/C ran with `peace_threshold=99`
(détente structurally disabled), matching the baseline doc's own
methodology. Arm D reran Arm A's exact config with `--peace-threshold 0`
(engine default, table-scaled to `min(4+num_players, max_turns-1) = 8` for
this config) to actually measure it — the baseline doc flagged this exact
gap ("Need a separate sweep with default détente settings") and it had
never been run.

**Result: 101/10,000 games (1.0%, 95% CI 0.8–1.2%) reach détente.** Not a
degenerate attractor (heuristics aren't optimizing for it, so this isn't
surprising), but not dead code either — it's reachable under pure
self-play roughly 1 game in 100. Whether that's "enough" is a design
question outside this sweep's scope, but the baseline's open question is
now answered with a number.

## d. Dominance + gradient: is GreedyHold still #1?

**No.** Post-fix leaderboard, conservative rating (`mu - 3·sigma`), Arm A
(r2) and Arm C (r3):

| Rank | Arm A (r2) | mu−3σ | Arm C (r3) | mu−3σ |
|---|---|---|---|---|
| 1 | **DishonestCooperator** | 34.96 | **DishonestCooperator** | 40.13 |
| 2 | ValueGreedy | 31.47 | Patron | 38.32 |
| 3 | TrustfulCooperator | 30.78 | ValueGreedy | 38.19 |
| 4 | Patron | 30.48 | Cooperator | 38.10 |
| 5 | **GreedyHold** | 30.30 | Bandwagon | 36.97 |
| 6 | Bandwagon | 30.15 | TitForTat | 36.33 |
| 7 | TitForTat | 30.08 | TrustfulCooperator | 35.76 |
| 8 | Cooperator | 26.68 | **GreedyHold** | 35.29 |
| ... | ... | ... | ... | ... |
| 19 | Sycophant | −1.75 | Sycophant | −13.88 |

GreedyHold drops from **rank 1 (pre-fix)** to **rank 5 (r2) / rank 8
(r3)** — genuinely dethroned, in both map configurations. But its
replacement at the top is **DishonestCooperator, the freerider exploit
heuristic itself** — the single highest-rated agent in both post-fix
configurations, by a clear margin in Arm C (40.13 vs runner-up Patron's
38.32) and a modest one in Arm A (34.96 vs ValueGreedy's 31.47). This is
the single most important sentence in this report: **fixing the
GreedyHold-dominance problem surfaced a worse problem the fixes don't
touch.**

**Is there now a real skill gradient?** Partially. The top 7 heuristics in
Arm A cluster within a ~5-point raw-mu band (35.1–40.1) — largely still
statistically compressed, and notably **GreedyHold, Bandwagon, and TitForTat
remain within 0.3 mu of each other**, reproducing the baseline's own
"tier-1 is a literal tie" finding (recommendation #1 in the baseline doc —
"collapse the top-3 tie" — is still unaddressed by 0a/0b). But that upper
cluster is now separated from a genuine floor by a **~20-36 point gap**
(mu−3σ spread top-to-bottom: 36.7 in Arm A, 54.0 in Arm C), and the floor
itself is now informative rather than flat: Sycophant's F6-driven collapse
to dead last (and *negative* mu−3σ in Arm C) is a real, mechanically-caused
outcome, not sampling noise. So: yes, more gradient than before, but it's
concentrated at the extremes (one dominant freerider, one heavily-punished
liar) rather than a smooth ranking across the middle.

(Note: this rank table and §e's raw-mean-score table below use different
statistics and needn't agree mid-pack — e.g. §e Arm A shows Cooperator's
raw mean, 42.04, above TrustfulCooperator's, 40.06, while this table's
OpenSkill conservative rating ranks TrustfulCooperator #3 above Cooperator's
#8. OpenSkill rewards *consistent* placement across opponents, not just
average score, so the two orderings diverging mid-pack is expected, not a
contradiction.)

## e. F6 effect: did penalizing intent-breaches rebalance dishonest vs honest cooperators?

**No — and it may be actively counterproductive.** Mean final score,
identical seeds/matchups (Arm A vs Arm B, so the delta is the isolated
causal effect of the penalty; 95% CIs shown). This isn't just seed-matched
sampling — it's an exact identity: no heuristic in the roster reads
`state.scores`, `state.reputation`, or the penalty config, and none of
elimination/détente/`is_terminal` depend on score, so arms A and B produce
bit-identical game trajectories that differ *only* in score bookkeeping.
Every row's Δ below equals `breaches/game × 1.0` (from §b) exactly, to the
third decimal:

| Heuristic | Penalties ON | Penalties OFF | Δ (OFF−ON) |
|---|---|---|---|
| DishonestCooperator | 49.585 [48.83, 50.34] | 49.585 [48.83, 50.34] | **+0.000** |
| OpportunisticBetrayer | 31.441 [30.78, 32.10] | 34.771 [34.13, 35.41] | +3.330 |
| Sycophant | 5.395 [5.08, 5.71] | 27.905 [27.40, 28.41] | **+22.510** |
| Cooperator | 42.036 [41.12, 42.95] | 46.879 [46.04, 47.72] | +4.843 |
| TrustfulCooperator | 40.056 [39.19, 40.93] | 46.832 [46.02, 47.65] | +6.776 |

Reading this against the brief's actual question ("rebalance dishonest vs
honest cooperators"):

- **F6 works exactly as intended against blatant, high-volume lying**
  (Sycophant: −22.5 points is a massive, decisive penalty — its entire
  score is now dominated by the breach fine).
- **F6 barely touches the purpose-built betrayer** (OpportunisticBetrayer:
  only −3.3, smaller in magnitude than what it does to two "honest"
  cooperators — see next point).
- **F6 penalizes the designed-honest cooperators (Cooperator −4.8,
  TrustfulCooperator −6.8) *more* than it penalizes OpportunisticBetrayer
  (−3.3).** This is the inverted-incentive finding from §b made concrete in
  score terms: cooperative unit-reassignment triggers the same penalty
  machinery as strategic betrayal, and because Cooperator/TrustfulCooperator
  attempt Support far more often over 15 turns than OpportunisticBetrayer's
  "at most one betrayal per turn" cap, they rack up *more* breach volume.
- **F6 has zero effect on the freerider exploit it was hoped to close**
  (DishonestCooperator: Δ=0.000, bit-identical). The gap between
  DishonestCooperator (49.585) and the honest cooperators it's designed to
  outcompete (Cooperator 42.036, TrustfulCooperator 40.056 — a **7.5-9.5
  point gap even with F6 fully engaged**) is essentially untouched by F6,
  matching Fable's own citation of the pre-existing `KNOWN EXPLOIT` comment
  in `resolve.py` (+10.7 to +12.0 in fixed-seat testing) — the exploit
  persists at a comparable magnitude in mixed-roster play too.

**Verdict on 3e: no, F6 as implemented does not cleanly rebalance dishonest
vs honest cooperators.** It correctly nukes one specific failure mode
(constant, high-frequency lying about Hold vs Move), but the mechanism it
uses — comparing declared Intent to submitted order per unit, with no
notion of *why* they diverge — can't distinguish "helping" from
"betraying," and is entirely blind to the freerider pattern (declare
truthfully, simply never reciprocate) that the project's own code already
flagged as the leading exploit.

## f. Verdict: does the arena now reward more than quiet GreedyHold expansion?

**Yes and no — the failure mode moved, it didn't disappear.**

**Yes:** GreedyHold is dethroned (rank 5-8, not rank 1), real combat happens
(38.7-44.3% of games vs 9% before), cooperative Support orders are ~4-5×
more common, betrayal has real mechanical teeth against the *specific* lying
pattern it targets (Sycophant is crushed), and détente is reachable (not
dead code, 1.0%).

**No:** the ladder's summit is now occupied by a heuristic (DishonestCooperator)
whose entire strategy is to *look* cooperative (ALLY stance, truthful
Move-intent declarations) while *never reciprocating* — and F6's
breach-detection is structurally incapable of seeing this, because nothing
about it is a broken commitment in the narrow "declared X, did Y" sense the
engine checks. Worse, the mechanism built to punish dishonesty currently
falls hardest on cooperative support-reassignment (Opportunist,
CoalitionBuilder: ~19-20 breaches/game) and on two heuristics explicitly
named "honest"/"trustful" cooperators — while barely touching the one
heuristic explicitly named "opportunistic betrayer."

If the fitness bar is "does quiet GreedyHold-style expansion still win by
default" — no, that specific failure mode from the baseline sweep is fixed.
If the fitness bar is "does the social/cooperation layer actually reward
honesty over freeriding" — no, not yet: the highest-value strategy in both
post-fix configurations is freeriding on the appearance of cooperation, and
the mechanism meant to prevent that doesn't detect it.

## Limitations & follow-up

1. **(Flagged in the brief, confirmed necessary.)** All 19 heuristics are
   fixed-logic and non-adaptive: none of them read `GameConfig` to change
   strategy, none use Pacts (F5) at all (`reputation_pact_breaches_per_player`
   is 0 for every heuristic in every arm — confirmed by the new test), and
   only a few use reputation/leverage defensively (as a *gate*, e.g. "don't
   support a freerider"), never offensively (no heuristic tries to *build*
   reputation as a strategic asset, or exploit an opponent's damaged
   reputation). This sweep **cannot** test Fable's actual top-line claim —
   "no press-blind heuristic ranks top-tier against press-using agents" —
   because there are no press-using agents in the roster to rank against.
   **Concrete follow-up: this needs LLM agents or new press-using
   heuristics** (e.g. a heuristic that actually negotiates Pacts, or one
   that strategically times reciprocation based on the public reputation
   ledger) before the "press beats press-blind" claim can be tested at all.

2. **(New, discovered by this sweep.)** F6's intent-verification is
   **unit-order-diff based with no notion of pro-social vs anti-social
   divergence.** Before investing further in press-savvy agents, this is
   worth fixing or at least explicitly scoping — otherwise any future
   agent that tries to be a *good, adaptive* cooperator (reassigning units
   to support allies opportunistically, same as `Cooperator` does today)
   will accumulate breach penalties for the act of cooperating. Candidate
   fixes worth a design pass: (a) don't penalize a broken Move-intent whose
   actual order was a `Support` *of an ally in good standing* (the
   divergence helped someone, it didn't hurt anyone); (b) let agents mark
   an Intent as "soft" (informational, revocable) vs "hard" (a real
   promise) so support-heavy heuristics aren't forced to choose between
   declaring nothing and being penalized for helping; (c) separately track
   "intent broken to help a third party" vs "intent broken to attack" in
   the reputation ledger so observers (and future LLM negotiators) can
   tell the difference from the public record.

3. **The freerider exploit (DishonestCooperator) is untouched and is now
   the #1-rated strategy in both tested configurations.** This predates
   0a/0b (it's the project's own documented `KNOWN EXPLOIT`) but this sweep
   is the first confirmation that it survives F6 fully intact and is the
   single best-performing heuristic post-fix. Closing it needs a mechanism
   that penalizes *never* reciprocating a declared cooperative stance, not
   just breaking a specific declared order — e.g. gate the alliance-capture
   bonus (or add a separate reputation signal) on a rolling reciprocation
   ratio, not just a same-turn AidSpend.

4. This sweep did not attempt to replicate the baseline's lead-change /
   supply-growth-rate analysis (baseline §"How wide is the gap?") — out of
   scope for the brief's falsifiable-test ask list (a-f) and not needed to
   answer it; flagging so a future reader doesn't assume it was checked and
   found clean.
