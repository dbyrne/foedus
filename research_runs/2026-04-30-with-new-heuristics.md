# Bundle 7 — Sim Sweep Analysis

**Total games analyzed:** 1000

## Per-heuristic final score (across all game-instances)

| Heuristic | n games | mean | median | stddev | min | max |
|---|---|---|---|---|---|---|
| Aggressive | 212 | 62.67 | 48.50 | 38.88 | 11 | 229 |
| AntiLeader | 191 | 47.83 | 44.00 | 27.42 | 6 | 157 |
| Bandwagon | 228 | 132.91 | 127.50 | 54.22 | 17 | 266 |
| CoalitionBuilder | 199 | 96.06 | 94.00 | 46.49 | 9 | 233 |
| ConservativeBuilder | 240 | 23.66 | 25.00 | 4.04 | 5 | 25 |
| Cooperator | 199 | 160.90 | 164.00 | 65.90 | 21 | 327 |
| Defensive | 198 | 24.09 | 25.00 | 3.24 | 7 | 25 |
| DishonestCooperator | 206 | 152.28 | 150.50 | 61.14 | 32 | 307 |
| Greedy | 218 | 43.57 | 36.00 | 24.66 | 8 | 152 |
| GreedyHold | 212 | 131.65 | 129.50 | 53.81 | 14 | 292 |
| LateCloser | 216 | 47.17 | 41.00 | 28.50 | 7 | 200 |
| Opportunist | 229 | 120.70 | 98.00 | 74.23 | 13 | 359 |
| OpportunisticBetrayer | 235 | 58.18 | 47.00 | 42.73 | 6 | 278 |
| Patron | 205 | 172.42 | 172.00 | 72.25 | 24 | 356 |
| Random | 211 | 43.81 | 36.00 | 28.40 | 7 | 152 |
| Sycophant | 207 | 44.60 | 39.00 | 24.33 | 9 | 150 |
| TitForTat | 206 | 137.36 | 129.00 | 55.43 | 14 | 306 |
| TrustfulCooperator | 206 | 163.54 | 162.50 | 73.93 | 21 | 358 |
| ValueGreedy | 182 | 142.34 | 141.50 | 59.54 | 32 | 313 |

## Pairing win-rate matrix (row vs column)

Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).

