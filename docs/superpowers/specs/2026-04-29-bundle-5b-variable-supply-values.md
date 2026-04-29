# Bundle 5b (C3) — Variable Supply Values

**Status:** Implementation complete; awaiting empirical validation.
**Date:** 2026-04-29.

## 1. Motivation

The post-Bundle-4 baseline (5000-game sweep with full heuristic adaptation; see foedus#15 PR description) shows GreedyHold's pure-expansion strategy still outperforms coalition play (DC retains a +5.33 fixed-seat advantage; AntiLeader still loses on raw score to GH despite gaining real combat dislodgements). The structural problem is that **all supplies score +1 per turn**, so a strategy that maximizes raw count is optimal regardless of *which* supplies it controls. There's no positional preference embedded in the map.

Bundle 5b introduces **variable supply values** as a heterogeneity-injection: ~5% of non-HOME SUPPLY nodes yield +2 score per turn instead of +1. Maps stop being interchangeable, and strategies that prioritize *which* supply to take (Bandwagon, future value-aware agents) gain a real advantage over count-maximizers (GreedyHold).

## 2. Goals and non-goals

### Goals
- Add per-supply value heterogeneity at modest scale (5%, value=2 only — first pass).
- Differentiate Bandwagon-style "join-the-leader-on-the-+2" from GreedyHold's count-maximization in the score-victory regime.
- Keep the engine simple — no per-turn variation, no fog of value.
- Backward-compatible: setting `high_value_supply_fraction=0` returns to v1 uniform scoring.

### Non-goals
- A tier of value=3 supplies (deferred until +2 is measured).
- Archetype-specific value placement (continental_sweep places value uniformly; archetype hooks land later).
- Fog-of-value: high-value supplies are public knowledge.
- Variable HOME values — homes always yield 1.

## 3. Locked design decisions

| Dimension | Decision |
|---|---|
| Eligible nodes | Non-HOME `SUPPLY` nodes only (HOMEs always yield 1) |
| Default fraction | `0.20` (20% of eligible nodes) — see §7 sweep curve |
| Default high-value yield | `2` (one step above default 1) |
| Distribution | Uniform random across eligible nodes (not archetype-specific in v1) |
| Determinism | Seeded from `(config.seed * 17 + 7)`; same seed → same value placement |
| Storage | `Map.supply_values: dict[NodeId, int]` — only stores overrides; missing entries default to 1 via `Map.supply_value(n)` |
| Visibility | Public — `Map.supply_values` is part of the wire-serialized map and visible to all clients |
| Application point | `initial_state(config, m)` — assigns values once at game start if not pre-assigned |
| Wire format | `Map.supply_values` round-trips; missing key in older blobs → empty dict |

## 4. Engine changes

```python
# foedus/core.py
@dataclass(frozen=True)
class Map:
    # ... existing fields ...
    supply_values: dict[NodeId, int] = field(default_factory=dict)

    def supply_value(self, n: NodeId) -> int:
        return self.supply_values.get(n, 1)

@dataclass
class GameConfig:
    # ... existing ...
    high_value_supply_fraction: float = 0.05
    high_value_supply_yield: int = 2
```

`foedus/resolve.py` step 8 (tiered scoring) replaces the hardcoded `+1 per controlled supply` with `+map.supply_value(n) per controlled supply`. `initial_state` invokes a new `_assign_high_value_supplies(m, config)` helper that:
1. Filters eligible nodes (non-HOME SUPPLY only).
2. Computes `count = floor(len(eligible) * fraction + 0.5)`.
3. Samples `count` nodes deterministically from a config-seed-derived RNG.
4. Returns a new Map with `supply_values` populated.

The check `if not m.supply_values:` skips re-assignment when the input Map already has values populated (e.g., wire-loaded states, replay).

## 5. Wire format

`serialize_map` adds `supply_values: dict[str, int]` (string-keyed for JSON). `deserialize_map` reads with `data.get("supply_values") or {}` for backward-compat. `serialize_config` exposes `high_value_supply_fraction` and `high_value_supply_yield` so clients can label high-value supplies and replay deterministically.

## 6. Sweep CLI

```sh
# Default (Bundle 5b on, fraction=0.20):
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py --num-games 5000 \
    --max-turns 15 --workers 8 --out /tmp/sweep_b5b.jsonl

# Disable C3 to compare:
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py --num-games 5000 \
    --max-turns 15 --workers 8 --high-value-fraction 0 \
    --out /tmp/sweep_v1.jsonl

# Conservative — 5% (mechanic on but barely visible):
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py --num-games 5000 \
    --max-turns 15 --workers 8 --high-value-fraction 0.05 \
    --out /tmp/sweep_b5b_low.jsonl
```

## 7. Validation plan

Empirical sweep curve (n=5000 random pool, full 16-heuristic roster) over
high-value fraction (where VG = ValueGreedy, GH = GreedyHold):

| Fraction | VG | GH | VG−GH | Coop−DC | dislodge/game | tier-1 sd |
|---|---|---|---|---|---|---|
| OFF (0.00) | (≡ GH) | 60.7 | — | +2.02 | 1.88 | 19.0 |
| 5% | 62.5 | 62.9 | −0.35 | +3.00 | 1.60 | 20.5 |
| 10% | 66.1 | 65.7 | +0.37 | +2.76 | 1.61 | 22.0 |
| 15% | 66.1 | 65.7 | +0.37 | +2.76 | 1.61 | 22.0 |
| **20% (default)** | **69.6** | **68.6** | **+1.04** | **+3.06** | **1.60** | **23.3** |

The default of 20% was chosen because it's the lowest fraction at which
VG demonstrably breaks above GH in the random pool. Lower fractions (5%)
leave the mechanic invisible; higher fractions (>30%) over-skew variance
without proportional differentiation gain. Sweeps to run after merge:

| Test | Expectation |
|---|---|
| `--seats Bandwagon,GreedyHold,GreedyHold,GreedyHold` (n=2000) at fraction=0.05 vs fraction=0 | Bandwagon mean rises relative to GH baseline (Bandwagon's join-the-leader behavior tends to land on the +2 hex when leader takes it) |
| Full random pool (n=5000) with C3 on vs off | Score variance per heuristic increases at C3=on (more strategy-discriminating) |
| Tier 1 spread test | Top-cluster spread widens — count-maximizer (GH) and value-aware joiner (Bandwagon) diverge measurably (>3 points) |
| Mean dislodgements/game | Should rise modestly: high-value supplies become contested targets (Bundle 4's combat reward + leverage already rewards attacks) |

If +2 produces measurable differentiation but Bandwagon doesn't break ahead of GH, follow-up bundle adds a second tier at +3 on a smaller fraction (~1%).

## 8. Backward compatibility

- `Map(...)` without `supply_values` works (default empty dict).
- `serialize_map` always emits `supply_values` (possibly empty); `deserialize_map` accepts blobs without the key.
- `GameConfig(high_value_supply_fraction=0)` reverts to v1 uniform scoring.
- Existing tests pass without modification — value=1 is the default for any node not explicitly overridden.

## 9. Heuristic implications

Existing heuristics walk to "nearest unowned supply" without considering value. Two follow-up heuristics to add (later PR, after measurement):

- **ValueGreedy** — like GreedyHold but BFS-prefers high-value supplies over low-value when distances are equal.
- **ValueBandwagon** — joins the leader specifically on high-value targets (cross-supports + aid spends on the leader's intent if the dest is value=2).

Without these, the existing 15-heuristic roster will capture *some* differentiation purely from random tiebreaks, but full effect requires value-aware play. Defer until v0 numbers are in hand.

## 10. What's still deferred

- Archetype-specific value placement (continental → uniform; highland_pass → near pass; riverlands → near crossings).
- Fog-of-value (do scouts reveal supply values? — likely no, but reconsider with hidden-info bundles).
- Value=3 tier on a smaller fraction (~1%).
- Adjacency tax (A3 — separate spec; pairs naturally with C3).
