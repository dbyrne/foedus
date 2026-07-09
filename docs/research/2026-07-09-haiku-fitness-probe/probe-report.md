# Haiku fitness probe — is Claude Haiku 4.5 fit for the canonical arena re-run? (2026-07-09)

## Question (pre-registered, per `foedus-experiment-roadmap`)

The canonical Ruleset-v1 8-game campaign (`docs/research/2026-07-04-canonical-campaign-v1/`)
used Sonnet for all 3 LLM entrants. A full Sonnet re-run (post the require_dest "pin" legality
fix, PR #47) burns real subscription budget. Before committing to a re-run, this probe asks: is
Haiku 4.5 *fit* to stand in for Sonnet — cheaply — without changing what the canonical campaign is
measuring?

**Pre-registered decision rule:**
- **HAIKU FIT** → fail-rate ≤ ~8% (the Sonnet run #1 baseline) **AND** real coordination **AND**
  no degeneracy → use Haiku for the re-run (large cost savings).
- **UNFIT** → high fail-rate or degenerate/non-strategic play → fall back to Sonnet.
- **BORDERLINE** → mixed signal → flag for a judgment call, don't auto-decide.

**Explicit caveat going in:** the original canonical null (PR #38/#44) was measured with Sonnet.
Swapping to Haiku for the re-run changes *two* variables at once (model **and** the post-#47
parser fix) relative to that null. This probe's job is to establish whether that combined swap is
acceptable — not to produce a second sealed leaderboard entry. n=2, single arm, not sealed.

## Protocol

`scripts/foedus_canonical_campaign.py --match-id haiku-fitness-probe-2026-07-09 --num-games 2
--backend claude-cli --model haiku --out-dir docs/research/2026-07-09-haiku-fitness-probe/run`

Same format as the canonical campaign: Ruleset-v1 (4 seats, 12-turn cap, détente@8), 3 Haiku
entrants (Delta/Echo/Foxtrot) + 1 scripted `DishonestCooperator` house freerider (Golf, neutral
handle), cyclic seat rotation, cross-game memory, commit-reveal seeds (commitment
`8c73f3f93...` — see `run/seed_manifest.revealed.json`). 2 games only (cost cap). The run
survived one crash-resume (the executing session was reaped before any game started; resumed
with `--resume` from game 0 using the already-sealed seeds — no reseal, no game replayed twice).

## Results — mechanical (parse-fail / degeneracy)

| | Sonnet run #1 baseline (8 games, results.md §7.4) | **Haiku probe (2 games)** |
|---|---|---|
| Decisions | 576 (3 seats × 12 turns × 2 phases × 8 games) | **144** (3 seats × 12 turns × 2 phases × 2 games) |
| Fell back (any) | 47 | **0** |
| — timeout | 19 | 0 |
| — transport | 0 | 0 |
| — true-parse | 28 | 0 |
| **Fail rate** | **8.2%** | **0.0%** |

Per-identity (`scripts/foedus_haiku_probe_report.py`):

| identity | decisions | timeout | transport | parse | fail rate |
|---|---|---|---|---|---|
| Delta | 48 | 0 | 0 | 0 | 0.0% |
| Echo | 48 | 0 | 0 | 0 | 0.0% |
| Foxtrot | 48 | 0 | 0 | 0 | 0.0% |

**Degeneracy flags** (`foedus.eval.probe_metrics`): all-Hold turns are real and not rare — 18 of
72 orders-phase decisions (25%) across the three identities (Delta 3/24, Echo 10/24, Foxtrot
5/24; Echo's are concentrated late-game, e.g. game 0 turns 9/11/12 of 12). **Repeated-identical-
order runs (≥3 consecutive turns, byte-identical orders dict regardless of board state) are
genuinely zero** for all three identities in both games — the metric this axis most cares about
(state-blind copy-paste) found nothing, including across Echo's late-game Hold stretches: the set
of held units changes turn to turn (e.g. game 0 turn 8: {u5,u8}; turn 10: {u5,u8,u9}), so each
turn is still a distinct, apparently-considered decision rather than a frozen resubmission. Given
the ruleset's explicit walk-in/instant capture rules reward Holding a captured node through
resolution, a fair reading is late-game consolidation rather than collapse — but that's an
interpretation, not something this metric verifies; the raw all-Hold count is reported as-is.
(An earlier version of this report claimed "zero all-Hold turns" — that was a parser bug in
`_orders_dict`, which didn't strip the markdown fences every real `raw_response` uses and so
silently skipped all 72 orders-phase records. Caught in the two-reviewer honesty pass; fixed and
re-run — see `foedus/eval/probe_metrics.py`.)

Both games ran the full 12-turn cap (no elimination, no détente). Engine compute: 2.62h total,
78.6m/game mean (game 0: 76.8m, game 1: 80.4m) — informational only; not what the fail-rate
metric measures, but relevant to planning an 8-game re-run's wall-clock.

**Verdict on this axis: dramatically clears the bar.** 0/144 vs. 47/576 — better than the Sonnet
baseline by every sub-category, not just on net rate. This is the axis the probe primarily exists
to de-risk (parse-fail directly burns wall-clock and retries), and it is not close.

## Results — social / coordination

This axis is the harder call, and the honest answer is *thin, not degenerate*.

**Support orders** (bare + require_dest "pin", post-#47-fix honest count):

| identity | bare | pin | total |
|---|---|---|---|
| Delta | 13 | 0 | 13 |
| Echo | 5 | 1 | 6 |
| Foxtrot | 4 | 1 | 5 |

24 declared Support orders total across both games. To find out how many of these were actual
*inter-player* coordination (vs. a unit propping up its own owner's other unit — always legal,
never diplomacy), I rebuilt a unit→owner map per game from the `VISIBLE UNITS` block embedded in
every prompt (ground truth, not inference) and cross-referenced every declared Support's target:

- **Cross-player Support: 2 of 24** (both in game 1, turn 9/10-displayed, same turn) — Foxtrot
  proposed a pact to Delta in that turn's *negotiate* phase (`counterparty=1`, terms: Foxtrot
  moves u7, Delta supports u7, Foxtrot supports Delta's u3), and in that same turn's *orders*
  phase both sides actually submitted their half: Delta's u3 declared `Support(target=7)`
  [Foxtrot's unit] and Foxtrot's u0 declared `Support(target=3)` [Delta's unit] — confirmed
  directly from both seats' raw `orders`-phase responses, both parsed cleanly
  (`fell_back=False`), and Delta's own prompt for that turn lists the pact as
  `[proposed] ... awaiting p1 acceptance` with exactly those three terms. **Correction from an
  earlier version of this report:** that version said only Foxtrot's half was visible in the
  rendered transcript and speculated Delta's half was dropped as geometrically illegal at
  resolution. That was wrong on two counts, caught in the two-reviewer honesty pass: (1)
  `run/transcript_game1.md` only ever records *declared negotiate-phase intents*, not resolved
  orders — no resolution log is persisted anywhere in `run/`, so Delta's absence there says
  nothing about whether its Support order actually applied; (2) `Support(target=7)` is listed
  among Delta's own legal options in that turn's prompt (generated by `foedus/legal.py`'s
  enumeration), which contradicts the "geometric legality miss" theory outright. Correct
  statement: **both parties submitted orders matching all three pact terms in the same turn**;
  whether the resolver actually applied Delta's Support is not determinable from any artifact
  committed here.
- **Freerider subsidy: 0 of 24.** No Support order, in either game, ever targeted a Golf-owned
  unit. This is the metric the original PR #38 concern was named after ("tables kept subsidizing
  the freerider") — Haiku never did this, in either game.
- **Pact activity:** 2 proposals out of 72 negotiation-phase decisions (2.8%), 0 formal
  acceptances. The one proposal above; a second (game 0, Foxtrot→Echo, mutual-Hold) also went
  unanswered.
- **Stance toward the freerider:** both games show at least one entrant flipping Golf from
  neutral to **hostile** mid-game after repeated no-follow-through "ally" declarations (game 0:
  Delta from turn 4 onward; game 1: Foxtrot from turn 10 onward) — a behavioral reaction, not just
  a verbal one.
- **Freerider outcome:** Golf placed last in game 0 (23 pts, 4th) but 2nd in game 1 (40 pts,
  losing only to Echo's 44). Reaction did not translate into containment — **this matches, not
  contradicts, the Sonnet run #1 finding** (results.md §7.2/§8: hostility toward the freerider rose
  only marginally (+0.03) and freerider margin/win-rate moved the *wrong* way (margin +5.92,
  wins 1→2) even over 8 games with memory). Haiku is not uniquely bad at this; full campaigns with
  a stronger model showed the same shape of result.

**Self-notes** (verbatim, model's own words — 3 of 6 total, representative spread):

> Delta (game 0): "[...] Golf: declared ally all 11 turns but never committed to pact or
> support--pure empty posturing. Don't be fooled. Foxtrot: neutral threat (26 pts). Your
> independent strategy worked; you don't need alliances to win. [...]"

> Echo (game 1): "Golf declared ally all 11 turns but never formalized a pact or gave support.
> They scored 40 (close to your 44). Consider whether to ignore their future declarations, accept
> selectively, or demand actual support. [...] Next time, test whether accepting Golf's pacts
> creates mutual advantage or just enables them."

> Foxtrot (game 1): "Golf: declared ally 11 turns, refused pact, gave zero support - pure
> deception. [...] Never give support without signed mutual pact. Next game: demand pact before
> helping anyone, or stay independent like Echo. [...]"

All three entrants independently and correctly diagnosed Golf's declare-ally/never-deliver
pattern by name, in both games, using their own fogged observations (not given the freerider
label) — this is the discrimination signal the campaign format is built to test for. The
strategic conclusion they converge on ("play independently, don't extend trust") is a rational
response to an environment with one persistent defector and no reliable partners yet identified
— not evidence of confusion or incoherence.

## Verdict

**HAIKU FIT — with explicit caveats on the sparse-coordination signal and the corrected
degeneracy read.**

- Mechanical axis: **clears the bar decisively** (0.0% vs. the ≤8%-ish target, an 8.2
  percentage-point margin under the Sonnet baseline). Repeated-identical-order runs — the
  state-blind-copy-paste flag — are genuinely zero for all three identities in both games.
  All-Hold turns are real and not rare (18/72 orders-phase decisions, concentrated in one
  identity's late-game play) but are not, by themselves, what this rule's "no degeneracy" clause
  is checking for; see the mechanical-results section above for the honest count and its
  ambiguity.
- Coordination axis: **not degenerate, but thin.** Correct, repeated, unprompted freerider
  identification in every self-note; zero freerider subsidy; one genuine, fully mutual-submitted
  Support coordination following an explicit same-turn pact proposal (execution outcome at
  resolution not determinable from the artifacts here); behavioral (not just verbal) hostility
  shift toward the defector. This clears "engages with the social layer" — it does not clear a
  higher bar of "reliably forms and executes alliances," but the pre-registered rule asks for
  *real coordination vs. degenerate play*, not campaign-winning diplomacy.
- The freerider still wasn't contained (won/placed 2nd once) — flagged honestly, but this mirrors
  the Sonnet baseline's own §7.2/§8 finding over 4× the games, so it isn't evidence against Haiku
  specifically.
- **Why FIT and not BORDERLINE:** the coordination evidence here (2 of 24 declared Support orders
  cross-player, 2 of 72 pact proposals, 0 formal acceptances) is genuinely thin on its own, and a
  reader could reasonably read it as BORDERLINE rather than FIT. The call to FIT rests on two
  things this report can actually check: (1) the axis this probe exists to de-risk — parse-fail,
  the direct driver of wasted wall-clock/retries in a re-run — clears by a wide, unambiguous
  margin, and that is the dominant cost lever; (2) the coordination signal, thin as it is, is
  *engaged* rather than *absent or contradictory* (correct defector ID, zero subsidy, a real
  mutual coordination attempt), and it is not visibly worse in kind than what the 8-game Sonnet
  baseline itself showed on the same axis. Someone weighting the coordination axis more heavily,
  or wanting a same-model comparison before trusting it, could reasonably land on BORDERLINE
  instead — that judgment call is flagged here rather than resolved by this report.

**Caveats for whoever acts on this:** n=2 games is a small sample for the coordination axis in
particular (the mechanical 0% is a strong signal even at n=2 given the Sonnet baseline's 8.2% had
material spread per-game too; a count of 2 cross-player Support declarations out of 24 total is
not — a larger sample could show more or none). This is a single arm, not a sealed run, and does
not update the canonical leaderboard or OpenSkill standings. The recommendation is to proceed with
Haiku for the cost-saving re-run; the model decision itself is David's.

## Artifacts

- `run/` — sweep.jsonl, telemetry.jsonl, per-seat decision logs, transcripts, campaign memory,
  seed manifests (sealed + revealed), standings.json, run_summary.json.
- `scripts/foedus_haiku_probe_report.py` — regenerates the mechanical/social tables above from
  `run/` (`PYTHONPATH=. python3 scripts/foedus_haiku_probe_report.py --out-dir
  docs/research/2026-07-09-haiku-fitness-probe/run`).
- `foedus/eval/probe_metrics.py` — degeneracy flags + self-note extraction, new for this probe.
