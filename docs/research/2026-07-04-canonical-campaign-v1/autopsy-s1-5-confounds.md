# S1.5 — Confound-resolution pass (deciding run #2's arm)

**Status:** analysis-only, read-only over the sealed `run/`. Zero new games,
zero LLM calls. Extends `autopsy-s1.md` (S1, PR #45), which recommended the
**Economics** arm off a ~1-in-20 executed→paid conversion rate but flagged
three confounds (its section 4) that could flip the fix entirely. This memo
resolves all three from data already on disk.

**Tooling (new, this pass):**

- `foedus/eval/resolution_replay.py` — replays a sealed game turn-by-turn
  through the REAL engine (`foedus.loop.play_game` +
  `foedus.resolve._resolve_orders_detailed`), substituting a `ReplayAgent`
  that reproduces each seat's LOGGED decision for the live LLM call.
  Tested against synthetic fixtures (`tests/test_resolution_replay.py`),
  including a full equivalence test that drives one game twice — live and
  replayed — and asserts an identical final turn/scores/units/ownership/
  eliminated (the outcome-bearing fields), plus a dedicated regression test
  that the replay's per-seat agent construction preserves strict seat order
  (0..N-1) rather than whatever order `llm_seats`/`freerider_seats` list
  seats in — same-turn pact-proposal ordering depends on it (see that
  test's docstring).
- `foedus/eval/punishment_metrics.py` — extended with `clean_call_subset`,
  `fell_back_by_seat_turn`, `client_error_by_seat_turn` (Check 2), and
  `count_require_dest_declarations` (the corpus-wide `require_dest` sweep
  behind the 67-declaration total in Check 1+3, below).
- `scripts/foedus_s1_5_confound_check.py` — orchestrates all three checks
  over the full 8-game corpus. Regenerate every number below with:

  ```sh
  PYTHONPATH=. python3 scripts/foedus_s1_5_confound_check.py \
      --out-dir docs/research/2026-07-04-canonical-campaign-v1/run
  ```

## 0. Replay integrity, first

Before trusting anything below: the replay reproduces **all 8 games exactly**
— final scores, turn count, and eliminations match `sweep.jsonl` in every
game, and cross-checking the replay's own actually-submitted orders against
each seat's independently-logged `parsed` field (what the ORIGINAL run
submitted, after its own legality gate) turns up **zero mismatches** across
every logged decision in the corpus. This is the harness's own self-check
(`verify_replay_fidelity`), not just an aggregate score match. Everything
that follows is read directly off `foedus.resolve`'s own
`ResolutionDetail` for the replayed turns, not re-derived by diffing
before/after state.

## 1. Check 1 — resolution-truth replay

**Verdict: FLIPS-to-combat-resolution/legality-parser-bug** (not the literal
"scoring bug" framing the confound anticipated, but a code bug in the same
family: the resolver never *sees* several orders that would have changed the
outcome, because a validation layer that sits upstream of it silently drops
them — see Check 3, which this check's numbers turn out to be inseparable
from).

Of the 39 executed order-actions (25 `attack_move`, 14 `attack_support`)
across all 8 games, direct replay through `_resolve_orders_detailed` finds:

| | count |
|---|---|
| attack_move: **dislodged** Golf's unit | **2** (g4 turn 7, g7 turn 11) |
| attack_move: bounced | 23 |
| attack_support: survived to resolution (bare `Support(target=X)`) | 2 |
| attack_support: dropped before resolution (`require_dest` Support) | 12 |

**The ground-truth dislodge count is 2, not the S1 headline's 1.** g4 turn 7
was already confirmed directly against the MAP block's ownership marks in
`autopsy-s1.md` §1.2 — this replay reproduces it exactly (Foxtrot's u2
`Move(dest=11)` dislodges Golf's u0, `outcome[2]="success"`,
`dislodged_by[0]=2`). **g7 turn 11 is a NEW finding**: Foxtrot (seat1 in g7)
submits `u3 Move(dest=9)`; the replay shows it dislodges Golf's u2
(`outcome[3]="success"`, `dislodged_by[2]=3`) — but the S1 autopsy's
`golf_income_drop_turns` for g7 is empty (`paid_count=0` for that game),
because turn 11 is g7's **last turn** (`total_turns=12`, decisions run
0..11) — there is no turn-12 negotiate prompt to observe the resulting score
change in, so the score-delta proxy is structurally blind to a dislodge on a
game's final turn. This is a genuine limitation of the proxy the S1 doc
already flagged in the abstract (§0: "paid" is an outcome-level proxy, not
ground truth) — replay confirms a concrete instance of it costing a real
data point, in the direction of **undercounting** capture.

