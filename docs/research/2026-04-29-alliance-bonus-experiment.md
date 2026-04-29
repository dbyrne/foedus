# Alliance bonus + Cooperator — quick experiment

**Status:** Q&D experiment, not a feature. Gated behind `FOEDUS_ALLIANCE_BONUS` env var; defaults to 0 (off). Cooperator heuristic added to ROSTER. Result feeds into a future Bundle 4 spec, not committed-to mechanic.

**Question:** Does rewarding cross-player SupportMove on captured supplies open a second top-tier strategy alongside GreedyHold?

**Answer:** Yes, when paired with a heuristic that actually attempts cross-supports. The default 11-heuristic roster never issues cross-player SupportMoves, so the bonus alone is dead weight; adding a Cooperator that reads declared Intents and supports adjacent ALLY attacks creates the missing exploit path.

## Cross-config sweep (5000 games each, T=15, full 12-heuristic random pool)

| Config | bonus | Coop | GH | BW | TFT | Aggr | Coop−GH | SupMv% | disl/g |
|---|---|---|---|---|---|---|---|---|---|
| r2 4p | 0 | 40.9 | 42.5 | 41.1 | 41.3 | 33.2 | **−1.6** | 4.06% | 0.36 |
| r2 4p | 3 | 42.5 | 42.8 | 41.3 | 41.5 | 33.4 | −0.2 | 4.06% | 0.36 |
| r2 4p | 10 | 46.2 | 43.3 | 41.9 | 42.0 | 33.9 | +3.0 | 4.06% | 0.36 |
| r3 6p | 0 | 50.1 | 49.9 | 49.8 | 50.1 | 32.8 | +0.3 | 3.70% | 0.49 |
| r3 6p | 3 | 52.0 | 50.1 | 50.1 | 50.3 | 33.0 | **+1.9** | 3.70% | 0.49 |
| r3 6p | 10 | 56.4 | 50.6 | 50.6 | 50.8 | 33.3 | +5.8 | 3.70% | 0.49 |
| r2 6p | 0 | 28.6 | 28.7 | 28.5 | 28.5 | 28.5 | −0.2 | 4.88% | 0.56 |
| r2 6p | 3 | 30.5 | 29.0 | 28.8 | 28.8 | 28.7 | +1.5 | 4.88% | 0.56 |
| r2 6p | 10 | 34.9 | 29.5 | 29.4 | 29.4 | 29.3 | +5.4 | 4.88% | 0.56 |
| r4 4p | 0 | 79.0 | 78.2 | 78.5 | 78.6 | 19.4 | +0.8 | 1.55% | 0.06 |
| r4 4p | 3 | 80.4 | 78.3 | 78.6 | 78.7 | 19.4 | +2.1 | 1.55% | 0.06 |
| r4 4p | 10 | 83.5 | 78.6 | 78.9 | 78.9 | 19.5 | +5.0 | 1.55% | 0.06 |

## Findings

**1. The mechanism is robust across geometry.** At bonus=10, Cooperator beats GreedyHold by +3.0 to +5.8 in every config tested. The exact bonus needed for parity varies (~bonus 1 at r3_4p; ~bonus 3 at r2_4p) but the slope is consistent.

**2. Cooperator under-performs GH at bonus=0 on small maps.** Cross-support has setup cost when geometry is tight (Cooperator waits for declared Intents that match adjacency, missing expansion turns). The bonus is needed to overcome that overhead. On bigger maps the wait costs less because expansion is faster anyway.

**3. SupportMove % is config-determined, not bonus-determined.** Range 1.55% (r4 sparse) to 4.88% (r2_6p crowded). Heuristics are static; the bonus changes scoring but not behavior. With adaptive agents (NN training), the bonus would shape strategy *choice* — these numbers are the upper bound of what a fixed cross-supporting strategy can earn at each bonus level.

**4. Crowded maps already compress the tier structure.** At r2_6p bonus=0, Coop / GH / BW / TFT / Aggressive all within 0.3 of each other (~28.5). The dominant-strategy hegemony only really exists at radius 3+. The bonus then re-establishes a tier with Cooperator at the top.

**5. The "depth-loud" config (r3 6p) is also bonus-friendly.** It produces the cleanest scaling: Coop−GH = +0.3 / +1.9 / +5.8 at bonus 0 / 3 / 10. This is probably the right benchmark for tuning the bonus.

