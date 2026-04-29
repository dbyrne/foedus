# Bundle 7 — Sim Sweep Analysis

**Total games analyzed:** 5000

## Per-heuristic final score (across all game-instances)

| Heuristic | n games | mean | median | stddev | min | max |
|---|---|---|---|---|---|---|
| Aggressive | 1762 | 25.36 | 23.00 | 11.93 | 4 | 86 |
| AntiLeader | 1853 | 22.22 | 22.00 | 7.98 | 4 | 54 |
| Bandwagon | 1834 | 63.55 | 64.00 | 18.51 | 11 | 119 |
| ConservativeBuilder | 1743 | 14.99 | 15.00 | 0.25 | 8 | 15 |
| Defensive | 1848 | 14.99 | 15.00 | 0.15 | 10 | 15 |
| Greedy | 1827 | 21.31 | 16.00 | 8.62 | 5 | 72 |
| GreedyHold | 1800 | 63.87 | 63.00 | 18.52 | 15 | 117 |
| OpportunisticBetrayer | 1882 | 22.95 | 21.00 | 8.99 | 4 | 66 |
| Random | 1858 | 23.83 | 22.00 | 9.96 | 4 | 71 |
| Sycophant | 1783 | 20.73 | 15.00 | 8.06 | 6 | 57 |
| TitForTat | 1810 | 63.75 | 64.00 | 17.86 | 11 | 124 |

## Pairing win-rate matrix (row vs column)

Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).

| | Aggressive | AntiLeader | Bandwagon | ConservativeBuilder | Defensive | Greedy | GreedyHold | OpportunisticBetrayer | Random | Sycophant | TitForTat |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Aggressive** | — | 0.47 | 0.06 | 0.51 | 0.54 | 0.40 | 0.08 | 0.40 | 0.43 | 0.44 | 0.04 |
| **AntiLeader** | 0.31 | — | 0.03 | 0.63 | 0.58 | 0.39 | 0.04 | 0.37 | 0.41 | 0.47 | 0.04 |
| **Bandwagon** | 0.94 | 0.97 | — | 1.00 | 1.00 | 0.97 | 0.46 | 0.96 | 0.97 | 0.97 | 0.50 |
| **ConservativeBuilder** | 0.01 | 0.04 | 0.00 | — | 0.00 | 0.03 | 0.00 | 0.02 | 0.07 | 0.04 | 0.00 |
| **Defensive** | 0.02 | 0.04 | 0.00 | 0.00 | — | 0.05 | 0.00 | 0.01 | 0.09 | 0.05 | 0.00 |
| **Greedy** | 0.25 | 0.31 | 0.03 | 0.38 | 0.42 | — | 0.02 | 0.30 | 0.36 | 0.32 | 0.01 |
| **GreedyHold** | 0.92 | 0.96 | 0.51 | 1.00 | 1.00 | 0.98 | — | 0.96 | 0.97 | 0.98 | 0.49 |
| **OpportunisticBetrayer** | 0.32 | 0.37 | 0.04 | 0.49 | 0.46 | 0.38 | 0.03 | — | 0.40 | 0.37 | 0.03 |
| **Random** | 0.46 | 0.52 | 0.03 | 0.74 | 0.75 | 0.52 | 0.03 | 0.50 | — | 0.55 | 0.02 |
| **Sycophant** | 0.27 | 0.26 | 0.02 | 0.38 | 0.38 | 0.31 | 0.02 | 0.31 | 0.32 | — | 0.02 |
| **TitForTat** | 0.95 | 0.95 | 0.47 | 1.00 | 1.00 | 0.97 | 0.49 | 0.96 | 0.97 | 0.98 | — |

## Lead-change frequency

Mean lead changes per game: **1.15**

Median: 1, max: 7, games with 0 changes: 558

## Order-type distribution (across all games × all players × all turns)

- **Hold:** 27.3%
- **Move:** 70.0%
- **SupportHold:** 0.6%
- **SupportMove:** 2.2%

## Dislodgement rate

Mean dislodgements per game: **0.15**

Games with at least one dislodgement: 439 of 5000

## Betrayer success vs TitForTat

When Betrayer X and TitForTat appear in the same game, average score difference (X − TitForTat):

- **Sycophant** vs TitForTat (n=427): -42.76 (TitForTat punishes)
- **OpportunisticBetrayer** vs TitForTat (n=422): -38.41 (TitForTat punishes)

## Winner vs 2nd-place score gap

Mean gap: 24.19, median: 18