**The g5-turn-9 "mystery" (autopsy-s1.md §1.4) is resolved, but not the way
either preset bucket predicts.** Replay confirms the attack (Foxtrot's u0
`Move(dest=6)`) really did bounce (`outcome[0]="fail"`) at every one of its
three attempts (turns 8, 9, 11) — genuinely, not a scoring/turn-order
artifact. But *why* it bounced is new: Foxtrot's own reasoning ("I get
attack strength 2 vs. the lone defender's strength 1") was mechanically
correct *if its Support order had reached the resolver* — it never did (see
Check 3). Reinstating it via `counterfactual_reinstate_order`, however,
*still* shows a bounce in all three g5 attempts, for a distinct and
legitimate reason: Golf's own unit independently moves onto Foxtrot's home
node (2) that same turn in each case, and an enemy Move into a supporter's
own square **cuts its support regardless of whether that move itself
succeeds** (`foedus.resolve._compute_cuts` / `_find_cutters` — ordinary
Diplomacy mechanics, not a bug). So g5 specifically bounces for two
independent, compounding reasons — a real support-cut on top of the
parser-dropped order — and would **not** have converted even with Check 3's
bug fixed. This is the one case in the corpus where "genuinely bounced" is
the full and correct explanation.

## 2. Check 2 — clean-call payoff subset

**Verdict: RESOLVED — infra reliability is NOT the driver.**

`fell_back` (as logged) conflates two different things: a genuine transport
failure (`raw_response` is literally `<client error: ...>`, e.g. g1 turn 8's
Echo timeout cited in autopsy-s1.md §1.3) and a call that *succeeded* but
needed the label-sanitizer to recover otherwise-malformed JSON (a cosmetic
parse-quality signal — see `foedus.agents.llm.parse._sanitize_node_labels`).
Both are reported, since conflating them would understate the clean subset:

| subset | executed | paid |
|---|---|---|
| full (all 39) | 39 | 1 |
| clean, broad (excludes any fallback, incl. sanitizer-recovery) | 11 | 1 |
| clean, **strict** (excludes only genuine client-error/timeout) | **34** | **1** |

Only 3 of the 39 executions' involved (seat, turn) pairs had a genuine
transport failure that turn (g1 t9, g5 t9, g6 t10 — all `<client error:
RuntimeError('claude -p timed out after 300.0s')>` or equivalent); the other
11 "dirty" broad-subset exclusions are sanitizer-recovered calls that
returned real, usable JSON. On the **strict** (correctly-scoped) clean
subset — 34 of 39 executions, an 87% coverage that is not a small or
cherry-picked sample — the conversion rate is unchanged: still 1 confirmed
by the proxy (2 by ground truth, per Check 1, and both of those — g4 t7, g7
t11 — occur on turns with no client-error at all, so they remain in the
strict-clean set). Restricting to reliable calls does not move the needle.

