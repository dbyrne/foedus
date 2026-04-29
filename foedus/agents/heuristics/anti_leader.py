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

from foedus.core import Hold, Move, Order, Press, Stance, UnitId


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
        # Find leader's owned supply nodes (set for O(1) membership).
        leader_supplies = {
            n for n, o in state.ownership.items() if o == leader
            and state.map.is_supply(n)
        }
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
            key=lambda n: (self._dist(state, unit.location, n), n),
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
