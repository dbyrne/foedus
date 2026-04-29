# Depth Eval Framework — Design

**Status:** Spec, ready for implementation plan.
**Date:** 2026-04-29.

## 1. Motivation

Through Bundles 6–7 and the alliance/reciprocity work, every mechanic
change has been evaluated by a hand-written research document: pick some
scenarios, run the sweep, eyeball the numbers, write the markdown. This
is unrepeatable — each baseline picks a slightly different probe set,
different sample sizes, different metrics. Comparing two bundles means
re-reading two docs.

We need a fixed battery of measurements that runs the same way every
time, emits a structured artifact, and supports machine-readable
before/after comparison. The framework should let us answer two
questions cheaply for any candidate change:

1. *What does the meta look like right now?* (Snapshot.)
2. *What did this change do?* (Diff against a previous snapshot.)

It should also be easy to add or remove probes as the agent roster and
mechanic surface evolve.

## 2. Goals and non-goals

### Goals

- Single command produces a depth report (JSON + Markdown) for the
  current engine + agent state.
- Same probes, sample sizes, seeds, and pinned config every run, so
  results are diff-able.
- Report covers three readouts: mechanic engagement, counterplay
  (pairwise win-rate matrix), and fragility (random-pool vs
  fixed-seat).
- A second command produces a delta table comparing two reports.
- Probe list and engagement counters are extensible by a single-line
  edit.
- Knob-sweep mode (Tier 3) for evaluating a *new* mechanic by sweeping
  one of its parameters.

### Non-goals

- Replacing the ad-hoc research docs entirely. They capture narrative
  and judgement; this framework captures the numbers underneath them.
- Replacing the pytest suite. Depth eval is statistical evaluation of
  agent behaviour, not correctness testing.
- New agent training infrastructure. v2 NN training is out of scope.

## 3. The three readouts

| Readout | Question | How measured |
|---|---|---|
| **(D) Engagement** | Are the mechanics actually used? | Per-game counters (dislodgements, SupportMove, SupportHold, AidSpend, leverage-bonus fires, alliance-bonus fires, BetrayalObservations, détente streak-resets) → tier-1 means + per-probe means. |
| **(B) Counterplay** | Does each top strategy have a counter? | Pairwise win-rate matrix from tier-1 random pool. Cycles → strategic depth; dominance → shallow. |
| **(E) Fragility** | Does the meta hold under adversarial seating? | Gap between an agent's random-pool ranking and its score in fixed-seat probes. Cooperator winning random pool but losing `1 DC vs 3 Coop` is a fragility signal. |

## 4. Probe battery

### Tier 1 — Random pool

- Full heuristic roster, 4 random seats per game.
- `n=2000` games (overrideable).
- Pinned seed (overrideable via `--reseed`).
- Powers all of (D), (B), and the random-pool half of (E).

### Tier 2 — Fixed-seat canaries

Each probe is a named entry; `n=500` per probe by default; pinned seed;
parallelizable across probes.

| Name | Seats | What it canaries |
|---|---|---|
| `freerider_canary` | DC, Coop, Coop, Coop | Freerider exploit on cooperators. |
| `coalition_pressure` | GH, AntiLeader, AntiLeader, AntiLeader | Whether coordinated counter-leader play can pressure GH. |
| `detente_lying` | Sycophant×4 | Détente-by-lying bug: closes peaceful collective victory while breaking declared intents. |
| `mutual_coop` | Cooperator×4 | Do honest cooperators cooperate without an exploiter present? |
| `altruism_punished` | Coop, GH, GH, GH | Cost of being the only cooperator. |
| `pure_expansion` | GH×4 | Score-victory baseline; engagement floor. |
| `noise_floor` | Random, GH, GH, GH | Sanity: GH should beat noise. |
| `aid_asymmetry` | TrustfulCoop×2, Patron×2 | Bundle 4: pay-fairly vs subsidize-then-defect. |

The list lives as a Python list in `scripts/foedus_depth_eval.py`;
adding/removing a probe is one entry.

### Tier 3 — Knob sweep (on demand only)

`--knob-sweep <param>=<v1>,<v2>,...` reruns Tier 1 at each value of one
config knob and emits a sensitivity table. Not part of the standard
battery; used when evaluating a single mechanic's parameterization.