## Implications for the real Bundle 4 spec

When this gets brainstormed properly:

- **Default bonus around 3** gives Cooperator a small edge without dominating. Bonus 10 turns it into the new monopoly. The window between is where a designed game wants to live.

- **The Sycophant exploit gets sharper at higher bonuses.** OpportunisticBetrayer scores +2.1 at bonus=10 just by occasionally hitting cross-support intents it lied about. A "DishonestCooperator" (declares cross-support intents, defects) would score even higher. Bundle 4 *requires* paired Intent-break consequences or it's exploitable.

- **The press system carries the cooperation signal.** Cooperator works because it reads other players' declared Move-on-supply Intents. Without the press system, no alliance is possible — which means the press system has new mechanical responsibility (and the current Sycophant-can-lie problem is now a *gameplay* issue, not just a research curiosity).

- **SupportMove % doesn't move with bonus — but should, in a tuned game.** Static heuristics can't react to scoring changes. The full effect of an alliance multiplier would only emerge with learning agents; for now we're measuring the *availability* of the second strategy, not its emergence.

## Reproducible

```sh
# Toggle the bonus:
FOEDUS_ALLIANCE_BONUS=3 PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
  --num-games 5000 --max-turns 15 --workers 16 \
  --map-radius 3 --num-players 6 \
  --out /tmp/sweep_b3.jsonl
```

`Cooperator` is in `foedus/agents/heuristics/cooperator.py`; the bonus
logic is in `foedus/resolve.py` step 8b. Both intentionally hacky;
both gated on env var so the default behavior on `main` is unchanged.

## Update — DishonestCooperator probe

Added a `DishonestCooperator` (declares cross-support Intents like Cooperator, but never reciprocates — pure GreedyHold orders) and tested the predicted freerider exploit.

### 1 DC vs 3 Cooperator — the controlled setup

| bonus | DC | Coop avg | DC − Coop |
|---|---|---|---|
| 0 | **64.0** | 53.3 | **+10.7** |
| 3 | 73.1 | 61.1 | +12.0 |
| 10 | 94.5 | 79.4 | +15.1 |

**The exploit works even at bonus=0** (+10.7). The score bonus widens it but isn't the source. Two structural advantages compound:

1. **Free attack-success** — Cooperators support DC's published Move intents, so DC's attacks succeed where they'd otherwise bounce.
2. **Time arbitrage** — Cooperators waste ~30% of their turns supporting; DC spends 100% on expansion (it's pure GreedyHold under the hood).

### 13-heuristic random pool — the result reverses

| bonus | Cooperator | DC | Δ |
|---|---|---|---|
| 0 | 62.6 | 63.0 | DC +0.4 |
| 3 | **65.0** | 63.8 | **Coop +1.2** |
| 10 | **70.5** | 65.8 | **Coop +4.7** |

In random pools, Cooperator-at-a-table-with-another-Cooperator is more productive (mutual support, ~40% SupportMove rate, two-way bonuses) than DC-at-a-table-with-one-Cooperator (unilateral support, one-way bonus). Cooperator pairs self-select into local cooperative cliques where they outscore the diluted-freerider DC.

### Implications for Bundle 4

1. **The exploit is real and invisible.** A random-pool sweep would *miss* it (in fact would show Cooperator winning). Bundle 4 evaluation MUST include a fixed-seat exploit test (e.g. `1 DC vs 3 Coop`, `2 DC vs 2 Coop`) — random pairings hide the structural problem because dishonest agents are diluted out of cooperator-rich neighborhoods.

2. **The structural exploit is bonus-independent.** Bundle 4 needs Intent-break consequences regardless of the bonus value: the time-arbitrage advantage exists at any positive bonus and even at zero. *Detecting* a broken cross-support Intent is straightforward (Cooperator declared they'd attack supply X with their unit U, but at order-resolution time U is held or moved elsewhere). The penalty design is what needs the brainstorm.

3. **Cooperator pair coordination is fragile.** Two Cooperators outscore solo GreedyHold *only* when both publish honest intents. A meta where 1/3 of agents are dishonest would invert the equilibrium — Cooperator pairs become unsafe and the strategy collapses. The bonus mechanism without intent-break consequences would *destabilize* cooperation rather than create it.

