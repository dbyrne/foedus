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
        next_step = self._step_toward(state, player, unit.location, target)
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
            for nbr in shuffled_neighbors(state, player, node):
                if nbr not in visited:
                    visited.add(nbr)
                    q.append(nbr)
        return None

    @staticmethod
    def _step_toward(state: GameState, player: PlayerId, from_node: NodeId,
                     to_node: NodeId) -> NodeId | None:
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
