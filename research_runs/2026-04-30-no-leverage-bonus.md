# Bundle 7 — Sim Sweep Analysis

**Total games analyzed:** 1000

## Per-heuristic final score (across all game-instances)

| Heuristic | n games | mean | median | stddev | min | max |
|---|---|---|---|---|---|---|
| Aggressive | 212 | 62.69 | 48.00 | 39.03 | 11 | 229 |
| AntiLeader | 191 | 48.65 | 45.00 | 29.33 | 6 | 212 |
| Bandwagon | 228 | 137.35 | 132.00 | 53.17 | 17 | 281 |
| CoalitionBuilder | 199 | 88.22 | 79.00 | 39.41 | 9 | 203 |
| ConservativeBuilder | 240 | 23.82 | 25.00 | 3.92 | 5 | 25 |
| Cooperator | 199 | 159.02 | 153.00 | 64.58 | 23 | 329 |
| Defensive | 198 | 24.21 | 25.00 | 3.17 | 7 | 25 |
| DishonestCooperator | 206 | 170.35 | 161.00 | 67.15 | 32 | 350 |
| Greedy | 218 | 43.21 | 36.00 | 23.51 | 7 | 132 |
| GreedyHold | 212 | 133.97 | 132.00 | 51.34 | 14 | 282 |
| LateCloser | 216 | 49.27 | 42.00 | 30.20 | 8 | 188 |
| Opportunist | 229 | 106.20 | 93.00 | 52.83 | 13 | 258 |
| OpportunisticBetrayer | 235 | 66.48 | 49.00 | 51.97 | 6 | 321 |
| Patron | 205 | 133.83 | 124.00 | 63.87 | 24 | 309 |
| Random | 211 | 44.59 | 36.00 | 30.54 | 6 | 182 |
| Sycophant | 207 | 44.29 | 39.00 | 22.74 | 9 | 134 |
| TitForTat | 206 | 141.19 | 134.50 | 52.78 | 23 | 306 |
| TrustfulCooperator | 206 | 150.51 | 141.50 | 67.61 | 31 | 340 |
| ValueGreedy | 182 | 146.79 | 145.50 | 58.92 | 32 | 313 |

## Pairing win-rate matrix (row vs column)

Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).

