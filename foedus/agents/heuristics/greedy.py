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
from foedus.agents.heuristics._tiebreak import shuffled_neighbors
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
        # No state — pure function of GameState. Stateless agents are
        # easier to reason about and trivially serializable.
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
        """ALLY toward the active opponent whose supply count is closest
        to mine; NEUTRAL toward all others (omitted from the dict).
        Ties broken by lower player_id. No intents.

        Spec: docs/superpowers/specs/2026-04-28-press-driver-design.md
        """
        my_supply = state.supply_count(player)
        active_opponents = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        if not active_opponents:
            return Press(stance={}, intents=[])
        # min() with tuple key gives us closest-distance, then lower-pid.
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
        # If we're adjacent, move in directly (unless blocked by an own unit).
        if m.is_adjacent(unit.location, target):
            occupant = state.unit_at(target)
            if occupant is None or occupant.owner != player:
                return Move(dest=target)
            return Hold()

        # Otherwise step along a shortest path to the target.
        next_step = self._step_toward(state, player, unit.location, target)
        if next_step is None:
            return Hold()
        occupant = state.unit_at(next_step)
        if occupant is None or occupant.owner != player:
            return Move(dest=next_step)
        return Hold()

    @staticmethod
    def _nearest_unowned_supply(state: GameState, player: PlayerId,
                                start: NodeId) -> NodeId | None:
        """BFS from `start` to the closest supply node not owned by `player`.

        Returns the target NodeId, or None if no such node is reachable.
        Ties are broken deterministically by NodeId (sorted neighbor walk).
        """
        m = state.map
        visited: set[NodeId] = {start}
        q: deque[NodeId] = deque([start])
        while q:
            node = q.popleft()
            if node != start and m.is_supply(node) \
                    and state.ownership.get(node) != player:
                return node
            for nbr in shuffled_neighbors(state, player, node):
                if nbr not in visited:
                    visited.add(nbr)
                    q.append(nbr)
        return None

    @staticmethod
    def _step_toward(state: GameState, player: PlayerId, from_node: NodeId,
                     to_node: NodeId) -> NodeId | None:
        """Return a neighbor of `from_node` on a shortest path to `to_node`.

        Implementation: BFS from `to_node` outward; pick the neighbor of
        `from_node` with the smallest distance back. Deterministic (sorted
        node iteration breaks ties).
        """
        m = state.map
        dist: dict[NodeId, int] = {to_node: 0}
        q: deque[NodeId] = deque([to_node])
        while q:
            node = q.popleft()
            for nbr in shuffled_neighbors(state, player, node):
                if nbr not in dist:
                    dist[nbr] = dist[node] + 1
                    q.append(nbr)
        best: NodeId | None = None
        best_d = float("inf")
        for nbr in shuffled_neighbors(state, player, from_node):
            d = dist.get(nbr, float("inf"))
            if d < best_d:
                best_d = d
                best = nbr
        return best
