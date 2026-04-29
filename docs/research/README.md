# Research notes

Empirical investigations of the foedus engine — what we measured, what
we found, what's still open. Each doc is dated and self-contained;
together they form the trail of evidence behind design decisions
made between Bundle 7 and Bundle 8.

## Index

| Date | Doc | Topic |
|---|---|---|
| 2026-04-29 | [bundle-7-baseline.md](2026-04-29-bundle-7-baseline.md) | Original 5000-game baseline (pre seat-fix). Sets the v1 reference numbers for the 11-heuristic roster. |
| 2026-04-29 | [bundle-7-baseline-v2.md](2026-04-29-bundle-7-baseline-v2.md) | Re-run baseline after PR #13 seat-imbalance fix. Tier structure clean; same numbers updated to post-fix code. |
| 2026-04-29 | [depth-and-balance.md](2026-04-29-depth-and-balance.md) | What the v2 baseline reveals about strategic depth: three-tier structure, Tier-1 statistical tie, 91% no-dislodgement games, betrayer mechanic decorative. Five recommendations. |
| 2026-04-29 | [detente-baseline.md](2026-04-29-detente-baseline.md) | How often the détente collective-victory fires (1.3% with default threshold), which heuristics enable it (only ALLY-everyone agents), and the détente-by-lying bug. |
| 2026-04-29 | [alliance-bonus-experiment.md](2026-04-29-alliance-bonus-experiment.md) | Quick alliance-multiplier prototype + Cooperator + DishonestCooperator. Confirms the mechanism creates a second Tier-1 strategy at bonus=3, and the freerider exploit is real (visible in fixed-seat tests, hidden in random-pool tests). |

## How to reproduce any of these

All sweeps use `scripts/foedus_sim_sweep.py` and `scripts/foedus_sim_analyze.py`.

```sh
# v2 baseline (alliance bonus on by default = 3):
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
  --num-games 5000 --max-turns 15 --workers 16 \
  --out /tmp/baseline.jsonl
PYTHONPATH=. python3 scripts/foedus_sim_analyze.py /tmp/baseline.jsonl

# v1 scoring (no alliance bonus):
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
  --num-games 5000 --max-turns 15 --workers 16 \
  --alliance-bonus 0 \
  --out /tmp/baseline_no_bonus.jsonl

# Détente firing rate:
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
  --num-games 5000 --max-turns 15 --workers 16 \
  --peace-threshold 0 \
  --out /tmp/detente.jsonl

# Cross-config knob study:
for r in 2 3 4 5; do
  for n in 2 3 4 6; do
    PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
      --num-games 5000 --max-turns 15 --workers 16 \
      --map-radius $r --num-players $n \
      --out /tmp/r${r}_n${n}.jsonl
  done
done

# Fixed-seat exploit test (the depth-loud benchmark):
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
  --num-games 5000 --max-turns 15 --workers 16 \
  --seats "DishonestCooperator,Cooperator,Cooperator,Cooperator" \
  --out /tmp/dc_exploit.jsonl
```

## Key sweep flags introduced this round

| Flag | Default | Purpose |
|---|---|---|
| `--workers N` | 1 | ProcessPoolExecutor parallelism. Use `0` for `os.cpu_count()`. ~7× speedup on 16-core. |
| `--map-radius R` | 3 | Hex-disk radius. r=2 is ~19 nodes (crowded), r=5 is ~91 nodes (sparse). |
| `--num-players N` | 4 | Player count. 6p compresses tier structure; 2p amplifies it. |
| `--archetype A` | continental_sweep | Map type: continental_sweep / highland_pass / riverlands / uniform. |
| `--roster A,B,C` | all 13 | Restrict the random pool to a subset. |
| `--seats A,B,C,D` | unset | Fixed assignment per game (length must match num-players). Required for adversarial / exploit tests. |
| `--peace-threshold T` | 99 (off) | Détente threshold. `0` uses engine default. |
| `--alliance-bonus B` | engine default (3) | Alliance-capture bonus. `0` = v1 scoring. |

## Open questions for the next round

1. **Does Bundle 4's real spec hold up under fixed-seat adversarial tests?** Any proposed Intent-break consequence design needs to push DC ≤ Cooperator in `1 DC vs 3 Coop` *and* in random pools.
2. **Sycophant vs OpportunisticBetrayer** — currently statistically equivalent. Does any Intent-break penalty design split them visibly?
3. **Does détente-by-lying (Sycophant tables triggering peaceful collective victory) get fixed for free** by Intent-break consequences, or does it need its own rule (e.g., observed Intent-break resets `mutual_ally_streak`)?
4. **Is the GreedyHold/Bandwagon/TitForTat tier-1 tie a problem** or a feature? The data say they're statistically indistinguishable; is this OK because they declare different stances, or should it be visible in scoring too?