| | Aggressive | AntiLeader | Bandwagon | CoalitionBuilder | ConservativeBuilder | Cooperator | Defensive | DishonestCooperator | Greedy | GreedyHold | LateCloser | Opportunist | OpportunisticBetrayer | Patron | Random | Sycophant | TitForTat | TrustfulCooperator | ValueGreedy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Aggressive** | — | 0.54 | 0.24 | 0.33 | 0.77 | 0.12 | 0.84 | 0.12 | 0.57 | 0.15 | 0.53 | 0.16 | 0.49 | 0.17 | 0.59 | 0.58 | 0.14 | 0.17 | 0.07 |
| **AntiLeader** | 0.32 | — | 0.21 | 0.13 | 0.79 | 0.03 | 0.67 | 0.08 | 0.70 | 0.10 | 0.51 | 0.14 | 0.38 | 0.04 | 0.42 | 0.43 | 0.06 | 0.09 | 0.06 |
| **Bandwagon** | 0.76 | 0.79 | — | 0.94 | 0.97 | 0.38 | 0.97 | 0.43 | 0.94 | 0.52 | 0.95 | 0.79 | 0.89 | 0.63 | 0.94 | 0.97 | 0.47 | 0.36 | 0.35 |
| **CoalitionBuilder** | 0.67 | 0.87 | 0.06 | — | 1.00 | 0.19 | 1.00 | 0.05 | 0.82 | 0.23 | 0.88 | 0.44 | 0.70 | 0.16 | 0.82 | 0.87 | 0.13 | 0.18 | 0.21 |
| **ConservativeBuilder** | 0.00 | 0.06 | 0.00 | 0.00 | — | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | 0.02 | 0.00 | 0.06 | 0.00 | 0.12 | 0.09 | 0.00 | 0.00 | 0.00 |
| **Cooperator** | 0.88 | 0.97 | 0.62 | 0.77 | 1.00 | — | 1.00 | 0.28 | 1.00 | 0.56 | 0.88 | 0.86 | 0.83 | 0.91 | 1.00 | 0.96 | 0.48 | 0.58 | 0.54 |
| **Defensive** | 0.00 | 0.10 | 0.00 | 0.00 | 0.04 | 0.00 | — | 0.00 | 0.09 | 0.00 | 0.06 | 0.02 | 0.00 | 0.00 | 0.22 | 0.05 | 0.00 | 0.00 | 0.00 |
| **DishonestCooperator** | 0.88 | 0.92 | 0.57 | 0.95 | 1.00 | 0.72 | 1.00 | — | 0.94 | 0.54 | 0.97 | 0.85 | 0.95 | 0.86 | 1.00 | 0.93 | 0.72 | 0.87 | 0.63 |
| **Greedy** | 0.24 | 0.30 | 0.06 | 0.16 | 0.44 | 0.00 | 0.48 | 0.06 | — | 0.00 | 0.32 | 0.14 | 0.34 | 0.00 | 0.48 | 0.32 | 0.09 | 0.00 | 0.03 |
| **GreedyHold** | 0.85 | 0.90 | 0.45 | 0.77 | 1.00 | 0.41 | 1.00 | 0.46 | 1.00 | — | 0.91 | 0.86 | 0.79 | 0.39 | 1.00 | 0.94 | 0.44 | 0.45 | 0.77 |
| **LateCloser** | 0.31 | 0.31 | 0.05 | 0.12 | 0.69 | 0.12 | 0.45 | 0.03 | 0.45 | 0.09 | — | 0.16 | 0.32 | 0.10 | 0.52 | 0.30 | 0.03 | 0.09 | 0.05 |
| **Opportunist** | 0.84 | 0.86 | 0.18 | 0.56 | 1.00 | 0.14 | 0.98 | 0.15 | 0.86 | 0.14 | 0.84 | — | 0.81 | 0.03 | 0.68 | 0.88 | 0.47 | 0.21 | 0.19 |
| **OpportunisticBetrayer** | 0.36 | 0.51 | 0.11 | 0.30 | 0.74 | 0.17 | 0.70 | 0.05 | 0.52 | 0.21 | 0.45 | 0.19 | — | 0.37 | 0.59 | 0.56 | 0.21 | 0.45 | 0.07 |
| **Patron** | 0.83 | 0.96 | 0.34 | 0.84 | 1.00 | 0.09 | 1.00 | 0.14 | 1.00 | 0.61 | 0.90 | 0.97 | 0.63 | — | 0.94 | 1.00 | 0.62 | 0.24 | 0.52 |
| **Random** | 0.38 | 0.47 | 0.06 | 0.17 | 0.79 | 0.00 | 0.78 | 0.00 | 0.48 | 0.00 | 0.45 | 0.32 | 0.39 | 0.06 | — | 0.45 | 0.03 | 0.06 | 0.00 |
| **Sycophant** | 0.27 | 0.23 | 0.03 | 0.13 | 0.57 | 0.04 | 0.54 | 0.07 | 0.56 | 0.06 | 0.43 | 0.12 | 0.33 | 0.00 | 0.48 | — | 0.00 | 0.03 | 0.11 |
| **TitForTat** | 0.86 | 0.94 | 0.50 | 0.87 | 1.00 | 0.52 | 1.00 | 0.28 | 0.91 | 0.53 | 0.97 | 0.50 | 0.79 | 0.38 | 0.97 | 1.00 | — | 0.52 | 0.38 |
| **TrustfulCooperator** | 0.83 | 0.91 | 0.64 | 0.82 | 1.00 | 0.42 | 1.00 | 0.13 | 1.00 | 0.55 | 0.91 | 0.76 | 0.55 | 0.76 | 0.94 | 0.97 | 0.48 | — | 0.46 |
| **ValueGreedy** | 0.93 | 0.94 | 0.59 | 0.79 | 1.00 | 0.46 | 1.00 | 0.37 | 0.94 | 0.23 | 0.92 | 0.81 | 0.93 | 0.48 | 1.00 | 0.89 | 0.62 | 0.54 | — |

## Lead-change frequency

Mean lead changes per game: **1.78**

Median: 1, max: 8, games with 0 changes: 16

## Order-type distribution (across all games × all players × all turns)

- **Hold:** 26.4%
- **Move:** 62.3%
- **Support:** 11.3%

## Dislodgement rate

Mean dislodgements per game: **2.20**

Games with at least one dislodgement: 482 of 1000

## Betrayer success vs TitForTat

When Betrayer X and TitForTat appear in the same game, average score difference (X − TitForTat):

- **Sycophant** vs TitForTat (n=34): -106.44 (TitForTat punishes)
- **OpportunisticBetrayer** vs TitForTat (n=33): -72.48 (TitForTat punishes)

## Winner vs 2nd-place score gap

Mean gap: 74.36, median: 56