## 5. Pinned config

| Setting | Value |
|---|---|
| Players | 4 |
| Map | `continental_sweep`, radius 3 |
| `max_turns` | 15 |
| Engine knobs | Defaults shipping at the time of the run (current default = Bundle 4 on). |

Overrideable via flags; canonical runs use these values.

## 6. Artifact

### File layout

```
docs/research/depth/
  2026-04-29-bundle4-shipping.json     # machine-readable
  2026-04-29-bundle4-shipping.md       # auto-rendered from JSON
  2026-04-30-bundle5-rfc.json
  2026-04-30-bundle5-rfc.md
```

### JSON shape (sketch)

```json
{
  "run_id": "2026-04-29-bundle4-shipping",
  "git_sha": "ec2ad01",
  "git_branch": "bundle-4-trust-and-aid",
  "timestamp": "2026-04-29T15:23:11Z",
  "config": {
    "players": 4,
    "map_radius": 3,
    "max_turns": 15,
    "aid_token_cap": 10,
    "alliance_bonus": 3,
    "combat_reward": 1.0,
    "...": "..."
  },
  "stat_rigor": "bootstrap",
  "n_bootstrap_resamples": 1000,
  "tier1_random_pool": {
    "n_games": 2000,
    "seed": 42,
    "rankings": [
      { "agent": "TrustfulCooperator", "mean_score": 70.51,
        "ci95": [69.84, 71.18], "n_appearances": 727 }
    ],
    "pairwise_winrate": {
      "row_agents": ["GreedyHold", "Cooperator", "..."],
      "col_agents": ["GreedyHold", "Cooperator", "..."],
      "matrix":     [[null, 0.52, 0.48], [0.48, null, 0.51], "..."]
    },
    "engagement": {
      "dislodgements_per_game": 1.88,
      "support_move_pct": 0.041,
      "support_hold_pct": 0.012,
      "aid_spend_pct": 0.18,
      "leverage_bonuses_fired_per_game": 0.71,
      "alliance_bonuses_fired_per_game": 0.34,
      "betrayals_observed_per_game": 1.4,
      "detente_streak_resets_per_game": 0.6
    }
  },
  "tier2_probes": [
    {
      "name": "freerider_canary",
      "seats": ["DishonestCooperator", "Cooperator", "Cooperator", "Cooperator"],
      "n": 500,
      "score_diff": -5.33,
      "ci95": [-6.10, -4.55],
      "interpretation": "DC − mean(Coop)",
      "engagement": { "...": "..." }
    }
  ],
  "tier3_knob_sweep": null
}
```

### Markdown report

Generated from the JSON at write time. Sections: header (run_id, sha,
timestamp, config), Tier 1 ranking table, pairwise win-rate matrix
heat-map, engagement table, Tier 2 probe table, Tier 3 sweep (if
present). The Markdown is regeneratable from the JSON; the JSON is
canonical.

## 7. Comparison

`scripts/compare_depth_runs.py before.json after.json` prints a delta
table on metrics that moved by more than a printable epsilon (default:
0.05 for rates, 0.5 for score-diffs, 5pp for percentages). Non-moving
metrics are dropped from the table. Optional `--full` prints all
metrics regardless.

Sample output:

```
                              before    after    Δ
dislodgements/game             0.17     1.88   +1.71
support_move_pct               2.2%    4.1%   +1.9pp
freerider_canary (DC−Coop)    +10.7    +5.33  −5.37
sycophant_detente_rate         100%      0%   −100pp
```

## 8. Stat rigor

`--bootstrap / --no-bootstrap`. Default off (point estimates only).
With `--bootstrap`, every Tier-1 ranking entry, every Tier-2 score
diff, and every pairwise winrate entry gets a 95% bootstrap confidence
interval (1000 resamples by default; `--bootstrap-n` overrideable).
Bootstrap is applied to the per-game outcome list, not to the raw
score, so ties and ordering effects are preserved.

Use point estimates for fast iteration during a session; commit a
bootstrap run when finalizing a result for a research doc or PR.

## 9. Code layout

### New files

- `scripts/foedus_depth_eval.py` — orchestrator. Parses args, builds
  per-probe sweep invocations, dispatches via
  `concurrent.futures.ProcessPoolExecutor` (one worker per probe is
  fine; each probe's own sweep runs further parallelism internally if
  desired), aggregates JSONL, computes metrics, writes the JSON +
  Markdown artifact.
