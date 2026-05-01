# Bundle 7 — Sim Sweep Analysis

**Total games analyzed:** 1000

## Per-heuristic final score (across all game-instances)

| Heuristic | n games | mean | median | stddev | min | max |
|---|---|---|---|---|---|---|
| Aggressive | 212 | 62.03 | 48.50 | 38.28 | 11 | 229 |
| AntiLeader | 191 | 46.17 | 44.00 | 25.52 | 6 | 125 |
| Bandwagon | 228 | 134.06 | 129.00 | 54.67 | 17 | 281 |
| CoalitionBuilder | 199 | 88.65 | 82.00 | 40.62 | 9 | 203 |
| ConservativeBuilder | 240 | 23.82 | 25.00 | 3.95 | 5 | 25 |
| Cooperator | 199 | 160.02 | 159.00 | 62.10 | 21 | 327 |
| Defensive | 198 | 24.14 | 25.00 | 3.26 | 7 | 25 |
| DishonestCooperator | 206 | 154.95 | 149.50 | 61.48 | 32 | 314 |
| Greedy | 218 | 43.06 | 35.50 | 23.80 | 7 | 132 |
| GreedyHold | 212 | 130.87 | 130.50 | 52.45 | 14 | 282 |
| LateCloser | 216 | 47.33 | 40.50 | 31.15 | 7 | 244 |
| Opportunist | 229 | 125.05 | 113.00 | 70.54 | 13 | 357 |
| OpportunisticBetrayer | 235 | 57.32 | 47.00 | 42.57 | 6 | 318 |
| Patron | 205 | 160.48 | 161.00 | 62.35 | 24 | 309 |
| Random | 211 | 44.21 | 38.00 | 30.16 | 6 | 182 |
| Sycophant | 207 | 42.87 | 36.00 | 23.19 | 9 | 134 |
| TitForTat | 206 | 139.65 | 131.00 | 52.99 | 23 | 306 |
| TrustfulCooperator | 206 | 156.30 | 159.00 | 62.80 | 21 | 340 |
| ValueGreedy | 182 | 143.65 | 141.50 | 59.26 | 32 | 313 |

## Pairing win-rate matrix (row vs column)

Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).

