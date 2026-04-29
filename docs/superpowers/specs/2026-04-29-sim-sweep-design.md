# Bundle 7 — Bulk simulation harness + diverse heuristic roster

**Status:** Design approved. Ready for implementation plan.
**Date:** 2026-04-29
**Author:** David Erner + Claude (Opus)

## Why

Up to now we have evaluated game design changes through small-N LLM
playtests (~1–2 games per change). That gives anecdotal signal but not
statistical signal. We can't quantify "is this mechanic adding strategic
depth?" without running many games across many strategies.

The foedus engine is fast (~50–100 ms per game). We can run thousands of
games in minutes. What's missing is **diverse heuristic agents** — right
now we have just `HeuristicAgent` (greedy expansion) and `RandomAgent`.
You can't measure rock-paper-scissors dynamics with two strategies.

This bundle builds:
1. A roster of 11 heuristic strategies (8 "honest" + 3 "betrayer"
   variants) that span the strategy space.
2. A bulk simulation harness that runs N games with random pairings
   from the roster, recording per-game stats.
3. An analysis script that computes depth-indicator metrics from the
   per-game data.
4. A baseline run on `main` to give us our first depth numbers.

The output is a research artifact — both code (reusable for future
mechanic-change evaluation) and a baseline analysis document. After this
lands, every Bundle that changes a mechanic (Bundle 4 alliance
multipliers, etc.) gets evaluated against this baseline using the same
sweep.

## Out of scope

- D — fog-respecting `legal_orders_for_unit`
- H — threat-context in per-player view
- Chat UX work
- LLM-driven playtests (those continue in their own track via the press
  server / `scripts/foedus_press_*`)

## Heuristic roster

11 heuristics in `foedus/agents/heuristics/` (new package). Each
implements the existing `Agent` Protocol (`choose_orders`,
`choose_press`, `chat_drafts`).

The eight "honest" heuristics:

| # | Name | Strategy summary |
|---|---|---|
| 1 | **Random** | random legal orders (existing — moved into the package) |
| 2 | **Greedy** | walk to nearest unowned supply, never holds (existing — moved) |
| 3 | **GreedyHold** | walk to nearest unowned supply, then HOLD on it for one turn to flip via Bundle 2 rule (b) |
| 4 | **Defensive** | hold home + adjacent supplies; never advance further |
| 5 | **Aggressive** | prioritize dislodging enemy units on supplies. Uses SupportMove when an ally would help; else solo Move |
| 6 | **AntiLeader** | target the opponent with the highest supply count. Pivots target each turn as standings shift |
| 7 | **Bandwagon** | declare ALLY toward all opponents in stance; mirror the leader's last-round order pattern (e.g. if leader expanded, expand; if held, hold) |
| 8 | **ConservativeBuilder** | only capture supplies adjacent to current owned territory; never venture further |

The three betrayers (⚠️ designed to test press / betrayal teeth):

| # | Name | Strategy summary |
|---|---|---|
| 9 | **Sycophant** | declares ALLY in stance toward all; sends a public chat saying "let's cooperate"; actually plays Greedy (no holds, attacks if convenient). Pure deception — no Intent declaration, just stance lying |
| 10 | **OpportunisticBetrayer** | declares ALLY + a public Intent matching their planned move; submits the planned order **unless** an opponent's supply is exposed (held by lone weak unit), in which case they pivot to attack and break their own Intent → triggers BetrayalObservation |
| 11 | **TitForTat** | starts ALLY toward all opponents. Maintains an internal `hostile_set` (in-process, not in `GameState`). At the start of each round, checks `state.betrayals[me]` for any new betrayals from this turn; adds those betrayers' player_ids to `hostile_set`. From then on, declares HOSTILE stance toward anyone in `hostile_set` and prioritizes attacking them. **Never un-HOSTILE'd** — once you betrayed me, you're hostile for the rest of the game. (Simpler than forgive/forget; matches the classic Tit-for-Tat result that early betrayal punishment dominates in iterated games.) |

Each ~50–80 LOC, single-file. Total roster ~700 LOC of heuristic code.

`RandomAgent` and `HeuristicAgent` (the existing names) remain
importable from their old paths via re-exports. No breaking changes for
existing callers.

## Simulation harness

New script: `scripts/foedus_sim_sweep.py`. CLI flags:

| Flag | Default | Meaning |
|---|---|---|
| `--num-games` | 5000 | total games to run |
| `--seed-offset` | 0 | per-game seed = OFFSET + game_id |
| `--max-turns` | 15 | per-game turn cap |
| `--archetype` | continental_sweep | map archetype |
| `--num-players` | 4 | seats per game |
| `--roster` | all 11 | comma-separated heuristic names to draw from |
| `--out` | `/tmp/foedus_sim_sweep_<timestamp>.jsonl` | output JSONL path |

Per-game flow:

1. Pick `num_players` heuristics by uniform-random sampling **with
   replacement** from the roster (a 4-player game can have multiple
   instances of the same heuristic).