| | Aggressive | AntiLeader | Bandwagon | CoalitionBuilder | ConservativeBuilder | Cooperator | Defensive | DishonestCooperator | Greedy | GreedyHold | LateCloser | Opportunist | OpportunisticBetrayer | Patron | Random | Sycophant | TitForTat | TrustfulCooperator | ValueGreedy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Aggressive** | — | 0.50 | 0.24 | 0.24 | 0.81 | 0.12 | 0.81 | 0.12 | 0.57 | 0.12 | 0.59 | 0.14 | 0.51 | 0.10 | 0.59 | 0.62 | 0.14 | 0.13 | 0.07 |
| **AntiLeader** | 0.36 | — | 0.15 | 0.20 | 0.85 | 0.03 | 0.67 | 0.04 | 0.64 | 0.07 | 0.62 | 0.14 | 0.33 | 0.04 | 0.42 | 0.40 | 0.03 | 0.09 | 0.11 |
| **Bandwagon** | 0.76 | 0.85 | — | 0.80 | 0.97 | 0.33 | 0.97 | 0.43 | 0.94 | 0.48 | 0.95 | 0.61 | 0.80 | 0.49 | 0.94 | 0.94 | 0.43 | 0.38 | 0.32 |
| **CoalitionBuilder** | 0.76 | 0.80 | 0.20 | — | 1.00 | 0.29 | 1.00 | 0.11 | 0.79 | 0.29 | 0.88 | 0.41 | 0.70 | 0.16 | 0.85 | 0.84 | 0.35 | 0.21 | 0.17 |
| **ConservativeBuilder** | 0.00 | 0.03 | 0.00 | 0.00 | — | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | 0.04 | 0.00 | 0.14 | 0.00 | 0.15 | 0.14 | 0.00 | 0.00 | 0.00 |
| **Cooperator** | 0.88 | 0.97 | 0.68 | 0.71 | 1.00 | — | 1.00 | 0.56 | 1.00 | 0.59 | 0.96 | 0.78 | 0.86 | 0.39 | 1.00 | 0.96 | 0.48 | 0.58 | 0.62 |
| **Defensive** | 0.03 | 0.10 | 0.00 | 0.00 | 0.04 | 0.00 | — | 0.00 | 0.14 | 0.00 | 0.09 | 0.04 | 0.17 | 0.00 | 0.22 | 0.17 | 0.00 | 0.00 | 0.00 |
| **DishonestCooperator** | 0.88 | 0.96 | 0.57 | 0.89 | 1.00 | 0.44 | 1.00 | — | 0.90 | 0.49 | 0.97 | 0.64 | 0.95 | 0.29 | 1.00 | 0.86 | 0.59 | 0.52 | 0.50 |
| **Greedy** | 0.24 | 0.36 | 0.06 | 0.18 | 0.47 | 0.00 | 0.45 | 0.10 | — | 0.00 | 0.32 | 0.16 | 0.43 | 0.00 | 0.48 | 0.40 | 0.09 | 0.00 | 0.03 |
| **GreedyHold** | 0.88 | 0.93 | 0.48 | 0.71 | 1.00 | 0.41 | 1.00 | 0.51 | 1.00 | — | 0.93 | 0.60 | 0.83 | 0.24 | 1.00 | 0.94 | 0.44 | 0.42 | 0.77 |
| **LateCloser** | 0.25 | 0.26 | 0.05 | 0.12 | 0.67 | 0.04 | 0.42 | 0.03 | 0.45 | 0.07 | — | 0.12 | 0.35 | 0.03 | 0.55 | 0.41 | 0.03 | 0.09 | 0.08 |
| **Opportunist** | 0.86 | 0.86 | 0.36 | 0.59 | 1.00 | 0.22 | 0.96 | 0.33 | 0.84 | 0.40 | 0.88 | — | 0.81 | 0.03 | 0.71 | 0.90 | 0.56 | 0.24 | 0.39 |
| **OpportunisticBetrayer** | 0.34 | 0.56 | 0.20 | 0.30 | 0.66 | 0.14 | 0.57 | 0.05 | 0.43 | 0.17 | 0.42 | 0.19 | — | 0.15 | 0.59 | 0.54 | 0.21 | 0.20 | 0.07 |
| **Patron** | 0.90 | 0.96 | 0.49 | 0.84 | 1.00 | 0.61 | 1.00 | 0.71 | 1.00 | 0.76 | 0.97 | 0.97 | 0.85 | — | 0.97 | 1.00 | 0.65 | 0.53 | 0.76 |
| **Random** | 0.38 | 0.47 | 0.06 | 0.12 | 0.76 | 0.00 | 0.78 | 0.00 | 0.48 | 0.00 | 0.42 | 0.29 | 0.39 | 0.03 | — | 0.45 | 0.03 | 0.06 | 0.00 |
| **Sycophant** | 0.23 | 0.30 | 0.06 | 0.16 | 0.57 | 0.04 | 0.44 | 0.14 | 0.52 | 0.06 | 0.41 | 0.10 | 0.38 | 0.00 | 0.48 | — | 0.03 | 0.00 | 0.11 |
| **TitForTat** | 0.86 | 0.97 | 0.53 | 0.61 | 1.00 | 0.52 | 1.00 | 0.41 | 0.91 | 0.53 | 0.97 | 0.44 | 0.79 | 0.35 | 0.97 | 0.97 | — | 0.33 | 0.38 |
| **TrustfulCooperator** | 0.87 | 0.91 | 0.62 | 0.79 | 1.00 | 0.42 | 1.00 | 0.48 | 1.00 | 0.55 | 0.91 | 0.69 | 0.80 | 0.47 | 0.94 | 1.00 | 0.67 | — | 0.50 |
| **ValueGreedy** | 0.93 | 0.89 | 0.62 | 0.83 | 1.00 | 0.38 | 1.00 | 0.50 | 0.94 | 0.23 | 0.92 | 0.61 | 0.93 | 0.24 | 1.00 | 0.89 | 0.62 | 0.50 | — |

## Lead-change frequency

Mean lead changes per game: **1.84**

Median: 1, max: 8, games with 0 changes: 16

## Order-type distribution (across all games × all players × all turns)

- **Hold:** 27.2%
- **Move:** 62.2%
- **Support:** 10.6%

## Dislodgement rate

Mean dislodgements per game: **4.33**

Games with at least one dislodgement: 521 of 1000

## Betrayer success vs TitForTat

When Betrayer X and TitForTat appear in the same game, average score difference (X − TitForTat):

- **Sycophant** vs TitForTat (n=34): -101.38 (TitForTat punishes)
- **OpportunisticBetrayer** vs TitForTat (n=33): -71.82 (TitForTat punishes)

## Winner vs 2nd-place score gap

Mean gap: 78.98, median: 62

