# Détente firing rate baseline

**Source:** 5000-game sweep on commit `d8442f6`, all 11 heuristics, random pairings, 4p × 15 max-turns × continental_sweep r3, **`peace_threshold=0`** (engine default = `4 + num_players` = 8 consecutive mutual-ALLY turns).

## Headline: 1.3%

| | Count | Pct |
|---|---|---|
| Total games | 5000 | 100% |
| Détente fired | 67 | **1.3%** |
| Average game length when détente fired | 8.00 turns | (= threshold exactly) |
| Average game length otherwise | 15.00 turns | (max) |

Détente cuts game length nearly in half *when it fires*, and always closes a multi-winner collective victory (67/67 ended with all 4 surviving players sharing the win).

## Détente fires only on all-ALLY tables

| Heuristic | Détente rate when present |
|---|---|
| Sycophant | 3.3% |
| Bandwagon | 3.2% |
| TitForTat | 2.7% |
| OpportunisticBetrayer | 2.2% |
| **Aggressive, AntiLeader, ConservativeBuilder, Defensive, Greedy, GreedyHold, Random** | **0.0%** |

Every successful détente had all 4 seats drawn from `{Bandwagon, Sycophant, TitForTat, OpportunisticBetrayer}` — the four heuristics that emit `Stance.ALLY` toward all surviving opponents. **A single Aggressive/AntiLeader/Greedy/etc seat at the table guarantees détente never fires** (those heuristics emit no ALLY or only HOSTILE toward specific targets).

Top compositions producing 100% détente rate (≥5 games each):

- `Bandwagon, Bandwagon, OpportunisticBetrayer, Sycophant`  6/6
- `Bandwagon, Bandwagon, Sycophant, TitForTat`              5/5
- `Bandwagon, OpportunisticBetrayer, Sycophant, Sycophant`  5/5
- `Bandwagon, Sycophant, Sycophant, TitForTat`              6/6

## Why GreedyHold can't trigger détente

GreedyHold's `choose_press` returns `ALLY` toward only the *closest-supply* opponent — not toward all opponents. The détente rule requires the all-pairs mutual-ALLY matrix (every ordered pair `(i, j)` of survivors must have `stance[i][j] == ALLY`). Top-tier tables therefore can't peace out: GH is in tier 1, but its ALLY pattern is sparse, breaking the streak.

This is **a real depth signal** — the rule mechanism actually does what it should: peaceful collective victory requires *publicly committed* peace from everyone, and the strongest expansion strategy doesn't commit to it. Good design.

## The bug: détente can be triggered by lying

Sycophant's `choose_press` returns `Stance.ALLY` toward all opponents — but it plays Greedy under the hood, walking toward enemy supplies and capturing them. OpportunisticBetrayer also declares ALLY while breaking its own Intents to attack exposed enemies. **Both still trigger détente** because the rule only checks declared stance, not consistency with orders.

Consequence: a table of 4 Sycophants closes a "peaceful" collective victory in 8 turns despite all 4 secretly racing for supply expansion underneath. The mechanism rewards the lie, not the peace. Average per-player score at détente is **17.0** (each player held + captured ~17 supplies in 8 turns, exactly the GreedyHold expansion rate).

## What "ought to happen" — design questions surfaced

This baseline doesn't recommend a fix; it surfaces three design questions that need a brainstorming round:

1. **Should détente require zero observed Intent-breaks (or zero unprovoked attacks) during the streak?** Currently broken Intents fire BetrayalObservations but don't reset `mutual_ally_streak`. Tying them together would make Sycophant + OB unable to trigger détente even when present — which is probably the right outcome.

2. **Should HOSTILE-stance-followed-by-attack be a stronger signal than the current binary stance check?** A table where everyone declares ALLY but one player is being constantly dislodged is structurally not a peace.

3. **Is 1.3% the right rate?** Diplomacy has draws but they're rare; 1.3% feels low-but-not-broken. The actual issue is *which* games hit it (currently: only games full of always-ALLY heuristics), not the total count. With the lying-fix proposed above, the rate would drop further — to maybe 0.3% or so — since true all-honest-ALLY tables are mostly Bandwagon-only.

## Reproducible

```sh
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py --num-games 5000 --max-turns 15 \
  --workers 16 --peace-threshold 0 --out /tmp/baseline_detente.jsonl
```

The new `--peace-threshold` flag (default 99 = disabled) lets future sweeps measure how mechanic changes affect the firing rate. Pass `0` for the engine default; pass any positive int for an explicit override.
