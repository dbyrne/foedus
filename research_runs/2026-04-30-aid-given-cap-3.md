# Bundle 7 — Sim Sweep Analysis

**Total games analyzed:** 1000

## Per-heuristic final score (across all game-instances)

| Heuristic | n games | mean | median | stddev | min | max |
|---|---|---|---|---|---|---|
| Aggressive | 212 | 61.93 | 48.50 | 38.20 | 11 | 229 |
| AntiLeader | 191 | 46.13 | 44.00 | 25.60 | 6 | 125 |
| Bandwagon | 228 | 134.24 | 129.00 | 54.72 | 17 | 281 |
| CoalitionBuilder | 199 | 87.86 | 79.00 | 40.69 | 9 | 203 |
| ConservativeBuilder | 240 | 23.82 | 25.00 | 3.95 | 5 | 25 |
| Cooperator | 199 | 160.67 | 166.00 | 62.52 | 21 | 327 |
| Defensive | 198 | 24.14 | 25.00 | 3.26 | 7 | 25 |
| DishonestCooperator | 206 | 154.61 | 149.00 | 61.54 | 32 | 314 |
| Greedy | 218 | 43.07 | 35.50 | 23.94 | 7 | 132 |
| GreedyHold | 212 | 130.57 | 130.50 | 51.91 | 14 | 282 |
| LateCloser | 216 | 47.69 | 41.00 | 31.67 | 7 | 244 |
| Opportunist | 229 | 127.69 | 117.00 | 71.27 | 13 | 357 |
| OpportunisticBetrayer | 235 | 56.97 | 47.00 | 43.00 | 6 | 318 |
| Patron | 205 | 159.68 | 159.00 | 61.08 | 24 | 309 |
| Random | 211 | 44.21 | 38.00 | 30.16 | 6 | 182 |
| Sycophant | 207 | 42.87 | 36.00 | 23.19 | 9 | 134 |
| TitForTat | 206 | 139.63 | 131.00 | 53.09 | 23 | 306 |
| TrustfulCooperator | 206 | 156.22 | 159.00 | 63.20 | 21 | 340 |
| ValueGreedy | 182 | 144.01 | 142.50 | 59.25 | 32 | 313 |

## Pairing win-rate matrix (row vs column)

Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).