**Caveat on this check's blind spot:** it can only flag a turn dirty via a
seat whose order *itself* parsed into a tracked execution — a seat whose
ENTIRE call fails (pure `<client error>`, no JSON at all) contributes no
execution entry for `classify_orders_execution` to find, so it never enters
the "involved seats" set in the first place. g1 turn 8's Echo timeout
(autopsy-s1.md §1.3 — Echo's *Support* call for the Foxtrot→Echo pact) is
exactly this case: Foxtrot's paired `Move(dest=4)` still shows up as a
(legal, bounced) execution, and turn 8 is clean under the strict definition
above, even though the coordination WAS genuinely undermined by a real
timeout. This one non-payoff is real and infra-caused (as S1 already
reported), but it is invisible to both the full 39-count and this check's
"clean" filter by construction — not a case this check can be credited with
excluding. It is a single instance, not a pattern: even crediting it as an
infra failure, that is 1 of 39, not enough to explain the aggregate gap.

One more scoping note on the 34/39 strict figure: `client_error_by_seat_turn`
folds a seat's negotiate-phase and orders-phase calls into one dirty/clean
flag per (seat, turn) via OR, so a turn where only the *negotiate* call
timed out but the *orders* call for that same seat succeeded is still
excluded from the strict-clean set. This is conservative in the direction
that matters (it can only shrink the clean subset, never inflate the
reported coverage), so it does not threaten the RESOLVED verdict — noted
here only so the 87% figure's exact scope is explicit.

## 3. Check 3 — legality survival

**Verdict: FLIPS-to-combat-resolution/legality-parser-bug — this is the
decisive confound.**

Every one of the 39 executed order-actions was re-checked against
`foedus.legal.legal_orders_for_unit` at the REPLAYED state for that turn
(not the original run's state — they are identical per Check 0's fidelity
check), with a second-order check for any `Support(..., require_dest=X)`
order: does `foedus.resolve`'s own normalization (`_normalize_with_reason`,
the exact function `_resolve_orders_detailed` calls) accept it, given what
every other unit actually did that turn?

| legality | count |
|---|---|
| legal (reached the resolver as declared) | 27 |
| **illegal, but ONLY because of a parser/prompt-schema gap** | **12** |
| illegal for a genuine geometric reason | **0** |

