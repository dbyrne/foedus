# Bundle 7 Sim Sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bulk simulation harness with 11 diverse heuristic agents (8 honest + 3 betrayer variants) so we can quantify game depth across thousands of games.

**Architecture:** Reorganize `foedus/agents/` into a `heuristics/` sub-package, add 9 new heuristic variants alongside the existing 2 (relocated). Add a sweep script (`scripts/foedus_sim_sweep.py`) that runs N games via random pairings and emits JSONL. Add an analyzer (`scripts/foedus_sim_analyze.py`) that computes depth-indicator metrics from the JSONL.

**Tech Stack:** Python 3.10+, pytest. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-04-29-sim-sweep-design.md` (committed at `5ec9d50`).

**Branch:** `bundle7-sim-sweep` (already created off main; commit `5ec9d50` holds the spec).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `foedus/agents/heuristics/__init__.py` | Create | Package marker + re-exports of all 11 heuristic classes |
| `foedus/agents/heuristics/random_agent.py` | Create | `RandomAgent` (relocated from `foedus/agents/random_agent.py`) |
| `foedus/agents/heuristics/greedy.py` | Create | `Greedy` class (relocated from `HeuristicAgent` in `foedus/agents/heuristic.py`) |
| `foedus/agents/heuristics/greedy_hold.py` | Create | `GreedyHold` |
| `foedus/agents/heuristics/defensive.py` | Create | `Defensive` |
| `foedus/agents/heuristics/aggressive.py` | Create | `Aggressive` |
| `foedus/agents/heuristics/anti_leader.py` | Create | `AntiLeader` |
| `foedus/agents/heuristics/bandwagon.py` | Create | `Bandwagon` |
| `foedus/agents/heuristics/conservative_builder.py` | Create | `ConservativeBuilder` |
| `foedus/agents/heuristics/sycophant.py` | Create | `Sycophant` (betrayer) |
| `foedus/agents/heuristics/opportunistic_betrayer.py` | Create | `OpportunisticBetrayer` (betrayer) |
| `foedus/agents/heuristics/tit_for_tat.py` | Create | `TitForTat` (betrayer) |
| `foedus/agents/random_agent.py` | Modify | Replace contents with `from foedus.agents.heuristics.random_agent import RandomAgent` (backward-compat) |
| `foedus/agents/heuristic.py` | Modify | Replace contents with `from foedus.agents.heuristics.greedy import Greedy as HeuristicAgent` (backward-compat) |
| `scripts/foedus_sim_sweep.py` | Create | Bulk simulation harness |
| `scripts/foedus_sim_analyze.py` | Create | Depth-metrics analyzer |
| `tests/test_heuristics.py` | Create | Unit tests for all 11 heuristic variants |
| `tests/test_sim_sweep.py` | Create | Integration test for the sweep harness |
| `tests/test_sim_analyze.py` | Create | Integration test for the analyzer |
| `docs/research/2026-04-29-bundle-7-baseline.md` | Create (Task 6) | Baseline analysis from running the sweep on main |

---

## Task 1: Package skeleton + relocations

**Files:**
- Create: `foedus/agents/heuristics/__init__.py`
- Create: `foedus/agents/heuristics/random_agent.py`
- Create: `foedus/agents/heuristics/greedy.py`
- Modify: `foedus/agents/random_agent.py` (replace with backward-compat re-export)
- Modify: `foedus/agents/heuristic.py` (replace with backward-compat re-export)

This task moves the existing two agents into the new package and verifies backward compatibility. No behavior change.

- [ ] **Step 1: Create `foedus/agents/heuristics/__init__.py`**

```python
"""Heuristic agents for foedus.

Each heuristic is a single-purpose strategy implementation. They share
the foedus.agents.base.Agent Protocol (choose_orders, choose_press,
chat_drafts).

The roster is intentionally diverse so bulk simulation sweeps can
measure rock-paper-scissors dynamics, betrayal teeth, and other
depth-indicator metrics.
"""

from __future__ import annotations

from foedus.agents.heuristics.aggressive import Aggressive
from foedus.agents.heuristics.anti_leader import AntiLeader
from foedus.agents.heuristics.bandwagon import Bandwagon
from foedus.agents.heuristics.conservative_builder import ConservativeBuilder
from foedus.agents.heuristics.defensive import Defensive
from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.agents.heuristics.opportunistic_betrayer import OpportunisticBetrayer
from foedus.agents.heuristics.random_agent import RandomAgent
from foedus.agents.heuristics.sycophant import Sycophant
from foedus.agents.heuristics.tit_for_tat import TitForTat

__all__ = [
    "Aggressive",
    "AntiLeader",
    "Bandwagon",
    "ConservativeBuilder",
    "Defensive",
    "Greedy",
    "GreedyHold",
    "OpportunisticBetrayer",
    "RandomAgent",
    "Sycophant",
    "TitForTat",
]

# Roster registry for the sim sweep harness — name → class. Tasks 2-4
# add to this incrementally as new heuristics land.
ROSTER = {
    "Random": RandomAgent,
    "Greedy": Greedy,
    "GreedyHold": GreedyHold,
    "Defensive": Defensive,
    "Aggressive": Aggressive,
    "AntiLeader": AntiLeader,
    "Bandwagon": Bandwagon,
    "ConservativeBuilder": ConservativeBuilder,
    "Sycophant": Sycophant,
    "OpportunisticBetrayer": OpportunisticBetrayer,
    "TitForTat": TitForTat,
}
```

NOTE: Tasks 2-5 will create the missing files referenced by these imports. For Task 1, only `Random` and `Greedy` exist; the other 9 imports will be `ImportError` until Task 2 adds them. **To make Task 1 land cleanly without a broken import chain, write the `__init__.py` minimally for now (only the 2 existing classes), then expand it as each subsequent task adds heuristics.**

So for Task 1, write `__init__.py` with ONLY these imports:

```python
"""Heuristic agents for foedus.

[same docstring as above]
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics.random_agent import RandomAgent

__all__ = ["Greedy", "RandomAgent"]

ROSTER = {
    "Random": RandomAgent,
    "Greedy": Greedy,
}
```

Subsequent tasks will extend `__all__` and `ROSTER`.

- [ ] **Step 2: Create `foedus/agents/heuristics/random_agent.py`**

Copy the entire content of `foedus/agents/random_agent.py` (the existing file) into the new path. No changes; just relocation.

```python
"""Reference random agent: picks a uniformly-random legal order per unit."""

from __future__ import annotations

import random

from foedus.core import GameState, Order, PlayerId, UnitId
from foedus.legal import legal_orders_for_unit


class RandomAgent:
    """Picks a uniformly-random legal order for each owned unit.

    Useful as a baseline opponent during NN training and as a smoke-test
    for engine correctness (a random agent should never crash the resolver).
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def choose_orders(
        self, state: GameState, player: PlayerId
    ) -> dict[UnitId, Order]:
        orders: dict[UnitId, Order] = {}
        for u in state.units.values():
            if u.owner != player:
                continue
            choices = legal_orders_for_unit(state, u.id)
            orders[u.id] = self._rng.choice(choices)
        return orders

    def choose_press(self, state, player):  # type: ignore[no-untyped-def]
        from foedus.core import Press
        return Press(stance={}, intents=[])

    def chat_drafts(self, state, player):  # type: ignore[no-untyped-def]
        return []
```

- [ ] **Step 3: Create `foedus/agents/heuristics/greedy.py`**

Copy the entire content of `foedus/agents/heuristic.py` into the new path BUT rename the class from `HeuristicAgent` to `Greedy`. Update the docstring's first line accordingly.

```python
"""Greedy expansion heuristic — walks toward nearest unowned supply.

Existing behavior from `foedus.agents.heuristic.HeuristicAgent`,
relocated and renamed for the heuristics package. The public name
`HeuristicAgent` continues to work via a re-export in
`foedus/agents/heuristic.py` for backward compat.

For each owned unit, find the nearest unowned supply center via BFS over
the map graph and move one step toward it. If the unit is already adjacent
to the target, move in. If the path is blocked by an own unit (Rule X says
we can't dislodge own), hold. If no unowned supply is reachable, hold.
This is a deliberately simple baseline.

Note: This heuristic does NOT implement the Bundle 2 hold-to-flip pattern.
Use `GreedyHold` for that (walks then holds to actually flip the supply).
"""

from __future__ import annotations

from collections import deque

from foedus.agents.base import Agent  # noqa: F401  (used by isinstance in tests)
from foedus.core import (
    ChatDraft,
    GameState,
    Hold,
    Move,
    NodeId,
    Order,
    PlayerId,
    Press,
    Stance,
    Unit,
    UnitId,
)


