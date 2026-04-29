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
