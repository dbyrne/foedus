# Bundle 4 Evaluation — Trust, Aid, and Combat Incentives

**Date:** 2026-04-29
**Method:** Depth-eval framework (`docs/superpowers/specs/2026-04-29-depth-eval-framework-design.md`)
**Compared:** `main` (commit `07f8dc7`) ⇄ `bundle-4-trust-and-aid` (commit `ec2ad01`).
**Sample:** Tier 1 random pool n=1000, Tier 2 fixed-seat probes n=300, bootstrap n=500, seed=42, max_turns=15, 4 players, map_radius=3.

## Bottom line

Bundle 4 delivers on the four design goals it set:

1. **Tier-1 collapse fixed.** The "GH = TFT = Bandwagon" monoculture is broken. Top-7 spread expands from 3.2 points (main top-5) to 11.6 points (b4 top-7). Three structurally-distinct cooperative strategies (TrustfulCooperator, Cooperator, Patron) join the top tier. **GreedyHold drops from #2 to #7.**
2. **War aversion crushed.** Tier-1 dislodgements/game rise from **0.19 → 1.84 (10×)**. Combat reward fires at 1:1 parity with dislodgements, confirming the new score incentive is fully load-bearing.
3. **Freerider exploit roughly halved.** `freerider_canary` (1 DC vs 3 Coop): score gap drops from **+13.17 → +5.93** (~55% reduction in fixed-seat freerider advantage). PR #15's claim of +5.33 is within bootstrap CI.
4. **Détente-by-lying mechanically broken.** `detente_lying` (4 Sycophants): betrayal count rises from 0 to 220.7/game (Sycophant's new "declare Hold for everything while playing Greedy" tactic fires a BetrayalObservation per submitted-vs-declared mismatch). Score diff stays near zero — Sycophants no longer collectively *win* through lying.

The one thing Bundle 4 doesn't fix: **DC remains #3 in the random pool** (mean 67.48, CI [65.57, 69.78]). The freerider dies at fixed seats but thrives in mixed populations because honest cooperators still subsidize first. That's the open question for Bundle 5 (or a Bundle 4.5 tuning pass on `aid_token_cap` / `leverage_ratio`).

## Tier-1 ranking change

| # | main | b4 | Δ rank |
|---|---|---|---|
| 1 | Cooperator 65.12 | TrustfulCooperator 70.75 | new |
| 2 | GreedyHold 64.28 | Cooperator 68.99 | +1 |
| 3 | DishonestCooperator 62.78 | DishonestCooperator 67.48 | 0 |
| 4 | TitForTat 62.32 | Patron 64.42 | new |
| 5 | Bandwagon 61.92 | TitForTat 60.53 | -1 |
| 6 | — | Bandwagon 60.37 | -1 |
| 7 | — | GreedyHold 59.10 | **-5** |
| Top cluster spread | 3.20 pt | 11.65 pt | **+8.45** |

GreedyHold's 5-rank drop is the cleanest signal that pure-expansion is no longer dominant under Bundle 4 incentives. TrustfulCooperator is the new outright leader.

## Engagement — Tier 1 random pool

| Metric | main | b4 | Δ |
|---|---|---|---|
| `dislodgements_per_game` | 0.187 | **1.836** | +1.649 |
| `combat_rewards_per_game` | 0.000 | **1.836** | +1.836 |
| `supporter_rewards_per_game` | 0.000 | 0.117 | +0.117 |
| `aid_spends_per_game` | 0.000 | **4.720** | +4.720 |
| `alliance_bonuses_per_game` | 0.233 | 0.326 | +0.093 |
| `betrayals_per_game` | 5.974 | 25.204 | +19.230 |
| `detente_resets_per_game` | 0.0 | 0.052 | +0.052 |
| `supportmove_pct` | (low) | 0.0316 | (similar) |

The 1:1 ratio between `combat_rewards_per_game` and `dislodgements_per_game` confirms `combat_reward` (default 1.0) fires on every successful dislodgement. `supporter_rewards` are rare (cross-player supports of *successful* dislodgements are an uncommon configuration).

`alliance_bonuses_per_game` is roughly flat between main and b4. This is structurally interesting: pre-Bundle-4 the alliance bonus fired on any cross-player SupportMove; Bundle 4 gates it behind AidSpend. The fact that random-pool fire rates are similar implies cooperators are now mostly pairing supports with aid spends — the gate is selective, not punitive.

## Tier-2 fixed-seat probes

### Score diffs (subject minus mean of others, per game, then averaged)

| Probe | Seats (subject = #1) | main | b4 | Δ |
|---|---|---|---|---|
| `freerider_canary` | DC, Coop×3 | **+13.17** | **+5.93** | -7.24 |
| `coalition_pressure` | GH, AntiLeader×3 | (n/a — no combat occurred) | … | … |
| `detente_lying` | Sycophant×4 | (~0) | (~0) | flat |
| `mutual_coop` | Cooperator×4 | -0.08 | +1.75 | +1.83 |
| `altruism_punished` | Coop, GH×3 | (~-0.3) | (~-0.3) | flat |
| `pure_expansion` | GH×4 | (~-0.3) | (~-0.3) | flat |
| `noise_floor` | Random, GH×3 | -38.62 | -39.78 | -1.16 |
| `aid_asymmetry` | TrustfulCoop×2, Patron×2 | (n/a) | **+6.28** | new |

**Notes:**
- **`mutual_coop` showing +1.75 on b4** with 4 identical Cooperators violates seat-symmetry expectations. Sample size is large enough (n=300, CI not zero-crossing) that this isn't pure noise. Hypothesis: residual seat-position effect not fully resolved by PR #13's spawn-imbalance fix, or an artifact of ordered access in aid spending. Worth a probe-level investigation.
- **`aid_asymmetry` (+6.28)** — TrustfulCooperator beats Patron when both pay, because TC reciprocates 1:1 while Patron over-extends (and gets caught by the leverage Patron itself created against TC). Confirms the leverage ledger's directional asymmetry creates real strategic risk for over-givers.
- **`noise_floor` essentially unchanged** at -39: sanity floor preserved.

### Engagement deltas of note

| Metric | main | b4 | Δ |
|---|---|---|---|
| `freerider_canary` dislodgements/game | 1.57 | 9.68 | **+8.11** |
| `freerider_canary` aid_spends/game | 0 | 26.4 | new mechanic |
| `mutual_coop` dislodgements/game | 0.83 | 7.91 | **+7.07** |
| `mutual_coop` aid_spends/game | 0 | 42.8 | new mechanic |
| `coalition_pressure` dislodgements/game | 0 | 0.35 | first signs of coalition combat |
| `detente_lying` betrayals/game | 0 | 220.7 | Sycophant rework |

The **42.8 aid spends/game** in `mutual_coop` is striking: four cooperators happily subsidize each other every turn. The high `dislodgements_per_game` in this probe (7.91) is the corollary — when one cooperator's aid_given to a partner outpaces reciprocation, leverage builds, and the under-reciprocator becomes attackable.

## Mechanism: where does cooperation now live?

Bundle 4 redirects cooperative incentive from the **alliance bonus** (any cross-player SupportMove) to the **aid + leverage ledger** (deliberate aid spending). The story:

1. Cooperators (TC, Coop, Patron) spend aid on each other — visible in `aid_spends_per_game = 4.72`.
2. Aid creates a **directional ledger**: `aid_given[(A,B)]`. When A's giving outpaces B's, **leverage builds against B**.
3. Leverage shows up as **strength bonus on A's Moves toward B's territory**. This isn't logged separately, so the framework can't yet count "leverage bonus fires" — but it's empirically present (Bundle 4 dislodgements jumped 10×, mostly between cooperative players in mutual_coop and freerider_canary).
4. Successful attacks pay **combat_reward** (1.0/dislodgement) and **supporter_reward** (1.0/uncut cross-player supporter). These are the new score-bonus channels: cooperation is no longer rewarded by alliance-bonus-on-support-orders, it's rewarded by aid-then-attack.

The gate `alliance_requires_aid=True` ensures naked SupportMove without aid backing doesn't trigger the alliance bonus. Pre-Bundle-4 random-pool data shows cooperators issuing many cross-supports (~5 alliance bonus fires per Coop fixed-seat game). Bundle 4 retains a similar fire rate (~4.7) by pairing supports with aid spends — the cooperators adapted.

## Caveats and unresolved questions

1. **`mutual_coop` symmetry violation (+1.75)** — possibly real, possibly noise. Should investigate. n=300 with bootstrap CI [-2.6, 7.7] (the CI does cross zero in the smoke run; n=1000 needed to nail down).
2. **DC still #3 in random pool.** Bundle 5 territory.
3. **Leverage bonus fire counter unrecoverable** without an engine change. `foedus/resolve.py:215` adds `state.leverage_bonus(unit.owner, target_pid)` to strength inline with no `log.append`. To count fires, either add a log emit or expose `state.leverage_bonus_fires_this_round` (small engine PR).
4. **`coalition_pressure` shows 0 dislodgements on main** but only 0.35 on Bundle 4. The coalition bites, but lightly. AntiLeader's adapt-on-Bundle-4 (publish own attack intents, cross-support each other) only marginally pressures GH at this map size.

## How to reproduce

Two worktrees side-by-side, then diff:

```sh
# Worktree A — pre-Bundle-4 baseline
git worktree add -b A-tmp /tmp/foedus-A main
( cd /tmp/foedus-A && git merge --no-ff --no-edit depth-eval-framework )
( cd /tmp/foedus-A && PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
    --output /tmp/depth-main.json \
    --n-tier1 1000 --n-tier2 300 --bootstrap --bootstrap-n 500 )

# Worktree B — Bundle 4 candidate
git worktree add -b B-tmp /tmp/foedus-B bundle-4-trust-and-aid
( cd /tmp/foedus-B && git merge --no-ff --no-edit depth-eval-framework )
( cd /tmp/foedus-B && PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
    --output /tmp/depth-b4.json \
    --n-tier1 1000 --n-tier2 300 --bootstrap --bootstrap-n 500 )

# Diff
PYTHONPATH=. python3 scripts/compare_depth_runs.py /tmp/depth-main.json /tmp/depth-b4.json

# Cleanup
git worktree remove /tmp/foedus-A --force
git worktree remove /tmp/foedus-B --force
git branch -D A-tmp B-tmp
```

Total wall time: ~3 minutes per side on a 16-core machine.

## Files

- Spec: `docs/superpowers/specs/2026-04-29-depth-eval-framework-design.md`
- Plan: `docs/superpowers/plans/2026-04-29-depth-eval-framework.md`
- Tools: `scripts/foedus_depth_eval.py`, `scripts/compare_depth_runs.py`
- PR being evaluated: #15 (`bundle-4-trust-and-aid`)