class Greedy:
    """Greedy expansion: each unit walks toward the closest unowned supply.

    Press behavior: ALLY toward the active opponent with closest supply
    count (carried over from the previous HeuristicAgent so existing
    integration tests still pass). No intents, no chat.
    """

    def __init__(self) -> None:
        pass

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        orders: dict[UnitId, Order] = {}
        for unit in state.units.values():
            if unit.owner != player:
                continue
            orders[unit.id] = self._choose_for_unit(state, player, unit)
        return orders

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        my_supply = state.supply_count(player)
        active_opponents = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        if not active_opponents:
            return Press(stance={}, intents=[])
        closest = min(
            active_opponents,
            key=lambda p: (abs(state.supply_count(p) - my_supply), p),
        )
        return Press(stance={closest: Stance.ALLY}, intents=[])

    def chat_drafts(self, state: GameState,
                    player: PlayerId) -> list[ChatDraft]:
        return []

    def _choose_for_unit(self, state: GameState, player: PlayerId,
                         unit: Unit) -> Order:
        target = self._nearest_unowned_supply(state, player, unit.location)
        if target is None:
            return Hold()
        m = state.map
        if m.is_adjacent(unit.location, target):
            occupant = state.unit_at(target)
            if occupant is None or occupant.owner != player:
                return Move(dest=target)
            return Hold()
        next_step = self._step_toward(state, unit.location, target)
        if next_step is None:
            return Hold()
        occupant = state.unit_at(next_step)
        if occupant is None or occupant.owner != player:
            return Move(dest=next_step)
        return Hold()

    @staticmethod
    def _nearest_unowned_supply(state: GameState, player: PlayerId,
                                start: NodeId) -> NodeId | None:
        m = state.map
        visited: set[NodeId] = {start}
        q: deque[NodeId] = deque([start])
        while q:
            node = q.popleft()
            if node != start and m.is_supply(node) \
                    and state.ownership.get(node) != player:
                return node
            for nbr in sorted(m.neighbors(node)):
                if nbr not in visited:
                    visited.add(nbr)
                    q.append(nbr)
        return None

    @staticmethod
    def _step_toward(state: GameState, from_node: NodeId,
                     to_node: NodeId) -> NodeId | None:
        m = state.map
        dist: dict[NodeId, int] = {to_node: 0}
        q: deque[NodeId] = deque([to_node])
        while q:
            node = q.popleft()
            for nbr in sorted(m.neighbors(node)):
                if nbr not in dist:
                    dist[nbr] = dist[node] + 1
                    q.append(nbr)
        best: NodeId | None = None
        best_d = float("inf")
        for nbr in sorted(m.neighbors(from_node)):
            d = dist.get(nbr, float("inf"))
            if d < best_d:
                best_d = d
                best = nbr
        return best
```

- [ ] **Step 4: Replace `foedus/agents/random_agent.py` content**

Replace the entire file contents with:

```python
"""Backward-compat re-export of RandomAgent (Bundle 7).

The implementation lives in foedus.agents.heuristics.random_agent now.
This module re-exports it under its historical import path so existing
callers (including foedus-godot tests that reference the string
"foedus.agents.random_agent.RandomAgent") keep working.
"""

from __future__ import annotations

from foedus.agents.heuristics.random_agent import RandomAgent

__all__ = ["RandomAgent"]
```

- [ ] **Step 5: Replace `foedus/agents/heuristic.py` content**

Replace the entire file contents with:

```python
"""Backward-compat re-export of HeuristicAgent → Greedy (Bundle 7).

The implementation lives in foedus.agents.heuristics.greedy.Greedy now.
This module re-exports it as HeuristicAgent so existing callers
(including foedus-godot tests that reference the string
"foedus.agents.heuristic.HeuristicAgent") keep working.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy import Greedy as HeuristicAgent

__all__ = ["HeuristicAgent"]
```

- [ ] **Step 6: Run the full test suite to verify no regressions**

Run: `python3 -m pytest -q`

Expected: 373 passed, 1 skipped (same as baseline). The relocations are pure refactoring; no behavior changes. If any test fails, inspect the import path issue and fix.

- [ ] **Step 7: Commit**

```bash
git add foedus/agents/heuristics/__init__.py foedus/agents/heuristics/random_agent.py foedus/agents/heuristics/greedy.py foedus/agents/random_agent.py foedus/agents/heuristic.py
git commit -m "$(cat <<'EOF'
Bundle 7: relocate RandomAgent + HeuristicAgent into heuristics package

New package foedus/agents/heuristics/ that will host all 11 heuristic
variants. Tasks 2-5 add the 9 new variants. Task 1 just relocates the
existing 2:
  RandomAgent -> heuristics/random_agent.py (unchanged content)
  HeuristicAgent -> heuristics/greedy.py (renamed Greedy)

Backward compat: foedus.agents.random_agent and foedus.agents.heuristic
are now thin re-exports under their historical paths so external
callers (foedus-godot tests reference these by string) keep working.

No behavior changes. Tests: 373 passed, 1 skipped (unchanged).

Spec: docs/superpowers/specs/2026-04-29-sim-sweep-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 3 simple new heuristics (GreedyHold, Defensive, ConservativeBuilder) + tests

**Files:**
- Create: `foedus/agents/heuristics/greedy_hold.py`
- Create: `foedus/agents/heuristics/defensive.py`
- Create: `foedus/agents/heuristics/conservative_builder.py`
- Modify: `foedus/agents/heuristics/__init__.py` (add the 3 new classes to imports + ROSTER)
- Create: `tests/test_heuristics.py` (start the test file with tests for these 3 + reuse some basic tests for Random/Greedy)

This task adds 3 new heuristic variants plus the test infrastructure for the whole roster.

- [ ] **Step 1: Create `foedus/agents/heuristics/greedy_hold.py`**

Strategy spec: like Greedy, but if a unit is currently AT an unowned supply, HOLD instead of moving away. This triggers Bundle 2 rule (b) — a unit at a supply at start AND end of turn flips ownership.

```python
"""GreedyHold — walks toward nearest unowned supply, then HOLDs to flip.

Bundle 2-aware variant of Greedy. Where Greedy keeps walking forward
turn after turn (ineffective under the dislodge-or-hold rule), GreedyHold
stops to hold and capture each supply via rule (b).

Strategy:
  for each owned unit u:
    if u is at a supply NOT owned by player:
      Hold (will flip via rule (b) at end of turn)
    elif u can reach an unowned supply:
      Move one step toward nearest unowned supply
    else:
      Hold

Press: same as Greedy (ALLY toward closest-supply opponent).
"""

from __future__ import annotations

from collections import deque

from foedus.core import (
    ChatDraft,
    GameState,
    Hold,
    Move,
    NodeId,
    Order,
    PlayerId,
    Press,
    Stance,
    Unit,
    UnitId,
)


class GreedyHold:
    def __init__(self) -> None:
        pass

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        orders: dict[UnitId, Order] = {}
        for unit in state.units.values():
            if unit.owner != player:
                continue
            orders[unit.id] = self._choose_for_unit(state, player, unit)
        return orders

    def _choose_for_unit(self, state: GameState, player: PlayerId,
                         unit: Unit) -> Order:
        m = state.map
        # If we're sitting on an unowned supply, HOLD to flip.
        if m.is_supply(unit.location) \
                and state.ownership.get(unit.location) != player:
            return Hold()
        # Otherwise step toward nearest unowned supply (same as Greedy).
        target = self._nearest_unowned_supply(state, player, unit.location)
        if target is None:
            return Hold()
        if m.is_adjacent(unit.location, target):
            occupant = state.unit_at(target)
            if occupant is None or occupant.owner != player:
                return Move(dest=target)
            return Hold()
        next_step = self._step_toward(state, unit.location, target)
        if next_step is None:
            return Hold()
        occupant = state.unit_at(next_step)
        if occupant is None or occupant.owner != player:
            return Move(dest=next_step)
        return Hold()

    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        my_supply = state.supply_count(player)
        active_opponents = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        if not active_opponents:
            return Press(stance={}, intents=[])
        closest = min(
            active_opponents,
            key=lambda p: (abs(state.supply_count(p) - my_supply), p),
        )
        return Press(stance={closest: Stance.ALLY}, intents=[])

    def chat_drafts(self, state: GameState,
                    player: PlayerId) -> list[ChatDraft]:
        return []

    @staticmethod
    def _nearest_unowned_supply(state: GameState, player: PlayerId,
                                start: NodeId) -> NodeId | None:
        m = state.map
        visited: set[NodeId] = {start}
        q: deque[NodeId] = deque([start])
        while q:
            node = q.popleft()
            if node != start and m.is_supply(node) \
                    and state.ownership.get(node) != player:
                return node
            for nbr in sorted(m.neighbors(node)):
                if nbr not in visited:
                    visited.add(nbr)
                    q.append(nbr)
        return None

    @staticmethod
    def _step_toward(state: GameState, from_node: NodeId,
                     to_node: NodeId) -> NodeId | None:
        m = state.map
        dist: dict[NodeId, int] = {to_node: 0}
        q: deque[NodeId] = deque([to_node])
        while q:
            node = q.popleft()
            for nbr in sorted(m.neighbors(node)):
                if nbr not in dist:
                    dist[nbr] = dist[node] + 1
                    q.append(nbr)
        best: NodeId | None = None
        best_d = float("inf")
        for nbr in sorted(m.neighbors(from_node)):
            d = dist.get(nbr, float("inf"))
            if d < best_d:
                best_d = d
                best = nbr
        return best
```

- [ ] **Step 2: Create `foedus/agents/heuristics/defensive.py`**

Strategy spec: holds owned supplies; never advances beyond them.

```python
"""Defensive — holds owned supplies, never advances.

For each owned unit:
  if u is at any owned supply (home or captured):
    Hold
  elif u is at a supply NOT yet owned by player:
    Hold (will flip via rule (b))
  else:
    move one step toward the nearest owned supply (retreat home)

