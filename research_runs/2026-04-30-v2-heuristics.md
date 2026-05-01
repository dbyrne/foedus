# Bundle 7 — Sim Sweep Analysis

**Total games analyzed:** 1000

## Per-heuristic final score (across all game-instances)

| Heuristic | n games | mean | median | stddev | min | max |
|---|---|---|---|---|---|---|
| Aggressive | 212 | 62.42 | 48.50 | 38.99 | 11 | 229 |
| AntiLeader | 191 | 46.51 | 44.00 | 25.72 | 6 | 129 |
| Bandwagon | 228 | 134.70 | 129.00 | 54.11 | 17 | 281 |
| CoalitionBuilder | 199 | 84.23 | 77.00 | 40.32 | 9 | 203 |
| ConservativeBuilder | 240 | 23.73 | 25.00 | 4.02 | 5 | 25 |
| Cooperator | 199 | 163.93 | 166.00 | 65.93 | 21 | 327 |
| Defensive | 198 | 24.13 | 25.00 | 3.27 | 7 | 25 |
| DishonestCooperator | 206 | 152.30 | 147.50 | 59.91 | 32 | 307 |
| Greedy | 218 | 42.85 | 33.50 | 23.85 | 7 | 132 |
| GreedyHold | 212 | 130.80 | 130.00 | 51.67 | 14 | 282 |
| LateCloser | 216 | 46.35 | 40.50 | 28.28 | 7 | 164 |
| Opportunist | 229 | 121.40 | 107.00 | 73.10 | 13 | 359 |
| OpportunisticBetrayer | 235 | 54.49 | 45.00 | 38.71 | 6 | 278 |
| Patron | 205 | 173.26 | 176.00 | 71.41 | 24 | 356 |
| Random | 211 | 44.32 | 36.00 | 30.31 | 6 | 182 |
| Sycophant | 207 | 42.84 | 38.00 | 22.96 | 9 | 134 |
| TitForTat | 206 | 140.08 | 131.00 | 53.03 | 23 | 306 |
| TrustfulCooperator | 206 | 162.40 | 160.00 | 73.76 | 21 | 340 |
| ValueGreedy | 182 | 143.76 | 143.00 | 59.58 | 32 | 313 |

## Pairing win-rate matrix (row vs column)

Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).

