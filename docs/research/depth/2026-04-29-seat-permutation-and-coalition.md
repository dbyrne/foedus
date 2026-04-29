# Seat Permutation + Coalition-Pressure Investigation

**Date:** 2026-04-29 (post-Bundle-5b session)
**Branch:** `seat-permutation`
**Sample:** Tier 1 random pool n=1000, Tier 2 fixed-seat probes n=300, bootstrap n=500, seed=42, max_turns=15.
**Compares:** unpermuted Tier-2 (from `2026-04-29-post-bundle5b-evaluation.md`) ⇄ permuted Tier-2 (this run, same main commit `e7bc3f8`).

This addresses the two follow-ups parked in the post-Bundle-5b evaluation:

1. **Seat permutation** in fixed-seat probes (eliminates the residual ~5% player-ID-tiebreak bias).
2. **Coalition-pressure investigation** (probe got *worse* post-Bundle-5b).

## 1. What permutation does

For each Tier-2 probe, the orchestrator now:

- Computes the unique permutations of `probe.seats` (4×Coop → 1; 1 DC + 3 Coop → 4; 2 TC + 2 Patron → 6).
- Splits `n_tier2` games evenly across the permutations, same seed each.
- Concatenates the records.
- Identifies the subject by **agent class** (`probe.seats[probe.subject_index]`), not seat index.
- `score_diff = mean(scores at subject-agent seats) - mean(scores at non-subject seats)`, averaged across games.

For all-same probes (mutual_coop, pure_expansion, detente_lying), there's no contrast group; `score_diff` is 0 by definition. This is correct: those probes measure engagement and absolute behavior, not differential.

## 2. Tier-2 results: unpermuted vs permuted

Same n_tier2=300, same engine state (current main).

| Probe | Subject | Unperm. | Permuted | Δ |
|---|---|---|---|---|
| `freerider_canary` | DC vs 3 Coop | +7.44 | **+5.98** | -1.46 |
| `coalition_pressure` | GH vs 3 AL | +16.72 | **+31.37** | **+14.65** |
| `detente_lying` | (4 Sycophant) | ≈0 | 0.00 | — |
| `mutual_coop` | (4 Coop) | +1.69 | **0.00** | -1.69 |
| `altruism_punished` | Coop vs 3 GH | ≈-0.30 | **-0.00** | seat-noise neutralized |
| `pure_expansion` | (4 GH) | ≈-0.30 | 0.00 | seat-noise neutralized |
| `noise_floor` | Random vs 3 GH | -46.90 | **-48.45** | -1.55 |
| `aid_asymmetry` | TC vs Patron (2v2) | +6.61 | **+23.32** | **+16.71** |

### Headline observations

- **All-same probes go to exactly 0** as designed. The previous +1.69 in `mutual_coop` and -0.30 in `pure_expansion` were pure seat-bias artifacts.
- **`freerider_canary` barely moved** (-1.46). The DC-vs-3-Coop effect is not seat-position-dependent; it's a real strategic mismatch. Final permuted CI: [+2.47, +9.03].
- **`coalition_pressure` nearly doubled (+16.72 → +31.37)**. The unpermuted result was *understating* GH's advantage because GH was always at seat 0 (vulnerable position relative to 3-AL coordination), while seats 1–3 had average bias 0. Permuted reveals GH wins by ~31 points across all seat assignments. **The 3-AntiLeader coalition is much weaker than we thought.**
- **`aid_asymmetry` more than tripled (+6.61 → +23.32)**. Permutation lets us see TC's reciprocation strategy clearly dominates Patron's give-then-defect strategy in 2v2. Engagement metrics show this probe is the most Bundle-4-loaded scenario in the battery: 45.7 aid_spends/game, 23.5 leverage_bonuses/game, 12.4 dislodgements/game.

## 3. Coalition pressure investigation

The permuted +31.37 result, combined with engagement metrics, paints a clear picture:

```
coalition_pressure (1 GH vs 3 AntiLeader) — permuted, n=300
  dislodgements/game           = 0.43   (low; 3-AL coalition rarely lands a kill on GH)
  aid_spends/game              = 2.17   (some coordination via aid)
  combat_rewards/game          = 0.43   (= dislodgements; combat reward fires)
  supporter_rewards/game       = 0.36   (cross-player supports DO occur)
  leverage_bonuses/game        = 0.02   (coalition can't accumulate leverage; GH never spends aid)
  betrayals/game               = 53.82  (heavy intent traffic; AL is verbose about coalition)
  supportmove_pct              = 0.165  (16.5% of orders are SupportMove — coalition is trying!)
```

**The mechanism failure** is now clear:

- AntiLeaders DO publish supports (16.5% supportmove rate is high) and DO spend aid on each other (2.2/game).
- But they rarely land a dislodgement (0.43/game) — barely above noise.
- And they accumulate ~zero leverage on GH (0.02/game) because GH never spends aid, so there's no leverage gradient pointing at GH to weaponize.

The Bundle 4 leverage system is **directional**: it fires when player A has subsidized B more than B has subsidized A. Since GH never participates in aid, no leverage ever accumulates against it. The coalition's only weapon against GH is *raw combat support*, which Bundle 4 modestly reinforces (supporter_reward = 0.36/game) but doesn't transform.

Worse: Bundle 5b made GH *stronger* (variable supply values reward unit deployment skill, which GH has). Net result: ALs work harder to coordinate but lose by more.

### Implication for design

The leverage system can't pressure a non-participant. To make coalitions effective against pure-expansion strategies, future bundles need a mechanic that:

- (a) Lets cooperators **directly damage** non-cooperators via combat coordination (Bundle 4 already provides this via supporter_reward, but the magnitude is small).
- (b) Or makes pure-expansion strategies **structurally pay** for not engaging with the trust system (e.g., a small score penalty for never spending aid, or a "isolation tax").
- (c) Or strengthens cross-player SupportMove resolution mechanics so coordinated 3-on-1 attacks reliably overwhelm a defender.

Out of scope for this PR. Worth flagging as a Bundle 6 candidate.

## 4. Implementation notes

- `Probe.subject_index` is now derived to a `subject_agent` (class name) at runtime. The probe registry didn't change; the orchestrator looks up `probe.seats[probe.subject_index]` and passes the agent class to metrics.
- New helper: `_unique_seat_permutations(seats)` in `scripts/foedus_depth_eval.py`. 5 unit tests cover the cases (all-same, 1-distinct, 2-pairs, all-distinct, deterministic order).
- New metrics path: `probe_score_diff(records, subject_agent="ClassName")` and `probe_per_game_diffs(records, subject_agent=...)`. The legacy `subject_index` path is retained for backward compat.
- All 478 tests pass (was 473 + 5 new permutation tests).

## 5. How to reproduce

```sh
PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
    --output /tmp/depth-permuted.json \
    --n-tier1 1000 --n-tier2 300 \
    --bootstrap --bootstrap-n 500
```

About 5 minutes wall time on 16 cores. Each probe runs N permutations sequentially internally (small n per perm), with parallelism across probes.

## 6. Aggregate verdict

- ✅ Seat-position bias eliminated from probe results.
- ✅ All-same probes return clean 0 for score_diff (correct).
- ✅ Mixed probes give honest "role" effect averaged over seat assignments.
- 📊 Permutation reveals the **GH-vs-3-AL coalition is much weaker** than unpermuted measurement suggested. Bundle 6 candidate.
- 📊 Permutation reveals **TC dominates Patron in 2v2** by 23+ points — the leverage ledger creates real strategic risk for over-givers, as designed.

## Files

- Spec: `docs/superpowers/specs/2026-04-29-depth-eval-framework-design.md`
- Plan: `docs/superpowers/plans/2026-04-29-depth-eval-framework.md`
- Prior: `docs/research/depth/2026-04-29-post-bundle5b-evaluation.md`