| | Aggressive | AntiLeader | Bandwagon | CoalitionBuilder | ConservativeBuilder | Cooperator | Defensive | DishonestCooperator | Greedy | GreedyHold | LateCloser | Opportunist | OpportunisticBetrayer | Patron | Random | Sycophant | TitForTat | TrustfulCooperator | ValueGreedy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Aggressive** | — | 0.54 | 0.24 | 0.33 | 0.77 | 0.12 | 0.81 | 0.08 | 0.57 | 0.12 | 0.53 | 0.16 | 0.51 | 0.07 | 0.59 | 0.62 | 0.14 | 0.13 | 0.07 |
| **AntiLeader** | 0.29 | — | 0.15 | 0.17 | 0.82 | 0.03 | 0.67 | 0.08 | 0.64 | 0.07 | 0.51 | 0.14 | 0.33 | 0.04 | 0.42 | 0.43 | 0.03 | 0.03 | 0.06 |
| **Bandwagon** | 0.76 | 0.85 | — | 0.94 | 0.97 | 0.45 | 0.97 | 0.43 | 0.94 | 0.48 | 0.95 | 0.61 | 0.86 | 0.49 | 0.94 | 0.94 | 0.47 | 0.36 | 0.32 |
| **CoalitionBuilder** | 0.67 | 0.83 | 0.06 | — | 1.00 | 0.26 | 1.00 | 0.05 | 0.82 | 0.23 | 0.88 | 0.41 | 0.76 | 0.13 | 0.80 | 0.90 | 0.16 | 0.14 | 0.21 |
| **ConservativeBuilder** | 0.00 | 0.06 | 0.00 | 0.00 | — | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | 0.02 | 0.00 | 0.11 | 0.00 | 0.12 | 0.14 | 0.00 | 0.00 | 0.00 |
| **Cooperator** | 0.88 | 0.97 | 0.55 | 0.74 | 1.00 | — | 1.00 | 0.59 | 1.00 | 0.56 | 0.96 | 0.89 | 0.89 | 0.61 | 1.00 | 0.96 | 0.55 | 0.58 | 0.65 |
| **Defensive** | 0.03 | 0.10 | 0.00 | 0.00 | 0.04 | 0.00 | — | 0.00 | 0.09 | 0.00 | 0.09 | 0.02 | 0.10 | 0.00 | 0.22 | 0.15 | 0.00 | 0.00 | 0.00 |
| **DishonestCooperator** | 0.92 | 0.92 | 0.57 | 0.95 | 1.00 | 0.41 | 1.00 | — | 0.90 | 0.54 | 0.97 | 0.73 | 0.92 | 0.54 | 1.00 | 0.90 | 0.59 | 0.61 | 0.53 |
| **Greedy** | 0.24 | 0.36 | 0.06 | 0.16 | 0.44 | 0.00 | 0.45 | 0.10 | — | 0.00 | 0.35 | 0.14 | 0.39 | 0.00 | 0.48 | 0.36 | 0.06 | 0.00 | 0.03 |
| **GreedyHold** | 0.88 | 0.93 | 0.48 | 0.77 | 1.00 | 0.44 | 1.00 | 0.46 | 1.00 | — | 0.93 | 0.57 | 0.79 | 0.21 | 1.00 | 0.94 | 0.44 | 0.45 | 0.73 |
| **LateCloser** | 0.31 | 0.33 | 0.05 | 0.12 | 0.67 | 0.04 | 0.42 | 0.03 | 0.39 | 0.07 | — | 0.04 | 0.39 | 0.03 | 0.55 | 0.35 | 0.03 | 0.09 | 0.05 |
| **Opportunist** | 0.84 | 0.86 | 0.39 | 0.59 | 1.00 | 0.11 | 0.98 | 0.27 | 0.84 | 0.43 | 0.96 | — | 0.84 | 0.13 | 0.71 | 0.90 | 0.56 | 0.24 | 0.45 |
| **OpportunisticBetrayer** | 0.34 | 0.56 | 0.14 | 0.24 | 0.69 | 0.11 | 0.63 | 0.08 | 0.48 | 0.21 | 0.39 | 0.16 | — | 0.15 | 0.54 | 0.54 | 0.15 | 0.31 | 0.14 |
| **Patron** | 0.93 | 0.96 | 0.49 | 0.87 | 1.00 | 0.39 | 1.00 | 0.46 | 1.00 | 0.79 | 0.97 | 0.87 | 0.85 | — | 0.97 | 1.00 | 0.62 | 0.47 | 0.72 |
| **Random** | 0.38 | 0.47 | 0.06 | 0.17 | 0.79 | 0.00 | 0.78 | 0.00 | 0.48 | 0.00 | 0.39 | 0.29 | 0.44 | 0.03 | — | 0.45 | 0.03 | 0.06 | 0.00 |
| **Sycophant** | 0.23 | 0.27 | 0.06 | 0.10 | 0.54 | 0.04 | 0.44 | 0.10 | 0.52 | 0.06 | 0.43 | 0.07 | 0.36 | 0.00 | 0.48 | — | 0.00 | 0.00 | 0.11 |
| **TitForTat** | 0.86 | 0.97 | 0.50 | 0.84 | 1.00 | 0.45 | 1.00 | 0.41 | 0.94 | 0.53 | 0.97 | 0.44 | 0.85 | 0.38 | 0.97 | 1.00 | — | 0.36 | 0.38 |
| **TrustfulCooperator** | 0.87 | 0.97 | 0.64 | 0.86 | 1.00 | 0.38 | 1.00 | 0.39 | 1.00 | 0.55 | 0.91 | 0.72 | 0.69 | 0.50 | 0.94 | 1.00 | 0.64 | — | 0.50 |
| **ValueGreedy** | 0.93 | 0.94 | 0.65 | 0.79 | 1.00 | 0.35 | 1.00 | 0.47 | 0.94 | 0.27 | 0.92 | 0.55 | 0.86 | 0.28 | 1.00 | 0.89 | 0.62 | 0.50 | — |

## Lead-change frequency

Mean lead changes per game: **1.82**

Median: 1, max: 8, games with 0 changes: 16

## Order-type distribution (across all games × all players × all turns)

- **Hold:** 26.6%
- **Move:** 62.1%
- **Support:** 11.2%

## Dislodgement rate

Mean dislodgements per game: **3.57**

Games with at least one dislodgement: 514 of 1000

## Betrayer success vs TitForTat

When Betrayer X and TitForTat appear in the same game, average score difference (X − TitForTat):

- **Sycophant** vs TitForTat (n=34): -108.50 (TitForTat punishes)
- **OpportunisticBetrayer** vs TitForTat (n=33): -79.67 (TitForTat punishes)

## Winner vs 2nd-place score gap

Mean gap: 72.41, median: 56

