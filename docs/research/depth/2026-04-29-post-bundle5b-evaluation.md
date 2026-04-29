# Post-Bundle-5b Evaluation + Leverage Counter + Mutual-Coop Investigation

**Date:** 2026-04-29 (late session)
**Compared:** pre-Bundle-4 (`07f8dc7`) ⇄ post-Bundle-5b + leverage emit (`237c0ed`).
**Sample:** Tier 1 random pool n=1000, Tier 2 fixed-seat probes n=300, bootstrap n=500, seed=42.
**Plus:** Focused mutual_coop probe at n=2000, bootstrap n=1000.

This combines three follow-ups from the Bundle 4 evaluation:

1. **Leverage bonus counter unblocked** (PR #19 added the engine emit). The framework can now measure how often the leverage strength bonus actually fires.
2. **Cumulative evaluation** of Bundles 4+5b together against the pre-Bundle-4 baseline.
3. **Investigation** of the mutual_coop symmetry violation flagged in the Bundle 4 evaluation.

## 1. Cumulative impact (pre-Bundle-4 → post-Bundle-5b)

### Tier-1 ranking restructure

| # | pre-Bundle-4 (top 5) | post-Bundle-5b (top 8) |
|---|---|---|
| 1 | Cooperator 65.12 | TrustfulCooperator 80.29 |
| 2 | GreedyHold 64.28 | DishonestCooperator 76.52 |
| 3 | DishonestCooperator 62.78 | Cooperator 74.81 |
| 4 | TitForTat 62.32 | Patron 73.09 |
| 5 | Bandwagon 61.92 | ValueGreedy 69.55 |
| 6 | — | TitForTat 69.16 |
| 7 | — | GreedyHold 69.10 |
| 8 | — | Bandwagon 65.69 |
| Top-cluster spread | 3.20 pt | **14.60 pt** |

GH dropped from #2 to #7. The new value-aware heuristic (ValueGreedy, from Bundle 5b) inserts at #5, sitting clearly above the old GH/TFT/Bandwagon cluster but below the cooperators. The two new Bundle-4-specific cooperative agents (TrustfulCooperator, Patron) join DC and Cooperator at the top. **Eight strategies with a 14.6 point spread** — the deepest top-tier the meta has shown.

### Engagement deltas

| Metric | pre-b4 | post-5b | Δ |
|---|---|---|---|
| `dislodgements_per_game` | 0.187 | **1.735** | +1.548 (9×) |
| `combat_rewards_per_game` | 0.000 | 1.735 | new (1:1 with dislodgements) |
| `supporter_rewards_per_game` | 0.000 | 0.125 | new |
| **`leverage_bonuses_per_game`** | 0.000 | **2.517** | **first measurement** |
| `aid_spends_per_game` | 0.000 | 4.472 | new |
| `alliance_bonuses_per_game` | 0.000 | 0.262 | new |
| `betrayals_per_game` | 5.974 | 22.184 | +16.21 |
| `detente_resets_per_game` | 0.0 | 0.042 | new |

**Leverage fires at 2.5/game** — the previously-invisible mechanic is now empirically active. Compare to `aid_spends_per_game = 4.47`: roughly half of all aid spends eventually translate into a Move that carries leverage strength. Combined with `combat_rewards_per_game = 1.735` (which equals dislodgements 1:1), the causal chain is now legible: aid → leverage → strike.

### Tier-2 score diffs

| Probe | pre-b4 | post-5b | Δ |
|---|---|---|---|
| `freerider_canary` (DC vs 3 Coop) | +13.17 | **+7.44** | -5.73 (~44% reduction) |
| `coalition_pressure` (1 GH vs 3 AL) | +13.67 | +16.72 | +3.06 (worse) |
| `mutual_coop` | -0.08 | +1.69 | +1.76 (seat effect, see §3) |
| `noise_floor` (Random vs 3 GH) | -38.62 | -46.90 | -8.28 (b5 makes GH stronger) |
| `aid_asymmetry` (TC×2 vs Patron×2) | n/a | +6.61 | new |

**Notable:** `coalition_pressure` *worsened*. The 3-AntiLeader coalition pressures GH less effectively after Bundle 5b — likely because variable supply values give skilled GH (and ValueGreedy) a structural premium that AL's coordination doesn't compensate for. Worth a separate look.

## 2. Leverage counter — first measurement

The PR #19 log emit (`leverage bonus +N to pX (via uY) vs pZ`) lets the framework count leverage fires. Per-game means in the post-Bundle-5b sweep:

| Context | leverage_bonuses_per_game |
|---|---|
| Tier-1 random pool | 2.52 |
| `freerider_canary` (DC + 3 Coop) | tier-2 captures it; cooperators leverage DC heavily |
| `mutual_coop` (4 Coop) | 3.52 (one Coop leverages another every 4 turns or so) |

Combined with the existing counters, the full Bundle-4 mechanic chain is now measurable end-to-end:

```
aid_spends → leverage_bonuses → combat_rewards
   4.47          2.52            1.74
   ────────────────────────────────────────
   spent      half eventually    half become
              fire a bonus       dislodgements
```

This is the first time we can verify the "spend creates leverage creates strike" causal chain by counting each step.

## 3. The mutual_coop symmetry violation — explained

The Bundle 4 evaluation flagged that `mutual_coop` (4 identical Cooperators) showed a +1.75 score_diff for seat 0. We promised an investigation at higher n.

### Investigation: per-seat means at n=2000

```
Seat | Mean | Median | StdDev | vs mean(others)
-----+------+--------+--------+----------------
  0  | 74.51 | 74.00 | 23.07 |   +2.23
  1  | 73.73 | 73.00 | 23.45 |   +1.19
  2  | 72.44 | 71.00 | 23.44 |   −0.54
  3  | 70.68 | 70.00 | 22.78 |   −2.88
```

The asymmetry is **real, monotone, and matches PR #13's reported residual**. Seat-spread is 3.83 points, ~5% of mean — exactly the residual PR #13 left after the spawn-imbalance fix (60% → 5%).

So the +1.75 we saw earlier in the Bundle 4 probe wasn't a Bundle-4 artifact — it's the pre-existing residual seat effect, *visible* in this probe specifically because mutual_coop puts four identical agents under the only thing that distinguishes them: their player ID.

### Likely cause

Player-ID tiebreaks during simultaneous order resolution. When Cooperators issue identical-target orders or contend for the same supply, deterministic resolution rules favor lower IDs. Across 15 turns, this accumulates.

### Recommendation

This is a Tier-2 follow-up, not a Bundle 4 (or 5b) regression. Possible directions:
1. **Document** the residual as a known caveat in `tests/test_seat_imbalance.py` (or wherever PR #13's regression test lives) and accept it.
2. **Randomize** the player-ID order for tiebreaks each turn (would eliminate the bias but adds noise).
3. **Per-game seat permutation** during sweeps — seat assignment becomes part of the random pool randomization.

For mechanic evaluation, the cleanest fix is **(3)**: rotate the cooperator-class assignments across seats in fixed-seat probes, average over rotations. The depth-eval framework could do this internally without engine changes.

## 4. How to reproduce

Three sweeps:

```sh
# Pre-Bundle-4 baseline (cherry-pick framework onto 07f8dc7)
git worktree add -b A-tmp /tmp/foedus-A 07f8dc7
( cd /tmp/foedus-A && git cherry-pick c0ea872 )
( cd /tmp/foedus-A && PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
    --output /tmp/depth-pre-b4.json \
    --n-tier1 1000 --n-tier2 300 --bootstrap --bootstrap-n 500 )

# Current main (post Bundle 4 + 5b + leverage emit)
PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
    --output /tmp/depth-post-5b.json \
    --n-tier1 1000 --n-tier2 300 --bootstrap --bootstrap-n 500

# mutual_coop deep dive
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
    --num-games 2000 --max-turns 15 \
    --seats Cooperator,Cooperator,Cooperator,Cooperator \
    --out /tmp/mutual-coop-raw.jsonl --seed-offset 42

# Diff
PYTHONPATH=. python3 scripts/compare_depth_runs.py \
    /tmp/depth-pre-b4.json /tmp/depth-post-5b.json
```

## 5. Aggregate verdict

Bundle 4 + Bundle 5b together:

- ✅ Tier-1 spread expanded **3pt → 14.6pt** (8 viable strategies)
- ✅ War aversion crushed (9× combat rate)
- ✅ Freerider exploit reduced 44% even at fixed seats
- ✅ Aid + leverage + combat-reward chain fully instrumented and measurable
- ✅ Sycophant detente exploit broken
- ⚠️ Coalition pressure on the leader *worse* post-5b (variable supply values reward skilled GH/VG)
- ⚠️ ~5% seat-position residual still present (known, pre-existing)

**Recommendation:** No regression. Two follow-up flags (coalition vs variable supply, seat permutation in fixed-seat probes) but neither blocks shipping.

## Files

- Spec: `docs/superpowers/specs/2026-04-29-depth-eval-framework-design.md`
- Plan: `docs/superpowers/plans/2026-04-29-depth-eval-framework.md`
- Prior: `docs/research/depth/2026-04-29-bundle4-evaluation.md`
- PRs: #15 (Bundle 4), #17 (Bundle 5b), #18 (depth-eval framework), #19 (leverage emit)