| | Aggressive | AntiLeader | Bandwagon | CoalitionBuilder | ConservativeBuilder | Cooperator | Defensive | DishonestCooperator | Greedy | GreedyHold | LateCloser | Opportunist | OpportunisticBetrayer | Patron | Random | Sycophant | TitForTat | TrustfulCooperator | ValueGreedy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Aggressive** | — | 0.54 | 0.24 | 0.33 | 0.77 | 0.12 | 0.81 | 0.08 | 0.57 | 0.12 | 0.53 | 0.19 | 0.51 | 0.07 | 0.59 | 0.62 | 0.14 | 0.13 | 0.07 |
| **AntiLeader** | 0.29 | — | 0.15 | 0.17 | 0.82 | 0.03 | 0.67 | 0.08 | 0.64 | 0.07 | 0.51 | 0.14 | 0.33 | 0.04 | 0.42 | 0.43 | 0.03 | 0.03 | 0.06 |
| **Bandwagon** | 0.76 | 0.85 | — | 0.94 | 0.97 | 0.45 | 0.97 | 0.43 | 0.94 | 0.48 | 0.95 | 0.61 | 0.86 | 0.51 | 0.94 | 0.94 | 0.47 | 0.33 | 0.32 |
| **CoalitionBuilder** | 0.67 | 0.83 | 0.06 | — | 1.00 | 0.26 | 1.00 | 0.05 | 0.82 | 0.23 | 0.88 | 0.36 | 0.76 | 0.13 | 0.80 | 0.90 | 0.16 | 0.14 | 0.21 |
| **ConservativeBuilder** | 0.00 | 0.06 | 0.00 | 0.00 | — | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | 0.02 | 0.00 | 0.09 | 0.00 | 0.12 | 0.14 | 0.00 | 0.00 | 0.00 |
| **Cooperator** | 0.88 | 0.97 | 0.55 | 0.74 | 1.00 | — | 1.00 | 0.59 | 1.00 | 0.59 | 0.92 | 0.86 | 0.89 | 0.64 | 1.00 | 0.96 | 0.55 | 0.58 | 0.65 |
| **Defensive** | 0.03 | 0.10 | 0.00 | 0.00 | 0.04 | 0.00 | — | 0.00 | 0.09 | 0.00 | 0.09 | 0.02 | 0.10 | 0.00 | 0.22 | 0.15 | 0.00 | 0.00 | 0.00 |
| **DishonestCooperator** | 0.92 | 0.92 | 0.57 | 0.95 | 1.00 | 0.41 | 1.00 | — | 0.90 | 0.54 | 0.97 | 0.64 | 0.92 | 0.54 | 1.00 | 0.90 | 0.59 | 0.65 | 0.53 |
| **Greedy** | 0.24 | 0.36 | 0.06 | 0.16 | 0.44 | 0.00 | 0.45 | 0.10 | — | 0.00 | 0.35 | 0.14 | 0.39 | 0.00 | 0.48 | 0.36 | 0.06 | 0.00 | 0.03 |
| **GreedyHold** | 0.88 | 0.93 | 0.48 | 0.77 | 1.00 | 0.41 | 1.00 | 0.46 | 1.00 | — | 0.93 | 0.54 | 0.79 | 0.21 | 1.00 | 0.94 | 0.44 | 0.45 | 0.73 |
| **LateCloser** | 0.31 | 0.33 | 0.05 | 0.12 | 0.67 | 0.08 | 0.42 | 0.03 | 0.39 | 0.07 | — | 0.04 | 0.39 | 0.03 | 0.55 | 0.35 | 0.03 | 0.09 | 0.05 |
| **Opportunist** | 0.81 | 0.86 | 0.39 | 0.64 | 1.00 | 0.14 | 0.98 | 0.36 | 0.84 | 0.46 | 0.96 | — | 0.86 | 0.17 | 0.71 | 0.90 | 0.56 | 0.24 | 0.45 |
| **OpportunisticBetrayer** | 0.34 | 0.56 | 0.14 | 0.24 | 0.71 | 0.11 | 0.63 | 0.08 | 0.48 | 0.21 | 0.39 | 0.14 | — | 0.07 | 0.54 | 0.54 | 0.15 | 0.27 | 0.07 |
| **Patron** | 0.93 | 0.96 | 0.46 | 0.87 | 1.00 | 0.36 | 1.00 | 0.46 | 1.00 | 0.79 | 0.97 | 0.83 | 0.93 | — | 0.97 | 1.00 | 0.62 | 0.50 | 0.72 |
| **Random** | 0.38 | 0.47 | 0.06 | 0.17 | 0.79 | 0.00 | 0.78 | 0.00 | 0.48 | 0.00 | 0.39 | 0.29 | 0.44 | 0.03 | — | 0.45 | 0.03 | 0.06 | 0.00 |
| **Sycophant** | 0.23 | 0.27 | 0.06 | 0.10 | 0.54 | 0.04 | 0.44 | 0.10 | 0.52 | 0.06 | 0.43 | 0.10 | 0.36 | 0.00 | 0.48 | — | 0.00 | 0.00 | 0.11 |
| **TitForTat** | 0.86 | 0.97 | 0.50 | 0.84 | 1.00 | 0.45 | 1.00 | 0.41 | 0.94 | 0.53 | 0.97 | 0.44 | 0.85 | 0.38 | 0.97 | 1.00 | — | 0.36 | 0.38 |
| **TrustfulCooperator** | 0.87 | 0.97 | 0.67 | 0.86 | 1.00 | 0.42 | 1.00 | 0.35 | 1.00 | 0.55 | 0.91 | 0.72 | 0.73 | 0.47 | 0.94 | 1.00 | 0.64 | — | 0.50 |
| **ValueGreedy** | 0.93 | 0.94 | 0.65 | 0.79 | 1.00 | 0.35 | 1.00 | 0.47 | 0.94 | 0.27 | 0.92 | 0.55 | 0.93 | 0.28 | 1.00 | 0.89 | 0.62 | 0.50 | — |

## Lead-change frequency

Mean lead changes per game: **1.83**

Median: 1, max: 10, games with 0 changes: 16

## Order-type distribution (across all games × all players × all turns)

- **Hold:** 26.7%
- **Move:** 62.3%
- **Support:** 11.0%

## Dislodgement rate

Mean dislodgements per game: **3.70**

Games with at least one dislodgement: 515 of 1000

## Betrayer success vs TitForTat

When Betrayer X and TitForTat appear in the same game, average score difference (X − TitForTat):

- **Sycophant** vs TitForTat (n=34): -108.50 (TitForTat punishes)
- **OpportunisticBetrayer** vs TitForTat (n=33): -80.61 (TitForTat punishes)

## Winner vs 2nd-place score gap

Mean gap: 72.26, median: 54

