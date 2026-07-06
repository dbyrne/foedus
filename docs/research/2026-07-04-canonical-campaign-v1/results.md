# Canonical Ruleset-v1 campaign — results + honest verdict

**Status:** PRE-REGISTERED (criteria fixed before the run); results + verdict
filled in after the match. No prompt tweaks, no re-runs after the seeds are
revealed.
**Date:** 2026-07-04
**Archive:** this directory (see `README.md` for layout + seed verification).
**Harness:** `scripts/foedus_canonical_campaign.py` (+ `foedus.eval.campaign`),
`scripts/foedus_canonical_scorecard.py`. Board preset: `foedus.presets.ruleset_v1`.

---

## 1. What this run is

The **first official match** in the ratified standard format
(`docs/design/2026-07-04-ruleset-v1.md`). It does triple duty:

1. **Leaderboard seed** — the first Ruleset-v1 OpenSkill result.
2. **Science — defector punishment.** In the PR #38 cross-game campaign,
   seed-3's table kept subsidizing the `DishonestCooperator` freerider and never
   punished it. **Over a full campaign with memory + rotation, does a persistent
   freerider get identified and coordinated against — subsidy trending toward 0,
   coalition strengthening, its margin falling game-over-game?**
3. **Training corpus** — the durably-archived Sonnet decision-logs feed the gym
   pipeline (`M-foedus-gym-pipeline-v0`).

## 2. Format (ratified, not chosen here)

| Knob | Value |
|---|---|
| Seats / turns / radius | 4 / 12 / 2 (`continental_sweep`, détente threshold 8) |
| Toggles | reciprocation ledger ON · campaign memory ON · retreats OFF · LLM timeout 300 s |
| Roster | 3 Sonnet entrants (`claude-cli`) + 1 `DishonestCooperator` house freerider |
| Seat rotation | cyclic Latin square (§7.4); the freerider rotates like everyone else |
| Seeds | commit-reveal, SHA-256 sealed before / revealed after (§7.5) |
| Rating | OpenSkill (Plackett-Luce), one identity per entrant, conservative μ − 3σ |
| Games | **8** (two full rotation cycles) |
| Handles | Delta / Echo / Foxtrot (LLM entrants) · **Golf** (freerider house anchor) — neutral; the handle→role map is operator-side only |

The memory-mode / game-count decision (see §3) is pinned at launch and recorded
in `campaign_plan.json`.

## 3. Pre-registered design note — rotation vs. cross-game memory

A code-level tension was flagged before the run: PR #38 campaign memory keys
opponents **by seat** and its self-note prompt tells each agent *"the next game
reuses the SAME seats"* (`render.py:48`). Under the ratified **seat rotation**,
an agent's note "seat 2 freeloaded" is applied to a *different* entrant next
game. So the defector-punishment question's answer is **conditional on how this
is resolved**, and that resolution is pinned here before any data:

- **Verbatim (rotation + seat-keyed memory):** cross-game freerider-tracking is
  broken *by construction*; the pre-registered expectation is **null** learning,
  and the finding is the *mechanism*, not a coordination trend.
- **Identity-keyed memory:** opponents are tracked by stable identity across
  rotated seats; a real learning signal is possible.
- **No rotation:** seat-keyed memory is coherent; a real learning signal is
  possible at the cost of seat-balanced rating.

> **Pinned for this run: Option B — identity-keyed memory (Ruleset v1.1).**
> David approved 2026-07-04 (see the §12 amendment in the ruleset doc). Entrants
> carry stable neutral handles; cross-game memory + self-notes + OpenSkill
> identity key on the handle, so the freerider *can* be tracked across rotated
> seats. This is the only option that serves all three duties and is the correct
> arena design. The pre-registered expectation is therefore a **live** learning
> signal (not a structural null): if the table can punish a persistent defector,
> v1.1 is what lets it.

## 4. Pre-registered metrics (computed by `foedus_canonical_scorecard.py`)

Per game, and as a games-1→N trajectory:

- **Freerider outcome** — win (Y/N) and **margin** = freerider final score −
  mean LLM final score.
- **Subsidy** — count of LLM `Support` orders whose target is a freerider unit
  (the table spending actions to help the freerider).
- **Coalition (LLM↔LLM supports)** — LLM `Support` orders targeting *another*
  LLM seat's unit.
- **Stance-toward-freerider** — fraction of (turn × freerider) stance
  declarations that were hostile.
- **Parse-fail**, split **timeout vs. true** (a `<client error: … timed out …>`
  fallback is a cost artifact, not a model failure), per entrant identity.
- **OpenSkill standings** — conservative μ − 3σ per entrant identity.

## 5. Pre-registered verdict bar (learning-across-campaign)

Reported honestly regardless of direction:

- **Punishment forms** iff, across the back half vs. the front half of the
  match: **subsidy falls**, **coalition rises**, **freerider margin falls**, and
  **hostility-toward-freerider rises** — with the freerider winning fewer of the
  later games. A majority of these four moving the "right" way, monotonically
  enough to not be one-game noise, is the bar.
- **Null / anti-signal, reported plainly:** front half ≈ back half (memory
  didn't teach), or subsidy *rises* (memory seduced the table further). Under the
  verbatim (A) resolution the null is *expected* and the value is the mechanism.
- **Caveat baked in:** a single 8-game match is a *provisional* read (design
  §6.5); the persistent ladder does the real convergence. No strong claim is
  made from 8 (or 4) points — trends are reported with the raw per-game series
  so the reader can judge.

## 6. Resolver invariant

The PR #39 one-unit-per-node invariant (`tests/test_invariants.py`) is asserted
to hold across every finalized turn of the campaign (see §7.5). **PASS** —
`foedus_verify_invariant.py` replayed all 8 sealed boards under 20 random
heuristic pairings each (**1 856** per-turn one-unit-per-node checks); zero
violations. Seed manifest independently re-verified: `verified=true`,
`seeds_match_sweep=true` (`invariant_check.json`).

---

## 7. Results

> Filled in after the match from `scorecard.json` + `standings.json` +
> `invariant_check.json`. Match `canonical-v1-2026-07-05`; seal commitment
> `115b9931…de2b`; completed 2026-07-06 14:31 EDT. **No prompt tweaks, no
> re-runs; the verdict below is called against the §5 bar as pre-registered.**

### 7.1 Per-game scorecard + trajectory

Score by **handle** (seats rotate; `margin` = Golf − mean of the three LLMs;
`subsidy` = LLM Supports aimed at a Golf unit; `coalition` = LLM↔LLM Supports;
`hostility` = fraction of turn×Golf stance declarations that were hostile). All
8 games ran the full 12 turns; none reached the détente threshold (all decided
by score at turn 12).

| game | seed (short) | Golf@ | Delta | Echo | Foxtrot | **Golf** | winner | margin | subsidy | coalition | hostility | wall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| g0 | 1139001886… | s3 | 23 | 32 | 34 | **22** | Foxtrot | −7.7 | 2 | 0 | 0.00 | 116m |
| g1 | 4586517569… | s0 | 19 | 42 | 23 | **44** | **Golf** | +16.0 | 0 | 12 | 0.45 | 142m |
| g2 | 3287949421… | s1 | 23 | 35 | 41 | **23** | Foxtrot | −10.0 | 0 | 4 | 0.58 | 89m |
| g3 | 8911441032… | s2 | 23 | 34 | 38 | **32** | Foxtrot | +0.3 | 1 | 8 | 0.43 | 105m |
| g4 | 6540892972… | s3 | 41 | 35 | 20 | **33** | Delta | +1.0 | 0 | 11 | 0.54 | 117m |
| g5 | 5518973295… | s0 | 30 | 37 | 19 | **44** | **Golf** | +15.3 | 0 | 15 | 0.18 | 115m |
| g6 | 5725558501… | s1 | 34 | 23 | 32 | **40** | **Golf** | +10.3 | 0 | 25 | 0.48 | 123m |
| g7 | 5227907280… | s2 | 34 | 36 | 36 | **31** | — (Echo/Foxtrot tie @36) | −4.3 | 0 | 4 | 0.37 | 114m |

Aggregate (8 games):

| handle | role | total | mean | outright wins | μ | σ | **μ−3σ** |
|---|---|---|---|---|---|---|---|
| **Echo** | LLM | 274 | 34.2 | 0 | 27.71 | 7.12 | **6.35** |
| **Golf** | freerider | 269 | 33.6 | 3 (g1, g5, g6) | 24.56 | 7.17 | **3.06** |
| **Foxtrot** | LLM | 243 | 30.4 | 3 (g0, g2, g3) | 24.23 | 7.14 | **2.81** |
| **Delta** | LLM | 227 | 28.4 | 1 (g4) | 23.01 | 7.06 | **1.84** |

The freerider is **tied for most outright wins (3)** and 2nd on every axis
(cumulative score, mean, μ−3σ). Echo is the consistent high-placer — highest
cumulative score with *zero* outright wins (never top, never below 23).

### 7.2 First-half (g0–3) vs. second-half (g4–7) — the learning signal

| signal | §5 "right" direction | front half | back half | moved |
|---|---|---|---|---|
| subsidy / game | ↓ falls | 0.75 | **0.00** | ↓ −0.75 — **right way** |
| coalition (LLM↔LLM) / game | ↑ rises | 6.0 | **13.75** | ↑ +7.75 — **right way** |
| hostility → freerider | ↑ rises | 0.364 | 0.394 | ↑ +0.03 — right way (marginal) |
| **freerider margin** | ↓ falls | −0.34 | **+5.58** | ↑ +5.92 — **WRONG way** |
| **freerider wins** | ↓ fewer | 1 | **2** | ↑ — **WRONG way** |

The two **behavioral** withdrawal signals fired cleanly (the table stopped
subsidizing Golf entirely; honest↔honest coalition more than doubled). But both
**outcome** measures went the wrong way: Golf's margin rose and it won *more* of
the later games — its two back-half wins (g5, g6) land in the highest-coalition
regime (15 and 25 LLM↔LLM supports).

### 7.3 OpenSkill standings (leaderboard seed)

Inaugural Ruleset-v1 standings, conservative μ−3σ (PlackettLuce, one identity
per entrant): **Echo 6.35 › Golf 3.06 › Foxtrot 2.81 › Delta 1.84**
(`standings.json`). σ ≈ 7.1 for all four after 8 games, so the three below Echo
are **not well separated** (Golf/Foxtrot/Delta conservative estimates overlap
heavily); the ordering under Echo is provisional. **Echo is the first name on
the Ruleset-v1 ladder.**

### 7.4 Parse-fail (timeout vs. true) + wall-clock

Across all 8 games and both phases (576 LLM decisions = 3 LLM seats × 12 turns ×
2 phases × 8 games; Golf is scripted and makes no LLM calls):

| identity | fell back | **timeout** | transport | **true-parse** | of decisions |
|---|---|---|---|---|---|
| Delta | 14 | 7 | 0 | 7 | 192 |
| Echo | 14 | 7 | 0 | 7 | 192 |
| Foxtrot | 19 | 5 | 0 | 14 | 192 |
| **total** | **47** | **19** | **0** | **28** | **576 → 8.2%** |

**Split: 40% timeout (contention) / 60% true model-side parse / 0% transport.**
No game exceeded the 20% pause guardrail (per-game range 1.4%–15.3%). This split
was the input to the parallel-seat-calls decision: since ~40% of fallbacks are
already contention/timeout at 1 concurrent call, running 4 concurrent `claude
-p` calls/phase would risk inflating that share — one of three reasons the
mid-match hot-swap was declined (stay-plain).

Wall-clock: **15.36 h total engine compute** across all 8 games, **mean 115.2
m/game** (per-game 89–142 m). Calendar span 2026-07-05 17:46 → 2026-07-06 14:31
EDT (~20.8 h) because of **one mid-run reboot** (2026-07-06 05:57), recovered by
crash-resume from a clean 4-game boundary — **zero data loss, seal intact**.
(`run_summary.json` reports these whole-match totals — 576 decisions, 8.2%
parse-fail, 15.36 h engine compute. The resumed process *originally* emitted
resume-leg-only totals — 288 decisions / 7.85 h; the two-reviewer pass caught
that resume-aggregation bug and it was **fixed in this PR**, with the summary
regenerated deterministically from the canonical `sweep.jsonl` + `telemetry.jsonl`
— the sealed data (sweep/telemetry/standings/manifests) is byte-unchanged,
verified by checksum. `match_wall_clock_s` is now engine compute, resume-safe by
construction so a reboot gap cannot inflate it.)

### 7.5 Resolver invariant

**PASS** (see §6): 1 856 one-unit-per-node checks across 8 boards × 20 heuristic
pairings, zero violations; commit-reveal manifest re-verified.

## 8. Verdict

**Headline: NULL on defector-containment — "a Sonnet table does not reliably
dethrone the freerider under Ruleset v1."** Called honestly against the §5 bar,
no spin.

**What happened.** With identity-keyed memory (v1.1) + rotation, the honest
table *detected and behaviorally reacted* to the persistent freerider: subsidy
to Golf fell to zero (0.75 → 0.0/game) and honest↔honest coalition more than
doubled (6.0 → 13.75/game). That is a real, legible positive sub-finding —
memory + the reciprocation ledger were enough to make the table **stop
cooperating with a known defector and close ranks among themselves.**

**But the reaction did not contain the freerider.** The load-bearing outcome
measure the §1/§5 question names — *the freerider's margin falling
game-over-game* — went the **opposite** way (−0.34 → +5.58), and Golf won *more*
of the later games (1 → 2), finishing **tied for most wins (3/8, 38%; random
share ≈ 25%)** and **2nd of 4 on the leaderboard** (μ−3σ 3.06, above two of the
three honest entrants). The two back-half Golf wins land exactly in the
highest-coalition games — consistent with the hypothesis (offered as a
hypothesis, not a claim) that a **tighter, more predictable honest bloc became
more exploitable** by a fixed defector.

**Against the pre-registered §5 bar.** Three of the four listed signals moved
the "right" way (subsidy↓, coalition↑, hostility↑-marginal), a bare majority —
**but the majority is carried entirely by *intent* signals, while both *outcome*
measures the bar also requires (freerider margin falling; freerider winning
fewer later games) failed.** I decline to score this "punishment forms": the
research question is about *containment*, and containment did not occur.
Hostility-toward-freerider was essentially flat (+0.03), so even the behavioral
majority is really two signals, not three. **Verdict: NULL on containment, with
a genuine positive sub-finding on cooperation-withdrawal.**

**Caveats (baked into §5).** n = 8 games, one map archetype, a single *scripted*
`DishonestCooperator` (a fixed exploiter, not an adaptive adversary). The
back-half margin rise leans on two games (g5, g6); g7 Golf placed last. σ ≈ 7.1
leaves the sub-Echo ladder unresolved. No strong claim is made from 8 points —
the persistent ladder does the real convergence. The raw per-game series (§7.1)
is published so the reader can judge the noise.

**Deliverables recorded.** Leaderboard seed: **Echo #1** (first Ruleset-v1
OpenSkill result). Training corpus archived: **24 Sonnet decision-logs / 576
decisions** (`decisions_game{g}_seat{s}.jsonl`), plus transcripts, cross-game
memory, sweep, telemetry — the durable SFT corpus for `M-foedus-gym-pipeline-v0`.
Resolver invariant: **held** (1 856 checks). Seal: **verified** (commit-reveal
`115b9931…de2b`, seeds match sweep). Match integrity: intact across one reboot +
crash-resume, no re-rolls, no prompt edits.
