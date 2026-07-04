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
| Games | `<N>` (8 = two full rotation cycles; or 4 = one cycle) |

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

> **Pinned for this run:** `<A / B / C>` — `<one-line rationale from Nova>`.

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
to hold across every finalized turn of the campaign (see §8). `<PASS/FAIL>`.

---

## 7. Results

> _Filled in after the match from `scorecard.json` + `standings.json`._

### 7.1 Per-game scorecard + trajectory

_TODO(run): table of game · seed · freerider seat · won · margin · subsidy ·
coalition · hostility · wall-clock._

### 7.2 First-half vs. second-half (the learning signal)

_TODO(run): subsidy / coalition / margin / hostility deltas._

### 7.3 OpenSkill standings

_TODO(run): μ / σ / μ−3σ per entrant._

### 7.4 Parse-fail (timeout vs. true) + wall-clock

_TODO(run): per-entrant fallback split; match wall-clock; mean min/game._

## 8. Verdict

> _Filled in after the match — honest, against the §5 bar._

_TODO(run): did the defector get punished? PASS / NULL / ANTI, with the
mechanism. Leaderboard seed recorded. Corpus archived (N decision-logs). Resolver
invariant held._
