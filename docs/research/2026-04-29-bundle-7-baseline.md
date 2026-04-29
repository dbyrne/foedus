# Bundle 7 — Sim Sweep Analysis

**Total games analyzed:** 5000

## Findings summary

The top-3 heuristics by mean final score are GreedyHold (61.26), Bandwagon (61.00), and TitForTat (60.90) — a tight cluster far above the rest of the field, with the next-best (Aggressive, 26.61) scoring less than half as much. The win-rate matrix shows no rock-paper-scissors cycles among the top three: GreedyHold and TitForTat are nearly even (0.49/0.48 mutual win rates), and Bandwagon sits between them, with no A > B > C > A triangle of any significance. Both betrayer archetypes are severely punished: TitForTat outscores Sycophant by 36.31 points on average and OpportunisticBetrayer by 34.57 points when they share a game, firmly in the "TitForTat punishes" regime. SupportMove accounts for only 2.1% of all orders, confirming that cooperative support orders are very rarely chosen by the current heuristics — a potential area for strategic improvement.

## Per-heuristic final score (across all game-instances)

| Heuristic | n games | mean | median | stddev | min | max |
|---|---|---|---|---|---|---|
| Aggressive | 1762 | 26.61 | 26.00 | 11.60 | 4 | 84 |
| AntiLeader | 1853 | 22.32 | 22.00 | 8.16 | 4 | 52 |
| Bandwagon | 1834 | 61.00 | 60.00 | 20.78 | 15 | 125 |
| ConservativeBuilder | 1743 | 14.97 | 15.00 | 0.39 | 6 | 15 |
| Defensive | 1848 | 14.95 | 15.00 | 0.52 | 8 | 15 |
| Greedy | 1827 | 23.53 | 24.00 | 9.02 | 4 | 59 |
| GreedyHold | 1800 | 61.26 | 61.00 | 19.96 | 15 | 119 |
| OpportunisticBetrayer | 1882 | 24.42 | 25.00 | 9.22 | 4 | 67 |
| Random | 1858 | 23.57 | 22.00 | 10.17 | 4 | 66 |
| Sycophant | 1783 | 23.39 | 24.00 | 8.88 | 4 | 71 |
| TitForTat | 1810 | 60.90 | 60.00 | 19.91 | 12 | 123 |

## Pairing win-rate matrix (row vs column)

Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).

| | Aggressive | AntiLeader | Bandwagon | ConservativeBuilder | Defensive | Greedy | GreedyHold | OpportunisticBetrayer | Random | Sycophant | TitForTat |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Aggressive** | — | 0.52 | 0.10 | 0.63 | 0.64 | 0.45 | 0.10 | 0.44 | 0.52 | 0.48 | 0.09 |
| **AntiLeader** | 0.33 | — | 0.03 | 0.64 | 0.64 | 0.42 | 0.03 | 0.40 | 0.46 | 0.37 | 0.04 |
| **Bandwagon** | 0.89 | 0.96 | — | 1.00 | 1.00 | 0.94 | 0.47 | 0.93 | 0.97 | 0.92 | 0.49 |
| **ConservativeBuilder** | 0.01 | 0.04 | 0.00 | — | 0.01 | 0.04 | 0.00 | 0.03 | 0.10 | 0.02 | 0.00 |
| **Defensive** | 0.02 | 0.04 | 0.00 | 0.00 | — | 0.07 | 0.00 | 0.03 | 0.05 | 0.04 | 0.00 |
| **Greedy** | 0.36 | 0.40 | 0.06 | 0.52 | 0.55 | — | 0.06 | 0.39 | 0.50 | 0.39 | 0.05 |
| **GreedyHold** | 0.90 | 0.97 | 0.49 | 1.00 | 1.00 | 0.94 | — | 0.93 | 0.98 | 0.92 | 0.48 |
| **OpportunisticBetrayer** | 0.36 | 0.42 | 0.06 | 0.61 | 0.61 | 0.40 | 0.06 | — | 0.46 | 0.37 | 0.08 |
| **Random** | 0.39 | 0.46 | 0.03 | 0.73 | 0.75 | 0.40 | 0.02 | 0.43 | — | 0.46 | 0.03 |
| **Sycophant** | 0.33 | 0.42 | 0.07 | 0.55 | 0.59 | 0.43 | 0.07 | 0.46 | 0.41 | — | 0.05 |
| **TitForTat** | 0.90 | 0.96 | 0.50 | 0.99 | 1.00 | 0.94 | 0.49 | 0.91 | 0.96 | 0.94 | — |

## Lead-change frequency

Mean lead changes per game: **1.21**

Median: 1, max: 5, games with 0 changes: 384

## Order-type distribution (across all games × all players × all turns)

- **Hold:** 26.8%
- **Move:** 70.5%
- **SupportHold:** 0.6%
- **SupportMove:** 2.1%

## Dislodgement rate

Mean dislodgements per game: **0.15**

Games with at least one dislodgement: 452 of 5000

## Betrayer success vs TitForTat

When Betrayer X and TitForTat appear in the same game, average score difference (X − TitForTat):

- **Sycophant** vs TitForTat (n=427): -36.31 (TitForTat punishes)
- **OpportunisticBetrayer** vs TitForTat (n=422): -34.57 (TitForTat punishes)

## Winner vs 2nd-place score gap

Mean gap: 24.11, median: 18