Press: NEUTRAL toward all (boring opponents are not hostile).
"""

from __future__ import annotations

from collections import deque

from foedus.core import (
    ChatDraft, GameState, Hold, Move, NodeId, Order, PlayerId, Press,
    Unit, UnitId,
)


class Defensive:
    def __init__(self) -> None:
        pass

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        orders: dict[UnitId, Order] = {}
        for unit in state.units.values():
            if unit.owner != player:
                continue
            orders[unit.id] = self._choose_for_unit(state, player, unit)
        return orders

    def _choose_for_unit(self, state, player, unit):
        m = state.map
        # If at supply (owned or unowned), Hold (own supplies stay owned;
        # unowned supplies flip via rule (b)).
        if m.is_supply(unit.location):
            return Hold()
        # Otherwise step back toward an owned supply.
        target = self._nearest_owned_supply(state, player, unit.location)
        if target is None:
            return Hold()
        if m.is_adjacent(unit.location, target):
            return Move(dest=target)
        next_step = self._step_toward(state, unit.location, target)
        if next_step is None:
            return Hold()
        return Move(dest=next_step)

    def choose_press(self, state, player):
        return Press(stance={}, intents=[])

    def chat_drafts(self, state, player):
        return []

    @staticmethod
    def _nearest_owned_supply(state, player, start):
        m = state.map
        visited = {start}
        q = deque([start])
        while q:
            node = q.popleft()
            if node != start and m.is_supply(node) \
                    and state.ownership.get(node) == player:
                return node
            for nbr in sorted(m.neighbors(node)):
                if nbr not in visited:
                    visited.add(nbr)
                    q.append(nbr)
        return None

    @staticmethod
    def _step_toward(state, from_node, to_node):
        m = state.map
        dist = {to_node: 0}
        q = deque([to_node])
        while q:
            node = q.popleft()
            for nbr in sorted(m.neighbors(node)):
                if nbr not in dist:
                    dist[nbr] = dist[node] + 1
                    q.append(nbr)
        best = None
        best_d = float("inf")
        for nbr in sorted(m.neighbors(from_node)):
            d = dist.get(nbr, float("inf"))
            if d < best_d:
                best_d = d
                best = nbr
        return best
```

- [ ] **Step 3: Create `foedus/agents/heuristics/conservative_builder.py`**

Strategy spec: only captures supplies adjacent to ALREADY-owned territory; never ventures further.

```python
"""ConservativeBuilder — captures only supplies adjacent to owned territory.

Strategy:
  for each owned unit u:
    if u is at a supply NOT owned by player AND that supply is adjacent
       to at least one OTHER node owned by player:
      Hold (will flip via rule (b))
    elif u is at an owned supply AND has an adjacent unowned supply
         that's also adjacent to OTHER owned territory:
      Move to that adjacent unowned supply
    elif u is at an owned supply:
      Hold (defend)
    else:
      Move one step back toward an owned supply (retreat)

Press: NEUTRAL toward all.
"""

from __future__ import annotations

from collections import deque

from foedus.core import ChatDraft, GameState, Hold, Move, Order, PlayerId, Press, UnitId


class ConservativeBuilder:
    def __init__(self) -> None:
        pass

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        orders: dict[UnitId, Order] = {}
        # Build a set of all nodes adjacent to player's owned territory
        # (territory = any owned supply or plain).
        owned_nodes = {n for n, o in state.ownership.items() if o == player}
        adj_to_owned = set()
        for n in owned_nodes:
            for nbr in state.map.neighbors(n):
                adj_to_owned.add(nbr)
        for unit in state.units.values():
            if unit.owner != player:
                continue
            orders[unit.id] = self._choose_for_unit(
                state, player, unit, owned_nodes, adj_to_owned
            )
        return orders

    def _choose_for_unit(self, state, player, unit, owned_nodes, adj_to_owned):
        m = state.map
        loc = unit.location
        # If at unowned supply that touches owned territory: Hold to flip.
        if m.is_supply(loc) and state.ownership.get(loc) != player \
                and any(nbr in owned_nodes for nbr in m.neighbors(loc)):
            return Hold()
        # If at owned supply: look for an adjacent unowned supply that
        # ALSO touches owned territory; move there to start a flip.
        if m.is_supply(loc) and state.ownership.get(loc) == player:
            for nbr in sorted(m.neighbors(loc)):
                if (m.is_supply(nbr)
                        and state.ownership.get(nbr) != player
                        and any(n in owned_nodes - {loc}
                                for n in m.neighbors(nbr))):
                    occupant = state.unit_at(nbr)
                    if occupant is None or occupant.owner != player:
                        return Move(dest=nbr)
            return Hold()
        # Otherwise retreat toward owned territory.
        if owned_nodes:
            for nbr in sorted(m.neighbors(loc)):
                if nbr in owned_nodes:
                    return Move(dest=nbr)
        return Hold()

    def choose_press(self, state, player):
        return Press(stance={}, intents=[])

    def chat_drafts(self, state, player):
        return []
```

- [ ] **Step 4: Update `foedus/agents/heuristics/__init__.py`**

Replace contents with the full version (includes 3 new classes):

```python
"""Heuristic agents for foedus.

[same docstring as Task 1 step 1]
"""

from __future__ import annotations

from foedus.agents.heuristics.conservative_builder import ConservativeBuilder
from foedus.agents.heuristics.defensive import Defensive
from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.agents.heuristics.random_agent import RandomAgent

__all__ = [
    "ConservativeBuilder",
    "Defensive",
    "Greedy",
    "GreedyHold",
    "RandomAgent",
]

ROSTER = {
    "Random": RandomAgent,
    "Greedy": Greedy,
    "GreedyHold": GreedyHold,
    "Defensive": Defensive,
    "ConservativeBuilder": ConservativeBuilder,
}
```

- [ ] **Step 5: Create `tests/test_heuristics.py`**

This file will be extended in subsequent tasks. Start with shared fixtures + tests for Random, Greedy, GreedyHold, Defensive, ConservativeBuilder.

```python
"""Bundle 7 — unit tests for the heuristic roster.

