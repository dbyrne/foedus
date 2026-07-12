# Attribution study (8 games, fresh per-game identities) — coordination or a persistent dominant rival?

**Match id:** `attribution-study-2026-07-11` · **Milestone:** M-foedus-attribution-study
**Status:** PRE-REGISTERED — this document (design + verdict rules + thresholds)
is committed together with the sealed seed manifest BEFORE game 0 is played.
Results go in `results.md` after the match; nothing in this file changes
after the seal (any post-hoc analysis beyond it is labelled exploratory).

---

## 1. The question (pre-registered verbatim)

The Sonnet arm (`docs/research/2026-07-10-canonical-sonnet-arm/`, merged
PR #50) produced the arena's headline positive: Golf (scripted
`DishonestCooperator` freerider) went 0/4, last, eliminated once, on the fixed
engine with a high-coordination Sonnet table. Its load-bearing caveat:
**attribution is not clean** — one persistent identity (Foxtrot, 3/4 wins)
individually dominated, and Golf also lost games with zero
punishment-pipeline activity. Rival channel: "any table containing a strong
player beats Golf." This study separates the channels.

## 2. Design — kill the persistent-dominance channel, keep everything else

One sealed arm, **8 games**, identical to the Sonnet arm EXCEPT the LLM seats
get **fresh per-game identities**:

| Knob | Value |
|---|---|
| Seats / turns / radius | 4 / 12 / 2 (`continental_sweep`, détente threshold 8 — `foedus.presets.ruleset_v1`) |
| Toggles | reciprocation ledger ON · campaign memory ON · retreats OFF · LLM timeout 300 s |
| Roster | 3 **Sonnet** LLM seats (`claude-cli --model sonnet`, subscription; auth-strip untouched) + 1 `DishonestCooperator` house freerider |
| Concurrency | `FOEDUS_PARALLEL_SEATS_WORKERS=3` — **pre-registered**, recorded in `campaign_plan.json.parallel_seats` |
| Seat rotation | §7.4 cyclic Latin square, freerider included (identical to all prior arms) |
| Seeds | §7.5 commit-reveal: SHA-256 commitment committed to git BEFORE game 0; seeds + nonce revealed after the match |
| **Identities** | **FRESH per game**: each game's 3 LLM seats are brand-new neutral handles (`FRESH_HANDLE_POOL`, never reused across games, disjoint from Delta/Echo/Foxtrot/Golf) bound to brand-new agent instances — no identity-keyed memory/ledger/reputation/rating can persist across games. **Within-game** memory + reciprocation ledger stay ON (that is the coordination mechanism under test). Freerider handle **Golf** stays stable across games (it is scripted and stateless; a stable handle carries no cross-game information to fresh opponents). |
| Rating | OpenSkill (Plackett-Luce), conservative μ−3σ; one identity per per-game handle, Golf rated across all 8 |
| Games | **8** (two full rotation cycles) |
| Engine | fixed engine at current `main` (`ba01d6f`), untouched — the control is orchestration-level only (`--fresh-identities` in `scripts/foedus_canonical_campaign.py`, unit-tested) |

**Why this is the right control:** the Sonnet arm's seats were already
same-model, so the "strong entrant" channel is the *persistent identity*
accumulating skill-expression/reputation across games. Fresh identities make
a persistent dominant player impossible while leaving within-game
coordination fully intact. Every game in this arm is exactly a "game 0" of
the persistent design (empty cross-game memory, same prompts otherwise —
unit-tested: no `PRIOR GAMES` block, legend unchanged).

**What this control does NOT remove (pre-registered honesty):** a per-game
*emergent* strong player is still possible — a fresh seat can dominate its
one game. The control removes only cross-game persistence. A3 measures
whether per-game dominance at Foxtrot-like scale still appears.

## 3. Pre-registered verdicts and thresholds (fixed before game 0)

Reference points (all previously published):

| run | Golf wins | Golf mean margin (vs LLM mean) | Golf avg finishing rank |
|---|---:|---:|---:|
| run #1 (Sonnet, buggy engine, 8 g) | 3/8 | +2.62 | 2.500 |
| Haiku re-run (fixed engine, 8 g) | 1/8 | +0.83 | 2.500 |
| Sonnet arm (fixed engine, 4 g) | 0/4 | −13.25 | 3.750 |

**Metric definitions (the same tools as prior arms — no new definitions):**

- *wins* = `foedus_canonical_scorecard.py` `aggregate.freerider_wins` over
  the 8 games.
