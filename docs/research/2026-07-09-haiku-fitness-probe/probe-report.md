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

**Degeneracy flags** (`foedus.eval.probe_metrics`): zero all-Hold turns, zero repeated-identical-
order runs (≥3 consecutive turns), for all three identities, both games. Haiku never collapsed
into the "give up and Hold" or "resubmit the same orders regardless of the board" failure modes
this axis exists to catch.

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

- **Cross-player Support: 2 of 24** (both in game 1, turn 9/10-displayed) — Delta's u3 declared
  `Support(target=7)` [Foxtrot's unit] and, the same round, Foxtrot's u0 declared
  `Support(target=3)` [Delta's unit]. This immediately follows a pact **proposal** Foxtrot sent
  Delta the prior turn (`counterparty=1`, terms: Foxtrot moves u7, Delta supports u7, Foxtrot
  supports Delta's u3) — a real, specific coordination attempt, not a vague ally gesture.
  Cross-referencing the rendered game transcript (`run/transcript_game1.md`), only Foxtrot's half
  is visible as an executed order in the resolved turn history; Delta's declared reciprocal
  Support does not appear post-resolution (both parsed cleanly, `fell_back=False` for both — this
  looks like a *geometric* legality miss, not a parsing failure, consistent with `foedus/legal.py`
  silently dropping illegal submissions per the project's normalization invariant). So: a genuine
  two-sided coordination *attempt*, with (at best) one-sided *execution*.
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
  contradicts, the Sonnet run #1 finding** (results.md §7.4: hostility toward the freerider rose
  only marginally and freerider margin/win-rate moved the *wrong* way even over 8 games with
  memory). Haiku is not uniquely bad at this; full campaigns with a stronger model showed the same
  shape of result.

**Self-notes** (verbatim, model's own words — 3 of 6 total, representative spread):

> Delta (game 0): "Golf: declared ally all 11 turns but never committed to pact or support—pure
> empty posturing. Don't be fooled. [...] Your independent strategy worked; you don't need
> alliances to win."

> Echo (game 1): "Golf declared ally all 11 turns but never formalized a pact or gave support.
> They scored 40 (close to your 44). Consider whether to ignore their future declarations, accept
> selectively, or demand actual support. [...] Next time, test whether accepting Golf's pacts
> creates mutual advantage or just enables them."

> Foxtrot (game 1): "Golf: declared ally 11 turns, refused pact, gave zero support - pure
> deception. [...] Never give support without signed mutual pact. Next game: demand pact before
> helping anyone, or stay independent like Echo."

All three entrants independently and correctly diagnosed Golf's declare-ally/never-deliver
pattern by name, in both games, using their own fogged observations (not given the freerider
label) — this is the discrimination signal the campaign format is built to test for. The
strategic conclusion they converge on ("play independently, don't extend trust") is a rational
response to an environment with one persistent defector and no reliable partners yet identified
— not evidence of confusion or incoherence.

## Verdict

**HAIKU FIT — with an explicit caveat on the sparse-coordination signal.**

- Mechanical axis: **clears the bar decisively** (0.0% vs. ≤8% target, 47-point margin under the
  Sonnet baseline, zero degeneracy flags).
- Coordination axis: **not degenerate.** Correct, repeated, unprompted freerider identification;
  zero freerider subsidy; one genuine (if only half-executed) inter-player Support coordination
  attempt following an explicit pact proposal; behavioral (not just verbal) hostility shift toward
  the defector. This clears "engages with the social layer" — it does not clear a higher bar of
  "reliably forms and executes alliances," but the pre-registered rule asks for *real coordination
  vs. degenerate play*, not campaign-winning diplomacy.
- The freerider still wasn't contained (won/placed 2nd once) — flagged honestly, but this mirrors
  the Sonnet baseline's own §7.4 finding over 4× the games, so it isn't evidence against Haiku
  specifically.

**Caveats for whoever acts on this:** n=2 games is a small sample for the coordination axis in
particular (the mechanical 0% is a strong signal even at n=2 given the Sonnet baseline's 8.2% had
material spread per-game too; the coordination count of "2 cross-player Supports in 144
decisions" is not — a larger sample could show more or none). This is a single arm, not a sealed
run, and does not update the canonical leaderboard or OpenSkill standings. The recommendation is
to proceed with Haiku for the cost-saving re-run; the model decision itself is David's.

## Artifacts

- `run/` — sweep.jsonl, telemetry.jsonl, per-seat decision logs, transcripts, campaign memory,
  seed manifests (sealed + revealed), standings.json, run_summary.json.
- `scripts/foedus_haiku_probe_report.py` — regenerates the mechanical/social tables above from
  `run/` (`PYTHONPATH=. python3 scripts/foedus_haiku_probe_report.py --out-dir
  docs/research/2026-07-09-haiku-fitness-probe/run`).
- `foedus/eval/probe_metrics.py` — degeneracy flags + self-note extraction, new for this probe.