Each heuristic gets verified against a small synthetic state. We check:
- choose_orders returns one Order per owned unit
- All orders are LEGAL (in legal_orders_for_unit's list)
- choose_press returns a Press
- chat_drafts returns a list

Plus heuristic-specific spec checks (e.g. Defensive never moves away from
owned supplies; GreedyHold holds when on unowned supply).
"""

from __future__ import annotations

import pytest

from foedus.agents.heuristics import (
    ConservativeBuilder,
    Defensive,
    Greedy,
    GreedyHold,
    RandomAgent,
)
from foedus.core import GameConfig, Hold, Move, Press, Unit
from foedus.legal import legal_orders_for_unit
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


@pytest.fixture
def state_4p():
    """4-player CONTINENTAL_SWEEP state at turn 0."""
    cfg = GameConfig(num_players=4, max_turns=15, seed=42)
    m = generate_map(4, seed=42)
    return initial_state(cfg, m)


def _all_orders_legal(agent_cls, state, player):
    agent = agent_cls() if agent_cls is not RandomAgent else agent_cls(seed=1)
    orders = agent.choose_orders(state, player)
    owned = [u for u in state.units.values() if u.owner == player]
    assert set(orders.keys()) == {u.id for u in owned}, \
        f"expected one order per owned unit"
    for uid, order in orders.items():
        legal = legal_orders_for_unit(state, uid)
        assert order in legal, \
            f"{agent_cls.__name__} produced illegal order {order} for u{uid}"


# ------- Random + Greedy (existing, regression) -------

def test_random_orders_all_legal(state_4p):
    _all_orders_legal(RandomAgent, state_4p, 0)


def test_greedy_orders_all_legal(state_4p):
    _all_orders_legal(Greedy, state_4p, 0)


def test_greedy_press_returns_press(state_4p):
    p = Greedy().choose_press(state_4p, 0)
    assert isinstance(p, Press)


# ------- GreedyHold -------

def test_greedy_hold_orders_all_legal(state_4p):
    _all_orders_legal(GreedyHold, state_4p, 0)


def test_greedy_hold_holds_on_unowned_supply(state_4p):
    """If a player's unit is on a supply they don't yet own, GreedyHold
    must Hold (to flip via rule b), not Move away."""
    # Place P0's u0 manually onto an unowned supply (using mutation since
    # GameState is mutable for this kind of test setup). Find an unowned
    # supply node.
    from foedus.core import NodeType
    unowned_supplies = [
        n for n, t in state_4p.map.node_types.items()
        if t in (NodeType.SUPPLY, NodeType.HOME)
        and state_4p.ownership.get(n) is None
    ]
    assert unowned_supplies, "test fixture has no unowned supplies"
    target = unowned_supplies[0]
    # Move u0 to target via direct mutation.
    u0 = state_4p.units[0]
    new_unit = Unit(id=u0.id, owner=u0.owner, location=target)
    state_4p.units[0] = new_unit
    orders = GreedyHold().choose_orders(state_4p, 0)
    assert orders[0] == Hold(), \
        f"GreedyHold should Hold on unowned supply, got {orders[0]}"


# ------- Defensive -------

def test_defensive_orders_all_legal(state_4p):
    _all_orders_legal(Defensive, state_4p, 0)


def test_defensive_holds_when_on_supply(state_4p):
    """Defensive on home (a supply) holds — never advances."""
    orders = Defensive().choose_orders(state_4p, 0)
    u0 = state_4p.units[0]
    assert orders[0] == Hold(), \
        f"Defensive should Hold on home, got {orders[0]}"


# ------- ConservativeBuilder -------

def test_conservative_builder_orders_all_legal(state_4p):
    _all_orders_legal(ConservativeBuilder, state_4p, 0)


def test_conservative_builder_holds_on_initial_state(state_4p):
    """At turn 0 each player only has 1 unit at home with adjacent
    supplies. ConservativeBuilder might Move OR Hold — either is
    acceptable. The strict invariant is that it never Moves away from
    owned territory by more than one hop."""
    orders = ConservativeBuilder().choose_orders(state_4p, 0)
    u0 = state_4p.units[0]
    order = orders[0]
    # Either Hold or Move to an adjacent node.
    assert isinstance(order, (Hold, Move))
    if isinstance(order, Move):
        assert order.dest in state_4p.map.neighbors(u0.location), \
            f"ConservativeBuilder moved to non-adjacent node {order.dest}"
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/test_heuristics.py -v`

Expected: all tests pass (~9 tests in this task; subsequent tasks add more).

- [ ] **Step 7: Run full suite**

Run: `python3 -m pytest -q`

Expected: 373 baseline + 9 new = 382 passed, 1 skipped.

- [ ] **Step 8: Commit**

```bash
git add foedus/agents/heuristics/ tests/test_heuristics.py
git commit -m "$(cat <<'EOF'
Bundle 7: 3 honest heuristics — GreedyHold, Defensive, ConservativeBuilder

- GreedyHold: like Greedy but Holds on unowned supplies (Bundle-2-aware
  capture pattern).
- Defensive: never advances; holds owned supplies. Lower-bound strategy.
- ConservativeBuilder: only captures supplies adjacent to owned
  territory. Slower than Greedy but resilient.

ROSTER registry now has 5 entries. tests/test_heuristics.py adds 9 unit
tests covering legal-order generation + each heuristic's strategy
invariant.

Spec: docs/superpowers/specs/2026-04-29-sim-sweep-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 3 complex new heuristics (Aggressive, AntiLeader, Bandwagon) + tests

**Files:**
- Create: `foedus/agents/heuristics/aggressive.py`
- Create: `foedus/agents/heuristics/anti_leader.py`
- Create: `foedus/agents/heuristics/bandwagon.py`
- Modify: `foedus/agents/heuristics/__init__.py` (add the 3 new classes)
- Modify: `tests/test_heuristics.py` (add tests for the 3 new heuristics)

These three are more complex than Task 2's. The spec for each:

- **Aggressive**: prioritize dislodging enemy units on supplies. Use SupportMove when an ally would help; else solo Move.
- **AntiLeader**: target the opponent with highest supply count. Pivot target each turn.
- **Bandwagon**: ALLY everyone in stance. For orders, mirror the leader's last-round order pattern (e.g., if the leader expanded, expand; if the leader held, hold). Without prior-turn data, fall back to GreedyHold.

- [ ] **Step 1: Create `foedus/agents/heuristics/aggressive.py`**

```python
"""Aggressive — prioritize dislodging enemy units on supplies.

Strategy:
  for each owned unit u:
    Find adjacent enemy units sitting on supplies (i.e. dislodge targets).
    If at least one found:
      Pick the highest-value target (supply > plain).
      If another own unit is also adjacent to the target node, that
        unit issues SupportMove; this unit Moves.
      Else solo Move.
    Else: walk toward nearest unowned supply (Greedy fallback).

Press: HOSTILE toward all opponents (we're attacking everyone).
"""

from __future__ import annotations

from collections import deque

from foedus.core import (
    ChatDraft, GameState, Hold, Move, NodeId, Order, PlayerId, Press,
    Stance, SupportMove, UnitId,
)


class Aggressive:
    def __init__(self) -> None:
        pass

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        my_units = [u for u in state.units.values() if u.owner == player]
        orders: dict[UnitId, Order] = {}
        # First pass: find dislodge targets and assign attacker + supporter.
        # A "dislodge target" is an enemy unit on a supply that's adjacent
        # to at least one of our units.
        m = state.map
        used_supporters: set[UnitId] = set()
        for u in my_units:
            adj = m.neighbors(u.location)
            for nbr in sorted(adj):
                # Look for enemy on supply at nbr.
                target_unit = state.unit_at(nbr)
                if (target_unit is None
                        or target_unit.owner == player
                        or not m.is_supply(nbr)):
                    continue
                # Found an enemy on a supply, adjacent to u. Try to find
                # a supporter from my_units.
                supporter = next(
                    (s for s in my_units
                     if s.id != u.id
                     and s.id not in used_supporters
                     and s.id not in orders
                     and m.is_adjacent(s.location, nbr)),
                    None,
                )
                if supporter is not None:
                    orders[u.id] = Move(dest=nbr)
                    orders[supporter.id] = SupportMove(
                        target=u.id, target_dest=nbr,
                    )
                    used_supporters.add(supporter.id)
                else:
                    orders[u.id] = Move(dest=nbr)
                break
        # Second pass: any remaining unit walks Greedy.
        for u in my_units:
            if u.id in orders:
                continue
            orders[u.id] = self._greedy_step(state, player, u)
        return orders

    def _greedy_step(self, state, player, unit):
        m = state.map
        target = self._nearest_unowned_supply(state, player, unit.location)
        if target is None:
            return Hold()
        if m.is_adjacent(unit.location, target):
            occupant = state.unit_at(target)
            if occupant is None or occupant.owner != player:
                return Move(dest=target)
            return Hold()
        next_step = self._step_toward(state, unit.location, target)
        if next_step is None:
            return Hold()
        occupant = state.unit_at(next_step)
        if occupant is None or occupant.owner != player:
            return Move(dest=next_step)
        return Hold()

    def choose_press(self, state, player):
        opponents = {
            p: Stance.HOSTILE
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        return Press(stance=opponents, intents=[])

    def chat_drafts(self, state, player):
        return []

    # BFS helpers (same as Greedy).
    @staticmethod
    def _nearest_unowned_supply(state, player, start):
        m = state.map
        visited = {start}
        q = deque([start])
        while q:
            node = q.popleft()
            if node != start and m.is_supply(node) \
                    and state.ownership.get(node) != player:
                return node
            for nbr in sorted(m.neighbors(node)):
                if nbr not in visited:
                    visited.add(nbr)
                    q.append(nbr)
        return None

    @staticmethod
    def _step_toward(state, from_node, to_node):
        m = state.map
        dist = {to_node: 0}
        q = deque([to_node])
        while q:
            node = q.popleft()
            for nbr in sorted(m.neighbors(node)):
                if nbr not in dist:
                    dist[nbr] = dist[node] + 1
                    q.append(nbr)
        best = None
        best_d = float("inf")
        for nbr in sorted(m.neighbors(from_node)):
            d = dist.get(nbr, float("inf"))
            if d < best_d:
                best_d = d
                best = nbr
        return best
```

- [ ] **Step 2: Create `foedus/agents/heuristics/anti_leader.py`**

```python
"""AntiLeader — targets opponent with highest supply count.

Strategy:
  Identify leader = opponent with most supplies (tie -> lowest pid).
  For each owned unit u:
    If adjacent to leader's territory: Move into it.
    Else: walk one step toward leader's nearest owned supply.

Press: HOSTILE toward leader, NEUTRAL toward others.
"""

from __future__ import annotations

from collections import deque

from foedus.core import (
    ChatDraft, GameState, Hold, Move, NodeId, Order, PlayerId, Press,
    Stance, UnitId,
)


class AntiLeader:
    def __init__(self) -> None:
        pass

    def _find_leader(self, state, player):
        opponents = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        if not opponents:
            return None
        return max(opponents,
                   key=lambda p: (state.supply_count(p), -p))

    def choose_orders(self, state, player):
        leader = self._find_leader(state, player)
        orders: dict[UnitId, Order] = {}
        if leader is None:
            for u in state.units.values():
                if u.owner == player:
                    orders[u.id] = Hold()
            return orders
        # Find leader's owned supply nodes.
        leader_supplies = [
            n for n, o in state.ownership.items() if o == leader
            and state.map.is_supply(n)
        ]
        for unit in state.units.values():
            if unit.owner != player:
                continue
            orders[unit.id] = self._step_toward_leader(
                state, player, unit, leader_supplies
            )
        return orders

    def _step_toward_leader(self, state, player, unit, leader_supplies):
        m = state.map
        # Adjacent to leader territory → Move in.
        for nbr in sorted(m.neighbors(unit.location)):
            if nbr in leader_supplies:
                occupant = state.unit_at(nbr)
                if occupant is None or occupant.owner != player:
                    return Move(dest=nbr)
        # Else walk toward nearest leader supply.
        if not leader_supplies:
            return Hold()
        target = min(
            leader_supplies,
            key=lambda n: self._dist(state, unit.location, n),
        )
        next_step = self._step_toward(state, unit.location, target)
        if next_step is None:
            return Hold()
        occupant = state.unit_at(next_step)
        if occupant is None or occupant.owner != player:
            return Move(dest=next_step)
        return Hold()

    @staticmethod
    def _dist(state, a, b):
        m = state.map
        if a == b:
            return 0
        seen = {a}
        q = deque([(a, 0)])
        while q:
            node, d = q.popleft()
            for nbr in m.neighbors(node):
                if nbr == b:
                    return d + 1
                if nbr not in seen:
                    seen.add(nbr)
                    q.append((nbr, d + 1))
        return float("inf")

    @staticmethod
    def _step_toward(state, from_node, to_node):
        m = state.map
        dist = {to_node: 0}
        q = deque([to_node])
        while q:
            node = q.popleft()
            for nbr in sorted(m.neighbors(node)):
                if nbr not in dist:
                    dist[nbr] = dist[node] + 1
                    q.append(nbr)
        best = None
        best_d = float("inf")
        for nbr in sorted(m.neighbors(from_node)):
            d = dist.get(nbr, float("inf"))
            if d < best_d:
                best_d = d
                best = nbr
        return best

    def choose_press(self, state, player):
        leader = self._find_leader(state, player)
        if leader is None:
            return Press(stance={}, intents=[])
        return Press(stance={leader: Stance.HOSTILE}, intents=[])

    def chat_drafts(self, state, player):
        return []
```

- [ ] **Step 3: Create `foedus/agents/heuristics/bandwagon.py`**

```python
"""Bandwagon — ALLY everyone, mirror the leader's behavior.

Strategy:
  Identify leader = opponent with most supplies.
  Press: ALLY toward all active opponents.
  Orders: fall back to GreedyHold (mirror "expansion" since most leaders
    expand). The "mirror leader's last-round order pattern" idea is hard
    to implement without engine-side per-turn order log; GreedyHold is
    a reasonable proxy for "do what successful expanders do".
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    ChatDraft, GameState, Order, PlayerId, Press, Stance, UnitId,
)


class Bandwagon:
    def __init__(self) -> None:
        self._inner = GreedyHold()

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        return self._inner.choose_orders(state, player)

    def choose_press(self, state, player):
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        return Press(stance=opponents, intents=[])

    def chat_drafts(self, state, player):
        return []
```

- [ ] **Step 4: Update `foedus/agents/heuristics/__init__.py`**

Extend imports + ROSTER:

```python
from foedus.agents.heuristics.aggressive import Aggressive
from foedus.agents.heuristics.anti_leader import AntiLeader
from foedus.agents.heuristics.bandwagon import Bandwagon
from foedus.agents.heuristics.conservative_builder import ConservativeBuilder
from foedus.agents.heuristics.defensive import Defensive
from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.agents.heuristics.random_agent import RandomAgent

__all__ = [
    "Aggressive", "AntiLeader", "Bandwagon", "ConservativeBuilder",
    "Defensive", "Greedy", "GreedyHold", "RandomAgent",
]

ROSTER = {
    "Random": RandomAgent,
    "Greedy": Greedy,
    "GreedyHold": GreedyHold,
    "Defensive": Defensive,
    "Aggressive": Aggressive,
    "AntiLeader": AntiLeader,
    "Bandwagon": Bandwagon,
    "ConservativeBuilder": ConservativeBuilder,
}
```

- [ ] **Step 5: Add tests to `tests/test_heuristics.py`**

Append:

```python
from foedus.agents.heuristics import Aggressive, AntiLeader, Bandwagon
from foedus.core import Stance


def test_aggressive_orders_all_legal(state_4p):
    _all_orders_legal(Aggressive, state_4p, 0)


def test_aggressive_press_is_hostile(state_4p):
    p = Aggressive().choose_press(state_4p, 0)
    assert all(s == Stance.HOSTILE for s in p.stance.values()), \
        f"Aggressive should declare HOSTILE toward all opponents"


def test_anti_leader_orders_all_legal(state_4p):
    _all_orders_legal(AntiLeader, state_4p, 0)


def test_anti_leader_press_targets_leader(state_4p):
    """At turn 0 all players have equal supplies; AntiLeader picks the
    lowest-pid opponent (tie-break)."""
    p = AntiLeader().choose_press(state_4p, 0)
    # Should declare HOSTILE toward exactly one opponent.
    assert sum(1 for s in p.stance.values() if s == Stance.HOSTILE) == 1


def test_bandwagon_orders_all_legal(state_4p):
    _all_orders_legal(Bandwagon, state_4p, 0)


def test_bandwagon_press_allies_everyone(state_4p):
    p = Bandwagon().choose_press(state_4p, 0)
    assert all(s == Stance.ALLY for s in p.stance.values())
    # Should have 3 entries (3 opponents in 4-player game).
    assert len(p.stance) == 3
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/test_heuristics.py -v`

Expected: all tests pass (15 total now).

- [ ] **Step 7: Run full suite**

Run: `python3 -m pytest -q`

Expected: 388 passed, 1 skipped.

- [ ] **Step 8: Commit**

```bash
git add foedus/agents/heuristics/ tests/test_heuristics.py
git commit -m "$(cat <<'EOF'
Bundle 7: 3 honest heuristics — Aggressive, AntiLeader, Bandwagon

- Aggressive: dislodges enemy units on supplies; uses SupportMove when
  ally-units would help.  HOSTILE toward all.
- AntiLeader: targets opponent with most supplies, pivots each turn.
- Bandwagon: ALLY toward all opponents in stance; orders inherit from
  GreedyHold (reasonable proxy for "do what successful expanders do").

ROSTER now has 8 entries.  6 new tests cover orders-are-legal and
press-stance invariants per heuristic.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 3 betrayer heuristics (Sycophant, OpportunisticBetrayer, TitForTat) + tests

**Files:**
- Create: `foedus/agents/heuristics/sycophant.py`
- Create: `foedus/agents/heuristics/opportunistic_betrayer.py`
- Create: `foedus/agents/heuristics/tit_for_tat.py`
- Modify: `foedus/agents/heuristics/__init__.py`
- Modify: `tests/test_heuristics.py`

The 3 betrayers test press teeth.

- [ ] **Step 1: Create `foedus/agents/heuristics/sycophant.py`**

```python
"""Sycophant — declares ALLY in stance + chat, plays Greedy.

Pure deception. No Intent declaration (so no BetrayalObservation fires
since they never committed to anything specific). Tests whether stance
+ chat alone create real strategic constraint.

Press: ALLY toward all opponents in stance.
Chat: public broadcast saying "let's cooperate".
Orders: identical to Greedy (no holds, walks forward).
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy import Greedy
from foedus.core import (
    ChatDraft, GameState, Order, PlayerId, Press, Stance, UnitId,
)


class Sycophant:
    def __init__(self) -> None:
        self._inner = Greedy()

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        return self._inner.choose_orders(state, player)

    def choose_press(self, state, player):
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        return Press(stance=opponents, intents=[])

    def chat_drafts(self, state, player):
        return [ChatDraft(
            recipients=None,
            body="Let's all cooperate. I'm declaring ALLY toward everyone.",
        )]
```

- [ ] **Step 2: Create `foedus/agents/heuristics/opportunistic_betrayer.py`**

```python
"""OpportunisticBetrayer — declares Intent, breaks it when target is exposed.

Strategy:
  Compute Greedy's plan (greedy_orders).
  Press: ALLY toward all + declare a public Intent for each unit
    matching greedy_orders (commits publicly).
  Orders: by default match the declared intent. BUT if any opponent's
    supply is "exposed" (held by lone unit, no nearby allied defenders),
    pivot one of our units to attack instead — breaks our own Intent
    → triggers BetrayalObservation.

For the simple version: always declare Intent matching Greedy plan.
On orders: if there's an enemy unit on a supply adjacent to one of
our units (any opponent), break Intent and Move to attack.

Press: ALLY toward all + Intents.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy import Greedy
from foedus.core import (
    ChatDraft, GameState, Hold, Intent, Move, Order, PlayerId, Press,
    Stance, UnitId,
)


class OpportunisticBetrayer:
    def __init__(self) -> None:
        self._inner = Greedy()

    def _planned_orders(self, state, player):
        return self._inner.choose_orders(state, player)

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        planned = self._planned_orders(state, player)
        # Look for an opponent unit on a supply, adjacent to one of our units.
        m = state.map
        for u in state.units.values():
            if u.owner != player:
                continue
            for nbr in sorted(m.neighbors(u.location)):
                target = state.unit_at(nbr)
                if (target is None
                        or target.owner == player
                        or not m.is_supply(nbr)):
                    continue
                # Found exposed enemy on supply. Break the planned Intent
                # for u and attack instead.
                planned[u.id] = Move(dest=nbr)
                return planned  # Just one betrayal per turn
        return planned

    def choose_press(self, state, player):
        opponents = {
            p: Stance.ALLY
            for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        }
        # Declare Intents matching the planned (pre-betrayal) orders.
        planned = self._planned_orders(state, player)
        intents = [
            Intent(unit_id=uid, declared_order=order, visible_to=None)
            for uid, order in planned.items()
        ]
        return Press(stance=opponents, intents=intents)

    def chat_drafts(self, state, player):
        return []
```

- [ ] **Step 3: Create `foedus/agents/heuristics/tit_for_tat.py`**

```python
"""TitForTat — ALLY by default, HOSTILE-once-betrayed.

Maintains an in-process hostile_set (instance variable, not in
GameState — meaning each new game starts fresh). At the start of each
choose_press / choose_orders call, scans state.betrayals[player] for
NEW betrayers and adds them to hostile_set. Once HOSTILE, stays HOSTILE
for the rest of the game.

Press: ALLY toward not-hostile opponents; HOSTILE toward hostile_set.
Orders: prioritize attacking units owned by hostile players; else
GreedyHold fallback.
"""

from __future__ import annotations

from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
    ChatDraft, GameState, Move, Order, PlayerId, Press, Stance, UnitId,
)


class TitForTat:
    def __init__(self) -> None:
        self.hostile_set: set[PlayerId] = set()
        self._inner = GreedyHold()

    def _update_hostile_set(self, state, player):
        for b in state.betrayals.get(player, []):
            self.hostile_set.add(b.betrayer)

    def choose_orders(self, state: GameState,
                      player: PlayerId) -> dict[UnitId, Order]:
        self._update_hostile_set(state, player)
        # Look for hostile player units adjacent to ours; attack.
        m = state.map
        orders: dict[UnitId, Order] = {}
        for u in state.units.values():
            if u.owner != player:
                continue
            attacked = False
            for nbr in sorted(m.neighbors(u.location)):
                target = state.unit_at(nbr)
                if (target is not None
                        and target.owner in self.hostile_set):
                    orders[u.id] = Move(dest=nbr)
                    attacked = True
                    break
            if not attacked:
                # Fallback to GreedyHold for this unit.
                fallback = self._inner.choose_orders(state, player)
                orders[u.id] = fallback.get(u.id)
        return orders

    def choose_press(self, state, player):
        self._update_hostile_set(state, player)
        opponents = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        stance = {}
        for p in opponents:
            stance[p] = (Stance.HOSTILE if p in self.hostile_set
                         else Stance.ALLY)
        return Press(stance=stance, intents=[])

    def chat_drafts(self, state, player):
        return []
```

- [ ] **Step 4: Update `foedus/agents/heuristics/__init__.py`**

Add the 3 betrayers to imports and ROSTER. Final version:

```python
"""Heuristic agents for foedus."""

from __future__ import annotations

from foedus.agents.heuristics.aggressive import Aggressive
from foedus.agents.heuristics.anti_leader import AntiLeader
from foedus.agents.heuristics.bandwagon import Bandwagon
from foedus.agents.heuristics.conservative_builder import ConservativeBuilder
from foedus.agents.heuristics.defensive import Defensive
from foedus.agents.heuristics.greedy import Greedy
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.agents.heuristics.opportunistic_betrayer import OpportunisticBetrayer
from foedus.agents.heuristics.random_agent import RandomAgent
from foedus.agents.heuristics.sycophant import Sycophant
from foedus.agents.heuristics.tit_for_tat import TitForTat

__all__ = [
    "Aggressive", "AntiLeader", "Bandwagon", "ConservativeBuilder",
    "Defensive", "Greedy", "GreedyHold", "OpportunisticBetrayer",
    "RandomAgent", "Sycophant", "TitForTat",
]

ROSTER = {
    "Random": RandomAgent,
    "Greedy": Greedy,
    "GreedyHold": GreedyHold,
    "Defensive": Defensive,
    "Aggressive": Aggressive,
    "AntiLeader": AntiLeader,
    "Bandwagon": Bandwagon,
    "ConservativeBuilder": ConservativeBuilder,
    "Sycophant": Sycophant,
    "OpportunisticBetrayer": OpportunisticBetrayer,
    "TitForTat": TitForTat,
}
```

- [ ] **Step 5: Add betrayer tests to `tests/test_heuristics.py`**

```python
from foedus.agents.heuristics import (
    OpportunisticBetrayer, Sycophant, TitForTat,
)


def test_sycophant_orders_all_legal(state_4p):
    _all_orders_legal(Sycophant, state_4p, 0)


def test_sycophant_press_allies_everyone(state_4p):
    p = Sycophant().choose_press(state_4p, 0)
    assert all(s == Stance.ALLY for s in p.stance.values())


def test_sycophant_chat_includes_cooperation_pitch(state_4p):
    drafts = Sycophant().chat_drafts(state_4p, 0)
    assert len(drafts) == 1
    assert "ally" in drafts[0].body.lower() or \
           "cooperate" in drafts[0].body.lower()


def test_opportunistic_betrayer_orders_all_legal(state_4p):
    _all_orders_legal(OpportunisticBetrayer, state_4p, 0)


def test_opportunistic_betrayer_press_includes_intents(state_4p):
    p = OpportunisticBetrayer().choose_press(state_4p, 0)
    assert len(p.intents) >= 1, "should declare at least one Intent"


def test_tit_for_tat_orders_all_legal(state_4p):
    _all_orders_legal(TitForTat, state_4p, 0)


def test_tit_for_tat_starts_ally_toward_all(state_4p):
    """No prior betrayals → all ally."""
    p = TitForTat().choose_press(state_4p, 0)
    assert all(s == Stance.ALLY for s in p.stance.values())


def test_tit_for_tat_retaliates_against_betrayer(state_4p):
    """If state.betrayals[player] has an entry, that betrayer becomes
    HOSTILE."""
    from foedus.core import BetrayalObservation, Hold, Intent
    agent = TitForTat()
    # Inject a fake betrayal: P1 betrayed P0.
    fake_intent = Intent(unit_id=2, declared_order=Hold(),
                         visible_to=None)
    obs = BetrayalObservation(
        turn=0, betrayer=1, intent=fake_intent,
        actual_order=Hold(),
    )
    state_4p.betrayals[0] = [obs]
    p = agent.choose_press(state_4p, 0)
    assert p.stance.get(1) == Stance.HOSTILE
    assert p.stance.get(2) == Stance.ALLY  # Other opponents unchanged
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/test_heuristics.py -v`

Expected: 22 tests pass.

- [ ] **Step 7: Run full suite**

Run: `python3 -m pytest -q`

Expected: 395 passed, 1 skipped.

- [ ] **Step 8: Commit**

```bash
git add foedus/agents/heuristics/ tests/test_heuristics.py
git commit -m "$(cat <<'EOF'
Bundle 7: 3 betrayer heuristics — Sycophant, OpportunisticBetrayer, TitForTat

Test press teeth: do declared stances + Intents create real strategic
constraint?

- Sycophant: ALLY in stance + public chat saying cooperate, but plays
  Greedy under the hood. Pure deception via lying-stance only (no
  Intent declarations → no BetrayalObservations fire).
- OpportunisticBetrayer: declares ALLY + public Intent matching
  Greedy plan. Breaks the Intent (and triggers BetrayalObservation)
  whenever an enemy unit is found exposed on a supply adjacent to ours.
- TitForTat: ALLY by default; tracks hostile_set in-process, adds
  any opponent appearing in state.betrayals[me]; HOSTILE-and-attacks
  thereafter.  Once HOSTILE, stays HOSTILE for the rest of the game.

ROSTER complete at 11 heuristics.  7 new tests cover betrayer-specific
invariants (stance is ally for honest start, intents declared,
TitForTat retaliation upon observed betrayal).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Sweep harness + integration test

**Files:**
- Create: `scripts/foedus_sim_sweep.py`
- Create: `tests/test_sim_sweep.py`

The sweep harness runs N games with random pairings and emits JSONL.

- [ ] **Step 1: Create `scripts/foedus_sim_sweep.py`**

```python
"""Bulk simulation harness — runs N foedus games with random heuristic
pairings and emits one JSONL line per game.

Usage:
    PYTHONPATH=. python3 scripts/foedus_sim_sweep.py \
        --num-games 5000 --max-turns 15

Spec: docs/superpowers/specs/2026-04-29-sim-sweep-design.md
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

from foedus.agents.heuristics import ROSTER
from foedus.core import (
    Archetype, GameConfig, Hold, Move, Press, SupportHold, SupportMove,
)
from foedus.mapgen import generate_map
from foedus.press import (
    finalize_round, signal_chat_done, signal_done, submit_press_tokens,
)
from foedus.resolve import initial_state


ORDER_TYPE_NAMES = {
    Hold: "Hold", Move: "Move",
    SupportHold: "SupportHold", SupportMove: "SupportMove",
}


def _order_type_name(order):
    return ORDER_TYPE_NAMES.get(type(order), "Unknown")


def run_one_game(game_id: int, seed: int, agent_names: list[str],
                 max_turns: int, archetype: Archetype,
                 num_players: int) -> dict:
    """Run a single game, return the per-game JSONL record."""
    cfg = GameConfig(
        num_players=num_players, max_turns=max_turns, seed=seed,
        archetype=archetype, peace_threshold=99,
    )
    m = generate_map(num_players, seed=seed,
                     archetype=archetype, map_radius=cfg.map_radius)
    state = initial_state(cfg, m)
    agents = [ROSTER[name](
        seed=seed * 1000 + i if name == "Random" else None,
    ) if name == "Random" else ROSTER[name]()
        for i, name in enumerate(agent_names)]

    supply_per_turn: dict[int, list[int]] = {}
    score_per_turn: dict[int, list[float]] = {}
    order_counts: Counter = Counter()
    dislodgement_count = 0

    while not state.is_terminal():
        survivors = [
            p for p in range(num_players) if p not in state.eliminated
        ]
        # Press round.
        for p in survivors:
            press = agents[p].choose_press(state, p)
            state = submit_press_tokens(state, p, press)
            state = signal_chat_done(state, p)
            state = signal_done(state, p)
        # Collect orders.
        orders = {p: agents[p].choose_orders(state, p) for p in survivors}
        # Count order types.
        for p_orders in orders.values():
            for order in p_orders.values():
                order_counts[_order_type_name(order)] += 1
        # Finalize.
        prev_units = dict(state.units)
        state = finalize_round(state, orders)
        # Count dislodgements: units in prev_units NOT in new state.units.
        for uid in prev_units:
            if uid not in state.units:
                dislodgement_count += 1
        # Snapshot.
        supply_per_turn[state.turn] = [
            state.supply_count(p) for p in range(num_players)
        ]
        score_per_turn[state.turn] = [
            state.scores.get(p, 0.0) for p in range(num_players)
        ]

    return {
        "game_id": game_id,
        "seed": seed,
        "agents": agent_names,
        "max_turns_reached": max_turns,
        "total_turns": state.turn,
        "is_terminal": state.is_terminal(),
        "winners": state.winners(),
        "final_scores": [state.scores.get(p, 0.0)
                         for p in range(num_players)],
        "supply_counts_per_turn": {str(k): v for k, v in supply_per_turn.items()},
        "score_per_turn": {str(k): v for k, v in score_per_turn.items()},
        "order_type_counts": dict(order_counts),
        "dislodgement_count": dislodgement_count,
        "betrayal_count_per_player": [
            len(state.betrayals.get(p, []))
            for p in range(num_players)
        ],
        "detente_reached": state.detente_reached,
        "eliminated": sorted(state.eliminated),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-games", type=int, default=5000)
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--archetype", default="continental_sweep")
    parser.add_argument("--num-players", type=int, default=4)
    parser.add_argument("--roster", default="",
                        help="comma-separated heuristic names; default: all")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    archetype = Archetype(args.archetype)
    roster_names = (args.roster.split(",") if args.roster
                    else list(ROSTER.keys()))
    for n in roster_names:
        if n not in ROSTER:
            print(f"ERR: unknown heuristic {n!r}", file=sys.stderr)
            return 1

    out_path = Path(args.out) if args.out else \
        Path(f"/tmp/foedus_sim_sweep_{int(time.time())}.jsonl")
    rng = random.Random(args.seed_offset)

    t0 = time.time()
    with out_path.open("w") as f:
        for game_id in range(args.num_games):
            seed = args.seed_offset + game_id
            agent_names = [rng.choice(roster_names)
                           for _ in range(args.num_players)]
            record = run_one_game(
                game_id, seed, agent_names, args.max_turns,
                archetype, args.num_players,
            )
            f.write(json.dumps(record) + "\n")
            if (game_id + 1) % 100 == 0:
                elapsed = time.time() - t0
                rate = (game_id + 1) / elapsed
                print(f"[{game_id+1}/{args.num_games}] {elapsed:.1f}s "
                      f"({rate:.1f} games/s)", file=sys.stderr)
    elapsed = time.time() - t0
    print(f"Wrote {args.num_games} games to {out_path} in {elapsed:.1f}s",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create `tests/test_sim_sweep.py`**

```python
"""Bundle 7 — integration test for the simulation harness."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_sweep_runs_and_produces_jsonl(tmp_path: Path) -> None:
    """Run the harness with --num-games 10 --max-turns 4 and verify
    the JSONL output structure."""
    out_path = tmp_path / "out.jsonl"
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "foedus_sim_sweep.py"),
         "--num-games", "10",
         "--max-turns", "4",
         "--out", str(out_path)],
        env={"PYTHONPATH": str(repo_root)},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, \
        f"sweep exited {result.returncode}: stderr={result.stderr}"
    lines = out_path.read_text().strip().split("\n")
    assert len(lines) == 10
    for line in lines:
        record = json.loads(line)
        # Schema checks.
        for key in ("game_id", "seed", "agents", "total_turns",
                    "is_terminal", "winners", "final_scores",
                    "supply_counts_per_turn", "score_per_turn",
                    "order_type_counts", "dislodgement_count",
                    "betrayal_count_per_player", "detente_reached",
                    "eliminated"):
            assert key in record, f"missing key {key!r}"
        # Logical checks.
        assert len(record["agents"]) == 4
        assert len(record["final_scores"]) == 4
        assert all(s >= 0 for s in record["final_scores"])
        assert record["total_turns"] <= 4
        assert record["is_terminal"] is True
