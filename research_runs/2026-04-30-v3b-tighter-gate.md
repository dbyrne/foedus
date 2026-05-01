# Bundle 7 — Sim Sweep Analysis

**Total games analyzed:** 1000

## Per-heuristic final score (across all game-instances)

| Heuristic | n games | mean | median | stddev | min | max |
|---|---|---|---|---|---|---|
| Aggressive | 212 | 62.73 | 48.50 | 38.92 | 11 | 229 |
| AntiLeader | 191 | 46.65 | 44.00 | 25.75 | 6 | 129 |
| Bandwagon | 228 | 134.13 | 129.00 | 54.39 | 17 | 281 |
| CoalitionBuilder | 199 | 85.25 | 77.00 | 40.80 | 9 | 203 |
| ConservativeBuilder | 240 | 23.80 | 25.00 | 3.97 | 5 | 25 |
| Cooperator | 199 | 160.93 | 165.00 | 64.37 | 21 | 327 |
| Defensive | 198 | 24.20 | 25.00 | 3.13 | 7 | 25 |
| DishonestCooperator | 206 | 152.02 | 147.50 | 59.47 | 32 | 307 |
| Greedy | 218 | 42.88 | 33.00 | 23.99 | 7 | 132 |
| GreedyHold | 212 | 131.20 | 131.00 | 52.08 | 14 | 282 |
| LateCloser | 216 | 46.65 | 39.50 | 30.64 | 7 | 200 |
| Opportunist | 229 | 129.75 | 125.00 | 71.99 | 13 | 357 |
| OpportunisticBetrayer | 235 | 54.64 | 45.00 | 38.89 | 6 | 278 |
| Patron | 205 | 166.60 | 167.00 | 66.92 | 24 | 316 |
| Random | 211 | 44.09 | 36.00 | 30.24 | 6 | 182 |
| Sycophant | 207 | 42.81 | 37.00 | 23.22 | 9 | 134 |
| TitForTat | 206 | 139.83 | 132.50 | 53.42 | 23 | 306 |
| TrustfulCooperator | 206 | 162.91 | 160.00 | 74.51 | 21 | 340 |
| ValueGreedy | 182 | 143.70 | 142.50 | 59.54 | 32 | 313 |

## Pairing win-rate matrix (row vs column)

Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).

