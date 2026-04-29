"""AntiLeader — coordinates with non-leader allies to attack the leader.

Strategy:
  Identify leader = opponent with most supplies (tie -> lowest pid).
  Press: HOSTILE toward leader, ALLY toward each non-leader survivor
    so coalition cross-supports can fire alliance bonus + leverage.
    Publishes Move-on-leader-territory intents so other AntiLeaders
    can SupportMove our attacks.
  Orders:
    Phase 1: For each owned unit, check if any *other non-leader* player
      has declared a Move-on-leader-territory intent we can geographically
      support. If yes, SupportMove it (cross-support coordinated attack).
    Phase 2: Remaining units walk/Move toward leader's territory (the
      original AntiLeader behavior).
  Aid: spend tokens on each cross-support we plan to make so the
    alliance bonus + leverage accumulate on the supports.

Bundle 4 turns the previously-toothless AntiLeader into a real coalition
mechanism: combat reward + supporter reward make every successful
dislodgement of the leader directly score-positive for all uncut
cross-player supporters of the attack.
"""

from __future__ import annotations

from collections import deque

from foedus.agents.heuristics._tiebreak import shuffled_neighbors
from foedus.core import (
    AidSpend, Hold, Intent, Move, Order, Press, Stance, SupportMove, UnitId,
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
        # Find leader's owned supply nodes (set for O(1) membership).
        leader_supplies = {
            n for n, o in state.ownership.items() if o == leader
            and state.map.is_supply(n)
        }
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        used: set = set()
        # Phase 1: cross-support other non-leader players' attacks on leader.
        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid == leader:
                continue
            if other_pid in state.eliminated:
                continue
            for intent in press.intents:
                ord_ = intent.declared_order
                if not isinstance(ord_, Move):
                    continue
                if ord_.dest not in leader_supplies:
                    continue
                target_unit = state.units.get(intent.unit_id)
                if target_unit is None or target_unit.owner != other_pid:
                    continue
                # Find one of our units adjacent to the destination.
                for u in my_units:
                    if u.id in used:
                        continue
                    if not m.is_adjacent(u.location, ord_.dest):
                        continue
                    if u.location == ord_.dest:
                        continue
                    orders[u.id] = SupportMove(
                        target=intent.unit_id,
                        target_dest=ord_.dest,
                    )
                    used.add(u.id)
                    break
        # Phase 2: remaining units walk/attack toward leader.
        for unit in my_units:
            if unit.id in used:
                continue
            orders[unit.id] = self._step_toward_leader(
                state, player, unit, leader_supplies
            )
        return orders

    def _step_toward_leader(self, state, player, unit, leader_supplies):
        m = state.map
        # Adjacent to leader territory → Move in.
        for nbr in shuffled_neighbors(state, player, unit.location):
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
        next_step = self._step_toward(state, player, unit.location, target)
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
    def _step_toward(state, player, from_node, to_node):
        m = state.map
        dist = {to_node: 0}
        q = deque([to_node])
        while q:
            node = q.popleft()
            for nbr in shuffled_neighbors(state, player, node):
                if nbr not in dist:
                    dist[nbr] = dist[node] + 1
                    q.append(nbr)
        best = None
        best_d = float("inf")
        for nbr in shuffled_neighbors(state, player, from_node):
            d = dist.get(nbr, float("inf"))
            if d < best_d:
                best_d = d
                best = nbr
        return best

    def choose_press(self, state, player):
        leader = self._find_leader(state, player)
        if leader is None:
            return Press(stance={}, intents=[])
        # HOSTILE to leader, ALLY to other non-leaders so coalition supports
        # pass the mutual-ALLY gate. Publish own attack intents so other
        # AntiLeaders see our planned moves and can cross-support them.
        stance = {leader: Stance.HOSTILE}
        for p in range(state.config.num_players):
            if p == player or p == leader or p in state.eliminated:
                continue
            stance[p] = Stance.ALLY
        # Compute *attack-only* planned orders for intents (not full
        # cross-supports; those depend on others' intents this round).
        leader_supplies = {
            n for n, o in state.ownership.items() if o == leader
            and state.map.is_supply(n)
        }
        intents = []
        for unit in state.units.values():
            if unit.owner != player:
                continue
            order = self._step_toward_leader(
                state, player, unit, leader_supplies
            )
            if isinstance(order, Move) and order.dest in leader_supplies:
                intents.append(Intent(
                    unit_id=unit.id,
                    declared_order=order,
                    visible_to=None,
                ))
        return Press(stance=stance, intents=intents)

    def choose_aid(self, state, player):
        """Bundle 4: back each cross-support we plan against the leader."""
        balance = state.aid_tokens.get(player, 0)
        if balance <= 0:
            return []
        if not state.press_history:
            return []
        last = state.press_history[-1]
        my_prev = last.get(player)
        if my_prev is None:
            return []
        leader = self._find_leader(state, player)
        if leader is None:
            return []
        leader_supplies = {
            n for n, o in state.ownership.items() if o == leader
            and state.map.is_supply(n)
        }
        m = state.map
        my_units = [u for u in state.units.values() if u.owner == player]
        used: set = set()
        spends: list = []
        for other_pid, press in state.round_press_pending.items():
            if other_pid == player or other_pid == leader:
                continue
            if other_pid in state.eliminated:
                continue
            their_prev = last.get(other_pid)
            if their_prev is None:
                continue
            if my_prev.stance.get(other_pid, Stance.NEUTRAL) != Stance.ALLY:
                continue
            if their_prev.stance.get(player, Stance.NEUTRAL) != Stance.ALLY:
                continue
            for intent in press.intents:
                ord_ = intent.declared_order
                if not isinstance(ord_, Move):
                    continue
                if ord_.dest not in leader_supplies:
                    continue
                target_unit = state.units.get(intent.unit_id)
                if target_unit is None or target_unit.owner != other_pid:
                    continue
                # Need one of our units adjacent to the dest (so we'd
                # actually back this with a SupportMove in choose_orders).
                for u in my_units:
                    if u.id in used:
                        continue
                    if not m.is_adjacent(u.location, ord_.dest):
                        continue
                    if u.location == ord_.dest:
                        continue
                    spends.append(AidSpend(
                        target_unit=intent.unit_id,
                        target_order=ord_,
                    ))
                    used.add(u.id)
                    break
                if len(spends) >= balance:
                    break
            if len(spends) >= balance:
                break
        return spends[:balance]

    def chat_drafts(self, state, player):
        return []