| | Aggressive | AntiLeader | Bandwagon | CoalitionBuilder | ConservativeBuilder | Cooperator | Defensive | DishonestCooperator | Greedy | GreedyHold | LateCloser | Opportunist | OpportunisticBetrayer | Patron | Random | Sycophant | TitForTat | TrustfulCooperator | ValueGreedy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Aggressive** | — | 0.54 | 0.24 | 0.33 | 0.77 | 0.12 | 0.81 | 0.08 | 0.57 | 0.12 | 0.56 | 0.16 | 0.53 | 0.10 | 0.59 | 0.62 | 0.14 | 0.13 | 0.07 |
| **AntiLeader** | 0.29 | — | 0.15 | 0.13 | 0.82 | 0.03 | 0.67 | 0.08 | 0.64 | 0.07 | 0.54 | 0.14 | 0.33 | 0.04 | 0.42 | 0.43 | 0.03 | 0.06 | 0.06 |
| **Bandwagon** | 0.76 | 0.85 | — | 0.94 | 0.97 | 0.38 | 0.97 | 0.43 | 0.94 | 0.52 | 0.95 | 0.64 | 0.86 | 0.51 | 0.94 | 0.94 | 0.47 | 0.38 | 0.32 |
| **CoalitionBuilder** | 0.67 | 0.87 | 0.06 | — | 1.00 | 0.23 | 1.00 | 0.05 | 0.82 | 0.23 | 0.88 | 0.31 | 0.68 | 0.06 | 0.80 | 0.90 | 0.13 | 0.18 | 0.21 |
| **ConservativeBuilder** | 0.00 | 0.03 | 0.00 | 0.00 | — | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | 0.02 | 0.00 | 0.14 | 0.00 | 0.15 | 0.14 | 0.00 | 0.00 | 0.00 |
| **Cooperator** | 0.88 | 0.97 | 0.62 | 0.77 | 1.00 | — | 1.00 | 0.59 | 1.00 | 0.62 | 0.96 | 0.81 | 0.89 | 0.45 | 1.00 | 0.96 | 0.52 | 0.65 | 0.65 |
| **Defensive** | 0.03 | 0.10 | 0.00 | 0.00 | 0.04 | 0.00 | — | 0.00 | 0.09 | 0.00 | 0.09 | 0.04 | 0.17 | 0.00 | 0.22 | 0.15 | 0.00 | 0.00 | 0.00 |
| **DishonestCooperator** | 0.92 | 0.92 | 0.57 | 0.95 | 1.00 | 0.41 | 1.00 | — | 0.90 | 0.54 | 0.97 | 0.58 | 0.95 | 0.29 | 1.00 | 0.90 | 0.59 | 0.52 | 0.53 |
| **Greedy** | 0.24 | 0.36 | 0.06 | 0.16 | 0.44 | 0.00 | 0.48 | 0.10 | — | 0.00 | 0.29 | 0.16 | 0.41 | 0.00 | 0.48 | 0.36 | 0.06 | 0.00 | 0.03 |
| **GreedyHold** | 0.88 | 0.93 | 0.45 | 0.77 | 1.00 | 0.38 | 1.00 | 0.46 | 1.00 | — | 0.93 | 0.60 | 0.83 | 0.24 | 1.00 | 0.94 | 0.44 | 0.45 | 0.77 |
| **LateCloser** | 0.28 | 0.31 | 0.05 | 0.12 | 0.67 | 0.04 | 0.42 | 0.03 | 0.48 | 0.07 | — | 0.08 | 0.39 | 0.03 | 0.52 | 0.35 | 0.03 | 0.06 | 0.05 |
| **Opportunist** | 0.84 | 0.86 | 0.36 | 0.69 | 1.00 | 0.19 | 0.96 | 0.42 | 0.84 | 0.40 | 0.92 | — | 0.84 | 0.03 | 0.71 | 0.90 | 0.50 | 0.28 | 0.39 |
| **OpportunisticBetrayer** | 0.32 | 0.56 | 0.14 | 0.32 | 0.66 | 0.11 | 0.57 | 0.05 | 0.45 | 0.17 | 0.39 | 0.16 | — | 0.11 | 0.56 | 0.51 | 0.15 | 0.20 | 0.03 |
| **Patron** | 0.90 | 0.96 | 0.46 | 0.94 | 1.00 | 0.55 | 1.00 | 0.71 | 1.00 | 0.76 | 0.97 | 0.97 | 0.89 | — | 0.97 | 1.00 | 0.65 | 0.53 | 0.76 |
| **Random** | 0.38 | 0.47 | 0.06 | 0.17 | 0.76 | 0.00 | 0.78 | 0.00 | 0.48 | 0.00 | 0.42 | 0.29 | 0.41 | 0.03 | — | 0.41 | 0.03 | 0.06 | 0.00 |
| **Sycophant** | 0.23 | 0.27 | 0.06 | 0.10 | 0.54 | 0.04 | 0.44 | 0.10 | 0.52 | 0.06 | 0.43 | 0.10 | 0.38 | 0.00 | 0.52 | — | 0.00 | 0.00 | 0.11 |
| **TitForTat** | 0.86 | 0.97 | 0.50 | 0.87 | 1.00 | 0.48 | 1.00 | 0.41 | 0.94 | 0.53 | 0.97 | 0.47 | 0.85 | 0.35 | 0.97 | 1.00 | — | 0.36 | 0.38 |
| **TrustfulCooperator** | 0.87 | 0.94 | 0.62 | 0.82 | 1.00 | 0.35 | 1.00 | 0.48 | 1.00 | 0.55 | 0.94 | 0.66 | 0.80 | 0.47 | 0.94 | 1.00 | 0.64 | — | 0.50 |
| **ValueGreedy** | 0.93 | 0.94 | 0.62 | 0.79 | 1.00 | 0.35 | 1.00 | 0.47 | 0.94 | 0.23 | 0.92 | 0.61 | 0.97 | 0.24 | 1.00 | 0.89 | 0.62 | 0.50 | — |

## Lead-change frequency

Mean lead changes per game: **1.84**

Median: 1, max: 9, games with 0 changes: 16

## Order-type distribution (across all games × all players × all turns)

- **Hold:** 27.2%
- **Move:** 62.0%
- **Support:** 10.8%

## Dislodgement rate

Mean dislodgements per game: **4.20**

Games with at least one dislodgement: 523 of 1000

## Betrayer success vs TitForTat

When Betrayer X and TitForTat appear in the same game, average score difference (X − TitForTat):

- **Sycophant** vs TitForTat (n=34): -108.21 (TitForTat punishes)
- **OpportunisticBetrayer** vs TitForTat (n=33): -82.58 (TitForTat punishes)

## Winner vs 2nd-place score gap

Mean gap: 77.96, median: 59