```

- [ ] **Step 3: Run targeted test**

Run: `python3 -m pytest tests/test_sim_sweep.py -v`

Expected: 1 passed in ~5-10 seconds (10 games × ~75 ms each plus subprocess overhead).

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest -q`

Expected: 396 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add scripts/foedus_sim_sweep.py tests/test_sim_sweep.py
git commit -m "$(cat <<'EOF'
Bundle 7: bulk simulation harness — scripts/foedus_sim_sweep.py

Runs N games with random heuristic pairings (with replacement) from
the ROSTER.  Per-game JSONL output captures final scores, per-turn
supply / score history, order-type counts, dislodgement count,
betrayal counts.  Default 5000 games × 15 turns × 4 players ≈ 6 min.

Integration test verifies 10-game sweep produces well-formed JSONL.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Analyzer + integration test + run baseline + write report

**Files:**
- Create: `scripts/foedus_sim_analyze.py`
- Create: `tests/test_sim_analyze.py`
- Create: `docs/research/2026-04-29-bundle-7-baseline.md`

- [ ] **Step 1: Create `scripts/foedus_sim_analyze.py`**

```python
"""Analyzer — reads JSONL sim sweep output, emits depth-metrics report.

Usage:
    PYTHONPATH=. python3 scripts/foedus_sim_analyze.py path/to/sweep.jsonl

Outputs a markdown report to stdout.

Spec: docs/superpowers/specs/2026-04-29-sim-sweep-design.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_records(paths: list[Path]) -> list[dict]:
    out = []
    for p in paths:
        with p.open() as f:
            for line in f:
                out.append(json.loads(line))
    return out


def per_heuristic_scores(records: list[dict]) -> dict[str, list[float]]:
    """Return {heuristic_name: [final_score for each game-instance]}."""
    out = defaultdict(list)
    for r in records:
        for player_idx, name in enumerate(r["agents"]):
            out[name].append(r["final_scores"][player_idx])
    return out


def per_pairing_winrate(records: list[dict]) -> dict[tuple[str, str], float]:
    """Return {(A, B): fraction of games where A scored higher than B}."""
    pair_counts: dict[tuple[str, str], list[int]] = defaultdict(
        lambda: [0, 0])  # [A_wins, total]
    for r in records:
        agents = r["agents"]
        scores = r["final_scores"]
        for i, name_i in enumerate(agents):
            for j, name_j in enumerate(agents):
                if i == j:
                    continue
                pair_counts[(name_i, name_j)][1] += 1
                if scores[i] > scores[j]:
                    pair_counts[(name_i, name_j)][0] += 1
    return {k: (v[0] / v[1] if v[1] > 0 else 0.0)
            for k, v in pair_counts.items()}


def lead_change_count(record: dict) -> int:
    """Count unique-leader changes across the game's score history."""
    score_per_turn = record["score_per_turn"]
    sorted_turns = sorted(int(k) for k in score_per_turn.keys())
    last_leader = None
    changes = 0
    for t in sorted_turns:
        scores = score_per_turn[str(t)]
        max_score = max(scores)
        leaders = [i for i, s in enumerate(scores) if s == max_score]
        leader = leaders[0] if len(leaders) == 1 else None
        if leader != last_leader:
            changes += 1
        last_leader = leader
    return changes


def order_type_distribution(records: list[dict]) -> dict[str, float]:
    total = Counter()
    for r in records:
        total.update(r["order_type_counts"])
    grand_total = sum(total.values())
    return {k: v / grand_total for k, v in total.items()} if grand_total else {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+",
                        help="One or more JSONL files from foedus_sim_sweep.py")
    args = parser.parse_args()
    paths = [Path(p) for p in args.paths]
    records = load_records(paths)
    n_games = len(records)
    print(f"# Bundle 7 — Sim Sweep Analysis\n")
    print(f"**Total games analyzed:** {n_games}\n")

    # Per-heuristic mean / median / stddev.
    print("## Per-heuristic final score (across all game-instances)\n")
    print("| Heuristic | n games | mean | median | stddev | min | max |")
    print("|---|---|---|---|---|---|---|")
    scores = per_heuristic_scores(records)
    for name in sorted(scores.keys()):
        s = scores[name]
        print(f"| {name} | {len(s)} | "
              f"{statistics.mean(s):.2f} | {statistics.median(s):.2f} | "
              f"{statistics.stdev(s):.2f} | "
              f"{min(s):.0f} | {max(s):.0f} |")
    print()

    # Pairing win-rate matrix.
    print("## Pairing win-rate matrix (row vs column)\n")
    print("Each cell: fraction of games where row-agent scored higher than column-agent (when they appeared together).\n")
    names = sorted(scores.keys())
    print("| | " + " | ".join(names) + " |")
    print("|---" + "|---" * len(names) + "|")
    winrate = per_pairing_winrate(records)
    for r in names:
        row = [f"**{r}**"]
        for c in names:
            if r == c:
                row.append("—")
            else:
                wr = winrate.get((r, c), 0.0)
                row.append(f"{wr:.2f}")
        print("| " + " | ".join(row) + " |")
    print()

    # Lead-change frequency.
    leads_per_game = [lead_change_count(r) for r in records]
    print(f"## Lead-change frequency\n")
    print(f"Mean lead changes per game: **{statistics.mean(leads_per_game):.2f}**\n")
    print(f"Median: {statistics.median(leads_per_game):.0f}, "
          f"max: {max(leads_per_game)}, "
          f"games with 0 changes: {sum(1 for x in leads_per_game if x == 0)}\n")

    # Order-type distribution.
    print(f"## Order-type distribution (across all games × all players × all turns)\n")
    od = order_type_distribution(records)
    for ot in ("Hold", "Move", "SupportHold", "SupportMove"):
        print(f"- **{ot}:** {od.get(ot, 0.0):.1%}")
    print()

    # Dislodgement rate.
    dislodge_per_game = [r["dislodgement_count"] for r in records]
    print(f"## Dislodgement rate\n")
    print(f"Mean dislodgements per game: **{statistics.mean(dislodge_per_game):.2f}**\n")
    print(f"Games with at least one dislodgement: "
          f"{sum(1 for x in dislodge_per_game if x > 0)} of {n_games}\n")

    # Betrayer success vs TitForTat.
    print(f"## Betrayer success vs TitForTat\n")
    print("When Betrayer X and TitForTat appear in the same game, "
          "average score difference (X − TitForTat):\n")
    for betrayer in ("Sycophant", "OpportunisticBetrayer"):
        diffs = []
        for r in records:
            ag = r["agents"]
            scores_ = r["final_scores"]
            if betrayer in ag and "TitForTat" in ag:
                b_idx = ag.index(betrayer)
                t_idx = ag.index("TitForTat")
                diffs.append(scores_[b_idx] - scores_[t_idx])
        if diffs:
            mean_diff = statistics.mean(diffs)
            sign = "+" if mean_diff > 0 else ""
            print(f"- **{betrayer}** vs TitForTat (n={len(diffs)}): "
                  f"{sign}{mean_diff:.2f} "
                  f"({'betrayer profits' if mean_diff > 0 else 'TitForTat punishes' if mean_diff < 0 else 'wash'})")
        else:
            print(f"- **{betrayer}**: no co-occurrence games found")
    print()

    # Score gap winner vs 2nd.
    gaps = []
    for r in records:
        scores_ = sorted(r["final_scores"], reverse=True)
        gaps.append(scores_[0] - scores_[1])
    print(f"## Winner vs 2nd-place score gap\n")
    print(f"Mean gap: {statistics.mean(gaps):.2f}, "
          f"median: {statistics.median(gaps):.0f}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create `tests/test_sim_analyze.py`**

```python
"""Bundle 7 — integration test for the analyzer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _make_jsonl(tmp_path: Path) -> Path:
    """Create a tiny synthetic JSONL with 5 games."""
    records = []
    for i in range(5):
        records.append({
            "game_id": i,
            "seed": i,
            "agents": ["Greedy", "GreedyHold", "Defensive", "Random"],
            "max_turns_reached": 7,
            "total_turns": 7,
            "is_terminal": True,
            "winners": [1],
            "final_scores": [10.0, 20.0, 5.0, 7.0],
            "supply_counts_per_turn": {
                str(t): [t, t+1, 1, 1] for t in range(1, 8)
            },
            "score_per_turn": {
                str(t): [t * 1.0, t * 2.0, 1.0, 1.0]
                for t in range(1, 8)
            },
            "order_type_counts": {
                "Hold": 10, "Move": 18, "SupportMove": 0, "SupportHold": 0,
            },
            "dislodgement_count": 0,
            "betrayal_count_per_player": [0, 0, 0, 0],
            "detente_reached": False,
            "eliminated": [],
        })
    out = tmp_path / "input.jsonl"
    with out.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return out


def test_analyzer_produces_markdown_report(tmp_path: Path) -> None:
    jsonl = _make_jsonl(tmp_path)
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "foedus_sim_analyze.py"),
         str(jsonl)],
        env={"PYTHONPATH": str(repo_root)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, \
        f"analyzer exited {result.returncode}: stderr={result.stderr}"
    out = result.stdout
    # Spot-check sections.
    assert "# Bundle 7 — Sim Sweep Analysis" in out
    assert "Total games analyzed: 5" in out
    assert "## Per-heuristic final score" in out
    assert "## Pairing win-rate matrix" in out
    assert "## Lead-change frequency" in out
    assert "## Order-type distribution" in out
    assert "## Dislodgement rate" in out
    assert "## Betrayer success vs TitForTat" in out
    # Greedy mean = 10, GreedyHold mean = 20.
    assert "Greedy" in out and "GreedyHold" in out
    # Order-type: roughly 10/(10+18) Hold = 35.7%
    assert "Move:" in out and "Hold:" in out
```

- [ ] **Step 3: Run targeted test**

Run: `python3 -m pytest tests/test_sim_analyze.py -v`

Expected: 1 passed.

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest -q`

Expected: 397 passed, 1 skipped.

- [ ] **Step 5: Run the baseline sweep**

```bash
PYTHONPATH=. python3 scripts/foedus_sim_sweep.py --num-games 5000 --max-turns 15 \
    --out /tmp/foedus_sim_baseline.jsonl
```

Expected: ~5-8 minutes runtime. Final stderr line: `Wrote 5000 games to /tmp/foedus_sim_baseline.jsonl in <X>s`.

- [ ] **Step 6: Generate the baseline report**

```bash
mkdir -p docs/research
PYTHONPATH=. python3 scripts/foedus_sim_analyze.py /tmp/foedus_sim_baseline.jsonl \
    > docs/research/2026-04-29-bundle-7-baseline.md
```

Open `docs/research/2026-04-29-bundle-7-baseline.md` and add a one-paragraph "Findings summary" at the top: state the headline observations from the table (which heuristic dominates, which betrayer profits more, are there any rock-paper-scissors cycles in the win-rate matrix, what fraction of orders are SupportMove). This is the human-written analysis layer atop the numbers.

- [ ] **Step 7: Commit**

```bash
git add scripts/foedus_sim_analyze.py tests/test_sim_analyze.py docs/research/2026-04-29-bundle-7-baseline.md
git commit -m "$(cat <<'EOF'
Bundle 7: analyzer + baseline run

scripts/foedus_sim_analyze.py reads sweep JSONL and emits a markdown
depth-metrics report: per-heuristic scores, pairing win-rate matrix,
lead-change frequency, order-type distribution, dislodgement rate,
betrayer-vs-TitForTat success, score gaps.

Baseline run: 5000 games × 15 turns × 4 players × roster of 11
heuristics with random pairings.  Output committed at
docs/research/2026-04-29-bundle-7-baseline.md.  This is the reference
data for evaluating future mechanic changes (Bundle 4 alliance
multipliers, etc.).

Integration test verifies analyzer output structure on a synthetic
5-game JSONL.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Push, open PR, dispatch Sonnet final reviewer

- [ ] **Step 1: Run full suite + smoke**

Run: `python3 -m pytest -q`
Expected: 397 passed, 1 skipped.

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin bundle7-sim-sweep
gh pr create --title "Bundle 7: Sim sweep harness + 11-heuristic roster" --body "$(cat <<'EOF'
## Summary

Builds a bulk simulation harness with 11 diverse heuristic agents (8
honest + 3 betrayer variants) so we can quantify game depth across
thousands of games. After this lands, every Bundle that changes a
mechanic gets evaluated against this baseline using the same sweep.

Spec: \`docs/superpowers/specs/2026-04-29-sim-sweep-design.md\`
Plan: \`docs/superpowers/plans/2026-04-29-sim-sweep-bundle-7.md\`
Baseline report: \`docs/research/2026-04-29-bundle-7-baseline.md\`

## What changes

| | What |
|---|---|
| **\`foedus/agents/heuristics/\` package** | New package; relocates RandomAgent + HeuristicAgent (renamed Greedy), plus 9 new variants |
| **9 new heuristics** | GreedyHold, Defensive, Aggressive, AntiLeader, Bandwagon, ConservativeBuilder, Sycophant, OpportunisticBetrayer, TitForTat |
| **Backward compat** | \`foedus.agents.heuristic.HeuristicAgent\` and \`foedus.agents.random_agent.RandomAgent\` still work via re-exports |
| **\`scripts/foedus_sim_sweep.py\`** | Runs N games with random pairings; emits one JSONL line per game with full per-turn snapshots and aggregate counts |
| **\`scripts/foedus_sim_analyze.py\`** | Computes 7 depth-indicator metrics from JSONL: per-heuristic scores, pairing win-rate matrix, lead changes, order-type distribution, dislodgement rate, betrayer-vs-TitForTat success, score gaps |
| **Baseline run** | 5000 games × 15 turns × 4 players, output committed at \`docs/research/2026-04-29-bundle-7-baseline.md\` |

## Test plan
- [x] \`pytest -q\` → 397 passed, 1 skipped (was 373 + 1 on main; +24 net new tests)
- [x] Sweep harness integration test runs 10-game sweep cleanly
- [x] Analyzer integration test produces well-formed markdown
- [x] Baseline run completed in < 10 min, committed

## Out of scope
- D fog-respecting legal-orders (Bundle 8)
- H threat-context (Bundle 8)
- Chat UX (Bundle 8)
- Bundle 4 alliance multipliers (separate bundle, will use this baseline)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Dispatch Sonnet final reviewer**

After PR is open, dispatch a `superpowers:code-reviewer` subagent with model `sonnet`. Pass:
- PR URL
- Branch base/head SHAs
- Spec + plan paths
- Summary: 11 heuristics + sweep harness + analyzer + baseline run
- Specific things to check: backward-compat (existing imports still work), agent Protocol conformance, JSONL schema completeness, analyzer numerical correctness (mean/stddev), reasonable handling of edge cases (single-survivor games, games that hit max_turns vs détente)

- [ ] **Step 4: Address review findings**

Standard fix-and-push loop until approved.

---

## Self-Review Checklist

**Spec coverage:**
- [x] All 11 heuristics → Tasks 1, 2, 3, 4
- [x] ROSTER registry → Task 1 (initial), Tasks 2-4 (extended)
- [x] Backward-compat re-exports → Task 1 Steps 4, 5
- [x] Sweep harness → Task 5
- [x] Analyzer with 7 metrics → Task 6 Step 1
- [x] Baseline run → Task 6 Step 5
- [x] Baseline report committed → Task 6 Steps 6, 7
- [x] Unit tests for each heuristic → Task 1 (Random/Greedy regression), Task 2 (3 simple), Task 3 (3 complex), Task 4 (3 betrayers)
- [x] Integration tests for sweep + analyzer → Tasks 5, 6
- [x] No engine changes (purely additive) → confirmed across all tasks

**Placeholder scan:** No "TBD" / "TODO" / vague items. All code blocks are complete; all test code is concrete; all commit messages are full.

**Type consistency:** `RandomAgent` / `Greedy` / `GreedyHold` / `Defensive` / `Aggressive` / `AntiLeader` / `Bandwagon` / `ConservativeBuilder` / `Sycophant` / `OpportunisticBetrayer` / `TitForTat` are the 11 class names used consistently across imports, tests, and ROSTER. `Press` / `Stance` / `Intent` / `ChatDraft` types match `foedus/core.py` definitions throughout.