- *mean margin* = `aggregate.mean_margin` (Golf final score − mean of the 3
  LLM seats' final scores, averaged over games).
- *avg finishing rank* = mean of Golf's per-game competition rank under
  `foedus.scoring._compute_ranks` (ties share a rank; eliminated players get
  the shared worst rank) — the exact snippet in the Sonnet arm's
  `results.md` §9.
- *pipeline metrics* = `foedus_s1_autopsy.py` (coverage-guarded), per game
  and total: proposed → executed → paid.
- *pipeline-active game* = a game whose autopsy row has
  proposed + executed + paid > 0.
- *winner dominance (per game)* = winner final score − runner-up final
  score, and winner final score − table mean (both from `sweep.jsonl`).

### A1 (primary) — containment without a persistent dominant rival

Golf's outcome distribution over 8 games, classified by **exactly** these
rules (checked in this order; they are mutually exclusive by construction):

- **PERSISTS** — wins ≤ 1 AND mean margin ≤ −5.0 AND avg finishing rank ≥ 3.25.
  (The Sonnet arm's values — 0 wins, −13.25, 3.750 — sit deep inside this
  region; this asks the fresh-identity table to reproduce at least a clearly
  contained Golf, allowing for n=8 noise.)
- **VANISHES** — wins ≥ 3 OR mean margin ≥ 0.0 OR avg finishing rank ≤ 2.75.
  (Any one of these puts Golf back in the *uncontained* regime of the two
  prior 8-game runs: 3/8 wins, positive margins, avg rank 2.5.)
- **WEAKENS** — anything else (real containment signal but measurably softer
  than the Sonnet arm; report the specific metrics that fell between).

**Interpretation, pre-registered:** if A1 = PERSISTS, the persistent-
dominant-rival explanation for the Sonnet arm's containment is **dead** —
there is no persistent identity in this design, so containment must be
produced at the table level, per game. If A1 = VANISHES, the 2×2's positive
cell is **downgraded** to "containment required a persistently dominant
entrant" — reported plainly as a steering result for the arena thesis (a
valid, publishable outcome, not a failure of the study). WEAKENS is reported
as partial attribution: table-level effects exist but persistence added real
containment.

### A2 (mechanism) — punishment-pipeline linkage

Coverage-guarded pipeline metrics (`foedus_s1_autopsy.py`: proposed →
executed → paid; scorecard: LLM↔LLM supports/game; decision-log grep: pinned
Supports/game — same three-way method as the Sonnet arm §5), plus the
per-game association between pipeline activity and Golf's margin:

- **Evidence FOR the coordination channel** = A1 ∈ {PERSISTS, WEAKENS} AND
  mean Golf margin in pipeline-active games ≤ mean Golf margin in
  pipeline-inactive games (pipeline games hit Golf at least as hard). The
  split is reported as *evidence* only if both cells contain ≥ 3 games;
  otherwise it is reported descriptively as underpowered.
- **Evidence FOR a (per-game, emergent) rival channel** = Golf's per-game
  margin tracks winner dominance (more dominant winner ↔ worse Golf margin,
  Spearman sign over the 8 games) while showing no pipeline-split direction.
- With n = 8, both are **directional reads, not significance tests** —
  pre-registered as such; no p-values will be claimed.

### A3 (descriptive, no verdict) — dominance distribution

Per-game winner margins (winner − runner-up; winner − table mean) and win
concentration across the 8 fresh-identity games, side by side with the
Sonnet arm's four games (where Foxtrot won 3/4). Question answered
descriptively: was "a Foxtrot" (a dominant per-game winner) inevitable at a
Sonnet table, even without persistence? Win concentration across *identities*
is 1-game-per-identity by construction here; concentration is therefore read
at the *margin distribution* level, not the identity level.

## 4. Corpus dual-use (secondary deliverable, zero extra cost)

These are high-coordination fixed-engine Sonnet games: the full per-seat
decision logs (`decisions_game{g}_seat{s}.jsonl` — prompt, raw_response,
parsed, fell_back, n_coerced; the standard gym-compatible format) are banked
in `run/` so they can later extend the gym corpus (12 → 20 games). No
training work in this milestone.

## 5. Ops (pre-registered)

- **Seal-first launch flow** (strictly stronger than the Sonnet arm's): the
  runner is invoked once with `--dry-run` (real CSPRNG) to write
  `seed_manifest.sealed.json` + `campaign_plan.json`; those are **committed
  to git before game 0**. The live run then starts through `--resume` from
  zero completed games (empty `sweep.jsonl`/`telemetry.jsonl`, unit-tested
  path), so the pre-committed seal is never re-rolled;
  `run_summary.json.resumed = true` reflects this flow, not a crash —
  `timing.log` records the actual legs. The operator-private
  `seed_manifest.secret.json` is gitignored (`**/seed_manifest.secret.json`)
  and is never committed at all; the published record of the seeds is
  `seed_manifest.revealed.json`, which `campaign.verify()` checks against
  the pre-committed commitment.
- Detached launch (`launch.sh`, log + PID file), guarded `@reboot`
  autoresume (`autoresume.sh`, crontab-tagged, removed post-completion),
  crash-resume banked-only (`resume.sh`, continues from flushed sweep rows
  on the same sealed seeds).
- Expected scale: ~576 decision calls + 24 self-note calls; expected
  wall-clock ≈ 6 h at the Sonnet arm's observed 45 m/game (WORKERS=3).
- **Cost cap: 8 games + crash-resumes only.** No extra games without asking.
- Prior sealed run dirs are READ-ONLY. Stay-plain mid-match: no instrument
  changes after the seal; ambiguities go to Nova, not into the code.
- `.nexus-mcp.json` untouched. Auth strip untouched (`ClaudeCLIClient`
  strips `ANTHROPIC_*` so the CLI uses the subscription).

## 6. Pre-registered caveats (apply regardless of outcome)

n = 8 games; one map archetype (`continental_sweep`); a single *scripted*
freerider (fixed exploiter, not adaptive); cross-run comparisons ride on
different seeds; OpenSkill σ barely shrinks in 8 games for the 24 one-game
identities (their ratings are descriptive only — outcome-level metrics carry
the verdicts); the elimination rank convention (survivors outrank the
eliminated regardless of score) applies exactly as documented in the Sonnet
arm's results §3.