| | Aggressive | AntiLeader | Bandwagon | CoalitionBuilder | ConservativeBuilder | Cooperator | Defensive | DishonestCooperator | Greedy | GreedyHold | LateCloser | Opportunist | OpportunisticBetrayer | Patron | Random | Sycophant | TitForTat | TrustfulCooperator | ValueGreedy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Aggressive** | — | 0.54 | 0.24 | 0.33 | 0.77 | 0.12 | 0.81 | 0.12 | 0.57 | 0.12 | 0.56 | 0.14 | 0.53 | 0.10 | 0.59 | 0.62 | 0.14 | 0.17 | 0.07 |
| **AntiLeader** | 0.29 | — | 0.15 | 0.17 | 0.85 | 0.03 | 0.67 | 0.08 | 0.64 | 0.07 | 0.54 | 0.14 | 0.33 | 0.04 | 0.42 | 0.43 | 0.03 | 0.06 | 0.06 |
| **Bandwagon** | 0.76 | 0.85 | — | 0.94 | 0.97 | 0.38 | 0.97 | 0.43 | 0.94 | 0.48 | 0.95 | 0.58 | 0.86 | 0.51 | 0.94 | 0.94 | 0.47 | 0.36 | 0.32 |
| **CoalitionBuilder** | 0.67 | 0.83 | 0.06 | — | 1.00 | 0.23 | 1.00 | 0.05 | 0.79 | 0.23 | 0.88 | 0.21 | 0.76 | 0.13 | 0.80 | 0.90 | 0.13 | 0.18 | 0.21 |
| **ConservativeBuilder** | 0.00 | 0.03 | 0.00 | 0.00 | — | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | 0.02 | 0.00 | 0.14 | 0.00 | 0.15 | 0.14 | 0.00 | 0.00 | 0.00 |
| **Cooperator** | 0.88 | 0.97 | 0.62 | 0.77 | 1.00 | — | 1.00 | 0.59 | 1.00 | 0.62 | 0.92 | 0.81 | 0.89 | 0.45 | 1.00 | 0.96 | 0.52 | 0.65 | 0.65 |
| **Defensive** | 0.03 | 0.10 | 0.00 | 0.00 | 0.04 | 0.00 | — | 0.00 | 0.09 | 0.00 | 0.09 | 0.02 | 0.17 | 0.00 | 0.22 | 0.15 | 0.00 | 0.00 | 0.00 |
| **DishonestCooperator** | 0.88 | 0.92 | 0.57 | 0.95 | 1.00 | 0.41 | 1.00 | — | 0.90 | 0.54 | 0.94 | 0.61 | 0.95 | 0.29 | 1.00 | 0.90 | 0.59 | 0.52 | 0.53 |
| **Greedy** | 0.24 | 0.36 | 0.06 | 0.18 | 0.44 | 0.00 | 0.45 | 0.10 | — | 0.00 | 0.35 | 0.14 | 0.41 | 0.00 | 0.48 | 0.36 | 0.06 | 0.00 | 0.03 |
| **GreedyHold** | 0.88 | 0.93 | 0.48 | 0.77 | 1.00 | 0.38 | 1.00 | 0.46 | 1.00 | — | 0.93 | 0.54 | 0.83 | 0.27 | 1.00 | 0.94 | 0.44 | 0.45 | 0.73 |
| **LateCloser** | 0.28 | 0.31 | 0.05 | 0.12 | 0.67 | 0.08 | 0.42 | 0.06 | 0.39 | 0.07 | — | 0.00 | 0.39 | 0.03 | 0.48 | 0.35 | 0.03 | 0.09 | 0.05 |
| **Opportunist** | 0.86 | 0.86 | 0.42 | 0.79 | 1.00 | 0.19 | 0.98 | 0.39 | 0.84 | 0.46 | 1.00 | — | 0.84 | 0.27 | 0.71 | 0.90 | 0.56 | 0.28 | 0.45 |
| **OpportunisticBetrayer** | 0.32 | 0.56 | 0.14 | 0.24 | 0.66 | 0.11 | 0.57 | 0.05 | 0.45 | 0.17 | 0.39 | 0.16 | — | 0.11 | 0.56 | 0.51 | 0.15 | 0.20 | 0.03 |
| **Patron** | 0.90 | 0.96 | 0.46 | 0.87 | 1.00 | 0.55 | 1.00 | 0.71 | 1.00 | 0.73 | 0.97 | 0.73 | 0.89 | — | 0.97 | 1.00 | 0.62 | 0.53 | 0.72 |
| **Random** | 0.38 | 0.47 | 0.06 | 0.17 | 0.76 | 0.00 | 0.78 | 0.00 | 0.48 | 0.00 | 0.48 | 0.29 | 0.41 | 0.03 | — | 0.41 | 0.03 | 0.06 | 0.00 |
| **Sycophant** | 0.23 | 0.27 | 0.06 | 0.10 | 0.54 | 0.04 | 0.44 | 0.10 | 0.52 | 0.06 | 0.43 | 0.10 | 0.38 | 0.00 | 0.52 | — | 0.00 | 0.00 | 0.11 |
| **TitForTat** | 0.86 | 0.97 | 0.50 | 0.87 | 1.00 | 0.48 | 1.00 | 0.41 | 0.94 | 0.53 | 0.97 | 0.42 | 0.85 | 0.38 | 0.97 | 1.00 | — | 0.36 | 0.38 |
| **TrustfulCooperator** | 0.83 | 0.94 | 0.64 | 0.82 | 1.00 | 0.35 | 1.00 | 0.48 | 1.00 | 0.55 | 0.91 | 0.69 | 0.80 | 0.47 | 0.94 | 1.00 | 0.64 | — | 0.50 |
| **ValueGreedy** | 0.93 | 0.94 | 0.65 | 0.79 | 1.00 | 0.35 | 1.00 | 0.47 | 0.94 | 0.27 | 0.95 | 0.55 | 0.97 | 0.28 | 1.00 | 0.89 | 0.62 | 0.50 | — |

## Lead-change frequency

Mean lead changes per game: **1.85**

Median: 1, max: 9, games with 0 changes: 16

## Order-type distribution (across all games × all players × all turns)

- **Hold:** 27.2%
- **Move:** 62.8%
- **Support:** 10.1%

## Dislodgement rate

Mean dislodgements per game: **4.49**

Games with at least one dislodgement: 523 of 1000

## Betrayer success vs TitForTat

When Betrayer X and TitForTat appear in the same game, average score difference (X − TitForTat):

- **Sycophant** vs TitForTat (n=34): -108.56 (TitForTat punishes)
- **OpportunisticBetrayer** vs TitForTat (n=33): -82.67 (TitForTat punishes)

## Winner vs 2nd-place score gap

Mean gap: 76.16, median: 58