- `scripts/compare_depth_runs.py` — delta tool.

### Modified files

- `scripts/foedus_sim_sweep.py` — add per-game JSONL fields:
  - `aid_spends_count`
  - `leverage_bonuses_fired`
  - `alliance_bonuses_fired`
  - `betrayals_observed`
  - `detente_streak_resets`
  Counter sources from existing engine state where possible:
  `state.round_aid_pending` (spends submitted), the
  `BetrayalObservation` list (betrayals), `state.mutual_ally_streak`
  transitions (détente resets), and `state.aid_given` deltas across
  turns (which double as the leverage-bonus-fired witness when the
  bonus is computed at resolution time).
- The implementation plan must verify whether Bundle 4 emits
  resolution-log lines for leverage-bonus and alliance-bonus fires;
  if not, it picks one of two paths: (a) derive counts from state
  deltas and the resolution log entries that already exist, without
  engine changes; (b) add minimal counter fields to `GameState`
  (e.g., `last_round_alliance_bonus_fires: int`) populated by
  `_resolve_orders`. (a) is preferred — engine stays pure; (b) is
  acceptable if the data isn't otherwise recoverable.

### New directory

- `docs/research/depth/` — artifact location.

## 10. Tests

- `tests/test_depth_eval.py`:
  - End-to-end smoke: run depth-eval with `--n-tier1 10
    --n-tier2 5 --probes freerider_canary,pure_expansion --no-bootstrap`,
    parse the resulting JSON, assert structural correctness.
  - Counters present and non-negative in the rendered Tier 1
    engagement section.
  - With `--bootstrap`, every score has a populated `ci95` field.
- `tests/test_compare_depth_runs.py`:
  - Construct two synthetic JSON artifacts that differ by exactly one
    metric; assert the comparator prints a one-row delta table.
  - Construct two identical artifacts; assert empty delta table
    (without `--full`) and full table (with `--full`).
- `tests/test_sim_sweep_engagement_counters.py`:
  - Run a single tiny sweep with Bundle 4 on; assert the new counter
    fields exist on every JSONL line and are non-negative integers.

## 11. Open questions

1. **Pairwise winrate normalization.** With 4-player free-for-all
   games, "A beat B" is ambiguous. Candidate definitions:
   a. *Score-rank within game.* `winrate(A,B) = P(A's score > B's score | both in game)`.
   b. *Solo-win share.* `winrate(A,B) = P(A is sole highest scorer | both in game)`.
   c. *Pairwise mean diff.* Not a winrate, but a signed score
      difference. Drops the rock-paper-scissors readout.
   
   Lean: (a). Defer choice to implementation; record the chosen
   definition in the JSON's metadata.

2. **Tier 2 probe stability.** Some probes (`mutual_coop`,
   `pure_expansion`) may have near-zero variance once the meta
   stabilises and become uninformative. Plan: keep them; the
   compare-runs tool will simply not surface them. Cost is low.

3. **Per-probe knob overrides.** Should a probe be able to override
   the global config (e.g., `detente_lying` with
   `--peace-threshold=0`)? Lean: yes, allow per-probe `config_override`
   dicts in the `PROBES` list. This is an implementation detail; lock
   in the plan.

4. **Trend chart across runs.** Out of scope for this spec, but the
   JSON shape is designed so that a future tool can ingest a directory
   of artifacts and render trend charts. No work to do now.

## 12. Acceptance criteria

- `python3 scripts/foedus_depth_eval.py --output docs/research/depth/$(date -I)-bundle4.json`
  completes in <5 minutes on a 16-core machine, produces a valid JSON
  artifact, and writes a sibling Markdown report.
- `python3 scripts/compare_depth_runs.py A.json B.json` prints a
  delta table and exits 0.
- `pytest tests/test_depth_eval.py tests/test_compare_depth_runs.py
  tests/test_sim_sweep_engagement_counters.py` passes.
- The Bundle 4 PR's hand-counted numbers (DC freerider +5.33, détente
  rate 0%, dislodgements/game 1.88) reproduce within bootstrap CI when
  the framework is run against `bundle-4-trust-and-aid`.
