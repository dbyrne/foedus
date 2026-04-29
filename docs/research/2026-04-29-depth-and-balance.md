# Depth & Balance Analysis (post seat-fix baseline)

**Source:** 5000-game sweep on commit `d8442f6`, all 11 heuristics, random pairings, 4p × 15 turns × continental_sweep r3, all seat-fix corrections in place. Raw report: `2026-04-29-bundle-7-baseline-v2.md`.

## The headline: the game has three tiers, and tier 1 is a tie

| Tier | Mean score | Heuristics | Reading |
|---|---|---|---|
| 1 | **63.7 ± 18.4** | GreedyHold, TitForTat, Bandwagon | Hold-to-flip expanders |
| 2 | 21.5 ± 9.5  | Aggressive, Random, OpportunisticBetrayer, AntiLeader, Greedy, Sycophant | Walk-forward agents |
| 3 | **15.0 ± 0.2** | Defensive, ConservativeBuilder | Do-nothing floor (5 home supplies × 3 turn-multiplier) |

**Tier 1 is literally indistinguishable.** In 1505 games containing two or more top-3 heuristics, GH wins 485, BW 493, TFT 479 — within sampling noise. All three play *the same orders* (GreedyHold under the hood); only stance differs. The score-victory game currently has **one optimal strategy** (GreedyHold expansion); the rest is decoration.

## How wide is the gap?

Tier 1 gains **+3.3 supplies between turns 5 and 15**; tier 2 gains +0.5 to +1.0. **Tier 1 outpaces tier 2 by ~5×.** Once you start hold-to-flipping, you snowball; nothing in the rules pulls leaders back.

## How contested are the games?

- **91% of games have zero dislodgements.** Players almost never directly fight.
- **0.7% have any elimination.** Most games run all 15 turns with everyone alive.
- **SupportMove: 2.2% of all orders. SupportHold: 0.6%.** Cooperative tactics are ~absent.
- **12.1% of games end in a tie for 1st place.** When two tier-1 players race, they often hit the supply-cap together.
- **58% of games never see a lead change** (median 1, max 7).

The mechanical depth budget is being *spent* on a footrace, not a war.

## Why current betrayer mechanics don't bite

- Only **17.4% of games** ever fire a BetrayalObservation (Sycophant + OpportunisticBetrayer must both be present *and* OB has to find an exposed enemy on a supply adjacent to an own unit).
- Even when betrayals fire, the engine has **zero consequences for breaking an Intent** beyond the observation itself. Sycophant ≡ OpportunisticBetrayer to within stat noise (20.7 vs 23.0 mean).
- TFT's punishment of betrayers (-43 vs Sycophant, -38 vs OB in head-to-head) is real but *not because betrayal failed* — it's because TFT plays GreedyHold underneath and lands in tier 1, while betrayers play Greedy and land in tier 2.

## What the data says about depth knobs

**Established:**

| Knob | Effect on score gap | Effect on cooperation |
|---|---|---|
| Map radius | +14 to top-3 mean per radius step | SupportMove **3.2% at r2 → 0.9% at r5** |
| Player count | -10 to top-3 per +1 player | SupportMove +0.6%/player |
| Archetype | Continental > Uniform > Riverlands ≈ Highland | Modest (1.5–2.1%) |
| Turn count | Linear gap-widening | Stable order-mix |

**Smaller maps and more players push games toward contention.** Bundle 4 / future mechanic experiments should baseline at r2 or r=3 with 6 players, not the current 4p/r3 default — that's where the cooperative-tactics signal is loudest.

## What the data says about open mechanic questions

### Q: Are alliance multipliers (Bundle 4 candidate) needed?

**Yes — strongly.** The collapse in dislodgement rate (91% of games never fight) and the ALLY-everywhere top-3 tie suggest the game has no incentive structure for actually using stances. A multiplier on captured-with-support would give SupportMove a reason to exist.

### Q: Should Intent-breaks have engine consequences?

**Yes.** Currently Sycophant (lying ALLY without Intents) and OpportunisticBetrayer (declaring Intents then breaking them) are statistically equivalent. The Intent mechanism is informational only; without a cost, betrayers behave as if no commitment existed. Options:
- Score deduction per broken Intent.
- Lose access to receiving SupportMove from any observer for K turns.
- Dislodgement combat ratio penalty when attacking a player who saw your broken Intent recently.

### Q: Is the hold-to-flip rule too dominant?

**Yes, in the score-victory regime.** Bundle 2's hold-to-flip rule is what enables tier-1 snowball. It's load-bearing — removing it would break détente — but it currently has no counterweight. Possible counterweights:
- Hold attrition: holding cost X per turn beyond turn N.
- Supply depletion: supplies that pay out for K turns then go fallow.
- Adjacency tax: holding a supply adjacent to ≥2 enemy nodes costs more.

### Q: Does the détente collective-victory ever trigger here?

The default `detente_threshold = 4 + num_players = 8`. With `peace_threshold=99` set in the harness, no. **Need a separate sweep with default détente settings to see how often peaceful collective-victory actually fires** in self-play.

## Recommendations

1. **Collapse the top-3 tie.** Either Bandwagon should genuinely mirror leader behaviour (currently a copy of GreedyHold) and TFT should have visible orders distinct from GH, or two of these heuristics should be retired.
2. **Bundle 4: alliance multiplier** — highest-leverage mechanic to push SupportMove% from 2% toward something meaningful.
3. **Intent-break consequences** — the cheapest way to differentiate Sycophant from OB and force betrayer strategies to actually trade off.
4. **Re-baseline with default détente threshold** to measure how often peaceful victory fires in heuristic self-play. If it's ~0%, the détente rule is dormant; if >50%, it's the actual game.
5. **Stop using `--archetype continental_sweep --map-radius 3` as the default benchmark.** That's the most-permissive setting; it dilutes any real-cooperation signal. Default to **`--map-radius 2 --num-players 6`** for sensitivity sweeps when measuring future mechanic changes.

