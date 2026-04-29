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
