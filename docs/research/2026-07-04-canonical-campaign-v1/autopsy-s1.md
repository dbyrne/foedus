# S1 — Corpus autopsy of canonical run #1 (pre-registering run #2's arm)

**Status:** analysis-only, read-only over the sealed run. Zero new games played.
**Input:** `run/` — the canonical 8-game Ruleset-v1 match (`sweep.jsonl`, 8 rows;
`preflight/live-resume-2026-07-05/**` is a separate resume-test and is excluded
throughout). `results.md` / `scorecard.json` are the published top-line
scorecard this autopsy extends, not replaces.
**Tooling:** `foedus/eval/punishment_metrics.py` (tested, `tests/test_punishment_metrics.py`)
+ `scripts/foedus_s1_autopsy.py` (thin CLI + integration test
`tests/test_s1_autopsy_script.py`). Regenerate every number below with:

```sh
PYTHONPATH=. python3 scripts/foedus_s1_autopsy.py \
    --out-dir docs/research/2026-07-04-canonical-campaign-v1/run \
    --scorecard docs/research/2026-07-04-canonical-campaign-v1/scorecard.json
```

## 0. What "proposed / executed / paid" mean here (read before the numbers)

The campaign's press is **structured JSON**, not free-text chat (no
`chat_drafts` were used) — so "proposing to punish Golf" has to be
operationalized from `press.stance`, `press.intents`, and `pacts.propose`,
each already emitted per decision in `decisions_game{g}_seat{s}.jsonl`:

- **PROPOSED** — any of: a declared attack-move **intent** (a `Move` whose
  `dest` is a node the declaring seat's own fogged view shows a Golf unit
  occupying at that moment); a declared **Support** intent whose target unit
  is *any* seat's declared attack-move that same turn (self- or cross-seat);
  or a **pact proposal** to a non-Golf counterparty containing an attack-move
  term (flagged `coordinated=True` when the same proposal's terms also carry
  a matching Support term — a genuine two-party joint commitment).
  A bare **hostile stance** toward Golf is reported separately as *sentiment*,
  not counted as a proposal — a stance label is cheap talk, not a concrete
  coordination act (see §2.3 for why that distinction matters empirically).
- **EXECUTED** — the orders-phase analogue: a submitted `Move` onto a node the
  acting seat's own view shows Golf occupying, or a submitted `Support` whose
  target is *any* seat's executed attack-move that turn. This is what was
  actually **sent to the engine**, not necessarily what the engine's
  geometry/strength check let land — see the limitation in §4.
