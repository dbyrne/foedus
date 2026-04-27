# agent_game

A small multiplayer strategy game designed as a sandbox for training neural
networks against search-resistant opponents — more like Go or poker than chess.

Inspired by [Diplomacy](https://en.wikipedia.org/wiki/Diplomacy_(game)):
simultaneous secret orders, multi-agent alliance dynamics, fog of war,
procedural maps. Stripped down enough that the engine fits in roughly 1k LOC
and the test suite runs in 50ms — rich enough that minimax and alpha-beta are
useless.

## Why this exists

Training NNs on chess-likes is well-trodden. The interesting frontier is
multi-agent games where:

- **Simultaneous orders** kill the game tree (no minimax).
- **Hidden information** (fog of war) demands belief modeling.
- **3+ players** force real alliance reasoning, not zero-sum optimization.
- **Procedural maps** prevent memorization, force generalization.

`agent_game` is a small, hackable testbed for those problems.

## Install

```sh
git clone https://github.com/dbyrne/agent_game.git
cd agent_game
pip install -e .[dev]
pytest      # 88 tests, ~70ms
```

## Your first game

```python
from agent_game import GameConfig, RandomAgent, play_game

config = GameConfig(num_players=4, seed=42, max_turns=20)
agents = {p: RandomAgent(seed=p) for p in range(4)}

final = play_game(agents, config=config)
print(f"Winner: player {final.winner}")
print(f"Final scores: {final.final_scores()}")
```

Or step through interactively:

```sh
python -m agent_game.cli --players 4 --seed 42
```

## Build your own agent

The `Agent` protocol is one method:

```python
from agent_game import GameState, PlayerId, UnitId, Order
from agent_game.legal import legal_orders_for_unit
from agent_game.fog import visible_state_for

class GreedyAgent:
    """Whenever possible, move toward an unowned supply center."""

    def choose_orders(
        self, state: GameState, player: PlayerId
    ) -> dict[UnitId, Order]:
        view = visible_state_for(state, player)  # honor fog
        orders = {}
        for unit in state.units.values():
            if unit.owner != player:
                continue
            legal = legal_orders_for_unit(state, unit.id)
            # Replace with your own logic; here we just hold.
            orders[unit.id] = legal[0]
        return orders
```

That's the whole interface — anything implementing `choose_orders` is an
agent. Plug it into `play_game({0: GreedyAgent(), 1: RandomAgent(), …}, config)`.

## The game in 30 seconds

- Procedural hex map of ~37 nodes, freshly generated each game.
- 2–6 players, one **home node** each on the perimeter.
- Each turn, all players simultaneously and secretly write **orders** for each unit:
  - **Hold** — stay put.
  - **Move** — go to an adjacent node.
  - **Support** — lend +1 strength to an ally's hold or move.
- Strength comparison resolves contested moves; ties bounce; supports get cut by attacks.
- Every 3 turns, a **build phase**: extra units spawn at unoccupied territory you control, up to your supply-center count.
- Score +1 per turn per controlled supply center. Highest cumulative score after 25 turns wins (or last player standing).

The simplifications vs. full Diplomacy are deliberate: dislodged units are
eliminated (no retreat phase), no convoys, head-to-head uses simple
move-strength comparison. Documented in
[`agent_game/resolve.py`](agent_game/resolve.py).

## Architecture

```
agent_game/
  core.py             types: GameState, Map, Unit, Order subclasses
  mapgen.py           procedural hex map generation
  resolve.py          simultaneous-order resolution
  fog.py              per-player visible-state filtering
  legal.py            enumerate geometrically-valid orders for a unit
  loop.py             play_game(agents, config) -> final GameState
  cli.py              interactive REPL
  agents/
    base.py           Agent protocol
    random_agent.py   uniform-random reference agent
tests/                88 tests, all passing in ~70ms
```

## Roadmap

- [x] **v1**: engine, fog, procedural maps, random agent, tests, docs
- [ ] **v1.5**: heuristic agent + replay tooling
- [ ] **v2**: small NN trained via no-press self-play
- [ ] **v3**: MCP wrapper + local LLM (Ollama) negotiator for press play

The longer-term plan is a two-tier architecture inspired by Meta's Cicero, at
much smaller scale: a strategic NN trained via no-press self-play, paired with
a local LLM (via [Ollama](https://ollama.com)) handling chat-based negotiation
at inference time. The NN never sees chat; the LLM bias-injects soft
constraints into the NN's policy. The MCP wrapper means you can swap any
LLM (local or Claude, Gemini, etc.) into the negotiator slot.

## Status

v1, pre-release. Engine internals (resolution rules, state semantics) are
well-tested and stable. The agent-facing API may shift before v1.0 if usage
feedback suggests improvements. Issues and PRs welcome.

## License

MIT — see [LICENSE](LICENSE).