2. Build a fresh game with the per-game seed.
3. Run the press round-lifecycle to terminal:
   - Each turn, every active player calls `choose_press` (or empty for
     non-press heuristics) → `submit_press_tokens` → `signal_chat_done`
     → `signal_done`.
   - Then `finalize_round(state, orders)` where `orders[player] =
     agent.choose_orders(state, player)`.
4. Capture per-turn snapshots:
   - `supply_counts_per_turn`: dict of `turn → list[int]` (per-player
     supply count after each turn's resolution)
   - `score_per_turn`: dict of `turn → list[float]`
5. Capture per-game aggregates:
   - `order_type_counts`: dict mapping `Hold/Move/SupportHold/SupportMove
     → int` (across all players × all turns)
   - `dislodgement_count`: int (count of "dislodged" outcomes)
   - `betrayal_count_per_player`: list[int]
6. Emit one JSONL record per game.

JSONL schema (one line per game):

```json
{
  "game_id": 0,
  "seed": 0,
  "agents": ["GreedyHold", "Defensive", "Sycophant", "Random"],
  "max_turns_reached": 15,
  "total_turns": 15,
  "is_terminal": true,
  "winners": [0],
  "final_scores": [42.0, 31.0, 27.0, 21.0],
  "supply_counts_per_turn": {"1": [1,1,1,1], "2": [2,1,1,1], ...},
  "score_per_turn": {"1": [1.0,1.0,1.0,1.0], ...},
  "order_type_counts": {"Hold": 24, "Move": 30, "SupportHold": 0, "SupportMove": 6},
  "dislodgement_count": 3,
  "betrayal_count_per_player": [0, 1, 0, 0],
  "detente_reached": false,
  "eliminated": []
}
```

Estimated runtime: **5000 games × ~75 ms = ~6 min** for the default
configuration.

## Analysis script

New script: `scripts/foedus_sim_analyze.py`. Reads a JSONL file (or
multiple) and computes the depth-indicator metrics. Output: a
markdown report at `docs/research/<date>-<topic>-baseline.md`.

### Metrics computed

| Metric | Formula | What it tells us |
|---|---|---|
| **Mean / median final score per heuristic** | aggregate across all games where heuristic appeared | strategic strength ranking |
| **Per-pairing win-rate matrix** (11×11) | for each (A,B) pair, fraction of games where A scored higher than B (when they appeared in same game) | rock-paper-scissors signal — cycles in the directed-win graph indicate real meta-game depth |
| **Score variance per heuristic** | stddev of final scores across games | high = seed/map dominates over strategy; mid = strategy + variance both contribute (depth); zero = pure strategy / no depth |
| **Lead-change frequency** | mean count of times the **unique** score-leader changes per game (ties don't count as a change). For each turn t, compute the unique top scorer (or None if tied). Increment counter when this differs from turn t-1's value (treating None→player or player→None as changes too) | high = contested games; low = predictable |
| **Order-type distribution** | fraction of all orders that are Hold / Move / SupportHold / SupportMove | tells us whether supports are vestigial (~99% Hold/Move = vestigial) or load-bearing |
| **Dislodgement rate per game** | mean dislodgements per game | combat engagement intensity |
| **Betrayer success against TitForTat** | mean (Sycophant final score) − (TitForTat final score) when they appeared in the same game; same for OpportunisticBetrayer | press teeth — if positive, betrayers profit; if negative, TitForTat punishes them; near zero, mixed |
| **Score gap between winner and 2nd place** | distribution | tight = contested; long-tail = blowouts |

The report includes one written paragraph per metric explaining what
the number suggests about the game's current strategic depth.

### Baseline run

After the harness lands, run:

```bash
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py --num-games 5000
PYTHONPATH=. python3 scripts/foedus_sim_analyze.py /tmp/foedus_sim_sweep_*.jsonl
```

Save the analysis output as
`docs/research/2026-04-29-bundle-7-baseline.md` and commit. This becomes
the reference data for evaluating future mechanic changes.

## Components and data flow

```
                ┌──── scripts/foedus_sim_sweep.py ────┐
                │                                      │
                │  for game_id in range(num_games):    │
                │    seed = offset + game_id           │
                │    pick roster → agents              │
                │    initial_state(cfg, generate_map)  │
                │    while not terminal:               │
                │       run press round                │
                │       record snapshots               │
                │    write JSONL line                  │
                └────┬─────────────────────────────────┘
                     │
                     ▼
                JSONL output (~5000 lines, ~5 MB)
                     │
                     ▼
            ┌── scripts/foedus_sim_analyze.py ──┐
            │  load JSONL                       │
            │  compute metrics                  │
            │  emit markdown report             │
            └──────────┬────────────────────────┘
                       │
                       ▼
        docs/research/2026-04-29-bundle-7-baseline.md
```

The harness uses only existing engine APIs (`initial_state`,
`generate_map`, `submit_press_tokens`, `signal_chat_done`, `signal_done`,
`finalize_round`). No engine changes.

## File structure

| File | Status | Responsibility |
|---|---|---|
| `foedus/agents/heuristics/__init__.py` | Create | Package marker; re-exports for backward compat |
| `foedus/agents/heuristics/random_agent.py` | Move | Existing `RandomAgent`, relocated |
| `foedus/agents/heuristics/greedy.py` | Move | Existing `HeuristicAgent` renamed `Greedy` |
| `foedus/agents/heuristics/greedy_hold.py` | Create | New `GreedyHold` |
| `foedus/agents/heuristics/defensive.py` | Create | New `Defensive` |
| `foedus/agents/heuristics/aggressive.py` | Create | New `Aggressive` |
| `foedus/agents/heuristics/anti_leader.py` | Create | New `AntiLeader` |
| `foedus/agents/heuristics/bandwagon.py` | Create | New `Bandwagon` |
| `foedus/agents/heuristics/conservative_builder.py` | Create | New `ConservativeBuilder` |
| `foedus/agents/heuristics/sycophant.py` | Create | New `Sycophant` (betrayer 1) |
| `foedus/agents/heuristics/opportunistic_betrayer.py` | Create | New `OpportunisticBetrayer` (betrayer 2) |
| `foedus/agents/heuristics/tit_for_tat.py` | Create | New `TitForTat` (betrayer 3) |
| `foedus/agents/random_agent.py` | Modify | Backward-compat re-export of `RandomAgent` |
| `foedus/agents/heuristic.py` | Modify | Backward-compat re-export of `HeuristicAgent` (alias for `Greedy`) |
| `scripts/foedus_sim_sweep.py` | Create | The simulation harness |
| `scripts/foedus_sim_analyze.py` | Create | The analysis script |
| `tests/test_heuristics.py` | Create | Unit tests for each heuristic (basic legal-order generation) |
| `tests/test_sim_sweep.py` | Create | Integration test for harness (10 games × 4 turns) |
| `tests/test_sim_analyze.py` | Create | Integration test for analyzer (compute metrics from a small JSONL) |

## Backward compatibility

- `from foedus.agents.heuristic import HeuristicAgent` continues to work
  (re-exports as alias for `Greedy`).
- `from foedus.agents.random_agent import RandomAgent` continues to work
  (re-exports from new location).
- All existing tests using these names pass without modification.
- The legacy `HeuristicAgent` is kept as an alias rather than renamed
  in-place to avoid breaking external callers (foedus-godot E2E tests
  reference `foedus.agents.heuristic.HeuristicAgent` by string).

## Testing

### Unit tests in `tests/test_heuristics.py` (new)

For each of the 11 heuristics, verify:
- `choose_orders(state, player)` returns a dict with one entry per owned
  unit, each entry a valid `Order` for that unit
- `choose_press(state, player)` returns a `Press` (may be empty)
- `chat_drafts(state, player)` returns a list (may be empty)
- For betrayers specifically: their `choose_press` declares stances
  consistent with their strategy spec (e.g. Sycophant always declares
  ALLY toward all)

~30 tests total.

### Integration test in `tests/test_sim_sweep.py` (new)

Runs the harness with `--num-games 10 --max-turns 4` and verifies:
- Exactly 10 JSONL lines emitted
- Each line has all required keys
- Final scores are non-negative integers
- `total_turns <= max_turns`

### Integration test in `tests/test_sim_analyze.py` (new)

Feeds a hand-crafted 5-game JSONL into the analyzer and verifies the
markdown report contains all expected sections + reasonable numeric
values (mean / median calcs verified by hand).

### No engine-level tests needed

Bundle 7 doesn't change the engine. All press / resolve / mapgen tests
keep passing unchanged.

## Open questions resolved

| # | Question | Resolution |
|---|---|---|
| 1 | Scope split | A — Bundle 7 = sim harness + roster (subsumes Bundle 5's heuristic-strategy revision). Remaining Bundle 5 items become Bundle 8. |
| 2 | Roster size | Big with betrayers — 11 heuristics including 3 betrayer variants |
| 3 | Tournament structure | B — random pairings with replacement, 5000 games |
| 4 | Game length | B — 15 turns |

## Success criteria

1. All 11 heuristics implemented, each with passing unit tests.
2. `scripts/foedus_sim_sweep.py` runs cleanly to completion on 5000-game
   sweep in under 10 minutes.
3. `scripts/foedus_sim_analyze.py` produces a markdown report with all
   listed metrics from the JSONL output.
4. Baseline report committed at
   `docs/research/2026-04-29-bundle-7-baseline.md`.
5. Existing test suite (`pytest -q`) stays at 373+ passed plus the new
   tests.
6. Backward-compat: `from foedus.agents.heuristic import HeuristicAgent`
   and `from foedus.agents.random_agent import RandomAgent` still work.