**All 12 dropped orders were geometrically valid — `foedus.resolve`'s own
normalization would have accepted every single one.** The mechanism:
`foedus.legal.legal_orders_for_unit` never enumerates the `require_dest`
("pin") variant of Support as a candidate order — by explicit design, per
its own docstring ("Pin variants ... are NOT enumerated; pinning is an
opt-in expressive behavior, not part of the default candidate set"). But
`foedus.agents.llm.parse.parse_order` (used for BOTH negotiate-phase Intents
and live orders) legality-gates a submitted order by checking membership in
exactly that candidate list — so **any Support order using `require_dest`
is unconditionally coerced to `Hold()`, regardless of validity.** And the
`require_dest` field is not a model hallucination: it is explicitly
documented in the prompt's own "Order objects" schema section
(`foedus/agents/llm/render.py` lines 364 / 453,
`{"type": "Support", "target": <unit_id>, "require_dest": <node_id>}`),
right next to the per-unit "legal orders" list that never actually offers
it. **A corpus-wide sweep (independent of the 39-execution set, covering
every `require_dest` Support declared anywhere in all 8 games — orders-phase
submissions, negotiate-phase declared Intents, and negotiate-phase
pact-proposal terms, since all three route through the same `parse_order`
legality gate) confirms this is not occasional: 67 declaration-events total
(29 orders-phase / 28 negotiate-intents / 10 pact-terms), every one coerced
to `Hold()` by the mechanism above. Zero exceptions.** ("Declaration-events"
because the same underlying order can appear more than once across surfaces
— e.g. declared as a negotiate-phase Intent at turn T, then submitted as the
actual orders-phase order at that same turn T — so 67 is not a claim of 67
*distinct* orders, it is 67 *times* the parser gate discarded a `require_dest`
Support somewhere in the corpus.) This 67 is the true denominator for how
often the bug silently discards a declared order — not just the 12 that
happened to back an executed attack on Golf, which is the only subset
independently re-verified end-to-end against the resolver below.

Of the 12 parser-gap-dropped Support order-actions specifically backing an
attack on Golf, reinstating the order (`counterfactual_reinstate_order`,
holding every other unit's actual submitted order fixed) flips the paired
mover from `fail` to `success` in **9 of 12** cases:

| game | turns | attacker (entrant) | flips to success? |
|---|---|---|---|
| g0 | 5, 6, 10, 11 | Foxtrot (seat2) | yes (all 4) |
| g1 | 8 | Delta (seat1) | yes |
| g4 | 3, 4 | Foxtrot (seat2) | yes (both) |
| g5 | 8, 9, 11 | Foxtrot (seat3) | **no** (support-cut — see Check 1) |
| g6 | 10, 11 | Foxtrot (seat0) | yes (both) |

(Seat numbers differ because entrants rotate seats each game per §7.4 of the
ruleset; "Foxtrot" is the same persistent identity throughout.)

**The clearest single illustration in the corpus is g4 itself.** Foxtrot's
unit 6 attempts the *identical* declared support — same supporting unit,
same mover (unit 2), same target node (11) — three times:

| g4 turn | u6's declared Support | legality | u2 (mover) outcome |
|---|---|---|---|
| 3 | `Support(target=2, require_dest=11)` | illegal_parser_gap → dropped to `Hold()` | fail |
| 4 | `Support(target=2, require_dest=11)` | illegal_parser_gap → dropped to `Hold()` | fail |
| 7 | `Support(target=2)` **(bare, no require_dest)** | legal → survives as `Support(target=2)` | **success — dislodges Golf's u0** |

This is turn 7, the one payoff `autopsy-s1.md` §1.2 confirmed directly
against the MAP block's ownership marks. Same entrant, same units, same
target, same intent — the only thing that changed between the two failed
attempts and the one success is which Support syntax the model happened to
emit that turn. g7 turn 11 (the newly-found second dislodge, Echo
`Support(target=3)` backing Foxtrot's mover) is the same bare-syntax
pattern. **Both of the corpus's two real dislodges used the syntax the
parser actually accepts; every attempt using the syntax the prompt ALSO
documents, but the parser silently rejects, failed** — a clean, no-exceptions
split, not a marginal effect.

**This is not "models mis-reasoning geometry."** The autopsy-s1.md §4
residual explicitly anticipated that outcome ("a meaningful share ... turn
out to be geometrically illegal ... models mis-reasoning geometry, not the
payoff structure itself being weak"). What the data actually shows is the
opposite: the models' geometric reasoning was consistently *correct* (0 of
12 genuinely illegal), and a specific, mechanical, unconditional parser gap
threw the orders away anyway. Fixing `foedus.legal`'s candidate enumeration
(or loosening `parse_order`'s equality-based legality check for
`require_dest` Supports) is a small, targeted, verifiable code change with a
direct causal line to 9 additional real dislodges in this exact corpus: the
attack-move dislodge rate goes from 2 of 25 (8%) actually observed to 11 of
25 (44%) counterfactually achievable — a 5.5x jump — simply by letting the
already-correct Support orders reach the resolver, no ruleset change
involved. (Restricted to the 14 attack-move attempts that had ANY Support
declared behind them, the jump is from 2-of-14 to 11-of-14, i.e. most
supported attacks would have converted.)

## 4. Final run #2 arm verdict

**PIVOT to a combat-resolution/legality fix — NOT a straight Economics
campaign, and NOT a reliability-engineering push.**

- Check 2 (RESOLVED): the executed→paid gap survives an 87%-coverage clean
  subset excluding genuine transport failures. Infra reliability is not the
  driver.
- Check 3 (FLIPS): 12 of 39 executed order-actions — the model's own
  preferred, prompt-documented, and (per the counterfactual) usually-correct
  way of expressing coordinated support — never reach the resolver at all,
  due to a specific, code-level, unconditional gap between
  `foedus.legal.legal_orders_for_unit`'s candidate enumeration and
  `foedus.agents.llm.parse.parse_order`'s legality gate.
- Check 1 (FLIPS, corroborating): ground-truth replay finds 2 real
  dislodges, not 1 — the score-delta proxy undercounts, and the specific
  case it misses (g7 turn 11) is unrelated to Check 3, an independent data
  quality issue with the ORIGINAL proxy metric itself (blind to a capture on
  a game's final turn), not a confound in the "is Economics right" sense.

Running run #2 as a straight Economics campaign right now would measure the
combined effect of (a) whatever the ruleset-v2 payoff change actually does
and (b) this parser bug still silently discarding the majority of pin-style
coordinated Supports — an uninterpretable mixture. The corpus's own data
says the fix belongs in the engine/prompt layer first:

1. **Fix the `require_dest` legality gap** (`foedus/legal.py` +
   `foedus/agents/llm/parse.py::parse_order`) so a geometrically-valid pin
   Support is accepted, matching what the prompt already documents and what
   `foedus.resolve` already accepts internally. This is the highest-leverage,
   lowest-risk change available: it's a bug fix with a clear specification
   (make `parse_order`'s legality check match what `_normalize` already
   does), not a game-design change, and this corpus already shows its
   likely effect size (9 of 12 flip).
2. **Re-run the S1 punishment-metrics autopsy tooling** (unchanged) against
   either a small confirmatory re-run OR — cheaper — re-derive what
   executed→paid *would* look like on the sealed corpus with the fix
   applied, using this pass's own counterfactual numbers as the estimate (up
   to 11 of 25 attack-move attempts converting, vs. 2 actually observed).
3. **Only then** decide whether a *further* Economics change (e.g. a
   supporter-side reward increase) is still warranted on top of the fix —
   the original Economics hypothesis (base-strength ties bounce by default,
   a mover-takes-all payoff under-rewards the supporter) may still hold and
   may still be worth pursuing for run #2, but it should be measured against
   a corpus where coordinated Support orders actually reach the engine.

## 5. Confidence + residual unknowns

**Confidence: high** on Check 2 (RESOLVED) and Check 3 (FLIPS) — both rest
on a replay whose fidelity is independently verified against every logged
decision in the corpus with zero mismatches, not a sample or a proxy.
**Confidence: high** on Check 1's g4t7/g5 findings (direct engine
ground-truth); **moderate-high** on the g7t11 undercount being purely a
proxy blind spot rather than something else, since it rests on one instance
— though the mechanism (last-turn dislodge, no next-turn negotiate prompt to
observe) is structural and fully explains the gap, not merely correlated
with it.

**What would still change this:**

- **The g5 support-cut finding (§1) generalizes only as far as this corpus
  shows.** It is possible other games have a similar interaction (a
  would-be-flipped parser-gap Support gets cut by an unrelated enemy move)
  that this pass didn't specifically look for beyond the 12 parser-gap
  cases already checked — but those 12 ARE the full set (not a sample), so
  this is a completeness note, not an open question: all 12 were checked,
  9 flip, 3 don't (for the stated reason), and no others exist to check.
- **This memo does not re-verify the S1 autopsy's other findings**
  (coalition-vs-margin correlations, the sentiment/action decoupling in
  g2/g3, etc.) — those are untouched by any of the three confounds and
  stand as published.
- **The fix itself is not implemented here** (out of scope: this pass is
  read-only analysis). The 9-of-12 counterfactual-flip figure is the
  expected effect size on THIS sealed corpus specifically, not a
  guaranteed outcome for a fresh run #2 — different games, different
  entrants' emergent tactics, and a corrected legality gate will not
  reproduce these exact numbers, only the qualitative direction (a real,
  substantial jump in executed→paid conversion once coordinated Supports
  stop being silently discarded).
- **Smallest additional cut that would settle any remaining doubt:** apply
  the `require_dest` fix, re-run this pass's own tooling
  (`scripts/foedus_s1_5_confound_check.py`) on a SHORT confirmatory re-run
  (2-3 games reusing the same freerider seat pattern) before committing to
  a full 8-game run #2 — cheap, and directly checks whether the fix's
  effect size holds up outside the sealed corpus.

## Reproducibility

All counts above are produced by regenerating with
`scripts/foedus_s1_5_confound_check.py` (modules:
`foedus.eval.resolution_replay`, extensions to
`foedus.eval.punishment_metrics`), which reads the sealed `run/` directory —
that is the only thing in this pass that touches it. The unit tests for
those same modules (`tests/test_resolution_replay.py`,
`tests/test_clean_call_subset.py`, `tests/test_s1_5_confound_check_script.py`)
run against synthetic fixtures only; none of them touches the sealed run
artifacts. Re-run the command in the header to regenerate; pass `--json`
for the full per-game, per-execution classification (declared order, canon
order post-resolution, outcome, and — for parser-gap cases — the
counterfactual mover outcome).
