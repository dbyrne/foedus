"""ValueGreedy — Bundle 5b (C3) aware: prefers high-value unowned supplies.

Strategy:
  Like GreedyHold, but the "nearest unowned supply" BFS is replaced with
  "highest-value reachable unowned supply, tiebreak by distance".

  Rationale: in a 15-turn game, a value=2 supply at distance 3 yields
  ~12 score over the remaining horizon, vs ~14 for a value=1 supply at
  distance 1. Pure distance-greedy misses the better target. Value-first
  with distance tiebreak captures the right ranking on the typical map
  where high-value supplies are sparse.

Press: ALLY toward the closest-supply opponent (matches GreedyHold).
"""

from __future__ import annotations

from collections import deque

from foedus.agents.heuristics._tiebreak import shuffled_neighbors
from foedus.agents.heuristics.greedy_hold import GreedyHold
from foedus.core import (
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


class ValueGreedy:
    def __init__(self) -> None:
        self._inner = GreedyHold()

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
        # If sitting on an unowned supply, hold to flip (rule b).
        if m.is_supply(unit.location) \
                and state.ownership.get(unit.location) != player:
            return Hold()
        target = self._best_unowned_supply(state, player, unit.location)
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
        return self._inner.choose_press(state, player)

    def chat_drafts(self, state, player):
        return []

    @staticmethod
    def _best_unowned_supply(state: GameState, player: PlayerId,
                             start: NodeId) -> NodeId | None:
        """BFS the map and pick the unowned supply with the highest
        expected remaining-game ROI: `value * max(1, turns_remaining - d)`.

        Naive "highest value first" loses turns chasing distant +2 prizes
        when nearby value=1 supplies would yield more total score over the
        remaining horizon. ROI form picks value=1@d=1 over value=2@d=10
        when the game has 15 turns left, but value=2@d=2 over value=1@d=1.
        Distance tiebreak uses node id for determinism.
        """
        m = state.map
        dist: dict[NodeId, int] = {start: 0}
        q: deque[NodeId] = deque([start])
        while q:
            node = q.popleft()
            for nbr in shuffled_neighbors(state, player, node):
                if nbr not in dist:
                    dist[nbr] = dist[node] + 1
                    q.append(nbr)
        best: NodeId | None = None
        best_key: tuple[int, int, int] = (-(10**9), 0, 0)
        for n, d in dist.items():
            if n == start:
                continue
            if not m.is_supply(n):
                continue
            if state.ownership.get(n) == player:
                continue
            value = m.supply_value(n)
            # `value - d` is the "premium budget": a value=2 supply at d=1
            # scores 1 (better than nearest value=1 at d=1, score 0). A
            # value=2 at d=3 scores -1 — the detour costs more than the
            # bonus payout, so a closer value=1 wins. Distance tiebreaks
            # then prefer the nearest, then lowest node id.
            score = value - d
            key = (score, -d, -n)
            if key > best_key:
                best_key = key
                best = n
        return best

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