- **PAID** — Golf's own per-turn income, read from the public, unfogged
  `Scores: {...}` dict every negotiate prompt carries, **dropped** within 1–2
  turns of an execution. This income is **not** literally "owned-center
  count" — per `foedus/resolve.py`, a turn's score delta is supply value net
  of upkeep tax, plus a one-off alliance bonus and a one-off
  `combat_reward` for whoever dislodges someone that turn (none of these
  knobs are overridden in `campaign_plan.json`, so all are live at their
  defaults). A drop is therefore *consistent with* a lost center but not
  logically equivalent to one from the Scores dict alone — the corpus does
  not retain a turn-by-turn resolution/dislodge log (by design — see
  `CLAUDE.md`'s wire-protocol note), so in general "paid" is an
  **outcome-level proxy**, not ground truth. Where the corpus lets it be
  checked directly (the MAP block's `[node-mark:owner]` marks — see §1.2),
  this autopsy does so and says so explicitly; elsewhere, treat "paid" as
  "Golf's standing moved in the right direction near an attack," not as a
  confirmed capture. See §4 for a case where the proxy and direct evidence
  would plausibly disagree.

Node occupancy is judged from the **acting seat's own fogged snapshot** at
decision time (not a merged all-seeing view) — a seat can only deliberately
target what it can see. Unit ids are global, so cross-seat Support→Move
linkage (a genuine multi-party attack) is exact, not an approximation.

## 1. Headline counts

| | proposed | executed | paid |
|---|---|---|---|
| **total (8 games)** | **32** | **39** | **1** |

**39 order-actions (Moves and Supports, combined) were submitted in service of
an attack on Golf across the campaign, spread over 23 distinct game-turns in
6 of 8 games — and exactly one of those attack-turns produced an observable
income drop.** That single conversion, 1-of-23 attack-turns (1-of-8 engaged
games; 1-of-39 individual order-actions if counted at that finer grain), is
the single most load-bearing number in this autopsy — read whichever
denominator you prefer, the rate is in the low single digits.

### 1.1 Per game

| game | Golf@ | proposed | executed | paid | income-drop turn(s) |
|---|---|---|---|---|---|
| g0 | seat3 | 4 | 9 | 0 | — |
| g1 | seat0 | 9 | 6 | 0 | — |
| g2 | seat1 | **0** | **0** | 0 | — |
| g3 | seat2 | **0** | **0** | 0 | — |
| g4 | seat3 | 7 | 7 | **1** | turn 8 |
| g5 | seat0 | 2 | 6 | 0 | — |
| g6 | seat1 | 2 | 4 | 0 | — |
| g7 | seat2 | 8 | 7 | 0 | — |

Six of eight games show genuine, repeated attempts to punish Golf (proposed
**and** executed > 0); two show none at all. **Executed ≥ proposed in every
game but g1 and g7**, and totals across the campaign run executed(39) >
proposed(32) — attacks are being *launched* more often than they are
formally *pre-declared*. This isn't just an aggregate-count coincidence: of
the **17 declared attack-move intents** in the whole corpus, **all 17 (100%)**
were followed by that exact same (seat, turn, unit) submitting a matching
attack-move order in that turn's orders phase — a direct per-declaration
link, not an inference from totals. So the shortfall is not "the table talks
about punishing Golf and then chickens out at the orders phase" in any
sense — that rules out the literal reading of the Commitment-arm trigger (see
§3).

### 1.2 Case study — the one payoff (g4, turn 7)

Foxtrot (seat2) attacked the same Golf unit (`u0`) at node 11 on turns 3, 4
and 7 (`decisions_game4_seat2.jsonl`), a consistent 2-vs-1 each time: `u2`
Move(dest=11) + `u6` Support(target=2, require_dest=11). Golf's public
`Scores` income (visible in every seat's negotiate prompt, unfogged) for
seat3 across turns 0–11: `0,1,3,5,8,11,14,18,21,24,27,30` → per-turn deltas
`1,2,2,3,3,3,4,3,3,3,3` (turns 1-11) — income steps to 3/turn (turns 4-6), up
to 4/turn (turn 7), then drops back to and holds at 3/turn from turn 8
onward.

This is the one place in the corpus where the score-delta proxy (§0) can be
checked directly against the MAP block's `[node-mark:owner]` marks, which
this seat's own prompt carries every turn regardless of phase: at turns 5 and
6, node 11 reads `11$1:3` (owned by seat3 = Golf); by turn 8 it reads
`11$1:2` (owned by seat2 = Foxtrot) — confirmed again at turn 11, where
Foxtrot's own `VISIBLE UNITS` block shows `u2 at node 11 (YOURS)`. Golf
walked `u0` into node 11 and completed a walk-in capture around turn 6 (the
turn-7 income spike to 4), and Foxtrot's turn-7 attack **instantly
dislodged it that same turn**, converting node 11 to Foxtrot's ownership —
which is exactly why Golf's income reverts to 3 entering turn 8. This is
independent, direct ownership evidence, not just an inferred score-delta
coincidence, and it is the one instance in this corpus where "paid" is
fully confirmed rather than merely proxied. Final margin for g4 was still
only **+1.0** (Golf) — a genuine but marginal containment, not a rout.

(At turn 11 Foxtrot also attacks a *different* Golf unit, `u11`, that has
since appeared at node 6 — an unsupported single Move, not a continuation of
the node-11 pattern; it is not part of the payoff above.)

### 1.3 Case study — a formal pact broken by infrastructure, not resolve (g1)

g1 is the richest engagement in the corpus (proposed=9, executed=6, and the
only two **coordinated** two-party attack-pact *proposals* in the whole
campaign — a third proposal exists, g7 turn 7, but its terms lack a matching
Support and so is not flagged `coordinated`; "coordinated" here describes the
proposal's terms, not whether the counterparty went on to accept it, which
this classifier does not check): at turn 6,
Delta (seat1) proposes to Echo (seat2) — Delta's u5 Move(dest=8), Echo's u2
Support(target=5, require_dest=8); at turn 8, Foxtrot (seat3) proposes to Echo
— Foxtrot's u0 Move(dest=4), Echo's u2 Support(target=0, require_dest=4). Both
proposals are `coordinated=True` (a real joint commitment, not a solo
declaration) and both movers do execute their half of the attack that same
turn. But Echo's turn-8 **orders-phase call itself timed out**
(`decisions_game1_seat2.jsonl`, turn 8: `raw_response` =
`"<client error: RuntimeError('claude -p timed out after 300.0s')>"`) — the
promised Support never reached the engine; the fallback silently substituted
for it. Foxtrot's Move landed **alone**, at base strength 1 against Golf's
unsupported base hold-strength of 1 (Golf's scripted `DishonestCooperator`
never self-supports — `foedus/agents/heuristics/dishonest_cooperator.py`
delegates orders to plain `GreedyHold`, which never issues `Support`). An
unsupported attacker facing a static defender of equal strength fails to
dislodge per `foedus/resolve.py`'s move-resolution rule (the attacker-vs-
static-defender branch in `_resolve_moves`, not the mutual-swap `_resolve_h2h`
path — the two are distinct code paths for a reason worth citing correctly).
No income drop is
recorded for g1 (`golf_income_drop_turns: []`), and Golf **won** g1 outright
(margin +16.0, the largest of the campaign). Coordination was proposed and
half-executed; the campaign's own ~8.2% overall parse/timeout-fail rate
across both phases (published in `results.md` §7.4) is enough, on its own, to
break a two-party attack that needed both halves to land.

### 1.4 Case study — a seemingly clean 2-vs-1 that still didn't pay (g5)

Foxtrot (seat3) in g5 reasons through the combat math explicitly and
correctly *twice*, turns 9 and 11 (`decisions_game5_seat3.jsonl`): "*Node 6
… held by Golf's u9 with no adjacent Golf support … I get strength 2 vs. the
lone defender's strength 1, dislodging u9*" — and submits exactly that
(`Move(dest=6)` + `Support(target=0, require_dest=6)`) both times. Neither
other LLM seat supported Golf's u9 that turn (checked directly against both
other seats' turn-9 orders). Yet Golf's u9 is *still* shown occupying node 6
in Foxtrot's own turn-11 snapshot — the turn-9 attack did not dislodge it, for
a reason this corpus cannot pin down (no resolution/dislodge log is
archived; see §0 and §4). g5's income-drop list is empty for the whole game,
and Golf won it (margin +15.3, second-largest of the campaign). This is the
sharpest illustration in the corpus that *even attacks that look
mechanically sound to the model executing them* are not converting at
anywhere near the rate a naive strength count would predict.

### 1.5 Case study — hostile in words, silent in nodes (g2, g3)

The two zero-engagement games are **not** a fog artifact: Golf's units were
directly visible to at least one LLM seat for 6–9 consecutive turns in both
games (checked against every seat's own `VISIBLE UNITS` block, not a merged
view) — g2 seat0 sees Golf's unit at node 15 turns 3–11 and seat2 sees it at
node 16 turns 1–11; g3 seat1 and seat3 see Golf's units at nodes 14 and 6 from
turn 3 or 6 onward. Golf was in plain sight for most of both games and was
never once targeted by a declared or submitted attack. g2 in particular
carries the **highest hostile-stance fraction in the campaign (0.576)** —
more than half of all stance declarations toward Golf that game were HOSTILE
— alongside **zero** concrete proposals or executions. Sentiment did not
convert to action even once.

## 2. Mechanism decomposition

### 2.1 First-order (subsidy) and second-order (hostility) — reusing the published trend

Reused verbatim from `results.md` §7.2 / `scorecard.json` (not recomputed —
same source, same numbers, cited here for the decomposition):

| signal | front half (g0–3) | back half (g4–7) | moved |
|---|---|---|---|
| subsidy (LLM Supports aimed at Golf) / game | 0.75 | 0.00 | ↓ — right way |
| coalition (LLM↔LLM supports) / game | 6.0 | 13.75 | ↑ — right way |
| hostility → Golf (fraction of stance obs.) | 0.364 | 0.394 | ↑ +0.03 — flat |
| Golf margin | −0.34 | +5.58 | ↑ — wrong way |

First-order withdrawal (stop feeding Golf) worked cleanly; second-order
suspicion (declared hostility) barely moved.

### 2.2 Structural-subsidy test — coalition entanglement vs. resistance to Golf

The roadmap's literal hypothesis — more honest↔honest mutual-support
entanglement mechanically **crowds out** attacks on Golf (fewer honest units
free to contest its frontier) — tested as `pearson_r(coalition_per_game,
executed_attacks_per_game)` across the 8 games:

```
coalition (LLM<->LLM supports): [0, 12, 4, 8, 11, 15, 25, 4]
resistance (executed attacks vs Golf): [9, 6, 0, 0, 7, 6, 4, 7]
pearson r: -0.10
```

**No meaningful correlation on the literal channel** (troop occupation): high
and low coalition games both show 0–9 executed attacks; n=8 has essentially no
power to detect anything short of a large effect here, and this one is not
large. **The literal "fewer units free to attack" mechanism is not supported
by this corpus.**

But the same coalition metric correlates strongly with the **outcome** Golf
actually cares about:

```
r(coalition, Golf margin)   = +0.77   (more coalition -> Golf does BETTER)
r(coalition, subsidy)       = -0.53   (already known: coalition rises as subsidy falls)
r(hostility, executed)      = -0.59   (more declared hostility -> FEWER executed attacks)
r(hostility, proposed)      = +0.01   (declared hostility ~uncorrelated with concrete proposals)
```

Read together: coalition-building does **not** measurably reduce the raw
volume of attacks on Golf, but it strongly tracks with Golf ending up
*better off* — and declared hostility toward Golf is essentially decoupled
from (if anything, mildly anti-correlated with) actually attacking it (g0:
0% hostile stance, 9 executed attacks; g2: 58% hostile stance, 0 executed
attacks). The likely channel is not territorial denial but **commitment
lock-in**: publicly declared intents/pacts create a reputational cost
(`BetrayalObservation`) for pivoting away from them. A concrete instance of
this exact mechanism in play (not about Golf specifically, but illustrating
the cost structure that would apply equally to a would-be pivot onto Golf):
Delta (seat0), g0 turn 9 — *"since deviating from my public declared intents
would trigger a BetrayalObservation visible to all players … I'll honor my
declared intents rather than pivot to a risky, reputation-costing attack
whose success … is uncertain."* More mutual coalition-building means more
standing declared commitments an agent would have to publicly break to pivot
onto a *different*, better target — Golf.

**Caveat:** four correlations over n=8 games invites reading tea leaves;
treat these as directional/descriptive, not confirmatory. They agree with
each other (coalition tracks margin positively, hostility tracks action
negatively) and with the qualitative rationale text, which is why they're
reported, but none of this should be treated as a hypothesis test.

### 2.3 Sentiment vs. action, decoupled in both directions

- g0: 0% hostile stance toward Golf, 9 executed attacks (action without
  declared sentiment).
- g2: 58% hostile stance toward Golf, 0 executed attacks (declared sentiment
  without action).

A hostile stance declaration is cheap talk here — it costs nothing to send
and is not what the resolver acts on. Whatever run #2 changes, it should not
assume that raising declared suspicion (e.g., a stronger "notice the
freerider" prompt) is sufficient on its own; g2 already shows the table can be
maximally suspicious in word and take zero action.

## 3. Decision rule, applied

Pre-registered rule (spec, §3):

- punishment **never proposed** → **Awareness arm**
- **proposed but not executed** → **Commitment arm**
- **executed but didn't pay** → **Economics arm**

Against the data:

- **Never proposed**: true for 2/8 games (25%) — and in both, Golf was
  plainly visible for most of the game, so it is not an artifact of fog. This
  is a real, minority pattern (§1.5), not the dominant one.
- **Proposed but not executed**: not supported, and not just in aggregate —
  all **17 of 17** declared attack-move intents in the corpus were followed
  by that exact same (seat, turn, unit) submitting a matching order (§1.1),
  and both `coordinated=True` two-party pact proposals (g1) were followed by
  an execution attempt the same turn. Where coordination is explicitly
  proposed, it is attempted, essentially without exception.
- **Executed but didn't pay**: the dominant, corpus-wide pattern — 39
  order-actions across 23 distinct attack-turns, 6/8 games with real
  attempts, **1 converted attack-turn** (§1). This is true even for attacks
  that look mechanically sound on paper (§1.4) and even for a negotiated
  two-party pact proposal (§1.3).

**Recommended arm for run #2: ECONOMICS.**

The table is not blind to Golf (majority of games engage it; the two
non-engaging games still see it), and it is not failing to commit (declared
attack intents and proposed coordination pacts are attempted essentially
every time). What breaks is the **conversion of an attempted
punishment into an actual loss for Golf**: base-strength ties bounce by
default (Golf never self-supports, so this should be the easy case), a
two-party pact's payoff is fragile to a single dropped call, and even a
correctly-reasoned 2-vs-1 attack (g5) didn't visibly land. A ruleset-v2
change that makes a *successful* coordinated dislodgement of a repeat
freerider pay a clear, reliable dividend to **both** the mover and the
supporter — not just the mover, who captures the center outright while the
supporter's Support order is otherwise a pure opportunity cost — directly
targets the stage where this campaign's data shows the actual breakdown.

## 4. Confidence + what would change my mind

**Confidence: moderate-high** that Economics is the right arm over
Commitment or Awareness, given (a) the never-proposed rate is a 25% minority
and not fog-driven, (b) all 17 declared attack-move intents converted to a
matching order and both `coordinated=True` pacts were attempted, and (c) the
executed→paid conversion rate is roughly 1-in-20 by any denominator (1 of 23
attack-turns, 1 of 8 engaged games) across every game that engaged Golf at
all, including cases with textbook combat math (§1.4) and a negotiated pact
(§1.3).

**What would change my mind:**

- **A resolution/dislodge log.** This corpus, by design (`CLAUDE.md`), does
  not retain one — "paid" here is inferred from the public score trajectory,
  not from a per-combat trace. §1.4's g5 mystery (a model correctly reasons
  a 2-vs-1 dislodge, submits it twice, and Golf's unit is still there next
  time it's observed) is the sharpest reason to distrust any *specific*
  execution's fate without one. If a targeted replay of that exact game/turn
  (not a new campaign — just re-deriving the resolution from the sealed
  seed) showed the attack actually succeeded and Golf simply recaptured the
  node the *same* turn via a mechanic this analysis didn't account for, that
  would undercut the "attacks mechanically fail to pay" reading and point
  instead at a **scoring/turn-order** issue, not a combat-economics one —
  a different fix entirely.
- **The ~8.2% parse/timeout-fail rate as a confound.** g1's broken pact
  (§1.3) shows at least one non-payoff attributable to infrastructure, not
  incentives. Restricting the "executed" set to only turns where every
  involved seat's call actually returned (no fallback on either side) and
  checking whether the payoff rate on *that* subset is still near-zero would
  isolate Economics as the driver and strengthen this recommendation. If
  instead most non-payoffs turn out to
  be parse/timeout artifacts once measured cleanly, the fix is reliability
  engineering, not ruleset economics.
- **Illegal/geometrically-invalid Support orders.** This classifier counts
  what was *submitted*, not what survived the engine's silent legality
  normalization (`legal.py` drops illegal orders without raising, per
  `CLAUDE.md`). If a meaningful share of the 39 "executed" attack-supports
  turn out to be geometrically illegal (dropped before resolution), the true
  executed→paid denominator is smaller and the effective failure rate is
  *higher* than reported — which would only reinforce Economics, but for a
  partly different reason (models mis-reasoning geometry, not the payoff
  structure itself being weak) — and would argue for pairing the ruleset-v2
  economics change with better in-prompt legality feedback.
- **If run #2's Economics arm ships and the payoff rate doesn't move**, that
  would be the strongest evidence against this recommendation — it would
  mean the bottleneck is somewhere this autopsy didn't find (e.g. a genuine
  combat-resolution defect, or that Golf's scripted opportunism adapts to
  fill any gap the new payoff structure leaves open).

## Reproducibility

All counts and correlations above — including every §2.2 correlation, not
just coalition-vs-resistance — are produced by `scripts/foedus_s1_autopsy.py`
(module: `foedus/eval/punishment_metrics.py`), covered by 40 unit tests
(`tests/test_punishment_metrics.py`) and 3 integration tests
(`tests/test_s1_autopsy_script.py`) against synthetic fixtures — no test
touches the sealed run artifacts, which are read-only inputs. Re-run the
command in the header to regenerate; the full per-game/turn/seat citation
list, the `attack_move_intents_matched_by_execution` linkage stat, and the
`correlations` dict are all available via `--json`. The one exception is the
§1.2 g4 MAP-ownership cross-check, which is a manual read against the raw
JSONL (the classifier does not parse the MAP block) — cited with the exact
turn numbers and node marks so it can be re-verified by hand.
